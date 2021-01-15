from . import _Length, Millimeter, Centimeter, Meter, Kilometer
from .._unit import AbnormalScale


class _Imperial(_Length, AbnormalScale):
	# 0 base, 1 line, 2 inch, 3 foot, 4 yard
	_factors = [1.0, 12.0, 12.0, 3.0, 1760.0]
	_format = '{:2.2f}'
	_metric: Meter
	_scale: int

	def _lines(self):
		return self.changeScale(0)

	def _inches(self):
		return self.changeScale(1)

	def _feet(self):
		return self.changeScale(2)

	def _yards(self):
		return self.changeScale(3)

	def _miles(self):
		return self.changeScale(4)

	def _millimeter(self):
		return self._metric.mm.raw

	def _centimeter(self):
		return self._metric.cm.raw

	def _meter(self):
		return self._metric.m.raw

	def _kilometer(self):
		return self._metric.km.raw


class Line(_Imperial):
	_format = '{:2.2f}'
	_scale = 0
	_metric: Millimeter
	_unit = 'ln'

	def __init__(self, value):
		super().__init__(value)
		self._metric = Millimeter(value * 2.11666666)


class Inch(_Imperial):
	_format = '{:2.2f}'
	_scale = 1
	_metric: Centimeter
	_unit = 'in'

	def __init__(self, value):
		super().__init__(value)
		self._metric = Centimeter(value * 2.54)


class Foot(_Imperial):
	_scale = 2
	_metric: Meter
	_unit = 'ft'


	def __init__(self, value):
		super().__init__(value)
		self._metric = Meter(value * 0.3048)


class Yard(_Imperial):
	_scale = 3
	_metric: Meter
	_unit = 'yd'

	def __init__(self, value):
		super().__init__(value)
		self._metric = Meter(value * 0.9144)


class Mile(_Imperial):
	_scale = 4
	_metric: Kilometer
	_unit = 'mi'

	def __init__(self, value):
		super().__init__(value)
		self._metric = Kilometer(value * 1.609344)
