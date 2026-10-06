"""A straight meter: progress bars, batteries, segmented bars, thermometers.

`Bar` is a `Meter` on a `LineTrack`. It keeps everything a meter keeps - the value,
the range and its rounding, the value-to-position `Scale` - and answers the shape
questions with a line instead of an arc. YAML type ``realtime.bar``.

Where `Gauge` builds a scene item for each part (arc, zones, fill, needle, ticks),
a bar draws its parts in one canvas item, bottom to top: track, zones, fill, ticks,
markers, pointer, text. A bar is a few strokes and some text, so one paint pass is
smaller than a stack of items and keeps z-order and clipping in one place. Nothing
here touches `Gauge`; the two share `Meter` and `Scale`/`Track` only.

Every size is in px or a share of the bar's *cross* extent - its height when it lies
down, its width when it stands - so the same spec scales with the box. Colours go
through `Color.decode`, so ``$rule``, ``$accent`` and the other theme tokens work and
a raw value wins.

```yaml
- type: realtime.bar
  key: system.battery.charge
  display:
    range: {min: 0, max: 100}
    fill: {color: zone}
    zones: [{to: 20, color: $bad}, {from: 20, to: 50, color: $warn}, {from: 50, color: $good}]
    value-label: {position: end}
```
"""
import copy
from collections.abc import Mapping
from math import ceil, floor, isfinite, log10
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem

from LevityDash.lib.plugins.expressions import ExpressionError  # noqa: F401 - re-exported for specs that name it
from LevityDash.lib.stateful import Binding, StateProperty
from LevityDash.lib.ui import Color, Gradient, UILogger
from LevityDash.lib.ui.Geometry import DimensionType, parseWidth, size_px
from LevityDash.lib.ui.fonts import defaultFont
from LevityDash.lib.ui.glow import Glow, GlowMixin, paintGlow, resolveGlow
from LevityDash.lib.valuesource import openValueSource
from .elements import gaugeKeyName
from .meter import Meter
from .track import LineTrack

log = UILogger.getChild('meter.bar')

__all__ = ['Bar']

_CAPS = {'round': Qt.PenCapStyle.RoundCap, 'square': Qt.PenCapStyle.SquareCap, 'flat': Qt.PenCapStyle.FlatCap}

#: Sides of the box a label or tick can sit on, by the words a spec may use.
#: `before` is the top of a lying bar and the left of a standing one; `after` the other side.
_SIDES = {'before': 'before', 'above': 'before', 'top': 'before', 'left': 'before',
		'after': 'after', 'below': 'after', 'bottom': 'after', 'right': 'after', 'both': 'both'}

_MARKER_TYPES = ('line', 'triangle', 'pointer', 'dot', 'notch')

_STYLES = ('bar', 'battery', 'thermometer')


def _size(raw, name: str):
	"""A size spec (``12px``, ``20%``, ``0.2``) as a `parseWidth` value, or a `ValueError`."""
	value = parseWidth(raw, None)
	if value is None:
		raise ValueError(f'{name} {raw!r} is not a size')
	return value


def _color(raw) -> QColor:
	return Color.decode(raw).QColor


def _number(raw, name: str) -> float:
	if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not isfinite(raw):
		raise TypeError(f'{name} must be a finite number, not {raw!r}')
	return float(raw)


def _luminance(color: QColor) -> float:
	return 0.2126 * color.redF() + 0.7152 * color.greenF() + 0.0722 * color.blueF()


def _contrast(under: QColor) -> QColor:
	"""Text for a label that sits on ``under``: near-black on a light colour, white on a dark one."""
	return QColor('#101114') if _luminance(under) > 0.6 else QColor('#ffffff')


def _niceStep(span: float, target: int = 5) -> float:
	"""A tick interval of 1, 2 or 5 times a power of ten that gives about ``target`` steps."""
	if span <= 0:
		return 1.0
	raw = span / target
	power = 10 ** floor(log10(raw))
	return min((f * power for f in (1, 2, 5, 10)), key=lambda step: abs(log10(raw / step)))


def _alias(spec: Mapping, *keys, default=None):
	for key in keys:
		if key in spec:
			return spec[key]
	return default


class _SourceEnd:
	"""Adapts a value source to a setter on a bar part (a marker's value, a fill's end)."""

	def __init__(self, setter):
		self._setter = setter

	def setMarkerValue(self, value) -> None:
		self._setter(value)


class BarCanvas(QGraphicsItem):
	"""Paints a `Bar`. All the drawing is `Bar.paintBar`; this is the scene item that calls it."""

	def __init__(self, bar: 'Bar'):
		super().__init__(bar)
		self._bar = bar
		self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemHasNoContents, False)
		self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

	def boundingRect(self) -> QRectF:
		return self._bar.canvasRect()

	def paint(self, painter: QPainter, option, widget=None):
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		try:
			self._bar.paintBar(painter)
		except Exception as e:  # noqa: BLE001 - a bar that cannot draw must not take the board with it
			log.warning(f'Bar {gaugeKeyName(self._bar)} not drawn: {e!r}')


class Bar(GlowMixin, Meter):
	"""A meter on a straight track."""

	_valueClass = float
	_value = 0.0

	_canvas: Optional[BarCanvas] = None

	_orientation = 'horizontal'
	_style = 'bar'
	_trackSpec: Optional[dict] = None
	_valueSpec: Optional[dict] = None
	_unitSpec: Optional[dict] = None
	_captionSpec = None
	_subSpec = None
	_pointerSpec: Optional[dict] = None
	_majorSpec: Optional[dict] = None
	_minorSpec: Optional[dict] = None
	_fontSpec: Optional[str] = None

	def __init__(self, parent, *args, **kwargs):
		self.previousParent = None
		super().__init__(parent, *args, **kwargs)

	def _init_defaults_(self):
		self._valueClass = self.parent.container.value_type
		self._markers = []
		self._markerSpecs = []
		self._fill = None
		self._fillSpec = None
		self._zones = []
		self._zoneSpecs = []
		self._bindings = []
		self._pending = set()
		super()._init_defaults_()
		self._value = self._valueClass(0)
		self._pen = QPen(self.defaultColor)
		self._canvas = BarCanvas(self)
		self._canvas.setZValue(0)
		self.hide()

	@property
	def subtag(self) -> str:
		"""What the panel that holds this bar is saved as: ``realtime.bar``. A bar reports `DisplayType.Gauge`
		(inherited from `Meter`), which is what the panel's value feed keys on."""
		return 'bar'

	# -- what the owner expects of any meter ---------------------------------------------------------

	@property
	def value(self):
		return self._value

	@value.setter
	def value(self, value):
		if isinstance(value, (int, float)):
			self.valueClass = value
			if float(value) == float(self._value):
				return
			self._value = value
			self._redraw()

	def refresh(self):
		self._redraw()

	def _update_shape(self):
		self._redraw()

	def parentResized(self, arg):
		super(Meter, self).parentResized(arg)
		self.refresh()

	def _afterSetState(self):
		super()._afterSetState()
		self.refresh()

	def glowChanged(self):
		self._redraw()

	def _redraw(self):
		canvas = self._canvas
		if canvas is not None:
			canvas.prepareGeometryChange()
			canvas.update()

	def releaseSources(self):
		"""Stop and release every value source the markers and fill hold. Never raises."""
		for clear in (self._clearMarkers, self._clearFill):
			try:
				clear()
			except Exception as e:  # noqa: BLE001
				log.warning(f'Bar {gaugeKeyName(self)} could not release its value sources: {e!r}')

	# -- the box ------------------------------------------------------------------------------------

	@property
	def vertical(self) -> bool:
		return self._orientation == 'vertical'

	@property
	def across(self) -> float:
		"""The box's cross extent, in px: the reference every relative size resolves against."""
		rect = self.rect()
		return max(rect.width() if self.vertical else rect.height(), 1.0)

	@property
	def along(self) -> float:
		rect = self.rect()
		return max(rect.height() if self.vertical else rect.width(), 1.0)

	def sizeAcross(self, value, dimension: Optional[DimensionType] = None):
		"""A relative size resolved against the cross extent (the dial's `sizeAcross`, for a bar)."""
		return size_px(value, self.across, dimension=dimension)

	def sizeAlong(self, value, dimension: Optional[DimensionType] = None):
		"""A relative size resolved against the track's length."""
		return size_px(value, self.along, dimension=dimension)

	def canvasRect(self) -> QRectF:
		rect = QRectF(self.rect())
		glow = self.glow
		if glow is not None:
			rect = glow.pad(rect, self.across * 0.3, filled=True)
		return rect.adjusted(-2, -2, 2, 2)

	# -- state: shape --------------------------------------------------------------------------------

	@StateProperty(key='orientation', default='horizontal', allowNone=False, repr=True, after=Meter.rebuild)
	def orientation(self) -> str:
		"""``horizontal`` (the minimum at the left) or ``vertical`` (the minimum at the bottom)."""
		return self._orientation

	@orientation.setter
	def orientation(self, value: str):
		self._orientation = value

	@orientation.decode
	def orientation(self, value) -> str:
		text = str(value).strip().lower()
		if text not in ('horizontal', 'vertical'):
			raise ValueError(f'orientation must be horizontal or vertical, not {value!r}')
		return text

	@StateProperty(key='style', default='bar', allowNone=False, repr=True, after=Meter.rebuild)
	def style(self) -> str:
		"""``bar`` (a plain track), ``battery`` (an outlined cell with a terminal) or ``thermometer``
		(a tube with a bulb at the minimum; stands up whatever ``orientation`` says)."""
		return self._style

	@style.setter
	def style(self, value: str):
		self._style = value

	@style.decode
	def style(self, value) -> str:
		text = str(value).strip().lower()
		if text not in _STYLES:
			raise ValueError(f'style must be one of {", ".join(_STYLES)}, not {value!r}')
		return text

	@StateProperty(key='track', default=None, allowNone=True, after=Meter.rebuild)
	def track(self) -> Optional[dict]:
		"""The track under the data: ``{color, weight, cap, segments, gap}``. ``weight`` is a size
		(default 28% of the cross extent); ``cap`` is ``round`` (default), ``square`` or ``flat``;
		``segments`` and ``gap`` cut it into cells (a segmented ``fill`` cuts it the same way unless
		this says ``segments: false``)."""
		return self._trackSpec

	@track.setter
	def track(self, value: Optional[dict]):
		self._trackSpec = value

	@track.decode
	def track(self, value) -> Optional[dict]:
		return self._decodeMapping('track', value, {'color', 'weight', 'cap', 'segments', 'gap'})

	@track.encode
	def track(self, value):
		return copy.deepcopy(value) if value else None

	@StateProperty(key='pointer', default=None, allowNone=True, after=Meter.rebuild)
	def pointer(self) -> Optional[dict]:
		"""A marker shape riding the value, as a needle does on a dial:
		``{type: triangle|line|dot|notch, color, size, side}``. Left out, there is none."""
		return self._pointerSpec

	@pointer.setter
	def pointer(self, value: Optional[dict]):
		self._pointerSpec = value

	@pointer.decode
	def pointer(self, value) -> Optional[dict]:
		if value is True:
			value = {}
		if value is None or value is False:
			return None
		spec = self._decodeMapping('pointer', value, {'type', 'color', 'size', 'side', 'glow'})
		if spec is not None:
			self._checkMarkerType(spec)
		return spec

	@pointer.encode
	def pointer(self, value):
		return copy.deepcopy(value) if value else None

	@StateProperty(key='font', default=None, allowNone=True, after=Meter.rebuild)
	def font(self) -> Optional[str]:
		"""The text's font family, or a theme font token such as ``$mono``."""
		return self._fontSpec

	@font.setter
	def font(self, value: Optional[str]):
		self._fontSpec = value

	def _decodeMapping(self, name: str, value, known: set) -> Optional[dict]:
		if value is None:
			return None
		if not isinstance(value, Mapping):
			log.warning(f'Bar {gaugeKeyName(self)} ignored {name} {value!r}: expected a mapping')
			return None
		unknown = set(value) - known
		if unknown:
			log.warning(f'Bar {gaugeKeyName(self)} {name} ignored unknown keys {sorted(map(str, unknown))}')
		return dict(value)

	@staticmethod
	def _checkMarkerType(spec: Mapping) -> None:
		kind = str(spec.get('type', 'line')).strip().lower()
		if kind not in _MARKER_TYPES:
			raise ValueError(f'type must be one of {", ".join(_MARKER_TYPES)}, not {kind!r}')

	# -- state: labels and captions (plain mappings; drawn by the canvas) ---------------------------------

	@StateProperty(key='value-label', default=None, allowNone=True, repr=True)
	def valueLabel(self) -> Optional[dict]:
		"""The value as text: ``{visible, position, align, size, color, format}``. ``position`` is
		``end`` (default; the top of a standing bar), ``start``, ``above``, ``below``, ``left``,
		``right`` or ``inside`` (on the track; in a thermometer, in the bulb). ``size`` is the text height
		as a share of the cross extent; ``format`` is the unit's format mapping, as a gauge's value label takes."""
		return self._valueSpec

	@valueLabel.setter
	def valueLabel(self, value: Optional[dict]):
		self._valueSpec = value

	@valueLabel.decode
	def valueLabel(self, value) -> Optional[dict]:
		return self._decodeMapping('value-label', value, {'visible', 'position', 'align', 'size', 'color', 'format'})

	@valueLabel.encode
	def valueLabel(self, value):
		return copy.deepcopy(value) if value else None

	@StateProperty(key='unit-label', default=None, allowNone=True)
	def unitLabel(self) -> Optional[dict]:
		"""The unit's word (``mph``) beside the value, smaller and fainter: ``{visible, text, size, color}``.
		Off unless ``visible: true``; the value label's own ``format`` decides whether the *symbol* (% or °) shows."""
		return self._unitSpec

	@unitLabel.setter
	def unitLabel(self, value: Optional[dict]):
		self._unitSpec = value

	@unitLabel.decode
	def unitLabel(self, value) -> Optional[dict]:
		return self._decodeMapping('unit-label', value, {'visible', 'text', 'size', 'color'})

	@unitLabel.encode
	def unitLabel(self, value):
		return copy.deepcopy(value) if value else None

	@StateProperty(key='caption', default=None, allowNone=True)
	def caption(self) -> Optional[dict | str]:
		"""Small text above the bar, at its start: a string, or ``{text, value, format, size, color}``."""
		return self._captionSpec

	@caption.setter
	def caption(self, value):
		self._captionSpec = value

	@caption.decode
	def caption(self, value):
		return self._decodeCaption(value)

	@caption.encode
	def caption(self, value):
		return copy.deepcopy(value) if value else None

	@StateProperty(key='sub-label', default=None, allowNone=True)
	def subLabel(self) -> Optional[dict | str]:
		"""Small text below the bar, at its start: same forms as ``caption``."""
		return self._subSpec

	@subLabel.setter
	def subLabel(self, value):
		self._subSpec = value

	@subLabel.decode
	def subLabel(self, value):
		return self._decodeCaption(value)

	@subLabel.encode
	def subLabel(self, value):
		return copy.deepcopy(value) if value else None

	# -- state: graduations ------------------------------------------------------------------------------

	_TICK_KEYS = {'interval', 'count', 'length', 'width', 'side', 'color', 'labels', 'format', 'size', 'every', 'enabled'}

	@StateProperty(key='major', default=None, allowNone=True)
	def majorDivisions(self) -> Optional[dict]:
		"""Major ticks: ``{interval, count, length, width, side, color, labels, format, size}``.
		``interval`` is in the data's unit (default: a round step that gives about five); ``count`` splits
		the range instead. ``side`` is ``before`` (above a lying bar, left of a standing one), ``after`` or ``both``.
		``labels: true`` numbers them. There are no ticks unless this is set."""
		return self._majorSpec

	@majorDivisions.setter
	def majorDivisions(self, value: Optional[dict]):
		self._majorSpec = value

	@majorDivisions.decode
	def majorDivisions(self, value) -> Optional[dict]:
		return self._decodeTicks('major', value)

	@majorDivisions.encode
	def majorDivisions(self, value):
		return copy.deepcopy(value) if value else None

	@StateProperty(key='minor', default=None, allowNone=True)
	def minorDivisions(self) -> Optional[dict]:
		"""Minor ticks, between the major ones: ``{count, length, width, side, color}`` (``count`` is the number
		of steps each major step is cut into; default 5)."""
		return self._minorSpec

	@minorDivisions.setter
	def minorDivisions(self, value: Optional[dict]):
		self._minorSpec = value

	@minorDivisions.decode
	def minorDivisions(self, value) -> Optional[dict]:
		return self._decodeTicks('minor', value)

	@minorDivisions.encode
	def minorDivisions(self, value):
		return copy.deepcopy(value) if value else None

	def _decodeTicks(self, name: str, value) -> Optional[dict]:
		if value is True:
			value = {}
		if value is None or value is False:
			return None
		spec = self._decodeMapping(name, value, self._TICK_KEYS)
		if spec is not None and (side := spec.get('side')) is not None and str(side).lower() not in _SIDES:
			raise ValueError(f'side must be one of {", ".join(_SIDES)}, not {side!r}')
		return spec

	# -- state: zones, fill, markers (value-driven parts) -----------------------------------------------------

	@StateProperty(key='zones', default=None, allowNone=True, dependencies={'range'})
	def zones(self) -> Optional[list]:
		"""Coloured bands on the track: a list of ``{from, to, color, weight, opacity}``. A missing end is the range's end.
		``opacity: 0`` draws nothing but still colours a ``fill: {color: zone}``."""
		return self._zoneSpecs or None

	@zones.setter
	def zones(self, value: Optional[list]):
		zones, kept = [], []
		for spec in value or []:
			try:
				if not isinstance(spec, Mapping):
					raise TypeError('expected a mapping with from, to and color')
				unknown = set(spec) - {'from', 'to', 'color', 'weight', 'opacity', 'glow'}
				if unknown:
					log.warning(f'Bar {gaugeKeyName(self)} zone ignored unknown keys {sorted(map(str, unknown))}')
				if spec.get('color') is None:
					raise ValueError('a zone needs a color')
				zones.append({
					'from': None if spec.get('from') is None else _number(spec['from'], 'from'),
					'to': None if spec.get('to') is None else _number(spec['to'], 'to'),
					'color': spec['color'],
					'weight': None if spec.get('weight') is None else _size(spec['weight'], 'weight'),
					'opacity': self._opacity(spec.get('opacity')),
					'glow': Glow.decode(spec.get('glow')),
				})
				kept.append(copy.deepcopy(dict(spec)))
			except Exception as e:  # noqa: BLE001 - one bad zone is a warning, never a failed load
				log.warning(f'Bar {gaugeKeyName(self)} skipped zone {spec!r}: {e}')
		self._zones, self._zoneSpecs = zones, kept
		self._redraw()

	@staticmethod
	def _opacity(raw) -> float:
		if raw is None:
			return 1.0
		if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not 0 <= raw <= 1:
			raise ValueError(f'opacity must be a number from 0 to 1, not {raw!r}')
		return float(raw)

	@zones.decode
	def zones(self, value) -> list:
		if isinstance(value, Mapping):
			value = [value]
		if not isinstance(value, (list, tuple)):
			log.warning(f'Bar {gaugeKeyName(self)} ignored zones {value!r}: expected a list')
			return []
		return [dict(spec) for spec in value if isinstance(spec, Mapping)]

	@zones.encode
	def zones(self, value):
		return copy.deepcopy(value) if value else None

	@StateProperty(key='fill', default=None, allowNone=True, dependencies={'range', 'zones'})
	def fill(self) -> Optional[dict]:
		"""The part of the track up to a value: ``{from, to, color, gradient, weight, cap, segments, gap, opacity,
		glow}``. ``from`` and ``to`` are numbers, keys or expressions (default: the range minimum, and the
		bar's own value). ``color: zone`` takes the colour of the zone the end sits in."""
		return self._fillSpec

	@fill.setter
	def fill(self, value: Optional[dict]):
		self._clearFill()
		if not value:
			self._redraw()
			return
		try:
			self._fill = self._configureFill(value)
		except Exception as e:  # noqa: BLE001 - a bad fill is a warning, never a failed load
			log.warning(f'Bar {gaugeKeyName(self)} fill skipped: {e}')
			self._redraw()
			return
		self._fillSpec = copy.deepcopy(dict(value))
		self._redraw()

	@fill.decode
	def fill(self, value) -> Optional[dict]:
		if value is None:
			return None
		if value is True:
			return {}
		if not isinstance(value, Mapping):
			log.warning(f'Bar {gaugeKeyName(self)} ignored fill {value!r}: expected a mapping')
			return None
		return dict(value)

	@fill.encode
	def fill(self, value):
		return copy.deepcopy(value) if value else None

	def _configureFill(self, spec: Mapping) -> dict:
		name = gaugeKeyName(self)
		known = {'from', 'to', 'color', 'gradient', 'weight', 'cap', 'segments', 'gap', 'opacity', 'glow'}
		if unknown := set(spec) - known:
			log.warning(f'Bar {name} fill ignored unknown keys {sorted(map(str, unknown))}')
		fill = {'from': None, 'to': None, 'color': None, 'zone': False, 'gradient': None, 'weight': None, 'cap': None,
				'segments': 0, 'gap': None, 'opacity': 1.0, 'glow': Glow.decode(spec.get('glow'))}
		for end in ('from', 'to'):
			raw = spec.get(end)
			if raw is None:
				continue
			if isinstance(raw, str):
				self._pending.add(('fill', end))
				if (source := openValueSource(raw, f'Bar {name} fill {end}', 'the fill stays hidden')) is None:
					raise ValueError(f'{end} {raw!r} is not usable')
				self._bindings.append(('fill', Binding(source, _SourceEnd(lambda v, e=end: self._setFillEnd(e, v)).setMarkerValue)))
			else:
				fill[end] = _number(raw, end)
		if (weight := spec.get('weight')) is not None:
			fill['weight'] = _size(weight, 'weight')
		if (cap := spec.get('cap')) is not None:
			if str(cap).strip().lower() not in _CAPS:
				raise ValueError(f'cap must be one of {", ".join(_CAPS)}, not {cap!r}')
			fill['cap'] = str(cap).strip().lower()
		if (opacity := spec.get('opacity')) is not None:
			if isinstance(opacity, bool) or not isinstance(opacity, (int, float)) or not 0 <= opacity <= 1:
				raise ValueError(f'opacity must be a number from 0 to 1, not {opacity!r}')
			fill['opacity'] = float(opacity)
		if isinstance(spec.get('color'), str) and spec['color'].strip().lower() == 'zone':
			fill['zone'] = True
		elif spec.get('color') is not None:
			fill['color'] = spec['color']
		if spec.get('gradient') is not None:
			fill['gradient'] = Gradient.decode(spec['gradient'])
		if (segments := spec.get('segments')) is not None:
			if isinstance(segments, bool) or not isinstance(segments, int) or segments < 1:
				raise TypeError(f'segments must be a whole number of 1 or more, not {segments!r}')
			fill['segments'] = segments
		if (gap := spec.get('gap')) is not None:
			fill['gap'] = _size(gap, 'gap')
		return fill

	def _setFillEnd(self, end: str, value) -> None:
		try:
			value = float(value)
		except (TypeError, ValueError):
			return
		if not isfinite(value) or self._fill is None:
			return
		self._fill[end] = value
		self._pending.discard(('fill', end))
		self._redraw()

	def _clearFill(self):
		self._fill, self._fillSpec = None, None
		self._unlink('fill')

	def _unlink(self, owner: str):
		"""Release the value sources a part (``fill`` or ``markers``) holds."""
		dropped = [binding for name, binding in self._bindings if name == owner]
		self._bindings = [(name, binding) for name, binding in self._bindings if name != owner]
		self._pending = {p for p in self._pending if p[0] != owner}
		for binding in dropped:
			binding.unlink()

	@StateProperty(key='markers', default=None, allowNone=True, dependencies={'range'})
	def markers(self) -> Optional[list]:
		"""Extra indicators, each at its own value: ``{value, type, color, size, side}`` with ``type`` one of
		``line`` (across the track), ``triangle``, ``dot`` or ``notch``. ``value`` is a number, a key or an
		expression such as ``at(key, -3h)``; with no value yet the marker is hidden."""
		return self._markerSpecs or None

	@markers.setter
	def markers(self, value: Optional[list]):
		self._clearMarkers()
		markers, kept = [], []
		for spec in value or []:
			try:
				if not isinstance(spec, Mapping):
					raise TypeError('expected a mapping with a value')
				marker = self._configureMarker(spec)
			except Exception as e:  # noqa: BLE001 - one bad marker is skipped, never a failed load
				log.warning(f'Bar {gaugeKeyName(self)} skipped marker {spec!r}: {e}')
				continue
			markers.append(marker)
			kept.append(copy.deepcopy(dict(spec)))
		self._markers, self._markerSpecs = markers, kept
		self._redraw()

	@markers.decode
	def markers(self, value) -> list:
		if isinstance(value, Mapping):
			value = [value]
		if not isinstance(value, (list, tuple)):
			log.warning(f'Bar {gaugeKeyName(self)} ignored markers {value!r}: expected a list')
			return []
		return [dict(spec) for spec in value if isinstance(spec, Mapping)]

	@markers.encode
	def markers(self, value):
		return copy.deepcopy(value) if value else None

	def _configureMarker(self, spec: Mapping) -> dict:
		if unknown := set(spec) - {'value', 'type', 'color', 'size', 'side', 'glow'}:
			log.warning(f'Bar {gaugeKeyName(self)} marker ignored unknown keys {sorted(map(str, unknown))}')
		self._checkMarkerType(spec)
		marker = {'type': str(spec.get('type', 'line')).strip().lower(), 'color': spec.get('color'), 'value': None,
				'size': None if spec.get('size') is None else _size(spec['size'], 'size'),
				'side': _SIDES.get(str(spec.get('side', 'before')).lower(), 'before'), 'glow': Glow.decode(spec.get('glow'))}
		raw = spec.get('value')
		if isinstance(raw, bool):
			raise TypeError(f'a marker value must be a number, a key or an expression, not {raw!r}')
		if isinstance(raw, (int, float)):
			marker['value'] = float(raw)
		elif isinstance(raw, str):
			source = openValueSource(raw, f'Bar {gaugeKeyName(self)} marker value', 'the marker stays hidden')
			if source is None:
				raise ValueError(f'value {raw!r} is not usable')
			self._bindings.append(('markers', Binding(source, _SourceEnd(lambda v, m=marker: self._setMarkerValue(m, v)).setMarkerValue)))
		else:
			raise TypeError(f'a marker value must be a number, a key or an expression, not {raw!r}')
		return marker

	def _setMarkerValue(self, marker: dict, value) -> None:
		try:
			value = float(value)
		except (TypeError, ValueError):
			return
		if isfinite(value):
			marker['value'] = value
			self._redraw()

	def _clearMarkers(self):
		self._markers, self._markerSpecs = [], []
		self._unlink('markers')

	# -- drawing ---------------------------------------------------------------------------------------

	def _valueFont(self, px: float) -> QFont:
		font = QFont(defaultFont)
		if self._fontSpec:
			try:
				from LevityDash.lib.ui.colors import theme
				family = theme.font(str(self._fontSpec).lstrip('$')) if str(self._fontSpec).startswith('$') else str(self._fontSpec)
				font.setFamily(family)
			except Exception as e:  # noqa: BLE001
				log.debug(f'Bar {gaugeKeyName(self)} font {self._fontSpec!r} not found: {e}')
		font.setPixelSize(max(int(round(px)), 1))
		return font

	def _toData(self, value):
		"""``value`` in the data's own class, as a gauge converts a marker's value before placing it."""
		try:
			return self.valueClass(value)
		except Exception:  # noqa: BLE001
			return float(value)

	def _t(self, value) -> float:
		return self.value_scale.toT(float(self._toData(value)))

	def _text(self, value, spec) -> str:
		"""``value`` formatted the way a value label formats it: the unit's own format, merged over
		``show_unit: false`` (the word stays out; the symbol, % or °, comes with the unit)."""
		fmt = {'show_unit': False}
		if isinstance(spec, Mapping):
			fmt.update(spec)
		elif isinstance(spec, str):
			fmt = spec
		if value is None:
			return '⋯'
		data = value if hasattr(value, '__format__') and not isinstance(value, (int, float)) else self._toData(value)
		try:
			if isinstance(fmt, str):
				return data.__format__(fmt)
			return data.__format__('', **fmt)
		except Exception:  # noqa: BLE001 - a bad format must not blank the bar
			return f'{float(value):g}'

	def _unitText(self) -> str:
		spec = self._unitSpec or {}
		if spec.get('text') is not None:
			return str(spec['text'])
		unit = getattr(self._value, 'unit', None)
		return str(unit) if unit else ''

	def _caption(self, spec) -> tuple[str, Optional[QColor], float]:
		"""A caption spec as (text, colour, size share)."""
		if spec is None:
			return '', None, 0.0
		if isinstance(spec, str):
			return spec, None, 0.0
		text = spec.get('text')
		if text is None and spec.get('value') is not None:
			text = self._text(self._toData(self._valueOf(spec['value'])), spec.get('format'))
		color = _color(spec['color']) if spec.get('color') is not None else None
		return str(text or ''), color, float(spec['size'] if isinstance(spec.get('size'), (int, float)) else 0.0)

	def _valueOf(self, raw):
		return self._value if raw in ('value', True) else raw

	def _layout(self, painter: QPainter) -> Optional[dict]:
		"""Every length the paint needs, from the box, the specs and the current value."""
		rect = QRectF(self.rect())
		if rect.width() < 2 or rect.height() < 2:
			return None
		vertical = self.vertical or self._style == 'thermometer'
		pad = min(rect.width(), rect.height()) * 0.03
		rect.adjust(pad, pad, -pad, -pad)
		across = rect.width() if vertical else rect.height()
		along = rect.height() if vertical else rect.width()
		u = across
		track = self._trackSpec or {}
		style = self._style

		# Nominal sizes, as shares of the cross extent; shrunk together below when they do not fit.
		weight = self._px(track.get('weight'), u, {'bar': 0.28, 'battery': 0.5, 'thermometer': 0.24}[style])
		valueSpec = self._valueSpec if self._valueSpec is not None else {}
		showValue = valueSpec.get('visible', True) is not False and self._valueSpec != {'visible': False}
		position = str(valueSpec.get('position', 'inside' if style == 'thermometer' else 'end')).strip().lower()
		position = self._physicalSide(position, vertical)
		valueSize = self._px(valueSpec.get('size'), u, 0.42 if position in ('left', 'right') else 0.34)
		captionText, captionColor, captionSize = self._caption(self._captionSpec)
		subText, subColor, subSize = self._caption(self._subSpec)
		capPx = (captionSize and captionSize * u) or u * 0.2
		subPx = (subSize and subSize * u) or u * 0.2

		major = self._majorSpec
		minor = self._minorSpec
		tickSides = {'before': 0.0, 'after': 0.0}
		tickLabelPx = 0.0
		tickLen = 0.0
		if major is not None:
			tickLen = self._px(major.get('length'), u, 0.1)
			labels = major.get('labels', False)
			if labels:
				tickLabelPx = self._px(major.get('size'), u, 0.14)
			side = _SIDES.get(str(major.get('side', 'after')).lower(), 'after')
			for s in (('before', 'after') if side == 'both' else (side,)):
				tickSides[s] = tickLen + (tickLabelPx * (2.6 if vertical else 1.2) + u * 0.04 if labels else 0)
		if minor is not None:
			minLen = self._px(minor.get('length'), u, 0.06)
			side = _SIDES.get(str(minor.get('side', (major or {}).get('side', 'after'))).lower(), 'after')
			for s in (('before', 'after') if side == 'both' else (side,)):
				tickSides[s] = max(tickSides[s], minLen)

		# What stands off the track. Across it: ticks, and (on a lying bar) the caption and the value above or
		# below. Along it, on a standing bar: the caption, the sub-label and a value at either end.
		need = {'before': 0.0, 'after': 0.0}
		strip = {'before': 0.0, 'after': 0.0}
		target = strip if vertical else need
		if captionText:
			target['before'] += capPx * 1.25
		if subText:
			target['after'] += subPx * 1.25
		if showValue and position in ('top', 'bottom'):
			target['before' if position == 'top' else 'after'] += valueSize * 1.15
		need['before'] += tickSides['before']
		need['after'] += tickSides['after']
		bulb = weight * 1.0 if style == 'thermometer' else 0.0
		total = need['before'] + need['after'] + weight
		if style == 'thermometer':
			total = max(total, bulb * 2)  # the bulb is the widest part
		# Scale to fit: everything shrinks together, so the proportions hold.
		k = min(1.0, u / total) if total > 0 else 1.0
		if k < 1.0:
			weight *= k
			valueSize *= k
			capPx *= k
			subPx *= k
			tickLen *= k
			tickLabelPx *= k
			tickSides = {s: v * k for s, v in tickSides.items()}
			need = {s: v * k for s, v in need.items()}
			bulb *= k
			strip = {side: v * k for side, v in strip.items()}

		valueFont = self._valueFont(valueSize)
		fm = QFontMetricsF(valueFont)
		current = self._text(self._value, valueSpec.get('format'))
		widest = max(
			fm.horizontalAdvance(current),
			fm.horizontalAdvance(self._text(self._range.rounded_max, valueSpec.get('format'))),
		) if showValue else 0.0
		unitText = self._unitText() if (self._unitSpec or {}).get('visible') else ''
		unitFont = self._valueFont(valueSize * float((self._unitSpec or {}).get('size', 0.5) if isinstance((self._unitSpec or {}).get('size'), (int, float)) else 0.5))
		unitWidth = QFontMetricsF(unitFont).horizontalAdvance(f' {unitText}') if unitText else 0.0
		valueWidth = widest + unitWidth
		gap = u * 0.2

		# Along stack: a value at either end takes a strip.
		left = right = top = bottom = 0.0
		if showValue and position == 'left':
			left = valueWidth + gap
		elif showValue and position == 'right':
			right = valueWidth + gap
		if vertical and showValue and position in ('left', 'right'):
			pass
		avail = rect.adjusted(left, 0, -right, 0)
		if showValue and position in ('left', 'right') and valueWidth + gap > along * 0.45 and not vertical:
			shrink = along * 0.45 / (valueWidth + gap)
			valueFont = self._valueFont(valueSize * shrink)
			valueWidth *= shrink
			left, right = (left * shrink, right * shrink)
			avail = rect.adjusted(left, 0, -right, 0)

		# The track's cross position: the middle of what the stacks left over.
		crossLo = (rect.left() if vertical else rect.top()) + need['before']
		crossHi = (rect.right() if vertical else rect.bottom()) - need['after']
		crossMid = (crossLo + crossHi) / 2
		capStyle = _CAPS[str(track.get('cap', 'round')).lower()]
		capInset = weight / 2 if capStyle != Qt.PenCapStyle.FlatCap else 0.0
		if style == 'battery':
			capInset = weight * 0.16 + max(u * 0.045, 1.5)
		bulbCenter = None
		if vertical:
			a0, a1 = rect.bottom() - strip['after'] - capInset, rect.top() + strip['before'] + capInset
			if style == 'thermometer':
				# The scale starts where the tube meets the bulb, as on a real one.
				bulbCenter = QPointF(crossMid, rect.bottom() - strip['after'] - bulb)
				a0 = bulbCenter.y() - bulb * 0.75
			line = LineTrack(QPointF(crossMid, a0), QPointF(crossMid, a1))
		else:
			x0, x1 = avail.left() + capInset, avail.right() - capInset
			if style == 'battery':
				x1 -= weight * 0.22 + max(u * 0.045, 1.5)  # room for the terminal
			line = LineTrack(QPointF(x0, crossMid), QPointF(x1, crossMid))
		return {
			'rect': rect, 'vertical': vertical, 'u': u, 'line': line, 'weight': weight, 'cap': capStyle, 'bulb': bulb,
			'bulbCenter': bulbCenter,
			'valueFont': valueFont, 'unitFont': unitFont, 'showValue': showValue, 'position': position,
			'valueText': current, 'unitText': unitText, 'valueSize': valueSize, 'gap': gap,
			'captionText': captionText, 'captionColor': captionColor, 'capPx': capPx,
			'subText': subText, 'subColor': subColor, 'subPx': subPx,
			'tickSides': tickSides, 'tickLabelPx': tickLabelPx, 'avail': avail, 'need': need, 'strip': strip,
		}

	def _px(self, raw, ref: float, default: float) -> float:
		"""A size spec in px; a missing one is ``default`` of ``ref``."""
		if raw is None:
			return default * ref
		value = parseWidth(raw, None)
		if value is None:
			return default * ref
		return size_px(value, ref, dimension=DimensionType.width)

	@staticmethod
	def _physicalSide(position: str, vertical: bool) -> str:
		"""A value label's position as the side of the box it sits on: left, right, top, bottom or inside."""
		if position == 'inside':
			return 'inside'
		if vertical:
			return {'end': 'top', 'start': 'bottom', 'above': 'top', 'below': 'bottom'}.get(position, position)
		return {'end': 'right', 'start': 'left', 'above': 'top', 'below': 'bottom'}.get(position, position)

	def _point(self, line: LineTrack, t: float, cross: float = 0.0) -> QPointF:
		"""The point at ``t`` along the track and ``cross`` px to its *after* side."""
		p = line.pointAt(t)
		n = line.normalAt(t)
		return QPointF(p.x() + n.x() * cross, p.y() + n.y() * cross)

	def _resolveGradient(self, gradient: Gradient) -> Optional[Gradient]:
		"""``gradient`` with its stops in the data's unit, or None when none of them fits."""
		if gradient.hasUnits:
			resolved = gradient.resolve(self.valueClass)
			return resolved if len(resolved) else None
		if not issubclass(gradient.itemCls.__item__, self.valueClass):
			return gradient.as_type(self.valueClass, self._range.rounded_min, self._range.rounded_max)
		return gradient

	def _gradientColorAt(self, gradient: Gradient, t: float) -> QColor:
		return gradient.get_color_for_value(self.valueClass(self.value_scale.fromT(t))).QColor

	def _gradientBrush(self, line: LineTrack, gradient: Gradient) -> Optional[QBrush]:
		"""A brush for ``gradient`` laid along the whole track, value by value."""
		try:
			if (gradient := self._resolveGradient(gradient)) is None:
				return None
			brush = QLinearGradient(line.pointAt(0), line.pointAt(1))
			for i in range(33):
				brush.setColorAt(i / 32, self._gradientColorAt(gradient, i / 32))
			return QBrush(brush)
		except Exception as e:  # noqa: BLE001 - paint the plain colour rather than nothing
			log.warning(f'Bar {gaugeKeyName(self)} gradient not applied: {e!r}')
			return None

	def _underColor(self, t: float) -> QColor:
		"""The colour the track shows at position ``t``: the fill where it reaches, the track elsewhere."""
		track = self._trackSpec or {}
		color = _color(track['color']) if track.get('color') is not None else _color('$rule')
		fill = self._fill
		if fill is None or self._pending:
			return color
		start = fill['from'] if fill['from'] is not None else float(self._range.rounded_min)
		end = fill['to'] if fill['to'] is not None else self._value
		ta, tb = sorted((self._t(start), self._t(end)))
		if not ta - 1e-9 <= t <= tb + 1e-9:
			return color
		if fill['gradient'] is not None and (gradient := self._resolveGradient(fill['gradient'])) is not None:
			return self._gradientColorAt(gradient, t)
		if fill['zone']:
			return self._zoneColorAt(t) or _color('$accent')
		return _color(fill['color']) if fill['color'] is not None else _color('$accent')

	def _zoneColorAt(self, t: float) -> Optional[QColor]:
		"""The colour of the zone holding the position ``t``; the later zone wins on a shared cutoff.

		Compared as positions, not values: a zone's numbers are in the unit the author thinks in (65 for 65 %),
		which the data's own class may hold as a fraction.
		"""
		found = None
		for zone in self._zones:
			a = 0.0 if zone['from'] is None else self._t(zone['from'])
			b = 1.0 if zone['to'] is None else self._t(zone['to'])
			if min(a, b) - 1e-9 <= t <= max(a, b) + 1e-9:
				found = zone['color']
		return None if found is None else _color(found)

	def _stroke(self, painter: QPainter, path: QPainterPath, brush, width: float, cap: Qt.PenCapStyle, glow: Optional[Glow] = None):
		if path.isEmpty() or width <= 0:
			return
		paintGlow(painter, path, brush if isinstance(brush, QBrush) else QBrush(brush), width, glow, filled=True)
		pen = QPen(brush if isinstance(brush, QBrush) else QBrush(brush), width)
		pen.setCapStyle(cap)
		painter.setBrush(Qt.BrushStyle.NoBrush)
		painter.setPen(pen)
		painter.drawPath(path)

	def _segmentEdges(self, count: int, gapPx: float, length: float) -> list:
		"""The (t0, t1) of each of ``count`` cells along a track ``length`` px long, ``gapPx`` apart."""
		step = 1.0 / count
		half = min(max(gapPx, 0.0), length * step * 0.8) / length / 2 if length else 0.0
		return [(i * step + half, (i + 1) * step - half) for i in range(count)]

	def paintBar(self, painter: QPainter):
		layout = self._layout(painter)
		if layout is None:
			return
		line: LineTrack = layout['line']
		w = layout['weight']
		track = self._trackSpec or {}
		fill = self._fill
		style = self._style
		segments = (fill or {}).get('segments', 0) if track.get('segments') is not False else 0
		if isinstance(track.get('segments'), int) and not isinstance(track.get('segments'), bool):
			segments = track['segments']
		gap = self._px((track.get('gap') if track.get('gap') is not None else (fill or {}).get('gap')), layout['u'], 0.06) if segments else 0.0
		trackColor = _color(track['color']) if track.get('color') is not None else _color('$rule')
		cap = layout['cap']
		painter.save()
		try:
			self._paintBody(painter, layout, trackColor, segments, gap)
			self._paintZones(painter, layout)
			self._paintFill(painter, layout, segments, gap)
			self._paintTicks(painter, layout)
			self._paintMarkers(painter, layout)
			self._paintText(painter, layout)
		finally:
			painter.restore()

	def _paintBody(self, painter: QPainter, layout: dict, color: QColor, segments: int, gap: float):
		line: LineTrack = layout['line']
		w, cap, style = layout['weight'], layout['cap'], self._style
		length = line.lengthPx
		if style == 'thermometer':
			tube = QPainterPath()
			r = w / 2
			base = layout['bulbCenter']
			tube.addRoundedRect(QRectF(base.x() - r, line.pointAt(1).y() - r, w, base.y() - line.pointAt(1).y() + r), r, r)
			bulb = QPainterPath()
			bulb.addEllipse(base, layout['bulb'], layout['bulb'])
			shape = tube.united(bulb)
			painter.setPen(Qt.PenStyle.NoPen)
			painter.setBrush(color)
			painter.drawPath(shape)
			return
		if style == 'battery':
			shell = QPen(_color('$muted'), max(layout['u'] * 0.045, 1.5))
			shell.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
			a, b = line.pointAt(0), line.pointAt(1)
			pad = w * 0.16
			body = QRectF(a.x() - pad, a.y() - w / 2 - pad, (b.x() - a.x()) + pad * 2, w + pad * 2)
			painter.setPen(shell)
			painter.setBrush(Qt.BrushStyle.NoBrush)
			painter.drawRoundedRect(body, w * 0.24, w * 0.24)
			terminal = QRectF(body.right() + shell.widthF(), body.center().y() - w * 0.2, w * 0.22, w * 0.4)
			painter.setPen(Qt.PenStyle.NoPen)
			painter.setBrush(shell.color())
			painter.drawRoundedRect(terminal, w * 0.08, w * 0.08)
			# The dim track inside the cell, so an empty battery still reads as one.
		if segments:
			for t0, t1 in self._segmentEdges(segments, gap, length):
				self._stroke(painter, line.subPath(t0, t1), color, w, Qt.PenCapStyle.FlatCap)
		else:
			self._stroke(painter, line.subPath(0, 1), color, w, cap if style == 'bar' else Qt.PenCapStyle.FlatCap)

	def _paintZones(self, painter: QPainter, layout: dict):
		line: LineTrack = layout['line']
		for zone in self._zones:
			t0, t1 = sorted((0.0 if zone['from'] is None else self._t(zone['from']), 1.0 if zone['to'] is None else self._t(zone['to'])))
			if t1 - t0 < 1e-9:
				continue
			weight = layout['weight'] if zone['weight'] is None else size_px(zone['weight'], layout['u'], dimension=DimensionType.width)
			if zone['opacity'] <= 0:
				continue
			color = _color(zone['color'])
			color.setAlphaF(color.alphaF() * zone['opacity'])
			self._stroke(painter, line.subPath(t0, t1), color, weight, Qt.PenCapStyle.FlatCap, resolveGlow(zone['glow'], self.glow))

	def _paintFill(self, painter: QPainter, layout: dict, segments: int, gap: float):
		fill = self._fill
		if fill is None or self._pending:
			return
		line: LineTrack = layout['line']
		start = fill['from'] if fill['from'] is not None else float(self._range.rounded_min)
		end = fill['to'] if fill['to'] is not None else self._value
		if start is None or end is None:
			return
		ta, tb = sorted((self._t(start), self._t(end)))
		if tb - ta < 1e-9:
			return
		style = self._style
		w = layout['weight'] if fill['weight'] is None else size_px(fill['weight'], layout['u'], dimension=DimensionType.width)
		if style == 'battery':
			w = w * 0.84
		if style == 'thermometer':
			w = layout['weight'] * 0.62
		base = _color(fill['color']) if fill['color'] is not None else _color('$accent')
		brush = None
		if fill['gradient'] is not None:
			brush = self._gradientBrush(line, fill['gradient'])
		length = line.lengthPx or 1.0
		defaultCap = Qt.PenCapStyle.FlatCap if (segments or style != 'bar') else Qt.PenCapStyle.RoundCap
		cap = _CAPS[fill['cap']] if fill['cap'] else defaultCap
		# A round or square cap reaches half the weight past its stroke: pull each end in so the cap's edge
		# lands on the value, and so the fill starts where the track's own cap starts.
		capT = 0.0 if cap == Qt.PenCapStyle.FlatCap else (w / 2) / length
		trackCapped = layout['cap'] != Qt.PenCapStyle.FlatCap and style == 'bar'
		glow = resolveGlow(fill['glow'], self.glow)
		opacity = fill['opacity']
		painter.save()
		painter.setOpacity(painter.opacity() * opacity)

		def colorAt(t: float) -> QColor:
			if fill['zone']:
				return self._zoneColorAt(t) or base
			return base

		def span(t0: float, t1: float) -> QPainterPath:
			t0 += 0.0 if trackCapped and t0 <= 1e-9 else capT
			t1 -= 0.0 if trackCapped and t1 >= 1 - 1e-9 else capT
			if t1 <= t0:
				mid = (t0 + t1) / 2
				t0, t1 = mid, mid + 1e-4
			return line.subPath(t0, t1)

		def thermoSpan(t1: float) -> QPainterPath:
			# From the bulb's centre, so tube and bulb take the one colour.
			path = QPainterPath(layout['bulbCenter'])
			path.lineTo(line.pointAt(t1))
			return path

		if segments:
			for t0, t1 in self._segmentEdges(segments, gap, length):
				mid = (t0 + t1) / 2
				if not (ta <= mid <= tb):
					continue
				self._stroke(painter, line.subPath(t0, t1), brush or colorAt(mid), w, Qt.PenCapStyle.FlatCap, glow)
		else:
			color = brush or colorAt(tb)
			if style == 'thermometer' and ta <= 1e-9:
				self._stroke(painter, thermoSpan(tb), color, w, Qt.PenCapStyle.FlatCap, glow)
				painter.setPen(Qt.PenStyle.NoPen)
				painter.setBrush(brush or colorAt(0.0))
				bulb = layout['bulb'] * 0.78
				painter.drawEllipse(layout['bulbCenter'], bulb, bulb)
			else:
				self._stroke(painter, span(ta, tb), color, w, cap, glow)
		painter.restore()

	def _displayFactor(self) -> float:
		"""How many display units one unit of the data's float is: 100 for a percentage held as a fraction."""
		try:
			held = float(self._toData(100))
			return 100.0 / held if held else 1.0
		except Exception:  # noqa: BLE001
			return 1.0

	def _tickValues(self, spec: Mapping, rounded_min: float, rounded_max: float) -> list:
		span = rounded_max - rounded_min
		if span <= 0:
			return []
		if spec.get('count') is not None:
			count = max(int(spec['count']), 1)
			interval = span / count
		elif spec.get('interval') is not None:
			interval = float(spec['interval'])
		else:
			interval = _niceStep(span)
		if interval <= 0:
			return []
		count = int(round(span / interval))
		return [rounded_min + interval * i for i in range(count + 1) if rounded_min + interval * i <= rounded_max + 1e-9]

	def _paintTicks(self, painter: QPainter, layout: dict):
		line: LineTrack = layout['line']
		# Intervals are in the author's units (25 for 25 %), which the data's class may hold as a fraction.
		factor = self._displayFactor()
		lo, hi = float(self._range.rounded_min) * factor, float(self._range.rounded_max) * factor
		u, w = layout['u'], layout['weight']
		vertical = layout['vertical']
		majors = []
		for spec, major in ((self._minorSpec, False), (self._majorSpec, True)):
			if spec is None:
				continue
			sides = _SIDES.get(str(spec.get('side', 'after')).lower(), 'after')
			sides = ('before', 'after') if sides == 'both' else (sides,)
			color = _color(spec['color']) if spec.get('color') is not None else _color('$faint')
			length = self._px(spec.get('length'), u, 0.1 if major else 0.06)
			width = self._px(spec.get('width'), u, 0.025 if major else 0.015)
			width = max(width, 1.0)
			if major:
				values = self._tickValues(spec, lo, hi)
				majors = values
			else:
				mc = max(int(spec.get('count', 5)), 1)
				base = majors or self._tickValues({}, lo, hi)
				values = []
				for a, b in zip(base, base[1:]):
					values.extend(a + (b - a) * i / mc for i in range(1, mc))
			k = layout['need']  # noqa: F841 - kept for symmetry with the layout; ticks are positioned from the track
			pen = QPen(color, width)
			pen.setCapStyle(Qt.PenCapStyle.FlatCap)
			painter.setPen(pen)
			painter.setBrush(Qt.BrushStyle.NoBrush)
			for side in sides:
				sign = -1.0 if side == 'before' else 1.0
				start = sign * (w / 2 + u * 0.03 + (w * 0.0))
				if self._style == 'battery':
					start = sign * (w * 0.5 + w * 0.16 + u * 0.03)
				for v in values:
					t = self._t(v)
					painter.drawLine(self._point(line, t, start), self._point(line, t, start + sign * length))
			if major and spec.get('labels'):
				self._paintTickLabels(painter, layout, spec, values, sides, length, w)

	def _paintTickLabels(self, painter: QPainter, layout: dict, spec: Mapping, values: list, sides: tuple, length: float, w: float):
		line: LineTrack = layout['line']
		u = layout['u']
		px = layout['tickLabelPx'] or u * 0.14
		font = self._valueFont(px)
		fm = QFontMetricsF(font)
		color = _color(spec['color']) if spec.get('color') is not None else _color('$faint')
		fmt = dict(spec.get('format') or {})
		if 'precision' not in fmt and len(values) > 1:
			step = abs(values[1] - values[0])
			fmt['precision'] = 0 if float(step).is_integer() else min(max(int(ceil(-log10(step) - 1e-9)), 0), 3)
		vertical = layout['vertical']
		if spec.get('every') is not None:
			every = max(int(spec['every']), 1)
		elif len(values) > 1:
			# Thin the labels until the widest one fits between its neighbours (a vertical bar is as tall as its text).
			texts = [self._text(self._toData(v), fmt) for v in values]
			reach = (fm.height() if vertical else max(fm.horizontalAdvance(t) for t in texts)) * 1.3
			spacing = line.lengthPx * abs(self._t(values[1]) - self._t(values[0]))
			every = max(int(ceil(reach / spacing)), 1) if spacing > 0 else 1
		else:
			every = 1
		painter.setFont(font)
		painter.setPen(color)
		for side in sides:
			sign = -1.0 if side == 'before' else 1.0
			base = sign * (w / 2 + u * 0.03 + length + u * 0.03)
			if self._style == 'battery':
				base = sign * (w * 0.5 + w * 0.16 + u * 0.03 + length + u * 0.03)
			for i, v in enumerate(values):
				if i % every:
					continue
				text = self._text(self._toData(v), fmt)
				anchor = self._point(line, self._t(v), base)
				# Hung off the tick's far end: a lying bar's labels hang below (or stand above) it, a standing bar's
				# sit to its right (or left).
				if vertical:
					self._drawText(painter, text, fm, anchor, -1 if side == 'after' else 1, 0)
				else:
					self._drawText(painter, text, fm, anchor, 0, -1 if side == 'after' else 1)

	def _paintMarkers(self, painter: QPainter, layout: dict):
		line: LineTrack = layout['line']
		for marker in self._markers:
			if marker['value'] is None:
				continue
			self._drawMarker(painter, layout, marker['type'], self._t(marker['value']), marker['color'], marker['size'], marker['side'], resolveGlow(marker['glow'], self.glow))
		pointer = self._pointerSpec
		if pointer is not None:
			size = None if pointer.get('size') is None else _size(pointer['size'], 'size')
			side = _SIDES.get(str(pointer.get('side', 'before')).lower(), 'before')
			self._drawMarker(painter, layout, str(pointer.get('type', 'triangle')).lower(), self._t(self._value), pointer.get('color'), size, side, resolveGlow(Glow.decode(pointer.get('glow')), self.glow))

	def _drawMarker(self, painter: QPainter, layout: dict, kind: str, t: float, color, size, side: str, glow: Optional[Glow]):
		line: LineTrack = layout['line']
		w, u = layout['weight'], layout['u']
		extent = size_px(size, u, dimension=DimensionType.width) if size is not None else w * 0.9
		fill = _color(color) if color is not None else _color('$text')
		sign = -1.0 if side == 'before' else 1.0
		center = self._point(line, t)
		painter.save()
		painter.setPen(Qt.PenStyle.NoPen)
		painter.setBrush(fill)
		tangent, normal = line.tangentAt(t), line.normalAt(t)

		def at(a: float, c: float) -> QPointF:
			return QPointF(center.x() + tangent.x() * a + normal.x() * c, center.y() + tangent.y() * a + normal.y() * c)

		if kind in ('triangle', 'pointer'):
			tip = sign * (w / 2 + u * 0.02)
			poly = QPolygonF([at(0, tip), at(-extent * 0.5, tip + sign * extent * 0.9), at(extent * 0.5, tip + sign * extent * 0.9)])
			path = QPainterPath()
			path.addPolygon(poly)
			path.closeSubpath()
			paintGlow(painter, path, QBrush(fill), extent * 0.5, glow, filled=True)
			painter.drawPolygon(poly)
		elif kind == 'dot':
			r = extent * 0.5
			ring = QPen(_color('$background'), max(r * 0.25, 1.0))
			path = QPainterPath()
			path.addEllipse(center, r, r)
			paintGlow(painter, path, QBrush(fill), r, glow, filled=True)
			painter.setPen(ring)
			painter.drawEllipse(center, r, r)
		else:
			reach = (w / 2 + u * 0.03) if kind == 'line' else (w * 0.5 * 0.95)
			thickness = max(u * 0.03, 1.5)
			pen = QPen(fill, thickness)
			pen.setCapStyle(Qt.PenCapStyle.FlatCap)
			a, b = (at(0, -reach), at(0, reach)) if kind == 'line' else (at(0, -reach), at(0, reach))
			path = QPainterPath()
			path.moveTo(a)
			path.lineTo(b)
			paintGlow(painter, path, QBrush(fill), thickness, glow)
			painter.setPen(pen)
			painter.drawLine(a, b)
		painter.restore()

	def _drawText(self, painter: QPainter, text: str, fm: QFontMetricsF, anchor: QPointF, hAlign: int, vAlign: int):
		"""Draw ``text`` with ``anchor`` at its left (-1), centre (0) or right (1) and its top (-1), middle (0) or bottom (1)."""
		tight = fm.tightBoundingRect(text)
		width = fm.horizontalAdvance(text)
		x = anchor.x() - (0 if hAlign < 0 else width / 2 if hAlign == 0 else width)
		# Digits and capitals: the cap height reads as the line's height, so centre on that.
		height = fm.capHeight() or tight.height()
		y = anchor.y() + (height if vAlign < 0 else height / 2 if vAlign == 0 else 0)
		painter.drawText(QPointF(x, y), text)

	def _paintText(self, painter: QPainter, layout: dict):
		rect: QRectF = layout['rect']
		line: LineTrack = layout['line']
		w, u = layout['weight'], layout['u']
		vertical = layout['vertical']
		position = layout['position']
		need = layout['need']
		if layout['captionText']:
			font = self._valueFont(layout['capPx'])
			painter.setFont(font)
			painter.setPen(layout['captionColor'] or _color('$faint'))
			fm = QFontMetricsF(font)
			x = rect.center().x() if vertical else layout['avail'].left()
			y = rect.top() + layout['capPx'] * 0.6
			self._drawText(painter, layout['captionText'], fm, QPointF(x, y), 0 if vertical else -1, 0)
		if layout['subText']:
			font = self._valueFont(layout['subPx'])
			painter.setFont(font)
			painter.setPen(layout['subColor'] or _color('$faint'))
			fm = QFontMetricsF(font)
			x = rect.center().x() if vertical else layout['avail'].left()
			y = rect.bottom() - layout['subPx'] * 0.6
			self._drawText(painter, layout['subText'], fm, QPointF(x, y), 0 if vertical else -1, 0)
		if not layout['showValue']:
			return
		spec = self._valueSpec or {}
		font = layout['valueFont']
		fm = QFontMetricsF(font)
		text = layout['valueText']
		a, b = line.pointAt(0), line.pointAt(1)
		mid = line.pointAt(0.5)
		color = _color(spec['color']) if spec.get('color') is not None else _color('$text')
		align = str(spec.get('align', '')).lower()
		gap = layout['gap']
		unit = layout['unitText']
		unitFont = layout['unitFont']
		unitFm = QFontMetricsF(unitFont)
		unitWidth = unitFm.horizontalAdvance(f' {unit}') if unit else 0.0
		total = fm.horizontalAdvance(text) + unitWidth

		def draw(anchor: QPointF, h: int, v: int):
			painter.setFont(font)
			painter.setPen(color)
			# Anchor the whole "value unit" run: the value first, then the unit after it.
			valueW = fm.horizontalAdvance(text)
			left = anchor.x() - (0 if h < 0 else total / 2 if h == 0 else total)
			self._drawText(painter, text, fm, QPointF(left, anchor.y()), -1, v)
			if unit:
				painter.setFont(unitFont)
				unitColor = _color(self._unitSpec['color']) if self._unitSpec.get('color') is not None else _color('$faint')
				painter.setPen(unitColor)
				self._drawText(painter, f' {unit}', unitFm, QPointF(left + valueW, anchor.y()), -1, v)

		avail: QRectF = layout['avail']
		if position == 'right':
			draw(QPointF(rect.right(), mid.y()), 1, 0)
		elif position == 'left':
			draw(QPointF(rect.left(), mid.y()), -1, 0)
		elif position in ('top', 'bottom'):
			h = {'start': -1, 'center': 0, 'end': 1}.get(align, 0 if vertical else 1)
			x = avail.left() if h < 0 else avail.right() if h > 0 else rect.center().x()
			if vertical:
				x = rect.center().x()
				h = 0
			size = layout['valueSize']
			if vertical:
				y = rect.top() + layout['strip']['before'] - size * 0.62 if position == 'top' else rect.bottom() - layout['strip']['after'] + size * 0.62
				if position == 'top' and layout['captionText']:
					y = rect.top() + layout['capPx'] * 1.25 + size * 0.62
			else:
				y = rect.top() + need['before'] - size * 0.62 if position == 'top' else rect.bottom() - need['after'] + size * 0.62
				if position == 'top' and layout['captionText']:
					y = rect.top() + layout['capPx'] * 1.25 + size * 0.62
			draw(QPointF(x, y), h, 0)
		else:  # inside
			valueT = self._t(self._value)
			if self._style == 'thermometer':
				if spec.get('color') is None:
					color = _contrast(self._underColor(0.0 if self._fill else valueT))
				draw(layout['bulbCenter'], 0, 0)
			else:
				h = {'start': -1, 'center': 0, 'end': 1}.get(align, 1)
				x = a.x() + w * 0.35 if h < 0 else b.x() - w * 0.35 if h > 0 else mid.x()
				if vertical:
					x, h = mid.x(), 0
				if spec.get('color') is None:
					color = _contrast(self._underColor({-1: 0.04, 0: 0.5, 1: 0.96}[h]))
				draw(QPointF(x, mid.y() if not vertical else a.y() - w), h, 0)
