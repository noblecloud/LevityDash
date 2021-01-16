from datetime import datetime

from src import config, SmartDictionary
from units import heat, length, others, pressure, time


class UnitTranslator(SmartDictionary):

	# _groups = {'temperature':   Temperature,
	#            'light':         Light,
	#            'precipitation': Precipitation,
	#            'pressure':      Pressure,
	#            'wind':          Wind,
	#            'lightning':     Lightning}

	_groups: SmartDictionary

	@property
	def classes(self):
		return self._classes

	@property
	def groups(self):
		return SmartDictionary(self._groups)


class Translator(SmartDictionary):
	_units: SmartDictionary
	_dateFormatString: str

	def __init__(self, *args, **kwargs):
		super(Translator, self).__init__(*args, **kwargs)
		_dateIntDivisor: int = 1
		_classes = SmartDictionary({
				'f':        heat.Fahrenheit,
				'c':        heat.Celsius,
				'%':        others.Humidity,
				'º':        int,
				'str':      str,
				'int':      int,
				'mmHg':     pressure.mmHg,
				'inHg':     pressure.inHg,
				'W/m^2':    others.Irradiance,
				'lux':      others.Illuminance,
				'mb':       pressure.hPa,
				'in':       length.Inch,
				'mi':       length.Mile,
				'mm':       length.Millimeter,
				'm':        length.Meter,
				'km':       length.Kilometer,
				'hr':       time.Hour,
				'min':      time.Minute,
				's':        time.Second,
				'date':     datetime,
				'timezone': str
		})

	# def __getitem__(self, item):
	# 	fetched = SmartDictionary(super(Translator, self).__getitem__(item), self._units[item])
	# 	try:
	# 		fetched['units'] = self._units[item]
	# 	except AttributeError:
	# 		logging.debug('Unable to get unit table for {}'.format(self.__class__.__name__))

	@property
	def units(self):
		return self._units


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
