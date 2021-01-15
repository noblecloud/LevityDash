from datetime import datetime, timedelta
from typing import Any
from src import config as conf


class _Measurement:

	pass


class Measurement(_Measurement):
	_meta: dict
	_symbol: str

	@property
	def symbol(self) -> str:
		return self._symbol

	@property
	def suffix(self) -> str:
		return '{}{}'.format(self._symbol, self._meta['unit'])


class Vector:
	_speed: Measurement
	_direction: int

	def __init__(self, speed, direction):
		self._speed = speed
		self._direction = direction

	def __str__(self):
		return '{:.1f}'.format(self._speed)

	def __repr__(self):
		return '{:.1f}'.format(self._speed)

	@property
	def speed(self):
		return self._speed

	@property
	def direction(self):
		return self._direction


class _Temperature:
	_symbol = 'º'

	value: object
	feelsLike: object
	dewpoint: object
	wetbulb: object
	heatIndex: object
	windChill: object
	deltaT: object

	def __getitem__(self, item):
		return self[item][config['Units']['heat']]

	# @property
	# def temperature(self):
	# 	return self[config['Units']['heat']]
	#
	# @property
	# def _localized(self):
	# 	return self[config['Units']['heat']]
	#
	# @property
	# def feelsLike(self):
	# 	return self._feelsLike[config['Units']['heat']]
	#
	# @property
	# def dewpoint(self):
	# 	return self._dewpoint[config['Units']['heat']]
	#
	# @property
	# def wetbulb(self):
	# 	return self._wetbulb[config['Units']['heat']]
	#
	# @property
	# def heatIndex(self):
	# 	return self._heatIndex[config['Units']['heat']]
	#
	# @property
	# def windChill(self):
	# 	return self._windChill[config['Units']['heat']]

	# @property
	# def deltaT(self):
	# 	return self._deltaT[config['Units']['heat']]


class _Wind(Measurement):
	global config
	_unit: dict[str, str] = {'us': 'mph', 'si': 'kph'}
	_gust: Vector
	_maxDaily: Measurement
	_average2Minute: Vector
	_average10Minute: Vector

	# def __init__(self, wind: Vector, gust: Vector, maxDaily: Union[int, float], average2Minute: Vector = None,
	#              average10Minute: Vector = None):
	# 	super().__init__(wind)
	# 	self._gust = gust
	# 	self._maxDaily = maxDaily
	# 	self._average2Minute = average2Minute
	# 	self._average10Minute = average10Minute

	# def __repr__(self):
	# 	return self
	#
	# def __str__(self):
	# 	return str(self)
	#
	# @property
	# def wind(self):
	# 	return self[config['Units']['windRate']]
	#
	# @property
	# def gust(self):
	# 	return self._gust[config['Units']['windRate']]
	#
	# @property
	# def max(self):
	# 	return self._maxDaily
	#
	# @property
	# def average2Minute(self):
	# 	return self._average2Minute
	#
	# @property
	# def average10Minute(self):
	# 	return self._average10Minute
	#
	# @property
	# def direction(self):
	# 	return self.direction


class _WindWF(Measurement):
	_unit: dict[str, str] = {'us': 'mph', 'si': 'm/s'}
	_speed: Measurement
	_direction: Measurement
	_lull: Measurement
	_gust: Measurement

	# @property
	# def wind(self):
	# 	return self
	#
	# @property
	# def speed(self):
	# 	return self
	#
	# @property
	# def gust(self):
	# 	return self._gust
	#
	# @property
	# def lull(self):
	# 	return self._lull
	#
	# @property
	# def direction(self):
	# 	return self._direction


class _Pressure(_Measurement):
	_unit = {'us': 'inHg', 'si': 'mb'}
	_relative: Measurement
	_seaLevel: Measurement
	_pressure: Measurement
	_trend: Measurement

	# 	def __init__(self, absolute: Union[int, float],
	# 	             relative: Union[int, float] = None,
	# 	             seaLevel: Union[int, float] = None):
	# 		super().__init__(absolute)
	# 		self._relative = relative
	# 		self._seaLevel = seaLevel

	# @property
	# def _localized(self):
	# 	return self[config['Units']['pressure']]
	#
	# @property
	# def absolute(self):
	# 	return self[config['Units']['pressure']]
	#
	# @property
	# def relative(self):
	# 	return self._relative[config['Units']['pressure']]
	#
	# @property
	# def seaLevel(self):
	# 	return self._seaLevel[config['Units']['pressure']]


class _Precipitation(Measurement):
	_symbol = ''
	_unit = {'us': 'in', 'si': 'mm'}
	_rate: Measurement
	_event: Measurement
	_hourly: Measurement
	_daily: Measurement
	_monthly: Measurement
	_yearly: Measurement
	_last: datetime
	_miniutes: timedelta
	_miniutesRaw: timedelta
	_miniutesYesterday: timedelta
	_miniutesYesterdayRaw: timedelta

	# def __init__(self, rate, hourly=None, event=None, daily=None, monthly=None, yearly=None, last: datetime = None, minutes=None, minutesYesterday=None):
	# 	super().__init__(rate)
	# 	self._event = event
	# 	self._hourly = hourly
	# 	self._daily = daily
	# 	self._monthly = monthly
	# 	self._yearly = yearly
	# 	self._last = last
	# 	self._minutesYesterday = minutesYesterday
	# 	self._minutes = minutes

	# @property
	# def rate(self):
	# 	return self
	#
	# @property
	# def event(self):
	# 	return self._event
	#
	# @property
	# def hourly(self):
	# 	return self._hourly
	#
	# @property
	# def daily(self):
	# 	return self._daily
	#
	# @property
	# def monthly(self):
	# 	return self._monthly
	#
	# @property
	# def yearly(self):
	# 	return self._yearly
	#
	# @property
	# def lastPrecipitation(self) -> datetime:
	# 	return self._last
	#
	# @property
	# def minutes(self):
	# 	return self._minutes
	#
	# @property
	# def minutesYesterday(self):
	# 	if hasattr(self, '_minutesYesterday'):
	# 		return self._minutesYesterday
	# 	else:
	# 		return self._miniutesYesterdayRaw


class _Lightning(Measurement):
	_strikeCount: Measurement
	_last1hr: Measurement
	_last3hr: Measurement

	# def __init__(self, strikeCount, last1hr=None, last3hr=None):
	# 	super().__init__(strikeCount)
	# 	self._last3hr = last3hr
	# 	self._last1hr = last1hr
	# 	self._strikeCount = self

	# @property
	# def last1hr(self) -> Measurement:
	# 	return self._last1hr
	#
	# @property
	# def last3hr(self) -> Measurement:
	# 	return self._last3hr


class _Light(Measurement):
	_irradiance: Measurement
	_uvi: int

	# def __init__(self, illuminance: float, uvi: int = None, irradiance: Union[int, float] = None):
	# 	super().__init__(illuminance)
	# 	self._uvi = uvi
	# 	self._irradiance = Measurement(irradiance)
	# 	self._illuminance = self

	# @property
	# def uvi(self):
	# 	return self._uvi
	#
	# @property
	# def irradiance(self):
	# 	return self._irradiance
	#
	# @property
	# def illuminance(self):
	# 	return self
