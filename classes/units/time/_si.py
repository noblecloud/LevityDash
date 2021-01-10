from . import _Time


class Millisecond(_Time):
	_format = '{:4.0f}'
	_scale = 0


class Second(_Time):
	_format = '{:2.1f}'
	_scale = 1


class Minute(_Time):
	_format = '{:2.1f}'
	_scale = 2


class Hour(_Time):
	_scale = 3


class Day(_Time):
	_scale = 4
