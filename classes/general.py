import logging
from datetime import datetime, timedelta
from typing import Any, Union

from config import conf as config
from units import *
from pytz import timezone

from units._unit import Unit

locale = 'us'
tz = timezone('America/New_York')


class AttributeTranslator:
	_data: dict

	def __getitem__(self, item):
		try:
			return self._data[item]
		except KeyError:
			raise ValueError

	# allow for property access to subscript keys
	__getattr__ = __getitem__


class SubAttributeTranslator(dict):
	__getattr__ = __getitem__


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
	_illuminance: str
	_precipitationRate: str
	_precipitationDaily: str
	_precipitationMonthly: str
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
	def precipitationRate(self):
		return self._precipitationRate

	@property
	def precipitationDaily(self):
		return self._precipitationDaily

	@property
	def precipitationMonthly(self):
		return self._precipitationMonthly

	@property
	def pressure(self):
		return self._pressure


class ConditionValue:
	_description: str
	_glyph: chr

	def __init__(self, data):
		self._description = data['description']
		self._glyph = data['icon']

	def __str__(self):
		return self._description

	def __repr__(self):
		return self._glyph

	@property
	def description(self):
		return self._description

	@property
	def glyph(self) -> chr:
		return self._glyph


class ConditionInterpreter:
	_library: dict[str, dict[str, str]]

	def __getitem__(self, item):
		return ConditionValue(self._library[item])


class ClimacellConditionInterpreter(ConditionInterpreter):
	_library = {
			'rain_heavy':          {'description': 'Substantial rain', 'icon': ''},
			'rain':                {'description': 'Rain', 'icon': ''},
			'rain_light':          {'description': 'Light rain', 'icon': ''},
			'freezing_rain_heavy': {'description': 'Substantial freezing rain', 'icon': ''},
			'freezing_rain':       {'description': 'Freezing rain', 'icon': ''},
			'freezing_rain_light': {'description': 'Light freezing rain', 'icon': ''},
			'freezing_drizzle':    {'description': 'Light freezing rain falling in fine pieces', 'icon': ''},
			'drizzle':             {'description': 'Light rain falling in very fine drops', 'icon': ''},
			'ice_pellets_heavy':   {'description': 'Substantial ice pellets', 'icon': ''},
			'ice_pellets':         {'description': 'Ice pellets', 'icon': ''},
			'ice_pellets_light':   {'description': 'Light ice pellets', 'icon': ''},
			'snow_heavy':          {'description': 'Substantial snow', 'icon': ''},
			'snow':                {'description': 'Snow', 'icon': ''},
			'snow_light':          {'description': 'Light snow', 'icon': ''},
			'flurries':            {'description': 'Flurries', 'icon': ''},
			'tstorm':              {'description': 'Thunderstorm conditions', 'icon': ''},
			'fog_light':           {'description': 'Light fog', 'icon': ''},
			'fog':                 {'description': 'Fog', 'icon': ''},
			'cloudy':              {'description': 'Cloudy', 'icon': ''},
			'mostly_cloudy':       {'description': 'Mostly cloudy', 'icon': ''},
			'partly_cloudy':       {'description': 'Partly cloudy', 'icon': ''},
			'mostly_clear':        {'description': 'Mostly clear', 'icon': ''},
			'clear':               {'description': 'Clear, sunny', 'icon': ''}
	}


# units = {
# 		'heat':     {'us': 'f', 'si0': 'c', 'si1': 'k'},
# 		'length':   {'us': ['in', 'ft', 'mi'], 'si': ['mm', 'm', 'km']},
# 		'time':     ['sec', 'minute', 'hour'],
# 		'pressure': {'us': 'inHg', 'si0': ['mb', 'mbar', 'hPa'], 'si1': 'mmHg'}
# }

#TODO: Move to translator
units = {'f': heat.Fahrenheit, 'c': heat.Celsius, 'in': length.Inch, 'mmHg': pressure.mmHg, 'mb': pressure.hPa, 'mi': length.Mile, 'hr': time.Hour}


class WeatherFlowUnits(AttributeTranslator):
	temperature: SubAttributeTranslator
	pressure: SubAttributeTranslator
	wind: SubAttributeTranslator
	light: SubAttributeTranslator
	precipitation: SubAttributeTranslator
	lightning: SubAttributeTranslator
	data: SubAttributeTranslator

	_temperature = {'temperature': {'type': 'heat', 'unit': 'c'},
	                'dewpoint':    {'type': 'heat', 'unit': 'c'},
	                'wetbulb':     {'type': 'heat', 'unit': 'c'},
	                'feelsLike':   {'type': 'heat', 'unit': 'c'},
	                'heatIndex':   {'type': 'heat', 'unit': 'c'},
	                'windChill':   {'type': 'heat', 'unit': 'c'},
	                'deltaT':      {'type': 'heat', 'unit': 'c'}}

	_pressure = {'pressure':   {'type': 'pressure', 'unit': 'mb'},
	             'absolute':   {'type': 'pressure', 'unit': 'mb'},
	             'seaLevel':   {'type': 'pressure', 'unit': 'mb'},
	             'airDensity': {'type': 'pressure', 'unit': 'mb'},
	             'trend':      {'type': 'str', 'unit': None}}

	_wind = {'direction': {'type': 'angle', 'unit': 'degrees'},
	         'speed':     {'type': 'speed', 'unit': ('m', 's')},
	         'lull':      {'type': 'speed', 'unit': ('m', 's')},
	         'gust':      {'type': 'speed', 'unit': ('m', 's')},
	         'interval':  {'type': 'interval', 'unit': 'second'}}

	_light = {'uvi':         {'type': 'index', 'unit': None},
	          'irradiance':  {'type': 'irradiance', 'unit': 'W/m^2'},
	          'illuminance': {'type': 'illuminance', 'unit': 'lux'}}

	_precipitation = {'type':                {'type': 'type', 'unit': 'int'},
	                  'typeYesterday':       {'type': 'type', 'unit': 'int'},
	                  'rate':                {'type': 'rate', 'unit': ('mm', 'h')},
	                  'hourly':              {'type': 'length', 'unit': 'mm'},
	                  'daily':               {'type': 'length', 'unit': 'mm'},
	                  'yesterday':           {'type': 'length', 'unit': 'mm'},
	                  'yesterdayRaw':        {'type': 'length', 'unit': 'mm'},
	                  'minutes':             {'type': 'time', 'unit': 'minute'},
	                  'minutesYesterday':    {'type': 'time', 'unit': 'minute'},
	                  'minutesYesterdayRaw': {'type': 'time', 'unit': 'minute'}}

	_lightning = {'lightning':         {'type': 'quantity', 'unit': None},
	              'lightningDistance': {'type': 'length', 'unit': 'km'},
	              'lightning1hr':      {'type': 'quantity', 'unit': None},
	              'lightning3hr':      {'type': 'quantity', 'unit': None}}

	_data: SubAttributeTranslator = {**_temperature,
	               'humidity':       {'type': 'concentration', 'unit': '%'},
	               **_pressure,
	               **_wind,
	               **_light,
	               **_precipitation,
	               **_lightning,
	               'battery':        {'type': 'power', 'unit': 'volts'},
	               'reportInterval': {'type': 'interval', 'unit': 'minutes'},
	               'time':           {'type': 'datetime', 'unit': None}}

	@property
	def temperature(self):
		return self._temperature

	@property
	def wind(self):
		return self._wind

	@property
	def pressure(self):
		return self._pressure

	@property
	def light(self):
		return self._light

	@property
	def precipitation(self):
		return self._precipitation

	@property
	def lightning(self):
		return self._lightning

	@property
	def data(self):
		return self._data

	def __getitem__(self, item):
		try:
			return self._data[item]
		except KeyError:
			raise ValueError

	def __getattr__(self, item):
		try:
			return self._data[item]['type'], self._data[item]['unit']
		except KeyError:
			raise ValueError


def __getitem__(self, item):
	try:
		return self._data[item]['type'], self._data[item]['unit']
	except KeyError:
		raise ValueError

# TODO: Deprecate this class
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


class WeatherFlowTranslator(AttributeTranslator):
	_units: AttributeTranslator = WeatherFlowUnits()

	@property
	def units(self):
		return self._units


class WeatherFlowStationTranslator(WeatherFlowTranslator):
	_light = {'uv':              'uvi',
	          'solar_radiation': 'irradiance',
	          'brightness':      'illuminance'}

	_temperature = {'air_temperature':      'temperature',
	                'dew_point':            'dewpoint',
	                'wet_bulb_temperature': 'wetbulb',
	                'feels_like':           'feelsLike',
	                'heat_index':           'heatIndex',
	                'wind_chill':           'windChill',
	                'delta_t':              'deltaT'}

	_wind = {'wind_direction':     'direction',
	         'wind_avg':           'speed',
	         'wind_lull':          'lull',
	         'wind_gust':          'gust',
	         'windSampleInterval': 'interval'}

	_precipitation = {'precip':                               'rate',
	                  'precip_accum_last_1hr':                'hourly',
	                  'precip_accum_local_day':               'daily',
	                  'precip_accum_local_yesterday_final':   'yesterday',
	                  'precip_accum_local_yesterday':         'yesterdayRaw',
	                  'precip_minutes_local_day':             'minutes',
	                  'precip_minutes_local_yesterday':       'minutesYesterdayRaw',
	                  'precip_minutes_local_yesterday_final': 'minutesYesterday',
	                  'precip_analysis_type':                 'type',
	                  'precip_analysis_type_yesterday':       'typeYesterday'}

	_pressure = {'barometric_pressure': 'pressure',
	             'station_pressure':    'absolute',
	             'sea_level_pressure':  'seaLevel',
	             'air_density':         'airDensity',
	             'pressure_trend':      'trend'}

	_lightning = {'lightning_strike_count':          'strikeCount',
	              'lightning_strike_count_last_1hr': 'lightning1hr',
	              'lightning_strike_count_last_3hr': 'lightning3hr'}

	_data: SubAttributeTranslator = {
			'timestamp':         'time',
			'timezone':          'timezone',
			**_temperature,
			'relative_humidity': 'humidity',
			**_light,
			**_pressure,
			**_wind,
			**_precipitation,
			**_lightning}

	@property
	def temperature(self):
		return self._temperature

	@property
	def wind(self):
		return self._wind

	@property
	def pressure(self):
		return self._pressure

	@property
	def lightning(self):
		return self._lightning

	@property
	def light(self):
		return self._light

	@property
	def precipitation(self):
		return self._precipitation

# TODO: Implement this class
class WeatherFlowDeviceTranslator(WeatherFlowTranslator):
	_indexToValue = {  # 0 - Epoch (Seconds UTC)
			0:  'time',
			# 1 - Wind Lull (m/s)
			1:  'lullSpeed',
			# 2 - Wind Avg (m/s)
			2:  'windSpeed',
			# 3 - Wind Gust (m/s)
			3:  'gustSpeed',
			# 4 - Wind Direction (degrees)
			4:  'windDirection',
			# 5 - Wind Sample Interval (seconds)
			5:  'windSampleInterval',
			# 6 - Pressure (MB)
			6:  'pressure',
			# 7 - Air Temperature (C)
			7:  'temperature',
			# 8 - Relative Humidity (%)
			8:  'humidity',
			# 9 - Illuminance (lux)
			9:  'illuminance',
			# 10 - UV (index)
			10: 'uvi',
			# 11 - Solar Radiation (W/m^2)
			11: 'irradiance',
			# 12 - Rain Accumulation (mm)
			12: 'precipitationHourlyRaw',
			# 13 - Precipitation Type (0 = none, 1 = rain, 2 = hail)
			13: 'precipitationType',
			# 14 - Average Strike Distance (km)
			14: 'lightningDistance',
			# 15 - Strike Count
			15: 'lightning',
			# 16 - Battery (volts)
			16: 'battery',
			# 17 - Report Interval (minutes)
			17: 'reportInterval',
			# 18 - Local Day Rain Accumulation (mm)
			18: 'precipitationDailyRaw',
			# 19 - Rain Accumulation Final (Rain Check) (mm)
			19: 'precipitationHourly',
			# 20 - Local Day Rain Accumulation Final (Rain Check) (mm)
			20: 'precipitationDaily',
			# 21 - Precipitation Aanalysis Type (0 = none, 1 = Rain Check with user display on, 2 = Rain Check with user display off)
			21: 'precipitationCheck'}

	_valueToIndex = {  # 0 - Epoch (Seconds UTC)
			'time':                   0,
			# 1 - Wind Lull (m/s)
			'lullSpeed':              1,
			# 2 - Wind Avg (m/s)
			'windSpeed':              2,
			# 3 - Wind Gust (m/s)
			'gustSpeed':              3,
			# 4 - Wind Direction (degrees)
			'windDirection':          4,
			# 5 - Wind Sample Interval (seconds)
			'windSampleInterval':     5,
			# 6 - Pressure (MB)
			'pressure':               6,
			# 7 - Air Temperature (C)
			'temperature':            7,
			# 8 - Relative Humidity (%)
			'humidity':               8,
			# 9 - Illuminance (lux)
			'illuminance':            9,
			# 10 - UV (index)
			'uvi':                    10,
			# 11 - Solar Radiation (W/m^2)
			'irradiance':             11,
			# 12 - Rain Accumulation (mm)
			'precipitationHourlyRaw': 12,
			# 13 - Precipitation Type (0 = none, 1 = rain, 2 = hail)
			'precipitationType':      13,
			# 14 - Average Strike Distance (km)
			'lightningDistance':      14,
			# 15 - Strike Count
			'lightning':              15,
			# 16 - Battery (volts)
			'battery':                16,
			# 17 - Report Interval (minutes)
			'reportInterval':         17,
			# 18 - Local Day precipitation Accumulation (mm)
			'precipitationDailyRaw':  18,
			# 19 - Rain Accumulation Final (Rain Check) (mm)
			'precipitationHourly':    19,
			# 20 - Local Day Rain Accumulation Final (Rain Check) (mm)
			'precipitationDaily':     20,
			# 21 - Precipitation Aanalysis Type (0 = none, 1 = Rain Check with user display on, 2 = Rain Check with user display off)
			'precipitationCheck':     21}

	def __getattr__(self, item):
		try:
			return self._valueToIndex[item]
		except KeyError:
			raise ValueError

	def __getitem__(self, item):
		try:
			if isinstance(item, str):
				return self._valueToIndex[item]
			elif isinstance(item, int):
				return self._indexToValue[item]
			else:
				raise ValueError
		except KeyError:
			raise ValueError

# TODO: Update to new data structure
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

	_precipitationRate = 'hourlyrainin'
	_precipitationEvent = 'eventrainin'
	_precipitationDaily = 'dailyrainin'
	_precipitationMonthly = 'monthlyrainin'
	_lastPrecipitation = 'lastRain'

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
	def precipitationEvent(self):
		return self._precipitationEvent

	@property
	def lastPrecipitation(self):
		return self._lastPrecipitation

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


class _Measurement:
	_value: Any

	def __init__(self, value: Any = None, meta: dict = None):
		self._value = value
		self._meta = meta

	def __repr__(self):
		return str(self._value)

	def __str__(self):
		return '{:.1f}'.format(float(self._localized)).rstrip('0').rstrip('.')

	def __add__(self, other):
		return self._value + other

	def __div__(self, other):
		return self._value / other

	def __eq__(self, other):
		return self._value == other

	def __abs__(self):
		return abs(self._value)

	def __floordiv__(self, other):
		return self._value // other

	def __mul__(self, other):
		return self._value * other

	def __float__(self):
		return self._value

	def __int__(self):
		return int(self._value)

	@property
	def _localized(self):
		return self._value


class Measurement(_Measurement):
	_meta: dict
	_symbol: str
	_value: Any

	@property
	def symbol(self) -> str:
		return self._symbol

	@property
	def suffix(self) -> str:
		return '{}{}'.format(self._symbol, self._meta['unit'])

	@property
	def _localized(self):
		return self._value

	@property
	def value(self):
		return self._localized

	@property
	def unit(self):
		return self._meta['unit']

	@property
	def type(self):
		return self._meta['type']

	@property
	def int(self):
		return int(round(self._value))


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


class MeasurementGroup(Measurement):
	global units
	global config

	def __init__(self, data: dict[str, Union[str, int, float]],
	             t: AttributeTranslator,
	             meta: dict[str, dict[str, str]]):
		for item in t.keys():
			name = t[item]
			if meta[name]['type'] == 'speed':
				try:
					d, time = tuple(config['Units']['wind'].split(','))
					time = units[time](1)
					distance = units[d]
					value = rate.Speed(distance(data[item]), time)
					setattr(self, '_' + name, value)
				except KeyError:
					print('what is this?')
			else:
				try:
					dataType = units[meta[name]['unit']]
				except KeyError:
					print('pass', name)
				try:
					if dataType:
						value = dataType(data[item])
					# value = dataType(data[item], meta[name])
					else:
						value = Measurement(data[item], meta[name])
					setattr(self, '_' + name, value)
				except KeyError:
					logging.warning('Unable to find key: {}'.format(item))
					pass

	@property
	def type(self):
		return self._value.type

	@property
	def unit(self):
		return self._value.unit


class Heat(Measurement):
	_symbol = 'º'
	_value = float

	@property
	def short(self):
		return '{:3d}'.format(round(self.value))

	@property
	def value(self):
		# global locale
		# if locale == 'si':
		# 	return self.celcius
		# if locale == 'us':
		# 	return self.fahrenheit
		# else:
		return float(self._value)

	def __repr__(self):
		return str(self._value)

	def __str__(self):
		return '{:.1f}'.format(self.value).rstrip('0').rstrip('.')

	@property
	def fahrenheit(self):
		if locale == 'si':
			return (float(self._value) * 1.8) + 32
		else:
			return self._value

	@property
	def celcius(self):
		if locale == 'us':
			return (float(self._value) - 32) * 1.8
		else:
			return self._value

	def __round__(self):
		return round(self._value)


class _Temperature(Measurement):
	_symbol = 'º'
	global config

	_value: Heat
	_feelsLike: Heat
	_dewpoint: Heat
	_wetbulb: Heat
	_heatIndex: Heat
	_windChill: Heat
	_deltaT: Heat

	@property
	def temperature(self):
		return self._value[config['Units']['heat']]

	@property
	def _localized(self):
		return self._value[config['Units']['heat']]

	@property
	def feelsLike(self):
		return self._feelsLike[config['Units']['heat']]

	@property
	def dewpoint(self):
		return self._dewpoint[config['Units']['heat']]

	@property
	def wetbulb(self):
		return self._wetbulb[config['Units']['heat']]

	@property
	def heatIndex(self):
		return self._heatIndex[config['Units']['heat']]

	@property
	def windChill(self):
		return self._windChill[config['Units']['heat']]

	@property
	def deltaT(self):
		return self._deltaT[config['Units']['heat']]


# class Temperature(_Temperature):
#
# 	def __init__(self, temperature: float, feelsLike: float = None, dewpoint: float = None,
# 	             wetbulb: float = None, heatIndex: float = None, windChill: float = None,
# 	             deltaT: float = None, locale: str = 'us'):
# 		super().__init__(temperature, locale)
# 		self._feelsLike = Heat(feelsLike)
# 		self._dewpoint = Heat(dewpoint)
# 		self._wetbulb = Heat(wetbulb)
# 		self._heatIndex = Heat(heatIndex)
# 		self._windChill = Heat(windChill)
# 		self._deltaT = Heat(deltaT)

# TODO: Build in localization
class Temperature(MeasurementGroup, _Temperature):
	_temperature: Heat

	def __init__(self, data: dict[str, Union[str, int, float, datetime, timezone]], t: AttributeTranslator):
		translator: dict = t.temperature
		unitMeta: dict = t.units.temperature
		super().__init__(data, translator, unitMeta)
		self._meta = t.units.temperature
		self._value = self._temperature


class Humidity(Measurement):
	_symbol = '%'

	@property
	def short(self):
		return '{:3d}'.format(round(self._value))


# TODO: Build in localization
class _Wind(Measurement):
	global config
	_unit: dict[str, str] = {'us': 'mph', 'si': 'kph'}
	_value: Vector
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

	def __repr__(self):
		return self._value

	def __str__(self):
		return str(self._value)

	@property
	def wind(self):
		return self._value[config['Units']['windRate']]

	@property
	def gust(self):
		return self._gust[config['Units']['windRate']]

	@property
	def max(self):
		return self._maxDaily

	@property
	def average2Minute(self):
		return self._average2Minute

	@property
	def average10Minute(self):
		return self._average10Minute

	@property
	def direction(self):
		return self._value.direction

	@property
	def speed(self):
		return self._value.speed[config['Units']['windRate']]


class _WindWF(Measurement):
	_unit: dict[str, str] = {'us': 'mph', 'si': 'm/s'}
	_value: Measurement
	_speed: Measurement
	_direction: Measurement
	_lull: Measurement
	_gust: Measurement

	@property
	def wind(self):
		return self._value

	@property
	def speed(self):
		return self._value

	@property
	def gust(self):
		return self._gust

	@property
	def lull(self):
		return self._lull

	@property
	def direction(self):
		return self._direction


# TODO: Build in localization
# TODO: Measurement Group
class Wind(MeasurementGroup, _WindWF):

	def __init__(self, data: dict, t):
		super().__init__(data, t.wind, t.units.wind)
		self._value = self._speed


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

	@property
	def _localized(self):
		return self._value[config['Units']['pressure']]

	@property
	def absolute(self):
		return self._value[config['Units']['pressure']]

	@property
	def relative(self):
		return self._relative[config['Units']['pressure']]

	@property
	def seaLevel(self):
		return self._seaLevel[config['Units']['pressure']]


# TODO: Build in localization
# TODO: Fix properties and sealevel
class Pressure(MeasurementGroup, _Pressure):

	def __init__(self, data: dict, t):
		super().__init__(data, t.pressure, t.units.pressure)
		self._value = self._pressure


# TODO: Build in localization
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
	def lastPrecipitation(self) -> datetime:
		return self._last

	@property
	def minutes(self):
		return self._minutes

	@property
	def minutesYesterday(self):
		if hasattr(self, '_minutesYesterday'):
			return self._minutesYesterday
		else:
			return self._miniutesYesterdayRaw


class Precipitation(MeasurementGroup, _Precipitation):

	def __init__(self, data: dict, t):
		super().__init__(data, t.precipitation, t.units.precipitation)
		self._value = self._rate


class _Lightning(Measurement):
	_strikeCount: Measurement
	_last1hr: Measurement
	_last3hr: Measurement

	# def __init__(self, strikeCount, last1hr=None, last3hr=None):
	# 	super().__init__(strikeCount)
	# 	self._last3hr = last3hr
	# 	self._last1hr = last1hr
	# 	self._strikeCount = self._value

	@property
	def last1hr(self) -> Measurement:
		return self._last1hr

	@property
	def last3hr(self) -> Measurement:
		return self._last3hr


# TODO: Measurement Group
class Lightning(_Lightning):
	def __init__(self, data: dict, t):
		for item in t.lightning.keys():
			name = t[item]
			value = data[item]
			setattr(self, '_' + name, value)
		self._value = self._strikeCount


# TODO: Build in localization
class _Light(Measurement):
	_irradiance: Measurement
	_uvi: int

	# def __init__(self, illuminance: float, uvi: int = None, irradiance: Union[int, float] = None):
	# 	super().__init__(illuminance)
	# 	self._uvi = uvi
	# 	self._irradiance = Measurement(irradiance)
	# 	self._illuminance = self._value

	@property
	def uvi(self):
		return self._uvi

	@property
	def irradiance(self):
		return self._irradiance

	@property
	def illuminance(self):
		return self._value


# TODO: Measurement Group
class Light(_Light):

	def __init__(self, data: dict, t):
		for item in t.light.keys():
			name = t[item]
			value = data[item]
			setattr(self, '_' + name, value)
		self._value = self._illuminance


class Observation(AttributeTranslator):
	timestamp: datetime
	timezone: timezone

	temperature: Temperature
	humidity: Humidity

	pressure: Pressure

	wind: Wind

	light: Light

	precipitation: Precipitation

	_translator: APITranslator

	_data: dict[str, Union[str, int, float, datetime, timezone]] = {}

	def __init__(self, data: dict[str, Union[str, int, float, datetime, timezone]],
	             translator: APITranslator,
	             tz: timezone = None):
		self._temperature = Temperature(data, translator)
		self._wind = Wind(data, translator)
		self._precipitation = Precipitation(data, translator)
		self._pressure = Pressure(data, translator)
		self._lightning = Lightning(data, translator)
		self._light = Light(data, translator)

	def localize(self, measurement, value):
		t = self._translator
		name = t[measurement]
		type, unit = t.units[name]
		if type in t.converter:
			value, unit = t.converter[type](value, unit)
		return name, value

	@property
	def precipitation(self):
		return self._precipitation

	@property
	def temperature(self):
		return self._temperature

	@property
	def wind(self):
		return self._wind

	@property
	def pressure(self):
		return self._pressure

	@property
	def light(self):
		return self._light


class WFObservation(Observation):
	lightning: Union[int, float, Lightning]
	lightning1hr: Measurement
	lightning3hr: Measurement

	# def __init__(self, data, translator: Union[APITranslator, WeatherFlowTranslator], tz: timezone = None):
	# 	for measurement in data.keys():
	# 		self._translator = translator
	# 		attrName, attrValue = self.localize(measurement, data[measurement])
	# 		self._data[attrName] = attrValue

	@property
	def lightning(self):
		return self._lightning


class AWObservation(Observation):
	_dateTime = datetime
	_temperature: Temperature
	_humidity: Humidity
	_pressure: Pressure

	def __init__(self, data, t: APITranslator):
		tz = timezone(data[t.timezone])
		self._dateTime = datetime.fromtimestamp(int(data[t.timestamp]) / 1e3, tz=tz)
		self._temperature = Temperature(data)
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


class Outdoors(AWObservation):
	_light: Light
	_wind: Wind
	_precipitation: Precipitation

	def __init__(self, data, t: APITranslator):
		super().__init__(data, t)

		def tr(x):
			return data[getattr(t, x)]

		if hasattr(t, 'irradiance') and hasattr(t, 'uvi'):
			self._light = Light(data[t.irradiance], data[t.uvi])

		wind = Vector(data[t.windSpeed], data[t.windDirection])
		gust = Vector(data[t.gustSpeed], data[t.gustDirection])
		self._wind = Wind(wind, gust, data[t.windMax])
		self._precipitation = Precipitation(data[t.precipitationRate])

	@property
	def light(self):
		return self._light

	@property
	def wind(self):
		return self._wind

	@property
	def precipitation(self):
		return self._precipitation


class WeatherStation:
	__indoor: AWObservation
	__outdoor: AWObservation


#
# def __getattr__(self, item):
# 	return self.__data[item]
#
# def __getitem__(self, item):
# 	return self._units[item]


class WeatherFlowStation(WeatherStation):
	__info = dict[str:Any]
	__currentWeather: Any
	__hourlyForecast: Any
	__dailyForecast: Any
	__translator: WeatherFlowTranslator

	def __init__(self, data):
		self.__translator = WeatherFlowTranslator()
		observationData = data['obs'][0]
		__currentWeather = Observation(observationData, self.__translator)


class AmbientWeatherStation:
	__info: dict[str:Any]

	empty = {'dateutc':        None, 'tempinf': None, 'humidityin': None, 'baromrelin': None, 'baromabsin': None,
	         'tempf':          None,
	         'winddir':        None, 'windspeedmph': None, 'windgustmph': None, 'maxdailygust': None,
	         'hourlyrainin':   None,
	         'eventrainin':    None, 'dailyrainin': None, 'weeklyrainin': None, 'monthlyrainin': None,
	         'totalrainin':    None,
	         'solarradiation': None, 'uv': None, 'feelsLike': None, 'dewPoint': None, 'feelsLikein': None,
	         'dewPointin':     None,
	         'lastRain':       None, 'tz': None, 'date': None}

	def __init__(self, params: dict, info: dict):
		self.__info = info
		self.__indoor = AWObservation(params, AmbientWeatherInterpIndoor())
		self.__outdoor = Outdoors(params, AmbientWeatherInterpOutdoor())

	@property
	def indoor(self) -> AWObservation:
		return self.__indoor

	@property
	def outdoor(self) -> AWObservation:
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
