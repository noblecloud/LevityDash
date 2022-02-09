from src import logging
from datetime import datetime
from functools import cached_property

from WeatherUnits.base import DerivedMeasurement, Measurement

from src.catagories import CategoryDict, CategoryItem, UnitMetaData, ValueNotFound, ValueWrapper
from src.utils import clearCacheAttr, ISOduration, levenshtein
from .units import unitDict

log = logging.getLogger(__name__)


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
		'tstorm':                {'description': 'Thunderstorm conditions', 'icon': ''},
		'fog_light':             {'description': 'Light fog', 'icon': ''},
		'fog':                   {'description': 'Fog', 'icon': ''},
		'cloudy':                {'description': 'Cloudy', 'icon': ''},
		'mostly_cloudy':         {'description': 'Mostly cloudy', 'icon': ''},
		'partly_cloudy':         {'description': 'Partly cloudy', 'icon': ''},
		'mostly_clear':          {'description': 'Mostly clear', 'icon': ''},
		'clear':                 {'description': 'Clear, sunny', 'icon': ''}
	}


class Translator(CategoryDict):
	units = unitDict

	def __init__(self, source: dict, observation: dict, category: str = None):
		self._observation = observation
		super(Translator, self).__init__(None, source, category)
		# print(self._dict)
		toConvert = [key for key, value in self._source.items() if isinstance(value, dict)]
		for key in toConvert:
			self._source[key] = UnitMetaData(key, self)

	def getExact(self, key: str):
		return self._source.get(key, None)

	def sourceKeyLookup(self, key: str) -> UnitMetaData:
		sourceKey = self._sourceKeys.get(key, None)

		if sourceKey is None:
			if key in self.subKeys():
				value = self[key], key
			else:
				## This originally searched for the closest match, but that was too slow and inaccurate
				## Instead, the key is ignored
				raise ValueNotFound(f'{key} not found')
				k = key
				key = self._sourceKeys[min([(levenshtein(key, i), i) for i in (list(self._sourceKeys.keys()))])[1]]
				value = self[key], '.'.join(key.split('.')[:-1] + [k])
				log.warning(f'{k} not found in using best match {value[1]}')
		else:
			sourceKey = CategoryItem(sourceKey)
			value = self._source[sourceKey], sourceKey
		if not isinstance(value[0], UnitMetaData):
			raise ValueNotFound(key)
		if not isinstance(value[1], CategoryItem):
			value = value[0], CategoryItem(value[1])
		return value

	@cached_property
	def _sourceKeys(self):
		sourceKeys = {}
		for k, v in self._source.items():
			if isinstance(v, dict):
				sourceKey = v.get('sourceKey', None)
				if isinstance(sourceKey, (tuple, list)):
					for i in sourceKey:
						sourceKeys[i] = k
				else:
					sourceKeys[sourceKey] = k
		return sourceKeys

	def translate(self, raw: dict, localize: bool = True, time: datetime = None):
		clearCacheAttr(self, '_sourceKeys')
		result = {}
		for key, value in raw.items():
			try:
				key, value = self.convert(key, value, localize=localize, time=time)
			except ValueError:
				continue
			except ValueNotFound:
				log.warning(f'{key} not found')
				continue

			result[CategoryItem(key)] = value
		return result

	def convert(self, key, value, localize: bool = True, time: datetime = None):

		measurementData, key = self.sourceKeyLookup(key)

		unitDefinition = measurementData['sourceUnit']
		typeString = measurementData['type']
		title = measurementData['title']
		if isinstance(unitDefinition, list):
			n, d = [self.units[cls] for cls in unitDefinition]
			comboCls: DerivedMeasurement = self.units['special'][typeString]
			measurement = comboCls(n(value), d(1), timestamp=time)
		elif unitDefinition == '*':
			specialCls = self.units['special'][typeString]
			kwargs = {'title': title, 'key': key, 'timestamp': self._time} if issubclass(specialCls, Measurement) else {}
			measurement = specialCls(value, **kwargs)
		elif typeString in ['date', 'datetime']:
			if isinstance(value, datetime):
				measurement = value
			else:
				if unitDefinition == 'epoch':
					try:
						measurement = datetime.fromtimestamp(value)
					except ValueError:
						measurement = datetime.fromtimestamp(value / 1000)
				elif unitDefinition == 'ISO8601':
					measurement = datetime.strptime(value, measurementData['format'])
				else:
					measurement = datetime.now()
					log.warning(f'Unable to convert date value "{value}" defaulting to current time')
		elif typeString == 'timedelta':
			if unitDefinition == 'epoch':
				measurement = self.units['s'](value)
			elif unitDefinition == 'ISO8601':
				measurement = ISOduration(value)
		elif unitDefinition is None:
			raise ValueError(f'Value Ignored: {key}')
		else:
			cls = self.units[unitDefinition]
			if isinstance(cls, type) and issubclass(cls, Measurement):
				measurement = cls(value, timestamp=time)
			else:
				measurement = cls(value)

		if isinstance(measurement, Measurement) and localize:
			sourceValue = measurement
			others = {'sourceValue': measurement}
			measurement = measurement.localize
		else:
			others = {}

		# get existing value
		# existing = self._observation.get(key, None)
		# if existing is not None:
		# 	existing.update(measurement, timestamp=time)
		# else:
		# 	measurement = ValueWrapper(value=measurement, key=key, metaData=measurementData, timestamp=time, source=self._observation)
		return key, {'value': measurement, 'timestamp': time, **others, **measurementData}
