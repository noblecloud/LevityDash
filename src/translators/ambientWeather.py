from pytz import timezone

from src import SmartDictionary
from src import config
from . import Translator, UnitTranslator


class AWUnits(UnitTranslator):
	# TODO: add support for all AmbientWeather devices https://github.com/ambient-weather/api-docs/wiki/Device-Data-Specs
	_time = SmartDictionary({'type': 'datetime', 'unit': 'ms'})
	_temperature = SmartDictionary({'temperature': {'type': 'temperature', 'unit': 'f', 'title': 'Temperature'},
	                                'dewpoint':    {'type': 'temperature', 'unit': 'f', 'title': 'Dewpoint'},
	                                'feelsLike':   {'type': 'temperature', 'unit': 'f', 'title': 'Feels Like'},
	                                'humidity':    {'type': 'humidity', 'unit': '%', 'title': 'Humidity'}})
	_pressure = SmartDictionary({'pressure': {'type': 'pressure', 'unit': 'inHg', 'title': 'Pressure'},
	                             'absolute': {'type': 'pressure', 'unit': 'inHg', 'title': 'Absolute'}})
	_wind = SmartDictionary({'direction': {'type': 'direction', 'unit': 'º', 'title': 'Direction'},
	                         'speed':     {'type': 'wind', 'unit': ('mi', 'hr'), 'title': 'Speed'},
	                         'gust':      {'type': 'wind', 'unit': ('mi', 'hr'), 'title': 'Gust'},
	                         'max':       {'type': 'wind', 'unit': ('mi', 'hr'), 'title': 'Max'}
	                         })
	_light = SmartDictionary({'uvi':        {'type': 'index', 'unit': 'int', 'title': 'UVI'},
	                          'irradiance': {'type': 'irradiance', 'unit': 'W/m^2', 'title': 'Irradiance'}})
	_precipitation = SmartDictionary({'rate':   {'type': 'precipitationRate', 'unit': ('in', 'hr'), 'title': 'Rate'},
	                                  'hourly': {'type': 'precipitationRate', 'unit': ('in', 'hr'), 'title': 'Hourly'},
	                                  'daily':  {'type': 'precipitationRate', 'unit': ('in', 'day'), 'title': 'Daily'},
	                                  # 'monthly': {'type': 'precipitation', 'unit': ('in', 'mth'), 'title': 'Monthly'},
	                                  'event':  {'type': 'length', 'unit': 'in', 'title': 'Event'},
	                                  'total':  {'type': 'length', 'unit': 'in', 'title': 'Total'},
	                                  'last':   {'type': 'date', 'unit': 'date', 'title': 'Last Rain'}
	                                  })

	def __init__(self, *args, **kwargs):
		super(AWUnits, self).__init__({
				'temperature':   self._temperature,
				'pressure':      self._pressure,
				'wind':          self._wind,
				'light':         self._light,
				'precipitation': self._precipitation,
				'time':          self._time}, *args, **kwargs)


class AWTranslator(Translator):
	# TODO: add support for all AmbientWeather devices https://github.com/ambient-weather/api-docs/wiki/Device-Data-Specs

	_units: SmartDictionary = AWUnits()
	_time = SmartDictionary({'dateutc': 'time'})
	_tz: timezone
	_dateFormatString = '%Y-%m-%dT%H:%M:%S.%fZ'
	_dateIntDivisor: int = 1000

	def __init__(self, *args, **kwargs):
		super(AWTranslator, self).__init__({'time': self._time}, *args, **kwargs)

	@property
	def units(self):
		return self._units

	@property
	def dateFormatString(self):
		return self._dateFormatString

	def tz(self):
		return config.tz


class AWTranslatorIndoor(AWTranslator):
	# Temperature
	_temperature = SmartDictionary({'tempinf':     'temperature',
	                                'dewPointin':  'dewpoint',
	                                'feelsLikein': 'feelsLike',
	                                'humidityin':  'humidity'})

	def __init__(self, *args, **kwargs):
		super(AWTranslator, self).__init__(
				{'temperature': self._temperature}, *args, **kwargs)


class AWTranslatorOutdoor(AWTranslator):
	# Temperature
	_temperature = SmartDictionary({'tempf':     'temperature',
	                                'dewPoint':  'dewpoint',
	                                'feelsLike': 'feelsLike',
	                                'humidity':  'humidity'})
	# Pressure
	_pressure = SmartDictionary({'baromrelin': 'pressure',
	                             'baromabsin': 'absolute'})

	# Outdoor Only
	# Wind
	_wind = SmartDictionary({'winddir':      'direction',
	                         'windspeedmph': 'speed',
	                         'windgustmph':  'gust',
	                         'maxdailygust': 'max'})
	# Light
	_light = SmartDictionary({'uv':             'uvi',
	                          'solarradiation': 'irradiance',
	                          'brightness':     'illuminance'})
	# Precipitation
	_precipitation = SmartDictionary({'hourlyrainin': 'rate',
	                                  'hourlyrainin': 'hourly',
	                                  'dailyrainin':  'daily',
	                                  # 'monthlyrainin': 'monthly',
	                                  'eventrainin':  'event',
	                                  'totalrainin':  'total',
	                                  'lastRain':     'last'})

	def __init__(self, *args, **kwargs):
		super(AWTranslator, self).__init__(
				{'time':          self._time,
				 'temperature':   self._temperature,
				 'light':         self._light,
				 'pressure':      self._pressure,
				 'wind':          self._wind,
				 'precipitation': self._precipitation}, *args, **kwargs)
