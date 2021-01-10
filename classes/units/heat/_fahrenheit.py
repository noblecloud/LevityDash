from . import _Heat


class Fahrenheit(_Heat):
	_unit = 'f'

	def _celsius(self):
		from ._celcius import Celsius
		return (self._value - 32) / 1.8

	def _fahrenheit(self):
		return self._value
	# (32°F − 32) × 1.8

	def _kelvin(self):
		# (32°F − 32) × 1.8 + 273.15
		return (self._value - 32) / 1.8 + 273.15
