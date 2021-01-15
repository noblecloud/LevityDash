from . import _Pressure


class inHg(_Pressure):
	_unit = 'inHg'

	def _hPa(self):
		return self._value * 33.86389

	def _mmHg(self):
		return self._value * 25.4

	def _inHg(self):
		return self._value
