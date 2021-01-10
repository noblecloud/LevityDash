from units._unit import Unit


class _Heat(Unit):

	@property
	def f(self):
		from units.heat import Fahrenheit
		return Fahrenheit(self._fahrenheit())

	@property
	def c(self):
		from units.heat import Celsius
		return Celsius(self._celsius())
