from collections import ChainMap
from datetime import datetime
from difflib import get_close_matches
from enum import Enum
from functools import cached_property, lru_cache
from typing import Dict, Hashable, Iterable, Optional, Set, Union, Sized, List

from dateutil import parser as DateParser
from rich.pretty import pretty_repr

from LevityDash.lib.plugins.utils import unitDict
from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.utils.shared import clearCacheAttr, now, Unset
from LevityDash.lib.plugins.categories import CategoryDict, CategoryItem, UnitMetaData, ValueNotFound
from LevityDash.lib.plugins.errors import InvalidData

log = LevityPluginLog.getChild('Schema')


class SchemaSpecialKeys(str, Enum):
	sourceData = "{{sourceData}}"
	metaData = "{{metaData}}"


tsk = SchemaSpecialKeys


class DotStorage(dict):
	"""
		A class that can be used to store values in a dictionary.
		This is useful for storing values in a dictionary that are
		not otherwise accessible.
	"""

	# TODO: This could probably be changed to a SimpleNamespace

	def __getattr__(self, item):
		return self[item]

	def __setattr__(self, key, value):
		if isinstance(value, dict):
			value = DotStorage(value)
		self[key] = value


class LevityDatagram(dict):
	sourceData: dict
	metaData: dict

	def __init__(self, data: dict, schema: 'Schema' = None, **kwargs):
		self.__creationTime = kwargs.get('creationTime', None) or now()
		self.__schema = schema
		self.__sourceData = kwargs.get('sourceData', {})
		self.__metaData = kwargs.get('metaData', {})
		self.__static = kwargs.get('static', False)
		self.__subItems = []
		self.__dataMap = kwargs.get('dataMap', None)
		super().__init__()
		self.__init_data__(data)
		self.mapData()
		self.validate()

	def __init_data__(self, data: dict):
		data = self.mapArrays(data)
		data = self.parseData(data=data)
		data = self.replaceKeys(data)
		data = self.replaceKeyVars(data)
		data = self.addDataKeyValues(data)
		self.update(data)

	@lru_cache(maxsize=16)
	def findTimeKey(self, data: dict) -> str:
		if isinstance(data, frozenset):
			timeKey = self.schema['timestamp']['sourceKey']
			if isinstance(timeKey, (list, tuple, set, frozenset)):
				for key in timeKey:
					if key in data:
						return key
			elif timeKey in data:
				return timeKey
			return (get_close_matches('timestamp', list(data), n=1, cutoff=0.5) or ['timestamp'])[0]
		else:
			return 'timestamp'

	def mapData(self):
		if self.__schema is None:
			return
		data = self
		dataMap = self.dataMap
		items = self.findAll() or [Subdatagram(parent=self, data=dict(self), path=())]
		for name, _map in dataMap.items():
			s = DotStorage({'map': _map})
			for item in items:
				match item:
					case Subdatagram(path=s.map):
						self[name] = items.pop(items.index(item))
						break
					case [Subdatagram(path=(s.map, i)), *_]:
						self[name] = items.pop(items.index(item))
						break
					case [Subdatagram(path=s.map), *_]:
						self[name] = items.pop(items.index(item))
						break

		# remove any items that were not mapped
		for key, value in list(data.items()):
			if key in dataMap:
				continue
			else:
				del data[key]

	def findAll(self):
		items = []

		def find(item: dict):
			match item:
				case [Subdatagram(), *_]:
					if len(item) == 1:
						items.append(item[0])
					else:
						items.append(item)
				case Subdatagram() as item:
					items.append(item)
				case dict():
					for key, value in item.items():
						find(value)

		find(self)
		return items

	@property
	def sourceData(self):
		return self.__sourceData

	@sourceData.setter
	def sourceData(self, value):
		self.__sourceData = value

	@property
	def metaData(self):
		return self.__metaData

	@metaData.setter
	def metaData(self, value):
		self.__metaData = value

	@property
	def creationTime(self):
		return self.__creationTime

	@property
	def schema(self):
		return self.__schema

	@property
	def static(self):
		return self.__static

	def __getitem__(self, item):
		if item.startswith('@'):
			if item.startswith('@meta.'):
				return self.metaData[f'@{item[6:]}']
			elif item.startswith('@source.'):
				return self.sourceData[f'@{item[8:]}']
			return self.metaData.get(item, None) or self.sourceData.get(item, None)
		return super().__getitem__(item)

	def __setitem__(self, key, value):
		if not self.static:
			if key in self.schema._ignored:
				return
			if not isinstance(value, LevityDatagram):
				self.parseData(key=key, value=value)
				data = self.replaceKeyVars({key: value})
			super().__setitem__(key, value)

	def replaceKeyVars(self, data: dict):
		def findVar(atom: str, ignore: set = None):
			if ignore is None:
				ignore = set()
			elif atom in ignore:
				return None
			ignore.add(atom)
			main = self.sourceData.get(atom, None) or self.metaData.get(atom, None)
			return main or findVar(self.schema.properties.get(atom, {}).get('alt', None), ignore) or 'NA'

		for key, value in dict(data).items():
			key = CategoryItem(key)
			keyVars = {f'{i}': findVar(i) for i in key.vars}
			if keyVars:
				data.pop(key)
				key = key.replaceVar(**keyVars)
			data[key] = value
		return data

	def replaceKeys(self, data: dict = None):
		nullKeys = self.schema.nullAllowedKeys
		for key, value in dict(data).items():
			data.pop(key)
			if key in self.schema._ignored:
				continue
			mappedKey = self.schema.sourceKeyMap.get(key, key)
			if value is None and mappedKey not in nullKeys:
				continue
			data[mappedKey] = value
		return data

	def addDataKeyValues(self, data: dict):
		if not self.schema.hasDataKeys:
			return data
		for key, dataKey in ((k, j) for k, v in self.schema.dataKeyItems.items() if (j := v.get('dataKey', None)) in data):
			data[key] = data[dataKey]
		return data

	def __hash__(self):
		return hash(tuple(self.sourceData.items()))

	def parseData(self, *_: None, key: str = None, value: str = None, data: dict = None, path: list = None):
		if key and value and data is None:
			data = {key: value}
		if data is None:
			raise SyntaxError('No data provided')
		storage = DotStorage({})
		for key, value in list(data.items()):
			storage.update({
				'key':     key,
				'value':   value,
				'path':    (*(path or ()), key),
				'timekey': self.findTimeKey(frozenset(value.keys())) if isinstance(value, dict) else ''
			})
			if len(storage.path) == 1:
				storage.path = storage.path[0]
			match value:
				case (str() | int() | float() | bool()):
					popLater = False
					if key in self.schema.properties:
						prop = self.schema.properties.get(key)
						if prop.get(tsk.sourceData, False):
							self.sourceData[f'@{self.schema.properties.getKey(key)}'] = value
							popLater = True
					if key in self.schema.metaData:
						meta = self.schema.metaData.get(key)
						if meta.get(SchemaSpecialKeys.metaData, False):
							if any(i in str(key) for i in ('time', 'date')):
								if isinstance(value, str):
									try:
										DateParser.parse(value)
									except DateParser.ParserError:
										continue
							self.metaData[f'@{self.schema.metaData.getKey(key)}'] = value
							popLater = True
					if popLater:
						data.pop(key)
				case {storage.timekey: list(timestamps), **rest} if storage.path in self.validPaths and any(key in self.schema.sourceKeys for key in value):
					expectedLen = len(value[storage.timekey])
					if any(len(v) != expectedLen for v in value.values()):
						raise InvalidData
					keys = list(value.keys())
					d = []
					basePath = storage.path if isinstance(storage.path, (tuple, list)) else (storage.path,)
					for i, _ in enumerate(timestamps):
						values = {k: value[k][i] for k in keys}
						itemPath = basePath + (i,)
						subdatagram = Subdatagram(parent=self, data=values, path=itemPath)
						if len(subdatagram):
							d.append(subdatagram)
					data[key] = d
				case dict() as obs if storage.path in self.validPaths and any(key in self.schema.sourceKeys for key in obs):
					data[key] = Subdatagram(parent=self, data=value, path=key)
				case dict():
					data[key] = self.parseData(data=value, path=[key])
				case [*items]:
					for i, item in enumerate(items):
						match item:
							case dict() as obs if any(key in self.schema.sourceKeys for key in obs):
								if all(i is None for i in item.values()):
									continue
								itemPath = (*(path or ()), key, i)
								value[i] = Subdatagram(parent=self, data=item, path=itemPath)
							case _:
								pass
				case _:
					pass

		return data

	def mapArrays(self, data, keyMap: Optional[str] = None):
		keyMap = keyMap or self.schema.getKeyMap(data, datagram=self) or {}
		if isinstance(keyMap, dict):
			for key, subMap in keyMap.items():
				if isinstance(data, list) and key == len(data) or (key is iter and len(subMap) == len(data)):
					data = [self.mapArrays(data=item, keyMap=subMap) for item in data]
				elif isinstance(data, dict) and (subData := data.get(key, None)) is not None and isinstance(subData, List) and len(subData) >= len(subMap) and ... in subMap:
					data[key] = self.mapArrays(subData, keyMap=subMap)
				elif isinstance(subMap, list) and key is filter:
					for k, v in list(data.items()):
						if k in subMap:
							continue
						data.pop(k)
				elif isinstance(data, list) and isinstance(data[0], list) and len(data[0]) == len(subMap):
					return [self.mapArrays(data=item, keyMap=subMap) for item in data]
				elif key in data:
					data[CategoryItem(key)] = self.mapArrays(data=data.pop(key), keyMap=subMap)
		elif isinstance(keyMap, list) and (len(keyMap) == len(data) or ... in keyMap):
			return {CategoryItem(key): value for key, value in zip((i for i in keyMap if i is not ...), data)}
		return data

	def replace(self, data: dict, metadata: dict = None):
		self.clear()
		m = {k: v for k, v in data.items() if k.startswith('@')}
		self.update(data)

	def replaceKey(self, oldKey: str, newKey: str):
		self[newKey] = self.pop(oldKey, None)

	def metaKeys(self):
		return *[f'@meta.{i.strip("@")}' for i in self.metaData.keys()], *[f'@source.{i.strip("@")}' for i in self.sourceData.keys()]

	def metaValues(self):
		return [*self.metaData.values(), *self.sourceData.values()]

	def metaItems(self):
		return zip(self.metaKeys(), self.metaValues())

	def __iter__(self):
		return super().items().__iter__()

	@property
	def __trunc(self):
		def trim(data):
			match data:
				case Subdatagram():
					meta = {k: v for k, v in data.metaData.items() if k not in self.metaData}
					source = {k: v for k, v in data.sourceData.items() if k not in self.sourceData}
					return {**meta, **source, **{k.name if isinstance(k, CategoryItem) else k: trim(v) for k, v in data.items()}}
				case dict():
					return {k: trim(v) for k, v in (V for i, V in enumerate(data.items()) if i < 3)}
				case list():
					return [trim(i) for i in data[:min(len(data), 3)]]
				case _:
					return data

		return {k: trim(v) for k, v in self.items()}

	def __str__(self):
		return pretty_repr({**self.metaData, **self.sourceData, **self.__trunc}, indent_size=2, max_depth=3, max_length=200, max_string=600)

	def __replaceWithSubData(self, key: str, value: str):
		self[key] = Subdatagram(parent=self, data=value, path=key)

	def getData(self, key: str):
		data = self.get(key, None)
		if isinstance(data, Subdatagram):
			return data
		if isinstance(data, dict):
			return LevityDatagram(data=data, schema=self.__schema, static=True, sourceData=self.sourceData, metaData=self.metaData)
		return None

	@property
	def dataMap(self):
		return self.__dataMap or self.schema.dataMaps.get(self.metaData.get('@type', ''), None) or dict()

	@property
	def validPaths(self):
		return list(self.dataMap.values())

	def validate(self):
		for key, value in list(self.items()):
			match value:
				case [Subdatagram()]:
					for item in value:
						item.validate()
				case Subdatagram():
					value.validate()
				case _ if key in self.schema and ((unitMetaData := self.schema.getExact(key)) and unitMetaData.hasValidation):
					validation = unitMetaData.validate(self, key, value)
					if not validation:
						self.pop(key)


class Subdatagram(LevityDatagram):
	def __init__(self, parent: LevityDatagram, data: dict, path: Union[str, tuple]):
		self.__path: tuple[str, int] = (path,) if isinstance(path, str) else tuple(path)
		self.__sourceData = {}
		self.__metaData = {}
		self.__parent = parent
		dict.__init__({})
		self.__init_data__(data)

	@property
	def sourceData(self):
		return ChainMap(self.__sourceData, self.__parent.sourceData)

	@sourceData.setter
	def sourceData(self, value):
		self.__sourceData = value

	@property
	def metaData(self):
		return ChainMap(self.__metaData, self.__parent.metaData)

	@metaData.setter
	def metaData(self, value):
		self.__metaData = value

	@property
	def parent(self):
		return self.__parent

	@property
	def schema(self):
		return self.__parent.schema

	@property
	def creationTime(self):
		return self.__parent.creationTime

	@property
	def static(self):
		return self.__parent.static

	@property
	def path(self):
		path = (*getattr(self.__parent, 'path', ()), *self.__path,)
		if len(path) == 1:
			return path[0]
		return path

	@property
	def dataMap(self):
		return self.__parent.dataMap

	@property
	def isTimeSeries(self) -> bool:
		return len(self) and all(isinstance(i, dict) for i in list(self.values())[:min(10, len(self))])

	def __str__(self, maxLen: int = None):
		maxLen = maxLen or 100
		if self.isTimeSeries:
			dataRepr = [i for i in self.values()[:min(5, len(self))]]
			return pretty_repr({**self.metaData, **self.sourceData, 'data': dataRepr}, indent_size=2, max_width=120, max_depth=1, max_length=maxLen, max_string=200)
		return pretty_repr({**self.metaData, **self.sourceData, **self}, indent_size=2, max_width=120, max_depth=1, max_length=maxLen, max_string=200)


class Properties(dict):

	def __init__(self, plugin: 'Plugin', source: dict):
		self.__plugin = plugin
		keys = [key for key in source.keys() if str(key).startswith('@')]
		for key in keys:
			self[key.strip('@')] = source.pop(key)
		super().__init__({'plugin': plugin})

	def __setitem__(self, key, value):
		key = key.strip('@')
		super().__setitem__(key, value)

	def __getitem__(self, key):
		key = key.strip('@')
		item = super().__getitem__(key)
		return item

	def get(self, key, default=Unset):
		if isinstance(key, str):
			key = key.strip('@')
		value = super().get(key, None)
		if value is not None:
			return value
		key = self.sourceKeys.get(key, None)
		if key is not None:
			return super().get(key, None)
		if default is not Unset:
			return default
		raise KeyError(key)

	def getKey(self, key):
		key = key.strip('@')
		if key in self.keys():
			return key
		return self.sourceKeys.get(key, key)

	def __contains__(self, key):
		if isinstance(key, str):
			key = key.strip('@')
		return super().__contains__(key) or key in self.sourceKeys

	@cached_property
	def sourceKeys(self):
		sourceKeys = {key: value['sourceKey'] for key, value in self.items() if 'sourceKey' in value}
		for key in [k for k in sourceKeys]:
			value = sourceKeys.pop(key)
			if isinstance(value, list):
				sourceKeys.update({v: key for v in value})
			else:
				sourceKeys[value] = key
		return sourceKeys

	@property
	def plugin(self) -> 'Plugin':
		return self.__plugin


class MetaData(dict):

	def __init__(self, plugin: 'Plugin', source: dict):
		self.__plugin = plugin
		keys = [key for key, value in source.items() if str(key).startswith('@meta') or SchemaSpecialKeys.metaData in value]
		keys = sorted(keys, key=lambda k: str(k).startswith('@'), reverse=True)
		for key in keys:
			originalKey = key
			key = str(key)
			key = key.replace('@meta.', '@', 1)
			if SchemaSpecialKeys.metaData not in source[originalKey] or originalKey.startswith('@meta.'):
				self[key] = source.pop(originalKey)
			else:
				self[key] = source[originalKey]
		super().__init__({'plugin': plugin})

	def __setitem__(self, key, value):
		if isinstance(value.get(SchemaSpecialKeys.metaData, False), str):
			key = value[SchemaSpecialKeys.metaData]
		key = key.strip('@')
		if 'key' not in value:
			value['key'] = key
		if key in self:
			self[key].update(value)
		else:
			if isinstance(value, dict) and not isinstance(value, UnitMetaData):
				value = UnitMetaData(value=value)
			super().__setitem__(key, value)
		clearCacheAttr(self, 'sourceKeys')
		clearCacheAttr(self, 'metaKeys')

	def __getitem__(self, key):
		key = key.strip('@')
		return super().__getitem__(key)

	def get(self, key, default=Unset):
		if isinstance(key, str):
			key = key.strip('@')
		value = super().get(key, None)
		if value is not None:
			return value
		key = self.sourceKeys.get(key, None)
		if key is not None:
			return super().get(key, None)
		if default is not Unset:
			return default
		raise KeyError(key)

	def getKey(self, key):
		if isinstance(key, str):
			key = key.strip('@')
		if key in self.keys():
			return key
		return self.sourceKeys.get(key, key)

	def __contains__(self, key):
		if isinstance(key, str):
			key = key.strip('@')
		return super().__contains__(key) or key in self.sourceKeys

	@cached_property
	def sourceKeys(self):
		sourceKeys = {key: value['sourceKey'] for key, value in self.items() if 'sourceKey' in value}
		keys = {key: value['key'] for key, value in self.items() if 'key' in value}
		for key in [k for k in sourceKeys]:
			value = sourceKeys.pop(key)
			if isinstance(value, (list, tuple)):
				sourceKeys.update({v: key for v in value})
			else:
				sourceKeys[value] = key
		return sourceKeys

	@cached_property
	def metaKeys(self) -> dict:
		return {key: value['key'] for key, value in self.items() if 'key' in value}

	def getValue(self, key, data: dict, default=Unset):
		if isinstance(key, str):
			key = key.strip('@')
		key = self[key].get('sourceKey', key)
		if isinstance(key, (list, tuple)):
			for k in key:
				if k in data:
					return data[k]
			if default is not Unset:
				return default
			raise KeyError(key)
		return data.get(key, default)

	@property
	def plugin(self):
		return self.__plugin


class Schema(CategoryDict):
	__schemas__ = {}
	units = unitDict
	_ignored: set[str]

	@classmethod
	def getFromAll(cls, key: str, default=None):
		result = {n: t.getExact(key) for n, t in cls.__schemas__.items() if key in t}
		return result

	def __init__(self, plugin: 'Plugin', source: dict, category: str = None, ignored: Iterable[str] = None, **kwargs):
		self._ignored = set(source.pop('ignored', []))
		category = ''
		self._plugin = plugin
		self.__requirements = self.buildRequirements(source)
		self.metaData = MetaData(plugin=plugin, source=source)
		self.properties = Properties(plugin=plugin, source=source)
		self.keyMaps = source.pop('keyMaps', {})
		self.dataMaps = source.pop('dataMaps', {})
		self.calculations = source.pop('calculations', {})
		self.aliases = source.pop('aliases', {})
		super(Schema, self).__init__(None, source, category)
		if ignored is not None:
			self._ignored.update(ignored)

		toConvert = [key for key, value in self._source.items() if isinstance(value, dict)]
		for key in toConvert:
			value = UnitMetaData(key=key, reference=self)
			self._source[key] = value
		self.__schemas__[plugin.name] = self
		self.__hash = hash((plugin, frozenset(self.keys())))

	def buildRequirements(self, data: dict):
		return {key: value['requires'] for key, value in data.items() if 'requires' in value}

	def propertySetters(self):
		return {key: value for key, value in self._source.items() if 'property' in value.keys() or 'setter' in value.keys()}

	def getExact(self, key: str | CategoryItem, silent: bool = False) -> Optional[UnitMetaData]:
		if not isinstance(key, CategoryItem):
			key = CategoryItem(key)
		result = self._source.get(key, None) or self._source.get(key.anonymous, None)
		if result is None:
			if str(key) in self.properties:
				return self.properties[str(key)]
			wildcardKeys = [k for k in self._source.keys() if k.hasWildcard and k == key]
			if len(wildcardKeys) == 1:
				result = self._source[wildcardKeys[0]]
			elif not silent:
				if len(wildcardKeys) > 1:
					log.warning(f'{key} has wildcard which results in multiple values for {key}')
				else:
					log.warning(f'{key} was not found in {self}')
		return result

	def __hash__(self):
		return self.__hash

	@cached_property
	def sourceKeyMap(self):
		keyMap = {key: value['sourceKey'] for key, value in self._source.items() if 'sourceKey' in value and key is not None}
		for key in [k for k in keyMap]:
			value = keyMap.pop(key)
			if isinstance(value, list):
				keyMap.update({v: key for v in value})
			else:
				keyMap[value] = key
		return keyMap

	@cached_property
	def hasDataKeys(self) -> bool:
		return any('dataKey' in value for value in self._source.values())

	@cached_property
	def dataKeyItems(self) -> Dict[CategoryItem, Dict]:
		return {k: v for k, v in self.flatDict.items() if 'dataKey' in v}

	@cached_property
	def dataMapPaths(self):
		def __recurse(dataMap, path):
			paths = []
			if isinstance(dataMap, dict):
				for key, value in dataMap.items():
					if isinstance(value, dict):
						paths.extend(__recurse(value, path + [key]))
					else:
						paths.append(path + [key])
			return paths

		paths = []
		for key, value in self.dataMaps.items():
			if isinstance(value, dict):
				paths.extend(__recurse(value, [key]))
			else:
				paths.append([key])
		return paths

	def __setitem__(self, key: CategoryItem, value: UnitMetaData):
		if not isinstance(value, UnitMetaData) and not isinstance(value, dict):
			value = UnitMetaData(key=key, value=value)
		super(Schema, self).__setitem__(key, value)

	def getKeyMap(self, source: Union[str, Iterable[str], Dict[str, str]], datagram: dict | None = None) -> Dict[str, str]:
		source = dict(source)
		if datagram is None:
			datagram = {}
		else:
			source.update(getattr(datagram, 'sourceData', {}))
			source.update(getattr(datagram, 'metaData', {}))
		match source:
			case dict():
				keys = {i for j in source.items() for i in j if isinstance(i, Hashable)}
			case list() | set() | tuple() | frozenset():
				keys = {i for i in source if isinstance(i, Hashable)}
			case str():
				keys = {source}
			case _:
				keys = set()
		if hasattr(source, 'metaData'):
			keys.update({i for j in source.metaItems() for i in j})
		mappings = [s for s in keys if isinstance(s, Hashable) and s in self.keyMaps]
		if len(mappings) == 1:
			return self.keyMaps[mappings[0]]
		elif len(mappings) > 1:
			return self.keyMaps[mappings[-1]]
		else:
			return None

	@lru_cache(maxsize=128)
	def getUnitMetaData(self, key: str, source) -> Optional[UnitMetaData]:
		if str(key).startswith('@meta.'):
			key = key[6:]
			data = self.metaData[key]
			if not isinstance(data, UnitMetaData):
				key = data.get('key', key)
				return self.getUnitMetaData(key, source)
			return data
		if key not in self:
			key = self.sourceKeyMap.get(key, None)
			if key is None:
				log.warning(f'{key} was not found in {self}')
				return None
		metaData = self.getExact(key)
		if metaData is None:
			keys = [str(key) for k in self._source.keys()]
			closestMatch = get_close_matches(str(key), keys, n=1, cutoff=0.5)
			if closestMatch:
				log.warning(f'{key} was not found in {self} but {closestMatch[0]} was found as it\'s closest match')
				return self.getUnitMetaData(closestMatch[0], source)
			else:
				log.warning(f'{key} was not found in {self}')
				return None
		return metaData

	def mapKeys(self, source: Union[str, Iterable[str]], data, keyMap: Optional[str] = None):
		keyMap = keyMap or self.getKeyMap(data) or {}
		if isinstance(keyMap, dict):
			for key, value in keyMap.items():
				if isinstance(data, list) and key is iter:
					data = [self.mapKeys(source, item, value) for item in data]
				# if len(data) == 1:
				# 	data = data[0]
				# 	newData.update(data)
				# else:
				# 	newData = data
				elif isinstance(value, list) and key is filter:
					for k, v in list(data.items()):
						if k in value:
							continue
						data.pop(k)
				elif key in data:
					data[key] = self.mapKeys(source, data.pop(key), value)
			data = self.__replaceSourceKeys(data)
		elif isinstance(keyMap, list) and len(keyMap) == len(data):
			return {keyMap[i]: data[i] for i in range(len(keyMap))}
		return data

	def __replaceSourceKeys(self, data: dict):
		if isinstance(data, (list, tuple)):
			return [self.__replaceSourceKeys(item) for item in data]
		for key, value in data.copy().items():
			if isinstance(value, dict):
				data[key] = self.__replaceSourceKeys(value)
			elif isinstance(value, (list, tuple)):
				data[key] = [self.__replaceSourceKeys(item) for item in value]
			elif key in self.sourceKeyMap:
				newKey = self.sourceKeyMap[key]
				data[newKey] = data.pop(key)
		return data

	def mapData(self, source: dict, data: dict, requiredKeys: Set[str] = None):
		data = self.mapKeys(source, data)
		possibleDataMaps = {k: v for k, v in self.dataMaps.items() if k in data or any(V[0] in [*data.values(), *data.keys()] for V in v)}
		for mapName, maps in possibleDataMaps.items():
			subData = data
			for subMap in (m for m in maps if m[0] in (*(i for i in subData.values() if isinstance(i, (str, int))), *subData.keys())):
				for key in subMap:
					if key in subData:
						subData = subData[key]
					elif key.isdigit() and len(subData) == 1:
						try:
							subData = subData.pop(int(key))
						except (IndexError, TypeError):
							break
					else:
						break
				else:
					data[mapName] = subData
					break
		self.__setProperties(source, '.', data)

		for key in list(data.keys()):
			if key not in self.dataMaps:
				data.pop(key)

		return data

	def __setProperties(self, source: dict, key: str, data: dict):
		if key in self._ignored:
			pass
		if key in self.keyMaps:
			key = self.keyMaps[key]
		if isinstance(data, dict):
			for key, value in data.items():
				if key in self._ignored:
					continue
				self.__setProperties(source, key, value)
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
			if len(sourceKey) == 1:
				return sourceKey.pop()
		raise ValueNotFound(f'{key} not found')

	@property
	def plugin(self) -> 'Plugin':
		return self._plugin

	@cached_property
	def sourceKeys(self):
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

	@cached_property
	def nullAllowedKeys(self) -> Set[CategoryItem]:
		return {key for key, metadata in self.flatDict.items() if metadata.get('allowNull', False)}

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
