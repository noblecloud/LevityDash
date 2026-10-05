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
import PySide6
from collections.abc import Mapping
from enum import Enum
from functools import cached_property
from itertools import combinations
from math import atan2, floor, hypot, inf, isclose, isfinite, isinf
from numbers import Number
from typing import TYPE_CHECKING, Any, Dict, Iterator, Optional, Union

from numpy import ceil, cos, pi, radians, sin, sqrt
from PySide6.QtCore import QPoint, QPointF, QRectF
from PySide6.QtGui import QBrush, QGradient, QPainter, QPainterPath, QPen, QTransform, Qt
from PySide6.QtWidgets import QGraphicsPathItem, QStyleOptionGraphicsItem, QWidget

from LevityDash.lib.stateful import SourceType, StateProperty, Stateful
from LevityDash.lib.stateful_mixins import ColorGradientMixin
from LevityDash.lib.ui import Color, Gradient, UILogger
from LevityDash.lib.ui.Geometry import (
	Alignment, AlignmentFlag, Dimension, DimensionType, DisplayPosition, RelativeFloat, Size, parseSize, size_px,
)
from LevityDash.lib.ui.frontends.PySide.Modules.Displays import SurfaceCentered
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Annotations import AnnotationLabels, AnnotationText
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.curvetext import CurveMode, warp_path
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import SizeGroup
from LevityDash.lib.ui.frontends.PySide.utils import DebugPaint, addCrosshair, outline_path
from LevityDash.lib.utils import Axis
from LevityDash.lib.utils.shared import (
	INVERSE_GOLDEN_RATIO, Unset, clearCacheAttr, defer, factors, get, guarded_cached_property, radialPoint,
)
from WeatherUnits import Angle, Length, Measurement, Percentage

from .scale import GaugeValue, Numeric, _isWholeSteps, decode_measurement, filter_factors

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
			log.warning(f'Gauge {_gaugeKeyName(self.gauge)} ignored label text {value!r}: use a mapping, compass or compass-16')
			return None
		if not isinstance(value, Mapping):
			log.warning(f'Gauge {_gaugeKeyName(self.gauge)} ignored label text {value!r}: expected a mapping or compass')
			return None
		clean = {}
		for key, word in value.items():
			try:
				float(key)
			except (TypeError, ValueError):
				log.warning(f'Gauge {_gaugeKeyName(self.gauge)} label text skipped key {key!r}: not a number')
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
				log.warning(f'Gauge {_gaugeKeyName(self.gauge)} tick label format {spec!r} failed: {e!r}')
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
