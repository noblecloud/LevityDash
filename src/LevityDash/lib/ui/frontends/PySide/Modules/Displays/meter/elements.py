"""The things a meter is made of, minus anything that only works on a dial.

A meter holds *items*: the track, its ticks, the needle or pointer that reads the
value, the fill that trails it, the text around it. These are the bases those
items share - the reference back to the meter they belong to, and the stateful and
path-item flavours of it - plus the value type variable the tick machinery is
generic over.

`Gauge.py` imports everything here and re-exports it, so nothing outside this
package has to know the split. The direction is one way: this module never
imports a display class at import time. Where it must name `Gauge` - to recognise
it in the arguments an item is constructed with - it imports it inside the call,
because a gauge imports this module.
"""
import copy
import PySide6
from collections.abc import Mapping
from enum import Enum
from functools import cached_property
from itertools import combinations
from math import atan2, floor, hypot, inf, isclose, isfinite, isinf
from numbers import Number
from typing import TYPE_CHECKING, Any, Dict, Iterator, Optional, Sequence, Type, Union

from numpy import ceil, cos, pi, radians, sin, sqrt
from PySide6.QtCore import (
	QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRectF, QSizeF, QTimer, QVariantAnimation, Signal,
)
from PySide6.QtGui import QBrush, QColor, QGradient, QPainter, QPainterPath, QPainterPathStroker, QPen, QPolygonF, QTransform, Qt
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QStyleOptionGraphicsItem, QWidget

from LevityDash.lib.stateful import Binding, SourceType, StateProperty, Stateful
from LevityDash.lib.stateful_mixins import ColorGradientMixin
from LevityDash.lib.ui import Color, Gradient, UILogger
from LevityDash.lib.ui.Geometry import (
	Alignment, AlignmentFlag, Dimension, DimensionType, DisplayPosition, RelativeFloat, Size, parseHeight, parseSize,
	parseWidth, size_px,
)
from LevityDash.lib.ui.frontends.PySide.Modules.Displays import SurfaceCentered
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Annotations import AnnotationLabels, AnnotationText
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.curvetext import CurveMode, warp_path
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import SizeGroup
from LevityDash.lib.ui.frontends.PySide.utils import DebugPaint, addCrosshair, outline_path
from LevityDash.lib.ui.frontends.PySide.utils import SoftShadow
from LevityDash.lib.utils import Axis
from LevityDash.lib.utils.shared import (
	INVERSE_GOLDEN_RATIO, ClosestMatchEnumMeta, Unset, clearCacheAttr, defer, factors, get,
	guarded_cached_property, now, radialPoint,
)
from LevityDash.lib.valuesource import openValueSource
from WeatherUnits import Angle, Length, Measurement, Percentage

from .scale import (
	CLOCK_HANDS, GaugeValue, Numeric, _isWholeSteps, clockTurn, decode_measurement, filter_factors, parseClockTime,
	shortestDelta,
)

if TYPE_CHECKING:  # the real import would be a cycle; see `gauge_class`
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Gauge import Gauge

#: The items' log channel. `Gauge.py` logs as 'Gauge'; these moved out of it, so
#: they log under the package name.
log = UILogger.getChild('meter.elements')

__all__ = ['GaugeItem', 'GaugePathItem', 'GaugeValue', 'Numeric', 'StatefulGaugeItem', 'StatefulGaugePathItem']


def gauge_class():
	"""The `Gauge` class, imported when it is needed rather than at import time.

	`Gauge.py` imports this module, so importing it back at module level would be
	a cycle. The class here is the one an item recognises its owner by.
	"""
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Gauge import Gauge
	return Gauge


def gaugeKeyName(gauge: 'Gauge') -> str:
	"""The key of the panel that owns `gauge`, for log messages. Never raises."""
	try:
		return str(gauge.parent.key)
	except Exception:
		return '<unkeyed>'


class GaugeItem:
	"""
	Base class for all gauge items.  This class provides a reference to the gauge that the item belongs to
	and will raise a ValueError if no gauge is provided.
	"""

	_gauge: 'Gauge'

	def __extract_gauge(self, args, kwargs):
		gauge = get(kwargs, 'gauge' 'parent', default=None, expectedType=gauge_class())
		if gauge is None:
			gauge = next((arg for arg in args if isinstance(arg, gauge_class())), None)
		if gauge is None:
			gauge = next((kwarg for kwarg in kwargs.values() if isinstance(kwarg, gauge_class())), None)
		if gauge is None:
			raise ValueError(f'No gauge provided for {self.__class__.__name__}')
		return gauge

	def __init__(self, *args, **kwargs):

		self._gauge = self.__extract_gauge(args, kwargs)

		try:
			super().__init__(*args, **kwargs)
		except TypeError:
			super().__init__()

	@property
	def gauge(self) -> 'Gauge':
		return self._gauge

	def remove(self):
		self.gauge.scene().removeItem(self)


class StatefulGaugeItem(GaugeItem, Stateful):

	def __init__(self, *args, **kwargs):
		super(StatefulGaugeItem, self).__init__(*args, **kwargs)
		self.prep_init(args=args, kwargs=kwargs, stateful_parent=self.gauge)


class GaugePathItem(GaugeItem, QGraphicsPathItem):

	_weight_scale: float = 1.0
	_shape: QPainterPath = QPainterPath()

	def __init__(self, *args, **kwargs):
		super(GaugePathItem, self).__init__(*args, **kwargs)
		self.setPen(self.gauge.pen)

	def _set_color(self, color: Color):
		self.setBrush(color.QColor)

	@guarded_cached_property(guardFunc=lambda x: x is not None, default=None)
	def gauge(self) -> 'Gauge':
		try:
			return self._gauge
		except AttributeError:
			pass

		parent = self.parentItem()
		while not isinstance(parent, gauge_class()):
			try:
				parent = parent.parentItem()
			except AttributeError:
				return None
		return parent


class StatefulGaugePathItem(Stateful, GaugePathItem):

	def __init__(self, *args, **kwargs):
		super(StatefulGaugePathItem, self).__init__(*args, **kwargs)
		self.prep_init(args=args, kwargs=kwargs, stateful_parent=self.gauge)


class Graduations(ColorGradientMixin, StatefulGaugeItem):
	"""
	Divisions for a gauge.  This class uses configured options and value information
	to determine the interval between graduations or the number of graduations to show
	on the gauge.  Intervals should always be integers unless the range is small (less than 3).
	If both the interval and count are set, the count will be ignored unless the provided
	interval is unsuitable.


	Parameters
	----------
	gauge : Gauge
		The gauge that this graduation belongs to
	**state: Mapping, optional
		The state to use for this graduation
	"""

	enabled: bool
	count: int
	min_count: int
	max_usr_count: int
	interval: int
	min_interval: int
	max_interval: int
	spacing: int
	min_spacing: int
	max_spacing: int
	required_interval_factors: set[int]
	excluded_interval_factors: set[int]

	class Type(Enum):
		Major = 0
		Minor = 1
		Micro = 2

	def __init__(self, gauge: 'Gauge', **kwargs):
		self.tick_type = kwargs.pop('type', self.Type.Major)
		super().__init__(gauge, **kwargs)
		self.add_defaults_to_state(kwargs)
		self.state = kwargs

	def __rich_repr__(self, exclude: set = None):
		yield 'type', self.tick_type.name
		yield from Stateful.__rich_repr__(self, exclude)

	@property
	def super_grad(self) -> Optional['Graduations']:
		if self.tick_type == self.Type.Major:
			return None
		elif self.tick_type == self.Type.Minor:
			return self.gauge.majorDivisions
		elif self.tick_type == self.Type.Micro:
			return self.gauge.minorDivisions

	@property
	def sub_grad(self) -> Optional['Graduations']:
		if self.tick_type == self.Type.Major:
			return self.gauge.minorDivisions
		elif self.tick_type == self.Type.Minor:
			return self.gauge.microDivisions
		elif self.tick_type == self.Type.Micro:
			return None

	@property
	def surface(self) -> 'TickSurface':
		return getattr(self.gauge, f'{self.tick_type.name.lower()}_ticks_surface', None)

	@StateProperty(key='enabled', default=True, repr=True, allowNone=False, singleVal=True)
	def enabled(self) -> bool:
		return self._enabled

	@enabled.setter
	def enabled(self, value: bool):
		self._enabled = value
		clearCacheAttr(self, 'interval')

	@StateProperty(key='labels', repr=True)
	def labels(self) -> 'GaugeTickTextGroup':
		"""
		The labels for the graduations.

		Major ticks are labeled by default.
		"""
		return self._labels

	@labels.factory
	def labels(self) -> 'GaugeTickTextGroup':
		labels = GaugeTickTextGroup(self, self.surface)
		return labels

	@labels.setter
	def labels(self, value: 'GaugeTickTextGroup'):
		self._labels = value

	@labels.setter
	def labels(self, value: 'GaugeTickTextGroup'):
		self._labels = value

	@StateProperty(key='count', default=None, dependencies={'interval'})
	def usr_count(self) -> int:
		"""
		The number of graduations to show on the gauge (including the first and last graduations).
		"""
		return self._usr_count

	@usr_count.setter
	def usr_count(self, value: int | None):
		self._usr_count = value

	@StateProperty(key='min-count', default=None)
	def min_usr_count(self) -> int:
		"""
		The minimum number of graduations to show on the gauge (including the first and last graduations).
		"""
		return self._min_usr_count

	@min_usr_count.setter
	def min_usr_count(self, value: int | float | None):
		if isinf(value):
			value = None
		elif isinstance(value, float):
			value = int(value) + 1
		self._min_usr_count = value

	@StateProperty(key='max-count', default=None)
	def max_usr_count(self) -> int:
		"""
		The maximum number of graduations to show on the gauge (including the first and last graduations).
		"""
		return self._max_usr_count

	@max_usr_count.setter
	def max_usr_count(self, value: int | float | None):
		if isinf(value):
			value = None
		elif isinstance(value, float):
			value = int(value) + 1
		self._max_usr_count = value

	@StateProperty(key='position', allowNone=False, default=DisplayPosition.Inside, decoder=DisplayPosition.decode)
	def position(self) -> DisplayPosition:
		"""
		The position of ticks relative (inside or outside) to the arc path.

		Example Config
		--------------
		```yaml
		position: 'inside' | outside | "out"
		```
		"""
		return self._position

	@position.setter
	def position(self, value: DisplayPosition):
		self._position = value

	@StateProperty(key='length', allowNone=False)
	def length(self) -> Percentage | Length:
		"""
		The length of the ticks.

		Values can be specified as a percentage, a physical length ('1in', '0.3mm`, etc.), or a number.
		Numerical values are treated as pixel lengths except for float values between 0.0 and 1.0, which are handled as percentages.

		For major ticks, percentages are relative to the gauge's radius.
		With minor and micro ticks it is relative to the pixel length of the major or minor ticks, respectively.

		Example Config
		--------------
		```yaml
		gauge:
			major-ticks:
				length: 0.1  # 10% of the gauge's radius
			minor-ticks:
				length: 70%  # 70% the length of the major ticks
			micro-ticks:
				length: 2mm  # Two millimeters
		```
		"""
		return self._length

	@length.item_default
	def length(self) -> Percentage | Length:
		match self.tick_type:
			case self.Type.Major:
				return Percentage(0.1)
			case self.Type.Minor | self.Type.Micro:
				return Percentage(0.7)
			case _:
				raise ValueError(f'Invalid tick type: {self.tick_type}')

	@length.setter
	def length(self, value: float):
		self._length = value

	@length.decode
	def length(self, value: str | float) -> Dimension | Length | Percentage:
		parsed_value = parseSize(value, default=Unset, allowFloat=True, dimension=DimensionType.length)
		if parsed_value is Unset:
			parsed_value = type(self).length.default(type(self))
		if type(parsed_value) is float:
			parsed_value = Percentage(parsed_value)
		return parsed_value

	@length.encode
	def length(self, value: Percentage | Length) -> str:
		return str(value)

	@property
	def length_px(self) -> float:
		match self.tick_type:
			case self.Type.Major:
				relative_to = self.gauge.radius
				value = self.gauge.sizeAcross(self.length)
			case self.Type.Minor:
				value = size_px(self.length, relative_to := self.gauge.majorDivisions.length_px)
			case self.Type.Micro:
				value = size_px(self.length, relative_to := self.gauge.minorDivisions.length_px)
			case _:
				raise ValueError(f'Invalid tick type: {self.tick_type}')

		if isinstance(value, Percentage):
			return float(value * relative_to)

		return float(value)

	@StateProperty(key='width', allowNone=False)
	def width(self) -> Dimension | Length | Percentage:
		"""
		The width of the ticks.

		Values can be specified as a percentage, a physical length (`0.3cm`, `2mm`, etc.), or a number.
		Numerical values are treated as pixel lengths except for float values between 0.0 and 1.0, which are handled as percentages.
		"""
		return self._width

	@width.setter
	def width(self, value: float):
		self._width = value

	@width.decode
	def width(self, value: str) -> Dimension | Length | Percentage:
		parsed_value = parseSize(value, default=Unset, allowFloat=True, dimension=DimensionType.length)
		if parsed_value is Unset:
			parsed_value = type(self).width.default(type(self))
		if type(parsed_value) is float:
			parsed_value = Percentage(parsed_value)
		return parsed_value

	@width.item_default
	def width(self) -> float:
		match self.tick_type:
			case self.Type.Major:
				return Percentage(INVERSE_GOLDEN_RATIO)
			case self.Type.Minor | self.Type.Micro:
				return Percentage(INVERSE_GOLDEN_RATIO * INVERSE_GOLDEN_RATIO)
			case _:
				raise ValueError(f'Invalid tick type: {self.tick_type}')

	@property
	def width_px(self) -> float:
		match self.tick_type:
			case self.Type.Major:
				value = size_px(self.width, relative_to := self.gauge.baseWidth)
			case self.Type.Minor:
				value = size_px(self.width, relative_to := self.gauge.majorDivisions.width_px)
			case self.Type.Micro:
				value = size_px(self.width, relative_to := self.gauge.minorDivisions.width_px)
			case _:
				raise ValueError(f'Invalid tick type: {self.tick_type}')

		if isinstance(value, Percentage):
			return float(value * relative_to)

		return float(value)

	@StateProperty(key='required-interval-factors', allowNone=False)
	def required_interval_factors(self) -> set[int | float]:
		"""
		The interval must be a multiple of all the specified factors.
		Default is `{1}` to allow for any integer interval.

		Note: This is currently experimental
		"""
		return self._required_interval_factors

	@required_interval_factors.setter
	def required_interval_factors(self, value: set[int | float] | None):
		self._required_interval_factors = value

	@required_interval_factors.item_default
	def required_interval_factors(self) -> set[int | float]:
		return {1}

	@required_interval_factors.decode
	def required_interval_factors(self, value: list | tuple | str | int | float) -> set[int | float]:
		if isinstance(value, (list, tuple)):
			return set(value)
		if isinstance(value, str):
			return set(float(v) for v in value.split(','))
		return {value}

	@StateProperty(key='excluded-interval-factors', allowNone=False)
	def excluded_interval_factors(self) -> set[int | float]:
		"""
		The interval must not be a multiple of any of the specified factors.
		Default is `{}` to allow for any interval.
		"""
		return self._excluded_interval_factors

	@excluded_interval_factors.setter
	def excluded_interval_factors(self, value: set[int | float] | None):
		self._excluded_interval_factors = value

	@excluded_interval_factors.item_default
	def excluded_interval_factors(self) -> set[int | float]:
		return set()

	@excluded_interval_factors.decode
	def excluded_interval_factors(self, value: list | tuple | str | int | float) -> set[int | float]:
		if isinstance(value, (list, tuple)):
			return set(value)
		if isinstance(value, str):
			return set(float(v) for v in value.split(','))
		return {value}

	@StateProperty(key='included-interval-factors', allowNone=False)
	def included_interval_factors(self) -> set[int | float]:
		"""
		The interval must be a multiple of at least one of the specified factors.
		Default is `{}` to allow for any interval.
		"""
		return self._included_interval_factors

	@included_interval_factors.setter
	def included_interval_factors(self, value: set[int | float] | None):
		self._included_interval_factors = value

	@included_interval_factors.item_default
	def included_interval_factors(self) -> set[int | float]:
		return set()

	@included_interval_factors.decode
	def included_interval_factors(self, value: list | tuple | str | int | float) -> set[int | float]:
		if isinstance(value, (list, tuple)):
			return set(value)
		if isinstance(value, str):
			return set(float(v) for v in value.split(','))
		return {value}

	# A `.levity` file gives a plain number here, and the setter stores it as
	# given, so the getter returns int or float as often as a Measurement.
	# Without them in the return type the check in StateProperty.existing()
	# raised the second time a gauge's state was set, which aborted the load.
	@StateProperty(key='interval', allowNone=False)
	def usr_interval(self) -> Measurement | int | float | Unset:
		"""
		The interval between graduations.

		If an interval is provided by the configuration and has the correct factors, it will be used.
		Otherwise, the nearest allowed interval will be used.
		"""
		return self._usr_interval

	@usr_interval.setter
	def usr_interval(self, value: Measurement | Unset):
		self._usr_interval = value

	@usr_interval.item_default
	def usr_interval(self) -> GaugeValue:

		value_class = self.gauge.valueClass

		value_range = self.gauge.range.rounded_range
		if not issubclass(value_class, Percentage):
			if value_range <= 10:
				if self.tick_type is Graduations.Type.Major:
					return value_class(1)
				elif self.tick_type is Graduations.Type.Minor:
					return value_class(0.5)
				elif self.tick_type is Graduations.Type.Micro:
					return value_class(0.1)
		else:
			if value_range <= 0.1:
				if self.tick_type is Graduations.Type.Major:
					return value_class(0.01)
				elif self.tick_type is Graduations.Type.Minor:
					return value_class(0.005)
				elif self.tick_type is Graduations.Type.Micro:
					return value_class(0.001)

		if self.tick_type == Graduations.Type.Major:
			if issubclass(value_class, Percentage):
				return value_class(0.1)
			return value_class(10)
		elif self.tick_type == Graduations.Type.Minor:
			if issubclass(value_class, Percentage):
				return value_class(0.05)
			return value_class(5)
		elif self.tick_type == Graduations.Type.Micro:
			if issubclass(value_class, Percentage):
				return value_class(0.01)
			return value_class(1)

	@usr_interval.decode
	def usr_interval(self, value: str | int | float | Measurement | Unset) -> Measurement | Unset:
		value = decode_measurement(value, self.gauge.valueClass)
		if isinstance(value, self.gauge.valueClass):
			return value
		else:
			try:
				return self.gauge.valueClass(float(value))
			except ValueError:
				pass
		return Unset

	@property
	def usr_interval_deg(self) -> Angle | Unset:
		gauge_angle_range = self.gauge.endAngle - self.gauge.startAngle

		if (interval := getattr(self, '_usr_interval', Unset)) is not Unset:
			pass
		elif (count := getattr(self, '_usr_count', Unset)) is not Unset:
			interval = self.gauge.range.roudend_range / count
		elif spacing := self.spacing_deg is not Unset:
			interval = spacing
		else:
			return Unset

		if isinstance(interval, self.gauge.valueClass | int | float):
			if not isinstance(interval, self.gauge.valueClass):
				interval_val = self.gauge.valueClass(interval)
			else:
				interval_val = interval
			interval_deg = float(self.gauge.range.roundend_range / interval_val) * gauge_angle_range
			return Angle(interval_deg, 'deg')
		elif isinstance(interval, Percentage | RelativeFloat):
			interval_px = self.width_px * interval
			interval_deg = float(gauge_angle_range * interval_px / self.gauge.radius)
			return Angle(interval_deg)
		elif isinstance(interval, Length):
			interval_px = size_px(interval, self.gauge.baseWidth)
			interval_deg = float(gauge_angle_range * interval_px / self.gauge.radius)
			return Angle(interval_deg)
		elif isinstance(interval, Angle):
			return interval
		return Unset

	@cached_property
	def interval(self) -> int | float:
		if self.enabled:
			return self.determine_interval()
		return self.gauge.range.rounded_range

	@property
	def interval_degree(self) -> Angle:
		interval = float(self.interval)
		gauge_angle_range = float(self.gauge.endAngle - self.gauge.startAngle)
		rounded_range = float(self.gauge.range.rounded_range)
		return Angle(float(interval / rounded_range * gauge_angle_range))

	@StateProperty(key='min-interval')
	def usr_min_interval(self) -> int | float:
		"""
		The minimum interval between graduations.
		"""
		return self._usr_min_interval

	@usr_min_interval.setter
	def usr_min_interval(self, value: int | float):
		self._usr_min_interval = value

	@usr_min_interval.item_default
	def usr_min_interval(self) -> float:
		return self._usr_min_interval

	@property
	def min_interval(self) -> Measurement | Unset:

		gauge_angle_range = self.gauge.endAngle - self.gauge.startAngle
		ValueClass = self.gauge.valueClass

		if (min_interval := getattr(self, '_usr_min_interval', Unset)) is not Unset:
			min_interval = ValueClass(min_interval)
		elif (count := getattr(self, '_usr_max_count', Unset)) is not Unset:
			min_interval = ValueClass(float(self.gauge.range.roudend_range) / count)
		elif (spacing := getattr(self, '_usr_min_spacing', Unset)) is not Unset:
			min_interval = ValueClass(float(self.gauge.range.roundend_range / spacing) * gauge_angle_range)
		else:
			min_interval = self._min_interval

		if isinstance(min_interval, self.gauge.valueClass | int | float):
			if not isinstance(min_interval, self.gauge.valueClass):
				min_interval = self.gauge.valueClass(min_interval)
			return min_interval
		elif isinstance(min_interval, Percentage | RelativeFloat):
			min_interval_px = self.width_px * min_interval
			min_interval_deg = float(self.gauge.range.roundend_range * min_interval_px / self.gauge.radius)
			return self.gauge.valueClass(max(min_interval_deg, self._min_interval))
		elif isinstance(min_interval, Length):
			min_interval_px = size_px(min_interval, self.gauge.baseWidth)
			min_interval_deg = float(self.gauge.range.roundend_range * min_interval_px / self.gauge.radius)
			return self.gauge.valueClass(max(min_interval_deg, self._min_interval))
		elif isinstance(min_interval, Angle):
			return self.gauge.valueClass(max(min_interval, self._min_interval))
		return self.gauge.valueClass(max(min_interval, self._min_interval))

	@property
	def max_interval(self) -> Measurement | Unset:
		gauge_angle_range = self.gauge.endAngle - self.gauge.startAngle

		if (max_interval := getattr(self, '_usr_max_interval', Unset)) is not Unset:
			pass
		elif (count := getattr(self, '_usr_min_count', Unset)) is not Unset:
			max_interval = self.gauge.range.roudend_range / count
		elif (spacing := getattr(self, '_usr_max_spacing', Unset)) is not Unset:
			max_interval = float(self.gauge.range.roundend_range / spacing) * gauge_angle_range
		else:
			max_interval = self.gauge.range.rounded_range

		if isinstance(max_interval, self.gauge.valueClass | int | float):
			if not isinstance(max_interval, self.gauge.valueClass):
				max_interval = self.gauge.valueClass(max_interval)
			return max_interval
		elif isinstance(max_interval, Percentage | RelativeFloat):
			max_interval_px = self.width_px * max_interval
			max_interval_deg = float(self.gauge.range.roundend_range * max_interval_px / self.gauge.radius)
			return self.gauge.valueClass(max(max_interval_deg, self._min_interval))
		elif isinstance(max_interval, Length):
			max_interval_px = size_px(max_interval, self.gauge.baseWidth)
			max_interval_deg = float(self.gauge.range.roundend_range * max_interval_px / self.gauge.radius)
			return self.gauge.valueClass(max(max_interval_deg, self._min_interval))
		elif isinstance(max_interval, Angle):
			return self.gauge.valueClass(max(max_interval, self._min_interval))
		return self.gauge.valueClass(max(max_interval, self._min_interval))

	@property
	def _min_interval(self) -> GaugeValue:
		"""
		The minimum interval between graduations given that allows
		for the ticks to be at least one width apart.
		"""
		min_spacing_degrees = self.min_spacing_deg
		gauge_value_range = self.gauge.range.rounded_range
		if isinstance(gauge_value_range, Percentage):
			gauge_value_range = float(gauge_value_range)
		gauge_angle_range = self.gauge.endAngle - self.gauge.startAngle
		value = gauge_value_range / (gauge_angle_range / min_spacing_degrees)
		return self.gauge.valueClass(value)

	@StateProperty(key='min-spacing', default=1.0, allowNone=False)
	def min_spacing(self) -> Angle | Length | Percentage:
		"""
		The minimum arc length spacing between graduations.
		All floats and percentages are interpreted as a fraction of the tick-width.
		"""
		return self._min_spacing

	@min_spacing.setter
	def min_spacing(self, value: float):
		self._min_spacing = value

	@min_spacing.decode
	def min_spacing(self, value: str | int | float) -> Angle | Length | Percentage:
		match value:
			case float(value):
				return Percentage(value)
			case int(value):
				return Angle(value)
			case str(value):
				value = parseSize(value, DimensionType.width)
				return value
			case _:
				raise ValueError(f'Invalid value for min-spacing: {value!r}')

	@property
	def spacing_deg(self) -> Angle | Unset:
		"""
		The spacing between graduations in degrees.
		Returns
		-------
		Angle
		"""

		if (usr_spacing := getattr(self, '_spacing', Unset)) is Unset:
			return usr_spacing

		radius = self.gauge.radius - self.length_px

		return self.gauge.value_to_angle_degrees(
			usr_spacing,
			radius_px=radius,
			relative_px=self.width_px,
		)

	@property
	def min_spacing_deg(self) -> Angle:
		"""
		The minimum spacing between graduations in degrees.
		Returns
		-------
		Angle
		"""
		if (usr_spacing := getattr(self, '_min_spacing', Unset)) is Unset:
			return usr_spacing

		radius = self.gauge.radius - self.length_px
		tick_width = self.width_px * 2
		arc_length_px = float(radius * self.gauge.fullAngle / 180 * pi)

		tick_gauge_coverage = tick_width / arc_length_px

		return Angle(self.gauge.fullAngle * tick_gauge_coverage)

	@property
	def min_spacing_val(self) -> float:
		return

	@StateProperty(key='max-spacing', default=None, allowNone=False)
	def max_spacing(self) -> float:
		"""
		The maximum arc length/degree spacing between graduations.
		All floats and percentages are interpreted as a fraction of the tick-width.
		"""
		return self._max_spacing

	@property
	def angle_range(self) -> float:
		# A disabled parent has count 0 and draws nothing, so its children
		# span the whole range, as determine_interval already assumes.
		if self.super_grad is None or not self.super_grad.count:
			return self.gauge.fullAngle
		else:
			return self.super_grad.angle_range / self.super_grad.count

	@property
	def min_interval_deg(self) -> Angle | Unset:
		if (min_interval := getattr(self, '_min_interval', Unset)) is not Unset:
			pass
		elif (max_usr_count := getattr(self, '_max_usr_count', Unset)) is not Unset:
			min_interval = self.gauge.range.rounded_range / max_usr_count
		elif max_spacing := getattr(self, '_max_spacing', Unset) is not Unset:
			min_interval = max_spacing

		return Unset

	@property
	def count(self):
		if self.enabled:
			interval = self.interval
			count = self.step_count(interval) + 1
			if count <= 1 and self.tick_type is Graduations.Type.Major:
				return 2
			return count
		return 0

	@property
	def startAngle(self):
		return self.gauge.startAngle - 90

	@property
	def compatible_intervals(self) -> set[float]:
		gauge = self.gauge
		range_value = gauge.range.rounded_range if self.tick_type is Graduations.Type.Major else self.super_grad.interval
		if isinstance(range_value, Percentage):
			range_value = float(range_value) * 100

		# A range that is NaN, infinite or zero has no meaningful factors, and
		# both of the things below go badly wrong on one: `int(NaN)` raises,
		# and the scaling loop never terminates for 0 because 0 * 10 is still
		# 0. This happens legitimately during construction, before a gauge's
		# range has resolved - so yield a single unit interval and let the
		# real one be computed once there is a range to compute it from.
		if not isfinite(range_value) or range_value <= 0:
			return {1.0}

		multiplier = 1
		while range_value <= 1:
			multiplier *= 10
			range_value *= 10

		include_interval_factors = self.included_interval_factors
		require_interval_factors = self.required_interval_factors
		exclude_interval_factors = self.excluded_interval_factors

		factors_list = factors(int(range_value))
		compatible_intervals = set()
		while not compatible_intervals:
			compatible_intervals = filter_factors(
				factors_list,
				included_factors=include_interval_factors,
				required_factors=require_interval_factors,
				excluded_factors=exclude_interval_factors
			)

			if not compatible_intervals:
				include_interval_factors = None
				require_interval_factors = None
			if not compatible_intervals:
				excluded_factors = None

		val_cls = self.gauge.valueClass
		if issubclass(val_cls, Percentage):
			compatible_intervals = {interval/100 for interval in compatible_intervals}

		if multiplier != 1:
			compatible_intervals = {interval / multiplier for interval in compatible_intervals}

		return compatible_intervals

	def step_count(self, interval=None) -> int:
		"""Whole intervals in the rounded range. Counted with a tolerance: 0.6 / 0.2 is 2.9999999999999996."""
		interval = float(self.interval if interval is None else interval)
		if not interval:
			return 0
		return floor(round(float(self.gauge.range.rounded_range) / interval, 9))

	def value_at(self, index: int) -> GaugeValue:
		"""The tick value at `index`, rounded so every caller gets the same float for the same tick."""
		return self.gauge.valueClass(round(float(self.gauge.range.rounded_min) + index * float(self.interval), 9))

	@property
	def tick_values(self) -> set[GaugeValue]:

		interval = self.interval
		gauge = self.gauge
		value_class = gauge.valueClass
		gauge_range = gauge.range

		if (super_grad := self.super_grad) is not None:
			super_tick_values = super_grad.tick_values
		else:
			super_tick_values = set()
		count = self.step_count(interval)
		# Index-based, through value_at, so a tick built from its index always
		# finds itself here. arange's float stepping and the index arithmetic
		# disagreed in the last digit (0.6000000000000001 against 0.6) and the
		# label for that tick raised KeyError.
		values = set(self.value_at(i) for i in range(count + 1)) - super_tick_values
		if self.tick_type is not Graduations.Type.Major:
			values.discard(self.value_at(count))
		return values

	def interval_to_deg(self, interval: GaugeValue) -> Angle:
		return self.gauge.value_to_angle_degrees(interval, self.gauge.radius)

	def determine_interval(self) -> GaugeValue:

		gauge = self.gauge

		# A minor tick subdivides a major one, and a micro subdivides a minor -
		# so each asks its parent for a count. `count` is 0 for a *disabled*
		# graduation, and dividing by it raised ZeroDivisionError out of
		# WeatherUnits' __truediv__, taking the whole gauge down. Disabling
		# major while leaving minor on is the documented way to get a plain
		# ring (docs: "major/minor/micro: {enabled: false}"), so this crashed
		# on exactly the configuration the design notes recommend.
		match self.tick_type:
			case Graduations.Type.Major:
				return self._determine_interval()
			case Graduations.Type.Minor:
				parent = gauge.majorDivisions
				if not parent.count:
					return gauge.range.rounded_range
				return self._determine_interval(
					range_value=gauge.range.rounded_range / parent.count,
					gauge_max_angle_deg=parent.angle_range / parent.count,
				)

			case Graduations.Type.Micro:
				parent = gauge.minorDivisions
				if not parent.count:
					return gauge.range.rounded_range
				return self._determine_interval(
					range_value=gauge.range.rounded_range / parent.count,
					gauge_max_angle_deg=parent.angle_range / parent.count,
				)
			case _:
				raise ValueError(f'Invalid tick type: {self.tick_type}')

	def _determine_interval(
		self,
		range_value: float | int = None,
		gauge_max_angle_deg: float | int = None,
		min_interval: float | int = None,
		max_interval: float | int = None,
		usr_interval: float | int = None,
		usr_count: int = None,
		usr_spacing_deg: float | int = None,
	) -> GaugeValue:

		# TODO: If the user has configured an interval, and no min/max interval or count, then use
		# the user's interval to determine the range.  This will have to be part of Gauge.GaugeRange

		gauge = self.gauge

		range_value = float(gauge.range.rounded_range) if range_value is None else range_value

		gauge_max_angle_deg = gauge.startAngle if gauge_max_angle_deg is None else gauge_max_angle_deg

		min_interval = self.min_interval if min_interval is None else min_interval
		max_interval = self.max_interval if max_interval is None else max_interval

		usr_interval = self.usr_interval if usr_interval is None else usr_interval
		usr_count = self.usr_count if usr_count is None else usr_count

		usr_spacing_deg = self.spacing_deg if usr_spacing_deg is None else usr_spacing_deg

		preferred_intervals = []

		if usr_count not in {Unset, None}:
			if usr_interval is None or self._state_item_sources[type(self).usr_interval] is SourceType.UserConfig:
				usr_interval = range_value / ((usr_count - 1) or 1)
		else:
			_min_count = self.min_usr_count or 2 if self.tick_type == Graduations.Type.Major else 1
			_max_count = self.max_usr_count or self.gauge.range.rounded_range

			# TODO: Finish the logic to use min and max count to add all intervals between min and max
			# to the preferred intervals list.  Then, if the user has specified an interval, add that
			# to the list.
			#
			# if self._state_item_sources[type(self).usr_interval] is not SourceType.UserConfig:
			# ...

			# if _min_count == 1 and _max_count == self.gauge.range.rounded_range:
			# 	pass
			# else:
			# 	preferred_intervals.append(range_value / _max_count)

		if usr_interval is not None:
			preferred_intervals.append(usr_interval)

		if usr_spacing_deg is not Unset:
			preferred_intervals.append(usr_spacing_deg / gauge_max_angle_deg * range_value)

		compatible_intervals = self.compatible_intervals

		# Warn only when the interval cannot tile the range. It used to warn when
		# it could (and the interval merely missed the filtered factor set), which
		# rejected a valid `interval: 1` on 28-32. Major only: minor and micro
		# intervals tile their parent's span and are often not the user's.
		if self.tick_type is Graduations.Type.Major and self._state_item_sources.get(Graduations.usr_interval, SourceType.ItemDefault) is SourceType.UserConfig:
			# An interval wider than the range is replaced below, so it is not worth a warning.
			if usr_interval not in compatible_intervals and float(usr_interval) <= float(range_value) and not _isWholeSteps(range_value, usr_interval):
				gauge_repr = f'Gauge.{gauge.valueClass.name.replace(" ", "")}(min={gauge.range.min}, max={gauge.range.max})'
				log.warning(f'User specified interval: {usr_interval} for {gauge_repr} is not compatible with the gauge range {gauge.range}')

		unfiltered_intervals = sorted(compatible_intervals)
		compatible_intervals = [
			self.gauge.valueClass(i) for i in unfiltered_intervals
			if float(min_interval) <= i <= float(max_interval)
		]

		# The min/max window can exclude every factor - a pressure gauge
		# spanning 27-31 inHg has few factors to choose from, and all of them
		# can fall outside it. The `min()` further down then raises on an
		# empty sequence. Preferring a badly-sized interval to no gauge at
		# all, fall back to the unfiltered set.
		if not compatible_intervals:
			compatible_intervals = [self.gauge.valueClass(i) for i in unfiltered_intervals]

		# An interval wider than the range cannot place a second tick. The built-in
		# default asks for 1 on any range up to 10, so a 0 to 0.6 gauge got a single
		# tick and no labels. Drop such asks and take the interval that gives about
		# five steps instead, as 0 to 0.5 already did.
		if not issubclass(gauge.valueClass, Percentage) and float(range_value) > 0:
			span = float(range_value)
			if any(float(i) > span * (1 + 1e-9) for i in preferred_intervals):
				preferred_intervals = [i for i in preferred_intervals if float(i) <= span * (1 + 1e-9)]
				if not preferred_intervals:
					usr_interval = min(
						compatible_intervals,
						key=lambda i: abs(span / float(i) - 5) if float(i) > 0 else inf,
					)
					preferred_intervals = [usr_interval]

		if issubclass(gauge.valueClass, Percentage):
			preferred_intervals = [abs(i) if isinstance(i, gauge.valueClass) else gauge.valueClass(abs(i) / 100) for i in preferred_intervals]

		interval_candidates = []

		# for each preferred interval, find the closest compatible interval
		for preferred_interval in preferred_intervals:
			if preferred_interval in compatible_intervals:
				interval_candidates.append(preferred_interval)
				continue
			elif float(range_value / preferred_interval).is_integer():
				interval_candidates.append(preferred_interval)
				continue
			preferred_interval = float(preferred_interval)
			closest_interval = min(compatible_intervals, key=lambda i: abs(i - preferred_interval))
			interval_candidates.append(closest_interval)

		if len(interval_candidates) > 1:
			return gauge.valueClass(min(interval_candidates, key=lambda interval: abs(interval - usr_interval)))
		elif len(interval_candidates) == 1:
			return gauge.valueClass(interval_candidates[0])
		else:
			closest_interval = min(compatible_intervals, key=lambda i: abs(i - usr_interval))
			if not isinstance(closest_interval, gauge.valueClass):
				closest_interval = gauge.valueClass(closest_interval)
			return closest_interval

	def _get_color_value(self) -> Number:
		return self.gauge.value

	def _set_fill_brush(self, color: Color):
		pen = self.surface.pen
		for tick in self.surface.ticks:
			tick.setPen(pen)

	def _map_gradient(self, gradient: Gradient) -> QGradient:
		return self.gauge.map_gradient_to(gradient, self.surface)


@DebugPaint
class Tick(GaugePathItem):
	_index: float
	_center: QPointF
	_radius: float
	_properties: Graduations
	_offsetAngle: float
	_label: 'GaugeTickText' = None
	startPoint: QPointF
	endPoint: QPointF

	@cached_property
	def _sub_ticks(self) -> list['SubTick']:
		return []

	def __init__(self, gauge: 'Gauge', surface: 'TickSurface', index: float):
		self._index = index
		super(Tick, self).__init__(gauge)
		self.setParentItem(surface)

		pen = QPen(self.gauge.pen.color())
		pen.setCapStyle(Qt.RoundCap)
		self.setPen(pen)
		self.rebuild()
		self.setAcceptedMouseButtons(Qt.LeftButton)

	def _debug_paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget):
		super().paint(painter, option, widget)
		zero = QPoint(0, 0)
		addCrosshair(painter, pos=zero, color=self._debug_paint_color)

	def remove(self):
		for subtick in self._sub_ticks:
			subtick.remove()
		self._sub_ticks.clear()
		if self.label is not None:
			self.label.remove()
		super(Tick, self).remove()

	def mousePressEvent(self, event):
		event.accept()
		print(event)

	def mouseMoveEvent(self, event):
		print(event.pos())

	def refresh(self):
		pen = self.parentItem().pen
		self.setPen(pen)
		clearCacheAttr(self, 'angle', 'value')
		self.draw()

	def rebuild(self):
		self.refresh()
		# self.rebuild_sub_ticks()

	def rebuild_sub_ticks(self):

		tick_count = self.sub_tick_count
		existing = self._sub_ticks[:]

		if tick_count == 0:
			return

		self._sub_ticks.clear()

		for i in range(self.sub_tick_count):
			if existing:
				sub_tick = existing.pop(0)
				sub_tick.rebuild()
			else:
				sub_tick = SubTick(self, i)
			self._sub_ticks.append(sub_tick)

		for sub_tick in existing:
			sub_tick.remove()

	@cached_property
	def angle(self):
		return self.properties.startAngle + self._index * float(self.properties.interval_degree)

	@cached_property
	def value(self) -> GaugeValue:
		return self.properties.value_at(self._index)

	@property
	def index(self):
		return self._index

	@index.setter
	def index(self, value):
		self._index = value
		self.refresh()

	@property
	def sub_tick_spacing(self) -> float:
		return self.properties.sub_grad.spacing

	@property
	def sub_tick_count(self):

		# Prevent the last tick from having sub ticks
		if self._index == self.properties.count:
			# But only if there is no super tick
			if self.properties.super_grad is None:
				return 0

		try:
			return self.properties.sub_grad.count
		except AttributeError:
			return 0

	@property
	def radius(self):
		return self.gauge.radius

	@property
	def properties(self):
		return self.parentItem()._properties

	def draw(self):
		path = QPainterPath()
		# The dial's own track places the tick: a point on the rim and the outward
		# direction there, in the same polar arithmetic this used to do inline. A
		# bar's track answers the same two questions, so this is the whole of what
		# a tick needs from the display it is on.
		track = self.gauge.arc.track
		point = track.pointAtAngle(self.angle)
		outward = track.normalAtAngle(self.angle)
		length = self.properties.length_px

		start = end = point
		match self.properties.position:
			case DisplayPosition.Below | DisplayPosition.Inside:
				end = point - outward * length
			case DisplayPosition.Above | DisplayPosition.Outside:
				end = point + outward * length
			case DisplayPosition.Center | _:
				half = outward * (length / 2)
				start, end = point - half, point + half
				if length > 0:  # keeps the outermost as the end point
					start, end = end, start

		p1 = start
		self.startPoint = p1
		p2 = end
		self.endPoint = p2
		path.moveTo(p1)
		path.lineTo(p2)
		self.setPath(path)
		# width = self.pen().widthF()
		# rect = QRectF(x2, y2, width, length + self.pen().widthF())

	def setLabel(self, label: 'GaugeTickText'):
		self._label = label

	@property
	def label(self) -> 'GaugeTickText':
		return self._label

	@label.setter
	def label(self, label: 'GaugeTickText'):
		self._label = label


class SubTick(Tick):
	_superTick: Tick

	def __init__(self, superTick: Tick, index: float):
		self._superTick = superTick
		super(SubTick, self).__init__(superTick.gauge, superTick.parentItem(), index)

	@property
	def properties(self):
		return self._superTick.properties.sub_grad

	@property
	def angle(self):
		return self._superTick.angle + self._index * self.properties.spacing


@DebugPaint
class TickSurface(GaugeItem, SurfaceCentered):
	_properties: Graduations
	_ticks: list[Tick] = cached_property(lambda self: [])

	def __init__(self, gauge: 'Gauge', properties: Graduations, *args, **kwargs):
		self._gauge = gauge
		self._properties = properties
		self.scale = 1
		GaugeItem.__init__(self, gauge)
		self.rebuild()

	def _debug_paint(self, painter, option, widget):
		self._normal_paint(painter, option, widget)
		addCrosshair(painter, pos=self.boundingRect().center())

	def refresh(self):
		self.setPos(self.gauge.center)

		clearCacheAttr(self, 'tick_path')
		for tick in self._ticks:
			# try:
			tick.refresh()
			# except AttributeError:
			# 	pass

		self._properties.labels.refresh()

	def rebuild(self):
		self.setZValue(-1000)
		if not self.gauge.gaugeRect.isValid() or self.gauge.gaugeRect.width() < 10 or self.gauge.gaugeRect.height() < 10:
			return

		self.resetTransform()

		tick_count = self.count
		existing = self._ticks[:]

		if tick_count == 1:
			return

		self._ticks.clear()

		added = 0

		tick_values = self._properties.tick_values

		interval = self._properties.interval
		for i in range(self.count):
			if self._properties.value_at(i) not in tick_values:
				continue
			if existing:
				tick = existing.pop(0)
				tick.index = i
			else:
				tick = Tick(self.gauge, self, i)
				added += 1
			self._ticks.append(tick)

		len_existing = len(existing)
		for tick in existing:
			tick.remove()

		self._ticks.sort(key=lambda t: t.index)

		if self._properties.labels.enabled:
			self._properties.labels.rebuild()

		tick_type = self._properties.tick_type.name.lower()
		print(f'{self.gauge.parent.key}: total {tick_type} ticks: {len(self._ticks)}, added: {added}, removed: {len_existing}')

	@property
	def ticks(self) -> list[Tick]:
		return self._ticks

	@property
	def gauge(self) -> 'Gauge':
		return self._gauge

	@property
	def spacing(self) -> float:
		return self._properties.spacing

	@property
	def count(self) -> int:
		return self._properties.count

	@cached_property
	def tick_path(self) -> QPainterPath:
		p = QPainterPath()
		labels_enabled = self._properties.labels.enabled
		for tick in self.ticks:
			p = p.united(tick.mapToScene(tick.path()))
			if labels_enabled and (label := tick.label) is not None:
				p = p.united(label.mapToScene(label.path()))
		return self.mapFromScene(p)

	@property
	def pen(self) -> QPen:
		pen = QPen(self.gauge.pen)
		pen.setWidthF(self._properties.width_px)
		pen.setBrush(self._properties.fill_brush)
		return pen

	def update_color(self):
		for tick in self.ticks:
			tick.update_color()


class GaugeTickText(GaugeItem, AnnotationText):

	"""
	TODO
	----
	When the item is not rotated, the alignment should be center
	"""

	_rotated: bool = True
	_flipUpsideDown = (True, True)
	_scale: Optional[float] = None

	group: 'GaugeTickTextGroup'
	tick: 'Tick'

	def _apply_group_transform(self, transform: QTransform, x: float, y: float):
		pass

	def __init__(self, gauge, tick, group, *args, **kwargs):
		self.group = group
		self.tick = tick
		tick.label = self
		kwargs['gauge'] = gauge
		kwargs['value'] = group.source.value_at(tick.index)
		# group.size_group.addItem(self)
		self.set_formatting_func(group.format_value)
		kwargs['labelGroup'] = group
		super(GaugeTickText, self).__init__(*args, **kwargs)

	def _valueAccessor(self) -> str:
		value = self.tick.value
		return value

	def setTransform(self, matrix: PySide6.QtGui.QTransform, *args) -> None:
		super().setTransform(matrix, *args)
		self._bend()
		self._updateShape()

	def _updateShape(self):
		matrix = self.transform()
		scale_x = matrix.m11() * self.scale()
		scale_y = matrix.m22() * self.scale()
		scale_value = (self.scaleSelection(scale_x, scale_y) or 1)
		self.prepareGeometryChange()
		self._shape = outline_path(self.path(), self.group.offset_px / scale_value)

	_bendKey: Optional[tuple] = None
	_bending: bool = False
	_flatRect: Optional[QRectF] = None

	def _labelRotation(self) -> tuple[float, bool]:
		"""The item's final rotation, and whether it was flipped half a turn to stay legible."""
		# Always computed: a label refreshed after `rotate: false` must drop the
		# angle an earlier refresh gave it.
		rotation = self.tick.angle + 90 if self.rotated else 0
		# Text that would read upside down is flipped half a turn so it stays legible.
		# A margin keeps near-vertical radial labels (a few degrees past 90/270) as they are.
		flipped = 105 < rotation % 360 < 255
		if flipped:
			rotation += 180
		return rotation, flipped

	def _layoutSignature(self) -> tuple:
		# The curve depends on where the tick sits, which the base signature never reads.
		return super()._layoutSignature() + (self.group.curve, round(self.tick.angle, 3), round(hypot(*self.tick.startPoint.toTuple()), 2))

	def _bend(self) -> bool:
		"""
		Replace the flat outline with one bent along the dial, when `curve` asks for it.
		Returns True if the path changed. Builds from text and font, never from the
		current path, so an already bent path is never bent twice. Fitting reads the
		flat rect the base class built, so label size does not depend on the angle.
		"""
		mode = self.group.curve
		if mode is CurveMode.none or not self.rotated or not self.text:
			self._bendKey = None
			return False
		scale = self.transform().m11() or 1.0
		radius = hypot(self.pos().x(), self.pos().y())
		if radius < 1e-6:
			return False
		_, flipped = self._labelRotation()
		font = self.font()
		key = (mode, self.text, font.key(), round(scale, 4), flipped, round(self.tick.angle, 4), round(radius, 2))
		if key == self._bendKey:
			return False
		side = -1 if flipped else 1
		try:
			viewScale = self.scene().viewScale.x
		except AttributeError:
			viewScale = 1
		path = warp_path(self.text, font, scale, radius, side, mode, 0.25 / (viewScale or 1))
		self._bendKey = key
		self._bending = True
		try:
			self.setPath(path)
		finally:
			self._bending = False
		self._updateShape()
		return True

	@property
	def offset_relative_to(self) -> float:
		return self.group.textSize_px

	def position(self, display_position: DisplayPosition = None) -> QPointF:

		position = display_position or self.display_position

		# Labels placed relative to the arc: inside is toward the center (like Below),
		# outside is away from it (like Above).
		if position == DisplayPosition.Outside:
			position = DisplayPosition.Above
		elif position == DisplayPosition.Inside:
			position = DisplayPosition.Below

		if self.group.source.position in {DisplayPosition.Above, DisplayPosition.Outside}:
			position = position.opposite

		match position:
			case DisplayPosition.Below:
				value = self.tick.endPoint
			case DisplayPosition.Above:
				value = self.tick.startPoint
			case DisplayPosition.Center:
				value = self.tick.endPoint / 2 + self.tick.startPoint / 2
			case DisplayPosition.Left:
				value = min(self.tick.startPoint, self.tick.endPoint, key=lambda p: p.x())
			case DisplayPosition.Right:
				value = max(self.tick.startPoint, self.tick.endPoint, key=lambda p: p.x())
			case _:
				raise ValueError(f'Invalid position: {position}')
		# return self.transform().map(value)
		return value

	@property
	def display_position(self) -> DisplayPosition:
		if self.tick is self.surface.ticks[0]:
			return self.group.position_leading
		elif self.tick is self.surface.ticks[-1]:
			return self.group.position_trailing
		return self.group.position

	def setPath(self, path: QPainterPath):
		if not self._bending:
			# A fresh flat path: the next bend must rebuild.
			self._bendKey = None
			self._flatRect = path.boundingRect()
		self._shape = outline_path(path, self.group.offset_px)
		self._debug_paint_shape = QPainterPath(self._shape)
		super(GaugeTickText, self).setPath(path)

	_shape: QPainterPath = QPainterPath()

	def shape(self) -> QPainterPath:
		return QPainterPath(self._shape)

	def boundingRect(self) -> QRectF:
		return self._shape.boundingRect()

	def setPos(self, pos: QPointF):
		"""This method is overridden to ensure that the text is not placed overlapping arc or tick."""
		super(GaugeTickText, self).setPos(pos)
		angle = self.tick.angle

		direction = 1 if self.group.position in {DisplayPosition.Above, DisplayPosition.Outside} else -1
		direction = 1

		disp_pos = self.display_position
		match disp_pos:
			case DisplayPosition.Below:
				move_direction = radialPoint(QPointF(0, 0), -1 * direction, angle)
			case DisplayPosition.Above:
				move_direction = radialPoint(QPointF(0, 0), 1 * direction, angle)
			case DisplayPosition.Center:
				move_direction = QPointF(0, 1 * direction)
			case DisplayPosition.Left:
				move_direction = QPointF(1 * direction, 0)
			case DisplayPosition.Right:
				move_direction = QPointF(-1 * direction, 0)
			case _:
				move_direction = radialPoint(QPointF(0, 0), 1 * direction, angle)

		moved_count = 0

		max_travel_distance = int(ceil(sqrt(sum(i**2 for i in self.limitRect.size().toTuple()))))
		self.prepareGeometryChange()
		# self._shape = outline_path(self.path(), self.group.offset_px)

		arc = self.gauge.arc
		arc_weight = arc.pen().width() / 2
		if pos == self.tick.startPoint and self.tick.startPoint != self.tick.endPoint:
			self.moveBy(*(move_direction * arc_weight).toTuple())
		else:
			if arc_weight > abs(self.group.source.length_px):
				diff = arc_weight - abs(self.group.source.length_px)
				self.moveBy(*(move_direction * diff).toTuple())

		# self.moveBy(*(move_direction * self.offset).toTuple())

		def colliding(other_item) -> bool:
			other_scene_path = other_item.mapToScene(other_item.shape())
			own_scene_path = self.mapToScene(self.shape())
			return own_scene_path.intersects(other_scene_path)

		def clearCollisions(moved_count: int = 0):
			while (self.collidesWithItem(arc) or self.collidesWithItem(self.tick)) and moved_count < max_travel_distance:
				self.moveBy(move_direction.x(), move_direction.y())
				moved_count += 1

		clearCollisions()
		# The nudge above ran against the flat shape; run it again against the bent one.
		if self._bend():
			clearCollisions()

		# self.prepareGeometryChange()
		# self._shape = outline_path(self.path(), 5)

	_placedKey: Optional[tuple] = None
	_placedPos: Optional[QPointF] = None

	def _placementKey(self, target: QPointF) -> tuple:
		"""Everything `setPos` reads: this label, the arc and the tick it must clear, and where it aims."""
		tick = self.tick
		arc = self.gauge.arc
		return (
			target, self.path(), self.sceneTransform(), self.rotation(), self.scale(), self.group.offset_px, self.display_position,
			self.limitRect.size(), self.group.source.length_px, tick.angle, tick.startPoint, tick.endPoint,
			arc.path(), arc.pen().width(), arc.sceneTransform(), tick.path(), tick.pen().width(), tick.sceneTransform(),
		)

	@property
	def repeats_first_label(self) -> bool:
		"""True for the last label of a full-circle dial, which sits on top of the first.

		0 and 360 are the same point on a compass, so both would draw "N" in
		one place. Hiding the last one also keeps it out of the overlap
		measurement, which would otherwise find two labels at distance zero
		and thin the whole dial to fit them.
		"""
		ticks = self.surface.ticks
		return len(ticks) > 2 and self.tick is ticks[-1] and isclose(float(self.gauge.fullAngle) % 360, 0, abs_tol=1e-6) and float(self.gauge.fullAngle) > 0

	def refresh(self):
		if self.repeats_first_label:
			self.hide()
			return
		if (interval := self.group.label_step) > 1 and self.tick.index % interval and not (self.is_last_tick and self.group._auto_step > 1 and self.group._keep_last):
			self.hide()
			return
		else:
			self.show()

		self.setRotation(self._labelRotation()[0])

		super(GaugeTickText, self).refresh()
		target = self.position()
		key = self._placementKey(target)
		# setPos() nudges the label off the arc and tick one pixel at a time, which
		# costs most of a gauge refresh. It is a function of the things in the key;
		# if none moved since the last placement and the label is still where that
		# placement left it, the answer is the position it already has.
		if key != self._placedKey or self.pos() != self._placedPos:
			self.setPos(target)
			self._placedKey = self._placementKey(target)
			self._placedPos = self.pos()
		if self.is_endcap:
			self.setToolTip("Endcap")

	@property
	def allowedWidth(self) -> float:

		radius = self.gauge.safe_radius if self.group.position == DisplayPosition.Below else self.gauge.exterior_safe_radius
		interval = self.group.source.interval

		arch_length_px = float(radius * self.gauge.fullAngle / 180 * pi)

		interval_arch_coverage = float(interval / self.gauge.range.rounded_range)

		return arch_length_px * interval_arch_coverage

	@property
	def rotated(self):
		if self.tick is self.surface.ticks[0]:
			return self.group.rotation_leading
		if self.tick is self.surface.ticks[-1]:
			return self.group.rotation_trailing
		return self.group.rotation

	@property
	def alignment(self) -> Alignment:
		if self.tick is self.surface.ticks[0]:
			return Alignment(self.group.align_leading)
		if self.tick is self.surface.ticks[-1]:
			return Alignment(self.group.align_trailing)
		return self.group.alignment

	@alignment.setter
	def alignment(self, value: Alignment):
		pass

	def getTextScale(self, textRect: QRectF = None, limitRect: QRectF = None) -> float:
		textRect = textRect or self._textRect or self._update_path()
		limitRect = limitRect or self.limitRect

		width = (textRect.width()) or 1
		height = (textRect.height()) or 1

		wScale = limitRect.width() / width
		hScale = limitRect.height() / height
		return round(self.scaleSelection(wScale, hScale), 4)

	def scaleSelection(self, x, y):
		return y

	@property
	def is_last_tick(self) -> bool:
		return self.tick is self.surface.ticks[-1]

	@property
	def is_endcap(self) -> bool:
		return self.tick is self.surface.ticks[0] or self.tick is self.surface.ticks[-1]


class GaugeTickTextGroup(AnnotationLabels[GaugeTickText]):

	__defaults__ = {
		'height': Size.Height(0.15, relative=True),
		'position': DisplayPosition.Below,
		'offset': Size.Height(0.1, relative=True),
	}

	font_scale: float = cached_property(lambda self: 1.0)
	radius_scale: float = cached_property(lambda self: 1.0)

	surface: 'TickSurface'
	source: 'Graduations'

	def shape(self) -> QPainterPath:
		path = QPainterPath()
		for label in self:
			sub_path = self.surface.mapFromItem(label, label.path())
			path.addPath(sub_path)
		return path

	@property
	def fill_brush(self) -> Dict[Number, QBrush]:
		values = self._ticks.tick_values
		if (gradient := self.gradient) is not None:
			return {value: QBrush(gradient.get_color_for_value(value).QColor) for value in values}
		return {value: QBrush(self.color.QColor) for value in values}

	@property
	def text_size_relative_to(self) -> Length | Size.Height | float:
		return self.gauge.radius

	@property
	def offset_relative_to(self) -> Length | Dimension:
		return self.source.length_px or self.textSize_px

	# The class-level ask every tick label starts from. Named rather than
	# inlined so `format_value` can merge the user's `format:` over it.
	#
	# Tick labels drop the WORD unit ('inHg', 'mph'): said once, by the unit
	# label, rather than on every tick. Symbols ('°', '%') stay glued to the
	# number, for the reason given on GaugeValueLabel's defaults.
	#
	# `compact=True` asks WeatherUnits for the unit's own *label* convention
	# rather than its reading convention. A dial face is not a readout: inHg
	# reads 29.92 but its ticks are 28, 29, 30, and hPa reads 1013.2 but its
	# ticks are 1000, 1010, 1020. That difference belongs to the unit, so it
	# is asked for here rather than spelled out per gauge - which is also why
	# it follows a unit change instead of having to be re-stated.
	_tickFormatDefaults: Mapping[str, Any] = {'compact': True, 'show_unit': False}

	@StateProperty(key='format', default=None, allowNone=False)
	def format_spec(self) -> str | dict:
		return getattr(self, '_format_spec', None)

	@format_spec.setter
	def format_spec(self, value: str | dict):
		self._format_spec = value

	def _spacingPrecision(self) -> int | None:
		"""How many decimals the tick values need, or None if they cannot be read.

		The decimals on a tick label follow the tick spacing: spacing 1 shows
		`28`, spacing 0.1 shows `0.1`, spacing 0.05 shows `29.95`. The answer
		is the smallest d for which every tick value is exact at d places, so
		it is never more than the scale needs and never less than the labels
		need to stay exact. Read off the graduations themselves rather than
		the nominal interval, so a range that is not an exact multiple of its
		interval still labels correctly.

		The test is "exact", not "still distinct": 0.25 steps on 29-30 stay
		distinct at one decimal (29.2 29.5 29.8) while two of them are wrong.

		The comparison has a tolerance because tick values are built by
		repeated float addition. 29.95 arrives as 29.950000000000003, and an
		exact test would push the answer to 3.
		"""
		try:
			values = [float(v) for v in self._ticks.tick_values]
		except Exception:  # noqa: BLE001 - a label rule must never blank the dial
			return None
		if not values:
			return None
		for places in range(0, 8):
			if all(isclose(v, round(v, places), rel_tol=0, abs_tol=1e-9 * max(1.0, abs(v))) for v in values):
				return places
		return None

	_COMPASS = {
		'compass': ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'),
		'compass-16': ('N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'),
	}

	@StateProperty(key='text', default=None, allowNone=True)
	def text_map(self) -> Optional[str | dict]:
		"""Words in place of numbers: ``{0: E, 100: F}``, ``compass`` or ``compass-16``."""
		return getattr(self, '_text_map', None)

	@text_map.setter
	def text_map(self, value):
		self._text_map = value

	@text_map.decode
	def text_map(self, value):
		if value is None:
			return None
		if isinstance(value, str):
			if value.strip().lower() in self._COMPASS:
				return value.strip().lower()
			log.warning(f'Gauge {gaugeKeyName(self.gauge)} ignored label text {value!r}: use a mapping, compass or compass-16')
			return None
		if not isinstance(value, Mapping):
			log.warning(f'Gauge {gaugeKeyName(self.gauge)} ignored label text {value!r}: expected a mapping or compass')
			return None
		clean = {}
		for key, word in value.items():
			try:
				float(key)
			except (TypeError, ValueError):
				log.warning(f'Gauge {gaugeKeyName(self.gauge)} label text skipped key {key!r}: not a number')
				continue
			clean[key] = str(word)
		return clean

	@text_map.encode
	def text_map(self, value):
		return dict(value) if isinstance(value, Mapping) else value

	@StateProperty(key='sign', default=False, allowNone=False)
	def sign(self) -> bool:
		"""Put a plus in front of positive labels (``+5``)."""
		return getattr(self, '_sign', False)

	@sign.setter
	def sign(self, value: bool):
		self._sign = bool(value)

	@staticmethod
	def _labelNumber(value) -> float:
		"""The number a tick shows. A Percentage floats as a fraction (50 % is 0.5), the label says 50."""
		number = float(value)
		return number * 100 if isinstance(value, Percentage) else number

	def _mappedText(self, value) -> Optional[str]:
		spec = self.text_map
		if spec is None:
			return None
		try:
			number = self._labelNumber(value)
		except (TypeError, ValueError):
			return None
		if isinstance(spec, str):
			names = self._COMPASS[spec]
			width = 360 / len(names)
			return names[int(((number % 360) + width / 2) // width) % len(names)]
		for key, word in spec.items():
			k = float(key)
			if abs(number - k) <= 1e-6 * max(1.0, abs(k)):
				return word
		return None

	def format_value(self, value: Measurement) -> str:
		mapped = self._mappedText(value)
		if mapped is not None:
			return mapped
		text = self._format_number(value)
		if self.sign:
			try:
				if self._labelNumber(value) > 0 and not text.startswith('+'):
					return '+' + text
			except (TypeError, ValueError):
				pass
		return text

	def _format_number(self, value: Measurement) -> str:
		# Merged rather than replaced, so `format: {precision: 0}` does not
		# bring the unit back on every tick. A user's format is an addition to
		# the default, never a replacement for it: dropping `compact` here
		# would put a padded reading back on every tick, and dropping
		# `show_unit` would say 'inHg' twenty times around one dial.
		spec = self.format_spec
		if spec is None or isinstance(spec, Mapping):
			# The item_default is the base; the user's `format:` merges over
			# it. Both sides are Mappings, so a dict ask composes with the
			# class's compact ask instead of replacing it.
			spec = {**self._tickFormatDefaults, **(spec or {})}
			# The tick spacing sets the decimals, unless the caller has already
			# said what precision they want: an explicit `precision:` in the
			# user's format: is their decision, not ours.
			#
			# The spacing replaces the unit's compact precision rather than
			# flooring it. Compact only drops padding, so rain in inches
			# (compact precision 2) with 0.1 ticks would otherwise read 0.10.
			# Where the spacing needs decimals the zeros stay, so a scale
			# reads 29.90 29.95 30.00, not 29.9 29.95 30.
			if 'precision' not in spec and (places := self._spacingPrecision()) is not None:
				spec = {**spec, 'precision': places}
				if places:
					spec['trailing_zeros'] = 'precision'
		if isinstance(value, Measurement):
			try:
				match spec:
					case str():
						return value.__format__(spec)
					case dict():
						return value.__format__('', **spec)
			except Exception as e:  # noqa: BLE001 - a bad spec must not blank the dial
				log.warning(f'Gauge {gaugeKeyName(self.gauge)} tick label format {spec!r} failed: {e!r}')
		elif value is None:
			return '⋯'
		return str(value)

	@cached_property
	def size_group(self) -> SizeGroup:
		tick_type = self._ticks.tick_type.name.lower()
		return self.gauge.localGroup.getAttrGroup(f'local.{tick_type}-textSize', matchAll=True)

	def onAxisTransform(self, axis: Axis):
		print('onAxisTransform', axis)

	def onDataChange(self, axis: Axis):
		print('onDataChange', axis)

	_auto_step: int = 1
	_keep_last: bool = True
	_measuring: bool = False

	@property
	def label_step(self) -> int:
		"""Show every n-th label: the configured `every`, or a step chosen to keep labels apart."""
		if self._measuring:
			return 1
		return max(self.interval, self._auto_step)

	def refresh(self):
		# Place every label first, then pick the thinning step from where they landed.
		self._measuring = True
		try:
			for label in self:
				label.refresh()
		finally:
			self._measuring = False
		self._auto_step, self._keep_last = self._measure_step()
		for label in self:
			label.refresh()

	def _measure_step(self) -> tuple[int, bool]:
		"""
		The smallest step at which neighbouring labels no longer overlap, and
		whether the last label can still be kept at that step.

		Only chosen for default tick intervals: an `interval` or `every` written in
		the config is taken as is.
		"""
		if 'interval' in self._ticks._user_set_state_items_ or 'every' in self._user_set_state_items_:
			return 1, True
		labels = sorted((l for l in self if l.isVisible()), key=lambda l: l.tick.index)
		if len(labels) < 3:
			return 1, True
		geometry = {}
		for label in labels:
			# The flat rect: a bent outline's box is bigger on the curved axis, and
			# the rotation term below would count that twice.
			rect = label._flatRect or label.path().boundingRect()
			geometry[label.tick.index] = (
				label.mapToParent(rect.center()),
				rect.width() * label.scale(),
				rect.height() * label.scale(),
				label.rotation(),
			)

		def extent(index: int, direction: QPointF) -> float:
			# Half-extent of the label's box measured along `direction`.
			_, w, h, rotation = geometry[index]
			beta = atan2(direction.y(), direction.x()) - radians(rotation)
			return (abs(w * cos(beta)) + abs(h * sin(beta))) / 2

		def overlaps(a: int, b: int) -> bool:
			delta = geometry[b][0] - geometry[a][0]
			distance = hypot(delta.x(), delta.y())
			if not distance:
				return True
			# Touching is not enough: keep half a label height between neighbours.
			gap = min(geometry[a][2], geometry[b][2]) / 2
			return distance < extent(a, delta) + extent(b, delta) + gap

		indices = [label.tick.index for label in labels]
		last = indices[-1]
		for keepLast in (True, False):
			for step in range(1, last + 1):
				kept = [i for i in indices if not i % step or (keepLast and i == last)]
				# Every pair, not just neighbours by value: labels pushed inward can
				# meet across the dial (both ends of a 240° arc land on the bottom row).
				if not any(overlaps(a, b) for a, b in combinations(kept, 2)):
					return step, keepLast
		return last, False

	def __init__(self, graduations: Graduations, surface: 'TickSurface'):
		self._gauge = graduations.gauge
		self._ticks = graduations
		super(GaugeTickTextGroup, self).__init__(graduations, surface)

	@cached_property
	def label_kwargs_generator(self) -> Iterator[dict[str, GaugeItem]]:
		all_ticks = self.labeled_ticks
		brush = self.fill_brush
		for tick in sorted(all_ticks, key=lambda t: t.index):
			yield dict(gauge=self._gauge, tick=tick, group=self, color=brush[tick.value])

	def resize(self, newSize: int):

		while newSize < (current_size := len(self)):
			self.pop().delete()

		if newSize > current_size:
			clearCacheAttr(self, 'label_kwargs_generator')
			for options in self.label_kwargs_generator:
				self.append(GaugeTickText(**options))

		# self._set_fill_brush(self.fill_brush)
		self.sort(key=lambda l: l.tick.index)

	def labelFactory(self, **kwargs) -> 'GaugeTickText':
		return GaugeTickText(**{**next(self.label_kwargs_generator), **kwargs})

	@StateProperty(key='position', allowNone=False, repr=True)
	def position(self) -> DisplayPosition:
		...

	@position.setter
	def position(self, value: DisplayPosition):
		self._position = value

	@StateProperty(key='enabled', allowNone=False, singleVal=True)
	def enabled(self) -> bool:
		return self._enabled

	@enabled.setter
	def enabled(self, value: bool):
		self._enabled = value
		self.resize(len(self.all_ticks) if value else 0)

	@enabled.item_default
	def enabled(self) -> bool:
		match self._ticks.tick_type:
			case Graduations.Type.Major:
				return True
			case Graduations.Type.Minor:
				return False
			case Graduations.Type.Micro:
				return False

	@StateProperty(key='rotate', allowNone=False, default=True, repr=True, after=refresh)
	def rotation(self) -> bool:
		return self._rotation

	@rotation.setter
	def rotation(self, value: bool):
		self._rotation = value

	@StateProperty(key='curve', default=CurveMode.none, allowNone=False, repr=True, after=refresh)
	def curve(self) -> CurveMode:
		return getattr(self, '_curve', CurveMode.none)

	@curve.setter
	def curve(self, value: CurveMode):
		self._curve = value

	@curve.decode
	def curve(self, value) -> CurveMode:
		if isinstance(value, CurveMode):
			return value
		if value in (False, None):
			return CurveMode.none
		return CurveMode[str(value).lower()]

	@curve.encode
	def curve(self, value: CurveMode) -> str:
		return value.value

	def _get_max_label(self) -> GaugeTickText:
		return max(self, key=lambda label: label.value)

	@StateProperty(key='position-leading', dependencies={'position'}, after=refresh)
	def position_leading(self) -> DisplayPosition:
		return getattr(self, '_position_leading', Unset) or self.position

	@position_leading.setter
	def position_leading(self, value: DisplayPosition):
		self._position_leading = value

	@position_leading.decode
	def position_leading(self, value: str) -> DisplayPosition:
		return DisplayPosition[value]

	@position_leading.condition(method='get')
	def position_leading(self, value: DisplayPosition) -> bool:
		return value is not self.position

	@StateProperty(key='position-trailing', dependencies={'position'}, after=refresh)
	def position_trailing(self) -> DisplayPosition:
		return getattr(self, '_position_trailing', Unset) or self.position

	@position_trailing.setter
	def position_trailing(self, value: DisplayPosition):
		self._position_trailing = value

	@position_trailing.decode
	def position_trailing(self, value: str) -> DisplayPosition:
		return DisplayPosition[value]

	@position_trailing.condition(method='get')
	def position_trailing(self, value: DisplayPosition) -> bool:
		return value is not self.position

	@StateProperty(key='rotate-leading', allowNone=False, default=False)
	def rotation_leading(self) -> bool:
		return self._rotation_leading

	@rotation_leading.setter
	def rotation_leading(self, value: bool):
		self._rotation_leading = value

	@StateProperty(key='rotate-trailing', allowNone=False, default=False)
	def rotation_trailing(self) -> bool:
		return self._rotation_trailing

	@rotation_trailing.setter
	def rotation_trailing(self, value: bool):
		self._rotation_trailing = value

	def _align_trailing_auto(self) -> AlignmentFlag:
		if self.rotation_trailing:
			return self.alignment.combined
		return AlignmentFlag.Center

	@StateProperty(key='align-trailing')
	def align_trailing(self) -> AlignmentFlag:
		return getattr(self, '_align_trailing', Unset) or self._align_trailing_auto()

	@align_trailing.setter
	def align_trailing(self, value: AlignmentFlag):
		self._align_trailing = value

	@align_trailing.decode
	def align_trailing(self, value: str) -> AlignmentFlag:
		return AlignmentFlag[value]

	@align_trailing.condition(method='get')
	def align_trailing(self, value: AlignmentFlag) -> bool:
		return value != self.alignment.combined

	def _align_leading_auto(self) -> AlignmentFlag:
		if self.rotation_leading:
			return self.alignment.combined
		return AlignmentFlag.Center

	@StateProperty(key='align-leading')
	def align_leading(self) -> AlignmentFlag:
		return getattr(self, '_align_leading', Unset) or self._align_leading_auto()

	@align_leading.setter
	def align_leading(self, value: AlignmentFlag):
		self._align_leading = value

	@align_leading.decode
	def align_leading(self, value: str) -> AlignmentFlag:
		return AlignmentFlag[value]

	@align_leading.condition(method='get')
	def align_leading(self, value: AlignmentFlag) -> bool:
		return value != self.alignment.combined

	@property
	def gauge(self) -> 'Gauge':
		return self._gauge

	@StateProperty(key='every', default=1, allowNone=False)
	def interval(self) -> int:
		return self._interval

	@interval.setter
	def interval(self, value: int):
		self._interval = value

	@property
	def labeled_ticks(self) -> list[Tick]:
		inverval = self.interval
		return [i for i in self.surface.childItems() if type(i) is Tick and i.label is None and not i.index % inverval]

	@property
	def all_ticks(self) -> list[Tick]:
		return [i for i in self.surface.childItems() if type(i) is Tick]

	@defer
	def build(self):
		clearCacheAttr(self, 'label_kwargs_generator')
		self.resize(len(self.all_ticks) if self.enabled else 0)

	@defer
	def rebuild(self):
		if self.enabled:
			self.build()
		self.refresh()

	@property
	def alignmentAuto(self) -> Alignment:
		if not self.rotation:
			return Alignment(AlignmentFlag.Center)
		match self.position:
			case DisplayPosition.Top:
				return Alignment(AlignmentFlag.BottomCenter)
			case DisplayPosition.Bottom:
				return Alignment(AlignmentFlag.TopCenter)
			case DisplayPosition.Left:
				return Alignment(AlignmentFlag.CenterLeft)
			case DisplayPosition.Right:
				return Alignment(AlignmentFlag.CenterRight)
			case DisplayPosition.Center | DisplayPosition.Auto:
				return Alignment(AlignmentFlag.Center)
			case _:
				return Alignment(AlignmentFlag.Center)


class Needle(StatefulGaugePathItem):
	_animation: QPropertyAnimation
	_animationSignal = Signal(float)

	class Type(str, Enum, metaclass=ClosestMatchEnumMeta):
		Needle = 'needle'
		Circle = 'circle'
		Triangle = 'triangle'
		Diamond = 'diamond'
		#: An arrowhead riding the arc itself rather than sweeping from the
		#: centre. The other edge shapes sit *at* the radius; this one is
		#: centred *on* the stroke, so it reads as a marker on the line.
		Marker = 'marker'
		#: A kite from the pivot to the tip, with an optional tail behind the
		#: pivot (``tail``) and a hub disc (``hub``): a barometer hand.
		Tapered = 'tapered'
		#: A shaft with an arrowhead at the rim (``point: out``, the default) or
		#: at the inner end (``point: in``). ``tail`` adds a second shaft on the
		#: opposite side and ``tail-dot`` caps it with a dot at the opposite rim:
		#: a wind-direction arrow.
		Arrow = 'arrow'
		#: A thin line from the pivot, with an optional counterweight disc
		#: (``tail-dot``) at the end of its tail (``tail``).
		Line = 'line'
		#: A knob riding the track, with an optional ``halo`` ring around it:
		#: a sun-path position.
		Dot = 'dot'
		#: A short bar across the track: a limit mark.
		Notch = 'notch'

	#: Styles drawn from the pivot, which can carry a ``hub``.
	_PIVOT_STYLES = frozenset({'needle', 'tapered', 'line'})

	_shown: Optional[float] = None
	_lastTarget: Optional[float] = None
	_anim: Optional[QVariantAnimation] = None
	_under: tuple = ()
	_over: tuple = ()

	def __init__(self, *args, **kwargs):
		super(Needle, self).__init__(*args, **kwargs)
		# self._animation = NeedleAnimation(self)
		pen = QPen()
		pen.setJoinStyle(Qt.RoundJoin)
		self.setPen(Qt.NoPen)
		self.add_defaults_to_state(kwargs)
		self.refresh()
		shadow = SoftShadow(owner=self)
		self.setGraphicsEffect(shadow)

	def draw(self):
		match self.type:
			case Needle.Type.Needle | 'needle':
				path = self._default()
			case Needle.Type.Circle | 'circle':
				path = self._edge_circle()
			case Needle.Type.Triangle | 'triangle':
				path = self._edge_triangle()
			case Needle.Type.Diamond | 'diamond':
				path = self._edge_diamond()
			case Needle.Type.Marker | 'marker':
				path = self._edge_marker()
			case Needle.Type.Tapered:
				path = self._style_tapered()
			case Needle.Type.Arrow:
				path = self._style_arrow()
			case Needle.Type.Line:
				path = self._style_line()
			case Needle.Type.Dot:
				path = self._style_dot()
			case Needle.Type.Notch:
				path = self._style_notch()
			case _:
				path = self._default()
		self.prepareGeometryChange()
		self._under, self._over = self._extras()
		self.setPath(path)

	def _brushColor(self) -> QColor:
		color = getattr(self, '_color', None)
		return self.gauge.defaultColor if color is None else color.QColor

	def refresh(self):
		gauge = self.gauge

		self.resetTransform()
		self.setBrush(QBrush(self._brushColor()))
		self.draw()

		self._applyAngle(gauge.value_to_angle(gauge.value))
		self.setPos(gauge.center)
		# resetTransform() above dropped the shift recenter() gave this item.
		# A value change refreshes the needle without a recenter, so put the
		# shift back or the pivot drifts off the arc's centre.
		self.setTransform(gauge._recenterTransform, combine=False)
		self.setZValue(-500)
		self.setVisible(getattr(self, '_visible', True))

	@StateProperty(key='visible', default=True, allowNone=False, after=refresh)
	def visible(self) -> bool:
		"""``false`` hides the needle itself, for a dial drawn with a ``fill`` and markers."""
		return getattr(self, '_visible', True)

	@visible.setter
	def visible(self, value: bool):
		self._visible = bool(value)

	@StateProperty(key='type', default=Type.Needle, allowNone=False, repr=True, after=refresh)
	def type(self) -> Type:
		return self._type

	@type.setter
	def type(self, value: Type):
		self._type = value

	@type.decode
	def type(self, value: str) -> Type:
		return Needle.Type[value]

	@StateProperty(key='width', allowNone=False, repr=True, dependencies={'type'}, after=refresh)
	def width(self) -> Size.Width | Length:
		return self._width

	@width.setter
	def width(self, value: Size.Width | Length):
		self._width = value

	@width.item_default
	def width(self) -> Size.Width | Length:
		# The styles added with the hands are thin; every older one keeps 10%.
		match self.type:
			case Needle.Type.Tapered:
				return Size.Width(0.09, relative=True)
			case Needle.Type.Arrow:
				return Size.Width(0.025, relative=True)
			case Needle.Type.Line:
				return Size.Width(0.012, relative=True)
			case Needle.Type.Dot:
				return Size.Width(0.09, relative=True)
			case Needle.Type.Notch:
				return Size.Width(0.02, relative=True)
			case _:
				return Size.Width(0.1, relative=True)

	@width.decode
	def width(self, value: str | float | int) -> Size.Width | Length:
		return parseWidth(value, type(self).width.default(type(self), self, update_source=False))

	@property
	def width_px(self) -> float:
		return self.gauge.sizeAcross(self.width, dimension=DimensionType.width)

	@StateProperty(key='length', allowNone=False, repr=True, dependencies={'type'}, after=refresh)
	def length(self) -> Size.Height | Length:
		return self._length

	@length.setter
	def length(self, value: Size.Height | Length):
		self._length = value

	@length.item_default
	def length(self) -> Size.Height | Length:
		match self.type:
			case Needle.Type.Needle | 'needle':
				return Size.Height(1.0, relative=True)
			case Needle.Type.Circle | 'circle':
				return Size.Height(0.2, relative=True)
			case Needle.Type.Triangle | 'triangle':
				return Size.Height(0.2, relative=True)
			case Needle.Type.Diamond | 'diamond':
				return Size.Height(0.2, relative=True)
			case Needle.Type.Tapered:
				return Size.Height(0.85, relative=True)
			case Needle.Type.Arrow:
				return Size.Height(0.4, relative=True)
			case Needle.Type.Line:
				return Size.Height(0.9, relative=True)
			case Needle.Type.Dot:
				return Size.Height(0.2, relative=True)
			case Needle.Type.Notch:
				return Size.Height(0.12, relative=True)
			case _:
				return Size.Height(1.0, relative=True)

	@length.decode
	def length(self, value: str | float | int) -> Size.Height | Length:
		return parseHeight(value, type(self).length.default(type(self), self, update_source=False))

	@property
	def length_px(self) -> float:
		return self.gauge.sizeAcross(self.length, dimension=DimensionType.height)

	@property
	def needleSize(self) -> QSizeF:
		return QSizeF(self.width_px, self.length_px)

	@StateProperty(key='offset', default=Size.Height(0, relative=True), allowNone=False, repr=True, after=refresh)
	def offset(self) -> Size.Height | Length:
		return self._offset

	@offset.setter
	def offset(self, value: Size.Height | Length):
		self._offset = value

	@offset.decode
	def offset(self, value: str | float | int) -> Size.Height | Length:
		return parseHeight(value, type(self).offset.default(type(self), self, update_source=False))

	@property
	def offset_px(self) -> float:
		return self.gauge.sizeAcross(self.offset, dimension=DimensionType.height)

	@StateProperty(key='color', default=None, allowNone=True, repr=True, after=refresh)
	def color(self) -> Color | None:
		"""Colour of the needle. Default: the gauge's text colour."""
		return getattr(self, '_color', None)

	@color.setter
	def color(self, value: Color | None):
		self._color = value

	@color.decode
	def color(self, value) -> Color | None:
		return None if value is None else Color.decode(value)

	@color.encode
	def color(self, value: Color | None) -> str | None:
		return None if value is None else str(value)

	@staticmethod
	def _optionalSize(parse, value):
		return None if value is None else parse(value, None)

	@staticmethod
	def _encodeSize(value) -> str | None:
		return None if value is None else str(value)

	@StateProperty(key='tail', default=None, allowNone=True, after=refresh)
	def tail(self) -> Size.Height | Length | None:
		"""Length behind the pivot, as a share of the radius (``tapered``, ``arrow``, ``line``)."""
		return getattr(self, '_tail', None)

	@tail.setter
	def tail(self, value):
		self._tail = value

	@tail.decode
	def tail(self, value):
		return Needle._optionalSize(parseHeight, value)

	@tail.encode
	def tail(self, value):
		return Needle._encodeSize(value)

	@StateProperty(key='tail-dot', default=None, allowNone=True, after=refresh)
	def tailDot(self) -> Size.Width | Length | None:
		"""Diameter of the dot at the end of the tail (``arrow``, ``line``)."""
		return getattr(self, '_tailDot', None)

	@tailDot.setter
	def tailDot(self, value):
		self._tailDot = value

	@tailDot.decode
	def tailDot(self, value):
		return Needle._optionalSize(parseWidth, value)

	@tailDot.encode
	def tailDot(self, value):
		return Needle._encodeSize(value)

	@StateProperty(key='head', default=None, allowNone=True, after=refresh)
	def head(self) -> Size.Height | Length | None:
		"""Length of the arrowhead (``arrow``). Default 12% of the radius."""
		return getattr(self, '_head', None)

	@head.setter
	def head(self, value):
		self._head = value

	@head.decode
	def head(self, value):
		return Needle._optionalSize(parseHeight, value)

	@head.encode
	def head(self, value):
		return Needle._encodeSize(value)

	@StateProperty(key='point', default=None, allowNone=True, after=refresh)
	def point(self) -> str | None:
		"""Where the ``arrow`` head sits: ``out`` (at the rim, default) or ``in`` (at the inner end)."""
		return getattr(self, '_point', None)

	@point.setter
	def point(self, value):
		self._point = value

	@point.decode
	def point(self, value):
		if value is None:
			return None
		value = str(value).strip().lower()
		if value not in ('in', 'out'):
			raise ValueError(f'needle point must be in or out, not {value!r}')
		return value

	@StateProperty(key='hub', default=None, allowNone=True, after=refresh)
	def hub(self) -> Size.Width | Length | None:
		"""Diameter of a disc at the pivot (``needle``, ``tapered``, ``line``), as a share of the radius."""
		return getattr(self, '_hub', None)

	@hub.setter
	def hub(self, value):
		self._hub = value

	@hub.decode
	def hub(self, value):
		return Needle._optionalSize(parseWidth, value)

	@hub.encode
	def hub(self, value):
		return Needle._encodeSize(value)

	@StateProperty(key='hub-color', default=None, allowNone=True, after=refresh)
	def hubColor(self) -> Color | None:
		"""Colour of the hub. Default: the needle colour."""
		return getattr(self, '_hubColor', None)

	@hubColor.setter
	def hubColor(self, value):
		self._hubColor = value

	@hubColor.decode
	def hubColor(self, value):
		return None if value is None else Color.decode(value)

	@hubColor.encode
	def hubColor(self, value):
		return None if value is None else str(value)

	@StateProperty(key='hub-hole', default=None, allowNone=True, after=refresh)
	def hubHole(self) -> float | None:
		"""Share of the hub's diameter cut out of its middle: a ring instead of a disc."""
		return getattr(self, '_hubHole', None)

	@hubHole.setter
	def hubHole(self, value):
		self._hubHole = value

	@hubHole.decode
	def hubHole(self, value):
		if value is None:
			return None
		if isinstance(value, str):
			value = float(value.strip().rstrip('%')) / 100 if value.strip().endswith('%') else float(value)
		return min(max(float(value), 0.0), 0.95)

	@StateProperty(key='halo', default=None, allowNone=True, after=refresh)
	def halo(self) -> Size.Width | Length | None:
		"""Width of a ring around a ``dot``, in the ``halo-color``."""
		return getattr(self, '_halo', None)

	@halo.setter
	def halo(self, value):
		self._halo = value

	@halo.decode
	def halo(self, value):
		return Needle._optionalSize(parseWidth, value)

	@halo.encode
	def halo(self, value):
		return Needle._encodeSize(value)

	@StateProperty(key='halo-color', default=None, allowNone=True, after=refresh)
	def haloColor(self) -> Color | None:
		return getattr(self, '_haloColor', None)

	@haloColor.setter
	def haloColor(self, value):
		self._haloColor = value

	@haloColor.decode
	def haloColor(self, value):
		return None if value is None else Color.decode(value)

	@haloColor.encode
	def haloColor(self, value):
		return None if value is None else str(value)

	@StateProperty(key='animate', default=0, allowNone=False, after=refresh)
	def animate(self) -> float:
		"""Milliseconds the hand takes to move to a new value; 0 (default) jumps.
		With a wrapping range (``range: {wrap: true}``) it takes the shorter way round."""
		return self._animate

	@animate.setter
	def animate(self, value: float):
		self._animate = value

	@animate.decode
	def animate(self, value) -> float:
		if isinstance(value, str):
			text = value.strip().lower()
			value = float(text[:-2]) if text.endswith('ms') else float(text[:-1]) * 1000 if text.endswith('s') else float(text)
		return max(0.0, float(value))

	def _radial(self, size: Size.Height | Size.Width | None, default: float = 0.0, *, dimension=DimensionType.height) -> float:
		"""A relative size in pixels, or ``default`` (a share of the radius) when unset."""
		if size is None:
			return default * self.gauge.radius
		return self.gauge.sizeAcross(size, dimension=dimension) or 0.0

	def _pivotY(self) -> float:
		return self.offset_px

	def _hubPath(self) -> Optional[QPainterPath]:
		hub = self.hub
		if hub is None or self.type.value not in self._PIVOT_STYLES:
			return None
		diameter = self.gauge.sizeAcross(hub, dimension=DimensionType.width) or 0.0
		if diameter <= 0:
			return None
		path = QPainterPath()
		path.setFillRule(Qt.FillRule.OddEvenFill)
		path.addEllipse(QPointF(0, self._pivotY()), diameter / 2, diameter / 2)
		if self.hubHole:
			hole = diameter / 2 * self.hubHole
			path.addEllipse(QPointF(0, self._pivotY()), hole, hole)
		return path

	def _extras(self) -> tuple[tuple, tuple]:
		"""Disc paths drawn beside the main path: ``(under, over)``, each a tuple of ``(path, colour)``."""
		under, over = [], []
		if (hub := self._hubPath()) is not None:
			over.append((hub, self._hubColor.QColor if getattr(self, '_hubColor', None) is not None else self.brush().color()))
		if self.type is Needle.Type.Dot and self.halo is not None:
			halo = self.gauge.sizeAcross(self.halo, dimension=DimensionType.width) or 0.0
			if halo > 0 and (color := getattr(self, '_haloColor', None)) is not None:
				r = self.width_px / 2 + halo
				path = QPainterPath()
				path.addEllipse(QPointF(0, self.offset_px - self.gauge.radius), r, r)
				under.append((path, color.QColor))
		return tuple(under), tuple(over)

	def boundingRect(self) -> QRectF:
		rect = super().boundingRect()
		for path, _ in (*self._under, *self._over):
			rect = rect.united(path.boundingRect())
		return rect

	def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
		painter.setPen(Qt.NoPen)
		for path, color in self._under:
			painter.setBrush(QBrush(color))
			painter.drawPath(path)
		super().paint(painter, option, widget)
		painter.setPen(Qt.NoPen)
		for path, color in self._over:
			painter.setBrush(QBrush(color))
			painter.drawPath(path)

	def _setShape(self, path: QPainterPath) -> QPainterPath:
		self._shape = QPainterPath(path)
		self._bounding_rect = path.boundingRect()
		return path

	@staticmethod
	def _stroke(line: QPainterPath, width: float, cap=Qt.PenCapStyle.FlatCap) -> QPainterPath:
		stroker = QPainterPathStroker()
		stroker.setWidth(max(width, 0.5))
		stroker.setCapStyle(cap)
		return stroker.createStroke(line)

	def _style_tapered(self) -> QPainterPath:
		"""A kite: wide at the pivot, narrowing to the tip, with a short tail behind.

		Length: pivot to tip. Width: across the pivot. Tail: behind the pivot.
		Offset: moves the pivot. Add ``hub`` for the disc over the pivot.
		"""
		y, w = self._pivotY(), self.width_px
		tip = QPointF(0, y - self.length_px)
		tail = self._radial(self.tail)
		path = QPainterPath()
		path.moveTo(tip)
		path.lineTo(w / 2, y)
		path.lineTo(w * 0.3, y + tail)
		path.lineTo(-w * 0.3, y + tail)
		path.lineTo(-w / 2, y)
		path.closeSubpath()
		return self._setShape(path)

	def _style_line(self) -> QPainterPath:
		"""A thin line with a counterweight: ``tail`` is the line behind the pivot,
		``tail-dot`` the disc at its end. Length: pivot to tip."""
		y, w = self._pivotY(), self.width_px
		tail = self._radial(self.tail)
		line = QPainterPath(QPointF(0, y + tail))
		line.lineTo(0, y - self.length_px)
		path = self._stroke(line, w, Qt.PenCapStyle.RoundCap)
		if self.tailDot is not None:
			r = self.gauge.sizeAcross(self.tailDot, dimension=DimensionType.width) / 2
			disc = QPainterPath()
			disc.addEllipse(QPointF(0, y + tail), r, r)
			path = path.united(disc)
		return self._setShape(path)

	def _style_arrow(self) -> QPainterPath:
		"""A wind-direction arrow: a shaft and head at the rim, and optionally a
		tail shaft ending in a dot at the opposite rim.

		Length: the shaft, from the rim inward. Width: shaft width.
		Head: head length (default 12%). Point: ``out`` (head at the rim) or ``in``.
		Tail: the opposite shaft's length, from the opposite rim inward.
		Tail-dot: diameter of the dot at the opposite rim. Offset: moves it all inward.
		"""
		radius, w = self.gauge.radius, self.width_px
		off = self.offset_px
		head = self._radial(self.head, 0.12)
		half = head * 0.42
		length = max(self.length_px, head)
		rim = off - radius
		path = QPainterPath()
		if (self.point or 'out') == 'out':
			shaft = QPainterPath(QPointF(0, rim + head * 0.6))
			shaft.lineTo(0, rim + length)
			path.addPath(self._stroke(shaft, w))
			path.moveTo(0, rim)
			path.lineTo(half, rim + head)
			path.lineTo(-half, rim + head)
			path.closeSubpath()
		else:
			shaft = QPainterPath(QPointF(0, rim))
			shaft.lineTo(0, rim + length - head * 0.6)
			path.addPath(self._stroke(shaft, w))
			path.moveTo(0, rim + length)
			path.lineTo(half, rim + length - head)
			path.lineTo(-half, rim + length - head)
			path.closeSubpath()
		tail = self._radial(self.tail)
		dot = (self.gauge.sizeAcross(self.tailDot, dimension=DimensionType.width) or 0.0) if self.tailDot is not None else 0.0
		far = radius - off
		if tail > 0:
			shaft = QPainterPath(QPointF(0, far - dot * 0.5))
			shaft.lineTo(0, far - tail)
			path.addPath(self._stroke(shaft, w))
		if dot > 0:
			path.addEllipse(QPointF(0, far - dot / 2), dot / 2, dot / 2)
		return self._setShape(path)

	def _style_dot(self) -> QPainterPath:
		"""A knob centred on the track. Width: diameter. Halo/halo-color: a ring around it."""
		r = self.width_px / 2
		path = QPainterPath()
		path.addEllipse(QPointF(0, self.offset_px - self.gauge.radius), r, r)
		return self._setShape(path)

	def _style_notch(self) -> QPainterPath:
		"""A bar across the track. Width: along the track. Length: across it."""
		w, length = self.width_px, self.length_px
		rect = QRectF(-w / 2, self.offset_px - self.gauge.radius - length / 2, w, length)
		path = QPainterPath()
		path.addRoundedRect(rect, w * 0.25, w * 0.25)
		return self._setShape(path)

	def _animateMs(self) -> float:
		try:
			return float(self.animate or 0)
		except (AttributeError, TypeError, ValueError):
			return 0.0

	def _applyAngle(self, target: float) -> None:
		"""Rotate to ``target`` degrees, easing there when ``animate`` is set.

		With a wrapping range the hand turns the shorter way across the join.
		Without ``animate`` this is a plain ``setRotation``, as it always was.
		"""
		target = float(target)
		ms = self._animateMs()
		if not ms or self._shown is None:
			self._stopAnimation()
			self._shown = self._lastTarget = target
			self.setRotation(target)
			return
		if target == self._lastTarget:
			self.setRotation(self._shown)
			return
		self._lastTarget = target
		shown = self._shown
		if getattr(self.gauge._range, 'wrap', False):
			destination = shown + shortestDelta(shown, target, float(self.gauge.fullAngle))
		else:
			destination = target
		self._stopAnimation()
		animation = QVariantAnimation()
		animation.setDuration(int(ms))
		animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
		animation.setStartValue(float(shown))
		animation.setEndValue(float(destination))
		animation.valueChanged.connect(self._onAnimated)
		self._anim = animation
		animation.start()

	def _onAnimated(self, value) -> None:
		self._shown = float(value)
		try:
			self.setRotation(self._shown)
		except RuntimeError:
			self._stopAnimation()

	def _stopAnimation(self) -> None:
		animation, self._anim = self._anim, None
		if animation is not None:
			animation.stop()

	_shape: QPainterPath = QPainterPath()

	def shape(self) -> QPainterPath:
		return self._shape or self.path()

	def _default(self) -> QPainterPath:
		"""
		Returns a standard tapering needle with a rounded bottom.

		Length: Controls the length of the needle
		Width: Controls the width of the needle
		Offset: Controls the offset of the needle from the center of the gauge
		"""

		cx = 0
		cy = self.offset_px
		middle = QPointF(cx, cy - self.length_px)
		needleWidth = self.width_px
		left = QPointF(cx - needleWidth / 2, cy)
		right = QPointF(cx + needleWidth / 2, cy)
		arcStart = QPointF(left)
		arcStart.setY(left.y() + needleWidth * 0.6)
		arcEnd = QPointF(right)
		arcEnd.setY(right.y() + needleWidth * 0.6)
		arcRect = QRectF(arcStart, QSizeF(needleWidth, -needleWidth))

		needlePath = QPainterPath()
		needlePath.arcMoveTo(arcRect, 0)
		needlePath.lineTo(middle)
		needlePath.arcTo(arcRect, 180, -180)
		needlePath.addEllipse(QPointF(cx, cy), needleWidth / 3, needleWidth / 3)

		# Set the needle's bounding rect and shape
		self._shape = shape = QPainterPath()
		bounding_rect = QRectF(0, 0, needleWidth, needleWidth)
		bounding_rect.moveCenter(QPointF(cx, cy))
		shape.addEllipse(bounding_rect)
		self._bounding_rect = shape.boundingRect()

		return needlePath

	def _edge_circle(self) -> QPainterPath:
		"""
		Returns a circle that is used as the indicator instead of a needle.

		Length: Not used
		Width: Controls the diameter of the circle
		Offset: Controls the offset of the circle from the arch path of the gauge
		"""

		cx = 0
		cy = self.offset_px
		pos = QPointF(cx, cy - self.gauge.radius)

		path = QPainterPath()
		path.addEllipse(pos, self.width_px / 2, self.width_px / 2)

		# Set the needle's bounding rect and shape
		self._shape = shape = QPainterPath(path)
		# bounding_rect = QRectF(0, 0, self.width_px, self.width_px)
		# bounding_rect.moveCenter(QPointF(pos))
		# shape.addEllipse(bounding_rect)
		self._bounding_rect = shape.boundingRect()

		return path

	def _edge_triangle(self) -> QPainterPath:
		"""
		Returns a triangle that is used as the indicator instead of a needle.

		Length: Controls the length of the triangle.  Positive values will point in, negative values will point out.
		Width: Controls the base width of the triangle
		Offset: Controls the offset of the triangle from the arch path of the gauge

		"""
		cx = 0
		cy = self.offset_px
		l = self.length_px
		w = self.width_px
		pos = QPointF(cx, cy - self.gauge.radius)
		shape = QPainterPath()
		tri_point = QPointF(pos + QPointF(0, l))
		tri_base_y = pos.y()
		tri_base_left = QPointF(pos.x() - w / 2, tri_base_y)
		tri_base_right = QPointF(pos.x() + w / 2, tri_base_y)
		shape.moveTo(tri_point)
		shape.lineTo(tri_base_left)
		shape.lineTo(tri_base_right)
		shape.lineTo(tri_point)
		shape.closeSubpath()
		self._shape = QPainterPath(shape)
		self._bounding_rect = shape.boundingRect()
		return shape

	def _edge_marker(self) -> QPainterPath:
		"""
		Returns an arrowhead that sits *on* the arc rather than pointing at it
		from the centre.

		Unlike the other edge shapes, which are placed at the radius, this one
		is centred on the arc's stroke, so with a matching weight it reads as a
		marker travelling along the line. The notched back keeps it an arrow
		rather than a triangle at a glance.

		Length: depth across the arc. Positive points inward.
		Width: width along the arc
		Offset: nudges it off the arc line
		"""
		cx = 0
		cy = self.offset_px
		l = self.length_px
		w = self.width_px
		# Centre on the stroke, not on the radius, so half sits either side.
		pos = QPointF(cx, cy - self.gauge.radius)
		shape = QPainterPath()
		tip = QPointF(pos.x(), pos.y() + l / 2)
		back_left = QPointF(pos.x() - w / 2, pos.y() - l / 2)
		back_right = QPointF(pos.x() + w / 2, pos.y() - l / 2)
		notch = QPointF(pos.x(), pos.y() - l / 6)
		shape.moveTo(tip)
		shape.lineTo(back_left)
		shape.lineTo(notch)
		shape.lineTo(back_right)
		shape.lineTo(tip)
		shape.closeSubpath()
		self._shape = QPainterPath(shape)
		self._bounding_rect = shape.boundingRect()
		return shape

	def _edge_diamond(self) -> QPainterPath:
		"""
		Returns a diamond that is used as the indicator instead of a needle.

		Length: Controls the height of the diamond
		Width: Controls the width of the diamond
		Offset: Controls the offset of the diamond from the arch path of the gauge

		"""
		cx = 0
		cy = self.offset_px
		l = self.length_px
		w = self.width_px
		pos = QPointF(cx, cy - self.gauge.radius)
		shape = QPainterPath()
		diamond_top = QPointF(pos.x(), pos.y() - l / 2)
		diamond_left = QPointF(pos.x() - w / 2, pos.y())
		diamond_bottom = QPointF(pos.x(), pos.y() + l / 2)
		diamond_right = QPointF(pos.x() + w / 2, pos.y())
		shape.moveTo(diamond_top)
		shape.lineTo(diamond_left)
		shape.lineTo(diamond_bottom)
		shape.lineTo(diamond_right)
		shape.lineTo(diamond_top)
		shape.closeSubpath()
		self._shape = QPainterPath(shape)
		self._bounding_rect = shape.boundingRect()
		return shape


class Arrow(Needle):

	def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget):
		# draw lines through the center
		painter.setPen(QPen(Qt.red))
		painter.drawRect(self.boundingRect())
		# c = self.boundingRect().center()
		# cTop = QPointF(c.x(), 0)
		# cBottom = QPointF(c.x(), self.boundingRect().height())
		# painter.drawLine(cTop, cBottom)
		# c = self.gauge.arc.center
		# cLeft = QPointF(0, c.y())
		# cRight = QPointF(self.boundingRect().width(), c.y())
		# horizontal = QLineF(cLeft, cRight)
		# painter.drawLine(horizontal)
		# horizontal.translate(0, self.gauge.radius/2/4)
		# painter.drawLine(horizontal)
		# horizontal.translate(0, -self.gauge.radius/2/4*2)
		# painter.drawLine(horizontal)
		# painter.drawLine(self.gauge.arc.center, self.gauge.arc.center + QPointF(0, self.needleLength))
		super(Arrow, self).paint(painter, option, widget)

	@property
	def safeZone(self):
		path = QPainterPath()
		radius = self.gauge.radius
		path.addEllipse(QPoint(0, 0), radius * 0.6, radius * 0.6)
		return path

	# super(Arrow, self).paint(painter, option, widget)

	def draw(self):
		# center = self._gauge.arc.center
		cx = 0
		cy = 0

		# Draw Circle
		radius = self.gauge.radius
		pointerHeight = radius * 0.178
		radius = radius - pointerHeight
		base = pointerHeight
		path = QPainterPath()

		# Draw Outer Circle
		path.setFillRule(Qt.FillRule.WindingFill)
		path.addEllipse(QPoint(cx, cy), radius, radius)

		# Draw Arrow
		middle = QPointF(cx, cy - pointerHeight - radius)
		left = QPointF(cx - base, cy - radius + 10)
		right = QPointF(cx + base, cy - radius + 10)
		arrow = QPolygonF()
		path.moveTo(left)
		path.lineTo(middle)
		path.lineTo(right)
		# arrow.append(middle)
		# arrow.append(left)
		# arrow.append(right)
		# path.addPolygon(arrow)


		# path.setFillRule(Qt.FillRule.WindingFill)

		# Draw Center Circle
		path.addEllipse(QPoint(0, 0), radius * 0.8, radius * 0.8)
		path.setFillRule(Qt.FillRule.OddEvenFill)

		self.setPath(path)


class GaugeMarker(Needle):
	"""An extra indicator on a gauge, with its own value.

	Shares every visual option with the needle (``type``, ``width``,
	``length``, ``offset``). The value comes from ``value:``, a number or a
	key, not from the panel's key. With no value yet the marker is hidden.
	"""

	_markerValue = None
	_markerColor: Optional[QColor] = None
	_binding: Optional[Binding] = None
	_warned = False
	_clockTimer: Optional[QTimer] = None
	_clockHand: Optional[str] = None

	#: Used when the marker names no ``length``: the needle default for the
	#: ``marker`` type is the full radius, which is far too long for a tick.
	DEFAULT_LENGTH = '20%'

	def configure(self, spec: Mapping) -> None:
		"""Apply the visual options and start the value source from ``spec``."""
		visual = {k: v for k, v in spec.items() if k not in ('value', 'color', 'time', 'at')}
		visual.setdefault('type', 'marker')
		if Needle.Type[visual['type']] is Needle.Type.Marker:
			visual.setdefault('length', self.DEFAULT_LENGTH)
		with self.action_pool:
			self.setItemState(visual)

		if (color := spec.get('color')) is not None:
			self._markerColor = Color.decode(color).QColor

		if spec.get('time') is not None:
			self._followClock(spec['time'], spec.get('at'))
			self.refresh()
			return

		raw = spec.get('value')
		if isinstance(raw, bool):
			raise TypeError(f'a marker value must be a number or a key, not {raw!r}')
		if isinstance(raw, (int, float)):
			self._markerValue = raw
		elif isinstance(raw, str):
			if (source := openValueSource(raw, f'Gauge {gaugeKeyName(self.gauge)} marker value', 'the marker stays hidden')) is not None:
				self._binding = Binding(source, self.setMarkerValue)
		else:
			raise TypeError(f'a marker value must be a number or a key, not {raw!r}')
		self.refresh()

	def close(self):
		self._stopAnimation()
		if self._clockTimer is not None:
			self._clockTimer.stop()
			self._clockTimer = None
		if self._binding is not None:
			self._binding.unlink()
			self._binding = None

	def _followClock(self, hand, at) -> None:
		"""Drive the marker from the time of day: ``time: hour|minute|second|day``.
		The hand turns once round the gauge's range (``range: {min: 0, max: 12, wrap: true}``
		for a 12 hour dial) however many units that holds.

		``at: 'HH:MM[:SS]'`` shows that fixed time instead and starts no timer.
		The timer runs on the GUI thread, once a second.
		"""
		hand = str(hand).strip().lower()
		if hand not in CLOCK_HANDS:
			raise ValueError(f'time must be one of {", ".join(CLOCK_HANDS)}, not {hand!r}')
		self._clockHand = hand
		if at is not None:
			self._fixedTime = parseClockTime(at)
			self._tickClock()
			return
		self._fixedTime = None
		self._clockTimer = QTimer()
		self._clockTimer.setInterval(1000)
		self._clockTimer.timeout.connect(self._tickClock)
		self._clockTimer.start()
		self._tickClock()

	def _tickClock(self) -> None:
		try:
			if self._fixedTime is not None:
				hours, minutes, seconds = self._fixedTime
			else:
				# The app's own clock, not the wall clock: `shared.now()` is what
				# `--freeze-time` patches (see _boot.freeze_time), so reading
				# datetime.now() here meant a frozen render still drew a live hand.
				current = now()
				hours, minutes, seconds = current.hour, current.minute, current.second + current.microsecond / 1e6
			self._clockFraction = clockTurn(self._clockHand, hours, minutes, seconds)
		except Exception as e:
			log.warning(f'Gauge {gaugeKeyName(self.gauge)} clock hand stopped: {e}')
			if self._clockTimer is not None:
				self._clockTimer.stop()
			return
		self.refresh()

	def setMarkerValue(self, value) -> None:
		"""Set the value to show. GUI thread only (the feed's slot runs there)."""
		self._markerValue = value
		self.refresh()

	_clockFraction: Optional[float] = None
	_fixedTime = None

	def _markerAngle(self) -> Optional[float]:
		if self._clockHand is not None:
			# Placed against the range as it is now: the range may load after the marker.
			if self._clockFraction is None:
				return None
			_range = self.gauge._range
			self._markerValue = float(_range.rounded_min) + self._clockFraction * float(_range.rounded_range)
		value = self._markerValue
		if value is None:
			return None
		gauge = self.gauge
		valueClass = gauge.valueClass
		try:
			if not isinstance(value, valueClass):
				value = valueClass(value)
		except Exception:
			value = float(value)
		try:
			return gauge.value_to_angle(value)
		except Exception as e:
			if not self._warned:
				self._warned = True
				log.warning(f'Gauge {gaugeKeyName(gauge)} cannot place marker value {value!r}: {e}')
			return None

	def refresh(self):
		gauge = self.gauge
		self.resetTransform()
		self.setBrush(QBrush(gauge.defaultColor if self._markerColor is None else self._markerColor))
		self.draw()
		angle = self._markerAngle()
		if angle is None:
			self.hide()
			return
		self._applyAngle(angle)
		self.setPos(gauge.center)
		# resetTransform() above dropped the shift recenter() gave this item.
		# A value change refreshes the needle without a recenter, so put the
		# shift back or the pivot drifts off the arc's centre.
		self.setTransform(gauge._recenterTransform, combine=False)
		self.setZValue(-500)
		self.show()


class GaugeZones(GaugeItem, QGraphicsItem):
	"""Coloured bands over the arc track, from a list of plain mappings.

	Each entry: ``from`` and ``to`` (numbers; default the range ends),
	``color`` (required), ``weight`` (default the arc's) and ``mark`` (draw a
	tick across the arc at each cutoff that is not a range end). A bad entry
	logs the gauge key and is skipped; nothing here raises during load.
	"""

	#: Over the arc (-800), under the fill (-700) and the needle (-500).
	Z_VALUE = -750

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self._zones: list = []
		self._strokes: list = []
		self._rect = QRectF()
		self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemHasNoContents, False)

	def close(self):
		self._zones = []
		self._strokes = []

	def configure(self, specs: Sequence) -> list:
		"""Validate ``specs``; keep the good ones. Returns the plain mappings kept."""
		name = gaugeKeyName(self.gauge)
		zones, kept = [], []
		for spec in specs:
			try:
				if not isinstance(spec, Mapping):
					raise TypeError('expected a mapping with from, to and color')
				unknown = set(spec) - {'from', 'to', 'color', 'weight', 'mark'}
				if unknown:
					log.warning(f'Gauge {name} zone ignored unknown keys {sorted(map(str, unknown))}')
				ends = []
				for end in ('from', 'to'):
					raw = spec.get(end)
					if raw is None:
						ends.append(None)
						continue
					if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not isfinite(raw):
						raise TypeError(f'{end} must be a finite number, not {raw!r}')
					ends.append(float(raw))
				if spec.get('color') is None:
					raise ValueError('a zone needs a color')
				color = Color.decode(spec['color']).QColor
				weight = None
				if (raw := spec.get('weight')) is not None:
					weight = parseWidth(raw, None)
					if weight is None:
						raise ValueError(f'weight {raw!r} is not a size')
				zones.append({'from': ends[0], 'to': ends[1], 'color': color, 'weight': weight, 'mark': bool(spec.get('mark', False))})
				kept.append(copy.deepcopy(dict(spec)))
			except Exception as e:
				log.warning(f'Gauge {name} skipped zone {spec!r}: {e}')
		self._zones = zones
		return kept

	def _span(self, zone) -> tuple[float, float]:
		"""The zone's start and end as dial angles; a missing end is the dial's end."""
		gauge = self.gauge
		lo = float(gauge.startAngle) if zone['from'] is None else self._angle(zone['from'])
		hi = float(gauge.endAngle) if zone['to'] is None else self._angle(zone['to'])
		return tuple(sorted((lo, hi)))

	def colorAtAngle(self, angle: float) -> Optional[QColor]:
		"""The colour of the zone holding ``angle``; the later zone wins on a shared cutoff."""
		found = None
		for zone in self._zones:
			try:
				lo, hi = self._span(zone)
			except Exception:
				continue
			if lo - 1e-9 <= angle <= hi + 1e-9:
				found = zone['color']
		return found

	def colorAt(self, value) -> Optional[QColor]:
		"""The colour of the zone holding ``value`` (a number or a measurement)."""
		try:
			return self.colorAtAngle(self._angle(value))
		except Exception:
			return None

	def _angle(self, value: float) -> float:
		gauge = self.gauge
		valueClass = gauge.valueClass
		try:
			converted = valueClass(value)
		except Exception:
			converted = float(value)
		return float(gauge.value_to_angle(converted))

	def refresh(self):
		self.prepareGeometryChange()
		self._strokes = []
		gauge = self.gauge
		bounds = QRectF()
		if not self._zones:
			self._rect = bounds
			self.hide()
			return
		try:
			rect = gauge.arc.centered_gauge_rect
			arcWeight = gauge.arc.weight_px
			marks = set()
			for zone in self._zones:
				a, b = self._span(zone)
				weight = gauge.sizeAcross(zone['weight'], dimension=DimensionType.width) if zone['weight'] is not None else arcWeight
				if zone['mark']:
					marks.update(x for x in (a, b) if float(gauge.startAngle) + 1e-6 < x < float(gauge.endAngle) - 1e-6)
				if not weight or a == b:
					continue
				path = QPainterPath()
				path.arcMoveTo(rect, -a + 90)
				path.arcTo(rect, -a + 90, -(b - a))
				pen = QPen(zone['color'], weight)
				pen.setCapStyle(Qt.PenCapStyle.FlatCap)
				self._strokes.append((path, pen))
				bounds = bounds.united(path.boundingRect().adjusted(-weight, -weight, weight, weight))
			for angle in sorted(marks):
				radius = rect.width() / 2
				reach = (arcWeight or 0) * 0.75
				path = QPainterPath()
				path.moveTo(radialPoint(QPointF(0, 0), radius - reach, angle))
				path.lineTo(radialPoint(QPointF(0, 0), radius + reach, angle))
				pen = QPen(gauge.defaultColor, max(1.5, (arcWeight or 0) * 0.12))
				pen.setCapStyle(Qt.PenCapStyle.FlatCap)
				self._strokes.append((path, pen))
				bounds = bounds.united(path.boundingRect().adjusted(-2, -2, 2, 2))
		except Exception as e:
			log.warning(f'Gauge {gaugeKeyName(gauge)} zones not drawn: {e}')
			self._strokes = []
		self._rect = bounds
		self.setPos(gauge.center)
		self.setZValue(self.Z_VALUE)
		self.setVisible(bool(self._strokes))
		self.update()

	def boundingRect(self) -> QRectF:
		return self._rect

	def paint(self, painter: QPainter, option, widget=None):
		painter.setBrush(Qt.BrushStyle.NoBrush)
		for path, pen in self._strokes:
			painter.setPen(pen)
			painter.drawPath(path)


class GaugeFill(GaugePathItem):
	"""A value-driven arc stroked over the track and under the needle.

	Spec keys: ``from`` (a number, key or expression; default the range
	minimum), ``to`` (a number, key or expression; omitted means the gauge value), ``weight`` (default the arc's) and
	``color`` (default the gauge colour). With no value to draw to, it is hidden.
	A source-fed end with no value yet hides the fill; a bad spec logs the gauge key and hides it.
	"""

	#: Between the arc (-800) and the needle (-500).
	Z_VALUE = -700

	_from: Optional[float] = None
	_to: Optional[float] = None
	_weight = None
	_color: Optional[QColor] = None
	_valid = False
	_warned = False
	_colorFromZones = False
	_segments: int = 0
	_gap = None
	_strokes: list = ()

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		# Ends fed by a value source that has not delivered yet: the fill is hidden.
		self._pending: set = set()
		self._bindings: list = []

	def close(self):
		"""Unlink the bindings, which releases the value sources."""
		bindings = self._bindings
		self._bindings, self._pending = [], set()
		for binding in bindings:
			binding.unlink()

	def setEnd(self, end: str, value) -> None:
		"""Set a source-fed end. GUI thread only (the feed's slot runs there)."""
		try:
			value = float(value)
		except (TypeError, ValueError):
			return
		if not isfinite(value):
			return
		setattr(self, f'_{end}', value)
		self._pending.discard(end)
		self._safeRefresh()

	def configure(self, spec: Mapping) -> None:
		"""Read ``spec``. Never raises: a bad spec warns and leaves the fill hidden."""
		self.close()
		self._valid = False
		self._from = self._to = self._weight = self._color = self._gap = None
		self._colorFromZones, self._segments, self._strokes = False, 0, ()
		name = gaugeKeyName(self.gauge)
		unknown = set(spec) - {'from', 'to', 'weight', 'color', 'segments', 'gap'}
		if unknown:
			log.warning(f'Gauge {name} fill ignored unknown keys {sorted(map(str, unknown))}')
		try:
			for end in ('from', 'to'):
				raw = spec.get(end)
				if raw is None:
					continue
				if isinstance(raw, bool):
					raise TypeError(f'{end} must be a number, a key or an expression, not {raw!r}')
				if isinstance(raw, (int, float)):
					if not isfinite(raw):
						raise TypeError(f'{end} must be finite, not {raw!r}')
					setattr(self, f'_{end}', float(raw))
				elif isinstance(raw, str):
					self._pending.add(end)
					if (source := openValueSource(raw, f'Gauge {name} fill {end}', 'the fill stays hidden')) is None:
						raise ValueError(f'{end} {raw!r} is not usable')
					self._bindings.append(Binding(source, _FillEnd(self, end).setMarkerValue))
				else:
					raise TypeError(f'{end} must be a number, a key or an expression, not {raw!r}')
			if (weight := spec.get('weight')) is not None:
				self._weight = parseWidth(weight, None)
				if self._weight is None:
					raise ValueError(f'weight {weight!r} is not a size')
			if isinstance(spec.get('color'), str) and spec['color'].strip().lower() == 'zone':
				self._colorFromZones = True
			elif (color := spec.get('color')) is not None:
				self._color = Color.decode(color).QColor
			if (segments := spec.get('segments')) is not None:
				if isinstance(segments, bool) or not isinstance(segments, int) or segments < 1:
					raise TypeError(f'segments must be a whole number of 1 or more, not {segments!r}')
				self._segments = segments
				if (gap := spec.get('gap')) is not None:
					self._gap = parseWidth(gap, None)
					if self._gap is None:
						raise ValueError(f'gap {gap!r} is not a size')
		except Exception as e:
			log.warning(f'Gauge {name} fill ignored, hidden: {e}')
			self.close()
			self._safeRefresh()
			return
		self._valid = True
		self._safeRefresh()

	def _safeRefresh(self):
		# The gauge may not be laid out yet while its state loads; Gauge.refresh redraws later.
		try:
			self.refresh()
		except Exception as e:
			log.debug(f'Gauge {gaugeKeyName(self.gauge)} fill not drawn yet: {e}')

	def _toValueClass(self, value):
		valueClass = self.gauge.valueClass
		try:
			if not isinstance(value, valueClass):
				value = valueClass(value)
		except Exception:
			value = float(value)
		return value

	def _angles(self) -> Optional[tuple[float, float]]:
		gauge = self.gauge
		start = self._from if self._from is not None else gauge._range.rounded_min
		end = self._to if self._to is not None else gauge.value
		if start is None or end is None:
			return None
		try:
			a = gauge.value_to_angle(self._toValueClass(start))
			b = gauge.value_to_angle(self._toValueClass(end))
			a, b = float(a), float(b)
		except Exception as e:
			if not self._warned:
				self._warned = True
				log.warning(f'Gauge {gaugeKeyName(gauge)} cannot place fill {start!r} to {end!r}: {e}')
			return None
		if not (isfinite(a) and isfinite(b)):
			return None
		return a, b

	def refresh(self):
		"""Redraw. Geometry and colour only; never asks the gauge to relayout."""
		gauge = self.gauge
		angles = self._angles() if self._valid and not self._pending else None
		if angles is None:
			self.hide()
			return
		# Either order: draw from the smaller angle to the larger. Both ends were
		# already clamped to the arc by value_to_angle. Equal angles draw nothing.
		a, b = sorted(angles)
		if a == b:
			self.hide()
			return
		weight = gauge.sizeAcross(self._weight, dimension=DimensionType.width) if self._weight is not None else gauge.arc.weight_px
		rect = gauge.arc.centered_gauge_rect
		zones = gauge._zonesItem
		base = gauge.defaultColor if self._color is None else self._color
		strokes = []
		if weight and self._segments:
			start, full = float(gauge.startAngle), float(gauge.fullAngle)
			step = full / self._segments
			radius = rect.width() / 2 or 1
			gapDeg = 0.0
			if self._gap is not None:
				gapPx = gauge.sizeAcross(self._gap, dimension=DimensionType.width) or 0
				gapDeg = gapPx / radius * 180 / pi
			# Never let the gap swallow the segment.
			gapDeg = min(max(gapDeg, 0.0), step * 0.8)
			for i in range(self._segments):
				sa, sb = start + i * step + gapDeg / 2, start + (i + 1) * step - gapDeg / 2
				mid = start + (i + 0.5) * step
				if not (a <= mid <= b):
					continue
				path = QPainterPath()
				path.arcMoveTo(rect, -sa + 90)
				path.arcTo(rect, -sa + 90, -(sb - sa))
				color = base
				if self._colorFromZones and zones is not None:
					color = zones.colorAtAngle(mid) or base
				strokes.append((path, color))
		elif weight:
			path = QPainterPath()
			path.arcMoveTo(rect, -a + 90)
			path.arcTo(rect, -a + 90, -(b - a))
			color = base
			if self._colorFromZones and zones is not None:
				endValue = self._to if self._to is not None else gauge.value
				color = zones.colorAt(endValue) or base
			strokes.append((path, color))
		full = QPainterPath()
		for path, _ in strokes:
			full.addPath(path)
		pen = QPen(gauge.pen)
		pen.setWidthF(weight or 0)
		pen.setCapStyle(Qt.PenCapStyle.FlatCap)
		pen.setBrush(QBrush(strokes[0][1] if strokes else base))
		self.setPen(pen)
		self.setBrush(Qt.BrushStyle.NoBrush)
		self.prepareGeometryChange()
		self._strokes = strokes
		self.setPath(full)
		self.setPos(gauge.center)
		self.setZValue(self.Z_VALUE)
		self.show()

	def _valueAtAngle(self, angle: float) -> float:
		gauge = self.gauge
		lo, span = float(gauge._range.rounded_min), float(gauge._range.rounded_range)
		return lo + (angle - float(gauge.startAngle)) / float(gauge.fullAngle) * span

	def paint(self, painter: QPainter, option, widget=None):
		painter.setBrush(Qt.BrushStyle.NoBrush)
		for path, color in self._strokes:
			pen = QPen(self.pen())
			pen.setBrush(QBrush(color))
			painter.setPen(pen)
			painter.drawPath(path)


class _FillEnd:
	"""Adapts one end of a fill to the setter a ``Binding`` drives."""

	def __init__(self, fill: 'GaugeFill', end: str):
		self._fill = fill
		self._end = end

	def setMarkerValue(self, value) -> None:
		self._fill.setEnd(self._end, value)
