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
from functools import cached_property
from math import floor, isclose, isinf, log10
from typing import TYPE_CHECKING, Optional, Type

from numpy import ceil
from WeatherUnits import Humidity, Measurement, Wind

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.stateful import StateProperty
from LevityDash.lib.ui import UILogger
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.elements import StatefulGaugeItem
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.scale import decode_measurement
from LevityDash.lib.utils.data import MinMax
from LevityDash.lib.utils.shared import clearCacheAttr, is_prime

if TYPE_CHECKING:  # the real import would be a cycle; see the module docstring
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Gauge import Gauge

#: The display class these meters belong to, handed over by `Gauge.py` once it has
#: defined it. Annotations here resolve against *this* module's globals.
Gauge = None

log = UILogger.getChild('meter')

__all__ = ['GaugeRange', 'Meter']


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
