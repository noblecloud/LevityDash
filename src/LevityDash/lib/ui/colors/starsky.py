"""Draws the real night sky (``lib/skymap.py``) into a pixmap the dashboard's ground blits.

The pixmap is rebuilt only when what it shows changes: the sky has turned a few minutes, the light has changed enough to
show or hide a magnitude, or the dashboard was resized. Between those a repaint is one ``drawPixmap``. Stars are soft
points (a small radial gradient, anti-aliased at sub-pixel positions), sized and brightened by magnitude and tinted by
colour temperature; the brightest get a faint halo.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap, QRadialGradient

from LevityDash.lib import skymap
from LevityDash.lib.ui.colors import backdrop

#: How often the sky is redrawn as it turns (it moves a quarter of a degree a minute).
REFRESH = 300
PLANET_COLORS = {'Venus': (255, 248, 230), 'Mars': (255, 170, 120), 'Jupiter': (255, 240, 215), 'Saturn': (250, 232, 190), 'Mercury': (235, 235, 235)}


def _soft(painter: QPainter, x: float, y: float, radius: float, rgb: tuple, alpha: float, falloff: float = 0.45) -> None:
	gradient = QRadialGradient(QPointF(x, y), radius)
	a = max(0.0, min(1.0, alpha))
	gradient.setColorAt(0.0, QColor(*rgb, round(255 * a)))
	gradient.setColorAt(falloff, QColor(*rgb, round(255 * a * 0.55)))
	gradient.setColorAt(1.0, QColor(*rgb, 0))
	painter.setBrush(gradient)
	painter.drawEllipse(QPointF(x, y), radius, radius)


def _horizonFade(x: float, y: float) -> float:
	"""Stars low over the horizon are dimmed by the air they shine through."""
	r = math.hypot(x, y)
	t = min(1.0, max(0.0, (r - 0.78) / 0.22))
	return 1.0 - 0.75 * t * t * (3 - 2 * t)


class StarLayer:
	"""One dashboard's star pixmap and what it was built from."""

	def __init__(self):
		self._key = None
		self._pixmap: Optional[QPixmap] = None

	def limit(self, base: float, elevation: Optional[float], haze: Optional[float], moon: float) -> float:
		"""The faintest magnitude visible now: twilight, cloud and the moon each take faint stars away. Steps of half a magnitude."""
		cloud = min(1.0, max(0.0, haze)) if haze is not None else 0.0
		limit = base - 3.5 * (1 - backdrop.twilight(elevation)) - 2.5 * cloud - 2.0 * moon
		return round(max(1.0, limit) * 2) / 2

	def pixmap(self, size: QRectF, scale: float, spec, elevation: Optional[float], haze: Optional[float]) -> Optional[QPixmap]:
		base = backdrop.starLimit(spec)
		if base is None:
			return None
		options = backdrop.starOptions(spec)
		lat, lon = _place(options)
		when = _when(options)
		bucket = int(when.timestamp() // REFRESH) if 'star-time' not in options else when.timestamp()
		moon = round(skymap.moonlight(lat, lon, when) * 4) / 4
		limit = self.limit(base, elevation, haze, moon)
		scale = max(0.5, min(3.0, round(scale * 4) / 4))
		key = (round(size.width()), round(size.height()), scale, limit, lat, lon, bucket)
		if key != self._key:
			self._key, self._pixmap = key, self._render(size, scale, limit, lat, lon, when)
		return self._pixmap

	def _render(self, size: QRectF, scale: float, limit: float, lat: float, lon: float, when: datetime) -> QPixmap:
		w, h = size.width(), size.height()
		pixmap = QPixmap(max(1, round(w * scale)), max(1, round(h * scale)))
		pixmap.setDevicePixelRatio(scale)
		pixmap.fill(Qt.transparent)
		painter = QPainter(pixmap)
		painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
		painter.setPen(Qt.NoPen)
		radius, cx, cy = max(w, h) * 0.62, w / 2, h / 2
		k = min(w, h) / 900.0
		margin = 12 * k + 12
		for x, y, mag, kelvin in skymap.project(lat, lon, when, limit):
			px, py = cx + x * radius, cy + y * radius
			if not (-margin <= px <= w + margin and -margin <= py <= h + margin):
				continue
			self._star(painter, px, py, mag, skymap.color(kelvin), _horizonFade(x, y), k)
		for x, y, mag, name in skymap.planets(lat, lon, when):
			px, py = cx + x * radius, cy + y * radius
			if -margin <= px <= w + margin and -margin <= py <= h + margin:
				self._star(painter, px, py, mag, PLANET_COLORS.get(name, (255, 255, 255)), _horizonFade(x, y), k, planet=True)
		painter.end()
		return pixmap

	@staticmethod
	def _star(painter, x, y, mag, rgb, fade, k, planet=False):
		core = max(0.7, k * (0.75 + 0.5 * max(0.0, 5.2 - mag)))
		alpha = max(0.35, min(1.0, 0.35 + 0.65 * (5.8 - mag) / 5.0)) * fade
		if mag < 3.2 or planet:
			_soft(painter, x, y, core * 5.0, rgb, 0.30 * alpha, falloff=0.25)
		_soft(painter, x, y, core * 2.0, rgb, alpha)


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
