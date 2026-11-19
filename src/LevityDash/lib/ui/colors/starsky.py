"""Draws the real night sky (``lib/skymap.py``) for a dashboard's ground.

Stars are splatted into a float image at the screen's own pixel density (so a 2x display gets 2x the pixels, not a
scaled-up 1x picture). The few hundred bright ones each get a tight core, a faint skirt and on the brightest a halo and
glints, with a touch of lateral chromatic aberration; the tens of thousands of faint ones (to magnitude 8, the dust a
long exposure shows) are one vectorised pass of tiny Gaussians. Brightness follows each star's flux through a tone
curve, dimmed by the air it shines through near the horizon, and colour follows its B-V index.

Under them is the Milky Way, sampled from a photograph of the whole galaxy (NASA's Deep Star Maps, built from ESA's Gaia
star counts; ``resources/data/milkyway.jpg``, galactic coordinates) at the place each pixel looks at, so the dust lanes,
the Rift, the bright Sagittarius clouds and the Magellanic Clouds are where they are in the real sky, plus a trace of
airglow low on the horizon. The picture is dithered so its faint gradients do not band.

Building takes a moment of numpy, so it runs on a worker thread (unless the sky is pinned for a render) and the old
picture stays until the new one arrives; a repaint in between is one ``drawPixmap``.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
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
#: Stars brighter than this are drawn one by one (core, skirt, halo, aberration); fainter ones in one vectorised pass.
BRIGHT = 4.5
#: Magnitudes lost per airmass: low stars dim (and the faint ones vanish) in the thick air near the horizon.
EXTINCTION = 0.28
AIRGLOW = (0.40, 0.75, 0.62)

#: The Milky Way picture: galactic longitude 0 in the middle, increasing to the left; latitude +50 at the top to -50 at
#: the bottom. Its pixels are an asinh stretch of linear light; MW_STRETCH undoes it.
MILKY_WAY = Path(__file__).resolve().parents[3] / 'resources' / 'data' / 'milkyway.jpg'
MW_STRETCH, MW_TOP = 0.02, 0.9089218378067017
MW_LATITUDE = 50.0
#: How bright the Milky Way is drawn against the stars (linear light, before the tone curve).
MW_GAIN = 1.0


def _lin(rgb) -> np.ndarray:
	return (np.asarray(rgb, dtype=np.float32) / 255.0) ** 2.2


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


def _splat(acc, px, py, mag, rgb, fade, scale, planet=False, aberration=0.0, centre=(0, 0), bv=None):
	"""One bright star (or planet): a core, a faint skirt, a halo on the brightest and glints on the very brightest.
	Its colour is ``rgb`` (0-255) or, for a star, its B-V index ``bv``, more saturated the brighter it is."""
	flux = 10 ** (-0.4 * 0.45 * (mag - 1.5))
	peak = min(flux, 6.0) * fade * (1.0 + 0.25 * (planet))
	size = (0.7 + 0.3 * scale) * (0.5 + 0.16 * max(0.0, 3.5 - mag)) * (0.88 + 0.24 * _jitter(px, py))
	whiteness = 0.40 - 0.22 * min(1.0, flux)
	if rgb is None:
		rgb = skymap.color(float(skymap.kelvin(bv)), 0.0)
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


def _extinct(alt) -> np.ndarray:
	"""Magnitudes added by the air at altitude ``alt``."""
	return EXTINCTION * (np.minimum(skymap.airmass(alt), 12.0) - 1.0)


@lru_cache(maxsize=4)
def _tints(whiteness: float) -> np.ndarray:
	"""Linear RGB (rows) for B-V from -0.4 to 2.0 in steps of 0.05, each normalised to its brightest channel."""
	rows = []
	for bv in np.arange(-0.4, 2.0001, 0.05):
		tint = _lin(skymap.color(float(skymap.kelvin(bv)), whiteness))
		rows.append(tint / tint.max())
	return np.array(rows, dtype=np.float32)


def _tint(bv, whiteness: float) -> np.ndarray:
	return _tints(whiteness)[np.clip(np.round((np.asarray(bv) + 0.4) / 0.05).astype(int), 0, 48)]


def _peak(mag):
	"""The flux curve, flattened by a gamma so faint stars stay visible."""
	return np.minimum(10 ** (-0.4 * 0.45 * (np.asarray(mag) - 1.5)), 6.0)


def _faintPeak(mag):
	"""Below BRIGHT the curve steepens back towards the physical one, so the thousands of faint stars span a real range
	of brightness (a few distinct, most barely there) rather than one even sprinkle."""
	return _peak(BRIGHT) * 10 ** (-0.4 * 0.9 * (np.asarray(mag) - BRIGHT))


def _dust(acc: np.ndarray, px: np.ndarray, py: np.ndarray, amp: np.ndarray, sigma: float) -> None:
	"""Add many small Gaussians at once: ``amp`` is (N, 3) peak light, positions in device pixels."""
	if not len(px):
		return
	height, width = acc.shape[1:]
	reach = 1 if sigma < 0.7 else 2
	ix, iy = np.floor(px).astype(np.int64), np.floor(py).astype(np.int64)
	star = np.arange(len(px))
	index, weight, owner = [], [], []
	for dy in range(-reach, reach + 1):
		for dx in range(-reach, reach + 1):
			x, y = ix + dx, iy + dy
			inside = (x >= 0) & (x < width) & (y >= 0) & (y < height)
			index.append((y * width + x)[inside])
			weight.append(np.exp(-((x + 0.5 - px) ** 2 + (y + 0.5 - py) ** 2) / (2 * sigma * sigma))[inside])
			owner.append(star[inside])
	index, weight, owner = np.concatenate(index), np.concatenate(weight), np.concatenate(owner)
	for channel in range(3):
		acc[channel] += np.bincount(index, weights=weight * amp[owner, channel], minlength=width * height).reshape(height, width).astype(np.float32)


def _stars(size: tuple, scale: float, lat: float, lon: float, when: datetime, limit: float, aberration: float = ABERRATION) -> QImage:
	w, h = size
	W, H = max(1, round(w * scale)), max(1, round(h * scale))
	acc = np.zeros((3, H, W), dtype=np.float32)
	radius, cx, cy = max(W, H) * 0.62, W / 2, H / 2
	margin = 14 * scale
	faintest = min(skymap.FAINTEST, limit + 2.5)
	x, y, mag, bv = skymap.project(lat, lon, when, faintest)
	px, py = cx + x * radius, cy + y * radius
	alt = math.pi / 2 - 2 * np.arctan(np.hypot(x, y))
	seen = mag + _extinct(alt)
	keep = (px >= -margin) & (px <= W + margin) & (py >= -margin) & (py <= H + margin) & (seen <= faintest)
	px, py, mag, bv, seen = px[keep], py[keep], mag[keep], bv[keep], seen[keep]
	bright = mag < BRIGHT
	for X, Y, m, s, c in zip(px[bright], py[bright], mag[bright], seen[bright], bv[bright]):
		_splat(acc, X, Y, s, None, 1.0, scale, aberration=aberration, centre=(cx, cy), bv=c)
	faint = ~bright
	fade = np.clip(faintest - seen[faint], 0.0, 1.0)  # the last magnitude before the cut fades out, so there is no edge
	amp = _tint(bv[faint], 0.45) * (_faintPeak(seen[faint]) * fade)[:, None]
	_dust(acc, px[faint], py[faint], amp.astype(np.float32), 0.42 + 0.22 * scale)
	for X, Y, m, name in skymap.planets(lat, lon, when):
		PX, PY = cx + X * radius, cy + Y * radius
		if -margin <= PX <= W + margin and -margin <= PY <= H + margin:
			alt = math.pi / 2 - 2 * math.atan(math.hypot(X, Y))
			_splat(acc, PX, PY, m + float(_extinct(alt)), PLANET_COLORS.get(name, (255, 255, 255)), 1.0, scale, planet=True, aberration=aberration, centre=(cx, cy))
	light = (1.0 - np.exp(-EXPOSURE * acc)) ** ENCODE
	return _pack(light, light.max(axis=0))


def _pack(rgb: np.ndarray, alpha: np.ndarray, dither: bool = False) -> QImage:
	"""A premultiplied ARGB image from light (3, H, W) and its coverage (H, W). ``dither`` adds a triangular half-step of
	noise before rounding, so smooth faint gradients do not break into bands."""
	a = np.clip(alpha, 0, 1)
	c = np.minimum(np.clip(rgb, 0, 1), a[None])
	scaleA, scaleC = a * 255, c * 255
	if dither:
		rng = np.random.default_rng(7)
		noise = (rng.random(a.shape, dtype=np.float32) - rng.random(a.shape, dtype=np.float32))
		scaleA = scaleA + noise
		scaleC = scaleC + noise[None]
		scaleC = np.minimum(np.maximum(scaleC, 0), np.maximum(scaleA, 0)[None])
	A = np.clip(scaleA + 0.5, 0, 255).astype(np.uint32)
	C = np.clip(scaleC + 0.5, 0, 255).astype(np.uint32)
	C = np.minimum(C, A[None])
	packed = np.ascontiguousarray((A << 24) | (C[0] << 16) | (C[1] << 8) | C[2])
	image = QImage(packed.data, packed.shape[1], packed.shape[0], packed.shape[1] * 4, QImage.Format.Format_ARGB32_Premultiplied)
	return image.copy()  # own the memory


@lru_cache(maxsize=1)
def _milkyWayMap() -> tuple:
	"""The Milky Way picture as uint8 (H, W, 3) and the table from its pixel values to linear light."""
	image = QImage(str(MILKY_WAY)).convertToFormat(QImage.Format.Format_RGB888)
	width, height, stride = image.width(), image.height(), image.bytesPerLine()
	pixels = np.frombuffer(image.constBits(), dtype=np.uint8, count=stride * height).reshape(height, stride)[:, :width * 3]
	table = MW_STRETCH * np.sinh(np.arange(256, dtype=np.float32) / 255.0 * math.asinh(MW_TOP / MW_STRETCH))
	return pixels.reshape(height, width, 3).copy(), table.astype(np.float32)  # a copy: the QImage owns its bytes


def _sampleMilkyWay(l: np.ndarray, b: np.ndarray) -> np.ndarray:
	"""Linear RGB (3, ...) of the Milky Way at galactic longitude and latitude in degrees (bilinear)."""
	pixels, table = _milkyWayMap()
	height, width = pixels.shape[:2]
	u = (0.5 - ((l + 180.0) % 360.0 - 180.0) / 360.0) * width - 0.5
	v = (MW_LATITUDE - b) / (2 * MW_LATITUDE) * height - 0.5
	v = np.clip(v, 0, height - 1.001)
	i0, j0 = np.floor(u).astype(np.int64), np.floor(v).astype(np.int64)
	fu, fv = (u - i0).astype(np.float32), (v - j0).astype(np.float32)
	i0, i1 = i0 % width, (i0 + 1) % width
	out = np.empty((3,) + l.shape, dtype=np.float32)
	for c in range(3):
		top = table[pixels[j0, i0, c]] * (1 - fu) + table[pixels[j0, i1, c]] * fu
		bottom = table[pixels[j0 + 1, i0, c]] * (1 - fu) + table[pixels[j0 + 1, i1, c]] * fu
		out[c] = top * (1 - fv) + bottom * fv
	return out


def _milkyWay(size: tuple, lat: float, lon: float, when: datetime, strength: float) -> QImage:
	"""The Milky Way and the airglow, one pixel per logical pixel (the photograph has no finer detail than that on a
	2x screen; it is drawn smoothly scaled)."""
	w, h = size
	nx, ny = max(8, int(w)), max(8, int(h))
	radius = max(nx, ny) * 0.62
	xs = (np.arange(nx, dtype=np.float32) + 0.5 - nx / 2) / radius
	ys = (np.arange(ny, dtype=np.float32) + 0.5 - ny / 2) / radius
	x, y = np.meshgrid(xs, ys)
	l, b, alt = skymap.galacticChart(lat, lon, when, x, y)
	light = _sampleMilkyWay(l, b)
	edge = np.clip((MW_LATITUDE - np.abs(b)) / 8.0, 0, 1)  # the picture ends at |b| = 50, where there is nearly nothing left
	air = 10 ** (-0.4 * _extinct(alt)) * np.clip(alt / 0.03, 0, 1)
	light *= (edge * air * strength * MW_GAIN).astype(np.float32)[None]
	r = np.hypot(x, y)
	glow = np.clip((r - 0.80) / 0.17, 0, 1) ** 2 * np.clip((1.0 - r) / 0.06, 0, 1) * 0.04 * (alt > 0)
	light += _lin(tuple(int(c * 255) for c in AIRGLOW))[:, None, None] * glow[None].astype(np.float32)
	light = (1.0 - np.exp(-EXPOSURE * light)) ** ENCODE
	return _pack(light, light.max(axis=0), dither=True)


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
			painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)  # starlight adds to the glow behind it
		painter.drawImage(target, stars)
		painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
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
