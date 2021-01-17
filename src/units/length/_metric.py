from typing import Any

from . import _Length


class _Metric(_Length):
	_format = '{:2.1f}'
	_magnitude: int
	_scale: int
	_imperial: Any

	def _feet(self):
		return self._meter() * 3.2808399

	def _inches(self):
		return self._feet() * 12

	def _miles(self):
		return self._feet() * 0.0001893939394

	def _yards(self):
		return self._feet() * 3

	def _millimeter(self):
		return self * pow(10, self._magnitude + 2)

	def _centimeter(self):
		return self * pow(10, self._magnitude + 1)

	def _meter(self):
		return self * pow(10, self._magnitude - 1)

	def _kilometer(self):
		return self * pow(10, self._magnitude - 4)


class Millimeter(_Metric):
	_type = 'microDistance'
	_format = '{:3.1f}'
	_magnitude = -2
	_scale = 1
	_unit = 'mm'


class Centimeter(_Metric):
	_type = 'smallDistance'
	_magnitude = -1
	_scale = 2
	_unit = 'cm'


class Meter(_Metric):
	_type = 'mediumDistance'
	_magnitude = 1
	_scale = 3
	_unit = 'm'


class Kilometer(_Metric):
	_type = 'largeDistance'
	_magnitude = 4
	_scale = 4
	_unit = 'km'
