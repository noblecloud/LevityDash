from collections.abc import Iterable
from typing import Callable, Hashable, Set, Union

from src import config, logging
from datetime import datetime
from functools import cached_property, lru_cache

from WeatherUnits.base import DerivedMeasurement, Measurement

from src.catagories import CategoryDict, CategoryItem, UnitMetaData, ValueNotFound
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
		'tstorm':              {'description': 'Thunderstorm conditions', 'icon': ''},
		'fog_light':           {'description': 'Light fog', 'icon': ''},
		'fog':                 {'description': 'Fog', 'icon': ''},
		'cloudy':              {'description': 'Cloudy', 'icon': ''},
		'mostly_cloudy':       {'description': 'Mostly cloudy', 'icon': ''},
		'partly_cloudy':       {'description': 'Partly cloudy', 'icon': ''},
		'mostly_clear':        {'description': 'Mostly clear', 'icon': ''},
		'clear':               {'description': 'Clear, sunny', 'icon': ''}
	}


def convert(source, data):
	measurementData = data
	# unit = measurementData['unit']
	# if isinstance(unit, str) and '@' in unit:
	# 	unit = lambda: getattr(source, unit)
	# if "@" in measurementData['unit']
	unitDefinition = measurementData['sourceUnit']
	# typeString = measurementData['type']
	# if isinstance(unitDefinition, list):
	# 	n, d = [units[cls] for cls in unitDefinition]
	# 	comboCls: DerivedMeasurement = self.units['special'][typeString]
	# 	measurement = comboCls(n(value), d(1), timestamp=source.time)
	# elif unitDefinition == '*':
	# 	specialCls = units['special'][typeString]
	# 	kwargs = {'timestamp': self._time} if issubclass(specialCls, Measurement) else {}
	# 	measurement = specialCls(value, **kwargs)
	# elif typeString in ['date', 'datetime']:
	# 	if isinstance(value, datetime):
	# 		measurement = value
	# 	else:
	# 		if unitDefinition == 'epoch':
	# 			try:
	# 				measurement = datetime.fromtimestamp(value)
	# 			except ValueError:
	# 				measurement = datetime.fromtimestamp(value / 1000)
	# 		elif unitDefinition == 'ISO8601':
	# 			measurement = datetime.strptime(value, measurementData['format'])
	# 		else:
	# 			measurement = datetime.now()
	# 			log.warning(f'Unable to convert date value "{value}" defaulting to current time')
	if typeString == 'timedelta':
		if unitDefinition == 'epoch':
			measurement = self.units['s'](value)
		elif unitDefinition == 'ISO8601':
			measurement = ISOduration(value)
	elif unitDefinition is None:
		raise ValueError(f'Value Ignored: {key}')
	else:
		cls = units[unitDefinition]
		if isinstance(cls, type) and issubclass(cls, Measurement):
			measurement = cls(value, timestamp=time)
		else:
			measurement = cls(value)

	if isinstance(measurement, Measurement) and localize:
		others = {'sourceValue': measurement, 'sourceValueRaw': value}
		measurement = measurement.localize
	else:
		others = {'sourceValue': value}


def propertyGetter(source: 'ObservationDict', data: dict):
	"""
		Returns a property getter that will return the value of the data
		key in the source dictionary.
		Order of preference:
			1. source[data['key']]
			2. source.get(data['attr'])
			3. data['default']
	"""

	def getter():
		if 'key' in data and data['key'] in source:
			return source[data['key']]
		elif 'attr' in data and hasattr(source, data['attr']):
			return getattr(source, data['attr'])
		else:
			unitCls = data['default'].get('unit', None)
			if unitCls is not None:
				value = data['default']['value']
				return unitCls(value)
			return data['default']

	return getter


#
# def conversionGetter(data: UnitMetaData):
#
#
#
# 	unit = data['unit']
# 	typeString = data.get('type', None)
# 	if typeString in ['date', 'datetime']:
# 		if isinstance(value, datetime):
# 			measurement = value
# 		else:
# 			if unitDefinition == 'epoch':
# 				try:
# 					measurement = datetime.fromtimestamp(value)
# 				except ValueError:
# 					measurement = datetime.fromtimestamp(value / 1000)
# 			elif unitDefinition == 'ISO8601':
# 				measurement = datetime.strptime(value, measurementData['format'])
# 			else:
# 				measurement = datetime.now()
# 				log.warning(f'Unable to convert date value "{value}" defaulting to current time'):


class Properties(dict):

	def __init__(self, source):
		keys = [key for key in source.keys() if str(key).startswith('@')]
		for key in keys:
			self[key.strip('@')] = source.pop(key)
		super().__init__()

	def __setitem__(self, key, value):
		key = key.strip('@')
		super().__setitem__(key, value)

	def __getitem__(self, key):
		key = key.strip('@')
		return super().__getitem__(key)

	def get(self, key, default=None):
		key = key.strip('@')
		return super().get(key, default)

	def __contains__(self, key):
		key = key.strip('@')
		return super().__contains__(key)


class Translator(CategoryDict):
	__translators__ = {}
	units = unitDict
	_ignored: set[str]

	@classmethod
	def getFromAll(cls, key: str, default=None):
		result = {n: t.getExact(key) for n, t in cls.__translators__.items() if key in t}
		return result

	def __init__(self, api: 'API', source: dict, category: str = None, ignored: Iterable[str] = None, **kwargs):
		self._ignored = set(source.pop('ignored', []))
		category = ''
		self.properties = Properties(source)
		self.keyMaps = source.pop('keyMaps', {})
		self.dataMaps = source.pop('dataMaps', {})
		self.calculations = source.pop('calculations', {})
		self.aliases = source.pop('aliases', {})
		super(Translator, self).__init__(None, source, category)
		if ignored is not None:
			self._ignored.update(ignored)
		self._api = api
		toConvert = [key for key, value in self._source.items() if isinstance(value, dict)]
		for key in toConvert:
			self._source[key] = UnitMetaData(key, self)
		self.__translators__[api.name] = self
		self.__hash = hash((api, frozenset(self.keys())))

	def propertySetters(self):
		return {key: value for key, value in self._source.items() if 'property' in value.keys() or 'setter' in value.keys()}

	def getExact(self, key: str):
		if not isinstance(key, CategoryItem):
			key = CategoryItem(key)
		foundKey = self._source.get(key, None) or self._source.get(key.anonymous, None)
		if foundKey is None:
			wildcardKeys = [k for k in self._source.keys() if k.hasWildcard and k == key]
			if len(wildcardKeys) == 1:
				foundKey = self._source[wildcardKeys[0]]
			elif len(wildcardKeys) > 1:
				raise ValueError(f'Multiple keys match "{key}"')
			else:
				raise KeyError(f'No key found for "{key}"')
		return foundKey

	def __hash__(self):
		return self.__hash

	def getKeyMap(self, source: Union[str, Iterable[str]]):
		if isinstance(source, str):
			source = [source]
		mappings = [s for s in source if isinstance(s, Hashable) and s in self.keyMaps]
		if len(mappings) == 1:
			return self.keyMaps[mappings[0]]
		elif len(mappings) > 1:
			return self.keyMaps[mappings[-1]]
		else:
			raise KeyError(f'No key map found for "{source}"')

	@lru_cache(maxsize=128)
	def getUnitMetaData(self, key: str, source) -> UnitMetaData:
		sourceKey = self._sourceKeys.get(key, None) or self.getExact(key)
		if isinstance(sourceKey, CategoryItem):
			value = self.getExact(sourceKey)
		elif isinstance(sourceKey, UnitMetaData):
			value = sourceKey
		elif sourceKey is None:
			keys = [k for k in self._source.keys() if k == key]
			## This originally searched for the closest match, but that was too slow and inaccurate
			## Instead, the key is ignored
			raise ValueNotFound(f'{key} not found')
			key = self._sourceKeys[min([(levenshtein(key, i), i) for i in (list(self._sourceKeys.keys()))])[1]]
			value = self[key], '.'.join(key.split('.')[:-1] + [k])
			log.warning(f'{k} not found in using best match {value[1]}')
		else:
			raise ValueNotFound(f'{key} not found, this should never happen...')
		value = dict(value)
		if not isinstance(value['sourceKey'], (str, CategoryItem)):
			value['sourceKey'] = str(key)
		return value

	def mapData(self, source: dict, data: dict, requiredKeys: Set[str] = None):
		newData = {}
		try:
			keyMap = self.getKeyMap(data.values())
			newData['keyMap'] = keyMap
		except KeyError:
			pass
		for mapName, maps in self.dataMaps.items():
			subData = data
			for subMap in maps:
				subMap = subMap.split('>')
				for key in subMap:
					if key in subData:
						subData = subData[key]
					elif key.isdigit() and len(subData) == 1:
						try:
							subData = subData[int(key)]
						except (IndexError, TypeError):
							break
					else:
						break
				else:
					newData[mapName] = subData
					break
		for key in data:
			if key in self.properties:
				newData[key] = data[key]
		data = self.__mapData(source, '.', newData)
		return data

	def __mapData(self, source: dict, key: str, data: dict):
		if key in self._ignored:
			pass
		if key in self.keyMaps:
			key = self.keyMaps[key]
		if isinstance(data, dict):
			return {k: self.__mapData(source, k, v) for k, v in data.items() if k not in self._ignored}
		elif isinstance(data, (tuple, list)):
			if key in self.keyMaps:
				return data
			return data
		else:
			if key in self.properties:
				prop = self.properties[key]
				if 'setter' in prop:
					setterDest = prop['setter'].strip('@').split('.')
					dest = self
					while setterDest:
						var = setterDest.pop(0)
						if hasattr(dest, var):
							dest = getattr(dest, var)
						elif var == 'source':
							dest = source
						if len(setterDest) == 0:
							setattr(dest, prop['attr'], data)

			return data

	def findKey(self, key: str, data: dict):
		metaData = self.getExact(key)
		sourceKey = metaData['sourceKey']
		if isinstance(sourceKey, str):
			return sourceKey
		elif isinstance(sourceKey, CategoryItem):
			return sourceKey
		elif isinstance(sourceKey, Iterable):
			sourceKey = set(sourceKey).intersection(set(data.keys()))
			return sourceKey.pop()
		else:
			raise ValueNotFound(f'{key} not found')

	@property
	def api(self):
		return self._api

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

	def translate(self, source: 'ObservationDict', raw: dict, localize: bool = True, time: datetime = None):
		clearCacheAttr(self, '_sourceKeys')
		result = {}
		for key, value in raw.items():
			if key in self._ignored:
				log.debug(f'Ignoring {key}')
				continue
			try:
				value = self.convert(source, key, value, localize=localize, time=time)
			except ValueError:
				continue
			except ValueNotFound:
				log.warning(f'{key} not found')
				continue
			result[value['key']] = value
		return result

	def convertIter(self, values: list, cls, localize: bool = True, **kwargs):
		return [cls(value) for value in values]

	def convertComboIter(self, values: list, cls, n, d, localize: bool = True):
		return [cls(n(value), d(1)) for value in values]

	def convertNonLocalizableIter(self, values: list, cls):
		return [cls(value) for value in values]

	def convertDateTimeIter(self, values: list, unitDefinition, measurementData):
		kwargs = {'tz': config.tz}
		if isinstance(values[0], datetime):
			return values
		if isinstance(values[0], (float, int)) and abs(values[0]) <= 0xffffffff:
			v = values[0]
			reduction = 1
			while v/reduction > 0xffffffff:
				reduction *= 10
			values = (v/reduction for v in values)
		if unitDefinition == 'epoch':
			cls = datetime.fromtimestamp
		elif unitDefinition == 'ISO8601':
			cls = datetime.strptime
			kwargs['format'] = measurementData['format']
		return [cls(v, **kwargs) for v in values]

	def getUnit(self, key: str):
		# if '@' in key:
		return self.getUnitMetaData(self, key)[0]

	def convert(self, source, key, value, localize: bool = True, time: datetime = None):
		measurementData = self.getUnitMetaData(source, key)
		# unit = measurementData['unit']
		# if isinstance(unit, str) and '@' in unit:
		# 	unit = lambda: getattr(source, unit)
		# if "@" in measurementData['unit']
		return {'value': value, **measurementData}
		unitDefinition = measurementData['sourceUnit']
		typeString = measurementData['type']
		# if isinstance(unitDefinition, list):
		# 	n, d = [self.units[cls] for cls in unitDefinition]
		# 	comboCls: DerivedMeasurement = self.units['special'][typeString]
		# 	measurement = comboCls(n(value), d(1), timestamp=time)
		# elif unitDefinition == '*':
		# 	specialCls = self.units['special'][typeString]
		# 	kwargs = {'timestamp': self._time} if issubclass(specialCls, Measurement) else {}
		# 	measurement = specialCls(value, **kwargs)
		# elif typeString in ['date', 'datetime']:
		# 	if isinstance(value, datetime):
		# 		measurement = value
		# 	else:
		# 		if unitDefinition == 'epoch':
		# 			try:
		# 				measurement = datetime.fromtimestamp(value)
		# 			except ValueError:
		# 				measurement = datetime.fromtimestamp(value / 1000)
		# 		elif unitDefinition == 'ISO8601':
		# 			measurement = datetime.strptime(value, measurementData['format'])
		# 		else:
		# 			measurement = datetime.now()
		# 			log.warning(f'Unable to convert date value "{value}" defaulting to current time')
		# elif typeString == 'timedelta':
		# 	if unitDefinition == 'epoch':
		# 		measurement = self.units['s'](value)
		# 	elif unitDefinition == 'ISO8601':
		# 		measurement = ISOduration(value)
		# elif unitDefinition is None:
		# 	raise ValueError(f'Value Ignored: {key}')
		# else:
		# 	cls = self.units[unitDefinition]
		# 	if isinstance(cls, type) and issubclass(cls, Measurement):
		# 		measurement = cls(value, timestamp=time)
		# 	else:
		# 		measurement = cls(value)
		#
		# if isinstance(measurement, Measurement) and localize:
		# 	others = {'sourceValue': measurement, 'sourceValueRaw': value}
		# 	measurement = measurement.localize
		# else:
		# 	others = {'sourceValue': value}

		# get existing value
		# existing = self._observation.get(key, None)
		# if existing is not None:
		# 	existing.update(measurement, timestamp=time)
		# else:
		# 	measurement = ValueWrapper(value=measurement, key=key, metaData=measurementData, timestamp=time, source=self._observation)
		return {'value': measurement, 'timestamp': time, **others, **measurementData}

	def convertFunction(self, key) -> Callable:
		measurementData = self.getUnitMetaData(key)

		"""Returns the function needed to convert a value for a given key"""

	def convertList(self, key, value, localize: bool = True):
		measurementData, key = self.getUnitMetaData(key)

		unitDefinition = measurementData['sourceUnit']
		typeString = measurementData['type']
		if isinstance(unitDefinition, list):
			n, d = [self.units[cls] for cls in unitDefinition]
			comboCls: DerivedMeasurement = self.units['special'][typeString]
			measurement = self.convertComboIter(value, comboCls, n, d, localize=localize)
		elif unitDefinition == '*':
			specialCls = self.units['special'][typeString]
			measurement = self.convertIter(value, specialCls, localize=localize)
		elif typeString in ['date', 'datetime']:
			measurement = self.convertDateTimeIter(value, unitDefinition, measurementData)
		elif typeString == 'timedelta':
			if unitDefinition == 'epoch':
				cls = self.units['s']
			elif unitDefinition == 'ISO8601':
				cls = ISOduration
			measurement = self.convertNonLocalizableIter(value, cls)
		elif unitDefinition is None:
			raise ValueError(f'Value Ignored: {key}')
		else:
			cls = self.units[unitDefinition]
			if isinstance(cls, type) and issubclass(cls, Measurement):
				measurement = self.convertIter(value, cls, localize=localize)
			else:
				measurement = self.convertNonLocalizableIter(value, cls)
		return key, measurement

	def __parseDateTime(self, measurementData, unitDefinition, value):
		if isinstance(value, datetime):
			return value
		else:
			if unitDefinition == 'epoch':
				if abs(value) <= 0xffffffff:
					value /= 1000
				cls = datetime.fromtimestamp
			elif unitDefinition == 'ISO8601':
				cls = datetime.strptime
				kwargs = {'format': measurementData['format']}
			else:
				raise ValueError(f'Unknown date format: {unitDefinition}')
		return cls(value, **kwargs)
