from collections import Callable
from datetime import datetime, timedelta
from math import log, pi, sin
from typing import Union

import numpy as np
from numpy import array, flip, flipud, pi
from PySide2.QtGui import QFont
from pytz import timezone

from os.path import abspath

configPath = abspath('../config.ini')


class FontInterface:
	_font: QFont = QFont()
	_size: Union[float, int] = 0

	def __init__(self, fontName):
		self._font.setFamily(fontName)

	def sized(self, value):
		if isinstance(value, int):
			self._font.setPointSize(value)
		elif isinstance(value, float):
			self._font.setPointSizeF(value)
		return self._font

	@property
	def size(self):
		return self._size

	@size.setter
	def size(self, value):
		self._size = value

	def __repr__(self):
		if isinstance(self._size, int):
			self._font.setPointSize(self._size)
		elif isinstance(self._size, float):
			self._font.setPointSizeF(self._size)
		return self._font


class Fonts:
	glyphs = FontInterface(u"Weather Icons")


class Keys:
	weatherFlowToken = 'f2f4cc66-7dec-4b09-bf64-f70c01da9690'


class fields:
	REALTIME: list[str] = ['precipitation', 'precipitation_type', 'temp', 'feels_like', 'dewpoint', 'wind_speed',
	                       'wind_gust', 'baro_pressure', 'visibility', 'humidity', 'wind_direction', 'sunrise',
	                       'sunset',
	                       'cloud_cover', 'cloud_ceiling', 'cloud_base', 'surface_shortwave_radiation', 'moon_phase',
	                       'weather_code']
	NOWCAST: list[str] = ['precipitation', 'precipitation_type', 'temp', 'feels_like', 'dewpoint', 'wind_speed',
	                      'wind_gust', 'baro_pressure', 'visibility', 'humidity', 'wind_direction', 'sunrise', 'sunset',
	                      'cloud_cover', 'cloud_ceiling', 'cloud_base', 'surface_shortwave_radiation', 'weather_code']
	HOURLY: list[str] = ['precipitation', 'precipitation_type', 'precipitation_probability', 'temp', 'feels_like',
	                     'dewpoint', 'wind_speed', 'wind_gust', 'baro_pressure', 'visibility', 'humidity',
	                     'wind_direction', 'sunrise', 'sunset', 'cloud_cover', 'cloud_ceiling', 'cloud_base', 'epa_aqi',
	                     'surface_shortwave_radiation', 'moon_phase', 'weather_code']
	DAILY: list[str] = ['precipitation', 'precipitation_accumulation', 'temp', 'feels_like', 'wind_speed',
	                    'baro_pressure', 'visibility', 'humidity', 'wind_direction', 'sunrise', 'sunset', 'moon_phase',
	                    'weather_code']
	HISTORICAL: list[str] = ['precipitation', 'precipitation_type', 'temp', 'feels_like', 'dewpoint', 'wind_speed',
	                         'wind_gust', 'baro_pressure', 'visibility', 'humidity', 'wind_direction', 'sunrise',
	                         'sunset', 'cloud_cover', 'cloud_ceiling', 'cloud_base', 'surface_shortwave_radiation',
	                         'weather_code']

	values: dict[str, list] = {'realtime': REALTIME, 'nowcast': NOWCAST, 'hourly': HOURLY, 'daily': DAILY}


FORECAST_TYPES = ['historical', 'realtime', 'nowcast', 'hourly', 'daily']

tz = timezone("US/Eastern")


class maxDates:

	def __init__(self):
		pass

	@staticmethod
	def historical() -> str:
		date = datetime.now() - timedelta(hours=3)
		print(date.strftime('%Y-%m-%d %H:%M:%S'))
		return date.strftime('%Y-%m-%d %H:%M:%S')

	@staticmethod
	def daily() -> str:
		date = datetime.now() + timedelta(days=14, hours=20)
		return date.strftime('%Y-%m-%d %H:%M:%S')

	@staticmethod
	def hourly() -> str:
		# date = datetime.now() + timedelta(hours=107, minutes=50)
		date = datetime.now() + timedelta(hours=72)
		return date.strftime('%Y-%m-%d %H:%M:%S')

	@staticmethod
	def realtime() -> str:
		date = datetime.now() + timedelta(minutes=2)
		return date.strftime('%Y-%m-%d %H:%M:%S')

	@staticmethod
	def nowcast() -> str:
		date = datetime.now() + timedelta(minutes=359)
		return date.strftime('%Y-%m-%d %H:%M:%S')


class Colors:
	kelvin = {3000: '#FFB16E', 3500: '#FFC18D', 4000: '#FFCEA6', 4500: '#FFDABB', 5000: '#FFE4CE', 5500: '#FFEDDE',
	          6000: '#FFF6ED'}

	def kelvinToHEX(self, temp: int) -> str:

		value = self.kelvinToRGB(temp)
		return '#%02x%02x%02x' % value

	def kelvinToRGB(self, temp: int) -> tuple[int, int, int]:

		def cleanup(value, limit):
			if value < 0:
				value = 0
			elif value > limit:
				value = limit
			else:
				value = int(value)
			return value

		# https://tannerhelland.com/2012/09/18/convert-temperature-rgb-algorithm-code.html

		if temp == 0:
			return 0, 0, 0

		temp /= 100

		# calculate red
		if temp <= 66:
			red = 255
		else:
			red = temp - 60
			red = 329.698727446 * pow(red, -0.1332047592)

		red = cleanup(red, 255)

		# calculate green
		if temp <= 66:
			green = temp
			green = 99.4708025861 * log(green) - 161.1195681661
		else:
			green = temp - 60
			green = 288.1221695283 * pow(green, -0.0755148492)

		green = cleanup(green, 255)

		# calculate blue
		if temp >= 66:
			blue = 255
		else:
			if temp <= 19:
				blue = 0
			else:
				blue = temp - 10
				blue = 138.5177312231 * log(blue) - 305.0447927307

		blue = cleanup(blue, 255)

		# print("{}, {}, {}, {}, ".format(red, green, blue, temp))

		return red, green, blue


class FractionalPi:

	def __init__(self, size: int, device: Callable = sin):
		self.device = device
		self.size = size
		self.step = pi / size
		self.current = 0

	def __iter__(self):
		return self

	def __next__(self):
		return self.next()

	def next(self):
		if self.current <= self.size:
			cur, self.current = self.current, self.current + 1
			return self.device(cur * self.step)
		raise StopIteration()


class FadeFilter:
	step: float
	multiplier: Union[int, float]
	current: int = 0
	filtedArray: list = []
	direction: str

	def __init__(self, multiplier: int = 1, direction: str = 'up'):
		self.multiplier = multiplier
		self.direction = direction

	def fadeArray(self, array: array):
		self.step = (array.size * self.multiplier) / 1


class LinearFade(FadeFilter):

	def __init__(self, multiplier: int = 1, direction: str = 'up'):
		super().__init__()
		self.multiplier = multiplier
		self.direction = direction

	def fadeArray(self, array: array) -> array:
		super().fadeArray(array)

		multiplier = FractionalPi(array.size)
		for x in array:
			x *= multiplier.next()
			self.filtedArray.append(x)
		if self.direction == 'up':
			return flipud(array)
		return np.array(self.filtedArray)


class LinearFade(FadeFilter):

	def __init__(self, multiplier: int = 1, direction: str = 'up'):
		super().__init__()
		self.multiplier = multiplier
		self.direction = direction

	def fadeArray(self, array: array) -> array:
		super().fadeArray(array)

		filter = np.linspace(1, 1, array[0].size)
		diff = abs(round(array[0].size * .95) - array[0].size)
		step = 1 / diff
		multiplier = 0
		for x in range(round(array[0].size * .95), array[0].size):
			if filter[x] - (step + multiplier) <= 0:
				filter[x] = filter[x] - (step * multiplier)
			multiplier += 1

		multiplier = FractionalPi(array.size)
		for x in array:
			x *= multiplier.next()
			self.filtedArray.append(x)

		filter = filter.reshape(filter.size, 1)
		self.filtedArray *= filter
		if self.direction == 'up':
			return flipud(self.filtedArray)
		return np.array(self.filtedArray)


class EaseFade(FadeFilter):

	def __init__(self, multiplier: int = 1, direction: str = 'up'):
		super().__init__(multiplier)

	def fadeArray(self, array: array) -> array:
		super().fadeArray(array)

		size = array[0].size
		time = np.linspace(-1.0, 1.0, size)
		place = (np.array(list(map((lambda i: 1 * pow(i, 3)), time))) / 2) + 0.5
		flare = np.linspace(1, 1, size)
		middle = int(place.size * 0.8)
		for x in range(size - (middle), size):
			flare[x] = flare[x - 1] * 1.01

		# index = 0
		# for x in range(minSize-middle, minSize):
		# 	y = flare[x]
		# 	z = flare[x - 1] - (0.94 * index)
		# 	flare[x] = flare[x - 1] - (0.85 * index)
		# 	index += 0.005
		flare = flare.reshape(flare.size, 1)
		new = array * place.reshape(place.size, 1) * flare
		if self.direction == 'up':
			return flip(new)
		return new

	def ease(self, t):
		if t < 0.5:
			return 16 * t * t * t * t * t
		p = (2 * t) - 2
		return 0.5 * p * p * p * p * p + 1


class SinFade(FadeFilter):

	def __init__(self, multiplier: int = 1, direction: str = 'up'):
		super().__init__(multiplier, direction=direction)

	def fadeArray(self, array: array) -> array:
		super().fadeArray(array)
		if self.direction == 'up':
			array = flip(array)
		multiplier = FractionalPi(array[0].size)
		for x in array:
			z = multiplier.next()
			print(z)
			x *= z
			self.filtedArray.append(x)
		return np.array(self.filtedArray)
