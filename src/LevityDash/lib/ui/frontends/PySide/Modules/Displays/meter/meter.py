"""The parts of a meter that are not about arcs.

A meter reads a value and shows it: the range it covers, the labels around the
value, and the items that read it - the zones, the fill, the markers, the needle.
What a meter does not know is the *shape* those items sit on. A `Gauge` adds the
arc, the angles and the radius-based sizing; a `Bar` (phase 3 of
docs/tasks/meter-and-bar.md) adds a straight track and answers the same questions
with its own extents.

`Gauge.py` imports everything here and re-exports it, so nothing outside this
package has to know the split. The one thing this module cannot import - `Gauge`
itself, named by the annotations below - is handed over at the foot of that file,
the same arrangement `meter/elements.py` uses.
"""
import copy
from collections.abc import Mapping
from functools import cached_property
from math import floor, isclose, isinf, log10, sqrt
from typing import TYPE_CHECKING, Optional, Sequence, Type, Union

from numpy import ceil
from PySide6.QtCore import QPointF, QRectF, QSizeF, Signal, Slot
from PySide6.QtGui import QTransform
from WeatherUnits import Humidity, Length, Measurement, Wind

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.stateful import StateProperty
from LevityDash.lib.ui import UILogger, Color
from LevityDash.lib.ui.Geometry import Alignment, AlignmentFlag, DimensionType, Size, ValueDisplayPosition, parseSize, parseX, parseY, size_px
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.DisplayBase import Display
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.curvetext import normalizeCorner
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.elements import (
	GaugeCaption, GaugeFill, GaugeMarker, GaugeUnit, GaugeValueLabel, GaugeZones, Graduations, Needle,
	StatefulGaugeItem, _UNIT_UNDER_VALUE, gaugeKeyName,
)
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.scale import GaugeValue, Numeric, Scale, decode_measurement
from LevityDash.lib.ui.frontends.PySide.utils import DisplayType
from LevityDash.lib.utils.data import MinMax
from LevityDash.lib.utils.shared import clearCacheAttr, defer, is_prime, INVERSE_GOLDEN_RATIO

if TYPE_CHECKING:  # the real import would be a cycle; see the module docstring
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Gauge import Gauge

#: The display class these meters belong to, handed over by `Gauge.py` once it has
#: defined it. Annotations here resolve against *this* module's globals.
Gauge = None

log = UILogger.getChild('meter')

__all__ = ['GaugeRange', 'Meter']


def _markerText(spec) -> str:
	"""The ``value:`` text of a marker spec, for log messages. Never raises."""
	try:
		return str(spec.get('value'))
	except Exception:
		return str(spec)


class GaugeRange(StatefulGaugeItem):
	_min: Measurement
	_max: Measurement
	valueClass: Type[Measurement]

	ranges = {
		'inhg': MinMax(27, 31),
		'mmhg': MinMax(730, 790),
		'mbar': MinMax(970, 1060),
		'f': MinMax(0, 120),
		'c': MinMax(-20, 50),
		'mph': MinMax(0, 15),
		'in/hr': MinMax(0, 3),
		'mm/hr': MinMax(0, 75),
		'v': MinMax(2.5, 3.3),
		'default': MinMax(0, 120),
		'lux': MinMax(0, 100000),
		'angle': MinMax(0, 360),
		'percentage': MinMax(0, 1),

		CategoryItem('*.humidity.*'):
			MinMax(
				Humidity(0),
				Humidity(1)
			),

		CategoryItem('environment.wind.speed'):
			MinMax(
				Wind.MetersPerSecond(0),
				Wind.MetersPerSecond(10)
			),

		CategoryItem('environment.wind.speed.gust'):
			MinMax(
				Wind.MetersPerSecond(0),
				Wind.MetersPerSecond(35)
			),

	}

	def __init__(self, gauge: 'Gauge', **state):
		super().__init__(gauge, **state)
		self.add_defaults_to_state(state)
		self.state = state

	@StateProperty(key='wrap', default=False, allowNone=False, repr=True)
	def wrap(self) -> bool:
		"""A cyclic scale: a value past the maximum comes round again from the minimum.
		A clock face (0-12 hours) or a bearing (0-360) turns instead of stopping at the end."""
		return self._wrap

	@wrap.setter
	def wrap(self, value: bool):
		self._wrap = bool(value)

	@StateProperty(key='round-to', repr=True)
	def round_to(self) -> int | float:
		return self._round_to

	@round_to.setter
	def round_to(self, value: int | float):
		self._round_to = value

	@round_to.item_default
	def round_to(self) -> int | float:
		span = abs(float(self.max - self.min))
		if 99 < span <= 350:
			return 10
		if log10(span).is_integer():
			return span / 10
		_power = floor(log10(span))
		while _power > -12:
			_divisor = 10 ** _power
			if isclose(span / _divisor, round(span / _divisor), rel_tol=1e-9):
				return _divisor
			_power -= 1
		# Nothing divides it (a span like 1/3): keep rounded_min finite.
		return 10 ** floor(log10(span))

	@StateProperty(key='min', repr=True)
	def min(self) -> Measurement:
		return self._min

	@min.setter
	def min(self, value: Measurement):
		self._reset_cache()
		self._min = value

	@min.decode
	def min(self, value: str | int | float) -> Measurement:
		return decode_measurement(value, self._gauge.valueClass)

	@min.item_default
	def min(self) -> Measurement:
		_type = self._gauge.valueClass
		try:
			limits_min = _type(self.default_range.min)
		except AttributeError:
			limits_min = 0
		if isinf(limits_min):
			limits_min = 0
		return _type(limits_min)

	@min.condition(method='get')
	def min(self, value: Measurement):
		return value != type(value).typedLimits.min

	@cached_property
	def rounded_min(self) -> Measurement:
		round_to = self.round_to
		if not round_to:
			return self.min
		# Round the quotient first: 29.9 / 0.1 is 298.99999999999994, which floors to 29.8.
		return self._gauge.valueClass(floor(round(float(self.min) / round_to, 9)) * round_to)

	@StateProperty(key='max', repr=True)
	def max(self) -> Measurement:
		return self._max

	@max.setter
	def max(self, value: Measurement):
		self._reset_cache()
		self._max = value

	@max.decode
	def max(self, value: str | int | float) -> Measurement:
		return decode_measurement(value, self._gauge.valueClass)

	@max.item_default
	def max(self) -> Measurement:
		_type = self._gauge.valueClass
		try:
			limits_max = _type(self.default_range.max)
		except AttributeError:
			limits_max = 100
		if isinf(limits_max):
			limits_max = 100
		return _type(limits_max)

	@max.condition(method='get')
	def max(self, value: Measurement):
		return value != type(value).typedLimits.max

	@cached_property
	def _rounded_max(self) -> Measurement:
		round_to = self.round_to
		if not round_to:
			return self.max
		return self._gauge.valueClass(ceil(round(float(self.max) / round_to, 9)) * round_to)

	@cached_property
	def rounded_max(self):
		rounded_range = self._rounded_range
		if isinstance(rounded_range, int) or (isinstance(rounded_range, float) and rounded_range.is_integer()):
			if is_prime(rounded_range):
				return self._rounded_max + 1
			return self._rounded_max

		# Count whole round_to steps, as rounded_min does, and add them to rounded_min.
		round_to = self.round_to
		if not round_to:
			return self._rounded_max
		steps = ceil(round(float(rounded_range) / round_to, 9))
		return self._gauge.valueClass(float(self.rounded_min) + steps * round_to)

	@property
	def range(self) -> Measurement:
		return abs(self.max - self.min)

	@range.setter
	def range(self, value: MinMax):
		self.min, self.max = value

	@cached_property
	def rounded_range(self) -> Measurement:
		return abs(self.rounded_max - self.rounded_min)

	@cached_property
	def _rounded_range(self) -> Measurement:
		return abs(self._rounded_max - self.rounded_min)

	@cached_property
	def range_int(self) -> int:
		return int(self.rounded_range)

	@staticmethod
	def _as_value_class(preset: MinMax, value_class) -> MinMax:
		"""Express a preset range in the unit the gauge actually displays.

		The CategoryItem presets are written in the unit the author
		happened to think in - `environment.wind.speed` is stored in m/s -
		but a gauge shows whatever the config localizes to. A US config
		displays mph, so the gauge got a 0-10 range while its needle moved
		in mph, and the graduations came out wrong (the wind dial rendered
		as a bare arc with no ticks at all).

		Conversion, not reinterpretation: MetersPerSecond(10) becomes
		MilesPerHour(22.4), so the dial spans the same real-world range.
		"""
		try:
			return MinMax(value_class(preset.min), value_class(preset.max))
		except Exception:
			# Not convertible (a plain number, or an unrelated dimension) -
			# use it as written rather than losing the preset entirely.
			return preset

	@property
	def default_range(self) -> MinMax:
		_type = self._gauge.valueClass

		try:
			similar_keys = [
				i for i in self.ranges
				if not isinstance(i, str)
					 and self._gauge.parent.key < i
			]
			similar_keys.sort(key=lambda i: len(i), reverse=True)
			for key in similar_keys:
				try:
					return self._as_value_class(self.ranges[key], _type)
				except KeyError:
					pass
		except AttributeError:
			pass

		try:
			if (preset_range := self.ranges.get(_type.unit.lower(), None)) is not None:
				return preset_range
		except AttributeError:
			pass

		try:
			return MinMax(_type.typedLimits.min, _type.typedLimits.max)
		except AttributeError:
			pass

		return MinMax(0, 100)

	def _reset_cache(self):
		clearCacheAttr(self, 'rounded_min', 'rounded_max', '_rounded_max', 'rounded_range', '_rounded_range', 'range_int')


class Meter(Display):
	"""A display that reads a value and shows it, whatever shape it sits on.

	Meter holds the value, the range it covers, the labels and captions around it,
	and the items that read the value: the zones, the fill, the markers, the
	needle. It does not hold a *shape*. `Gauge` adds the arc, the angles and the
	radius-based sizing on top of this; a `Bar` (phase 3) adds a straight track and
	answers the same size questions with its own extents.
	"""

	def _buildLabel(self, attr: str, labelType: type, value):
		"""Turn a `value-label`/`unit-label` mapping into a real label.

		Reuses the label already on the gauge when there is one, so a reload
		applies onto the existing item rather than orphaning it and building a
		second.
		"""
		if not isinstance(value, Mapping):
			return value
		label = getattr(self, attr, None)
		if not isinstance(label, labelType):
			label = labelType(self)
			label.textBox.setParentItem(self)
			label.hide()
		try:
			label.state = dict(value)
		except Exception as e:  # noqa: BLE001 - a bad key must not abort the load
			log.warning(f'{self}: could not apply {labelType.__name__} state {value!r}: {e}')
		return label

	@StateProperty(key='value-label', repr=True)
	def valueLabel(self) -> GaugeValueLabel:
		return self._valueLabel

	@valueLabel.factory
	def valueLabel(self) -> GaugeValueLabel:
		label = GaugeValueLabel(self)
		label.textBox.setParentItem(self)
		label.hide()
		# NB: the textBox was reparented to the gauge above, so it is no longer
		# a child of the label and `label.hide()` does not reach it. The value
		# text is what the viewer actually sees, so it stays visible - the
		# label wrapper being hidden is incidental.
		return label

	@valueLabel.setter
	def valueLabel(self, value: GaugeValueLabel):
		self._valueLabel = value

	@valueLabel.decode
	def valueLabel(self, value) -> GaugeValueLabel:
		# `value-label: {visible: false}` arrives as a plain mapping. Without a
		# decoder the setter stored it verbatim, and `_afterSetState` -> refresh()
		# then reached `self.valueLabel.textBox` on a dict. That AttributeError
		# aborted the whole dashboard load, which is what left a board showing
		# nothing but the moon. See docs/tasks/dashboard-wont-load.md.
		return self._buildLabel('_valueLabel', GaugeValueLabel, value)

	@StateProperty(key='unit-label', repr=True)
	def unitLabel(self) -> GaugeUnit:
		return self._unitLabel

	@unitLabel.factory
	def unitLabel(self) -> GaugeUnit:
		label = GaugeUnit(self)
		label.textBox.setParentItem(self)
		label.hide()
		label.textBox.hide()
		return label

	@unitLabel.setter
	def unitLabel(self, value: GaugeUnit):
		self._unitLabel = value

	@unitLabel.decode
	def unitLabel(self, value) -> GaugeUnit:
		return self._buildLabel('_unitLabel', GaugeUnit, value)

	@StateProperty(key='sub-label', default=None, allowNone=True, dependencies={'range', 'arc'})
	def subLabel(self) -> Optional[dict | str]:
		"""Small text below the centre value (and its unit): same forms as ``caption``."""
		return self._subSpec

	@subLabel.setter
	def subLabel(self, value):
		self._setCaption('_subItem', '_subSpec', 'sub-label', value)

	@subLabel.decode
	def subLabel(self, value):
		return Gauge._decodeCaption(value)

	@subLabel.encode
	def subLabel(self, value):
		return copy.deepcopy(value) if value else None

	@StateProperty(key='caption', default=None, allowNone=True, dependencies={'range', 'arc'})
	def caption(self) -> Optional[dict | str]:
		"""Small text above the centre value: a string, or ``{text, value, format, size, color}``."""
		return self._captionSpec

	@caption.setter
	def caption(self, value):
		self._setCaption('_captionItem', '_captionSpec', 'caption', value)

	@caption.decode
	def caption(self, value):
		return Gauge._decodeCaption(value)

	@caption.encode
	def caption(self, value):
		return copy.deepcopy(value) if value else None

	def _clearCaption(self, attr: str, specAttr: str) -> None:
		item = getattr(self, attr)
		setattr(self, attr, None)
		setattr(self, specAttr, None)
		if item is not None:
			item.close()
			if (scene := item.scene()) is not None:
				scene.removeItem(item)

	@staticmethod
	def _decodeCaption(value):
		if value is None or isinstance(value, (str, Mapping)):
			return value if not isinstance(value, Mapping) else dict(value)
		log.warning(f'ignored caption {value!r}: expected text or a mapping')
		return None

	def _setCaption(self, attr: str, specAttr: str, side: str, value) -> None:
		self._clearCaption(attr, specAttr)
		if not value:
			return
		# A bad caption is a warning, never a failed dashboard load.
		try:
			item = GaugeCaption(self, side)
			item.configure(value)
		except Exception as e:
			log.warning(f'Gauge {gaugeKeyName(self)} {side} skipped: {e}')
			return
		setattr(self, attr, item)
		setattr(self, specAttr, copy.deepcopy(value))

	def _syncCaptions(self):
		for item in self._captionItems():
			item.refresh()

	def _valueAnchor(self) -> QRectF:
		"""The box the centre value (and a unit hung under it) occupies, in gauge coordinates.
		With no visible value, a point at the dial's centre."""
		rects = []
		vbox = self.valueLabel.textBox
		try:
			if vbox.isVisibleTo(self):
				r = self.mapRectFromScene(vbox.scenePath().boundingRect())
				if not r.isEmpty():
					rects.append(r)
			ubox = self.unitLabel.textBox
			if rects and ubox.isVisibleTo(self) and ubox._position in _UNIT_UNDER_VALUE:
				r = self.mapRectFromScene(ubox.scenePath().boundingRect())
				if not r.isEmpty():
					rects.append(r)
		except Exception as e:  # noqa: BLE001
			log.warning(f'Gauge {gaugeKeyName(self)} could not measure its value: {e!r}')
		if not rects:
			return QRectF(self.center, QSizeF(0, 0))
		box = rects[0]
		for r in rects[1:]:
			box = box.united(r)
		return box

	def _syncUnitUnderValue(self):
		"""Hang a `float-under`/`below` unit under the value's final glyphs.

		The unit places itself from the value's box while both are still being
		laid out, and recenter() then shifts each again, so where it landed
		depended on update order - over the value as often as under it. Run
		last, against the glyphs as drawn: the gauge's version of Realtime's
		_syncFloatUnderPair.
		"""
		unit, value = getattr(self, '_unitLabel', None), getattr(self, '_valueLabel', None)
		if not isinstance(unit, GaugeUnit) or not isinstance(value, GaugeValueLabel):
			return
		ubox, vbox = unit.textBox, value.textBox
		try:
			if not ubox.isVisibleTo(self) or ubox._position not in _UNIT_UNDER_VALUE or ubox._warpActive:
				return
			v = self.mapRectFromScene(vbox.scenePath().boundingRect())
			u = self.mapRectFromScene(ubox.scenePath().boundingRect())
		except Exception as e:  # noqa: BLE001 - layout must never abort a load
			log.warning(f'Gauge {gaugeKeyName(self)} could not place its unit label: {e!r}')
			return
		if v.isEmpty() or u.isEmpty():
			return
		# A third of the unit's own height: reads as one block, never touches.
		shift = unit.offsetPx()
		dx = v.center().x() - u.center().x() + shift.x()
		dy = v.bottom() + u.height() / 3 - u.top() + shift.y()
		t = ubox.transform()
		# Shift the translation part only, in gauge coordinates.
		ubox.setTransform(QTransform(t.m11(), t.m12(), t.m21(), t.m22(), t.dx() + dx, t.dy() + dy))

	_captionItem: Optional[GaugeCaption] = None

	def _captionItems(self) -> list:
		return [i for i in (self._captionItem, self._subItem) if i is not None]

	_subItem: Optional[GaugeCaption] = None

	_unit: Optional[str] = None

	_value: GaugeValue = 0

	_valueClass: Type[GaugeValue] = float

	@property
	def value(self) -> GaugeValue:
		return self._value

	@value.setter
	def value(self, value):
		if isinstance(value, (int, float)):
			self.valueClass = value
			if float(value) == float(self._value):
				return
			self._value = value
			self.valueLabel.textBox.refresh()
			self.unitLabel.textBox.refresh()
			self.needle.refresh()
			for item in self._fillItems():
				item.refresh()
			self._update_shape()

	@property
	def valueClass(self) -> Type[GaugeValue]:
		# A container that has no class yet reports None; fields that decode while the states apply need something callable.
		return self._valueClass or float

	@valueClass.setter
	def valueClass(self, value):
		if not isinstance(value, type):
			value = type(value)
		if value is self._valueClass:
			return

		self._valueClass = value

		self.rebuild()

	@Slot(float)
	def updateSlot(self, value: Union[Measurement, Numeric]):
		if isinstance(value, (int, float)):
			self.valueClass = value

	@property
	def value_scale(self) -> Scale:
		"""This gauge's range as fractions - the value→``t`` half of the track's work.

		Not `scale`: `QGraphicsItem` already owns that name for the item's
		transform, and shadowing it would break `item.scale()` calls.
		"""
		_range = self._range
		return Scale.from_span(_range.rounded_min, _range.rounded_range, _range.wrap)

	@StateProperty(key='range', link=GaugeRange, allowNone=False, repr=True, sortOrder=-2)
	def range(self) -> GaugeRange:
		return self._range

	@range.setter
	def range(self, value: GaugeRange):
		self._range = value

	@range.factory
	def range(self) -> GaugeRange:
		return GaugeRange(self)

	@range.after
	def range(self):
		self.rebuild()

	valueChanged = Signal(float)

	_center_offset: QPointF | QPointF = QPointF(0, 0)

	_captionSpec = None

	_subSpec = None

	def releaseSources(self):
		"""Stop and release every value source the markers and fill hold.
		Called when the owning panel is deleted; never raises."""
		for clear in (self._clearMarkers, self._clearFill, self._clearZones,
					lambda: self._clearCaption('_captionItem', '_captionSpec'),
					lambda: self._clearCaption('_subItem', '_subSpec')):
			try:
				clear()
			except Exception as e:
				log.warning(f'Gauge {gaugeKeyName(self)} could not release its value sources: {e!r}')

	@property
	def type(self):
		return DisplayType.Gauge

	@property
	def displayType(self):
		return DisplayType.Gauge

	@defer
	def rebuild(self):
		# A meter without tick surfaces (a bar draws its own) just refreshes.
		for name in ('major_ticks_surface', 'minor_ticks_surface', 'micro_ticks_surface'):
			if (surface := getattr(self, name, None)) is not None:
				surface.rebuild()

		self.refresh()

	def _update_shape(self):
		clearCacheAttr(self, 'value_text_box_area_rect', 'full_gauge_path')

	def parentResized(self, arg: Union[QPointF, QSizeF, QRectF]):
		super().parentResized(arg)
		self.refresh()

	@property
	def pen(self):
		return self._pen

	@StateProperty(key='alignment', allowNone=False, after=rebuild, repr=True)
	def alignment(self) -> Alignment:
		return self._alignment

	@alignment.setter
	def alignment(self, value: Alignment):
		self._alignment = value

	@alignment.item_default
	def alignment(self) -> Alignment:
		return Alignment(AlignmentFlag.Center)

	@alignment.decode
	def alignment(self, value: str | int | tuple[AlignmentFlag, AlignmentFlag] | AlignmentFlag) -> Alignment:
		if isinstance(value, (str, int)):
			alignment = AlignmentFlag[value]
		elif value is None:
			alignment = AlignmentFlag.Center
		elif isinstance(value, tuple):
			return Alignment(*value)
		else:
			alignment = AlignmentFlag.Center
		return Alignment(alignment)

	#: Corner names `anchor` accepts, as the (x, y) share of the box the pivot sits at.
	_ANCHORS = {
		'top-left': (0, 0), 'top-right': (1, 0),
		'bottom-left': (0, 1), 'bottom-right': (1, 1),
	}

	_anchor: Optional[str] = None

	_s_inset = Size.Height(0.0, relative=True)

	@StateProperty(key='anchor', default=None, allowNone=True, after=rebuild, repr=True)
	def anchor(self) -> Optional[str]:
		"""Pin the pivot (the arc centre) to a corner of the box: ``top-left``, ``top-right``,
		``bottom-left`` or ``bottom-right``. ``radius`` then counts from the box's short side, so
		100% is the whole short side minus ``inset``. Use it for a quarter-circle dial that fills
		a card. Without it the dial is centred as before."""
		return self._anchor

	@anchor.setter
	def anchor(self, value: Optional[str]):
		self._anchor = value

	@anchor.decode
	def anchor(self, value) -> Optional[str]:
		if value is None:
			return None
		name = normalizeCorner(value)
		if name not in Gauge._ANCHORS:
			raise ValueError(f'anchor must be one of {sorted(Gauge._ANCHORS)}, got {value!r}')
		return name

	@StateProperty(key='inset', default=Size.Height(0.0, relative=True), allowNone=False, after=rebuild)
	def inset(self) -> Length | Size.Height:
		"""Gap between an `anchor`ed pivot and the box's two edges at that corner."""
		return self._s_inset

	@inset.setter
	def inset(self, value):
		self._s_inset = value

	@inset.decode
	def inset(self, value) -> Length | Size.Height:
		return parseSize(value, allowFloat=False, dimension=DimensionType.height)

	@inset.encode
	def inset(self, value) -> str:
		return str(value)

	@property
	def insetPx(self) -> float:
		if self._anchor is None:
			return 0.0
		return max(size_px(self._s_inset, min(self.height(), self.width())), 0.0)













	@property
	def baseWidth(self):
		return sqrt(self.height() ** 2 + self.width() ** 2) * INVERSE_GOLDEN_RATIO * 0.01

	@property
	def defaultColor(self):
		return Color.text.QColor

	def setRect(self, *args, **kwargs):
		super().setRect(*args, **kwargs)

	@StateProperty(key='needle', repr=True)
	def needle(self) -> Needle:
		return self._needle

	@needle.factory
	def needle(self) -> Needle:
		return Needle(self)

	@needle.setter
	def needle(self, value: Needle):
		self._needle = value

	@StateProperty(key='fill', default=None, allowNone=True, dependencies={'range', 'arc'})
	def fill(self) -> Optional[dict]:
		"""A value-driven arc over the track: ``{from, to, weight, color}``.

		Kept as the plain mapping the user wrote; the scene item is ``self._fillItem``.
		"""
		return self._fillSpec

	@fill.setter
	def fill(self, value: Optional[dict]):
		self._clearFill()
		if not value:
			return
		# A bad fill is a warning, never a failed dashboard load.
		try:
			item = GaugeFill(self)
			item.configure(value)
		except Exception as e:
			log.warning(f'Gauge {gaugeKeyName(self)} fill skipped: {e}')
			return
		self._fillItem = item
		self._fillSpec = copy.deepcopy(dict(value))

	@fill.decode
	def fill(self, value) -> Optional[dict]:
		if value is None:
			return None
		if not isinstance(value, Mapping):
			log.warning(f'Gauge {gaugeKeyName(self)} ignored fill {value!r}: expected a mapping')
			return None
		return dict(value)

	@fill.encode
	def fill(self, value: Optional[dict]) -> Optional[dict]:
		return copy.deepcopy(value) if value else None

	def _clearFill(self):
		item = self._fillItem
		self._fillItem = None
		if item is not None:
			item.close()
		self._fillSpec = None
		if item is not None and (scene := item.scene()) is not None:
			scene.removeItem(item)

	@StateProperty(key='zones', default=None, allowNone=True, dependencies={'range', 'arc'})
	def zones(self) -> Optional[list]:
		"""Coloured bands on the track: a list of ``{from, to, color, mark}`` mappings.

		Kept as the plain mappings the user wrote; the scene item is ``self._zonesItem``.
		"""
		return self._zoneSpecs or None

	@zones.setter
	def zones(self, value: Optional[list]):
		self._clearZones()
		if not value:
			return
		try:
			item = GaugeZones(self)
			kept = item.configure(value)
		except Exception as e:
			log.warning(f'Gauge {gaugeKeyName(self)} zones skipped: {e}')
			return
		if not kept:
			scene = item.scene()
			if scene is not None:
				scene.removeItem(item)
			return
		self._zonesItem = item
		self._zoneSpecs = kept
		try:
			item.refresh()
		except Exception as e:
			log.debug(f'Gauge {gaugeKeyName(self)} zones not drawn yet: {e}')

	@zones.decode
	def zones(self, value) -> list:
		if isinstance(value, Mapping):
			value = [value]
		if not isinstance(value, (list, tuple)):
			log.warning(f'Gauge {gaugeKeyName(self)} ignored zones {value!r}: expected a list')
			return []
		for spec in value:
			if not isinstance(spec, Mapping):
				log.warning(f'Gauge {gaugeKeyName(self)} skipped zone {spec!r}: expected a mapping')
		return [dict(spec) for spec in value if isinstance(spec, Mapping)]

	@zones.encode
	def zones(self, value: Optional[list]) -> Optional[list]:
		return copy.deepcopy(value) if value else None

	def _clearZones(self):
		item = self._zonesItem
		self._zonesItem = None
		self._zoneSpecs = []
		if item is not None:
			item.close()
			if (scene := item.scene()) is not None:
				scene.removeItem(item)

	@StateProperty(key='markers', default=None, allowNone=True, dependencies={'range', 'needle'})
	def markers(self) -> Optional[list]:
		"""Extra indicators: a list of ``{value, type, color, ...}`` mappings.

		Kept as the plain mappings the user wrote, so saving writes them back
		unchanged. The scene items built from them are ``self._markerItems``.
		"""
		return self._markerSpecs or None

	@markers.setter
	def markers(self, value: Optional[list]):
		self._clearMarkers()
		specs = []
		for spec in value or []:
			# One bad marker is skipped; it must never abort the dashboard load.
			try:
				marker = GaugeMarker(self)
				marker.configure(spec)
			except Exception as e:
				log.warning(f'Gauge {gaugeKeyName(self)} skipped marker {_markerText(spec)!r}: {e}')
				try:
					marker.close()
					self.scene().removeItem(marker)
				except Exception:
					pass
				continue
			self._markerItems.append(marker)
			specs.append(copy.deepcopy(dict(spec)))
		self._markerSpecs = specs

	@markers.decode
	def markers(self, value) -> list:
		if isinstance(value, Mapping):
			value = [value]
		if not isinstance(value, (list, tuple)):
			log.warning(f'Gauge {gaugeKeyName(self)} ignored markers {value!r}: expected a list')
			return []
		valid = []
		for spec in value:
			if isinstance(spec, Mapping):
				valid.append(dict(spec))
			else:
				log.warning(f'Gauge {gaugeKeyName(self)} skipped marker {spec!r}: expected a mapping with a value')
		return valid

	@markers.encode
	def markers(self, value: Optional[list]) -> Optional[list]:
		return copy.deepcopy(value) if value else None

	def _clearMarkers(self):
		for marker in self._markerItems:
			marker.close()
			if (scene := marker.scene()) is not None:
				scene.removeItem(marker)
		self._markerItems = []
		self._markerSpecs = []

	@StateProperty(key='major', repr=True, dependencies={'range'})
	def majorDivisions(self) -> Graduations:
		return self._majorDivisions

	@majorDivisions.factory
	def majorDivisions(self):
		return Graduations(gauge=self, type=Graduations.Type.Major)

	@majorDivisions.setter
	def majorDivisions(self, value: Graduations):
		self._majorDivisions = value

	@StateProperty(key='minor', repr=True, dependencies={'majorDivisions'})
	def minorDivisions(self) -> Graduations:
		return self._minorDivisions

	@minorDivisions.factory
	def minorDivisions(self):
		return Graduations(gauge=self, type=Graduations.Type.Minor)

	@minorDivisions.setter
	def minorDivisions(self, value: Graduations):
		self._minorDivisions = value

	@StateProperty(key='micro', repr=True, dependencies={'minorDivisions'})
	def microDivisions(self) -> Graduations:
		return self._microDivisions

	@microDivisions.factory
	def microDivisions(self):
		return Graduations(gauge=self, type=Graduations.Type.Micro)

	@microDivisions.setter
	def microDivisions(self, value: Graduations):
		self._microDivisions = value

	def _zoneItems(self) -> list:
		item = getattr(self, '_zonesItem', None)
		return [] if item is None else [item]

	def _fillItems(self) -> list:
		item = getattr(self, '_fillItem', None)
		return [] if item is None else [item]

	def glowChanged(self):
		"""The gauge's ``glow`` is the default for the fill, zones, needle and markers; the track has its own."""
		for item in (getattr(self, '_needle', None), *self._markerItems, *self._zoneItems(), *self._fillItems()):
			if item is not None:
				item.glowChanged()
