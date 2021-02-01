from enum import Enum

from src import config
from units import heat, length, rate, time
from units._unit import Measurement


class Wind(rate.Wind):

	def __new__(cls, numerator):
		value = numerator / 1
		return Measurement.__new__(cls, value)

	def __init__(self, value):
		numerator = length.Meter(float(value))
		denominator = time.Second(1)
		n, d = config['Units']['wind'].split(',')
		super(Wind, self).__init__(numerator[n], denominator[d])

	@property
	def localized(self):
		return self


class Heat(heat.Celsius):
	pass


class Precipitation(rate.Precipitation):
	def __new__(cls, numerator):
		value = numerator / 1
		return Measurement.__new__(cls, value)

	def __init__(self, value):
		numerator = length.Millimeter(float(value))
		denominator = time.Hour(1)
		n, d = config['Units']['wind'].split(',')
		super(Precipitation, self).__init__(numerator[n], denominator[d])

	@property
	def localized(self):
		return self


class PrecipitationDaily(rate.Precipitation):
	def __new__(cls, numerator):
		value = numerator / 1
		return Measurement.__new__(cls, value)

	def __init__(self, value):
		numerator = length.Millimeter(float(value))
		denominator = time.Day(1)
		n, d = config['Units']['wind'].split(',')
		super(PrecipitationDaily, self).__init__(numerator[n], denominator[d])

	@property
	def localized(self):
		return self


class PrecipitationType(Enum):
	NONE = 0
	RAIN = 1
	HAIL = 2
