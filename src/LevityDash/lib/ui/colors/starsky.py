"""Draws the real night sky (``lib/skymap.py``) for a dashboard's ground.

Stars are splatted into a float image at the screen's own pixel density (so a 2x display gets 2x the pixels, not a
scaled-up 1x picture): each is a tight bright core plus a faint wider skirt, and the brightest a halo, with the
brightness following the physical flux of its magnitude through a tone curve so most stars are faint pinpricks and a
handful stand out. Colours come from the colour temperature, more saturated on the brighter stars. Under them is the
Milky Way, drawn from the galactic plane's real geometry at low resolution and scaled up (it is soft), and a trace of
airglow low on the horizon.

Building takes a moment of numpy, so it runs on a worker thread (unless the sky is pinned for a render) and the old
picture stays until the new one arrives; a repaint in between is one ``drawPixmap``.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Callable, Optional

import numpy as np
from PySide6.QtCore import QObject, QRectF, QRunnable, QThreadPool, Qt, Signal
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPixmap

from LevityDash.lib import skymap
from LevityDash.lib.ui.colors import backdrop

#: How often the sky is redrawn as it turns (it moves a quarter of a degree a minute).
REFRESH = 300
PLANET_COLORS = {'Venus': (255, 248, 230), 'Mars': (255, 170, 120), 'Jupiter': (255, 240, 215), 'Saturn': (250, 232, 190), 'Mercury': (235, 235, 235)}
#: Photographic tone curve: the exposure and the gamma the light is encoded with.
EXPOSURE, ENCODE = 2.4, 0.78
MILKY_WAY_ALPHA = 0.36
AIRGLOW = (0.40, 0.75, 0.62)


def _lin(rgb) -> np.ndarray:
	return (np.asarray(rgb, dtype=np.float32) / 255.0) ** 2.2


def _horizonFade(r: float) -> float:
	"""Stars low over the horizon are dimmed by the air they shine through."""
	t = min(1.0, max(0.0, (r - 0.78) / 0.22))
	return 1.0 - 0.75 * t * t * (3 - 2 * t)


def _jitter(x: float, y: float) -> float:
	"""A stable 0-1 number per place, so no two stars come out the same size."""
	v = math.sin(x * 12.9898 + y * 78.233) * 43758.5453
	return v - math.floor(v)


def _gauss(acc: np.ndarray, px: float, py: float, sigma: float, amp: np.ndarray, reach: float = 4.0, channel: Optional[int] = None) -> None:
	"""Add ``amp`` (an RGB triple) times a Gaussian of ``sigma`` device pixels, centred on a sub-pixel position
	(to one colour ``channel`` only, when given: ``amp`` is then that channel's number)."""
	n = int(math.ceil(reach * sigma)) + 1
	height, width = acc.shape[1:]
	x0, x1, y0, y1 = max(0, int(math.floor(px)) - n), min(width, int(math.floor(px)) + n + 1), max(0, int(math.floor(py)) - n), min(height, int(math.floor(py)) + n + 1)
	if x0 >= x1 or y0 >= y1:
		return
	gx = np.exp(-((np.arange(x0, x1, dtype=np.float32) + 0.5 - px) ** 2) / (2 * sigma * sigma))
	gy = np.exp(-((np.arange(y0, y1, dtype=np.float32) + 0.5 - py) ** 2) / (2 * sigma * sigma))
	patch = gy[:, None] * gx[None, :]
	if channel is None:
		acc[:, y0:y1, x0:x1] += amp[:, None, None] * patch[None]
	else:
		acc[channel, y0:y1, x0:x1] += amp * patch


#: Lateral chromatic aberration: red lands this share further out from the centre of the picture than green, blue this much
#: further in, so a star's colours part more towards the corners (0.0008 is about 2 pixels at the edge of a 2x screen).
ABERRATION = 0.0008


def _fringe(acc, px, py, sigma, amp, aberration, centre, reach=4.0):
	"""``_gauss`` with the three colours at slightly different distances from ``centre`` (see ABERRATION)."""
	if not aberration:
		_gauss(acc, px, py, sigma, amp, reach)
		return
	dx, dy = px - centre[0], py - centre[1]
	for channel, shift in ((0, 1.0), (1, 0.0), (2, -1.0)):
		k = 1.0 + aberration * shift
		_gauss(acc, centre[0] + dx * k, centre[1] + dy * k, sigma, float(amp[channel]), reach, channel)


def _splat(acc, px, py, mag, rgb, fade, scale, planet=False, aberration=0.0, centre=(0, 0)):
	flux = 10 ** (-0.4 * 0.45 * (mag - 1.5))  # the flux curve, flattened by a gamma so faint stars stay visible
	peak = min(flux, 6.0) * fade * (1.0 + 0.25 * (planet))
	size = (0.7 + 0.3 * scale) * (0.5 + 0.16 * max(0.0, 3.5 - mag)) * (0.88 + 0.24 * _jitter(px, py))
	whiteness = 0.52 - 0.26 * min(1.0, flux)
	tint = _lin(tuple(int(round(c + (255 - c) * whiteness)) for c in rgb))
	tint = tint / tint.max()
	_fringe(acc, px, py, size, tint * peak, aberration, centre)
	_fringe(acc, px, py, size * 2.6, tint * peak * 0.10, aberration, centre)
	if flux > 0.7:
		_fringe(acc, px, py, size * 7.0, tint * peak * 0.035, aberration, centre, reach=3.0)
	if mag < 0.3 and not planet:
		_glints(acc, px, py, size, tint * peak * 0.05)


def _glints(acc, px, py, size, amp) -> None:
	"""Very faint diffraction spikes on the few brightest stars: a thin cross, fading with distance."""
	length = size * 16
	n = int(length)
	height, width = acc.shape[1:]
	ix, iy = int(px), int(py)
	for axis in (0, 1):
		for step in range(-n, n + 1):
			x, y = (ix + step, iy) if axis == 0 else (ix, iy + step)
			if 0 <= x < width and 0 <= y < height:
				acc[:, y, x] += amp * math.exp(-abs(step) / (length * 0.32))


def _stars(size: tuple, scale: float, lat: float, lon: float, when: datetime, limit: float, aberration: float = ABERRATION) -> QImage:
	w, h = size
	W, H = max(1, round(w * scale)), max(1, round(h * scale))
	acc = np.zeros((3, H, W), dtype=np.float32)
	radius, cx, cy = max(W, H) * 0.62, W / 2, H / 2
	margin = 14 * scale
	for x, y, mag, kelvin in skymap.project(lat, lon, when, limit):
		px, py = cx + x * radius, cy + y * radius
		if -margin <= px <= W + margin and -margin <= py <= H + margin:
			_splat(acc, px, py, mag, skymap.color(kelvin, 0.0), _horizonFade(math.hypot(x, y)), scale, aberration=aberration, centre=(cx, cy))
	for x, y, mag, name in skymap.planets(lat, lon, when):
		px, py = cx + x * radius, cy + y * radius
		if -margin <= px <= W + margin and -margin <= py <= H + margin:
			_splat(acc, px, py, mag, PLANET_COLORS.get(name, (255, 255, 255)), _horizonFade(math.hypot(x, y)), scale, planet=True, aberration=aberration, centre=(cx, cy))
	light = (1.0 - np.exp(-EXPOSURE * acc)) ** ENCODE
	return _pack(light, light.max(axis=0))


def _pack(rgb: np.ndarray, alpha: np.ndarray) -> QImage:
	"""A premultiplied ARGB image from light (3, H, W) and its coverage (H, W)."""
	a = np.clip(alpha, 0, 1)
	c = np.minimum(np.clip(rgb, 0, 1), a[None])
	packed = ((a * 255 + 0.5).astype(np.uint32) << 24) | ((c[0] * 255 + 0.5).astype(np.uint32) << 16) | ((c[1] * 255 + 0.5).astype(np.uint32) << 8) | (c[2] * 255 + 0.5).astype(np.uint32)
	packed = np.ascontiguousarray(packed)
	image = QImage(packed.data, packed.shape[1], packed.shape[0], packed.shape[1] * 4, QImage.Format.Format_ARGB32_Premultiplied)
	return image.copy()  # own the memory


def _milkyWay(size: tuple, lat: float, lon: float, when: datetime, strength: float) -> QImage:
	"""The Milky Way and the airglow at 1/6 of the picture's resolution (they have no fine detail)."""
	w, h = size
	nx, ny = max(8, int(w // 6)), max(8, int(h // 6))
	radius = max(nx, ny) * 0.62
	xs = (np.arange(nx, dtype=np.float32) + 0.5 - nx / 2) / radius
	ys = (np.arange(ny, dtype=np.float32) + 0.5 - ny / 2) / radius
	x, y = np.meshgrid(xs, ys)
	brightness, warmth, r = skymap.milkyway(lat, lon, when, x, y)
	up = (r <= 1.0)
	edge = np.clip((1.0 - r) / 0.04, 0, 1)
	arms, bulge = _lin((190, 205, 255)), _lin((255, 232, 196))
	color = arms[:, None, None] * (1 - warmth)[None] + bulge[:, None, None] * warmth[None]
	band = brightness * strength * MILKY_WAY_ALPHA * up * edge
	glow = np.clip((r - 0.80) / 0.17, 0, 1) ** 2 * np.clip((1.0 - r) / 0.06, 0, 1) * 0.10 * up
	light = color * band[None] + _lin(tuple(int(c * 255) for c in AIRGLOW))[:, None, None] * glow[None]
	light = np.clip(light, 0, 1) ** ENCODE
	return _pack(light, light.max(axis=0))


class _Done(QObject):
	finished = Signal(object, object)


class _Build(QRunnable):
	def __init__(self, key, args, done: _Done):
		super().__init__()
		self.key, self.args, self.done = key, args, done

	def run(self):
		try:
			stars, milky = _render(*self.args)
		except Exception:  # a failed build leaves the old sky up; the next refresh tries again
			stars = milky = None
		self.done.finished.emit(self.key, (stars, milky))


def _render(size, scale, lat, lon, when, limit, strength, aberration=ABERRATION):
	return _stars(size, scale, lat, lon, when, limit, aberration), (_milkyWay(size, lat, lon, when, strength) if strength > 0.02 else None)


class StarLayer:
	"""One dashboard's sky: the images, built off-thread when the clock is live, and the pixmap composed from them."""

	def __init__(self, onReady: Optional[Callable[[], None]] = None):
		self._onReady = onReady
		self._built = None  # (key, (stars image, milky way image))
		self._building = None
		self._wanted = None
		self._pixmap: Optional[QPixmap] = None
		self._pixKey = None
		self._done = _Done()
		self._done.finished.connect(self._finish)

	def limit(self, base: float, elevation: Optional[float], haze: Optional[float], moon: float) -> float:
		"""The faintest magnitude visible now: twilight, cloud and the moon each take faint stars away. Steps of half a magnitude."""
		cloud = min(1.0, max(0.0, haze)) if haze is not None else 0.0
		limit = base - 3.5 * (1 - backdrop.twilight(elevation)) - 2.5 * cloud - 0.8 * moon
		return round(max(1.0, limit) * 2) / 2

	def pixmap(self, size: QRectF, scale: float, spec, elevation: Optional[float], haze: Optional[float], occlusion: Optional[QPainterPath] = None) -> Optional[QPixmap]:
		base = backdrop.starLimit(spec)
		if base is None:
			return None
		options = backdrop.starOptions(spec)
		lat, lon = _place(options)
		when = _when(options)
		pinned = 'star-time' in options
		bucket = when.timestamp() if pinned else int(when.timestamp() // REFRESH)
		moon = round(skymap.moonlight(lat, lon, when) * 4) / 4
		limit = self.limit(base, elevation, haze, moon)
		strength = 0.0 if options.get('milky-way') is False else min(1.0, max(0.0, (limit - 3.5) / 2.0))
		scale = max(0.5, min(3.0, round(scale * 4) / 4))
		key = (round(size.width()), round(size.height()), scale, limit, lat, lon, bucket, round(strength, 1), options.get('star-aberration', 1.0))
		aberration = ABERRATION * float(options.get('star-aberration', 1.0))
		args = ((round(size.width()), round(size.height())), scale, lat, lon, when, limit, round(strength, 1), aberration)
		if self._built is None or self._built[0] != key:
			if pinned:
				self._built = (key, _render(*args))
			else:
				self._wanted = (key, args)
				self._start()
		hidden = tuple(round(v) for v in occlusion.boundingRect().getRect()) + (occlusion.elementCount(),) if occlusion is not None and not occlusion.isEmpty() else None
		if self._built is not None and self._pixKey != (self._built[0], hidden):
			self._pixmap = self._compose(size, self._built[0][2], self._built[1], occlusion)
			self._pixKey = (self._built[0], hidden)
		return self._pixmap

	def _start(self) -> None:
		if self._building is not None or self._wanted is None:
			return
		key, args = self._wanted
		self._building = key
		QThreadPool.globalInstance().start(_Build(key, args, self._done))

	def _finish(self, key, images) -> None:
		self._building = None
		if images[0] is not None:
			self._built = (key, images)
			self._pixKey = None
			if self._onReady:
				self._onReady()
		if self._wanted is not None and self._wanted[0] != key:
			self._start()

	@staticmethod
	def _compose(size: QRectF, scale: float, images: tuple, occlusion: Optional[QPainterPath]) -> QPixmap:
		stars, milky = images
		w, h = size.width(), size.height()
		pixmap = QPixmap(stars.width(), stars.height())
		pixmap.setDevicePixelRatio(stars.width() / w if w else scale)
		pixmap.fill(Qt.transparent)
		painter = QPainter(pixmap)
		painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
		target = QRectF(0, 0, w, h)
		if milky is not None:
			painter.drawImage(target, milky)
		painter.drawImage(target, stars)
		if occlusion is not None and not occlusion.isEmpty():
			# Cut out what hides the stars (a moon's disc, an item that says `occludes-stars`).
			painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
			painter.setPen(Qt.NoPen)
			painter.setBrush(Qt.black)
			painter.drawPath(occlusion.translated(-size.left(), -size.top()))
		painter.end()
		return pixmap


def _place(options: dict) -> tuple:
	place = options.get('star-place')
	if isinstance(place, (list, tuple)) and len(place) == 2:
		return float(place[0]), float(place[1])
	from LevityDash.lib.config import userConfig
	return float(userConfig.lat), float(userConfig.lon)


def _when(options: dict) -> datetime:
	pinned = options.get('star-time')
	if pinned:
		when = pinned if isinstance(pinned, datetime) else datetime.fromisoformat(str(pinned))
		return when if when.tzinfo else when.replace(tzinfo=timezone.utc)
	return datetime.now(timezone.utc)
