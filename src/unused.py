from datetime import datetime
from typing import Callable, Union

from pytz import timezone

from general import locale


class UnitConverter:
	heat: Callable
	speed: Callable
	pressure: Callable
	length: Callable
	rate: Callable
	time: Callable
	datetime: Callable

	global locale

	@staticmethod
	def heat(value: Union[int, float], unit: str) -> (float, str):
		if locale == 'us':
			if unit == 'c':
				return (value * 1.8) + 32, 'f'
			else:
				return value

	@staticmethod
	def speed(value: Union[int, float], unit: str) -> (float, str):
		if locale == 'us':
			if unit == 'm/s':
				return value * 2.2369362920544, 'mph'
			else:
				return value

	@staticmethod
	def pressure(value: Union[int, float], unit: str) -> (float, str):
		if locale == 'us':
			if unit == 'mb':
				return value * 0.029523, 'inHg'
			else:
				return value

	@staticmethod
	def length(value: Union[int, float], unit: str) -> (float, str):
		if locale == 'us':
			if unit == 'mm':
				return value * 0.039370, 'in'
			elif unit == 'm':
				return value + 3.2808, 'ft'
			elif unit == 'km':
				return value * 0.62137, 'mi'
			else:
				return value

	@staticmethod
	def rate(value: Union[int, float], unit: str) -> (float, str):
		if locale == 'us':
			if unit == 'mm/s':
				return value * 0.039370, 'in/s'
			elif unit == 'mm/h':
				return value * 0.039370, 'in/h'
			else:
				return value

	@staticmethod
	def datetime(value: int, *args, **kwargs) -> (datetime, timezone):
		global tz
		return datetime.fromtimestamp(value, tz), tz

	_data = {'heat': heat, 'speed': speed, 'pressure': pressure, 'length': length,
	         'rate': rate, 'datetime': datetime, 'time': datetime}

	def __contains__(self, key):
		return key in self._data.keys()

	def __getitem__(self, item) -> staticmethod:
		return self._data[item].__func__

	def __getattr__(self, item) -> staticmethod:
		return self._data[item].__func__
