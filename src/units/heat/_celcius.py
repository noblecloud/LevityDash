from . import _Heat


class Celsius(_Heat):
	_unit = 'c'

	def _celsius(self, delta: bool = False):
		return self

	def _fahrenheit(self, delta: bool = False):
		if delta:
			return self * 1.8
		else:
			return (self * 1.8) + 32

	def _kelvin(self):
		return self + 273.15
