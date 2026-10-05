import copy
import PySide6.QtGui
import numpy as np
from PySide6 import QtCore
from PySide6.QtCore import QPointF, QRectF, QPoint, QPropertyAnimation, QVariantAnimation, QTimer, Signal, QEasingCurve, QSizeF, Slot, QLineF, QObject
from PySide6.QtGui import (
	QFontMetricsF,
	QBrush, QFont, QPainter, QPainterPath,
	QPen, QPolygonF, QTransform, QRadialGradient, QGradient, QColor, Qt, QConicalGradient, QPainterPathStroker
)
from PySide6.QtWidgets import (
	QGraphicsItem, QGraphicsPathItem,
	QGraphicsScene, QStyleOptionGraphicsItem,
	QWidget, QGraphicsItemGroup
)
from enum import Enum
from functools import cached_property
from itertools import combinations
from math import inf, isclose,isfinite, isinf, floor, log10, atan2, hypot
from numbers import Number
from numpy import ceil, cos, pi, radians, sin, sqrt, number as np_number
from collections.abc import Mapping
from typing import Optional, Type, Union, Iterator, Iterable, TypeVar, Sequence, Dict

from LevityDash import LevityDashboard
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.expressions import Expression, ExpressionError
from LevityDash.lib.valuesource import openValueSource
from LevityDash.lib.plugins.plugin import AnySource
from LevityDash.lib.stateful import Binding, Stateful, StateProperty, SourceType
from LevityDash.lib.stateful_mixins import ColorGradientMixin
from LevityDash.lib.ui import UILogger, Color, Gradient
from LevityDash.lib.ui.Geometry import RelativeFloat, parseSize, DimensionType, size_px, Dimension, Size, Alignment, \
	AlignmentFlag, DisplayPosition, parseWidth, parseX, parseY, parseHeight, UnitDisplayPosition, ValueDisplayPosition
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays import SurfaceCentered, Surface
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Annotations import AnnotationText, AnnotationLabels
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.DisplayBase import Display
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.curvetext import CurveMode, WarpSpec, arcFit, normalizeCorner, warp_path
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Label import NonInteractiveLabel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import Text
from LevityDash.lib.ui.frontends.PySide.Modules.Handles import Handle
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import SizeGroup
from LevityDash.lib.ui.frontends.PySide.utils import DisplayType, addCrosshair, DebugPaint, SoftShadow, outline_path, \
	modifyTransformValues, rect_to_shape, addPath
from LevityDash.lib.utils import Axis
from LevityDash.lib.utils.data import MinMax
from LevityDash.lib.utils.shared import radialPoint, defer, factors, is_prime, Unset, clearCacheAttr, \
	INVERSE_GOLDEN_RATIO, closestStringInList, camelCase, guarded_cached_property, get, ClosestMatchEnumMeta
from WeatherUnits import Measurement, Angle, Wind, Humidity, auto as auto_wu, Length, Percentage

log = UILogger.getChild('Gauge')


def filter_factors(
	numbers: Iterable[int],
	required_factors: set[int] = None,
	included_factors: set[int] = None,
	excluded_factors: set[int] = None,
) -> set[int]:
	if required_factors is None:
		required_factors = set()

	return {
		n for n in numbers
		if required_factors <= (f := factors(int(n)))
		and (not included_factors or included_factors & f)
		and (not excluded_factors or not excluded_factors & f)
	}


def _isWholeSteps(span, interval) -> bool:
	"""Whether `interval` divides `span` into a whole number of steps, within float error."""
	try:
		span, interval = float(span), float(interval)
		steps = round(span / interval, 9)
	except (TypeError, ValueError, ZeroDivisionError, OverflowError):
		return False
	return steps == int(steps)


def formatDuration(minutes) -> str:
	"""A number of minutes as ``4h 49m``, or ``49m`` under an hour. Pure."""
	try:
		total = int(round(float(minutes)))
	except (TypeError, ValueError):
		return '\u22ef'
	sign, total = ('-' if total < 0 else ''), abs(total)
	hours, mins = divmod(total, 60)
	return f'{sign}{hours}h {mins:02d}m' if hours else f'{sign}{mins}m'


def shortestDelta(current: float, target: float, span: float = 360.0) -> float:
	"""The signed turn from ``current`` to ``target`` that crosses the join the short way.

	``span`` is one full turn of the scale. The result lies in ``[-span/2, span/2]``.
	"""
	delta = (target - current) % span
	return delta - span if delta > span / 2 else delta


class GaugeItem:
	"""
	Base class for all gauge items.  This class provides a reference to the gauge that the item belongs to
	and will raise a ValueError if no gauge is provided.
	"""

	_gauge: 'Gauge'

	def __extract_gauge(self, args, kwargs):
		gauge = get(kwargs, 'gauge' 'parent', default=None, expectedType=Gauge)
		if gauge is None:
			gauge = next((arg for arg in args if isinstance(arg, Gauge)), None)
		if gauge is None:
			gauge = next((kwarg for kwarg in kwargs.values() if isinstance(kwarg, Gauge)), None)
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


Numeric = Union[int, float, complex, np_number, Measurement]
GaugeValue = TypeVar('GaugeValue', bound=Numeric, covariant=True)


class StatefulGaugeItem(GaugeItem, Stateful):

	def __init__(self, *args, **kwargs):
		super(StatefulGaugeItem, self).__init__(*args, **kwargs)
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
				value = size_px(self.length, relative_to := self.gauge.radius)
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
		while not isinstance(parent, Gauge):
			try:
				parent = parent.parentItem()
			except AttributeError:
				return None
		return parent


class StatefulGaugePathItem(Stateful, GaugePathItem):

	def __init__(self, *args, **kwargs):
		super(StatefulGaugePathItem, self).__init__(*args, **kwargs)
		self.prep_init(args=args, kwargs=kwargs, stateful_parent=self.gauge)


@DebugPaint
class GaugeArc(StatefulGaugePathItem):

	_weight_scale = 0.75

	@property
	def safe_area(self) -> QPainterPath:
		return QPainterPath(self.shape())

	@property
	def scene_safe_area(self) -> QPainterPath:
		return self.mapToScene(self.shape())

	def __init__(self, *args, **kwargs):
		super(GaugeArc, self).__init__(*args, **kwargs)
		self.add_defaults_to_state(kwargs)
		self.state = kwargs

	def _debug_paint(self, painter: QPainter, opt, widget):
		color = QColor(Qt.GlobalColor.yellow)
		color.setAlphaF(0.5)
		addPath(painter, self.shape(), fill=color, color=QColor(Qt.GlobalColor.transparent))
		self._normal_paint(painter, opt, widget)
		# addCrosshair(painter, pos=self.path().boundingRect().center(), color=color, weight=4, size=10)

	def setPen(self, pen, *args, **kwargs):
		super(GaugeArc, self).setPen(pen, *args, **kwargs)

	@property
	def center(self):
		return self.gauge.rect().center()

	@property
	def center_offset(self) -> QPointF:
		return self._center_offset

	@property
	def centered_gauge_rect(self):
		rect = QRectF(self.gauge.gaugeRect)
		rect.moveCenter(QPoint(0, 0))
		return rect

	@defer
	def makeShape(self):
		inner_safe_radius = self.gauge.safe_radius
		outer_safe_radius = self.gauge.exterior_safe_radius

		width = outer_safe_radius - inner_safe_radius

		path = QPainterPath()
		path.setFillRule(Qt.FillRule.WindingFill)

		inner_rect = QRectF(-inner_safe_radius, -inner_safe_radius, inner_safe_radius * 2, inner_safe_radius * 2)
		radius_rect = QRectF(-outer_safe_radius, -outer_safe_radius, outer_safe_radius * 2, outer_safe_radius * 2)

		# draw the inner arc
		angle = self.startAngle
		path.arcMoveTo(inner_rect, -angle + 90)
		start_pos = path.currentPosition()
		path.arcTo(inner_rect, -angle + 90, -self.fullAngle)

		# draw a line going out from the inner arc to the outer arc
		current_pos = path.currentPosition()
		width_vector = radialPoint(QPointF(0, 0), width, self.endAngle - 90)
		path.lineTo(current_pos + width_vector)

		# draw the outer arc but in the opposite direction
		path.arcTo(radius_rect, -self.endAngle + 90, self.fullAngle)

		# draw a line going back to the inner arc
		path.lineTo(start_pos)

		path.closeSubpath()

		rect = self.parentItem().boundingRect()
		rect.moveCenter(path.boundingRect().center())
		pen = self.pen()
		path.addPath(outline_path(
			self.path(),
			weight=pen.widthF(),
			cap_style=pen.capStyle(),
			join_style=pen.joinStyle(),
			dash_pattern=pen.dashPattern()
		))
		self._shape = path

	def draw(self):
		self.resetTransform()
		path = QPainterPath()
		rect = self.centered_gauge_rect
		path.arcMoveTo(rect, -self.startAngle + 90)
		path.arcTo(rect, -self.startAngle + 90, -self.fullAngle)
		self._center_offset = path.boundingRect().center()
		self.gauge.update_center_offset(self._center_offset)
		self.setPath(path)
		self.makeShape()

	def refresh(self):
		self.draw()
		self.updateAppearance()
		self.setPos(self.gauge.center)
		self.setZValue(-800)

	def updateAppearance(self):
		pen = QPen(self.gauge.pen)
		if weight := self.weight_px:
			pen.setWidthF(weight)
			pen.setCapStyle(self.capStyle)
			if (color := self.color) is not None:
				pen.setBrush(QBrush(color.QColor))
			if (gradient := self.gradient) is not None:
				brush = self.gauge.map_gradient_to(gradient, self)
				pen.setBrush(brush)
		else:
			pen.setWidthF(0)
			pen.setBrush(Qt.NoBrush)

		self.setPen(pen)
		self.makeShape()
		self.setPos(self.gauge.center)

	def shape(self):
		return self._shape

	@StateProperty(key='color', default=None, after=refresh, allowNone=True)
	def color(self) -> Color | None:
		"""Colour of the track. Defaults to the gauge colour; a dark grey gives the unfilled-track look."""
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

	@StateProperty(key='gradient', default=None, after=refresh, decoder=Gradient.decode)
	def gradient(self) -> Gradient | None:
		return getattr(self, '_gradient', None)

	@gradient.setter
	def gradient(self, value: Gradient | None):
		self._gradient = value

	@StateProperty(key='weight', default=Size.Width(0.05, relative=True), after=refresh, allowNone=False, repr=True)
	def weight(self) -> Size.Width | Length:
		return self._weight

	@weight.setter
	def weight(self, value: Size.Width | Length):
		self._weight = value

	@weight.decode
	def weight(self, value: Size.Width | Length) -> float:
		return parseWidth(value, type(self).weight.default(type(self), self, update_source=False))

	@property
	def weight_px(self) -> float:
		return size_px(self.weight, self.gauge.radius, dimension=DimensionType.width)

	@StateProperty(key='start-angle', default=-120, after=refresh, allowNone=False, repr=True)
	def startAngle(self) -> float | int:
		return self._start_angle

	@startAngle.setter
	def startAngle(self, value: float | int):
		self._start_angle = value

	@StateProperty(key='end-angle', default=120, after=refresh, allowNone=False, repr=True)
	def endAngle(self) -> float | int:
		return self._end_angle

	@endAngle.setter
	def endAngle(self, value: float | int):
		self._end_angle = value

	@StateProperty(key='cap', default=Qt.PenCapStyle.FlatCap, after=refresh, allowNone=False)
	def capStyle(self) -> Qt.PenCapStyle:
		return self._cap_style

	@capStyle.setter
	def capStyle(self, value: Qt.PenCapStyle):
		self._cap_style = value

	@capStyle.decode
	def capStyle(value) -> Qt.PenCapStyle:
		caps: dict[str, Qt.PenCapStyle] = dict(Qt.PenCapStyle.__members__)
		capNames = list(caps.keys())
		cap = closestStringInList(value, capNames)
		return caps[cap]

	@capStyle.encode
	def capStyle(value) -> str:
		if value is None:
			return 'round'
		try:
			return camelCase(value.name.decode().strip('Cap'), titleCase=False)
		except AttributeError:
			return camelCase(value.name.strip('Cap'), titleCase=False)

	@property
	def fullAngle(self) -> float | int:
		return self.endAngle - self.startAngle

	@property
	def inverted(self) -> bool:
		"""Returns a bool of if the start angle is greater than the end angle"""
		return self.startAngle > self.endAngle


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
		angle = radians(self.angle)
		cosI, sinI = cos(angle), sin(angle)
		center = QPointF(0, 0)
		cx = center.x()
		cy = center.y()
		radius = self.radius
		length = self.properties.length_px

		x1 = x2 = radius * cosI
		y1 = y2 = radius * sinI

		match self.properties.position:
			case DisplayPosition.Below | DisplayPosition.Inside:
				x2 -= length * cosI
				y2 -= length * sinI
			case DisplayPosition.Above | DisplayPosition.Outside:
				x2 += length * cosI
				y2 += length * sinI
			case DisplayPosition.Center | _:
				half_x = length * cosI / 2
				half_y = length * sinI / 2

				x2 += half_x
				x1 -= half_x

				y2 += half_y
				y1 -= half_y

				if length > 0: # keeps the outermost as the end point
					x1, y1, x2, y2 = x2, y2, x1, y1

		p1 = QPointF(x1, y1)
		self.startPoint = p1
		p2 = QPointF(x2, y2)
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
		return size_px(self.width, self.gauge.radius, dimension=DimensionType.width)

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
		return size_px(self.length, self.gauge.radius, dimension=DimensionType.height)

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
		return size_px(self.offset, self.gauge.radius, dimension=DimensionType.height)

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
		radius = self.gauge.radius
		if size is None:
			return default * radius
		return size_px(size, radius, dimension=dimension) or 0.0

	def _pivotY(self) -> float:
		return self.offset_px

	def _hubPath(self) -> Optional[QPainterPath]:
		hub = self.hub
		if hub is None or self.type.value not in self._PIVOT_STYLES:
			return None
		diameter = size_px(hub, self.gauge.radius, dimension=DimensionType.width) or 0.0
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
			halo = size_px(self.halo, self.gauge.radius, dimension=DimensionType.width) or 0.0
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
			r = size_px(self.tailDot, self.gauge.radius, dimension=DimensionType.width) / 2
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
		dot = (size_px(self.tailDot, radius, dimension=DimensionType.width) or 0.0) if self.tailDot is not None else 0.0
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


# Unit positions that hang the unit under the value. `float-under` is the
# Realtime text display's name for it; `below` is the gauge's older one.
_UNIT_UNDER_VALUE = frozenset({UnitDisplayPosition.Below, UnitDisplayPosition.FloatUnder})


def _gaugeKeyName(gauge: 'Gauge') -> str:
	"""The key of the panel that owns ``gauge``, for log messages. Never raises."""
	try:
		return str(gauge.parent.key)
	except Exception:
		return '<unkeyed>'


def _markerText(spec) -> str:
	"""The ``value:`` text of a marker spec, for log messages. Never raises."""
	try:
		return str(spec.get('value'))
	except Exception:
		return str(spec)


#: What a marker's ``time:`` can follow. Each is one turn of the dial, whatever
#: the range: ``hour`` a 12 hour turn, ``minute`` and ``second`` 60 s, ``day`` 24 hours.
CLOCK_HANDS = ('hour', 'minute', 'second', 'day')


def clockTurn(hand: str, hours: int, minutes: int, seconds: float) -> float:
	"""How far round the dial a clock ``hand`` is at a time of day, from 0 up to (not including) 1. Pure.

	The hour and minute hands carry the smaller units, so they sweep rather than step.
	"""
	match hand:
		case 'hour':
			return ((hours % 12) + minutes / 60 + seconds / 3600) / 12
		case 'minute':
			return (minutes + seconds / 60) / 60
		case 'second':
			return seconds / 60
		case 'day':
			return (hours + minutes / 60 + seconds / 3600) / 24
	raise ValueError(f'a clock hand is one of {", ".join(CLOCK_HANDS)}, not {hand!r}')


def parseClockTime(text: str) -> tuple[int, int, float]:
	"""``'10:08'`` or ``'10:08:36'`` as ``(hours, minutes, seconds)``."""
	parts = str(text).strip().split(':')
	if not 2 <= len(parts) <= 3:
		raise ValueError(f'a clock time is HH:MM or HH:MM:SS, not {text!r}')
	hours, minutes = int(parts[0]), int(parts[1])
	seconds = float(parts[2]) if len(parts) == 3 else 0.0
	if not (0 <= hours < 24 and 0 <= minutes < 60 and 0 <= seconds < 60):
		raise ValueError(f'{text!r} is not a time of day')
	return hours, minutes, seconds


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
			if (source := openValueSource(raw, f'Gauge {_gaugeKeyName(self.gauge)} marker value', 'the marker stays hidden')) is not None:
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
				from datetime import datetime
				now = datetime.now()
				hours, minutes, seconds = now.hour, now.minute, now.second + now.microsecond / 1e6
			self._clockFraction = clockTurn(self._clockHand, hours, minutes, seconds)
		except Exception as e:
			log.warning(f'Gauge {_gaugeKeyName(self.gauge)} clock hand stopped: {e}')
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
				log.warning(f'Gauge {_gaugeKeyName(gauge)} cannot place marker value {value!r}: {e}')
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
		name = _gaugeKeyName(self.gauge)
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
				weight = size_px(zone['weight'], gauge.radius, dimension=DimensionType.width) if zone['weight'] is not None else arcWeight
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
			log.warning(f'Gauge {_gaugeKeyName(gauge)} zones not drawn: {e}')
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


class _FillEnd:
	"""Adapts one end of a fill to the setter a ``Binding`` drives."""

	def __init__(self, fill: 'GaugeFill', end: str):
		self._fill = fill
		self._end = end

	def setMarkerValue(self, value) -> None:
		self._fill.setEnd(self._end, value)


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
		name = _gaugeKeyName(self.gauge)
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
			log.debug(f'Gauge {_gaugeKeyName(self.gauge)} fill not drawn yet: {e}')

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
				log.warning(f'Gauge {_gaugeKeyName(gauge)} cannot place fill {start!r} to {end!r}: {e}')
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
		weight = size_px(self._weight, gauge.radius, dimension=DimensionType.width) if self._weight is not None else gauge.arc.weight_px
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
				gapPx = size_px(self._gap, gauge.radius, dimension=DimensionType.width) or 0
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


class GaugeCaption(GaugePathItem):
	"""A small line of text above (``caption``) or below (``sub-label``) the centre value.

	The spec is a string (static text) or a mapping: ``text`` (may hold ``{}``
	where the value goes), ``value`` (a key or expression to show; with no
	``format`` it prints as the value does, unit and all), ``format``
	(``duration`` turns minutes into ``4h 49m``; any other string is a Python
	format spec, and a mapping is the value label's ``format``, e.g. ``{precision: 0, show_unit: false}``), ``warp`` (bend the text along a
	circle, see `WarpSpec`; then ``gap`` and ``offset`` do not apply), ``size`` (text height as a share of the dial's diameter,
	default 7%), ``color``, ``weight`` (``bold``), ``gap`` (distance from the
	value, a share of the diameter, default 2%) and ``offset`` (``{x, y}``, shares of the
	diameter, added to where the gap puts it). A value source with no value
	yet shows nothing. A bad spec logs the gauge key and shows nothing.
	"""

	Z_VALUE = -400

	_text = ''
	_template = None
	_value = None
	_hasValue = False
	_format = None
	_size = None
	_gap = None
	_color: Optional[QColor] = None
	_bold = False
	_offset: Optional[tuple] = None
	_binding: Optional[Binding] = None
	_warp: Optional[WarpSpec] = None

	def __init__(self, gauge: 'Gauge', side: str):
		super().__init__(gauge)
		self._side = side
		self.setPen(Qt.PenStyle.NoPen)
		self.hide()

	def close(self):
		if self._binding is not None:
			self._binding.unlink()
			self._binding = None

	def configure(self, spec) -> None:
		self.close()
		if isinstance(spec, str):
			spec = {'text': spec}
		name = _gaugeKeyName(self.gauge)
		unknown = set(spec) - {'text', 'value', 'format', 'size', 'color', 'weight', 'gap', 'offset', 'warp'}
		if unknown:
			log.warning(f'Gauge {name} {self._side} ignored unknown keys {sorted(map(str, unknown))}')
		self._offset = _decodeOffset(spec.get('offset'))
		self._warp = WarpSpec.decode(spec.get('warp'))
		self._template = spec.get('text')
		self._hasValue = False
		self._format = spec.get('format')
		self._size = parseHeight(spec.get('size', '7%'), None)
		self._gap = parseHeight(spec.get('gap', '2%'), None)
		self._color = Color.decode(spec['color']).QColor if spec.get('color') is not None else None
		self._bold = str(spec.get('weight', '')).lower() == 'bold'
		raw = spec.get('value')
		if raw is not None:
			if (source := openValueSource(raw, f'Gauge {name} {self._side} value', 'the text stays hidden')) is not None:
				self._binding = Binding(source, self.setCaptionValue)
		self._rebuildText()

	def setCaptionValue(self, value) -> None:
		"""Set the shown value. GUI thread only."""
		self._value, self._hasValue = value, True
		self._rebuildText()
		self.gauge._syncCaptions()

	def _valueText(self) -> str:
		value, spec = self._value, self._format
		if spec == 'duration':
			return formatDuration(value)
		if spec is not None:
			try:
				if isinstance(value, Measurement):
					return value.__format__('', **spec) if isinstance(spec, Mapping) else value.__format__(spec)
				return format(float(value), spec)
			except Exception:
				return str(value)
		return str(value)

	def _rebuildText(self) -> None:
		if self._binding is not None and not self._hasValue:
			text = ''
		elif self._hasValue:
			shown = self._valueText()
			text = shown if self._template is None else str(self._template).replace('{}', shown)
		else:
			text = '' if self._template is None else str(self._template)
		self._text = text
		self._layoutDirty = True

	def _placeWarped(self, font) -> None:
		"""Bend the text along the warp circle instead of setting it beside the value.
		`gap` and `offset` do not apply: the circle decides where the text sits."""
		gauge = self.gauge
		card = gauge.parentItem() or gauge
		cardRect = gauge.mapRectFromItem(card, card.rect() if hasattr(card, 'rect') else card.boundingRect())
		place = self._warp.resolve(cardRect, (gauge.center, gauge.radius))
		fm = QFontMetricsF(font)
		scale = arcFit(fm.horizontalAdvance(self._text), fm.ascent() + fm.descent(), 1.0, place.radius)
		view = getattr(self.scene(), 'viewScale', None)
		epsilon = 0.25 / ((getattr(view, 'x', 1) or 1) if view is not None else 1)
		path = warp_path(self._text, font, scale, place.radius, place.side, self._warp.mode, epsilon, self._warp.amount)
		self.prepareGeometryChange()
		self.setPath(path)
		self.setTransform(QTransform().scale(scale, scale))
		self.setRotation(place.rotation)
		self.setPos(place.point)
		color = self._color
		if color is None:
			color = QColor(gauge.defaultColor)
			color.setAlphaF(0.65)
		self.setBrush(QBrush(color))
		self.setZValue(self.Z_VALUE)
		self.show()

	def refresh(self):
		"""Place the text against the centre value. Never raises."""
		gauge = self.gauge
		try:
			if not self._text:
				self.hide()
				return
			font = gauge.tickFont
			font.setPixelSize(max(1, int(size_px(self._size, gauge.radius * 2, dimension=DimensionType.height) or 1)))
			if self._bold:
				font.setWeight(QFont.Weight.Bold)
			path = QPainterPath()
			path.addText(0, 0, font, self._text)
			rect = path.boundingRect()
			if rect.isEmpty():
				self.hide()
				return
			if self._warp is not None:
				self._placeWarped(font)
				return
			self.setTransform(QTransform())
			self.setRotation(0)
			anchor = gauge._valueAnchor()
			gap = size_px(self._gap, gauge.radius * 2, dimension=DimensionType.height) or 0.0
			x = anchor.center().x() - rect.center().x()
			if self._side == 'caption':
				y = anchor.top() - gap - rect.bottom()
			else:
				y = anchor.bottom() + gap - rect.top()
			if self._offset:
				x += self._offset[0] * gauge.radius * 2
				y += self._offset[1] * gauge.radius * 2
			self.prepareGeometryChange()
			self.setPath(path)
			self.setPos(x, y)
			color = self._color
			if color is None:
				color = QColor(gauge.defaultColor)
				color.setAlphaF(0.65)
			self.setBrush(QBrush(color))
			self.setZValue(self.Z_VALUE)
			self.show()
		except Exception as e:  # noqa: BLE001 - layout must never abort a load
			log.warning(f'Gauge {_gaugeKeyName(gauge)} could not place its {self._side}: {e!r}')


class GaugeText(AnnotationText, GaugeItem):
	def __init__(self, *args, **kwargs):
		super(GaugeText, self).__init__(*args, **kwargs)


def _decodeOffset(value) -> Optional[tuple]:
	"""`{x, y}` (or `[x, y]`) as a pair of floats; None for nothing or all zero."""
	if value is None:
		return None
	if isinstance(value, Mapping):
		pair = (value.get('x', 0), value.get('y', 0))
	elif isinstance(value, (list, tuple)) and len(value) == 2:
		pair = tuple(value)
	else:
		raise ValueError(f'offset must be a mapping {{x, y}} or a pair, got {value!r}')
	x, y = float(pair[0]), float(pair[1])
	return None if x == 0 and y == 0 else (x, y)


def _shiftByOffset(box) -> None:
	"""Move a label's text box by its label's `offset`, in the gauge's own coordinates.
	Run after a refit has put the box where the layout wants it, so the shift never builds up."""
	if getattr(box, '_warpActive', False):
		return  # a warped label is pinned to its circle; `offset` would drag it off
	try:
		shift = box.parent.offsetPx()
	except Exception as e:  # noqa: BLE001 - layout must never abort a load
		log.warning(f'could not read a label offset: {e!r}')
		return
	if shift.isNull():
		return
	t = box.transform()
	box.setTransform(QTransform(t.m11(), t.m12(), t.m21(), t.m22(), t.dx() + shift.x(), t.dy() + shift.y()))


class GaugeLabel(NonInteractiveLabel, ColorGradientMixin, GaugeItem):

	def __init__(self, *args, **kwargs):
		GaugeItem.__init__(self, *args, **kwargs)
		assert isinstance(self.gauge, Gauge)
		NonInteractiveLabel.__init__(self, *args, **kwargs)

	def _get_color_value(self) -> Number:
		return self.gauge.value

	def _set_fill_brush(self, color: Color):
		self.textBox.setBrush(QBrush(color))

	@StateProperty(key='visible', default=True, allowNone=False, singleVal=True)
	def visible(self) -> bool:
		# The textBox is reparented to the gauge (see the `valueLabel` factory),
		# so the label wrapper's own visibility says nothing about what is drawn
		# - the textBox is the thing the viewer sees.
		return self.textBox.isVisible()

	@visible.setter
	def visible(self, value: bool):
		self.textBox.setVisible(value)
		if (gauge := self.gauge) is not None:
			# full_gauge_path counts only visible labels, so the cached centre
			# is stale the moment this changes.
			gauge.__dict__.pop('full_gauge_path', None)

	@StateProperty(key='offset', default=None, allowNone=True)
	def offset(self) -> Optional[tuple]:
		"""Shift the label from where it would sit: ``{x, y}`` as shares of the dial's diameter
		(``{x: 0, y: -0.1}`` is a tenth of the diameter up). Gauge Studio writes it when you drag the label."""
		return getattr(self, '_offset', None)

	@offset.setter
	def offset(self, value: Optional[tuple]):
		self._offset = value

	@offset.decode
	def offset(self, value) -> Optional[tuple]:
		return _decodeOffset(value)

	@offset.encode
	def offset(self, value: Optional[tuple]) -> Optional[dict]:
		return None if not value else {'x': round(value[0], 4), 'y': round(value[1], 4)}

	def offsetPx(self) -> QPointF:
		"""`offset` in gauge pixels."""
		value = getattr(self, '_offset', None)
		if not value:
			return QPointF()
		d = self.gauge.radius * 2
		return QPointF(value[0] * d, value[1] * d)


class GaugeValueLabel(GaugeLabel):

	parent: 'Gauge'

	_debug_paint_color = Color.randomColor.QColor

	__defaults__ = {
		'format': {
			# `show_unit` hides the WORD unit - 'mph', 'inHg' - which reads
			# fine as its own label beneath the dial.
			#
			# `unit_symbol` is deliberately NOT set here. It used to be False,
			# which also stripped '%' and '°' - symbols that belong glued to
			# the number, so a humidity gauge read a bare '56'. And it cannot
			# simply be flipped to True: unit_symbol is a *string*, not a
			# flag, so True renders the literal word ('61True'). Omitting it
			# lets each unit class supply its own symbol, which is the point.
			'show_unit': False,
		},
		# Relative, not the absolute 100px this used to be: a gauge is sized
		# by its panel, so a fixed-pixel label is correct at exactly one gauge
		# size and wildly wrong everywhere else - in a small panel it drew the
		# value several times larger than the dial it belonged to.
		'geometry': {
			'x': '0px',
			'y': '0px',
			'width': '45%',
			'height': '28%',
		},
		'margins': ('0', '0', '0', '0'),
	}

	class TextBox(Text):
		parent: 'GaugeValueLabel'
		surface: 'Gauge'

		@Text.alignment.getter
		def alignment(self):
			return self.parent.alignment

		@property
		def _position(self) -> ValueDisplayPosition:
			if (position := self.parent.position) is ValueDisplayPosition.Auto:
				position = self.parent.position_auto()
			return position

		def __rich_repr__(self):
			yield from super().__rich_repr__()
			yield 'alignment', self.alignment

		def _format_value_func(self, value):
			try:
				return self.parent.format_value(value.value)
			except AttributeError:
				return self.parent.format_value(value)

		# def paint(self, painter: QPainter, option, widget):
		# 	f = QRadialGradient(rainbow)
		# 	f.setRadius(max(self.boundingRect().width(), self.boundingRect().height()))
		# 	# f.setCenter(-self.boundingRect().topLeft())
		# 	# f.setFocalPoint(-self.boundingRect().topLeft())
		# 	f.setCoordinateMode(QGradient.CoordinateMode.LogicalMode)
		# 	painter.save()
		# 	# painter.setOpacity(0.5)
		# 	# painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
		#
		# 	shape = self.shape()
		# 	addPath(painter, shape, fill=f, color=Qt.GlobalColor.transparent)
		#
		# 	# shape = self.mapFromParent(self.parentItem()._gauge_path())
		# 	# addPath(painter, shape, fill=QBrush(Qt.GlobalColor.red), color=Qt.GlobalColor.transparent)
		#
		# 	painter.restore()
		# 	super().paint(painter, option, widget)
		#
		# 	painter.setBrush(QBrush(Qt.white))
		# painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Difference)

		# gauge = self.parent.parent
		# for collision_item in self.collidingItems():
		# 	if not gauge.isAncestorOf(collision_item):
		# 		continue
		# 	item_path = self.mapFromItem(collision_item, collision_item.shape())
		# 	painter.drawPath(item_path)

		@property
		def limitRect(self) -> QRectF:
			if self._position in (DisplayPosition.Left, DisplayPosition.Right):
				return self.parent.parent._sideValueRect().translated(-self.pos())
			arc = self.parent.parent.arc.sceneBoundingRect()
			# r = max(arc.width(), arc.height()) / sqrt(2)
			# g = self.parent.parent
			# r = g.radius
			# r /= self.transform().m11()
			# r = QRectF(0, 0, r, r)
			# r.moveCenter(self.mapFromItem(g, g.center))
			r = self.mapRectFromScene(arc)

			# self._debug_paint_shape = rect_to_shape(r)
			return r

		def getTextPosition(self, limitRect: QRectF = None) -> QPointF:

			gauge: Gauge = self.parent.parent
			arc: GaugeArc = gauge.arc

			min_angle, max_angle = sorted((arc.startAngle, arc.endAngle))

			angle_spread = max_angle - min_angle

			# if angle_spread <= 200:
			# 	return gauge.center

			arc_center = arc.mapToParent(arc.path().boundingRect().center())
			gauge_center = gauge.center

			match self._position:
				case ValueDisplayPosition.Left | ValueDisplayPosition.Right:
					# Beside the dial: the middle of the strip the dial left free.
					return gauge._sideValueRect().center()
				case ValueDisplayPosition.Inline:
					diff = arc_center - gauge_center
					return arc_center - (diff * (angle_spread / 360))
				case ValueDisplayPosition.Center:
					return gauge.center
				case ValueDisplayPosition.Top:
					return gauge.center + QPointF(0, max(-gauge.safe_radius, self.mapRectFromItem(gauge, gauge.gaugeRect).top()))
					# return gauge.center + QPointF(0, -gauge.safe_radius)
				case ValueDisplayPosition.Bottom:
					# Stands on the panel's bottom edge, above the strip a unit
					# label below it needs; bottom-aligned, so it grows upward
					# until getTextScale finds it touching the dial. It used to
					# be centred on the arc's lowest point, which left no room
					# under it and none to shrink into.
					return QPointF(gauge.center.x(), gauge.rect().bottom() - self._unit_reserve() - 1)
				case _:
					raise NotImplementedError

		def _valueAccessor(self):
			return self.parent.parent.value

		@defer(pool_attr='action_pool')
		def updateTransform(self, rect: QRectF = None, updateShared: bool = True, updatePath: bool = True, reason: str = None, *args):
			super().updateTransform(rect, updateShared, updatePath, reason=reason, *args)
			_shiftByOffset(self)
			# A refit resets this label to where the fit puts it, and Gauge.recenter
			# is not called again. Re-hang the unit from the value as it now is.
			self.parent.parent._syncUnitUnderValue()
			self.parent.parent._syncCaptions()

		def getTextScale(self, textRect: QRectF = None, limitRect: QRectF = None) -> float:

			"""
			Modifies the local transform until no there are no collisions, restores the original transform and returns the scale.
			"""

			gauge = self.parent.parent
			if self._position in (DisplayPosition.Left, DisplayPosition.Right):
				# The strip beside the dial is empty by construction, so there is
				# nothing to collide with: fit the glyphs to the strip.
				strip = gauge._sideValueRect()
				strip = strip.adjusted(*([self.parent.value_padding_px] * 2), *([-self.parent.value_padding_px] * 2))
				scale = Text.getTextScale(self, textRect, strip.translated(-self.pos()))
				base_path = self.path()
				if (size := self.parent.size) is not None and (glyph_height := base_path.boundingRect().height()) > 0:
					scale = min(scale, size_px(size, gauge.radius * 2) / glyph_height)
				return round(scale, 4)

			scale = super(GaugeValueLabel.TextBox, self).getTextScale()

			gauge_path = gauge._gauge_path()

			if self._position is DisplayPosition.Inline:
				# Without the recenter shift: that shift is computed from this
				# label's size, so fitting against the shifted needle would feed
				# back into the layout it depends on.
				needle = gauge.needle
				unshifted, _ = needle.transform().inverted()
				gauge_path.addPath(gauge.mapFromItem(needle, unshifted.map(needle.shape())))

			# PURE. The base class documents that getTextScale must not mutate
			# the transform, because a SizeGroup calls it on every member to
			# pick a shared scale - and this override used to violate that,
			# applying each trial scale to the live item and asking the scene
			# "am I colliding now?". Probing one member moved it in the scene,
			# which changed the answers for the others, and the group then
			# applied a shared scale that invalidated whatever the probe had
			# concluded. That is why collision fitting and size groups fought
			# each other.
			#
			# The test is the same, done arithmetically: this item's parent IS
			# the gauge (the factory reparents textBox to it), so a transform
			# built from the label's position and a trial scale maps the glyph
			# path into gauge coordinates without touching anything.
			#
			# Built from getTextPosition, NOT self.transform(): updateTransform
			# resets the transform to identity before asking for a scale, so
			# the old copy of it tested every trial at the gauge's top-left
			# corner. That always failed `bounds.contains`, and every gauge
			# value sat on the 0.2 floor whatever room it had.
			base_path = self.path()
			origin = self.getTextPosition(limitRect)
			# Which box the label has to stay inside depends on where it sits.
			# A Center/Inline label lives among the dial's own parts, so the
			# dial's square is the right constraint. A Below/Above one is
			# deliberately OUTSIDE the dial, and judging it against gaugeRect
			# rejected every size that cleared the graduations - the wind value
			# measured 'outside the dial but colliding with nothing' and was
			# shrunk anyway, all the way to the floor. Those positions belong
			# to the panel, not the dial.
			if self._position in (DisplayPosition.Center, DisplayPosition.Inline):
				bounds = gauge.gaugeRect
			else:
				bounds = gauge.rect()

			reserve = self._unit_reserve()
			gap = self.parent.value_padding_px

			# A bottom value hangs under the needle's pivot. The needle is not
			# part of gauge_path here (only an Inline value dodges it), so
			# without this the label grew upward until it touched the arc and
			# covered the hub. Its top must stay below the hub's lowest point.
			hub_bottom = None
			if self._position is DisplayPosition.Below and gauge.needle.type is Needle.Type.Needle:
				needle = gauge.needle
				hub_bottom = gauge.center.y() + needle.offset_px + needle.width_px * 0.6 + gauge.radius * 0.03

			gauge_bounds = gauge_path.boundingRect()

			def collides_at(trial: float) -> bool:
				t = QTransform.fromTranslate(origin.x(), origin.y())
				t.scale(trial, trial)
				candidate = t.map(base_path)
				if hub_bottom is not None and candidate.boundingRect().top() < hub_bottom:
					return True
				if reserve:
					# The unit hangs beneath the value, so the value has to
					# leave it a strip as wide as itself.
					rect = candidate.boundingRect()
					candidate.addRect(QRectF(rect.left(), rect.bottom(), rect.width(), reserve))
				if not bounds.contains(candidate.boundingRect()):
					return True
				# Clear of the dial's parts by a gap, not merely not touching:
				# without one, a bottom value grew until its edge stood against
				# the end tick labels beside it.
				# The padded shape is the glyphs plus a stroke around them.
				# Testing the two against the dial one after the other answers
				# the same as testing their union, which is slow to build. The
				# dial path has thousands of segments, and a boolean test
				# against all of them costs milliseconds per step. Cut it to
				# the box the label can touch first (a rectangle clip is
				# cheap); only the few segments inside are left to test.
				reach = candidate.boundingRect().adjusted(-gap, -gap, gap, gap) if gap else candidate.boundingRect()
				if not reach.intersects(gauge_bounds):
					return False
				clip = QPainterPath()
				clip.addRect(reach.adjusted(-1, -1, 1, 1))
				near = gauge_path.intersected(clip)
				if near.isEmpty():
					return False
				if gap and outline_path(candidate, gap * 2).intersects(near):
					return True
				return candidate.intersects(near)

			# The floor is relative: a bare 0.2 is in glyph-path units, so it
			# meant something different for every font size and stopped the
			# value long before it cleared the dial.
			# Steps of 5% down from the start scale. The answer is the first
			# step that is clear, or the step that reaches the floor. Collision
			# only gets rarer as the label shrinks, so bisect over the step
			# count instead of testing every step in turn.
			floor = scale * 0.2
			start = scale
			steps = 0
			while start * 0.95 ** steps > floor:
				steps += 1
			lo, hi = 0, steps  # the answer is in lo..hi; `hi` is accepted untested
			while lo < hi:
				mid = (lo + hi) // 2
				if collides_at(start * 0.95 ** mid):
					lo = mid + 1
				else:
					hi = mid
			scale = start
			for _ in range(lo):
				scale *= 0.95

			# `size` caps the glyph height at a share of the dial's diameter,
			# so a short value ('N', '0') stays as small as a long one.
			if (size := self.parent.size) is not None and (glyph_height := base_path.boundingRect().height()) > 0:
				scale = min(scale, size_px(size, gauge.radius * 2) / glyph_height)

			return round(scale, 4)

		def _unit_reserve(self) -> float:
			"""Height, in gauge pixels, a visible unit label below the value needs."""
			gauge = self.parent.parent
			unit = getattr(gauge, '_unitLabel', None)
			if not isinstance(unit, GaugeUnit) or not unit.textBox.isVisibleTo(gauge):
				return 0
			try:
				if unit.textBox._position not in _UNIT_UNDER_VALUE:
					return 0
				return unit.height_px + self.parent.value_padding_px
			except Exception as e:  # noqa: BLE001 - sizing must never abort a load
				log.warning(f'Gauge {_gaugeKeyName(gauge)} could not size its unit label: {e!r}')
				return 0

		_shapePath: QPainterPath = QPainterPath()

		def setPath(self, path: QPainterPath):
			matrix = self.transform()
			scale_x = matrix.m11() * self.scale()
			scale_y = matrix.m22() * self.scale()
			scale_value = (self.scaleSelection(scale_x, scale_y) or 1)
			self._debug_paint_shape = self._shape = outline_path(self._shapePath or path, self.parent.value_padding_px / scale_value)
			super().setPath(path)

		_shape: QPainterPath = QPainterPath()

		def setTransform(self, matrix: QTransform, **kwargs) -> None:
			super().setTransform(matrix, **kwargs)
			scale_x = matrix.m11() * self.scale()
			scale_y = matrix.m22() * self.scale()
			scale_value = (self.scaleSelection(scale_x, scale_y) or 1)
			self.prepareGeometryChange()
			self._shape = outline_path(self._shapePath or self.path(), self.parent.value_padding_px / scale_value)

		def shape(self) -> QPainterPath:
			return QPainterPath(self._shape)

		def boundingRect(self) -> QRectF:
			return self._shape.boundingRect()

		def sceneBoundingRect(self) -> QRectF:
			return self.mapToScene(self._shape).boundingRect()

	@StateProperty(key='alignment', allowNone=True, dependencies={'geometry', 'text', 'margins'})
	def alignment(self) -> Alignment:
		return getattr(self, '_alignment', None) or self.alignment_auto()

	@alignment.condition(method='get')
	def alignment(self) -> bool:
		return getattr(self, '_alignment', None) is not None

	@alignment.setter
	def alignment(self, value: Alignment):
		self._alignment = value

	@alignment.decode
	def alignment(self, value: str) -> Alignment:
		return Alignment(AlignmentFlag[value])

	@StateProperty(key='format', default=None, allowNone=False)
	def format_spec(self) -> str | dict:
		return getattr(self, '_format_spec', None)

	@format_spec.setter
	def format_spec(self, value: str | dict):
		self._format_spec = value

	def format_value(self, value: Measurement) -> str:
		format_spec = self.format_spec
		if format_spec == 'duration':
			return formatDuration(value)
		if format_spec is not None:
			if isinstance(value, Measurement):
				match format_spec:
					case str():
						return value.__format__(format_spec)
					case dict():
						return value.__format__('', **format_spec)
		elif value is None:
			return "⋯"
		return str(value)

	@StateProperty(key='size', default=None, allowNone=True)
	def size(self) -> Length | Dimension | None:
		"""
		Largest height of the value text, as a share of the dial's diameter.

		Without it the value grows until it touches the dial, so a short value
		such as 'N' or '0' comes out far larger than '7.4'.

		```yaml
		value-label: {size: 26%}
		```
		"""
		return getattr(self, '_size', None)

	@size.setter
	def size(self, value: Length | Dimension | None):
		self._size = value

	@size.decode
	def size(self, value: str | int | float) -> Length | Dimension | None:
		return parseSize(value, default=None)

	@StateProperty(key='value-padding', default=Size.Height(0.05, relative=True), allowNone=False)
	def value_padding(self) -> Length | Dimension | None:
		return self._value_padding

	@value_padding.setter
	def value_padding(self, value: Length | Dimension | None):
		self._value_padding = value

	@value_padding.decode
	def value_padding(self, value: str | int | float) -> Length | Dimension | None:
		return parseSize(value, default=None)

	@property
	def value_padding_px(self) -> float | int:
		value_padding = self.value_padding
		if value_padding is None:
			return 5
		return size_px(value_padding, (self.textBox._textRect or self.textBox.limitRect).height())

	@StateProperty(key='position', allowNone=False, default=ValueDisplayPosition.Auto, repr=True)
	def position(self) -> ValueDisplayPosition:
		return self._position

	@position.setter
	def position(self, value: ValueDisplayPosition):
		self._position = value

	@position.decode
	def position(self, value: str) -> ValueDisplayPosition:
		return ValueDisplayPosition[value]

	def alignment_auto(self) -> Alignment:
		# TODO: This a quick and slopy implementation and needs improvement

		# match self.position:
		# 	case ValueDisplayPosition.Inline:
		# 		return Alignment(AlignmentFlag.Bottom)
		# 	case _:
		# 		pass
		align = self.parent.alignment.combined

		if (position := self.position) is ValueDisplayPosition.Auto:
			position = self.position_auto()

		# A side value is centred on the middle of its strip.
		if position in (ValueDisplayPosition.Left, ValueDisplayPosition.Right):
			return Alignment(AlignmentFlag.Center)

		# A bottom value stands on the panel's bottom edge and grows upward
		# into the dial's mouth (see TextBox.getTextPosition).
		if position is ValueDisplayPosition.Bottom:
			return Alignment(self.parent.alignment.horizontal | AlignmentFlag.Bottom)

		min_angle, max_angle = sorted((self.parent.startAngle, self.parent.endAngle))

		angle_spread = max_angle - min_angle
		if angle_spread > 180 and position is not ValueDisplayPosition.Inline:
			return Alignment(align)

		angle_mid = ((min_angle + max_angle) / 2 + 90) % 360

		if 60 >= angle_mid or angle_mid >= 300:
			align |= AlignmentFlag.Right
		elif 240 >= angle_mid >= 120:
			align |= AlignmentFlag.Left

		if 135 >= angle_mid >= 45:
			align |= AlignmentFlag.Bottom
		elif 315 >= angle_mid >= 225:
			align |= AlignmentFlag.Top

		return Alignment(align)

	def position_auto(self) -> ValueDisplayPosition:
		if self.gauge.needle.type is Needle.Type.Needle and self.gauge.arc.fullAngle > 180:
			return ValueDisplayPosition.Inline
		return ValueDisplayPosition.Center


class GaugeUnit(GaugeLabel):

	surface: 'Gauge'
	__exclude__ = {'alignment'}

	_debug_paint_color = Color.randomColor.QColor

	__defaults__ = {
		# Relative for the same reason as GaugeValueLabel above.
		'geometry': {
			'x': '0px',
			'y': '0px',
			'width': '30%',
			'height': '14%',
		},
		'margins': ('0', '0', '0', '0'),
	}

	class TextBox(Text):

		surface: 'Gauge'

		@property
		def alignment(self) -> Alignment:
			return Alignment(AlignmentFlag.Center | AlignmentFlag.Top)

		@alignment.setter
		def alignment(self, value):
			pass

		@property
		def _position(self) -> UnitDisplayPosition:
			if (position := self.parent.position) is UnitDisplayPosition.Auto:
				position = self.parent.position_auto()
			return position

		@defer(pool_attr='action_pool')
		def updateTransform(self, rect: QRectF = None, updateShared: bool = True, updatePath: bool = True, reason: str = None, *args):
			super().updateTransform(rect, updateShared, updatePath, reason=reason, *args)
			_shiftByOffset(self)
			# Same as the value label's: a refit puts the unit back at the
			# value's raw box, which is not where it should hang.
			self.parent.parent._syncUnitUnderValue()
			self.parent.parent._syncCaptions()

		def getTextPosition(self, limitRect: QRectF = None) -> QPointF:
			match self._position:
				case UnitDisplayPosition.Below | UnitDisplayPosition.FloatUnder:
					return self._position_below()
				case UnitDisplayPosition.TrailingValue:
					return self._position_trailing_value()
				case _:
					raise NotImplementedError

		def _position_below(self) -> QPointF:
			try:
				value_label = self.surface.valueLabel.textBox.sceneBoundingRect()
				p = value_label.center()
				p.setY(value_label.bottom())
				p = self.mapFromScene(p)
				return p
			except AttributeError:
				pass

			return self.parent.parent.center

		def _position_trailing_value(self) -> QPointF:
			try:
				value_label = self.surface.valueLabel.textBox.sceneBoundingRect()
				p = value_label.bottomLeft()
				return self.mapFromScene(p)
			except AttributeError:
				pass

			return self.parent.parent.center

		def _position_leading_value(self) -> QPointF:
			raise NotImplementedError

		def setPath(self, path):
			self._shape = outline_path(path, self.parent.value_padding_px)
			super().setPath(path)

		_shape: QPainterPath = QPainterPath()

		def shape(self) -> QPainterPath:
			return self._shape

		def boundingRect(self) -> QRectF:
			return self.shape().boundingRect()

		def setTransform(self, *args, **kwargs):
			super().setTransform(*args, **kwargs)

			move_direction = QPointF(0, 1)

			moved_count = 0

			if not self.parentItem().alignment == AlignmentFlag.Center:
				return

			max_travel_distance = int(ceil(sqrt(sum(i ** 2 for i in self.limitRect.size().toTuple()))))

			# Move the unit label away from the value label if it collides with the needle
			# TODO: Make this use transformations rather than moveBy
			while self.collidesWithItem(self.surface.needle) and abs(moved_count) < max_travel_distance:
				self.moveBy(move_direction.x(), move_direction.y())
				moved_count += 1

		def _textAccessor(self) -> str:
			value_class = self.parent.parent.valueClass
			# A key with no unit class (a bare float, e.g. a plugin value whose
			# unit WeatherUnits does not know) has no unit to show. Raising here
			# aborted the whole dashboard load.
			return getattr(value_class, 'unit', None) or getattr(value_class, 'unit_symbol', None) or ''

		@property
		def limitRect(self) -> QRectF:
			arc = self.surface.arc.boundingRect()
			r = max(arc.width(), arc.height()) / sqrt(2)
			r = QRectF(0, 0, r, r)
			r.setHeight(self.parent.height_px)
			return r

	@cached_property
	def value_label(self) -> GaugeValueLabel:
		return self.gauge.valueLabel

	@StateProperty(key='height', default=Length.Millimeter(5), allowNone=False)
	def height(self) -> Measurement | Dimension | None:
		return self._height

	@height.setter
	def height(self, value: Measurement | Dimension | None):
		self._height = value

	@height.decode
	def height(self, value: str | int | float) -> Measurement | Dimension | None:
		return parseSize(value, default=None, allowFloat=False)

	@property
	def height_px(self) -> float | int:
		height = self.height
		if height is None:
			return 0
		return size_px(height, self.height_relative_to)

	@property
	def height_relative_to(self) -> float | int:
		return self.parent.radius

	@StateProperty(key='value-padding', default=Size.Height(0.05, relative=True), allowNone=False)
	def value_padding(self) -> Length | Dimension | None:
		return self._value_padding

	@value_padding.setter
	def value_padding(self, value: Length | Dimension | None):
		self._value_padding = value

	@value_padding.decode
	def value_padding(self, value: str | int | float) -> Length | Dimension | None:
		return parseSize(value, default=None)

	@property
	def value_padding_px(self) -> float | int:
		value_padding = self.value_padding
		if value_padding is None:
			return 5
		return size_px(value_padding, (self.textBox._textRect or self.textBox.limitRect).height())

	@StateProperty(key='position', default=UnitDisplayPosition.Auto, allowNone=False, repr=True)
	def position(self) -> UnitDisplayPosition:
		return self._position

	@position.setter
	def position(self, value: UnitDisplayPosition):
		self._position = value

	# @position.item_default
	# def position(self) -> UnitDisplayPosition:
	# 	label_position = self.value_label.position
	# 	match label_position:
	# 		case ValueDisplayPosition.Auto:
	# 			return self.position_auto()
	# 		case ValueDisplayPosition.Inline | ValueDisplayPosition.Center:
	# 			return UnitDisplayPosition.Below
	#
	# 	return UnitDisplayPosition.Below

	@position.decode
	def position(self, value: str) -> UnitDisplayPosition:
		return UnitDisplayPosition[value]

	def position_auto(self) -> UnitDisplayPosition:
		value_label_position = self.value_label.position
		if value_label_position is ValueDisplayPosition.Auto:
			value_label_position = self.value_label.position_auto()
		match value_label_position:
			case ValueDisplayPosition.Inline | ValueDisplayPosition.Center:
				return UnitDisplayPosition.Below
			case _:
				return UnitDisplayPosition.TrailingValue


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


def decode_measurement(value: str | int | float, default_type: Type[Measurement] = Unset) -> Measurement:
	match value:
		case str(v):
			value = auto_wu(v)
		case int(v) | float(v):
			value = default_type(v)
		case _:
			raise TypeError(f'Invalid type for min: {type(value)}')
	return value


@DebugPaint
class Gauge(Display):

	_center_offset: QPointF | QPointF = QPointF(0, 0)

	__value: float = 0.0
	_needleAnimation: QPropertyAnimation
	valueChanged = Signal(float)
	arc: GaugeArc

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

	grads: Graduations
	needleLength = 1.0
	needleWidth = 0.1
	_valueClass: Type[GaugeValue] = float
	_unit: Optional[str] = None
	_scene: QGraphicsScene
	_pen: QPen
	_cache: list
	__value: Union[Numeric, Measurement]

	def _init_defaults_(self):
		self._valueClass = self.parent.container.value_type
		self._markerItems = []
		self._markerSpecs = []
		self._fillItem = None
		self._fillSpec = None
		self._zonesItem = None
		self._zoneSpecs = []
		super()._init_defaults_()
		self.__value = value = self._valueClass(0)

		self._pen = QPen(self.defaultColor)

		self.major_ticks_surface = TickSurface(self, self.majorDivisions)
		self.minor_ticks_surface = TickSurface(self, self.minorDivisions)
		self.micro_ticks_surface = TickSurface(self, self.microDivisions)
		self.hide()
	# a = self.arc
	# self.unitLabel = unit_label = GaugeUnit(self)

	@StateProperty(key='range', link=GaugeRange, allowNone=False, repr=True, sortOrder=-2)
	def range(self) -> GaugeRange:
		return self._range

	@range.setter
	def range(self, value: GaugeRange):
		self._range = value

	@range.factory
	def range(self) -> GaugeRange:
		return Gauge.GaugeRange(self)

	@range.after
	def range(self):
		self.rebuild()

	@StateProperty(key='radius', default=Size.Height(1.0, relative=True), allowNone=False, repr=True, sortOrder=-1)
	def _radius(self) -> Length | Size.Height:
		return self._s_radius

	@_radius.setter
	def _radius(self, value: Length | Size.Height):
		self._s_radius = value

	@_radius.decode
	def _radius(self, value: int | float | str) -> Length | Size.Height:
		return parseSize(value, allowFloat=False, dimension=DimensionType.height)

	@_radius.encode
	def _radius(self, value: Length | Size.Height) -> str:
		return str(value)

	@StateProperty(key='arc', repr=True, dependencies={'radius'})
	def arc(self) -> GaugeArc:
		return self._arc

	@arc.factory
	def arc(self) -> GaugeArc:
		return GaugeArc(self)

	@arc.setter
	def arc(self, value: GaugeArc):
		self._arc = value

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
			log.warning(f'Gauge {_gaugeKeyName(self)} fill skipped: {e}')
			return
		self._fillItem = item
		self._fillSpec = copy.deepcopy(dict(value))

	@fill.decode
	def fill(self, value) -> Optional[dict]:
		if value is None:
			return None
		if not isinstance(value, Mapping):
			log.warning(f'Gauge {_gaugeKeyName(self)} ignored fill {value!r}: expected a mapping')
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

	_captionItem: Optional[GaugeCaption] = None
	_captionSpec = None
	_subItem: Optional[GaugeCaption] = None
	_subSpec = None

	def _setCaption(self, attr: str, specAttr: str, side: str, value) -> None:
		self._clearCaption(attr, specAttr)
		if not value:
			return
		# A bad caption is a warning, never a failed dashboard load.
		try:
			item = GaugeCaption(self, side)
			item.configure(value)
		except Exception as e:
			log.warning(f'Gauge {_gaugeKeyName(self)} {side} skipped: {e}')
			return
		setattr(self, attr, item)
		setattr(self, specAttr, copy.deepcopy(value))

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

	def _captionItems(self) -> list:
		return [i for i in (self._captionItem, self._subItem) if i is not None]

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
			log.warning(f'Gauge {_gaugeKeyName(self)} could not measure its value: {e!r}')
		if not rects:
			return QRectF(self.center, QSizeF(0, 0))
		box = rects[0]
		for r in rects[1:]:
			box = box.united(r)
		return box

	def _syncCaptions(self):
		for item in self._captionItems():
			item.refresh()

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
			log.warning(f'Gauge {_gaugeKeyName(self)} zones skipped: {e}')
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
			log.debug(f'Gauge {_gaugeKeyName(self)} zones not drawn yet: {e}')

	@zones.decode
	def zones(self, value) -> list:
		if isinstance(value, Mapping):
			value = [value]
		if not isinstance(value, (list, tuple)):
			log.warning(f'Gauge {_gaugeKeyName(self)} ignored zones {value!r}: expected a list')
			return []
		for spec in value:
			if not isinstance(spec, Mapping):
				log.warning(f'Gauge {_gaugeKeyName(self)} skipped zone {spec!r}: expected a mapping')
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
				log.warning(f'Gauge {_gaugeKeyName(self)} skipped marker {_markerText(spec)!r}: {e}')
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
			log.warning(f'Gauge {_gaugeKeyName(self)} ignored markers {value!r}: expected a list')
			return []
		valid = []
		for spec in value:
			if isinstance(spec, Mapping):
				valid.append(dict(spec))
			else:
				log.warning(f'Gauge {_gaugeKeyName(self)} skipped marker {spec!r}: expected a mapping with a value')
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

	def releaseSources(self):
		"""Stop and release every value source the markers and fill hold.
		Called when the owning panel is deleted; never raises."""
		for clear in (self._clearMarkers, self._clearFill, self._clearZones,
					lambda: self._clearCaption('_captionItem', '_captionSpec'),
					lambda: self._clearCaption('_subItem', '_subSpec')):
			try:
				clear()
			except Exception as e:
				log.warning(f'Gauge {_gaugeKeyName(self)} could not release its value sources: {e!r}')

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

	@property
	def type(self):
		return DisplayType.Gauge

	@property
	def displayType(self):
		return DisplayType.Gauge

	def __init__(self, parent, *args, **kwargs):
		self.previousParent = None
		super(Gauge, self).__init__(parent, *args, **kwargs)

	@property
	def startAngle(self) -> float:
		return self.arc.startAngle

	@property
	def leading_angle(self) -> float:
		"""Left side of the arc."""
		angle = sorted([self.startAngle, self.endAngle])[1]
		return angle % 360

	@property
	def endAngle(self) -> float:
		return self.arc.endAngle

	@property
	def trailing_angle(self) -> float:
		"""Right side of the arc."""
		angle = sorted([self.startAngle, self.endAngle])[0]
		return angle % 360

	def convert_gradient(self, gradient: 'Gradient') -> QConicalGradient:
		_type = self.valueClass
		rounded_min = self._range.rounded_min
		rounded_max = self._range.rounded_max
		if not issubclass(gradient.itemCls.__item__, _type):
			gradient = gradient.as_type(_type, rounded_min, rounded_max)
		return gradient.toQConicalGradient(
			start_angle=self.startAngle,
			stop_angle=self.endAngle,
			min_value=rounded_min,
			max_value=rounded_max,
		)

	def map_gradient_to(self, gradient: 'Gradient', item: QGraphicsPathItem | Surface = None) -> QConicalGradient:
		gradient = self.convert_gradient(gradient)
		gradient.setCenter(self._center_transform.map(self.mapToItem(item or self, self.center)))
		return gradient

	def _afterSetState(self):
		super()._afterSetState()

		self.refresh()

	_center_transform: QTransform = QTransform()
	#: The shift recenter() last applied to the needle, markers, arc, fills and ticks.
	_recenterTransform: QTransform = QTransform()

	# def paint(self, painter, option, widget):
	# 	super().paint(painter, option, widget)
	#
	# 	if issubclass(self.valueClass, Temperature):
	# 		f = self.get_gradient_for(self)
	# 	else:
	# 		f = QColor(self.defaultColor)
	#
	# 	# shape = self._shape()
	# 	shape = QPainterPath()
	# 	rect = self.gaugeRect
	# 	rect.moveCenter(self.center)
	# 	shape.addEllipse(rect)
	# 	addPath(painter, shape, fill=f)
	# 	addCrosshair(painter, pos=self._shape().boundingRect().center())
	# 	addCrosshair(painter, pos=option.rect.center())

	def recenter(self):

		bounds_rect = self._dialRect()

		# Measure at identity. `full_gauge_path` maps every child through its
		# CURRENT transform, so measuring while a previous centering is still
		# applied reports an already-centred shape, yields ~zero offset, and
		# the `setTransform(t, combine=False)` below then REPLACES the good
		# transform with a near-identity one - snapping the ticks back to
		# their uncentred position while the arc, drawn centred in its own
		# local space, appears to stay put. That is the "correct for a split
		# second, then jump" behaviour: the first pass centres correctly and
		# the second undoes it.
		centred_items = (
			self.needle, self.arc, *self._zoneItems(), *self._markerItems, *self._fillItems(),
			self.major_ticks_surface, self.minor_ticks_surface, self.micro_ticks_surface,
		)
		for item in centred_items:
			item.resetTransform()

		self._update_shape()
		own_shape = self.full_gauge_path
		own_shape_rect = own_shape.boundingRect()

		panel_center = bounds_rect.center()
		shape_center = own_shape_rect.center()
		center_offset = shape_center - panel_center

		t = QTransform()

		alignment = self.alignment

		if alignment.vertical.isCenter:
			t.translate(0, -center_offset.y())
		else:
			if own_shape_rect.height() >= bounds_rect.height():
				t.translate(0, bounds_rect.center().y() - own_shape_rect.center().y())
			elif own_shape_rect.top() <= bounds_rect.top():
				t.translate(0, bounds_rect.top() - own_shape_rect.top())
			elif own_shape_rect.bottom() >= bounds_rect.bottom():
				t.translate(0, bounds_rect.bottom() - own_shape_rect.bottom())

		if alignment.horizontal.isCenter:
			t.translate(-center_offset.x(), 0)
		else:
			if own_shape_rect.width() >= bounds_rect.width():
				t.translate(bounds_rect.center().x() - own_shape_rect.center().x(), 0)
			elif own_shape_rect.left() <= bounds_rect.left():
				t.translate(bounds_rect.left() - own_shape_rect.left(), 0)
			elif own_shape_rect.right() >= bounds_rect.right():
				t.translate(bounds_rect.right() - own_shape_rect.right(), 0)

		if self._anchor is not None:
			# The pivot is already where `anchor` put it; nothing to centre.
			t = QTransform()

		self._center_transform = QTransform()
		self._recenterTransform = QTransform(t)

		self.needle.setTransform(t, combine=False)
		for marker in self._markerItems:
			marker.setTransform(t, combine=False)
		self.arc.setTransform(t, combine=False)
		for item in self._zoneItems():
			item.setTransform(t, combine=False)
		for item in self._fillItems():
			item.setTransform(t, combine=False)

		# TODO: After transformation is set, the labels are not moved
		# correctly thus the 'refresh' method must be called after.
		# This needs to be corrected
		self.major_ticks_surface.setTransform(t, combine=False)
		self.majorDivisions.labels.refresh()
		self.minor_ticks_surface.setTransform(t, combine=False)
		self.minorDivisions.labels.refresh()
		self.micro_ticks_surface.setTransform(t, combine=False)
		self.microDivisions.labels.refresh()

		self.valueLabel.textBox.updateTransform(updatePath=False, reason='recenter')
		if self._valueSide() is None:
			self.valueLabel.textBox.setTransform(t, combine=True)

		self.unitLabel.textBox.updateTransform(updatePath=False, reason='recenter')
		self.unitLabel.textBox.setTransform(t, combine=True)

		self._syncUnitUnderValue()
		self._syncCaptions()

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
			log.warning(f'Gauge {_gaugeKeyName(self)} could not place its unit label: {e!r}')
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

	@defer
	def rebuild(self):
		self.major_ticks_surface.rebuild()
		self.minor_ticks_surface.rebuild()
		self.micro_ticks_surface.rebuild()

		self.refresh()

	def refresh(self):
		self.arc.refresh()
		for item in self._zoneItems():
			item.refresh()
		for item in self._fillItems():
			item.refresh()
		self.needle.refresh()
		for marker in self._markerItems:
			marker.refresh()

		self.major_ticks_surface.refresh()
		self.minor_ticks_surface.refresh()
		self.micro_ticks_surface.refresh()

		self._update_shape()
		# Defensive: refresh() runs from _afterSetState, which is inside the
		# dashboard load. Anything raising here aborts the *whole* load, so a
		# single malformed gauge used to leave a board with nothing on it. A
		# label that is not a label is worth a warning, not an empty screen.
		for label in (self.valueLabel, self.unitLabel):
			textBox = getattr(label, 'textBox', None)
			if textBox is None:
				log.warning(f'{self}: {type(label).__name__} has no textBox; skipping its refresh')
				continue
			textBox.refresh()
		self.recenter()

	def _update_shape(self):
		clearCacheAttr(self, 'value_text_box_area_rect', 'full_gauge_path')

	def parentResized(self, arg: Union[QPointF, QSizeF, QRectF]):
		super().parentResized(arg)
		self.refresh()

	_value: GaugeValue = 0

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

	def _zoneItems(self) -> list:
		item = getattr(self, '_zonesItem', None)
		return [] if item is None else [item]

	def _fillItems(self) -> list:
		item = getattr(self, '_fillItem', None)
		return [] if item is None else [item]

	def value_to_angle(self, value: Numeric) -> Angle:
		angle = float(value - self._range.rounded_min) / self._range.rounded_range * self.fullAngle + self.startAngle
		return Angle(sorted((self.startAngle, angle, self.endAngle))[1])

	@property
	def valueClass(self) -> Type[GaugeValue]:
		return self._valueClass

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

	def animateValue(self, start: Numeric, end: Numeric):
		if self._needleAnimation.state() == QtCore.QAbstractAnimation.Running:
			self._needleAnimation.stop()
		self._needleAnimation.setStartValue(float(start))
		self._needleAnimation.setEndValue(float(end))
		self._needleAnimation.start()

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

	def update_center_offset(self, offset: QPointF):
		self._center_offset = offset

	@StateProperty(key='center_offset', allowNone=True, after=rebuild, repr=True)
	def center_offset(self) -> QPointF:
		return getattr(self, '_center_offset', QPointF())

	@center_offset.setter
	def center_offset(self, value: QPointF):
		self._center_offset = value

	@center_offset.decode
	def center_offset(self, value: str | Sequence | dict) -> QPointF:
		if isinstance(value, str):
			value = value.split(',')

		if len(value) != 2:
			raise ValueError(f'center_offset must be a sequence or mapping of length 2, got {len(value)}')

		if isinstance(value, dict):
			x = parseX(value.get('x', 0), 0)
			y = parseY(value.get('y', 0), 0)
		else:
			x = parseX(value[0], 0)
			y = parseY(value[1], 0)
		return QPointF(x, y)

	@center_offset.encode
	def center_offset(self, value: QPointF) -> dict[str, float]:
		return {'x': round(value.x(), 3), 'y': round(value.y(), 3)}

	def _valueSide(self) -> Optional[ValueDisplayPosition]:
		"""`left` or `right` when the value label is set to sit beside the dial, else None."""
		label = getattr(self, '_valueLabel', None)
		position = getattr(label, '_position', None)
		if position in (ValueDisplayPosition.Left, ValueDisplayPosition.Right):
			return position
		return None

	def _sideStripWidth(self) -> float:
		"""Width the box gives a value beside the dial, from the far edge to the dial's."""
		if self._valueSide() is None:
			return 0.0
		width, height = self.width(), self.height()
		# A wide box keeps the dial at full height and gives the value what is left;
		# a narrow one shares the width, the dial taking the larger part.
		return min(width * 0.5, max(width * 0.34, width - height))

	def _dialRect(self) -> QRectF:
		"""The part of the box the dial lives in: all of it, less the strip a side value takes."""
		rect = QRectF(self.rect())
		side = self._valueSide()
		if side is None:
			return rect
		strip = self._sideStripWidth()
		if side is ValueDisplayPosition.Left:
			rect.setLeft(rect.left() + strip)
		else:
			rect.setRight(rect.right() - strip)
		return rect

	def _sideValueRect(self) -> QRectF:
		"""The strip beside the dial a `left`/`right` value is fitted to, in gauge coordinates.
		Centred on the pivot, so a value stays level with it however the sweep is cut."""
		rect = self.rect()
		strip = self._sideStripWidth()
		# A pinned pivot sits in a corner, so level with the box's middle instead.
		pivot_y = self.rect().center().y() if self._anchor is not None else self.center.y() + self._recenterTransform.dy()
		half = max(min(pivot_y - rect.top(), rect.bottom() - pivot_y), 1.0)
		left = rect.left() if self._valueSide() is ValueDisplayPosition.Left else rect.right() - strip
		return QRectF(left, pivot_y - half, strip, half * 2)

	@property
	def center(self) -> QPointF:

		if self._anchor is not None:
			fx, fy = self._ANCHORS[self._anchor]
			rect, inset = self._dialRect(), self.insetPx
			return QPointF(
				rect.left() + inset if fx == 0 else rect.right() - inset,
				rect.top() + inset if fy == 0 else rect.bottom() - inset,
			)

		p = self.alignment.multipliersAlt
		rect = self.boundingRect()
		x = rect.width() * p[0]
		y = rect.height() * p[1]
		p = QPointF(x, y)

		p -= self._center_offset
		if self._valueSide() is not None:
			p.setX(p.x() + self._dialRect().center().x() - self.rect().center().x())
		margin_rect = self.marginRect
		# keep p within the bounding rect
		p.setX(sorted((margin_rect.left(), p.x(), margin_rect.right()))[1])
		p.setY(sorted((margin_rect.top(), p.y(), margin_rect.bottom()))[1])

		return p

	@property
	def scene_center(self) -> QPointF:
		return self.mapToScene(self.center)

	@property
	def baseWidth(self):
		return sqrt(self.height() ** 2 + self.width() ** 2) * INVERSE_GOLDEN_RATIO * 0.01

	@property
	def radius_max(self):
		if self._anchor is not None:
			# The pivot is in a corner, so the dial may reach the whole short side.
			return max(min(self.height(), self._dialRect().width()) - self.insetPx - self.baseWidth, 1)
		return max(min(self.height(), self._dialRect().width()) / 2 - self.baseWidth, 1)

	@property
	def radius(self):
		return min(self.radius_max, self._radius)

	@property
	def radius(self) -> float:
		radius_max = self.radius_max
		return min(size_px(self._radius, radius_max), radius_max * 2)

	@property
	def gaugeRect(self) -> QRectF:
		f = QRectF(0.0, 0.0, self.radius * 2, self.radius * 2)
		f.moveCenter(self.rect().center())
		return f

	@property
	def fullAngle(self):
		return abs(self.endAngle + -self.startAngle)

	@property
	def defaultColor(self):
		return Color.text.QColor

	@property
	def tickFont(self):
		font = QFont()
		font.setPointSizeF(max(self.radius * .1, 18))
		return font

	def setRect(self, *args, **kwargs):
		super().setRect(*args, **kwargs)

	@property
	def duration(self):
		return self._needleAnimation.duration()

	@duration.setter
	def duration(self, value):
		self._needleAnimation.setDuration(value)

	@property
	def easing(self):
		return self._needleAnimation.getEasingCurve()

	@easing.setter
	def easing(self, value: QEasingCurve):
		if isinstance(QEasingCurve, value):
			self._needleAnimation.setEasingCurve(value)
		else:
			print('Not a valid easing curve')

	@property
	def arc_length(self) -> float:
		radius_px = self.radius
		return float(radius_px * self.fullAngle / 180 * pi)

	def value_to_angle(self, value: Numeric) -> float:
		_range = self._range
		s = self.startAngle
		e = self.endAngle
		if _range.wrap:
			span = float(_range.rounded_range)
			return s + (float(value - _range.rounded_min) % span) / span * self.fullAngle
		angle = float(value - _range.rounded_min) / _range.rounded_range * self.fullAngle + s
		return sorted((s, angle, e))[1]

	def value_to_angle_degrees(
		self,
		value: Numeric | Percentage | RelativeFloat | Length,
		relative_angle: Angle = None,
		relative_px: float = None,
		radius_px: float = None,
	) -> Angle:
		radius = radius_px or self.radius
		arc_length_px = float(radius * self.fullAngle / 180 * pi)

		if isinstance(value, Percentage):
			if relative_angle is not None:
				return Angle(relative_angle * value)
			elif relative_px is not None:
				return Angle(relative_px * value / arc_length_px * self.fullAngle)
		# elif issubclass(self.valueClass, Percentage):
		# 	value = float(value)

		if isinstance(value, (int, float, self.valueClass)):
			if isinstance(value, Percentage):
				value = float(value)
			value_arc_coverage = float(value / self._range.rounded_range)
			value_deg = value_arc_coverage * self.fullAngle
			return Angle(value_deg)

		elif isinstance(value, Percentage | RelativeFloat):
			# TODO: Add support for custom radius
			return Angle(value * relative_angle or self.fullAngle)
		elif isinstance(value, Length):
			value_px = size_px(value, relative_px or self.gauge.baseWidth)
			value = value_px / radius * 180 / pi
			return Angle(value)
		elif isinstance(value, Angle):
			return value

	def angle_degrees_to_value(
		self,
		angle: Angle | float | int,
		relative_angle: Angle = None,
		relative_px: float = None,
		radius_px: float = None,
	) -> float:

		radius = radius_px or self.radius
		arc_length_px = float(radius * self.fullAngle / 180 * pi)

		if isinstance(angle, Angle):
			angle = float(angle)
		elif isinstance(angle, (int, float)):
			angle = float(angle)
		else:
			raise TypeError(f'Invalid angle type: {type(angle)}')

		if isinstance(angle, (int, float)):
			if relative_angle is not None:
				angle = angle / float(relative_angle)
			elif relative_px is not None:
				angle = angle / relative_px * arc_length_px

			return angle / self.fullAngle * self._range.rounded_range

	def interval_to_count_float(self, interval: GaugeValue) -> float:
		return self._range.rounded_range / interval

	@property
	def safe_radius(self):
		major: Graduations = self.majorDivisions
		minor: Graduations = self.minorDivisions
		micro: Graduations = self.microDivisions

		arc_line_width = self.arc.pen().widthF()

		trim = max(arc_line_width / 2, 0)

		if major.enabled and major.position in {DisplayPosition.Below, DisplayPosition.Inside}:
			trim = max(major.length_px + major.width_px / 2, trim)
		if minor.enabled and minor.position in {DisplayPosition.Below, DisplayPosition.Inside}:
			trim = max(minor.length_px + minor.width_px / 2, trim)
		if micro.enabled and micro.position in {DisplayPosition.Below, DisplayPosition.Inside}:
			trim = max(micro.length_px + micro.width_px / 2, trim)

		return self.radius - trim

	@property
	def exterior_safe_radius(self):
		major: Graduations = self.majorDivisions
		minor: Graduations = self.minorDivisions
		micro: Graduations = self.microDivisions

		arc_line_width = self.arc.pen().widthF()

		extend = max(arc_line_width / 2, 0)

		if major.enabled and major.position in {DisplayPosition.Above, DisplayPosition.Outside}:
			extend = max(major.length_px + major.width_px / 2, extend)
		if minor.enabled and minor.position in {DisplayPosition.Above, DisplayPosition.Outside}:
			extend = max(minor.length_px + minor.width_px / 2, extend)
		if micro.enabled and micro.position in {DisplayPosition.Above, DisplayPosition.Outside}:
			extend = max(micro.length_px + micro.width_px / 2, extend)

		return self.radius + extend

	@property
	def value_safe_radius(self):

		major: Graduations = self.majorDivisions
		minor: Graduations = self.minorDivisions
		micro: Graduations = self.microDivisions

		trim = 0

		safe_radius = self.safe_radius
		if major.labels.enabled:
			labels: GaugeTickTextGroup = major.labels
			trim = max(labels.textSize_px + labels.offset_px, trim)
		if minor.labels.enabled:
			labels: GaugeTickTextGroup = minor.labels
			trim = max(labels.textSize_px + labels.offset_px, trim)
		if micro.labels.enabled:
			labels: GaugeTickTextGroup = micro.labels
			trim = max(labels.textSize_px + labels.offset_px, trim)

		return safe_radius - trim

	@property
	def safe_area(self) -> QPainterPath:
		return self.arc.mapToParent(self.arc.shape())

	def _debug_paint(self, painter: QPainter, option, widget):

		def add_gradient():
			painter.save()
			if (gradient := self.arc.gradient) is not None:
				painter.setBrush(self.map_gradient_to(gradient, self))
				painter.drawRect(option.rect)
			painter.restore()

		self._normal_paint(painter, option, widget)
	# addPath(painter, self.mapFromItem(self.arc, self.arc.shape(z)), type(self)._debug_paint_color, fill=type(self)._debug_paint_color)
	# f = QRadialGradient(rainbow)
	# f.setRadius(max(self.boundingRect().width(), self.boundingRect().height()) / 2)
	# f.setCenter(self.center)
	# f.setFocalPoint(self.center)
	# f.setCoordinateMode(QGradient.CoordinateMode.LogicalMode)
	# p = self._shape()
	# # addRect(painter, self.full_gauge_rect(), fill=f, opacity=.2)
	# p = outline_path(p, 5)
	# # self._normal_paint(painter, option, widget)
	# addPath(painter, p, fill=f)
	# addRect(painter, self.rect(), color=Qt.cyan, offset=-2, width=3)

	def _gauge_path(self) -> QPainterPath:
		"""Returns the path of the gauge, including the arc, ticks, and tick labels"""

		gauge_path = QPainterPath()
		gauge_path.setFillRule(Qt.WindingFill)

		# add arc
		gauge_path.addPath(self.mapFromItem(self.arc, self.arc.shape()))

		# add major ticks
		try:
			gauge_path.addPath(self.mapFromItem(self.major_ticks_surface, self.major_ticks_surface.tick_path))

			# add major tick labels
			if self.majorDivisions.labels.enabled:
				gauge_path.addPath(self.mapFromItem(self.major_ticks_surface, self.majorDivisions.labels.shape()))
		except AttributeError:
			pass

		# add minor ticks
		try:
			gauge_path.addPath(self.mapFromItem(self.minor_ticks_surface, self.minor_ticks_surface.tick_path))

			# add minor tick labels
			if self.minorDivisions.labels.enabled:
				gauge_path.addPath(self.mapFromItem(self.minor_ticks_surface, self.minorDivisions.labels.shape()))
		except AttributeError:
			pass

		# add micro ticks
		try:
			gauge_path.addPath(self.mapFromItem(self.micro_ticks_surface, self.micro_ticks_surface.tick_path))

			# add micro tick labels
			if self.microDivisions.labels.enabled:
				gauge_path.addPath(self.mapFromItem(self.micro_ticks_surface, self.microDivisions.labels.shape()))
		except AttributeError:
			pass

		return gauge_path

	@cached_property
	def full_gauge_path(self) -> QPainterPath:
		path = self._gauge_path()
		path.setFillRule(Qt.WindingFill)
		# Value-independent geometry only: arc, ticks, tick labels. The value
		# and unit labels (and the needle, fills, markers) change shape with
		# the value, and recenter() measures this path - counting them made a
		# partial dial land somewhere different for every value at load.
		return path.simplified()

	def full_gauge_rect(self) -> QRectF:
		return self.full_gauge_path.boundingRect()
