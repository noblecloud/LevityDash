"""`type: polar`: a plot whose angle is a direction or a time of day and whose radius is a value.

```yaml
- type: polar
  plot: rose                  # rose | trail | clock | carousel | radar
  direction: environment.wind.direction.direction   # rose and trail
  speed: environment.wind.speed.speed               # rose and trail; a key or an expression
  window: today               # today | 24h | +24h | 3d
  sectors: 16                 # rose: petals round the compass
  rings: 4                    # about this many value rings
  max: 30                     # outer ring: percent of time (rose), speed (trail), value (clock)
  gradient: WindSpeedGradient # colours by speed (rose, trail) or by value (clock)
```

```yaml
- type: polar
  plot: clock
  key: environment.temperature.temperature
  span: 24                    # 24 | 12 hours round the face
  top: noon                   # noon | midnight, for a 24 hour face
  accent: '#ff9124'           # the line, when there is no gradient
```

```yaml
- type: polar
  plot: carousel
  direction: environment.wind.direction.direction   # one current value, not a series
  view: 120                   # degrees across the strip
  compass: 16                 # letters: 4 | 8 | 16
  legend: true                # the bearing and its name under the pointer
```

```yaml
- type: polar
  plot: radar
  prefix: aircraft            # the slots to read: aircraft.1.bearing, aircraft.1.distance, ... aircraft.N.callsign
  slots: 20                   # how many slots to read, from the nearest
  max: 50                     # the rim, in the slots' distance unit (nautical miles for the Aircraft plugin)
  rings: 4
  labels: 6                   # name this many of the nearest; 0 for none
  ceiling: 40000              # altitude that takes the last colour of the gradient (feet)
  sweep: true                 # a sweep line turning once every 8 seconds
  glyphs: true                # a silhouette of each aircraft's kind, turned to its heading; false for dots
  glyph-scale: 1              # a multiplier on the silhouette's size, so the traffic reads from across a room
```

A radar puts each thing at its bearing from you (north up) and its distance from the middle, out to `max`. It
reads current values, not series: for each slot `N` of `prefix` the keys `prefix.N.bearing`, `.distance`, `.altitude`,
`.heading`, `.speed`, `.callsign`, `.type` and `.category`, with `prefix.count` saying how many slots are filled (the `Aircraft`
plugin publishes exactly these). The colour follows altitude through `gradient` (or the theme's cool-to-hot
ramp), the short tail follows heading and speed. `legend: false` drops the count in the corner and `altitudes: false`
the flight level after each name.

To show the radar only while something is overhead, give the item `when: aircraft.active` (the Aircraft plugin holds it
on for `hold` seconds after the last plane leaves, so the radar does not blink); `when: aircraft.near > 0` is the same
without the hold, and `when: aircraft.count > 0` any plane in range.

The carousel is a strip of compass letters that slides so the current direction stays under a pointer
in the middle (`[w N e]`). It reads one live value (`lib/valuesource.py`), not a series, and slides the
short way round, so 350 to 10 does not spin through south.

The other plots read whole series from the dispatcher (`feed.SeriesFeed`), so they draw the same
values a graph of that key would. `key`, `direction` and `speed` also take an expression over keys
(`key: environment.temperature.temperature - environment.temperature.dewpoint`, `speed: max(a, b)`).
It is evaluated at every sample time (`series.derive`), because a computed key holds one value and no
history. A time where an input has no sample yet is left out. Maths lives in `geometry.py` and the painting in `draw.py`; this
file reads the settings, owns the feeds and chooses what to hand to the painter.
"""
import time
from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import QEasingCurve, QRectF, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGraphicsItem

from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.plugins.expressions import Expression, ExpressionError
from LevityDash.lib.stateful import StateProperty
from LevityDash.lib.ui.colors import Color, Gradient, theme
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar import draw, radar
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.feed import Series, openCurrent, openFeed, openValue
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.geometry import (
	parseWindow, roseBins, windowBounds,
)
from LevityDash.lib.utils.shared import now as localNow

#: What a radar reads from each slot, and whether it is text.
_RADAR_FIELDS = {'callsign': True, 'type': True, 'category': True, 'bearing': False, 'distance': False, 'altitude': False, 'heading': False, 'speed': False}
_SWEEP_SECONDS = 8.0

__all__ = ['Polar']

log = LevityPluginLog.getChild('Polar')

_PLOTS = ('rose', 'trail', 'clock', 'carousel', 'radar')


def _oneOf(name: str, value, allowed: tuple):
	if value not in allowed:
		raise ValueError(f'{name} is one of {", ".join(map(str, allowed))}, not {value!r}')
	return value


def _expression(name: str, value) -> Optional[str]:
	"""The text of a key or an expression over keys, or None. Text that is neither says why."""
	if value is None or str(value).strip() == '':
		return None
	text = str(value).strip()
	try:
		Expression.parse(text)
	except ExpressionError as error:
		raise ValueError(f'{name}: {error}') from None
	return text


def _plain(value) -> Optional[float]:
	"""A number from whatever a key holds: a measurement's value, or a plain number."""
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.series import number
	return number(value)


class Polar(Panel, tag='polar'):
	"""A polar plot panel. The settings are listed in the module docstring."""

	__exclude__ = {..., 'items'}
	_acceptsChildren = False

	def __init__(self, *args, **kwargs):
		self._plot = 'rose'
		self._key = None
		self._direction = None
		self._speed = None
		self._window = 'today'
		self._sectors = 16
		self._rings = 4
		self._max = None
		self._min = None
		self._gradient = None
		self._accent = None
		self._compass = 8
		self._span = 24
		self._top = 'noon'
		self._smooth = True
		self._stamps = 6
		self._legend = True
		self._marks = True
		self._view = 120.0
		self._shown: Optional[float] = None
		self._slide = None
		self._source = None
		self._sourceText = None
		self._prefix = 'aircraft'
		self._slots = 20
		self._labels = 6
		self._ceiling = 40000.0
		self._sweep = False
		self._levels = True
		self._glyphs = True
		self._glyphScale = 1.0
		self._sweepTimer = None
		self._radarSources: list = []
		self._radarValues: dict = {}
		self._feeds: dict[str, object] = {}
		self._feedText: dict[str, str] = {}
		super().__init__(*args, **kwargs)
		self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemHasNoContents, False)
		# A clock face's hand moves; a minute is coarse enough and the timer is made on the GUI thread.
		self._clock = QTimer(interval=60_000)
		self._clock.timeout.connect(self.update)
		self._clock.start()
		self._connect()

	@property
	def isEmpty(self) -> bool:
		return False

	def refresh(self):
		self.update()

	def _changed(self):
		self.update()

	def _connectDirection(self):
		"""The carousel reads one live value, so it takes a value feed, not a series feed."""
		text = self._direction if self._plot == 'carousel' else None
		if text == self._sourceText:
			return
		self._dropSource()
		self._sourceText = text
		if text:
			try:
				self._source = openValue(text, self._follow)
			except Exception as error:  # noqa: BLE001 - a bad key must not abort the dashboard load
				log.warning(f'polar direction {text!r}: {error!r}; it shows no data')

	def _connectRadar(self):
		"""A radar reads one current value per field per slot, so it opens a value source for each."""
		wanted = (self._prefix, self._slots) if self._plot == 'radar' else None
		if wanted == getattr(self, '_radarWanted', None):
			self._startSweep()
			return
		self._dropRadar()
		self._radarWanted = wanted
		self._startSweep()
		if wanted is None:
			return
		keys = [('count', None, f'{self._prefix}.count')]
		keys += [(field, n, f'{self._prefix}.{n}.{field}') for n in range(1, self._slots + 1) for field in _RADAR_FIELDS]
		for field, slot, key in keys:
			try:
				source = openCurrent(key, lambda value, field=field, slot=slot: self._radarChanged(field, slot, value))
			except Exception as error:  # noqa: BLE001 - a bad key must not abort the dashboard load
				log.warning(f'polar radar {key!r}: {error!r}; it shows no data')
				continue
			if not source.opened:
				continue
			self._radarSources.append(source)
			self._radarChanged(field, slot, source.get())

	def _radarChanged(self, field: str, slot, value):
		if value is None or type(value).__name__ == 'UnsetType':
			return
		if field in ('callsign', 'type', 'category'):
			self._radarValues[(field, slot)] = str(value).strip()
		else:
			number = _plain(value)
			if number is None:
				return
			self._radarValues[(field, slot)] = number
		self.update()

	def _dropRadar(self):
		sources, self._radarSources = self._radarSources, []
		for source in sources:
			try:
				source.close()
			except Exception:  # noqa: BLE001
				pass
		self._radarValues.clear()

	def _startSweep(self):
		on = self._plot == 'radar' and self._sweep
		if on and self._sweepTimer is None:
			self._sweepTimer = QTimer(interval=66)
			self._sweepTimer.timeout.connect(self.update)
			self._sweepTimer.start()
		elif not on and self._sweepTimer is not None:
			self._sweepTimer.stop()
			self._sweepTimer = None

	def _dropSource(self):
		source, self._source = self._source, None
		if source is not None:
			source.close()

	def _follow(self, target: float):
		"""Slide the carousel to a new direction, the short way round the circle."""
		target %= 360
		if self._shown is None or not self.isVisible():
			self._shown = target
			self.update()
			return
		start = self._shown
		delta = ((target - start + 180) % 360) - 180
		if self._slide is not None:
			self._slide.stop()
		if abs(delta) < 0.01:
			return
		self._slide = QVariantAnimation(self, startValue=0.0, endValue=delta, duration=700)
		self._slide.setEasingCurve(QEasingCurve.Type.InOutCubic)
		self._slide.valueChanged.connect(lambda step, start=start: self._step(start + step))
		self._slide.start()

	def _step(self, degrees: float):
		self._shown = float(degrees) % 360
		self.update()

	# -- data ---------------------------------------------------------------------------------

	def _connect(self):
		"""Open a feed for each key the current plot reads, and close the ones it no longer reads.

		A key is a key or an expression over keys (`temperature - dewpoint`); an expression is
		evaluated at every sample, so the plot gets a whole series, not one value."""
		wanted = {
			'rose': {'direction': self._direction, 'speed': self._speed},
			'trail': {'direction': self._direction, 'speed': self._speed},
			'clock': {'value': self._key},
			'carousel': {},
			'radar': {},
		}[self._plot]
		wanted = {name: key for name, key in wanted.items() if key}
		self._connectDirection()
		self._connectRadar()
		for name in list(self._feeds):
			if wanted.get(name) != self._feedText.get(name):
				self._feeds.pop(name).close()
				self._feedText.pop(name, None)
		for name, key in wanted.items():
			if name not in self._feeds:
				try:
					self._feeds[name] = openFeed(str(key), self._changed)
					self._feedText[name] = str(key)
				except Exception as error:  # noqa: BLE001 - a bad key must not abort the dashboard load
					log.warning(f'polar {name} {key!r}: {error!r}; it shows no data')
		self.update()

	def release(self):
		"""Stop the clock and let go of every feed. A dashboard reload and `delete` both end here."""
		self._clock.stop()
		if self._sweepTimer is not None:
			self._sweepTimer.stop()
			self._sweepTimer = None
		self._dropRadar()
		self._radarWanted = None
		if self._slide is not None:
			self._slide.stop()
		self._dropSource()
		for feed in self._feeds.values():
			feed.close()
		self._feeds.clear()
		self._feedText.clear()

	def delete(self):
		self.release()
		super().delete()

	def _series(self, name: str) -> Series:
		feed = self._feeds.get(name)
		return feed.series if feed is not None else Series()

	def _windowed(self, series: Series) -> Series:
		start, end = windowBounds(parseWindow(self._window), localNow())
		return series.between(start, end)

	# -- settings -----------------------------------------------------------------------------

	@StateProperty(key='plot', default='rose', allowNone=False, after=_connect, repr=True)
	def plot(self) -> str:
		return self._plot

	@plot.setter
	def plot(self, value: str):
		self._plot = value

	@plot.decode
	def plot(self, value) -> str:
		return _oneOf('plot', str(value).lower(), _PLOTS)

	@StateProperty(key='key', default=None, after=_connect, repr=True)
	def key(self) -> Optional[str]:
		return self._key

	@key.setter
	def key(self, value: Optional[str]):
		self._key = value

	@key.decode
	def key(self, value) -> Optional[str]:
		return _expression('key', value)

	@StateProperty(key='direction', default=None, after=_connect, repr=True)
	def direction(self) -> Optional[str]:
		return self._direction

	@direction.setter
	def direction(self, value: Optional[str]):
		self._direction = value

	@direction.decode
	def direction(self, value) -> Optional[str]:
		return _expression('direction', value)

	@StateProperty(key='speed', default=None, after=_connect, repr=True)
	def speed(self) -> Optional[str]:
		return self._speed

	@speed.setter
	def speed(self, value: Optional[str]):
		self._speed = value

	@speed.decode
	def speed(self, value) -> Optional[str]:
		return _expression('speed', value)

	@StateProperty(key='prefix', default='aircraft', allowNone=False, after=_connect)
	def prefix(self) -> str:
		return self._prefix

	@prefix.setter
	def prefix(self, value: str):
		self._prefix = value

	@prefix.decode
	def prefix(self, value) -> str:
		text = str(value).strip().strip('.')
		if not text:
			raise ValueError('prefix is the start of the keys a radar reads, like aircraft')
		return text

	@StateProperty(key='slots', default=20, allowNone=False, after=_connect)
	def slots(self) -> int:
		return self._slots

	@slots.setter
	def slots(self, value: int):
		self._slots = value

	@slots.decode
	def slots(self, value) -> int:
		return max(1, min(60, int(value)))

	@StateProperty(key='labels', default=6, allowNone=False, after=refresh)
	def labels(self) -> int:
		return self._labels

	@labels.setter
	def labels(self, value: int):
		self._labels = value

	@labels.decode
	def labels(self, value) -> int:
		return max(0, int(value))

	@StateProperty(key='ceiling', default=40000.0, allowNone=False, after=refresh)
	def ceiling(self) -> float:
		return self._ceiling

	@ceiling.setter
	def ceiling(self, value: float):
		self._ceiling = value

	@ceiling.decode
	def ceiling(self, value) -> float:
		value = float(value)
		if value <= 0:
			raise ValueError(f'ceiling is above zero, not {value}')
		return value

	@StateProperty(key='sweep', default=False, allowNone=False, after=_connect)
	def sweep(self) -> bool:
		return self._sweep

	@sweep.setter
	def sweep(self, value: bool):
		self._sweep = bool(value)

	@StateProperty(key='glyphs', default=True, allowNone=False, after=refresh)
	def glyphs(self) -> bool:
		return self._glyphs

	@glyphs.setter
	def glyphs(self, value: bool):
		self._glyphs = bool(value)

	@StateProperty(key='glyph-scale', default=1.0, allowNone=False, after=refresh)
	def glyphScale(self) -> float:
		return self._glyphScale

	@glyphScale.setter
	def glyphScale(self, value: float):
		self._glyphScale = value

	@glyphScale.decode
	def glyphScale(self, value) -> float:
		return max(0.1, min(6.0, float(value)))

	@StateProperty(key='altitudes', default=True, allowNone=False, after=refresh)
	def altitudes(self) -> bool:
		return self._levels

	@altitudes.setter
	def altitudes(self, value: bool):
		self._levels = bool(value)

	@StateProperty(key='window', default='today', allowNone=False, after=refresh)
	def window(self) -> str:
		return self._window

	@window.setter
	def window(self, value: str):
		self._window = value

	@window.decode
	def window(self, value) -> str:
		parseWindow(value)
		return str(value)

	@StateProperty(key='sectors', default=16, allowNone=False, after=refresh)
	def sectors(self) -> int:
		return self._sectors

	@sectors.setter
	def sectors(self, value: int):
		self._sectors = value

	@sectors.decode
	def sectors(self, value) -> int:
		return _oneOf('sectors', int(value), (4, 8, 12, 16, 24, 32))

	@StateProperty(key='rings', default=4, allowNone=False, after=refresh)
	def rings(self) -> int:
		return self._rings

	@rings.setter
	def rings(self, value: int):
		self._rings = value

	@rings.decode
	def rings(self, value) -> int:
		return max(1, min(12, int(value)))

	@StateProperty(key='max', default=None, after=refresh)
	def max(self) -> Optional[float]:
		return self._max

	@max.setter
	def max(self, value: Optional[float]):
		self._max = value

	@max.decode
	def max(self, value) -> Optional[float]:
		return None if value is None else float(value)

	@StateProperty(key='min', default=None, after=refresh)
	def min(self) -> Optional[float]:
		return self._min

	@min.setter
	def min(self, value: Optional[float]):
		self._min = value

	@min.decode
	def min(self, value) -> Optional[float]:
		return None if value is None else float(value)

	@StateProperty(key='gradient', default=None, after=refresh, decoder=Gradient.decode)
	def gradient(self) -> Optional[Gradient]:
		return self._gradient

	@gradient.setter
	def gradient(self, value: Optional[Gradient]):
		self._gradient = value

	@StateProperty(key='accent', default=None, after=refresh)
	def accent(self) -> Optional[Color]:
		return self._accent

	@accent.setter
	def accent(self, value: Optional[Color]):
		self._accent = value

	@accent.decode
	def accent(self, value) -> Optional[Color]:
		return None if value is None else Color.decode(value)

	@accent.encode
	def accent(self, value: Optional[Color]) -> Optional[str]:
		return None if value is None else str(value)

	@StateProperty(key='compass', default=8, allowNone=False, after=refresh)
	def compass(self) -> int:
		return self._compass

	@compass.setter
	def compass(self, value: int):
		self._compass = value

	@compass.decode
	def compass(self, value) -> int:
		return _oneOf('compass', int(value), (4, 8, 16))

	@StateProperty(key='span', default=24, allowNone=False, after=refresh)
	def span(self) -> int:
		return self._span

	@span.setter
	def span(self, value: int):
		self._span = value

	@span.decode
	def span(self, value) -> int:
		return _oneOf('span', int(value), (12, 24))

	@StateProperty(key='top', default='noon', allowNone=False, after=refresh)
	def top(self) -> str:
		return self._top

	@top.setter
	def top(self, value: str):
		self._top = value

	@top.decode
	def top(self, value) -> str:
		return _oneOf('top', str(value).lower(), ('noon', 'midnight'))

	@StateProperty(key='view', default=120.0, allowNone=False, after=refresh)
	def view(self) -> float:
		return self._view

	@view.setter
	def view(self, value: float):
		self._view = value

	@view.decode
	def view(self, value) -> float:
		value = float(value)
		if not 20 <= value <= 360:
			raise ValueError(f'view is 20 to 360 degrees, not {value}')
		return value

	@StateProperty(key='smooth', default=True, allowNone=False, after=refresh)
	def smooth(self) -> bool:
		return self._smooth

	@smooth.setter
	def smooth(self, value: bool):
		self._smooth = bool(value)

	@StateProperty(key='stamps', default=6, allowNone=False, after=refresh)
	def stamps(self) -> int:
		return self._stamps

	@stamps.setter
	def stamps(self, value: int):
		self._stamps = value

	@stamps.decode
	def stamps(self, value) -> int:
		return max(0, int(value))

	@StateProperty(key='legend', default=True, allowNone=False, after=refresh)
	def legend(self) -> bool:
		return self._legend

	@legend.setter
	def legend(self, value: bool):
		self._legend = bool(value)

	@StateProperty(key='marks', default=True, allowNone=False, after=refresh)
	def marks(self) -> bool:
		return self._marks

	@marks.setter
	def marks(self, value: bool):
		self._marks = bool(value)

	# -- painting -----------------------------------------------------------------------------

	def _look(self) -> draw.Look:
		active = theme.active()
		accent = self._accent.QColor if self._accent is not None else active.color('accent').QColor
		return draw.Look(
			text=active.color('text').QColor, muted=active.color('muted').QColor, faint=active.color('faint').QColor,
			rule=active.color('rule').QColor, accent=accent,
			display=active.font('display'), mono=active.font('mono'),
			ramp=tuple(active.color(t).QColor for t in ('info', 'good', 'warn', 'bad')),
		)

	def _colorFor(self, look: draw.Look, series: Series, lo: float, hi: float):
		"""A function from a value to its colour: the gradient when there is one, else the theme's cool-to-hot ramp."""
		gradient = self._gradient
		if gradient is not None:
			if gradient.hasUnits and series.cls is not None:
				gradient = gradient.resolve(series.cls)
			return lambda value: gradient.get_color_for_value(value).QColor
		span = (hi - lo) or 1.0
		return lambda value: draw.rampColor(look.ramp, (value - lo) / span)

	def paint(self, painter: QPainter, option, widget=None):
		rect = QRectF(self.rect())
		if rect.width() < 8 or rect.height() < 8:
			return
		look = self._look()
		try:
			match self._plot:
				case 'rose':
					self._paintRose(painter, look, rect)
				case 'trail':
					self._paintTrail(painter, look, rect)
				case 'clock':
					self._paintClock(painter, look, rect)
				case 'radar':
					self._paintRadar(painter, look, rect)
				case 'carousel':
					draw.drawCarousel(painter, look, rect, self._shown, self._view, self._compass, self._legend)
		except Exception as error:  # noqa: BLE001 - a paint error must not take the dashboard down
			if getattr(self, '_paintError', None) != repr(error):
				self._paintError = repr(error)
				log.exception(f'polar {self._plot} failed to paint: {error!r}')

	def _blips(self) -> list:
		"""The filled slots as `radar.Blip`s: the first `count` of them, or every slot with a name when there is no count."""
		values = self._radarValues
		count = values.get(('count', None))
		blips = []
		for n in range(1, self._slots + 1):
			name = values.get(('callsign', n))
			distance = values.get(('distance', n))
			bearing = values.get(('bearing', n))
			if distance is None or bearing is None or (count is not None and n > count) or name == '':
				continue
			blips.append(radar.Blip(
				name or '?', bearing, distance, values.get(('altitude', n), 0.0),
				values.get(('heading', n), 0.0), values.get(('speed', n), 0.0),
				values.get(('type', n), ''), values.get(('category', n), ''),
			))
		return blips

	def _paintRadar(self, painter, look, rect):
		blips = self._blips()
		top = self._max if self._max is not None else 50.0
		colorFor = self._colorFor(look, Series(), 0.0, self._ceiling)
		sweep = None
		if self._sweep:
			sweep = (time.monotonic() % _SWEEP_SECONDS) / _SWEEP_SECONDS * 360
		radar.drawRadar(
			painter, look, rect, blips, top, self._rings, self._compass, colorFor, self._labels, self._levels,
			sweep, legend=self._legend, glyphs=self._glyphs, glyphScale=self._glyphScale,
		)

	def _pairs(self):
		"""Direction and speed samples that share a timestamp, inside the window."""
		directions, speeds = self._windowed(self._series('direction')), self._windowed(self._series('speed'))
		speedAt = dict(zip(speeds.times, speeds.values))
		times, ds, ss = [], [], []
		for when, direction in zip(directions.times, directions.values):
			if when in speedAt:
				times.append(when)
				ds.append(direction)
				ss.append(speedAt[when])
		return times, ds, ss, directions, speeds

	def _paintRose(self, painter, look, rect):
		times, directions, speeds, dirSeries, speedSeries = self._pairs()
		edges = None
		top = max(speeds, default=0.0)
		rose = roseBins(directions, speeds, self._sectors, edges, calmBelow=0.0)
		colorFor = self._colorFor(look, speedSeries, 0.0, max(rose.edges[-1], 1.0))
		binColors = []
		for i, lower in enumerate(rose.edges):
			upper = rose.edges[i + 1] if i + 1 < len(rose.edges) else lower + (rose.edges[1] - rose.edges[0] if len(rose.edges) > 1 else 1)
			binColors.append(colorFor((lower + upper) / 2))
		draw.drawRose(
			painter, look, rect, rose, binColors, speedSeries.unit, self._max, self._rings, self._compass,
			self._series('direction').now, self._legend,
		)

	def _paintTrail(self, painter, look, rect):
		times, directions, speeds, dirSeries, speedSeries = self._pairs()
		if parseWindow(self._window)[0] != 'ahead':
			# A trail is where the wind has been, so a forecast hour does not belong on it.
			cutoff = localNow() + timedelta(minutes=30)
			keep = [i for i, when in enumerate(times) if when <= cutoff]
			times, directions, speeds = [times[i] for i in keep], [directions[i] for i in keep], [speeds[i] for i in keep]
		colorFor = self._colorFor(look, speedSeries, 0.0, max(speeds, default=1.0))
		draw.drawTrail(
			painter, look, rect, times, directions, speeds, speedSeries.unit, colorFor, self._max, self._rings,
			self._compass, self._stamps,
		)

	def _paintClock(self, painter, look, rect):
		series = self._windowed(self._series('value'))
		if not len(series):
			return
		lo = self._min if self._min is not None else min(series.values)
		hi = self._max if self._max is not None else max(series.values)
		pad = (hi - lo) * 0.05 or 1.0
		if self._min is None:
			lo -= pad
		if self._max is None:
			hi += pad
		colorFor = self._colorFor(look, series, lo, hi) if self._gradient is not None else None
		draw.drawClock(
			painter, look, rect, series.times, series.values, series.unit, self._span, self._top,
			lo, hi, self._rings, colorFor, localNow(), self._series('value').now, self._smooth, self._marks,
		)
