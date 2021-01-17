from units._unit import Measurement


class Humidity(Measurement):
	_type = 'concentration'
	_format = "{:2d}"
	_unit = ''
	_suffix = '%'
