"""`type: map`: a weather map in the dashboard's own colours.

```yaml
- type: map
  layer: radar                # radar | temperature | wind | clouds | none
  zoom: 7                     # 1 world .. 16 street; radar data stops at 7 and is stretched past that
  lat: 40.7                   # the centre; both left out: [Location] from the config
  lon: -74.0
  basemap: auto               # auto | dark | light | none; auto follows the theme's background
  labels: true                # place names over the data
  opacity: 0.9                # of the data layer; left out: 0.92 for radar, 0.74 for the fields
  animate: true               # radar: loop the last two hours; false shows the latest picture
  speed: 600                  # radar: milliseconds a frame shows (the newest one stays three times as long)
  refresh: 300                # radar: seconds between asking for new pictures
  marker: true                # a dot where [Location] is
  legend: true                # the colour scale, bottom left
  stamp: true                 # the layer's name and time, top left
  range: [0, 20]              # wind (m/s) and temperature (°C): the ends of the scale; temperature follows [Comfort] when left out
  tiles: https://example.org/{z}/{x}/{y}.png   # your own base map (XYZ), in place of the built-in one
```

`radar` is RainViewer's composite of national weather radars: the service paints its own colours, so each colour is
read back as an echo strength (`palette.rainviewerIntensity`) and drawn again in an Oklch palette that belongs to the
dashboard. `temperature`, `wind` and `clouds` come from one Open-Meteo request for a coarse grid of points over the view
(about 70, asked again every half hour), smoothed with a spline into a picture, so they show the pattern across the
region, not any one town. The temperature ramp's quiet middle is your `[Comfort]` range. Wind draws an arrow at each
grid point too.

The base map is Esri's grey canvas, read as sea and land and tinted with the theme's `background`, `text` and `faint`
so it sits in the dashboard instead of on it. Click the map to pause or resume the radar loop. Tiles are cached on disk.
Free services, no keys; their terms ask for credit, which is printed small in the corner.

Geometry lives in `geo.py`, the sources in `data.py`, colour in `palette.py`, spline smoothing in `field.py` and thread
handling in `loader.py`; this file reads the settings and paints.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QBrush
from PySide6.QtWidgets import QGraphicsItem

from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.stateful import StateProperty
from LevityDash.lib.ui.colors import theme
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.weathermap import data, palette
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.weathermap.field import upsample, wrapDegrees
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.weathermap.geo import Viewport
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.weathermap.loader import Loader, toArray, toImage
from LevityDash.lib.ui.frontends.PySide.utils import cacheItem

__all__ = ['WeatherMap']

log = LevityPluginLog.getChild('WeatherMap')

_LAYERS = ('radar', 'temperature', 'wind', 'clouds', 'none')
_BASEMAPS = ('auto', 'dark', 'light', 'none')
_FIELD_REFRESH = 1800.0
_RETRY = 60.0
_TILE_LIMIT = 320  #: tiles kept in memory, per kind


def _oneOf(name: str, value, allowed: tuple):
	if value not in allowed:
		raise ValueError(f'{name} is one of {", ".join(map(str, allowed))}, not {value!r}')
	return value


def _tilesUrl(value) -> Optional[str]:
	if value is None or str(value).strip() == '':
		return None
	text = str(value).strip()
	if not text.startswith(('http://', 'https://')) or not all(f'{{{part}}}' in text for part in 'zxy'):
		raise ValueError('tiles is an http(s) URL with {z}, {x} and {y} in it')
	return text


def _remember(cache: dict, key, value, limit: int = _TILE_LIMIT):
	cache[key] = value
	while len(cache) > limit:
		cache.pop(next(iter(cache)))


def _rgb(token: str) -> np.ndarray:
	color = theme.active().color(token).QColor
	return np.array([color.red(), color.green(), color.blue()], dtype=np.float64)


def _luma(rgb: np.ndarray) -> float:
	return float((0.2126*rgb[0] + 0.7152*rgb[1] + 0.0722*rgb[2])/255.0)


def _unit(section: str, default: str) -> str:
	try:
		from LevityDash.lib.config import userConfig
		return (userConfig.get('Units', section, fallback=default) or default).strip().lower()
	except Exception:  # noqa: BLE001 - no config yet
		return default


def _temperatureText(celsius: float) -> str:
	if _unit('temperature', 'c').startswith('f'):
		return f'{celsius*9/5 + 32:.0f}°'
	return f'{celsius:.0f}°'


def _windText(ms: float) -> str:
	unit = _unit('wind', 'm/s')
	if unit.startswith('mph') or unit.startswith('mi'):
		return f'{ms*2.2369363:.0f} mph'
	if unit.startswith('k') and 'n' not in unit[:2]:
		return f'{ms*3.6:.0f} km/h' if unit.startswith('km') else f'{ms*1.943844:.0f} kt'
	if unit.startswith('kn') or unit.startswith('kt'):
		return f'{ms*1.943844:.0f} kt'
	return f'{ms:.0f} m/s'


def _homeLocation() -> Optional[tuple[float, float]]:
	try:
		from LevityDash.lib.config import userConfig
		lat, lon = userConfig.loc
		if getattr(userConfig, 'locationKnown', True) is False:
			return None
		return float(lat), float(lon)
	except Exception as error:  # noqa: BLE001 - a map with no place still draws the world
		log.debug(f'map: no location: {error!r}')
		return None


class WeatherMap(Panel, tag='map'):
	"""A weather map panel. The settings are listed in the module docstring."""

	__exclude__ = {..., 'items'}
	_acceptsChildren = False

	def __init__(self, *args, **kwargs):
		self._ready = False
		self._layer = 'radar'
		self._lat: Optional[float] = None
		self._lon: Optional[float] = None
		self._zoom = 7.0
		self._basemap = 'auto'
		self._labels = True
		self._opacity: Optional[float] = None
		self._animate = True
		self._speed = 600
		self._refresh = 300.0
		self._marker = True
		self._legend = True
		self._stamp = True
		self._range: Optional[tuple[float, float]] = None
		self._tiles: Optional[str] = None
		self._paused = False
		# data
		self._frames: list[data.Frame] = []
		self._framesAt = 0.0
		self._shown = 0
		self._base: dict = {}
		self._tint: dict = {}
		self._radar: dict = {}
		self._fieldGrid: Optional[data.FieldGrid] = None
		self._fieldKey = None
		self._fieldAt = 0.0
		self._fieldImage: Optional[tuple] = None
		self._failed: dict = {}
		self._warned: set = set()
		self._viewKey = None
		self._loader: Optional[Loader] = None
		super().__init__(*args, **kwargs)
		self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemHasNoContents, False)
		self._loader = Loader()
		self._stepper = QTimer(singleShot=True)
		self._stepper.timeout.connect(self._step)
		self._ticker = QTimer(interval=30_000)
		self._ticker.timeout.connect(self._tick)
		self._ticker.start()
		cacheItem(self)
		self._ready = True
		self.signals.resized.connect(self._resized)
		self._reload()

	# -- life ---------------------------------------------------------------------------------

	@property
	def isEmpty(self) -> bool:
		return False

	def refresh(self):
		self.update()

	def release(self):
		self._ready = False
		for timer in (getattr(self, '_stepper', None), getattr(self, '_ticker', None)):
			if timer is not None:
				timer.stop()
		if self._loader is not None:
			self._loader.close()

	def delete(self):
		self.release()
		super().delete()

	def _resized(self, *_):
		self._fieldImage = None
		self._reload()

	def itemChange(self, change, value):
		if change == QGraphicsItem.GraphicsItemChange.ItemVisibleHasChanged and value and self._ready:
			self._reload()
		return super().itemChange(change, value)

	# -- view ---------------------------------------------------------------------------------

	def _center(self) -> tuple[float, float]:
		if self._lat is not None and self._lon is not None:
			return self._lat, self._lon
		return _homeLocation() or (20.0, 0.0)

	def _viewport(self) -> Optional[Viewport]:
		rect = self.rect()
		if rect.width() < 8 or rect.height() < 8:
			return None
		lat, lon = self._center()
		return Viewport(lat, lon, self._zoom, rect.width(), rect.height())

	def _baseStyle(self) -> Optional[data.Basemap]:
		"""The built-in base map to draw, or None for no map."""
		if self._basemap == 'none':
			return None
		if self._basemap == 'auto':
			dark = _luma(_rgb('background')) < 0.5
		else:
			dark = self._basemap == 'dark'
		return data.BASEMAPS['dark' if dark else 'light']

	def _baseUrl(self, base: data.Basemap, z: int, x: int, y: int) -> str:
		if self._tiles:
			return self._tiles.format(z=z, x=x, y=y, s='a', r='')
		return data.basemapUrl(base, z, x, y)

	def _gridSize(self, vp: Viewport) -> tuple[int, int]:
		columns = int(max(6, min(10, round(vp.width/110) + 1)))
		rows = int(max(4, min(7, round(vp.height/110) + 1)))
		return columns, rows

	# -- asking -------------------------------------------------------------------------------

	def _reload(self, *_):
		"""Ask for whatever the current view needs and does not have. Cheap to call: what is held or in flight is skipped."""
		if not self._ready or self._loader is None:
			return
		vp = self._viewport()
		if vp is None:
			return
		base = self._baseStyle()
		if base is not None:
			self._askTiles(vp, base, 'base')
			if self._labels and not self._tiles:
				self._askTiles(vp, data.BASEMAPS[base.name + '-labels'], 'labels')
		if self._layer == 'radar':
			self._askFrames()
			self._askRadarTiles(vp)
			self._schedule()
		elif self._layer in ('temperature', 'wind', 'clouds'):
			self._askFields(vp)
		self.update()

	def _due(self, key) -> bool:
		failed = self._failed.get(key)
		return failed is None or time.monotonic() - failed > _RETRY

	def _askTiles(self, vp: Viewport, base: data.Basemap, kind: str):
		for spot in vp.tiles(base.max_zoom):
			key = (kind, base.name, *spot.key)
			if key in self._base or not self._due(key):
				continue
			url = self._baseUrl(base, *spot.key)
			self._loader.request(key, lambda url=url: _decodeBase(data.fetch(url, ttl=7*86400)), self._arrived)

	def _askFrames(self):
		if self._loader.busy(('index',)) or not self._due(('index',)):
			return
		if self._frames and time.monotonic() - self._framesAt < self._refresh:
			return
		self._loader.request(('index',), data.radarFrames, self._arrived)

	def _askRadarTiles(self, vp: Viewport):
		"""Newest picture first, so something shows at once; then the older ones for the loop."""
		spots = vp.tiles(data.RADAR_MAX_ZOOM)
		for frame in reversed(self._frames if self._animate else self._frames[-1:]):
			for spot in spots:
				key = ('radar', frame.time, *spot.key)
				if key in self._radar or self._loader.busy(key) or not self._due(key):
					continue
				url = data.radarUrl(frame, *spot.key)
				self._loader.request(key, lambda url=url: _decodeRadar(data.fetch(url, ttl=3600)), self._arrived)

	def _askFields(self, vp: Viewport):
		columns, rows = self._gridSize(vp)
		points = vp.grid(columns, rows)
		key = ('fields', round(vp.lat, 2), round(vp.lon, 2), round(vp.zoom, 2), columns, rows, round(vp.width), round(vp.height))
		if key == self._fieldKey and self._fieldGrid is not None and time.monotonic() - self._fieldAt < _FIELD_REFRESH:
			return
		if self._loader.busy(('fields',)) or not self._due(('fields',)):
			return
		self._fieldKey = key
		self._loader.request(('fields',), lambda: data.fetchFields(points, ttl=_FIELD_REFRESH/2), self._arrived)

	# -- answers ------------------------------------------------------------------------------

	def _arrived(self, key, result, error):
		kind = key[0]
		if error is not None:
			self._failed[key] = time.monotonic()
			if kind not in self._warned:  # once per kind: a tile that 404s must not fill the log
				self._warned.add(kind)
				log.warning(f'map {kind}: {error!r}; trying again in {int(_RETRY)} s')
			else:
				log.debug(f'map {kind}: {error!r}')
			return
		self._warned.discard(kind)
		self._failed.pop(key, None)
		if kind in ('base', 'labels'):
			_remember(self._base, key, result)
		elif kind == 'radar':
			_remember(self._radar, key, toImage(result), limit=_TILE_LIMIT*2)
		elif kind == 'index':
			self._frames = result
			self._framesAt = time.monotonic()
			self._shown = len(self._frames) - 1
			if (vp := self._viewport()) is not None:
				self._askRadarTiles(vp)
			self._schedule()
		elif kind == 'fields':
			self._fieldGrid = result
			self._fieldAt = time.monotonic()
			self._fieldImage = None
		self.update()

	def _tick(self):
		"""Twice a minute: ask again for what is old or failed."""
		if self.isVisible():
			self._reload()

	# -- the loop -----------------------------------------------------------------------------

	def _complete(self, frame: data.Frame, spots) -> bool:
		return all(('radar', frame.time, *s.key) in self._radar for s in spots)

	def _schedule(self):
		if self._layer != 'radar' or not self._animate or self._paused or len(self._frames) < 2 or not self._ready:
			self._stepper.stop()
			return
		if not self._stepper.isActive():
			self._stepper.start(self._speed)

	def _step(self):
		if not self._ready or self._layer != 'radar' or not self._animate or self._paused or not self._frames:
			return
		vp = self._viewport()
		if vp is None:
			return
		spots = vp.tiles(data.RADAR_MAX_ZOOM)
		count = len(self._frames)
		for hop in range(1, count + 1):  # the next picture that has all its tiles
			index = (self._shown + hop) % count
			if self._complete(self._frames[index], spots):
				self._shown = index
				break
		self.update()
		last = self._shown == count - 1
		self._stepper.start(self._speed*3 if last else self._speed)

	def mousePressEvent(self, mouseEvent):
		if self._layer == 'radar' and self._animate and mouseEvent.button() == Qt.MouseButton.LeftButton:
			self._paused = not self._paused
			self._schedule()
			self.update()
		super().mousePressEvent(mouseEvent)

	# -- settings -----------------------------------------------------------------------------

	@StateProperty(key='layer', default='radar', allowNone=False, after=_reload, repr=True)
	def layer(self) -> str:
		return self._layer

	@layer.setter
	def layer(self, value: str):
		# a word is already "decoded" to the loader, so the decoder never sees a misspelling: check here too
		self._layer = _oneOf('layer', str(value).lower(), _LAYERS)

	@layer.decode
	def layer(self, value) -> str:
		return _oneOf('layer', str(value).lower(), _LAYERS)

	@StateProperty(key='lat', default=None, after=_reload)
	def lat(self) -> Optional[float]:
		return self._lat

	@lat.setter
	def lat(self, value: Optional[float]):
		self._lat = value

	@lat.decode
	def lat(self, value) -> Optional[float]:
		if value is None:
			return None
		value = float(value)
		if not -90 <= value <= 90:
			raise ValueError(f'lat is -90 to 90, not {value}')
		return value

	@StateProperty(key='lon', default=None, after=_reload)
	def lon(self) -> Optional[float]:
		return self._lon

	@lon.setter
	def lon(self, value: Optional[float]):
		self._lon = value

	@lon.decode
	def lon(self, value) -> Optional[float]:
		if value is None:
			return None
		value = float(value)
		if not -180 <= value <= 180:
			raise ValueError(f'lon is -180 to 180, not {value}')
		return value

	@StateProperty(key='zoom', default=7.0, allowNone=False, after=_reload)
	def zoom(self) -> float:
		return self._zoom

	@zoom.setter
	def zoom(self, value: float):
		self._zoom = value

	@zoom.decode
	def zoom(self, value) -> float:
		value = float(value)
		if not 1 <= value <= 16:
			raise ValueError(f'zoom is 1 to 16, not {value}')
		return value

	@StateProperty(key='basemap', default='auto', allowNone=False, after=_reload)
	def basemap(self) -> str:
		return self._basemap

	@basemap.setter
	def basemap(self, value: str):
		self._basemap = _oneOf('basemap', str(value).lower(), _BASEMAPS)

	@basemap.decode
	def basemap(self, value) -> str:
		return _oneOf('basemap', str(value).lower(), _BASEMAPS)

	@StateProperty(key='labels', default=True, allowNone=False, after=_reload)
	def labels(self) -> bool:
		return self._labels

	@labels.setter
	def labels(self, value: bool):
		self._labels = bool(value)

	@StateProperty(key='opacity', default=None, after=refresh)
	def opacity(self) -> Optional[float]:
		return self._opacity

	@opacity.setter
	def opacity(self, value: Optional[float]):
		self._opacity = value

	@opacity.decode
	def opacity(self, value) -> Optional[float]:
		return None if value is None else max(0.0, min(1.0, float(value)))

	@StateProperty(key='animate', default=True, allowNone=False, after=_reload)
	def animate(self) -> bool:
		return self._animate

	@animate.setter
	def animate(self, value: bool):
		self._animate = bool(value)

	@StateProperty(key='speed', default=600, allowNone=False, after=_reload)
	def speed(self) -> int:
		return self._speed

	@speed.setter
	def speed(self, value: int):
		self._speed = value

	@speed.decode
	def speed(self, value) -> int:
		return max(50, min(10_000, int(value)))

	@StateProperty(key='refresh', default=300.0, allowNone=False, after=_reload)
	def refreshSeconds(self) -> float:
		return self._refresh

	@refreshSeconds.setter
	def refreshSeconds(self, value: float):
		self._refresh = value

	@refreshSeconds.decode
	def refreshSeconds(self, value) -> float:
		return max(60.0, float(value))

	@StateProperty(key='marker', default=True, allowNone=False, after=refresh)
	def marker(self) -> bool:
		return self._marker

	@marker.setter
	def marker(self, value: bool):
		self._marker = bool(value)

	@StateProperty(key='legend', default=True, allowNone=False, after=refresh)
	def legend(self) -> bool:
		return self._legend

	@legend.setter
	def legend(self, value: bool):
		self._legend = bool(value)

	@StateProperty(key='stamp', default=True, allowNone=False, after=refresh)
	def stamp(self) -> bool:
		return self._stamp

	@stamp.setter
	def stamp(self, value: bool):
		self._stamp = bool(value)

	@StateProperty(key='range', default=None, after=refresh)
	def range(self) -> Optional[list]:
		return None if self._range is None else list(self._range)

	@range.setter
	def range(self, value):
		self._range = None if value is None else tuple(value)
		self._fieldImage = None

	@range.decode
	def range(self, value):
		if value is None:
			return None
		low, high = (float(v) for v in value)
		if not low < high:
			raise ValueError(f'range is [low, high] with low below high, not {value!r}')
		return [low, high]

	@StateProperty(key='tiles', default=None, after=_reload)
	def tiles(self) -> Optional[str]:
		return self._tiles

	@tiles.setter
	def tiles(self, value: Optional[str]):
		self._tiles = _tilesUrl(value)

	@tiles.decode
	def tiles(self, value) -> Optional[str]:
		return _tilesUrl(value)

	# -- painting -----------------------------------------------------------------------------

	def _tintColors(self, base: data.Basemap) -> tuple[np.ndarray, np.ndarray]:
		"""The colours sea and land are painted in: the theme's background, and that pulled a little towards its text."""
		background, text = _rgb('background'), _rgb('text')
		sea = background
		land = background + (text - background)*(0.17 if base.dark else 0.10)
		return sea, land

	def _baseImage(self, base: data.Basemap, spot) -> Optional[QImage]:
		key = ('base', base.name, *spot.key)
		lum = self._base.get(key)
		if lum is None:
			return None
		sea, land = self._tintColors(base)
		tint = (key, tuple(sea), tuple(land))
		image = self._tint.get(tint)
		if image is None:
			span = (base.land - base.water) or 1.0
			t = (lum[0] - base.water)/span
			t = np.clip(np.where(t > 1.0, 1.0 + (t - 1.0)*3.0, t), 0.0, 2.2)[..., None]  # borders and roads sit just above land: lift them
			rgb = sea + (land - sea)*t
			out = np.empty(rgb.shape[:2] + (4,), dtype=np.uint8)
			out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
			out[..., 3] = 255
			image = toImage(out)
			for stale in [k for k in self._tint if k[0] == key]:
				del self._tint[stale]
			_remember(self._tint, tint, image)
		return image

	def _labelImage(self, base: data.Basemap, spot) -> Optional[QImage]:
		key = ('labels', base.name + '-labels', *spot.key)
		tile = self._base.get(key)
		if tile is None:
			return None
		color = theme.active().color('text').QColor
		tint = (key, color.rgba())
		image = self._tint.get(tint)
		if image is None:
			lum, alpha = tile
			strength = np.clip(lum*1.8, 0.0, 1.0)  # the glyphs are bright, their halo is not
			out = np.empty(alpha.shape + (4,), dtype=np.uint8)
			out[..., 0], out[..., 1], out[..., 2] = color.red(), color.green(), color.blue()
			out[..., 3] = np.clip(alpha*strength*color.alpha()*0.72, 0, 255).astype(np.uint8)
			image = toImage(out)
			_remember(self._tint, tint, image)
		return image

	@staticmethod
	def _text(painter: QPainter, point: QPointF, text: str, color: QColor):
		"""Text with a soft dark edge, so it reads over a pale layer as well as a dark map."""
		shadow = QColor(theme.active().color('background').QColor)
		shadow.setAlpha(190)
		for dx, dy in ((0.0, 1.2), (1.0, 0.6), (-1.0, 0.6), (0.0, -0.6)):
			painter.setPen(shadow)
			painter.drawText(QPointF(point.x() + dx, point.y() + dy), text)
		painter.setPen(color)
		painter.drawText(point, text)

	def _font(self, size: float, weight=QFont.Weight.DemiBold) -> QFont:
		font = QFont(theme.active().font('display'))
		font.setPixelSize(max(6, int(round(size))))
		font.setWeight(weight)
		return font

	def paint(self, painter: QPainter, option, widget=None):
		rect = QRectF(self.rect())
		if rect.width() < 8 or rect.height() < 8:
			return
		try:
			self._paint(painter, rect)
		except Exception as error:  # noqa: BLE001 - a paint error must not take the dashboard down
			if getattr(self, '_paintError', None) != repr(error):
				self._paintError = repr(error)
				log.exception(f'map failed to paint: {error!r}')

	def _paint(self, painter: QPainter, rect: QRectF):
		vp = self._viewport()
		if vp is None:
			return
		if self._viewKey != (vp.width, vp.height):  # the first paint, or a size that arrived without a signal
			self._viewKey = (vp.width, vp.height)
			QTimer.singleShot(0, self._reload)
		painter.save()
		painter.setClipRect(rect)
		painter.setRenderHints(QPainter.RenderHint.SmoothPixmapTransform | QPainter.RenderHint.Antialiasing)
		base = self._baseStyle()
		if base is not None:
			for spot in vp.tiles(base.max_zoom):
				image = self._baseImage(base, spot)
				if image is not None:
					painter.drawImage(QRectF(spot.left, spot.top, spot.size, spot.size), image)
		painter.setOpacity(self._opacity if self._opacity is not None else (0.92 if self._layer == 'radar' else 0.74))
		self._paintLayer(painter, vp, rect)
		painter.setOpacity(1.0)
		if base is not None and self._labels and not self._tiles:
			labels = data.BASEMAPS[base.name + '-labels']
			for spot in vp.tiles(labels.max_zoom):
				image = self._labelImage(labels, spot)
				if image is not None:
					painter.drawImage(QRectF(spot.left, spot.top, spot.size, spot.size), image)
		self._paintMarker(painter, vp)
		self._paintLegend(painter, rect)
		self._paintCredit(painter, rect, base)
		painter.restore()

	def _paintLayer(self, painter: QPainter, vp: Viewport, rect: QRectF):
		if self._layer == 'radar':
			frame = self._currentFrame(vp)
			if frame is None:
				return
			for spot in vp.tiles(data.RADAR_MAX_ZOOM):
				image = self._radar.get(('radar', frame.time, *spot.key))
				if image is not None:
					painter.drawImage(QRectF(spot.left, spot.top, spot.size, spot.size), image)
		elif self._layer in ('temperature', 'wind', 'clouds'):
			image = self._fieldPicture(vp)
			if image is not None:
				painter.drawImage(rect, image)
			if self._layer == 'wind':
				self._paintArrows(painter, vp)

	def _currentFrame(self, vp: Viewport) -> Optional[data.Frame]:
		if not self._frames:
			return None
		spots = vp.tiles(data.RADAR_MAX_ZOOM)
		if self._animate:
			order = [self._shown % len(self._frames)] + list(range(len(self._frames) - 1, -1, -1))
		else:
			order = list(range(len(self._frames) - 1, -1, -1))
		for index in order:
			if self._complete(self._frames[index], spots):
				return self._frames[index]
		return None

	# fields

	def _fieldScale(self):
		"""`(stops, lo, hi)` for the current field layer."""
		if self._layer == 'temperature':
			stops, lo, hi = palette.temperatureRamp()
			if self._range is not None:
				lo, hi = self._range
				stops, _, _ = palette.temperatureRamp(*_bandFor(lo, hi))
			return stops, lo, hi
		if self._layer == 'wind':
			lo, hi = self._range or (0.0, 22.0)
			return palette.WIND, lo, hi
		return palette.CLOUDS, 0.0, 100.0

	def _fieldPicture(self, vp: Viewport) -> Optional[QImage]:
		grid = self._fieldGrid
		if grid is None:
			return None
		key = (self._layer, self._range, round(vp.width), round(vp.height), id(grid))
		if self._fieldImage is not None and self._fieldImage[0] == key:
			return self._fieldImage[1]
		name = {'temperature': 'temperature', 'wind': 'wind', 'clouds': 'clouds'}[self._layer]
		stops, lo, hi = self._fieldScale()
		w, h = max(16, int(vp.width/3)), max(16, int(vp.height/3))
		picture = upsample(grid.values[name], h, w)
		image = toImage(palette.colorize(picture, palette.lut(stops), lo, hi))
		self._fieldImage = (key, image)
		return image

	def _paintArrows(self, painter: QPainter, vp: Viewport):
		grid = self._fieldGrid
		if grid is None:
			return
		speed, direction = grid.values['wind'], grid.values['direction']
		rows, columns = speed.shape
		color = theme.active().color('text').QColor
		scale = min(vp.width/columns, vp.height/rows)
		lo, hi = self._range or (0.0, 22.0)
		painter.save()
		for r in range(rows):
			for c in range(columns):
				s, d = speed[r, c], direction[r, c]
				if not (np.isfinite(s) and np.isfinite(d)):
					continue
				px, py = vp.width*c/(columns - 1), vp.height*r/(rows - 1)
				length = scale*(0.22 + 0.28*min(1.0, max(0.0, (s - lo)/(hi - lo))))
				if not (length/2 <= px <= vp.width - length/2 and length/2 <= py <= vp.height - length/2):
					continue  # an arrow cut by the edge reads as a wrong direction
				painter.save()
				painter.translate(px, py)
				painter.rotate(d + 180.0)  # direction is where the wind comes from; the arrow flies the other way
				painter.setPen(QPen(color, max(1.4, scale*0.035), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
				head = length*0.32
				painter.drawLine(QPointF(0, length/2), QPointF(0, -length/2))
				painter.drawLine(QPointF(0, -length/2), QPointF(-head, -length/2 + head))
				painter.drawLine(QPointF(0, -length/2), QPointF(head, -length/2 + head))
				painter.restore()
		painter.restore()

	# furniture

	def _paintMarker(self, painter: QPainter, vp: Viewport):
		if not self._marker:
			return
		home = _homeLocation()
		if home is None:
			return
		x, y = vp.project(*home)
		if not (0 <= x <= vp.width and 0 <= y <= vp.height):
			return
		radius = max(4.0, min(vp.width, vp.height)*0.012)
		accent = theme.active().color('accent').QColor
		text = theme.active().color('text').QColor
		halo = QColor(accent)
		halo.setAlpha(70)
		painter.setPen(Qt.PenStyle.NoPen)
		painter.setBrush(halo)
		painter.drawEllipse(QPointF(x, y), radius*2.6, radius*2.6)
		painter.setBrush(accent)
		painter.setPen(QPen(text, max(1.5, radius*0.28)))
		painter.drawEllipse(QPointF(x, y), radius, radius)

	def _legendSpec(self):
		"""`(stops, from, to, left label, right label, title)`: the ramp, the part of it the bar shows (0..1), and its words."""
		if self._layer == 'radar':
			return palette.PRECIP, 0.0, 1.0, 'Light', 'Heavy', 'Rain'
		stops, lo, hi = self._fieldScale()
		if self._layer == 'temperature':
			# Show the band people live in, not the whole -30 to 52 °C the ramp can paint.
			low, high = (-8.0, 42.0) if self._range is None else (lo, hi)
			if self._range is None:
				from LevityDash.lib.ui.colors import comfort
				c_low, c_high = comfort.configured()
				low, high = comfort.shift(low, c_low, c_high), comfort.shift(high, c_low, c_high)
			return stops, (low - lo)/(hi - lo), (high - lo)/(hi - lo), _temperatureText(low), _temperatureText(high), 'Temperature'
		if self._layer == 'wind':
			return stops, 0.0, 1.0, 'Calm', _windText(hi), 'Wind'
		return stops, 0.0, 1.0, 'Clear', 'Overcast', 'Cloud'

	def _paintLegend(self, painter: QPainter, rect: QRectF):
		if self._layer == 'none':
			return
		if self._stamp:
			self._paintStamp(painter, rect)
		if not self._legend:
			return
		stops, t0, t1, left, right, _ = self._legendSpec()
		unit = min(rect.width(), rect.height())
		margin = unit*0.04
		size = max(10.0, unit*0.045)
		font = self._font(size)
		metrics = QFontMetricsF(font)
		barW = max(90.0, min(rect.width()*0.34, unit*0.55))
		barH = max(5.0, size*0.42)
		text = theme.active().color('text').QColor
		muted = theme.active().color('muted').QColor
		x0, y0 = rect.left() + margin, rect.bottom() - margin - metrics.height() - barH - size*0.25
		gradient = QLinearGradient(x0, 0, x0 + barW, 0)
		table = range(48)
		for i in range(len(table)):
			f = i/(len(table) - 1)
			r, g, b, a = (int(v*255) for v in palette.ramp(stops, t0 + (t1 - t0)*f))
			gradient.setColorAt(f, QColor(r, g, b, max(a, 110)))
		path = QPainterPath()
		path.addRoundedRect(QRectF(x0, y0, barW, barH), barH/2, barH/2)
		painter.setPen(QPen(QColor(0, 0, 0, 70), 1))
		painter.setBrush(QBrush(gradient))
		painter.drawPath(path)
		painter.setFont(font)
		baseline = y0 + barH + size*0.25 + metrics.ascent()
		self._text(painter, QPointF(x0, baseline), left, text)
		self._text(painter, QPointF(x0 + barW - metrics.horizontalAdvance(right), baseline), right, text)

	def _paintStamp(self, painter: QPainter, rect: QRectF):
		unit = min(rect.width(), rect.height())
		margin = unit*0.04
		size = max(11.0, unit*0.052)
		_, _, _, _, _, title = self._legendSpec()
		when = None
		if self._layer == 'radar':
			vp = self._viewport()
			frame = self._currentFrame(vp) if vp is not None else None
			if frame is not None:
				when = datetime.fromtimestamp(frame.time).astimezone()
		elif self._fieldGrid is not None and self._fieldGrid.time:
			when = datetime.fromtimestamp(self._fieldGrid.time).astimezone()
		label = title.upper() if when is None else f'{title.upper()}  {when.strftime("%-I:%M %p").lstrip("0")}'
		if self._layer == 'radar' and self._paused:
			label += '  ❚❚'
		font = self._font(size)
		font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 104)
		painter.setFont(font)
		self._text(painter, QPointF(rect.left() + margin, rect.top() + margin + QFontMetricsF(font).ascent()), label, theme.active().color('text').QColor)

	def _paintCredit(self, painter: QPainter, rect: QRectF, base: Optional[data.Basemap]):
		parts = []
		if base is not None:
			parts.append('Esri, © OpenStreetMap' if not self._tiles else 'map tiles: see source')
		if self._layer == 'radar':
			parts.append('RainViewer')
		elif self._layer in ('temperature', 'wind', 'clouds'):
			parts.append(self._fieldGrid.source if self._fieldGrid is not None else 'Open-Meteo')
		if not parts:
			return
		unit = min(rect.width(), rect.height())
		font = self._font(max(7.0, unit*0.026), QFont.Weight.Normal)
		metrics = QFontMetricsF(font)
		painter.setFont(font)
		color = QColor(theme.active().color('muted').QColor)
		text = ' · '.join(parts)
		self._text(painter, QPointF(rect.right() - unit*0.03 - metrics.horizontalAdvance(text), rect.bottom() - unit*0.03 - metrics.descent()), text, color)


def _bandFor(lo: float, hi: float) -> tuple[float, float]:
	"""A comfort band that makes `palette.temperatureRamp` span exactly `lo`..`hi`: the built-in scale's 12..22 °C middle,
	moved to the same fraction of the span."""
	from LevityDash.lib.ui.colors import comfort
	built = (comfort.DEFAULT_LOW + 30.0)/82.0, (comfort.DEFAULT_HIGH + 30.0)/82.0
	return lo + (hi - lo)*built[0], lo + (hi - lo)*built[1]


def _decodeBase(body: bytes):
	"""A base-map tile as `(lum, alpha)`: luma 0..1 and alpha 0..1 floats, which is all the tint needs."""
	rgba = toArray(body).astype(np.float32)/255.0
	lum = 0.2126*rgba[..., 0] + 0.7152*rgba[..., 1] + 0.0722*rgba[..., 2]
	return lum, rgba[..., 3]


def _decodeRadar(body: bytes) -> np.ndarray:
	"""A RainViewer tile as RGBA bytes painted with the dashboard palette."""
	intensity = palette.rainviewerIntensity(toArray(body))
	return palette.colorize(intensity, palette.lut(palette.PRECIP))
