from . import _Heat


class Celsius(_Heat):
	_unit = 'c'

	def _celsius(self):
		return self.value

	def _fahrenheit(self):
		from ._fahrenheit import Fahrenheit
		return (self._value * 1.8) + 32

	def _kelvin(self):
		return self._value + 273.15
