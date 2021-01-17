from . import _Pressure


class mmHg(_Pressure):
	_unit = "mmHg"

	def _hPa(self):
		return self * 1.333224

	def _mmHg(self):
		return self

	def _inHg(self):
		return self * 0.03937007827511842


class hPa(_Pressure):
	_format = "{:4.1f}"
	_unit = 'hPa'

	def _hPa(self):
		return self

	def _mmHg(self):
		return self * 0.7500615050434136

	def _inHg(self):
		return self * 0.02952998016471232
