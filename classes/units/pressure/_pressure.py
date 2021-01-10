
from units._unit import Unit


class _Pressure(Unit):
	_format = "{:2.2f}"

	def __init__(self, value):
		self._value = value

	@property
	def mbar(self):
		from units.pressure import hPa
		return hPa(self._hPa())

	@property
	def mb(self):
		from units.pressure import hPa
		return hPa(self._hPa())

	@property
	def hPa(self):
		from units.pressure import hPa
		return hPa(self._hPa())

	@property
	def mmHg(self):
		from units.pressure import mmHg
		return mmHg(self._mmHg())

	@property
	def inHg(self):
		from units.pressure import inHg
		return inHg(self._inHg())
