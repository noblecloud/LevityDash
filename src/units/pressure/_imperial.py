from . import _Pressure


class inHg(_Pressure):
	_unit = 'inHg'

	def _hPa(self):
		return self * 33.86389

	def _mmHg(self):
		return self * 25.4

	def _inHg(self):
		return self
