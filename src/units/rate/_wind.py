from units.length import _Length
from units.time import _Time
from . import _Rate

class Wind(_Rate):
	_type = 'wind'
	_numerator: _Length
	_denominator: _Time

	@property
	def fts(self):
		return Wind(self._numerator.ft, self._denominator.s)

	@property
	def mih(self):
		converted = Wind(self._numerator.mi, self._denominator.hr)
		converted._suffix = 'mph'
		return converted

	@property
	def mph(self):
		return self.mih

	@property
	def inh(self):
		return Wind(self._numerator.inch, self._denominator.hr)

	@property
	def ms(self):
		return Wind(self._numerator.m, self._denominator.s)

	@property
	def mh(self):
		return Wind(self._numerator.m, self._denominator.hr)

	@property
	def kmh(self):
		return Wind(self._numerator.km, self._denominator.hr)

	@property
	def mmh(self):
		return Wind(self._numerator.mm, self._denominator.hr)

