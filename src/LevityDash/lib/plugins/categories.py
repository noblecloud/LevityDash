import re
from collections import ChainMap, Counter
from datetime import datetime
from functools import cached_property, lru_cache
from typing import Any, Callable, ClassVar, Dict, Hashable, Iterable, Mapping, Optional, TypeVar, Union, Type

from rich import repr
from rich.text import Text
from pytz import timezone

from LevityDash.lib.plugins.utils import SchemaProperty, unitDict
from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.utils.shared import (clearCacheAttr, ColorStr, get, getOrSet, LOCAL_TIMEZONE, matchWildCard, operatorDict,
                                         removeSimilar, subsequenceCheck, Unset)
from WeatherUnits import Measurement

log = LevityPluginLog.getChild('Categories')

__all__ = ['UnitMetaData', 'CategoryWildcard', 'CategoryAtom', 'CategoryItem', 'CategoryDict', 'CategoryEndpointDict', 'ValueNotFound']

RHS = TypeVar('RHS')
LHS = TypeVar('LHS')


class Requirement:
	operator: Callable
	rhs: RHS
	lhs: LHS
	negated: bool
	result: Union[bool, RHS, LHS]
	__operationName: str
	__storedResult: Union[bool, RHS, LHS]

	def __init__(self, *_, operator: Union[Callable, str], lhs: Any, lhsName: str = None, rhs: Any, rhsName: str = None, negated: bool = False):
		self.__operationName = operator if isinstance(operator, str) else operator.__name__
		self.__storedResult = Unset
		if not isinstance(operator, Callable):
			operator = operatorDict[operator]
		self.operator = operator
		self.rhs = rhs
		self.rhsName = rhsName
		self.lhs = lhs
		self.lhsName = lhsName
		self.negated = negated

	def __bool__(self):
		return self.result != self.negated

	@property
	def result(self):
		if self.__storedResult is Unset:
			self.__storedResult = self.operator(self.lhs, self.rhs)
		return self.__storedResult

	def reset(self):
		self.__storedResult = Unset

	def __str__(self):
		match bool(self):
			case True:
				return f'{self.__operationName}[{ColorStr.green("Passed ✔︎︎︎")}]'
			case False:
				return f'{self.__operationName}[{ColorStr.red("Failed ✘")}]: {self.lhs} {"not " if self.negated else ""}{self.__operationName} {self.rhs}'

	def __repr__(self):
		lhs = f'{self.lhsName}={self.lhs}' if self.lhsName else str(self.lhs)
		rhs = f'{self.rhsName}={self.rhs}' if self.rhsName else str(self.rhs)
		return f'{"︎︎✔︎" if self else "✘"} | {lhs} {operatorDict[self.operator]} {rhs}'


@repr.auto
class UnitMetaData(dict):

	def __init__(self, **kwargs):
		match kwargs:
			case {'key': key, 'reference': reference} | {'key': key, 'source': reference}:
				key = CategoryItem(key)
				value = kwargs.get('value', {})
			case {'value': dict(value)} if 'key' in value:
				key = CategoryItem(value['key'])
				value = kwargs.get('value', {})
				reference = None
			case {'key': key, 'value': dict(value)}:
				key = CategoryItem(key)
				reference = None
			case {}:
				raise ValueError('No data provided')
			case {**rest}:
				raise ValueError(f'Unknown data: {rest}')
			case _:
				raise ValueError(f'Unknown data: {kwargs}')

		if reference:
			for atom in (i for i in (*key.parents, key) if i in reference.flatDict):
				x = reference.getExact(atom)
				if isinstance(x, dict):
					value.update(x)
			value = self.findProperties(reference, value)
		value['key'] = key
		super(UnitMetaData, self).__init__(value)

	def __repr__(self):
		match dict(self):
			case {'key': CategoryItem(key) | key, **rest}:
				return f'UnitMetaData({key.name})'
			case {'sourceKey': key, **rest}:
				return f'UnitMetaData({key})'
			case _:
				return f'UnitMetaData({self})'

	def __hash__(self):
		return hash(self.key)

	def __findSimilar(self, key: 'CategoryItem'):
		from LevityDash.lib.plugins.schema import Schema
		return Schema.getFromAll(key, None)

	def findProperties(self, source: 'Schema', data: dict):
		if isinstance(data, UnitMetaData):
			data = dict(data)
		if isinstance(data, dict):
			alias = data.pop('alias', None) or data.pop('aliases', None)
			for key, value in data.items():
				if key == '{{metaData}}':
					continue
				data[key] = self.findProperties(source, value)
			if alias is not None:
				if isinstance(alias, dict):
					data['alias'] = self.findProperties(source, alias)
				else:
					data['alias'] = source.aliases.get(alias, {})
		elif isinstance(data, CategoryItem):
			pass
		elif isinstance(data, (tuple, list)):
			data = [self.findProperties(source, i) for i in data]
		elif isinstance(data, str):
			if data.startswith('@'):
				prop = source.properties.get(data, None)
				if prop is None:
					raise ValueNotFound(f'{data} not found')
				data = SchemaProperty(source, prop)
		# elif data in self.units:
		# 	data = self.units[data]
		return data

	@lru_cache(maxsize=256)
	def getConvertFunc(self, source: Hashable = None):
		typeString = self.get('type', None)
		unitDef = self.get('sourceUnit', None)
		kwargs = kwargs = self.get('kwargs', {})
		if typeString is None or unitDef is None:
			return lambda value: value
		if typeString in ('datetime', 'date'):
			if 'tz' in kwargs:
				if isinstance(kwargs['tz'], SchemaProperty):
					value = kwargs['tz']
					kwargs['tz'] = value(source)
				if isinstance(kwargs['tz'], str):
					kwargs['tz'] = timezone(kwargs['tz'])
			else:
				kwargs['tz'] = LOCAL_TIMEZONE
			if unitDef == 'epoch':
				return lambda value: datetime.fromtimestamp(int(value), **kwargs)
			elif unitDef == 'ISO8601':
				format = self.get('format', None)
				if isinstance(format, dict):
					format = format[source.dataName]
				return lambda value: datetime.strptime(value, format).astimezone(LOCAL_TIMEZONE)
		if isinstance(unitDef, str) and unitDef in unitDict:
			return lambda value: unitDict[unitDef](value, **kwargs)
		if isinstance(unitDef, str) and '[' in unitDef:
			unitType = unitDef.split('[')[0]
			unitDef = unitDef.split('[')[1].split(']')[0]
			cls = unitDict['special'][unitType][unitDict[unitDef]]
			return lambda value: cls(value, **kwargs)

		if isinstance(unitDef, Iterable):
			if len(unitDef) == 2:
				n, d = unitDef
				if isinstance(n, str) and n in unitDict:
					n = unitDict[n]
				if isinstance(d, str) and d in unitDict:
					d = unitDict[d]
				if isinstance(d, SchemaProperty):
					d = d(source)
				elif isinstance(d, type):
					d = d(1)
				if hasattr(d, 'value'):
					d = d.value
				comboCls = unitDict['special'][typeString][n: type(d)]
				return lambda value: comboCls(value, d, **kwargs)
		if typeString is not None and unitDef is not None:
			if isinstance(unitDef, str):
				cls = unitDict['str']
				return lambda value: cls(value, **kwargs)

		return lambda value: value

	@lru_cache(maxsize=64)
	def mapAlias(self, value: Any) -> Any:
		typeString = self.get('type', None)
		if not self.hasAliases:
			if typeString == 'icon':
				log.warning(f'No aliases found for {self.key}.  A mapping of icons must be provided in the schema.')
			else:
				log.warning(f'No aliases found for {self.key}')
			return value
		alias = self['alias']
		try:
			value = self.aliasDataType(value)
		except ValueError:
			pass
		return alias.get(value, value)

	@cached_property
	def aliasDataType(self) -> Type:
		aliasDict = self.get('alias', None)
		allTypes = set(type(i) for i in aliasDict)
		typeList = [type(i) for i in aliasDict]
		return max(((i, typeList.count(i)) for i in allTypes), key=lambda i: i[1], default=(str, 0))[0]

	def findValue(self, data: dict) -> Any:
		keys = list(set(data.keys()) & self.dataKeys)
		match len(keys):
			case 0:
				return None
			case _:
				return data[keys[0]]

	def validate(self, data: 'Subdatagram', key: Union[str, 'CategoryItem', Hashable] = Unset, value: Any = Unset) -> bool:
		log.verbose(f'Validating {self.key.name}', verbosity=4)

		def isValid(validation) -> bool:
			return all(v for k, v in validation.items() if '.' not in k)

		validation = {}

		# find the value from the provided data if not provided
		if value is Unset:
			keys = list(set(data.keys()) & set(self.dataKeys))
			match len(keys):
				case 0:
					validation['KeyFound'] = False
					value = None
				case 1:
					value = data[keys[0]]
					validation['KeyFound'] = True
				case _:
					log.warning(f'{self} found multiple keys: {keys} while validating')
					value = data[keys[0]]
					validation['KeyFound'] = True
					validation['KeyFound.MultipleKeys'] = keys

		if (required := self.get('requires', False)) and isValid(validation):
			log.verbose('Checking requirements...', verbosity=4)
			if isinstance(required, str):
				other = data.schema.get(required)
				validation['MeetsRequirements'] = True if self.testValidationLoop(other) and other.validate(data) else False
			elif isinstance(required, (list, tuple)):
				if all(data.schema.get(r).validate(data) for r in required if self.testValidationLoop(r)):
					validation['MeetsRequirements'] = True
				else:
					validation['MeetsRequirements'] = False
					validation['MeetsRequirements.Missing'] = list(set(required) - set(data.keys()))
			elif isinstance(required, dict):
				requirementValidation: dict[str, [Requirement]] = {}
				for requirementKey, requirements in required.items():
					requirementKey = CategoryItem(requirementKey)
					other = data.schema.get(requirementKey)
					otherValue = other.findValue(data)
					negate = requirements.get('negate', False)
					if self.testValidationLoop(other) and other.validate(data):
						results: [Requirement] = []
						operations = list(set(requirements.keys()) & set(operatorDict.keys()))
						for opName in operations:
							op = operatorDict[opName]
							compare = requirements[opName]
							localNegate = requirements['negate'] if 'negate' in requirements else negate
							results.append(Requirement(operator=op, lhs=otherValue, lhsName=requirementKey.name, rhs=compare, rhsName=None, negated=localNegate))
						requirementValidation[requirementKey] = results

					else:
						requirementValidation[requirementKey] = {'valid': [False]}
				failures = [i for j in [v for k, v in requirementValidation.items() if not all(v)] for i in j]
				report = self.__genReport(requirementValidation)
				if failures:
					if get(required, 'verbose', default=False) or not get(required, 'quiet', 'silent', 'silently', default=False):
						log.verbose(report, verbosity=5)
					else:
						log.verbose(report, verbosity=5)
					validation['MeetsRequirements'] = False
					validation['MeetsRequirements.Missing'] = failures
				else:
					validation['MeetsRequirements'] = True
					log.verbose(report, verbosity=4)
			else:
				raise TypeError(f'{self} requires must be a string, list, tuple, or dict')

		return isValid(validation)

	def __genReport(self, validationResults):
		status = any(i for j in [v for k, v in validationResults.items() if all(v)] for i in j)
		header = f'--- {self.key.name} - {"Success" if status else "Failure"} {"✔︎" if status else "✘"} ---'
		validationResults = [i for j in [v for v in validationResults.values()] for i in j]
		body = '\n'.join(f'  {i.__repr__()}' for i in validationResults)
		report = f'{header}\n{body}'
		return report

	def testValidationLoop(self, other: 'UnitMetaData') -> bool:
		"""
		Checks to see if both items require each other which would result in a loop
		"""
		overlap = self.requirements & other.requirements
		if self in overlap and other in overlap:
			log.warning(f'{self} and {other} require each other which would result in a loop')
			return False
		return True

	@property
	def hasValidation(self) -> bool:
		return 'requires' in self or 'requirements' in self

	@property
	def title(self):
		value = self.get('title', None)
		if value is None:
			others = self.__findSimilar(self['key'])
			if others is not None:
				titles = [x.get('title', None) for x in others]
				titles = [x for x in titles if x is not None]
				mostCommon = max(titles, key=titles.count)
				if mostCommon is not None:
					value = mostCommon
				return value
		return value

	@property
	def description(self):
		return self.get('description', None)

	@property
	def sourceKey(self):
		return self.get('sourceKey', None)

	@property
	def source(self):
		return self.get('source', None)

	@property
	def unit(self):
		return self.get('sourceUnit', None)

	@property
	def symbol(self):
		return self.get('symbol', None)

	@property
	def abbreviation(self):
		return self.get('aliases', None)

	@property
	def display(self):
		return self.get('display', None)

	@property
	def precision(self):
		return self.get('precision', None)

	@property
	def rounding(self):
		return self.get('rounding', None)

	@property
	def type(self):
		return self.get('type', None)

	@property
	def key(self):
		return self.get('key', None)

	@property
	def category(self):
		return CategoryItem(self.get('key', None))

	@cached_property
	def dataKeys(self) -> frozenset[str, 'CategoryItem']:
		sourceKeys = [self.sourceKey] if isinstance(self.sourceKey, (str, CategoryItem)) else self.sourceKey
		return frozenset({self.key, *(sourceKeys if sourceKeys is not None else [])})

	@cached_property
	def requirements(self) -> frozenset[str, 'CategoryItem', Hashable]:
		requires = self.get('requires', [])
		if not isinstance(requires, str) and isinstance(requires, Iterable):
			if isinstance(requires, Mapping):
				requires = requires.keys()
			elif all(isinstance(x, Hashable) for x in requires):
				requires = set(requires)
			else:
				raise TypeError(f'Requirements for {self.key} are invalid.  The following items are not hashable: {[x for x in requires if not isinstance(x, Hashable)]}')
		elif isinstance(requires, Hashable):
			requires = [requires]
		else:
			raise TypeError(f'Requirements for UnitMetaData must be a string, list or tuple of keys, or mapping of value/operation pairs')
		return frozenset(requires)

	@cached_property
	def hasAliases(self) -> bool:
		return 'alias' in self


class CategoryWildcard(str):
	__knownWildcards: ClassVar[Dict[str, 'CategoryWildcard']] = dict()

	def __new__(cls, value: str):
		if len(value) > 1:
			value = f'*{value.strip("*")}*'
		if (value := cls.__knownWildcards.get(value, None)) is None:
			value = cls.__knownWildcards[value] = super().__new__(cls, value)
		return value

	def __str__(self):
		return f'{ColorStr.italic(self)}'

	def __repr__(self):
		return f'{self}'

	def __hash__(self):
		return str.__hash__(self)

	def __eq__(self, other):
		if isinstance(other, CategoryWildcard):
			return True
		return super().__eq__(other)

	@classmethod
	def addWildcard(cls, wildcard: str):
		cls.__knownWildcards[str(wildcard)] = CategoryWildcard(wildcard)

	@classmethod
	def regexMatchPattern(cls) -> str:
		return rf'{"|".join(cls.__knownWildcards)}'

	@classmethod
	def contains(cls, item: str) -> bool:
		return item in cls.__knownWildcards or item in cls.__knownWildcards.items()


CategoryWildcard.addWildcard('*')
CategoryWildcard.addWildcard('@')


class CategoryAtom(str):

	def __new__(cls, value: str):
		if CategoryWildcard.contains(value):
			return CategoryWildcard(value)
		return super().__new__(cls, value)

	def __eq__(self, other):
		if isinstance(other, CategoryWildcard):
			return True
		return super().__eq__(other)

	def __hash__(self):
		return str.__hash__(self)


# Section CategoryItem
class CategoryItem(tuple):
	root: ClassVar['CategoryItem']
	__separator: str = '.'
	__source: Optional[Hashable]
	__existing__ = {}

	def __new__(cls, *values: Union[tuple, list, str], separator: Optional[str] = None, source: Any = None, **kwargs):
		if separator is not None:
			cls.__separator = separator
		valueArray = []
		for value in values:
			if value is None:
				continue
			elif isinstance(value, str):
				valueArray.extend(re.findall(rf"[\w|{CategoryWildcard.regexMatchPattern()}|\-]+", value))
			else:
				valueArray.extend(value)
		source = tuple(source) if isinstance(source, list) else (source,)
		id = hash((*tuple(valueArray), *source))
		if id in cls.__existing__:
			return cls.__existing__[id]
		kwargs['id'] = id
		valueArray = tuple(CategoryAtom(value) for value in valueArray)
		value = super(CategoryItem, cls).__new__(cls, valueArray, **kwargs)
		cls.__existing__[id] = value
		return value

	def __init__(self, *values: Union[tuple, list, str], separator: Optional[str] = None, source: Any = None, **kwargs):
		self.source = source
		self.__id = kwargs.pop('id', None)
		self.__hash = None

	@property
	def source(self) -> Hashable:
		return self.__source

	@source.setter
	def source(self, value: Hashable):
		if value is None:
			self.__source = value
			return
		if isinstance(value, Iterable):
			value = tuple(value)
		if not isinstance(value, Hashable):
			raise TypeError('source must be hashable')
		if not isinstance(value, tuple):
			value = (value,)
		self.__source = value

	@cached_property
	def hasWildcard(self):
		return any([str(item) == '*' or str(item).startswith("@") for item in tuple(self)])

	@cached_property
	def isRoot(self):
		return len(self) == 0

	@cached_property
	def anonymous(self) -> 'CategoryItem':
		return CategoryItem(self, source=None)

	@cached_property
	def isAnonymous(self) -> bool:
		return self.source is None

	@property
	def category(self) -> 'CategoryItem':
		return self[:-1]

	@property
	def name(self) -> str:
		values = tuple(self)
		if len(values) == 0:
			return ''
		if len(values) <= 2:
			return str(values[-1])
		else:
			name = str(values[1])
			for item in values[2:]:
				if item == '*' or item.lower() in name.lower():
					continue
				name += item.title()
			return name

	@property
	def key(self) -> str:
		return self[-1]

	def __hash__(self):
		if self.__hash is None:
			if self.__source is None:
				value = hash(str(self))
			else:
				value = hash((self.__source, self.__separator.join(self)))
			self.__hash = value
		return self.__hash

	def __str__(self):
		if self.__source is None:
			return self.__separator.join(self)
		return f'{":".join(str(_) for _ in self.__source)}:{self.__separator.join(self)}'

	def __repr__(self):
		if self:
			return self.__separator.join(self)
		else:
			return '.'

	def __rich_repr__(self) -> repr.Result:
		yield 'name', self.name
		yield 'key', str(self)
		if len(self) > 1:
			yield 'domain', str(self[0])
		if len(self) > 2:
			yield 'category', str(self[1])
		if len(self) > 3:
			yield 'key', tuple(str(i) for i in self[1:-1])
		if (source := self.source) is not None:
			yield 'source', source
		if self.hasWildcard:
			yield 'wildcard', True
			if vars := self.vars:
				yield 'vars', vars
		if self.isAnonymous:
			yield 'anonymous', True

	def __contains__(self, item):
		if self.isRoot:
			return True
		if not isinstance(item, CategoryItem):
			item = CategoryItem(item)
		if item.isRoot:
			return False
		return subsequenceCheck(list(item), list(self))

	def __lt__(self, other):
		if isinstance(other, str):
			other = CategoryItem(other)
		if self.isRoot or other.isRoot:
			return True
		m = min(len(self), len(other))
		return subsequenceCheck(list(self)[:m], list(other)[:m])

	def __gt__(self, other):
		if isinstance(other, str):
			other = CategoryItem(other)
		if self.isRoot or other.isRoot:
			return False
		m = min(len(self), len(other))
		return subsequenceCheck(list(self)[:m], list(other)[:m])

	def __eq__(self, other):
		if isinstance(other, str):
			nameMatch = self.name == other
			exactMatch = str(self) == other
			if nameMatch or exactMatch:
				return True
		if not isinstance(other, CategoryItem) and isinstance(other, (str, list, tuple, set, frozenset)):
			other = CategoryItem(other)
		elif other is None:
			return False
		if not isinstance(other, type(self)):
			return False
		if self.isRoot or other.isRoot:
			return False
		if self.hasWildcard or other.hasWildcard:
			return subsequenceCheck(list(self), list(other), strict=True)
		if self.source is not None and other.source is not None:
			return hash(self) == hash(other) and self.source == other.source
		return hash(self) == hash(other)

	def __add__(self, other):
		return CategoryItem([*self, *other])

	def __sub__(self, other):
		if self.isRoot:
			return other

		if isinstance(other, str):
			other = CategoryItem(other)
		if other.isRoot:
			return self

		start = 0
		for x, y in zip(self, other):
			if matchWildCard(x, y):
				start += 1
		return CategoryItem(self[start:], separator=self.__separator)

	def __and__(self, other):
		if isinstance(other, str):
			other = CategoryItem(other)
		if other.isRoot:
			return self[0]
		value = [x for x, y in zip(self, other) if matchWildCard(x, y)]
		return CategoryItem(value, separator=self.__separator)
		end = 0
		m = min(len(self), len(other)) - 1
		value = list(self)
		otherValue = list(other)
		newValue
		while (self and other) and end < m and matchWildCard(self[end], other[end]):
			end += 1
		return CategoryItem(self[:end], separator=self.__separator)

	def __xor__(self, other):
		'''
		This operation trims similar endings
		'time.temperature' ^ 'environment.temperature' = 'time'
		:param other:
		:type other:
		:return:
		:rtype:
		'''

		if not isinstance(other, CategoryItem):
			other = CategoryItem(other)
		if self.isRoot:
			return other
		if other.isRoot:
			return self

		trim = -1
		M = min(len(self), len(other))
		while -trim < M and (self and other) and (self[trim] == other[trim]):
			trim -= 1
		return CategoryItem(self[:trim], separator=self.__separator)

	def __truediv__(self, other):
		if isinstance(other, str):
			other = CategoryItem(other)

		if self.isRoot:
			return other
		if other.isRoot:
			return self

		value = [*[x for x, y in zip(self, other) if x != y or '*' in (x, y)], *self[len(other):]]
		while value and value[-1] == '*':
			value.pop(-1)
		return CategoryItem(value, separator=self.__separator)

	def __mod__(self, other):
		if isinstance(other, str):
			other = CategoryItem(other)

		if other.isRoot:
			return self[1:]

		return self[len(other):]

	def __floordiv__(self, other):
		if isinstance(other, str):
			other = CategoryItem(other)
		if other.isRoot:
			return self[:1]
		return self[:len(other)]

	def __iter__(self):
		return super().__iter__()

	def __getitem__(self, s) -> 'CategoryItem':
		if self.isRoot:
			return self
		return CategoryItem(list(self)[s], separator=self.__separator)

	def asStr(self):
		return str(self)

	def replaceVar(self, **vars):
		return CategoryItem([vars.get(f'{i}', i) for i in self], separator=self.__separator, source=self.__source)

	@cached_property
	def vars(self):
		return {i for i in self if i.startswith('@')}

	@cached_property
	def parents(self):
		return tuple(CategoryItem(self[:i], separator=self.__separator) for i in range(1, len(self)))

	def startswith(self, value: str):
		return self.__str__().startswith(value)

	@classmethod
	def representer(cls, dumper, data):
		return dumper.represent_scalar('tag:yaml.org,2002:str', str(data))

	@classmethod
	def keysToDict(cls, keys: Iterable['CategoryItem'], levelKey: 'CategoryItem' = None) -> Dict[CategoryAtom, 'CategoryItem']:
		if not keys:
			return levelKey
		levelKey = levelKey or CategoryItem.root
		subLevels = {k & (levelKey + CategoryItem('*')) for k in keys if k < levelKey}
		if subLevels:
			return {key[-1]: cls.keysToDict({k for k in keys if k < key} - {key}, key) for key in subLevels}
		return levelKey


root = CategoryItem(':')
CategoryItem.root = root


class CategoryDict(dict):
	_cache: dict

	def __init__(self, parent: dict = None, source: dict = None, category: str = None):
		self._cache = {}
		self._parent = parent
		self._category = CategoryItem(category)
		self._source = source

		for k in [i for i in source.keys() if not isinstance(i, CategoryItem)]:
			source[CategoryItem(k)] = source.pop(k)

	def refresh(self):
		clearCacheAttr(self, '_dict')
		clearCacheAttr(self, '_keys')
		clearCacheAttr(self, 'flatDict')

	def genWildCardKey(self, *keys: CategoryItem):
		'''
		Generates a key that matches any of the given keys
		:param keys:
		:type keys:
		:return:
		:rtype:
		'''
		if len(keys) == 1 and not isinstance(keys[0], (CategoryItem, str)):
			keys = keys[0]

		M = min(len(key) for key in keys)
		newKey = []
		for i in range(M):
			value = {key[i] for key in keys}
			if len(value) == 1:
				newKey.append(str(value.pop()))
			else:
				newKey.append('*')
		# while newKey and newKey == self.category:
		# 	newKey.pop()
		return CategoryItem(newKey)

	def __getitem__(self, item):
		'''
		Final attempt to find the key
		:param item:
		:type item: str
		:return:
		:rtype: Union[Dict[str, Dict[str, int]], Dict[str, str], SubCategory]
		'''
		# try to get the item directly from source without using the sources __getitem__ method
		# to prevent recursion
		if item in self._source.keys():
			return self._source.__getitem__(item)

		if item in self._dict:
			return self._dict[item]

		# convert the item to a CategoryItem
		if not isinstance(item, CategoryItem):
			item = CategoryItem(item)

		# if the item is length 1:
		# Own category is not wildcard

		if len(item) == 1:
			return {key: value if not isinstance(value, CategoryDict) else value[item] for key, value in self._dict.items() if (isinstance(value, CategoryDict) and item in value) or isinstance(value, TimeAwareValue)}
		# return {key: value if not isinstance(value, CategoryDict) else value[item] for key, value in self._dict.items() if item in value}
		else:
			k = item[1:]
			item = item[0]
			return {key: value if not isinstance(value, CategoryDict) else value[k] for key, value in self._dict.items() if key == item and isinstance(value, CategoryDict) and k in value}
			# return {key: value if not isinstance(value, CategoryDict) else value[k] for key, value in self._dict.items() if key == item and k in value}
			# if the item is a wildcard
			if str(item) == '*':
				pass

			# if the item matches the category exactly:
			if item == self._category:
				return self

			# if the item does not match the category exactly but matches a subcategory:
			subcategoriesContainingItem = {self.category + sub.category: sub[item] for sub in self._values() if item in sub}
			if subcategoriesContainingItem:
				if len(subcategoriesContainingItem) == 1:
					return subcategoriesContainingItem[0]
				else:
					key = self.genWildCardKey([value.category + item for value in subcategoriesContainingItem.values()])
					category_dict = CategoryDict(self, self._source, key)
					return category_dict

			# if the item does not match the category or subcategory:
			# try to find a subcategory that contains the item
			items = [key for key, value in self.items() if item in value]

			# if there is only one item that matches the item:
			if len(items) == 1:
				return self._dict[items[0]][item]

			# if there are multiple items that match the item:
			if len(items) > 1:
				key = self.category + item
				key = self.genWildCardKey([i for i in self._source if key in i])
				values = {key: self._dict[key][item] for key in items}

				sub_category = CategoryDict(self, self, key)
				sub_category._dict
				return sub_category

		if len(item) == 1:
			if not self._category == '*':
				# Check if it matches the immediate subcategories
				if any(item == key for key in self.keys()):
					return dict.__getitem__(self, item)
				# Check if the item matches any of the second level subcategories
				item = CategoryItem(['*', *item])
				items = {key: value for key, value in self._source.items() if key in item}
				if len(items) == 1:
					i = items.popitem()[1]
					self._cache[item] = i
					return item
				if len(items) > 1:
					category = SubCategory(self, items, item)
					self._cache[item] = category
					return category

			# Own category is wildcard
			if self._category == '*':
				# Check if it matches the immediate subcategories
				try:
					return self._dict[item]
				except KeyError:
					pass

				# Check if the item matches any of the second level subcategories
				keys = {key for key, value in self._dict.items() if item in value or item in key}
				if len(keys) == 1:
					category = self._dict[keys.pop()][item]
					self._cache[item] = category
					return category
				if len(keys) > 1:
					if item in keys:
						category = SubCategory(self, self._source, item)
					else:
						pass

					category._dict
					self._cache[item] = category
					return category
				# if len(keys) == 1:
				# 	return self._dict[keys.pop()]
				# if len(keys) > 1:
				# 	# When if more than one subcategory is found, return a SubCategory with a key that is the intersection of all keys
				# 	result = SubCategory(self, subcategories, CategoryItem([*self.category, *item]))
				# 	a = result._dict
				# 	return result
				else:
					raise KeyError(item)

		else:
			# check to see if the root of the key is the same as its own category
			if item[0] == self._category:
				items = {key: value for key, value in self._source.items() if key in item}
				if len(items) == 1:
					# if there is only one item in items return it
					return items.popitem()[1]
				else:
					# Otherwise, return a subcategory
					return SubCategory(self, items, item)
			# if the root is wildcard, ignore the first level of subcategories by adding the root to the key
			elif self._category == '*':
				item = CategoryItem(self._category + item)
				items = {key: value for key, value in self._source.items() if key in item}
				if len(items) == 1:
					# if there is only one item in items return it
					return items.popitem()[1]
				else:
					# Otherwise, return a subcategory
					return SubCategory(self, items, item)
			# if there is a wildcard in the key
			if item.hasWildcard:
				# Check if the item matches any of the immediate subcategories
				items = {key: value for key, value in self._source.items() if key < item}
				if len(items) == 1:
					# if there is only one item in items return it
					return items.popitem()[1]
				else:
					# Otherwise, return a subcategory
					return CategoryDict(self, self._source, item)

		raise KeyError(item)

	def __str__(self):
		return dict.__str__(self._dict)

	def __len__(self):
		return len(self._dict)

	@property
	def level(self):
		def __func():
			if not isinstance(self._parent, CategoryDict):
				return 0
			return self._parent.level + 1

		return getOrSet(self._cache, 'level', __func)

	def get(self, item, default=None):
		try:
			return self[item]
		except KeyError:
			return default

	def getExact(self, item, default=None):
		try:
			return dict.__getitem__(self._source, item)
		except KeyError:
			return default

	def __setitem__(self, key, value):
		if not isinstance(key, CategoryItem):
			key = CategoryItem(key)
		self._source.__setitem__(key, value)
		self.refresh()

	def __contains__(self, item):
		if not isinstance(item, CategoryItem):
			item = CategoryItem(item)
		return item in self.flatDict or any(item == i for i in self.wildcardKeys)

	@property
	def category(self) -> CategoryItem:
		if not isinstance(self._parent, CategoryDict) or self._parent.category is None:
			return self._category
		return self._parent.category + self._category

	@cached_property
	def _dict(self):
		if self.category.hasWildcard:
			cats2 = {}
			for key, value in self._source.items():
				if key < self.category:
					k = CategoryItem(removeSimilar(key, self.category))
					if k not in cats2:
						cats2[k] = [value]
					else:
						cats2[k].append(value)
			for key, value in cats2.items():
				if len(value) == 1:
					cats2[key] = value[0]
				else:
					cats2[key] = CategoryDict(self, self._source, key)
			return cats2
		keys = {key for key in self._source.keys() if self.category < key}
		cats = {k[self.level]: [] for k in keys if len(k) >= self.level + 1 or self.category.hasWildcard}
		for key in keys:
			if len(key) >= self.level + 1 or self.category.hasWildcard:
				cats[key[self.level]].append(key)
		# newKey = key[self.level] if not self.category.hasWildcard else key
		# cats[newKey].append(key)
		cats2 = {}
		try:
			for key, value in cats.items():
				if self.category.hasWildcard:
					key = CategoryItem(removeSimilar(key, self.category))
				if any(isinstance(v, CategoryItem) for v in value) and len(value) > 1:
					# _values = {k: self._source[k] for k in cats[key]}
					c = CategoryDict(self, self._source, key)
					cats2[key] = c
				else:
					if len(value) == 1:
						cats2[key] = self._source[value[0]]
					else:
						cats2[key] = value
			return cats2
		except KeyError:
			log.error(f'Unable to create subcategory for {self.category}')
			raise KeyError(self.category)

	@cached_property
	def wildcardKeys(self):
		return tuple({key for key in self._source.keys() if key.hasWildcard})

	@property
	def parent(self):
		return self._parent

	def keys(self):
		return self._dict.keys()

	def items(self):
		return self._dict.items()

	def values(self):
		return self._dict.values()

	@cached_property
	def flatDict(self):
		if self.category is not None:
			if hasattr(self, '_source'):
				items = dict.items(self._source)
			else:
				items = dict.items(self.parent.flatDict)
			return {k: v for k, v in items if self.category < k}
		else:
			return dict(self)

	@lru_cache(maxsize=8)
	def subValues(self, level: int = None):
		if level is None:
			return self.flatDict.values()
		level = self.level + level
		return [v for k, v in self.flatDict.items() if len(k) == level]

	@lru_cache(maxsize=8)
	def subItems(self, level: int = None):
		if level is None:
			return self.flatDict.items()
		level = self.level + level
		return [(k, v) for k, v in self.flatDict.items() if len(k) == level]

	def subKeys(self, level: int = None):
		if level is None:
			return self.flatDict.keys()
		level = self.level + level
		return getOrSet(self._cache, f'subKeys:{level}', (k for k, v in self.flatDict.items() if len(k) == level))

	def __iter__(self):
		return self._dict.__iter__()


class CategoryEndpointDict(CategoryDict):

	def __init__(self, *args, **kwargs):
		super(CategoryEndpointDict, self).__init__(*args, **kwargs)

	#
	# def keys(self):
	# 	return {**self._dict, **self._source.observations}.keys()
	#
	# def items(self):
	# 	return {**self._dict, **self._source.observations}.items()
	#
	# def _values(self):
	# 	return {**self._dict, **self._source.observations}._values()

	@cached_property
	def _dict(self):
		d = super(CategoryEndpointDict, self)._dict
		d.pop('time', None)
		d['sources'] = {plugin.name: plugin.containerCategories for plugin in self.parent.plugins}
		# a['sources'] = {}
		return d


class SubCategory(CategoryDict):

	def __init__(self, parent, values, category: CategoryItem):
		if not isinstance(category, CategoryItem):
			category = CategoryItem(category)
		self._parent = parent
		self._category = category
		if len(category) > 1:
			precount = len({k for k in values.keys() if self.category in k})
			values = {k/category if category.hasWildcard else k: v for k, v in values.items() if k in self.category}
			postCount = len(values)
			if postCount != precount:
				log.warning(f'{precount - postCount} out of {precount} items were removed from subcategory {self.category}')

	# super(CategoryDict, self).__init__(_values)

	def __repr__(self):
		return f'SubCategory({self._category})'

	def __str__(self):
		return f'SubCategory({self._category})'

	@cached_property
	def _dict(self) -> dict:
		if '*' not in str(self._category):
			wildcard = False
			keys = {(CategoryItem(b) - self.category) for b in dict.keys(self._parent)}
			cats = {k[0]: [] for k in keys if len(k) != 0}
		else:
			return dict(self)
			keys = {b[0] for b in dict.keys(self._parent) if self.category in b}
			cats = {k: [] for k in keys if len(k)}

		for key, value in dict.items(self):
			k = (key & self.category if wildcard else key - self.category)
			k = k if wildcard else k[0]
			cats[k].append(key)

		cats2 = {}
		raw = dict(self)
		for key, value in cats.items():
			key = CategoryItem(key)
			if len(value) == 1:
				cats2[key] = raw[value[0]]
			elif any(isinstance(v, CategoryItem) for v in value):
				values = {k: raw[k] for k in cats[key]}
				key = key[-1] if wildcard else key
				cats2[key] = SubCategory(self, values, key)
			else:
				cats2[key] = value
		return cats2

	def __getitem__(self, item):
		if not isinstance(item, CategoryItem):
			item = CategoryItem(item)
		try:
			return dict.__getitem__(self, item)
		except KeyError:
			pass
		try:
			return self._dict[item]
		except KeyError:
			raise KeyError(item)

	@property
	def category(self):
		if self._parent is not None and self._parent.category is not None and str(self._parent.category) != '*':
			return self._parent.category + self._category
		else:
			return self._category
		return None


class ValueNotFound(Exception):
	pass


__all__ = ['CategoryDict', 'CategoryEndpointDict', 'SubCategory', 'ValueNotFound', 'UnitMetaData']
