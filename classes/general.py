from datetime import datetime
from typing import Any, Union

from pytz import timezone


class APITranslator:
	_timestamp: str
	_temperature: str
	_dewpoint: str
	_feelsLike: str
	_humidity: str
	_windDirection: str
	_windSpeed: str
	_gustSpeed: str
	_gustDirection: str
	_uvi: str
	_irradiance: str
	_rainRate: str
	_rainDaily: str
	_rainMonthly: str
	_pressure: str

	@property
	def timestamp(self) -> str:
		return self._timestamp

	@property
	def temperature(self):
		return self._temperature

	@property
	def dewpoint(self):
		return self._dewpoint

	@property
	def feelsLike(self):
		return self._feelsLike

	@property
	def humidity(self):
		return self._humidity

	@property
	def windDirection(self):
		return self._windDirection

	@property
	def windSpeed(self):
		return self._windSpeed

	@property
	def gustSpeed(self):
		return self._gustSpeed

	@property
	def rainRate(self):
		return self._rainRate

	@property
	def rainDaily(self):
		return self._rainDaily

	@property
	def rainMonthly(self):
		return self._rainMonthly

	@property
	def pressure(self):
		return self._pressure


class AmbientWeatherInterp(APITranslator):
	# Date and Time
	_timestamp = 'dateutc'
	_timezone = 'tz'

	# Temperature
	_temperature = 'tempf'
	_dewpoint = 'dewPoint'
	_feelsLike = 'feelsLike'
	_humidity = 'humidity'

	# Pressure
	_pressure = 'baromabsin'
	_pressureRelative = 'baromrelin'

	@property
	def timezone(self):
		return self._timezone

	@property
	def pressureRelative(self):
		return self._pressureRelative


class AmbientWeatherInterpOutdoor(AmbientWeatherInterp):
	_windDirection = 'winddir'
	_windSpeed = 'windspeedmph'
	_gustSpeed = 'windgustmph'
	_gustDirection = 'winddir'
	_windMax = 'maxdailygust'

	_uvi = 'uv'
	_irradiance = 'solarradiation'

	_rainRate = 'hourlyrainin'
	_rainEvent = 'eventrainin'
	_rainDaily = 'dailyrainin'
	_rainMonthly = 'monthlyrainin'
	_lastRain = 'lastRain'

	@property
	def windMax(self):
		return self._windMax

	@property
	def gustDirection(self):
		return self._gustDirection

	@property
	def uvi(self):
		return self._uvi

	@property
	def rainEvent(self):
		return self._rainEvent

	@property
	def lastRain(self):
		return self._lastRain

	@property
	def irradiance(self):
		return self._irradiance

	@property
	def uvi(self):
		return self._uvi


class AmbientWeatherInterpIndoor(AmbientWeatherInterp):
	_temperature = 'tempinf'
	_dewpoint = 'dewPointin'
	_feelsLike = 'feelsLikein'
	_humidity = 'humidityin'


class Vector:
	_speed: Union[int, float]
	_direction: int

	def __init__(self, speed, direction):
		self._speed = speed
		self._direction = direction

	@property
	def speed(self):
		return self._speed

	@property
	def direction(self):
		return self._direction


class Measurement:
	_locale: str
	_unit: dict
	_symbol: str
	_value: Any

	def __init__(self, value: Any = None, locale: str = 'us'):
		self._locale = locale
		self._value = value

	def __repr__(self):
		return self._value

	def __str__(self):
		return '{:.2f}'.format(self._value)

	@property
	def unit(self) -> str:
		return self._unit[self._locale]

	@property
	def symbol(self) -> str:
		return self._symbol

	@property
	def suffix(self) -> str:
		return '{}{}'.format(self._symbol, self._unit)


class Temperature(Measurement):
	_unit = {'us': 'f', 'si': 'c'}
	_symbol = 'º'

	_value: float
	_feelsLike: float
	_dewpoint: float

	def __init__(self, value: float, feelsLike: float, dewpoint: float, locale: str = 'us'):
		super().__init__(value, locale)
		self._feelsLike = feelsLike
		self._dewpoint = dewpoint

	@property
	def temp(self) -> str:
		return str(self._value)

	@property
	def feelsLike(self) -> str:
		return str(self._feelsLike)

	@property
	def dewpoint(self) -> str:
		return str(self._dewpoint)


class Humidity(Measurement):
	_symbol = '%'


class Wind(Measurement):
	_unit: dict[str, str] = {'us': 'mph', 'si': 'kph'}
	_gust: Vector
	_maxDaily: Union[int, float]
	_average2Minute: Vector
	_average10Minute: Vector

	def __init__(self, wind: Vector, gust: Vector, maxDaily: Union[int, float], average2Minute: Vector = None,
	             average10Minute: Vector = None):
		super().__init__(wind)
		self._gust = gust
		self._maxDaily = maxDaily
		self._average2Minute = average2Minute
		self._average10Minute = average10Minute

	@property
	def wind(self) -> Vector:
		return self._wind

	@property
	def gust(self) -> Vector:
		return self._gust

	@property
	def average2Minute(self):
		return self._average2Minute

	@property
	def average10Minute(self):
		return self._average10Minute


class Pressure(Measurement):
	_unit = {'us': 'inHg', 'si': 'hPa'}
	_relative: Union[int, float]

	def __init__(self, absolute: Union[int, float], relative: Union[int, float] = None):
		super().__init__(absolute)
		self._relative = relative

	@property
	def absolute(self):
		return self._value

	@property
	def relative(self):
		return self._relative


class Rain(Measurement):
	_unit = {'us': 'in', 'si': 'mm'}
	_event: Union[int, float]
	_hourly: Union[int, float]
	_daily: Union[int, float]
	_monthly: Union[int, float]
	_yearly: Union[int, float]
	_last: datetime

	def __init__(self, rate, hourly=None, event=None, daily=None, monthly=None, yearly=None, last: datetime = None):
		super().__init__(rate)
		self._event = event
		self._hourly = hourly
		self._daily = daily
		self._monthly = monthly
		self._yearly = yearly
		self._last = last

	@property
	def rate(self):
		return self._value

	@property
	def event(self):
		return self._event

	@property
	def hourly(self):
		return self._hourly

	@property
	def daily(self):
		return self._daily

	@property
	def monthly(self):
		return self._monthly

	@property
	def yearly(self):
		return self._yearly

	@property
	def lastRain(self) -> datetime:
		return self._last


class Irradiance(Measurement):
	_unit = {'us': 'W/m²', 'si': 'lux'}
	_uvi: int = None

	def __init__(self, value: float, uvi: int = None):
		super().__init__(value)
		self._uvi = uvi

	@property
	def uvi(self):
		return self._uvi


class Location:
	_dateTime = datetime
	_temperature: Temperature
	_humidity: Humidity
	_pressure: Pressure

	def __init__(self, data, t: APITranslator):
		tz = timezone(data[t.timezone])
		self._dateTime = datetime.fromtimestamp(int(data[t.timestamp]) / 1e3, tz=tz)
		self._temperature = Temperature(data[t.temperature], data[t.feelsLike], data[t.dewpoint])
		self._humidity = Humidity(data[t.humidity])
		if hasattr(t, 'pressureRelative'):
			self._pressureRelative = Pressure(data[t.pressure], data[t.pressureRelative])
		else:
			self._pressure = Pressure(data[t.pressure])

	@property
	def datetime(self):
		return self._dateTime

	@property
	def temperature(self):
		return self._temperature

	@property
	def humidity(self):
		return self._humidity

	@property
	def pressure(self):
		return self._pressure


class Outdoors(Location):
	_irradiance: Irradiance
	_wind: Wind
	_rain: Rain

	def __init__(self, data, t: APITranslator):
		super().__init__(data, t)

		def tr(x):
			return data[getattr(t, x)]

		if hasattr(t, 'irradiance') and hasattr(t, 'uvi'):
			self._irradiance = Irradiance(data[t.irradiance], data[t.uvi])

		wind = Vector(data[t.windSpeed], data[t.windDirection])
		gust = Vector(data[t.gustSpeed], data[t.gustDirection])
		self._wind = Wind(wind, gust, data[t.windMax])
		self._rain = Rain(data[t.rainRate])

	@property
	def irradiance(self):
		return self._irradiance

	@property
	def wind(self):
		return self._wind

	@property
	def rain(self):
		return self._rain


class WeatherStation:
	__indoor: Location
	__outdoor: Location


class AmbientWeatherStation:
	__info: dict[str:Any]

	def __init__(self, params: dict, info: dict):
		self.__info = info
		self.__indoor = Location(params, AmbientWeatherInterpIndoor())
		self.__outdoor = Outdoors(params, AmbientWeatherInterpOutdoor())

	@property
	def indoor(self) -> Location:
		return self.__indoor

	@property
	def outdoor(self) -> Location:
		return self.__outdoor

	@property
	def coordinates(self) -> tuple[float, float]:
		return self.__info['coords']['coords']['lat'], self.__info['coords']['coords']['lon']

	@property
	def type(self) -> str:
		return self.__info['location']

	@property
	def address(self) -> str:
	    return self.__info['coords']['address']

	@property
	def elevation(self) -> float:
	    return self.__info['coords']['elevation']

	@property
	def city(self) -> str:
	    return self.__info['coords']['location']

	@property
	def name(self) -> str:
	    return self.__info['name']
