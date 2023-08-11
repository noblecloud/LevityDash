import numpy as np
from PySide6 import QtCore
from PySide6.QtCore import QPointF, QRectF, QPoint, QPropertyAnimation, Signal, QEasingCurve, QSizeF, Slot
from PySide6.QtGui import (
	QBrush, QFont, QPainter, QPainterPath,
	QPen, QPolygonF, QTransform, QRadialGradient, QGradient, QColor, Qt, QConicalGradient
)
from PySide6.QtWidgets import (
	QGraphicsPathItem,
	QGraphicsScene, QStyleOptionGraphicsItem,
	QWidget, QGraphicsItemGroup
)
from enum import Enum
from functools import cached_property
from math import isinf, floor, log10
from numbers import Number
from numpy import ceil, cos, pi, radians, sin, sqrt, number as np_number
from typing import Optional, Type, Union, Iterator, Iterable, TypeVar, Sequence

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.stateful import Stateful, StateProperty, SourceType
from LevityDash.lib.stateful_mixins import ColorGradientMixin
from LevityDash.lib.ui import UILogger, Color, Gradient
from LevityDash.lib.ui.Geometry import RelativeFloat, parseSize, DimensionType, size_px, Dimension, Size, Alignment, \
	AlignmentFlag, DisplayPosition, parseWidth, parseX, parseY
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays import SurfaceCentered, Surface
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Annotations import AnnotationText, AnnotationLabels
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.DisplayBase import Display
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Label import NonInteractiveLabel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import Text
from LevityDash.lib.ui.frontends.PySide.Modules.Handles import Handle
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import SizeGroup
from LevityDash.lib.ui.frontends.PySide.utils import DisplayType, addCrosshair, DebugPaint, SoftShadow, outline_path, \
	modifyTransformValues
from LevityDash.lib.utils import Axis
from LevityDash.lib.utils.data import MinMax
from LevityDash.lib.utils.shared import radialPoint, defer, factors, is_prime, Unset, clearCacheAttr, \
	INVERSE_GOLDEN_RATIO, closestStringInList, camelCase, guarded_cached_property
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


class GaugeItem:
	_gauge: 'Gauge'

	def __init__(self, *args, **kwargs):

		gauge = kwargs.get('gauge', None) or kwargs.get('parent', None) or next((a for a in args if isinstance(a, Gauge)), None) or next((v for v in kwargs.values() if isinstance(v, Gauge)), None)

		# find the gauge from the arguments or keyword arguments
		if not isinstance(gauge, Gauge):
			gauge = next((a for a in args if isinstance(a, Gauge)), None) or next((v for v in kwargs.values() if isinstance(v, Gauge)), None)
			if gauge is None:
				raise ValueError('GaugeItem must be initialized with a Gauge instance')
		self._gauge = gauge

		try:
			super().__init__(*args, **kwargs)
		except TypeError:
			super().__init__()

	@property
	def gauge(self) -> 'Gauge':
		if isinstance(self, Panel):
			gauge = self.localGroup
			while not isinstance(gauge, Gauge):
				gauge = gauge.parentItem()
			return gauge
		return self._gauge

	def remove(self):
		self.gauge.scene().removeItem(self)


Numeric = Union[int, float, complex, np_number, Measurement]
GaugeValue = TypeVar('GaugeValue', bound=Numeric, covariant=True)


class Graduations(GaugeItem, ColorGradientMixin, Stateful):
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


	State Properties
	----------

		All of the following properties are stateful and can be set in the config file.

		enabled : bool
			Whether this graduation is enabled

		length : Angle, Length, Percentage, AbsoluteFloat (default: 0.1)
			The length of each tick mark. Angle units are converted to arch length pixels.
			Percentage units are converted to a percentage of the gauge radius.
		width : float
			The line width of each tick. Angle units are converted to arch length pixels.
			Percentage units will be converted to a percentage of the tick length in.

		count : int, optional
			The number of ticks on the gauge. If this is set, the tick interval will be calculated automatically.
		min_count : int, optional (default=Unset)
			The minimum number of ticks on the gauge.
		max_usr_count : int, optional (default=Unset)
			The maximum number of ticks on the gauge.

		interval : int, optional
			The interval between ticks. If this is set, the number of ticks will be calculated automatically.
		min_interval : int, optional (default=Unset)
			The minimum interval between ticks.
		max_interval : int, optional (default=inf)
			The maximum interval between ticks.

		spacing : Angle, Length, Percentage, AbsoluteFloat, optional (default=Unset)
			The amount of visual space between ticks.
		min_spacing : Angle, Length, Percentage, AbsoluteFloat, optional (default=Unset)
			The minimum amount of visual space between ticks.
		max_spacing : Angle, Length, Percentage, AbsoluteFloat, optional (default=Unset)
			The maximum amount of visual space between ticks.

		required_interval_factors : set[int], optional (default=Unset)
			Require one of these factors to be a factor of the tick interval.
		excluded_interval_factors : set[int], optional (default=Unset)
			Exclude tick intervals that have any of these factors.


	Properties
	----------
		_min_spacing_dg : float
			The actual minimum spacing in degrees calculated from the tick length and width.
		length_px: float
			The length of each tick mark in pixels.
		width_px: float
			The width of each tick mark in pixels.
		spacing_px: float
			The spacing between each tick mark in pixels.


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
		super().__init__(gauge=gauge, **kwargs)
		self.state = self.prep_init(kwargs)

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

	@StateProperty(key='number-base', default=10)
	def number_base(self) -> int:
		return self._number_base

	@number_base.setter
	def number_base(self, value: int):
		self._number_base = value

	@number_base.decode
	def number_base(self, value: str | float):
		try:
			return int(value)
		except Exception as e:
			log.error(f'Invalid number base: {value}')
			log.exception(e)
			return 10

	@StateProperty(key='count', default=None, dependancies={'interval'})
	def usr_count(self) -> int:
		return self._usr_count

	@usr_count.setter
	def usr_count(self, value: int | None):
		self._usr_count = value

	@StateProperty(key='min-count', default=None)
	def min_usr_count(self) -> int:
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
		return self._max_usr_count

	@max_usr_count.setter
	def max_usr_count(self, value: int | float | None):
		if isinf(value):
			value = None
		elif isinstance(value, float):
			value = int(value) + 1
		self._max_usr_count = value

	@StateProperty(key='position', allowNone=False, default=DisplayPosition.Inside)
	def position(self) -> DisplayPosition:
		return self._position

	@position.setter
	def position(self, value: DisplayPosition):
		self._position = value

	@position.decode
	def position(self, value: str | DisplayPosition) -> DisplayPosition:
		return DisplayPosition[value]

	@StateProperty(key='length', allowNone=False)
	def length(self) -> Percentage | Length:
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
	def width(self) -> float:
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

	@StateProperty(key='interval', allowNone=False)
	def usr_interval(self) -> Measurement | Unset:
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

		Returns
		-------
		Angle | Length | Percentage
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
		return self._max_spacing

	@property
	def angle_range(self) -> float:
		if self.super_grad is None:
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
			count = int(self.gauge.range.rounded_range / interval) + 1
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
		values = set(value_class(i) for i in np.arange(
			float(gauge_range.rounded_min),
			float(gauge_range.rounded_max),
			float(interval)
		)) - super_tick_values
		if self.tick_type is Graduations.Type.Major:
			values.add(gauge_range.rounded_max)
		return values

	def interval_to_deg(self, interval: GaugeValue) -> Angle:
		return self.gauge.value_to_angle_degrees(interval, self.gauge.radius)

	def determine_interval(self) -> GaugeValue:

		gauge = self.gauge

		match self.tick_type:
			case Graduations.Type.Major:
				return self._determine_interval()
			case Graduations.Type.Minor:
				return self._determine_interval(
					range_value=gauge.range.rounded_range / gauge.majorDivisions.count,
					gauge_max_angle_deg=gauge.majorDivisions.angle_range / gauge.majorDivisions.count,
				)

			case Graduations.Type.Micro:
				return self._determine_interval(
					range_value=gauge.range.rounded_range / gauge.minorDivisions.count,
					gauge_max_angle_deg=gauge.minorDivisions.angle_range / gauge.minorDivisions.count,
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

		if self._state_item_sources.get(Graduations.usr_interval, SourceType.ItemDefault) is SourceType.UserConfig:
			if usr_interval not in compatible_intervals and float(range_value / usr_interval).is_integer():
				gauge_repr = f'Gauge.{gauge.valueClass.name.replace(" ", "")}(min={gauge.range.min}, max={gauge.range.max})'
				log.warning(f'User specified interval: {usr_interval} for {gauge_repr} is not compatible with the gauge range {gauge.range}')

		compatible_intervals = [
			self.gauge.valueClass(i) for i in sorted(compatible_intervals)
			if float(min_interval) <= i <= float(max_interval)
		]

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


@DebugPaint
class GaugeArc(Stateful, GaugePathItem):
	_weight_scale = 0.75

	@property
	def safe_area(self) -> QPainterPath:
		return QPainterPath(self.shape())

	@property
	def scene_safe_area(self) -> QPainterPath:
		return self.mapToScene(self.shape())

	def __init__(self, *args, **kwargs):
		super(GaugeArc, self).__init__(*args, **kwargs)
		kwargs = self.prep_init(kwargs)
		self.setItemState(kwargs)

	def _debug_paint(self, painter: QPainter, opt, widget):
		color = QColor(Qt.GlobalColor.yellow)
		self._normal_paint(painter, opt, widget)
		addCrosshair(painter, pos=self.path().boundingRect().center(), color=color, weight=4, size=10)

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
		safe_radius = self.gauge.safe_radius
		radius = self.gauge.exterior_safe_radius

		width = radius - safe_radius

		path = QPainterPath()
		path.setFillRule(Qt.FillRule.WindingFill)

		inner_rect = QRectF(-safe_radius, -safe_radius, safe_radius * 2, safe_radius * 2)
		radius_rect = QRectF(-radius, -radius, radius * 2, radius * 2)

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
		return self._index * self.properties.interval + self.gauge.range.rounded_min

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
class TickSurface(SurfaceCentered, GaugeItem):
	_properties: Graduations
	_ticks: list[Tick] = cached_property(lambda self: [])

	def __init__(self, gauge: 'Gauge', properties: Graduations, *args, **kwargs):
		self._gauge = gauge
		self._properties = properties
		self.scale = 1
		QGraphicsItemGroup.__init__(self, gauge)
		# super(TickSurface, self).__init__(parent=gauge, gauge=gauge, *args, **kwargs)
		# Surface.__init__(self, gauge)
		# super(GaugeItem, self).__init__(gauge)
		GaugeItem.__init__(self, gauge)
		self.rebuild()

	def _debug_paint(self, painter, option, widget):
		self._normal_paint(painter, option, widget)
		addCrosshair(painter, pos=self.boundingRect().center())

	def refresh(self):
		self.setPos(self.gauge.center)

		clearCacheAttr(self, 'tick_path')
		for tick in self.childItems():
			try:
				tick.refresh()
			except AttributeError:
				pass

		self._properties.labels.rebuild()

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
		for i in range(self.count + 1):
			if i * interval + self.gauge.range.rounded_min not in tick_values:
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

		self.refresh()

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


class Needle(Stateful, GaugePathItem):
	_animation: QPropertyAnimation
	_animationSignal = Signal(float)
	_value: float = 0.0

	def __init__(self, *args, **kwargs):
		super(Needle, self).__init__(*args, **kwargs)
		# self._animation = NeedleAnimation(self)
		pen = QPen()
		pen.setJoinStyle(Qt.RoundJoin)
		self.setPen(Qt.NoPen)
		self.prep_init(kwargs)
		self.refresh()
		shadow = SoftShadow(owner=self)
		self.setGraphicsEffect(shadow)

	@StateProperty(key='type', default='needle')
	def type(self) -> str:
		return self._type

	@type.setter
	def type(self, value: str):
		self._type = value

	@StateProperty(key='width', default=Size.Width(0.1, relative=True), allowNone=False, repr=True)
	def width(self) -> Size.Width:
		return self._width

	@width.setter
	def width(self, value: Size.Width):
		self._width = value

	@width.decode
	def width(self, value: str | float | int) -> Size.Width | Length:
		return parseWidth(value, type(self).width.default(type(self), self, update_source=False))

	@property
	def needleWidth(self) -> float:
		return size_px(self.width, self.gauge.radius)

	@property
	def needleLength(self) -> float:
		return self.gauge.needleLength * self.gauge.radius

	@property
	def needleSize(self) -> QSizeF:
		return QSizeF(self.needleWidth, self.needleLength)

	_shape: QPainterPath = QPainterPath()

	def shape(self) -> QPainterPath:
		return self._shape or self.path()

	# _boundingRect: QRectF = QRectF()

	# def boundingRect(self) -> QRectF:
	# 	return self._boundingRect or self.shape().boundingRect()
	#
	# def sceneBoundingRect(self) -> QRectF:
	# 	return self.mapRectFromScene(self._boundingRect or self.shape().boundingRect())

	def _default(self) -> QPainterPath:
		"""returns a standard tapering needle with a rounded bottom."""

		cx = 0
		cy = 0
		middle = QPointF(cx, cy - self.needleLength)
		needleWidth = self.needleWidth
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
		"""Returns a circle that is used as the indicator instead of a needle."""

		cx = 0
		cy = 0
		pos = QPointF(cx, cy - self.needleLength)

		path = QPainterPath()
		path.addEllipse(pos, self.needleWidth / 2, self.needleWidth / 2)

		# Set the needle's bounding rect and shape
		self._shape = shape = QPainterPath()
		bounding_rect = QRectF(0, 0, self.needleWidth, self.needleWidth)
		bounding_rect.moveCenter(QPointF(pos))
		shape.addEllipse(bounding_rect)
		self._bounding_rect = shape.boundingRect()

		return path

	def draw(self):
		if self.type == 'needle':
			self.setPath(self._default())
		elif self.type == 'edge_circle':
			self.setPath(self._edge_circle())

	def refresh(self):
		self.resetTransform()
		self.setBrush(QBrush(self.gauge.defaultColor))
		self.draw()
		self.setPos(self.gauge.center)
		self.setZValue(-500)


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


class GaugeText(AnnotationText, GaugeItem):
	def __init__(self, *args, **kwargs):
		super(GaugeText, self).__init__(*args, **kwargs)


class GaugeValueLabel(NonInteractiveLabel, ColorGradientMixin, GaugeItem):

	parent: 'Gauge'

	_debug_paint_color = Color.randomColor.QColor

	__defaults__ = {
		'format': {
			'showUnit': False,
			'decorator': False,
		},
		'geometry': {
			'x': '0px',
			'y': '0px',
			'width': '100px',
			'height': '100px',
		},
		'margins': ('0', '0', '0', '0'),
	}



	class TextBox(Text):
		parent: 'GaugeValueLabel'
		surface: 'Gauge'

		@property
		def alignment(self):
			return self.parent.alignment

		@alignment.setter
		def alignment(self, value):
			pass

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
			arc = self.surface.arc.boundingRect()
			r = max(arc.width(), arc.height()) / sqrt(2)
			r = QRectF(0, 0, r, r)
			r.moveCenter(arc.center())
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

			match self.parent.position:
				case DisplayPosition.Inline:
					diff = arc_center - gauge_center

					return arc_center - (diff * (angle_spread / 360))
				case DisplayPosition.Center:
					return gauge._center_transform.map(gauge_center)
				case _:
					raise NotImplementedError

		def _valueAccessor(self):
			return self.parent.parent.value

		def getTextScale(self, textRect: QRectF = None, limitRect: QRectF = None, transform: QTransform = None) -> float:

			scale = super(GaugeValueLabel.TextBox, self).getTextScale(textRect, limitRect, transform)

			modifyTransformValues(transform, xScale=scale, yScale=scale)
			self.setTransform(transform)

			gauge = self.parent.parent

			def colliding() -> bool:
				try:
					return self.collidesWithPath(self.mapFromParent(self.parentItem()._gauge_path()))
				except AttributeError:
					pass
				items = {i for i in self.collidingItems() if not isinstance(i, Handle) is gauge.isAncestorOf(i) and not isinstance(i, NonInteractiveLabel)}
				try:
					items -= {self.parentItem().needle}
				except AttributeError:
					pass
				return len(items) > 1

			while colliding() and scale > 0.2:
				scale *= 0.95
				modifyTransformValues(transform, xScale=scale, yScale=scale)
				self.setTransform(transform, combine=False)

			modifyTransformValues(transform, xScale=1, yScale=1)

			return scale

		def setPath(self, path: QPainterPath):
			self._shape = outline_path(path, self.parent.value_padding_px * 2 / (self.scale() or 1))
			super().setPath(path)

		_shape: QPainterPath = QPainterPath()

		def setTransform(self, matrix: QTransform, **kwargs) -> None:
			super().setTransform(matrix, **kwargs)
			scale_x = matrix.m11() * self.scale()
			scale_y = matrix.m22() * self.scale()
			scale_value = (self.scaleSelection(scale_x, scale_y) or 1)
			self._shape = outline_path(self.path(), self.parent.value_padding_px * 2 / scale_value)

		def shape(self) -> QPainterPath:
			return self._shape

		def boundingRect(self) -> QRectF:
			return self._shape.boundingRect()

		def sceneBoundingRect(self) -> QRectF:
			return self.mapToScene(self._shape).boundingRect()

	def _get_color_value(self) -> Number:
		return self.parent.value

	def _set_fill_brush(self, color: Color):
		self.textBox.setBrush(QBrush(color))

	@StateProperty(key='alignment', allowNone=False, dependencies={'geometry', 'text', 'margins'})
	def alignment(self) -> Alignment:
		if self._state_item_sources[GaugeValueLabel.alignment] is SourceType.ItemDefault:
			return self.alignment_auto()
		return self._alignment

	@alignment.setter
	def alignment(self, value: Alignment):
		self._alignment = value

	@alignment.decode
	def alignment(self, value: str) -> Alignment:
		return Alignment(AlignmentFlag[value])

	@alignment.item_default
	def alignment(self) -> Alignment:
		return Alignment(AlignmentFlag.Center)

	@StateProperty(key='format', default=None, allowNone=False)
	def format_spec(self) -> str | dict:
		return getattr(self, '_format_spec', None)

	@format_spec.setter
	def format_spec(self, value: str | dict):
		self._format_spec = value

	def format_value(self, value: Measurement) -> str:
		format_spec = self.format_spec
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

	@StateProperty(key='value-padding', default=Size.Height(0.05, relative=True), allowNone=False)
	def value_padding(self) -> Length | Dimension | None:
		return getattr(self, '_value_padding', None)

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

	@StateProperty(key='position', allowNone=False, repr=True)
	def position(self) -> DisplayPosition:
		return self._position

	@position.setter
	def position(self, value: DisplayPosition):
		self._position = value

	@position.item_default
	def position(self) -> DisplayPosition:
		return DisplayPosition.Inline

	@position.decode
	def position(self, value: str) -> DisplayPosition:
		return DisplayPosition[value]

	def alignment_auto(self) -> Alignment:
		# TODO: This a quick and slopy implementation and needs improvement

		match self.position:
			case DisplayPosition.Inline:
				return Alignment(AlignmentFlag.Center)
			case _:
				pass
		align = self.parent.alignment.combined

		min_angle, max_angle = sorted((self.parent.startAngle, self.parent.endAngle))

		angle_spread = max_angle - min_angle
		if angle_spread > 180:
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


class GaugeUnit(NonInteractiveLabel, GaugeItem):

	surface: 'Gauge'

	_debug_paint_color = Color.randomColor.QColor

	__defaults__ = {
		'geometry': {
			'x': '0px',
			'y': '0px',
			'width': '100px',
			'height': '100px',
		},
		'margins': ('0', '0', '0', '0'),
	}

	class TextBox(Text):

		surface: 'Gauge'

		@property
		def alignment(self):
			return Alignment(AlignmentFlag.Center | AlignmentFlag.Top)

		@alignment.setter
		def alignment(self, value):
			pass

		def getTextPosition(self, limitRect: QRectF = None) -> QPointF:
			try:
				value_label = self.surface.valueLabel.textBox.sceneBoundingRect()
				p = value_label.center()
				p.setY(value_label.bottom())
				p = self.mapFromScene(p)
				return p
			except AttributeError:
				pass

			return self.parent.parent.center

		def shape(self) -> QPainterPath:
			path = self.path()
			rect = self._textRect or path.boundingRect()
			return outline_path(path, rect.height() * 0.3)

		def boundingRect(self) -> QRectF:
			return self.shape().boundingRect()

		def setTransform(self, *args, **kwargs):
			super().setTransform(*args, **kwargs)

			move_direction = QPointF(0, 1)

			moved_count = 0

			if not self.parentItem().alignment == AlignmentFlag.Center:
				return

			max_travel_distance = int(ceil(sqrt(sum(i ** 2 for i in self.limitRect.size().toTuple()))))

			# TODO: Make this use transformations rather than moveBy
			while self.collidesWithItem(self.surface.needle) and abs(moved_count) < max_travel_distance:
				self.moveBy(move_direction.x(), move_direction.y())
				moved_count += 1

		def _textAccessor(self) -> str:
			value_class = self.parent.parent.valueClass
			return value_class.unit or value_class.decorator

		@property
		def limitRect(self) -> QRectF:
			arc = self.surface.arc.boundingRect()
			r = max(arc.width(), arc.height()) / sqrt(2)
			r = QRectF(0, 0, r, r)
			r.setHeight(self.parent.height_px)
			return r

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


class GaugeTickText(GaugeItem, AnnotationText):
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
		kwargs['value'] = gauge.valueClass(tick.index * group.source.interval + gauge.range.rounded_min)
		# group.size_group.addItem(self)
		self.set_formatting_func(group.format_value)
		kwargs['labelGroup'] = group
		super(GaugeTickText, self).__init__(*args, **kwargs)

	def _valueAccessor(self) -> str:
		value = self.tick.value
		return value

	@property
	def offset_relative_to(self) -> float:
		return self.group.textSize_px

	def position(self, display_position: DisplayPosition = None) -> QPointF:

		position = display_position or self.group.position

		match position:
			case DisplayPosition.Below:
				return self.tick.endPoint
			case DisplayPosition.Above:
				return self.tick.startPoint
			case DisplayPosition.Center:
				return self.tick.endPoint / 2 + self.tick.startPoint / 2
			case DisplayPosition.Left:
				return min(self.tick.startPoint, self.tick.endPoint, key=lambda p: p.x())
			case DisplayPosition.Right:
				return max(self.tick.startPoint, self.tick.endPoint, key=lambda p: p.x())
			case _:
				raise ValueError(f'Invalid position: {position}')

	@property
	def display_position(self) -> DisplayPosition:
		if self.tick.index == 0:
			return self.group.position_trailing
		elif self.tick.index == self.group.source.count - 1:
			return self.group.position_leading
		return self.group.position

	def setPath(self, path: QPainterPath):
		self._shape = outline_path(path, self.group.offset_px)
		# self._debug_paint_shape = QPainterPath(self._shape)
		super(GaugeTickText, self).setPath(path)

	_shape: QPainterPath = QPainterPath()

	def shape(self) -> QPainterPath:
		return QPainterPath(self._shape)

	def boundingRect(self) -> QRectF:
		return self._shape.boundingRect()

	def setPos(self, pos: QPointF):
		"""This method is overridden to ensure that the text is not placed overlapping the needle."""
		super(GaugeTickText, self).setPos(pos)

		angle = self.tick.angle

		disp_pos = self.display_position
		match disp_pos:
			case DisplayPosition.Below:
				move_direction = radialPoint(QPointF(0, 0), -1, angle)
			case DisplayPosition.Above:
				move_direction = radialPoint(QPointF(0, 0), 1, angle)
			case DisplayPosition.Center:
				move_direction = QPointF(0, 1)
			case DisplayPosition.Left:
				move_direction = QPointF(1, 0)
			case DisplayPosition.Right:
				move_direction = QPointF(-1, 0)
			case _:
				move_direction = radialPoint(QPointF(0, 0), 1, angle)

		moved_count = 0

		max_travel_distance = int(ceil(sqrt(sum(i**2 for i in self.limitRect.size().toTuple()))))
		self.prepareGeometryChange()
		self._shape = outline_path(self.path(), self.group.offset_px)

		arc_weight = self.gauge.arc.pen().width() / 2
		if pos == self.tick.startPoint:
			self.moveBy(*(move_direction * arc_weight).toTuple())
		else:
			if arc_weight > abs(self.group.source.length_px):
				diff = arc_weight - abs(self.group.source.length_px)
				self.moveBy(*(move_direction * diff).toTuple())

		while (self.collidesWithItem(self.gauge.arc) or self.collidesWithItem(self.tick)) and moved_count < max_travel_distance:
			self.moveBy(move_direction.x(), move_direction.y())
			moved_count += 1

		self.prepareGeometryChange()
		self._shape = outline_path(self.path(), 5)

	def refresh(self):
		if (interval := self.group.interval) > 1 and self.tick.index % interval:
			self.hide()
			return
		else:
			self.show()

		if self.rotated:
			self.setRotation(self.tick.angle + 90)

		super(GaugeTickText, self).refresh()
		self.setPos(self.position())

	@property
	def allowedWidth(self) -> float:

		radius = self.gauge.safe_radius if self.group.position == DisplayPosition.Below else self.gauge.exterior_safe_radius
		interval = self.group.source.interval

		arch_length_px = float(radius * self.gauge.fullAngle / 180 * pi)

		interval_arch_coverage = float(interval / self.gauge.range.rounded_range)

		return arch_length_px * interval_arch_coverage

	@property
	def rotated(self):
		index = self.tick.index
		if index == 0:
			return self.group.rotation_trailing
		if index == self.group.source.count - 1:
			return self.group.rotation_leading
		return self.group.rotation

	def getTextScale(self, textRect: QRectF = None, limitRect: QRectF = None, transform=None) -> float:
		textRect = textRect or self._textRect or self._update_path()
		limitRect = limitRect or self.limitRect

		width = (textRect.width()) or 1
		height = (textRect.height()) or 1

		wScale = limitRect.width() / width
		hScale = limitRect.height() / height
		return round(self.scaleSelection(wScale, hScale), 4)

	def scaleSelection(self, x, y):
		return y


class GaugeTickTextGroup(AnnotationLabels[GaugeTickText]):

	__defaults__ = {
		'height': Size.Height(0.15, relative=True),
		# 'offset': Size.Height(0.01, relative=True),
		'position': DisplayPosition.Below,
		'offset': Size.Height(0.10, relative=True),
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
	def text_size_relative_to(self) -> Length | Size.Height | float:
		return self.gauge.radius

	@property
	def offset_relative_to(self) -> Length | Dimension:
		return self.source.length_px or self.textSize_px

	@StateProperty
	def format_spec(self) -> str | dict:
		pass

	@format_spec.item_default
	def format_spec(self) -> dict | str:
		return {'showUnit': False, 'decorator': False}

	@cached_property
	def size_group(self) -> SizeGroup:
		tick_type = self._ticks.tick_type.name.lower()
		return self.gauge.localGroup.getAttrGroup(f'local.{tick_type}-textSize', matchAll=True)

	def onAxisTransform(self, axis: Axis):
		print('onAxisTransform', axis)

	def onDataChange(self, axis: Axis):
		print('onDataChange', axis)

	def refresh(self):
		for label in self:
			label.refresh()

	def __init__(self, graduations: Graduations, surface: 'TickSurface'):
		self._gauge = graduations.gauge
		self._ticks = graduations
		super(GaugeTickTextGroup, self).__init__(graduations, surface)

	@cached_property
	def label_kwargs_generator(self) -> Iterator[dict[str, GaugeItem]]:
		unlabeled_ticks = self.unlabeled_ticks
		brush = self.fill_brush
		for tick in sorted(unlabeled_ticks, key=lambda t: t.index):
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

	@StateProperty(key='rotate', allowNone=False, default=False, repr=True, after=AnnotationLabels.refresh)
	def rotation(self) -> bool:
		return self._rotation

	@rotation.setter
	def rotation(self, value: bool):
		self._rotation = value

	def _get_max_label(self) -> GaugeTickText:
		return max(self, key=lambda label: label.value)

	@StateProperty(key='position-leading', dependancies={'position'}, after=AnnotationLabels.refresh)
	def position_leading(self) -> DisplayPosition:
		return getattr(self, '_position_leading', Unset) or type(self).position_leading.get_item_default(self)

	@position_leading.setter
	def position_leading(self, value: DisplayPosition):
		self._position_leading = value

	@position_leading.item_default
	def position_leading(self) -> DisplayPosition:
		return self.position

	@position_leading.decode
	def position_leading(self, value: str) -> DisplayPosition:
		return DisplayPosition[value]

	@StateProperty(key='position-trailing', dependancies={'position'}, after=AnnotationLabels.refresh)
	def position_trailing(self) -> DisplayPosition:
		return getattr(self, '_position_trailing', Unset) or type(self).position_trailing.get_item_default(self)

	@position_trailing.setter
	def position_trailing(self, value: DisplayPosition):
		self._position_trailing = value

	@position_trailing.item_default
	def position_trailing(self) -> DisplayPosition:
		return self.position

	@position_trailing.decode
	def position_trailing(self, value: str) -> DisplayPosition:
		return DisplayPosition[value]

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

	@StateProperty(key='align-trailing', allowNone=False)
	def align_trailing(self) -> AlignmentFlag:
		return self._align_trailing

	@align_trailing.setter
	def align_trailing(self, value: AlignmentFlag):
		self._align_trailing = value

	@align_trailing.item_default
	def align_trailing(self) -> AlignmentFlag:
		# return AlignmentFlag.CenterRight if self.position is DisplayPosition.Below else AlignmentFlag.CenterLeft
		disp_pos = self.position
		match disp_pos:
			case DisplayPosition.Below:
				return AlignmentFlag.TopCenter
			case DisplayPosition.Above:
				return AlignmentFlag.BottomCenter
			case DisplayPosition.Left:
				return AlignmentFlag.CenterRight
			case DisplayPosition.Right:
				return AlignmentFlag.CenterLeft
			case DisplayPosition.Center:
				return AlignmentFlag.Center
			case _:
				return AlignmentFlag.Center

	@align_trailing.decode
	def align_trailing(self, value: str) -> AlignmentFlag:
		return AlignmentFlag[value]

	@StateProperty(key='align-leading', allowNone=False)
	def align_leading(self) -> AlignmentFlag:
		return self._align_leading

	@align_leading.setter
	def align_leading(self, value: AlignmentFlag):
		self._align_leading = value

	@align_leading.item_default
	def align_leading(self) -> AlignmentFlag:
		disp_pos = self.position
		match disp_pos:
			case DisplayPosition.Below:
				return AlignmentFlag.TopCenter
			case DisplayPosition.Above:
				return AlignmentFlag.BottomCenter
			case DisplayPosition.Left:
				return AlignmentFlag.CenterRight
			case DisplayPosition.Right:
				return AlignmentFlag.CenterLeft
			case DisplayPosition.Center:
				return AlignmentFlag.Center
			case _:
				return AlignmentFlag.Center

	@align_leading.decode
	def align_leading(self, value: str) -> AlignmentFlag:
		return AlignmentFlag[value]

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
	def unlabeled_ticks(self) -> list[Tick]:
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
	"""  I need an algorithm that will determine the best number of major, minor, and micro ticks on a gauge.

	Known:
	- radius of the gauge
	- the starting and end angle of the gauge arc
	- min/max values that will be displayed

	It needs to take in to effect the following options:
	 - tick width so that ticks don't overlap
	 - an optional min number of ticks for each level
	 - an optional max number of ticks for each level
	 - an optional number of preferred ticks which will override min tick
	 - a set of required interval factors
	 - a set of preferred interval factors
	 - a set of ignored factors

	Example:
		min: -2
		max: 22
		value range: 24
		factors: 1, 2, 3, 4, 6, 8, 12, 24
		preferred factors: 5, 10

		Since, none of the factors are in the preferred factors, use the
		preferred factors to find the smallest value range that
		is a multiple of any preferred factors.

		value_range = 24
		preferred_factors = [5, 10]
		new_range = min([((value_range // factor) + 1) * factor for factor in preferred_factors], key=lambda x: abs(x - value_range), default=10)


		preferred_factors: (5, 10)


	If value range is a prime number then the algorithm will need to be able to handle that.
	Ideally it would find the next non-prime number and use that as the max value.
	"""

	_center_offset: QPointF | QPointF = QPointF(0, 0)

	__value: float = 0.0
	_needleAnimation: QPropertyAnimation
	valueChanged = Signal(float)
	arc: GaugeArc

	class GaugeRange(Stateful):
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
			self._gauge = gauge
			self.state = self.prep_init(state)

		@StateProperty(key='round-to', repr=True)
		def round_to(self) -> int | float:
			return self._round_to

		@round_to.setter
		def round_to(self, value: int | float):
			self._round_to = value

		@round_to.item_default
		def round_to(self) -> int | float:
			_value_range = abs(float(self.max - self.min))

			if 99 < _value_range <= 350:
				return 10

			if log10(_value_range).is_integer():
				return _value_range / 10

			_power = int(log10(_value_range)) + 1

			while _value_range % 10 ** _power > 0:
				_power -= 1

			# if 0.5 < _power < 1:
			# 	return 1
			return 10 ** round(_power)

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
			return self._gauge.valueClass(floor(float(self.min) / round_to) * round_to)

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
			return self._gauge.valueClass(ceil(float(self.max) / round_to) * round_to)

		@cached_property
		def rounded_max(self):
			rounded_range = self._rounded_range
			if isinstance(rounded_range, int) or (isinstance(rounded_range, float) and rounded_range.is_integer()):
				if is_prime(rounded_range):
					return self._rounded_max + 1
				return self._rounded_max

			scaled_range = rounded_range
			while scaled_range < 1:
				scaled_range *= 10

			scaled_amount = scaled_range / rounded_range

			scaled_range = ceil(scaled_range)

			if is_prime(scaled_range):
				scaled_range += 1

			scaled_range /= scaled_amount

			return scaled_range

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
						return self.ranges[key]
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
		super()._init_defaults_()
		self.__value = value = self._valueClass(0)

		self._pen = QPen(self.defaultColor)

		self.major_ticks_surface = TickSurface(self, self.majorDivisions)
		self.minor_ticks_surface = TickSurface(self, self.minorDivisions)
		self.micro_ticks_surface = TickSurface(self, self.microDivisions)
		# a = self.arc
		# self.unitLabel = unit_label = GaugeUnit(self)

	@StateProperty(key='major', repr=True)
	def majorDivisions(self) -> Graduations:
		return self._majorDivisions

	@majorDivisions.factory
	def majorDivisions(self):
		return Graduations(gauge=self, type=Graduations.Type.Major)

	@majorDivisions.setter
	def majorDivisions(self, value: Graduations):
		self._majorDivisions = value

	@StateProperty(key='minor', repr=True)
	def minorDivisions(self) -> Graduations:
		return self._minorDivisions

	@minorDivisions.factory
	def minorDivisions(self):
		return Graduations(gauge=self, type=Graduations.Type.Minor)

	@minorDivisions.setter
	def minorDivisions(self, value: Graduations):
		self._minorDivisions = value

	@StateProperty(key='micro', repr=True)
	def microDivisions(self) -> Graduations:
		return self._microDivisions

	@microDivisions.factory
	def microDivisions(self):
		return Graduations(gauge=self, type=Graduations.Type.Micro)

	@microDivisions.setter
	def microDivisions(self, value: Graduations):
		self._microDivisions = value

	@StateProperty(key='needle', repr=True)
	def needle(self) -> Needle:
		return self._needle

	@needle.factory
	def needle(self) -> Needle:
		return Needle(self)

	@needle.setter
	def needle(self, value: Needle):
		self._needle = value

	@StateProperty(key='arc', repr=True)
	def arc(self) -> GaugeArc:
		return self._arc

	@arc.factory
	def arc(self) -> GaugeArc:
		return GaugeArc(self)

	@arc.setter
	def arc(self, value: GaugeArc):
		self._arc = value

	@StateProperty(key='value-label', repr=True)
	def valueLabel(self) -> GaugeValueLabel:
		return self._valueLabel

	@valueLabel.factory
	def valueLabel(self) -> GaugeValueLabel:
		label = GaugeValueLabel(self)
		label.textBox.setParentItem(self)
		return label

	@valueLabel.setter
	def valueLabel(self, value: GaugeValueLabel):
		self._valueLabel = value

	@StateProperty(key='unit-label', repr=True)
	def unitLabel(self) -> GaugeUnit:
		return self._unitLabel

	@unitLabel.factory
	def unitLabel(self) -> GaugeUnit:
		label = GaugeUnit(self)
		label.textBox.setParentItem(self)
		return label

	@unitLabel.setter
	def unitLabel(self, value: GaugeUnit):
		self._unitLabel = value

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
		self.needle.refresh()
		self.arc.refresh()

		value = self.__value
		angle = float(value - self._range.rounded_min) / self._range.rounded_range * self.fullAngle + self.startAngle
		angle = sorted((self.startAngle, angle, self.endAngle))[1]
		self.needle.setRotation(angle)
		self.rebuild()

	_center_transform: QTransform = QTransform()

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

		bounds_rect = self.rect()

		self._update_shape()
		own_shape = self._shape()
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

		self._center_transform = QTransform()

		self.major_ticks_surface.setTransform(t, combine=False)
		self.minor_ticks_surface.setTransform(t, combine=False)
		self.micro_ticks_surface.setTransform(t, combine=False)

		self.needle.setTransform(t, combine=False)
		self.arc.setTransform(t, combine=False)

		self.valueLabel.textBox.updateTransform(updatePath=False)
		self.valueLabel.textBox.setTransform(t, combine=True)

		self.unitLabel.textBox.updateTransform(updatePath=False)

		# Only update the unit label location if it's not relative to the value label
		if False and self.unitLabel:
			self.unitLabel.textBox.setTransform(t, combine=True)
		else:
			t = self.unitLabel.textBox.transform()
			self.unitLabel.textBox.setTransform(t, combine=False)

	@defer
	def rebuild(self):
		self.major_ticks_surface.rebuild()
		self.minor_ticks_surface.rebuild()
		self.micro_ticks_surface.rebuild()

		self.needle.refresh()
		self.valueLabel.textBox.refresh()
		self.unitLabel.textBox.refresh()
		self._update_shape()
		self.recenter()

	def refresh(self):
		self.major_ticks_surface.refresh()
		self.minor_ticks_surface.refresh()
		self.micro_ticks_surface.refresh()

		self.needle.refresh()
		self._update_shape()
		self.valueLabel.textBox.refresh()
		self.unitLabel.textBox.refresh()
		self.recenter()

	def _update_shape(self):
		clearCacheAttr(self, 'value_text_box_area_rect', 'full_gauge_path')

	def _shape(self):
		return self.full_gauge_path

	def parentResized(self, arg: Union[QPointF, QSizeF, QRectF]):
		super().parentResized(arg)
		self.refresh()

	@property
	def value(self) -> GaugeValue:
		return self._value

	@value.setter
	def value(self, value):
		if isinstance(value, (int, float)):
			self.valueClass = value
			self._value = value
			self.valueLabel.textBox.refresh()
			self.unitLabel.textBox.refresh()
			self._update_shape()
	# if isinstance(value, Measurement):
	# 	self.unit = value

	@property
	def _value(self):
		return self.__value

	@_value.setter
	def _value(self, value: float):
		self.__value = value
		angle = float(value - self._range.rounded_min) / self._range.rounded_range * self.fullAngle + self.startAngle
		angle = sorted((self.startAngle, angle, self.endAngle))[1]
		self.needle.setRotation(angle)

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

	@StateProperty(key='range', link=GaugeRange, allowNone=False, repr=True)
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
		return {'x': value, 'y': value}

	@property
	def center(self) -> QPointF:

		p = self.alignment.multipliersAlt
		rect = self.boundingRect()
		x = rect.width() * p[0]
		y = rect.height() * p[1]
		p = QPointF(x, y)

		p -= self._center_offset
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
		return max(min(self.height(), self.width()) / 2 - self.baseWidth, 1)

	@property
	def radius(self):
		return min(self.radius_max, self._radius)

	@StateProperty(key='radius', default=Size.Height(1.0, relative=True), allowNone=False, repr=True)
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

		if major.enabled:
			trim = max(major.length_px + major.width_px / 2, trim)
		if minor.enabled:
			trim = max(minor.length_px + minor.width_px / 2, trim)
		if micro.enabled:
			trim = max(micro.length_px + micro.width_px / 2, trim)

		return self.radius - trim

	@property
	def exterior_safe_radius(self):
		major: Graduations = self.majorDivisions
		minor: Graduations = self.minorDivisions
		micro: Graduations = self.microDivisions

		arc_line_width = self.arc.pen().widthF()

		extend = max(arc_line_width / 2, 0)

		if major.enabled:
			extend = max(major.width_px / 2, extend)
		if minor.enabled:
			extend = max(minor.width_px / 2, extend)
		if micro.enabled:
			extend = max(micro.width_px / 2, extend)

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
		path.addPath(self.mapFromItem(self.valueLabel.textBox, self.valueLabel.textBox.shape()))
		path.addPath(self.mapFromItem(self.unitLabel.textBox, self.unitLabel.textBox.shape()))
		path.addPath(self.mapFromItem(self.needle, self.needle.shape()))
		return path.simplified()

	def full_gauge_rect(self) -> QRectF:
		return self.full_gauge_path.boundingRect()
