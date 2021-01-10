# from typing import Callable, Union
from units import Callable, Union

from units._unit import Unit


class _Length(Unit):
	_value: Union[int, float]
	_millimeter: Callable
	_centimeter: Callable
	_meter: Callable
	_kilometer: Callable
	_lines: Callable
	_inches: Callable
	_feet: Callable
	_yards: Callable
	_miles: Callable

	def __init__(self, value):
		self._value = value

	@property
	def mm(self):
		from units.length import Millimeter
		return Millimeter(self._millimeter())

	@property
	def cm(self):
		from units.length import Centimeter
		return Centimeter(self._centimeter())

	@property
	def m(self):
		from units.length import Meter
		return Meter(self._meter())

	@property
	def km(self):
		from units.length import Kilometer
		return Kilometer(self._kilometer())

	@property
	def inch(self):
		from units.length import Inch
		return Inch(self._inches())

	@property
	def ft(self):
		from units.length import Foot
		return Foot(self._feet())

	@property
	def yd(self):
		from units.length import Yard
		return Yard(self._yards())

	@property
	def mi(self):
		from units.length import Mile
		return Mile(self._miles())
