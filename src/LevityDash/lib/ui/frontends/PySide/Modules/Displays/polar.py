"""A polar graph: a series drawn around a centre, not along a line.

```yaml
- type: polar-graph
  key: environment.temperature.temperature     # the radius: how far out a point sits
  angle: time                                  # the angle: the time of day, or another key
```

Two ways to spend the angle:

* ``angle: time`` is a clock face. The window (``today``, or a length such as
  ``24h``) is one turn; noon is at the top. Style ``area`` (default) fills under
  the curve, ``line`` strokes it. A hand marks now, and the day's high and low
  carry their values.
* ``angle: <key>`` takes the angle from a second series, usually a direction.
  Style ``trail`` (default) joins the last ``window`` of (direction, value)
  points and fades the old end. Style ``rose`` bins the directions into
  ``bins`` petals and sizes each by the mean value or by how often it was seen.

Everything outside the data (rings, spokes, labels) is drawn from the meter's
`ArcTrack`, so angles mean what they mean on a gauge: ``0`` is up, clockwise.
The module only reads: it never writes a key, and with no data it draws the
empty face.
"""
from datetime import datetime, timedelta
from math import ceil, floor, log10
from typing import List, Optional, Sequence, Tuple

import numpy as np
from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Slot
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QGraphicsItem

from LevityDash import LevityDashboard
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.plugin import AnySource
from LevityDash.lib.stateful import StateProperty
from LevityDash.lib.ui import Color, Gradient, UILogger
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.track import ArcTrack
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
from LevityDash.lib.utils import shared

__all__ = ['PolarGraph', 'niceStep']

log = UILogger.getChild('PolarGraph')

COMPASS = ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW')
STYLES = ('area', 'line', 'trail', 'rose')
_DURATIONS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}


def parseWindow(value) -> Optional[timedelta]:
	"""``today`` is `None`; ``90m``, ``6h``, ``2d`` or a number of hours are a length."""
	if value is None:
		return None
	if isinstance(value, timedelta):
		return value
	if isinstance(value, (int, float)):
		return timedelta(hours=float(value))
	text = str(value).strip().lower()
	if text in ('today', 'day', ''):
		return None
	unit = text[-1]
	if unit in _DURATIONS:
		try:
			return timedelta(seconds=float(text[:-1]) * _DURATIONS[unit])
		except ValueError:
			pass
	raise ValueError(f'window {value!r}: expected `today` or a length such as 6h, 90m, 2d')


def niceStep(span: float, target: int = 4) -> float:
	"""A round step (1, 2, 2.5, 5 times a power of ten) that gives about ``target`` steps over ``span``."""
	if span <= 0 or target < 1:
		return 1.0
	raw = span / target
	magnitude = 10 ** floor(log10(raw))
	for factor in (1, 2, 2.5, 5, 10):
		if raw <= factor * magnitude:
			return factor * magnitude
	return 10 * magnitude


def niceRange(low: float, high: float, target: int = 4) -> Tuple[float, float]:
	"""``low``..``high`` widened to whole steps."""
	if high <= low:
		high = low + 1.0
	step = niceStep(high - low, target)
	return floor(low / step) * step, ceil(high / step) * step


def binned(angles: np.ndarray, values: np.ndarray, bins: int, frequency: bool) -> np.ndarray:
	"""One number per petal: the mean value in it, or the share of points that landed in it.

	Petal ``i`` is centred on ``i * 360 / bins`` degrees, so north is the middle of petal 0.
	"""
	width = 360.0 / bins
	index = (np.floor(((angles % 360) + width / 2) / width).astype(int)) % bins
	if frequency:
		counts = np.bincount(index, minlength=bins).astype(float)
		return counts / counts.sum() if counts.sum() else counts
	sums = np.bincount(index, weights=values, minlength=bins)
	counts = np.bincount(index, minlength=bins)
	with np.errstate(invalid='ignore', divide='ignore'):
		means = np.where(counts > 0, sums / np.maximum(counts, 1), 0.0)
	return means


def smoothed(x: np.ndarray, y: np.ndarray, per: float) -> Tuple[np.ndarray, np.ndarray]:
	"""``y`` resampled so points sit about ``per`` apart in ``x``, with a monotone cubic between samples.

	An hourly series on a clock face is 15 degrees a sample, which shows as facets. Pchip never overshoots, so
	a smooth hump can not read higher than the day's real high.
	"""
	if len(x) < 3:
		return x, y
	from scipy.interpolate import PchipInterpolator
	steps = max(int(np.ceil((x[-1] - x[0]) / per)), len(x))
	grid = np.linspace(x[0], x[-1], steps)
	return grid, PchipInterpolator(x, y)(grid)


class _Feed(QObject):
	"""Listens to one key's series on the GUI thread and tells the owner something changed."""

	def __init__(self, owner: 'PolarGraph', key: CategoryItem):
		super().__init__()
		self.owner = owner
		self.key = key
		self.series = None
		self.valueClass = None
		self.waiting = False
		self.closed = False
		self.attach()

	def container(self):
		try:
			return LevityDashboard.get_container(self.key).getTimeseries(AnySource)
		except Exception:
			log.exception(f'polar graph could not look up {self.key}')
			return None

	def attach(self) -> bool:
		if self.closed or self.series is not None:
			return self.series is not None
		container = self.container()
		series = None if container is None else container.timeseries
		if series is None:
			if not self.waiting:
				self.waiting = True
				LevityDashboard.get_container(self.key).getPreferredSourceContainer(self, AnySource, self.late, timeseriesOnly=True)
			return False
		with series.signals as signal:
			if signal.connectSlot(self.changed):
				self.series = series
				return True
		log.warning(f'polar graph could not listen to {self.key}')
		return False

	def late(self, *args):
		self.waiting = False
		if self.attach():
			self.owner.dataChanged()

	@Slot()
	def changed(self, *args):
		if not self.closed:
			self.owner.dataChanged()

	def read(self, start: datetime, end: Optional[datetime]) -> List[Tuple[datetime, float]]:
		if self.series is None and not self.attach():
			return []
		try:
			items = list(self.series[start:end])
			if items:
				self.valueClass = type(items[0].value)
			return [(item.timestamp, float(item.value)) for item in items]
		except Exception:
			log.exception(f'polar graph could not read {self.key}')
			return []

	def now(self) -> Optional[float]:
		"""The latest realtime value, in the series' unit, or `None`."""
		try:
			return float(LevityDashboard.get_container(self.key).value.now.value)
		except Exception:
			return None

	def close(self):
		self.closed = True
		if self.series is not None:
			try:
				self.series.signals.disconnectSlot(self.changed)
			except Exception:
				pass
			self.series = None


class PolarCanvas(QGraphicsItem):
	"""Paints a `PolarGraph`. A plain item, so the panel's own layout never sees it."""

	def __init__(self, graph: 'PolarGraph'):
		super().__init__(graph)
		self.graph = graph
		self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
		self.setZValue(1)

	def boundingRect(self) -> QRectF:
		return self.graph.rect()

	def paint(self, painter: QPainter, option, widget=None):
		try:
			self.graph.paintPolar(painter)
		except Exception:
			log.exception('polar graph failed to paint')


class PolarGraph(Panel, tag='polar-graph'):
	__exclude__ = {..., 'items'}

	_key: Optional[CategoryItem] = None
	_angleKey: Optional[CategoryItem] = None
	_style: Optional[str] = None
	_window = None
	_startAngle: Optional[float] = None
	_range: Tuple[Optional[float], Optional[float]] = (None, None)
	_hole = 0.2
	_rings = 4
	_spokes: Optional[int] = None
	_labels: str = 'auto'
	_color: Optional[Color] = None
	_gradient: Optional[Gradient] = None
	_fill = 0.32
	_weight = 0.012
	_showNow = True
	_extremes = True
	_bins = 16
	_roseBy = 'value'
	_precision = 0
	_shownRange: Tuple[float, float] = (0.0, 1.0)
	_labelSize = 0.075

	def __init__(self, *args, **kwargs):
		self._feeds: dict = {}
		self._canvas = None
		super().__init__(*args, **kwargs)
		self._canvas = PolarCanvas(self)
		self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemHasNoContents)

	def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
		if change == QGraphicsItem.GraphicsItemChange.ItemSceneChange and value is None:
			# Leaving the scene (deleted, or the dashboard reloaded): stop listening.
			for feed in self._feeds.values():
				feed.close()
			self._feeds.clear()
		return super().itemChange(change, value)

	# section state

	def refresh(self):
		if self._canvas is not None:
			self._canvas.prepareGeometryChange()
			self._canvas.update()

	dataChanged = refresh

	def setRect(self, rect, *args, **kwargs):
		result = super().setRect(rect, *args, **kwargs)
		self.refresh()
		return result

	def _feed(self, key: Optional[CategoryItem]) -> Optional[_Feed]:
		if key is None:
			return None
		if key not in self._feeds:
			self._feeds[key] = _Feed(self, key)
		return self._feeds[key]

	def _drop(self, key: Optional[CategoryItem]):
		if key is not None and key not in (self._key, self._angleKey) and (feed := self._feeds.pop(key, None)):
			feed.close()

	@property
	def isTime(self) -> bool:
		return self._angleKey is None

	@property
	def style(self) -> str:
		# A rejected value can reach the setter as the raw text; only a known style counts.
		if self._style in STYLES:
			return self._style
		return 'area' if self.isTime else 'trail'

	@property
	def window(self) -> Optional[timedelta]:
		if isinstance(self._window, timedelta):
			return self._window
		if self.isTime:
			return None
		return timedelta(hours=6)

	@property
	def turnStart(self) -> float:
		"""The dial angle the data starts at. Noon at the top puts midnight at the bottom of a clock face."""
		if self._startAngle is not None:
			return self._startAngle
		return 180.0 if self.isTime else 0.0

	# section properties

	@StateProperty(key='key', default=None, allowNone=True, after=refresh, sortOrder=0)
	def key(self) -> Optional[CategoryItem]:
		"""The series whose value is the radius."""
		return self._key

	@key.setter
	def key(self, value):
		old, self._key = self._key, value
		self._feed(value)
		if old != value:
			self._drop(old)

	@key.decode
	def key(self, value) -> Optional[CategoryItem]:
		return None if value is None else CategoryItem(str(value))

	@key.encode
	def key(self, value) -> Optional[str]:
		return None if value is None else str(value)

	@StateProperty(key='angle', default='time', allowNone=False, after=refresh, sortOrder=1)
	def angle(self) -> str:
		"""`time`, or the key of the series that gives each point its angle (a direction in degrees)."""
		return 'time' if self._angleKey is None else str(self._angleKey)

	@angle.setter
	def angle(self, value):
		old, self._angleKey = self._angleKey, value
		self._feed(value)
		if old != value:
			self._drop(old)

	@angle.decode
	def angle(self, value) -> Optional[CategoryItem]:
		if value is None or str(value).strip().lower() == 'time':
			return None
		return CategoryItem(str(value))

	@angle.encode
	def angle(self, value) -> str:
		return 'time' if value is None else str(value)

	@StateProperty(key='style', default=None, allowNone=True, after=refresh, sortOrder=2)
	def styleName(self) -> Optional[str]:
		"""`area` or `line` (clock face), `trail` or `rose` (direction). Left out, the angle picks one."""
		return self._style

	@styleName.setter
	def styleName(self, value):
		self._style = value

	@styleName.decode
	def styleName(self, value) -> Optional[str]:
		if value is None:
			return None
		text = str(value).strip().lower()
		if text not in STYLES:
			log.warning(f'polar graph ignored style {value!r}: expected one of {", ".join(STYLES)}')
			return None
		return text

	@StateProperty(key='window', default=None, allowNone=True, after=refresh, sortOrder=3)
	def windowSpec(self) -> Optional[timedelta]:
		"""How much history: `today` (midnight to midnight, the clock default) or a length such as `6h`."""
		return self._window

	@windowSpec.setter
	def windowSpec(self, value):
		self._window = value

	@windowSpec.decode
	def windowSpec(self, value):
		try:
			return parseWindow(value)
		except ValueError as error:
			log.warning(f'polar graph ignored {error}')
			return None

	@windowSpec.encode
	def windowSpec(self, value):
		return None if value is None else f'{value.total_seconds() / 3600:g}h'

	@StateProperty(key='start-angle', default=None, allowNone=True, after=refresh, sortOrder=4)
	def startAngle(self) -> Optional[float]:
		"""The dial angle (0 up, clockwise) where the window starts. Clock face 180, direction 0."""
		return self._startAngle

	@startAngle.setter
	def startAngle(self, value):
		self._startAngle = value

	@StateProperty(key='range', default=None, allowNone=True, after=refresh, sortOrder=5)
	def radiusRange(self) -> Optional[dict]:
		"""`{min, max}` of the radius scale, in the series' unit. A side left out follows the data."""
		low, high = self._range
		if low is None and high is None:
			return None
		return {k: v for k, v in (('min', low), ('max', high)) if v is not None}

	@radiusRange.setter
	def radiusRange(self, value):
		value = value or {}
		self._range = (value.get('min'), value.get('max'))

	@radiusRange.decode
	def radiusRange(self, value) -> Optional[dict]:
		if value is None:
			return None
		if not isinstance(value, dict) or set(value) - {'min', 'max'}:
			log.warning(f'polar graph ignored range {value!r}: expected {{min: …, max: …}}')
			return None
		return {k: float(v) for k, v in value.items()}

	@StateProperty(key='hole', default=0.2, allowNone=False, after=refresh, sortOrder=6)
	def hole(self) -> float:
		"""The share of the radius left empty in the middle, so the lowest value does not collapse to a point."""
		return self._hole

	@hole.setter
	def hole(self, value):
		self._hole = min(max(float(value), 0.0), 0.9)

	@StateProperty(key='rings', default=4, allowNone=False, after=refresh, sortOrder=7)
	def rings(self) -> int:
		"""About how many value rings to draw. `0` draws none."""
		return self._rings

	@rings.setter
	def rings(self, value):
		self._rings = max(int(value), 0)

	@StateProperty(key='spokes', default=None, allowNone=True, after=refresh, sortOrder=8)
	def spokes(self) -> Optional[int]:
		"""How many spokes round the face. Default 8 (every 3 hours, or every compass point)."""
		return self._spokes

	@spokes.setter
	def spokes(self, value):
		self._spokes = None if value is None else max(int(value), 0)

	@StateProperty(key='labels', default='auto', allowNone=False, after=refresh, sortOrder=9)
	def labels(self) -> str:
		"""`auto` (hours for a clock face, compass points for a direction), `compass`, `hours`, `degrees` or `false`."""
		return self._labels

	@labels.setter
	def labels(self, value):
		self._labels = value

	@labels.decode
	def labels(self, value) -> str:
		if value is False or value is None:
			return 'false'
		text = str(value).strip().lower()
		if text not in ('auto', 'compass', 'hours', 'degrees', 'false'):
			log.warning(f'polar graph ignored labels {value!r}: expected auto, compass, hours, degrees or false')
			return 'auto'
		return text

	@labels.encode
	def labels(self, value) -> str | bool:
		return False if value == 'false' else value

	@StateProperty(key='color', default=None, allowNone=True, after=refresh, sortOrder=10)
	def color(self) -> Optional[Color]:
		"""The series colour. Default: the theme's accent."""
		return self._color

	@color.setter
	def color(self, value):
		self._color = value

	@color.decode
	def color(self, value) -> Optional[Color]:
		return None if value is None else Color.decode(value)

	@color.encode
	def color(self, value) -> Optional[str]:
		return None if value is None else str(value)

	@StateProperty(key='gradient', default=None, allowNone=True, after=refresh, sortOrder=11)
	def gradient(self) -> Optional[Gradient]:
		"""Colour by value instead of one colour. Stops are in the series' unit."""
		return self._gradient

	@gradient.setter
	def gradient(self, value):
		self._gradient = value

	@gradient.decode
	def gradient(self, value) -> Optional[Gradient]:
		return None if value is None else Gradient.decode(value)

	@StateProperty(key='fill', default=0.32, allowNone=False, after=refresh, sortOrder=12)
	def fill(self) -> float:
		"""Opacity of the area under a clock-face curve, and of rose petals. `0` leaves them out."""
		return self._fill

	@fill.setter
	def fill(self, value):
		self._fill = min(max(float(value), 0.0), 1.0)

	@StateProperty(key='weight', default=0.012, allowNone=False, after=refresh, sortOrder=13)
	def weight(self) -> float:
		"""Line weight as a share of the radius."""
		return self._weight

	@weight.setter
	def weight(self, value):
		self._weight = max(float(value), 0.0)

	@StateProperty(key='now', default=True, allowNone=False, after=refresh, sortOrder=14)
	def showNow(self) -> bool:
		"""A hand at the current time (clock face) and a dot at the current value."""
		return self._showNow

	@showNow.setter
	def showNow(self, value):
		self._showNow = bool(value)

	@StateProperty(key='extremes', default=True, allowNone=False, after=refresh, sortOrder=15)
	def extremes(self) -> bool:
		"""Mark the window's high and low with their values (clock face)."""
		return self._extremes

	@extremes.setter
	def extremes(self, value):
		self._extremes = bool(value)

	@StateProperty(key='bins', default=16, allowNone=False, after=refresh, sortOrder=16)
	def bins(self) -> int:
		"""How many petals a rose has."""
		return self._bins

	@bins.setter
	def bins(self, value):
		self._bins = min(max(int(value), 3), 72)

	@StateProperty(key='rose-by', default='value', allowNone=False, after=refresh, sortOrder=17)
	def roseBy(self) -> str:
		"""`value` sizes a petal by the mean value in its direction; `frequency` by how often the wind came from there."""
		return self._roseBy

	@roseBy.setter
	def roseBy(self, value):
		self._roseBy = value

	@roseBy.decode
	def roseBy(self, value) -> str:
		text = str(value).strip().lower()
		if text not in ('value', 'frequency'):
			log.warning(f'polar graph ignored rose-by {value!r}: expected value or frequency')
			return 'value'
		return text

	@StateProperty(key='precision', default=0, allowNone=False, after=refresh, sortOrder=18)
	def precision(self) -> int:
		"""Decimal places on every number the graph prints."""
		return self._precision

	@precision.setter
	def precision(self, value):
		self._precision = max(int(value), 0)

	@StateProperty(key='label-size', default=0.075, allowNone=False, after=refresh, sortOrder=19)
	def labelSize(self) -> float:
		"""Label height as a share of the radius."""
		return self._labelSize

	@labelSize.setter
	def labelSize(self, value):
		self._labelSize = max(float(value), 0.01)

	# section data

	def windowBounds(self) -> Tuple[datetime, datetime]:
		"""The window's start and end. Today runs midnight to midnight, local; a length ends now."""
		moment = shared.now()
		length = self.window
		if length is None:
			start = moment.replace(hour=0, minute=0, second=0, microsecond=0)
			return start, start + timedelta(days=1)
		return moment - length, moment

	def points(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
		"""(turn, angle, value) arrays, oldest first. ``turn`` is 0..1 through the window.

		On a clock face the angle is the turn; on a direction graph it is the direction, and
		the turn is how recent the point is. Empty arrays when a series has no data yet.
		"""
		empty = np.array([])
		feed = self._feed(self._key)
		if feed is None:
			return empty, empty, empty
		start, end = self.windowBounds()
		span = (end - start).total_seconds()
		rows = feed.read(start, end + timedelta(seconds=1))
		if not rows:
			return empty, empty, empty
		times = np.array([t.timestamp() for t, _ in rows])
		values = np.array([v for _, v in rows])
		turn = (times - start.timestamp()) / span
		if self.isTime:
			return turn, turn * 360.0, values
		directions = self._feed(self._angleKey)
		rows = directions.read(start, end + timedelta(seconds=1)) if directions else []
		if not rows:
			return empty, empty, empty
		dtimes = np.array([t.timestamp() for t, _ in rows])
		dvalues = np.array([v for _, v in rows])
		# Each value takes the direction measured nearest to it in time.
		nearest = np.abs(dtimes[None, :] - times[:, None]).argmin(axis=1)
		return turn, dvalues[nearest], values

	# section paint

	def paintPolar(self, painter: QPainter):
		rect = self.rect()
		radius = min(rect.width(), rect.height()) / 2
		if radius <= 4:
			return
		outer = radius * (1 - 1.55 * self._labelSize)
		if outer <= 4:
			return
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		painter.save()
		painter.translate(rect.center())
		try:
			self._paintFace(painter, outer, radius)
		finally:
			painter.restore()

	def _scale(self, values: np.ndarray, rose: Optional[np.ndarray]) -> Tuple[float, float]:
		low, high = self._range
		source = values if rose is None else rose
		data = source[np.isfinite(source)] if len(source) else source
		if low is None:
			low = float(data.min()) if len(data) else 0.0
			if self.style == 'rose' or not self.isTime:
				low = min(low, 0.0)
		if high is None:
			high = float(data.max()) if len(data) else 1.0
		if self._range == (None, None):
			low, high = niceRange(low, high, max(self._rings, 1))
		elif self._range[0] is None:
			low = niceRange(low, high, max(self._rings, 1))[0]
		elif self._range[1] is None:
			high = niceRange(low, high, max(self._rings, 1))[1]
		if high <= low:
			high = low + 1.0
		return low, high

	def _radiusAt(self, value, low: float, high: float, outer: float):
		inner = outer * self._hole
		share = np.clip((np.asarray(value, dtype=float) - low) / (high - low), 0.0, 1.0)
		return inner + share * (outer - inner)

	def _turnRect(self, r: float) -> QRectF:
		return QRectF(-r, -r, 2 * r, 2 * r)

	def _point(self, angle, r) -> QPointF:
		track = ArcTrack(self._turnRect(r), 0.0, 360.0)
		return track.pointAtAngle(float(angle) - 90.0)

	def _text(self, painter: QPainter, text: str, at: QPointF, color: QColor, size: float, bold: bool = False):
		font = QFont(painter.font())
		font.setPixelSize(max(int(size), 6))
		font.setBold(bold)
		painter.setFont(font)
		painter.setPen(color)
		box = QRectF(0, 0, size * len(text) * 0.9 + size, size * 1.6)
		box.moveCenter(at)
		painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

	def _format(self, value: float) -> str:
		return f'{value:.{self._precision}f}'

	def _resolved(self) -> Gradient:
		"""The gradient placed on this graph's scale, the way a gauge places it on its range.

		Stops pinned to a unit (`99°F`) convert to the series' unit and stay at that reading. Any other
		gradient is stretched over the radius range, as it would be over a gauge's.
		"""
		feed = self._feeds.get(self._key)
		valueClass = None if feed is None else feed.valueClass
		gradient = self._gradient
		if valueClass is None:
			return gradient
		if gradient.hasUnits:
			resolved = gradient.resolve(valueClass)
			return resolved if len(resolved) else gradient
		if issubclass(gradient.itemCls.__item__, valueClass):
			return gradient
		low, high = self._shownRange
		cache = self.__dict__.setdefault('_stretched', {})
		if (valueClass, low, high) not in cache:
			cache[valueClass, low, high] = gradient.as_type(valueClass, valueClass(low), valueClass(high))
		return cache[valueClass, low, high]

	def _seriesColor(self) -> QColor:
		return (self._color or Color.role('accent')).QColor

	def _valueColor(self, value: float) -> QColor:
		if self._gradient is None:
			return self._seriesColor()
		try:
			return self._resolved().get_color_for_value(value).QColor
		except Exception:
			return self._seriesColor()

	def _paintFace(self, painter: QPainter, outer: float, radius: float):
		turn, angles, values = self.points()
		style = self.style
		rose = None
		if style == 'rose' and len(values):
			rose = binned(angles, values, self._bins, self._roseBy == 'frequency')
		low, high = self._shownRange = self._scale(values, rose)
		grid = Color.role('rule').QColor
		muted = Color.role('muted').QColor
		text = Color.role('text').QColor
		labelPx = radius * self._labelSize
		weight = max(outer * self._weight, 1.0)
		self._paintGrid(painter, outer, low, high, grid, muted, labelPx, rose is not None and self._roseBy == 'frequency')
		if not len(values):
			return
		if style in ('area', 'line'):
			self._paintCurve(painter, outer, low, high, turn, values, weight, text, labelPx)
		elif style == 'trail':
			self._paintTrail(painter, outer, low, high, turn, angles, values, weight, text, labelPx)
		elif style == 'rose':
			self._paintRose(painter, outer, low, high, rose, weight)

	def _spokeCount(self) -> int:
		return 8 if self._spokes is None else self._spokes

	def _paintGrid(self, painter, outer, low, high, grid: QColor, muted: QColor, labelPx: float, share: bool):
		pen = QPen(grid)
		pen.setWidthF(1.0)
		pen.setCosmetic(True)
		painter.setBrush(Qt.BrushStyle.NoBrush)
		painter.setPen(pen)
		inner = outer * self._hole
		# Rings at round values. The outer ring is the scale's top.
		step = niceStep(high - low, max(self._rings, 1))
		values = [low + step * i for i in range(int((high - low) / step + 1e-9) + 1)] if self._rings else []
		if self._rings and (not values or values[-1] < high - 1e-9):
			values.append(high)
		for value in values:
			r = float(self._radiusAt(value, low, high, outer))
			painter.drawPath(ArcTrack(self._turnRect(r), 0.0, 360.0).subPath())
		if inner > 0:
			painter.drawPath(ArcTrack(self._turnRect(inner), 0.0, 360.0).subPath())
		spokes = self._spokeCount()
		start = self.turnStart
		for i in range(spokes):
			angle = start + 360.0 * i / spokes if self.isTime else 360.0 * i / spokes
			a, b = self._point(angle, inner), self._point(angle, outer)
			painter.drawLine(a, b)
		self._paintLabels(painter, outer, muted, labelPx)
		# Ring values sit just right of the top spoke, over the rings, so they read as a scale.
		for value in values[1:] if inner <= 0 else values:
			r = float(self._radiusAt(value, low, high, outer))
			shown = f'{value * 100:.0f}%' if share else self._format(value)
			self._text(painter, shown, QPointF(labelPx * 0.55 * len(shown) * 0.5 + 3, -r + labelPx * 0.55), muted, labelPx * 0.8)

	def _labelFor(self, mode: str, i: int, spokes: int) -> Optional[str]:
		if mode == 'hours':
			hour = (24 * i / spokes) % 24
			return f'{hour:02.0f}' if float(hour).is_integer() else None
		if mode == 'degrees':
			return f'{360 * i / spokes:.0f}°'
		if mode == 'compass':
			points = 8
			if spokes % points == 0 and i % (spokes // points) == 0:
				return COMPASS[(i // (spokes // points)) % points]
			return None
		return None

	def _paintLabels(self, painter, outer, color: QColor, labelPx: float):
		mode = self._labels
		if mode == 'false':
			return
		if mode == 'auto':
			mode = 'hours' if self.isTime else 'compass'
		spokes = self._spokeCount()
		if not spokes:
			return
		start = self.turnStart
		for i in range(spokes):
			label = self._labelFor(mode, i, spokes)
			if label is None:
				continue
			angle = start + 360.0 * i / spokes if self.isTime else 360.0 * i / spokes
			self._text(painter, label, self._point(angle, outer + labelPx * 0.95), color, labelPx)

	def _curvePoints(self, turn, values, low, high, outer):
		"""The curve as points in x (degrees) and r, smoothed, oldest first."""
		x, y = np.unique(np.column_stack([turn * 360.0, values]), axis=0).T if len(turn) > 1 else (turn * 360.0, values)
		x, y = smoothed(x, y, per=2.0)
		return x, self._radiusAt(y, low, high, outer)

	def _paintCurve(self, painter, outer, low, high, turn, values, weight, text: QColor, labelPx: float):
		x, r = self._curvePoints(turn, values, low, high, outer)
		start = self.turnStart
		pts = [self._point(start + a, rr) for a, rr in zip(x, r)]
		if len(pts) == 1:
			pts = [pts[0], pts[0]]
		inner = outer * self._hole
		line = QPainterPath(pts[0])
		for p in pts[1:]:
			line.lineTo(p)
		closed = (x[-1] - x[0]) >= 0.9 * 360.0
		if self._fill > 0 and self.style == 'area':
			fillPath = QPainterPath(line)
			if closed:
				fillPath.closeSubpath()
				fillPath.addPath(ArcTrack(self._turnRect(inner), 0.0, 360.0).subPath())
				fillPath.setFillRule(Qt.FillRule.OddEvenFill)
			else:
				for a in reversed(x):
					fillPath.lineTo(self._point(start + a, inner))
				fillPath.closeSubpath()
			painter.setPen(Qt.PenStyle.NoPen)
			painter.setBrush(QBrush(self._fillBrush(outer, low, high)))
			painter.drawPath(fillPath)
		painter.setBrush(Qt.BrushStyle.NoBrush)
		if self._gradient is None:
			pen = QPen(self._seriesColor(), weight, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
			painter.setPen(pen)
			if closed:
				line.closeSubpath()
			painter.drawPath(line)
		else:
			# One segment at a time, each the colour of the value at its far end.
			ys = np.interp(r, [inner, outer], [low, high])
			for i in range(1, len(pts)):
				painter.setPen(QPen(self._valueColor(float(ys[i])), weight, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
				painter.drawLine(pts[i - 1], pts[i])
			if closed:
				painter.setPen(QPen(self._valueColor(float(ys[0])), weight, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
				painter.drawLine(pts[-1], pts[0])
		if self._extremes and self.isTime:
			self._paintExtremes(painter, outer, low, high, turn, values, labelPx, text)
		if self._showNow and self.isTime:
			self._paintNow(painter, outer, low, high, turn, values, weight, text, labelPx)

	def _paintExtremes(self, painter, outer, low, high, turn, values, labelPx, text: QColor):
		for index, tint in ((int(np.argmax(values)), 'bad'), (int(np.argmin(values)), 'info')):
			value = float(values[index])
			r = float(self._radiusAt(value, low, high, outer))
			at = self._point(self.turnStart + turn[index] * 360.0, r)
			color = Color.role(tint).QColor
			painter.setPen(Qt.PenStyle.NoPen)
			painter.setBrush(color)
			dot = labelPx * 0.28
			painter.drawEllipse(at, dot, dot)
			# The label sits inward of the dot, towards the centre, where there is room.
			towards = QPointF(-at.x(), -at.y())
			length = max((towards.x() ** 2 + towards.y() ** 2) ** 0.5, 1.0)
			where = at + QPointF(towards.x() / length, towards.y() / length) * labelPx * 1.1
			self._text(painter, self._format(value), where, color, labelPx * 0.9, bold=True)

	def _paintNow(self, painter, outer, low, high, turn, values, weight, text: QColor, labelPx: float):
		start, end = self.windowBounds()
		span = (end - start).total_seconds()
		share = (shared.now() - start).total_seconds() / span
		if not 0.0 <= share <= 1.0:
			return
		angle = self.turnStart + share * 360.0
		inner = outer * self._hole
		pen = QPen(Color.role('text').QColor, max(weight * 0.6, 1.0), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
		pen.setColor(self._withAlpha(text, 0.85))
		painter.setPen(pen)
		painter.drawLine(self._point(angle, inner), self._point(angle, outer))
		feed = self._feed(self._key)
		value = feed.now() if feed else None
		if value is None and len(values):
			value = float(np.interp(share, turn, values))
		if value is None:
			return
		at = self._point(angle, float(self._radiusAt(value, low, high, outer)))
		painter.setPen(QPen(Color.role('background').QColor, max(weight * 0.7, 1.0)))
		painter.setBrush(self._valueColor(value))
		dot = max(weight * 1.6, labelPx * 0.3)
		painter.drawEllipse(at, dot, dot)
		self._text(painter, self._format(value), QPointF(0, 0), text, labelPx * 2.2, bold=True)

	def _fillBrush(self, outer: float, low: float, high: float):
		"""One colour, or with a gradient the colour of each radius's value, so the fill reads like the line."""
		if self._gradient is None:
			return self._withAlpha(self._seriesColor(), self._fill)
		inner = outer * self._hole
		brush = QRadialGradient(QPointF(0, 0), outer)
		for step in range(9):
			share = step / 8
			value = low + (high - low) * share
			brush.setColorAt(inner / outer + (1 - inner / outer) * share, self._withAlpha(self._valueColor(value), self._fill))
		return brush

	@staticmethod
	def _withAlpha(color: QColor, alpha: float) -> QColor:
		color = QColor(color)
		color.setAlphaF(alpha)
		return color

	def _trailPath(self, turn, angles, values):
		"""The trail between samples: direction turns the short way round, value follows a monotone cubic.

		Joining hourly samples with chords cuts straight across the centre when the wind swings through
		south; interpolating in angle and radius sweeps round the way the wind did. Returns
		(freshness 0..1, angle, value) for each step, oldest first.
		"""
		if len(turn) < 3:
			return turn, angles, values
		order = np.argsort(turn, kind='stable')
		t, a, v = turn[order], np.degrees(np.unwrap(np.radians(angles[order]))), values[order]
		t, keep = np.unique(t, return_index=True)
		a, v = a[keep], v[keep]
		if len(t) < 3:
			return t, a, v
		from scipy.interpolate import PchipInterpolator
		grid = np.linspace(t[0], t[-1], max(len(t) * 10, 40))
		return grid, PchipInterpolator(t, a)(grid) % 360.0, np.maximum(PchipInterpolator(t, v)(grid), 0.0)

	def _paintTrail(self, painter, outer, low, high, turn, angles, values, weight, text: QColor, labelPx: float):
		path_t, path_a, path_v = self._trailPath(turn, angles, values)
		path = [self._point(a, r) for a, r in zip(path_a, self._radiusAt(path_v, low, high, outer))]
		painter.setBrush(Qt.BrushStyle.NoBrush)
		steps = len(path)
		for i in range(1, steps):
			# Recent is solid; the far end of the window is a ghost.
			age = i / max(steps - 1, 1)
			color = self._valueColor(float(path_v[i]))
			color.setAlphaF(0.12 + 0.88 * age)
			painter.setPen(QPen(color, weight * (0.6 + 0.8 * age), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
			painter.drawLine(path[i - 1], path[i])
		pts = [self._point(a, r) for a, r in zip(angles, self._radiusAt(values, low, high, outer))]
		count = len(pts)
		painter.setPen(Qt.PenStyle.NoPen)
		for i, p in enumerate(pts):
			age = i / max(count - 1, 1)
			color = self._valueColor(float(values[i]))
			color.setAlphaF(0.15 + 0.6 * age)
			painter.setBrush(color)
			painter.drawEllipse(p, weight * 0.9, weight * 0.9)
		if self._showNow and count:
			last = pts[-1]
			hand = QPen(self._withAlpha(text, 0.35), max(weight * 0.5, 1.0), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
			painter.setPen(hand)
			painter.drawLine(QPointF(0, 0), last)
			painter.setPen(QPen(Color.role('background').QColor, max(weight * 0.7, 1.0)))
			painter.setBrush(self._valueColor(float(values[-1])))
			painter.drawEllipse(last, weight * 2.4, weight * 2.4)
			self._text(painter, self._format(float(values[-1])), QPointF(0, 0), text, labelPx * 1.8, bold=True)

	def _wedge(self, inner: float, outer: float, a0: float, a1: float) -> QPainterPath:
		"""The slice between two radii and two dial angles, from the same arcs the meter draws."""
		path = ArcTrack(self._turnRect(outer), a0, a1).subPath()
		back = ArcTrack(self._turnRect(max(inner, 0.0)), a1, a0).subPath()
		path.connectPath(back)
		path.closeSubpath()
		return path

	def _paintRose(self, painter, outer, low, high, petals: np.ndarray, weight: float):
		width = 360.0 / self._bins
		inner = outer * self._hole
		gap = min(width * 0.06, 1.5)
		for i, value in enumerate(petals):
			if not value > low:
				continue
			r = float(self._radiusAt(value, low, high, outer))
			if r <= inner:
				continue
			centre = i * width
			path = self._wedge(inner, r, centre - width / 2 + gap, centre + width / 2 - gap)
			color = self._valueColor(float(value))
			painter.setBrush(QBrush(self._withAlpha(color, min(max(self._fill, 0.05) * 2.2, 1.0))))
			painter.setPen(QPen(color, max(weight * 0.5, 1.0)))
			painter.drawPath(path)
