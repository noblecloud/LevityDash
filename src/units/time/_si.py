from . import _Time


class Millisecond(_Time):
	_unit = 'ms'
	_format = '{:4.0f}'
	_scale = 0


class Second(_Time):
	_unit = 's'
	_format = '{:2.1f}'
	_scale = 1


class Minute(_Time):
	_unit = 'min'
	_format = '{:2.1f}'
	_scale = 2


class Hour(_Time):
	_unit = 'hr'
	_scale = 3


class Day(_Time):
	_unit = 'd'
	_scale = 4
