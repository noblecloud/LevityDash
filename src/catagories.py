import re

from src import logging
from functools import cached_property
from typing import Any, Hashable, Iterable, Optional, Union

from PySide2.QtCore import Slot

from src.utils import clearCacheAttr, removeSimilar, subsequenceCheck, TranslatorProperty

log = logging.getLogger(__name__)


class UnitMetaData(dict):

	def __init__(self, key: str, reference: dict):
		if not isinstance(key, CategoryItem):
			key = CategoryItem(key)
		self._reference = reference
		value = {}
		for i in range(len(key)):
			try:
				x = reference.getExact(key[:i + 1])
				if x is not None:
					if all(isinstance(k, str) for k in x):
						value.update(x)
			except KeyError:
				pass
		value = self.findProperties(reference, value)
		super(UnitMetaData, self).__init__(value)
		self['key'] = key

	def __repr__(self):
		try:
			return self['sourceKey']
		except KeyError:
			return super(UnitMetaData, self).__repr__()

	def __hash__(self):
		return hash(self['sourceKey'])

	def __findSimilar(self, key: 'CategoryItem'):
		from plugins.translator import Translator
		return Translator.getFromAll(key, None)

	def findProperties(self, source: 'Translator', data: dict):
		if isinstance(data, UnitMetaData):
			data = dict(data)
		if isinstance(data, dict):
			alias = data.pop('alias', None) or data.pop('aliases', None)
			for key, value in data.items():
				data[key] = self.findProperties(source, value)
			if alias is not None:
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
				data = TranslatorProperty(source, prop)
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
				if isinstance(kwargs['tz'], TranslatorProperty):
					value = kwargs['tz']
					kwargs['tz'] = value(source)
				if isinstance(kwargs['tz'], str):
					kwargs['tz'] = pytz.timezone(kwargs['tz'])
			else:
				kwargs['tz'] = config.tz
			if unitDef == 'epoch':
				return lambda value: datetime.fromtimestamp(int(value), **kwargs)
			elif unitDef == 'ISO8601':
				format = self.get('format', None)
				if isinstance(format, dict):
					format = format[source.dataName]
				return lambda value: datetime.strptime(value, format).astimezone(config.tz)
		if typeString == 'icon':
			if self['iconType'] == 'glyph':
				alias = self['alias']
				return lambda value: alias.get(str(value), value)
		if isinstance(unitDef, str) and unitDef in unitDict:
			return lambda value: unitDict[unitDef](value, **kwargs)
		if isinstance(unitDef, Iterable):
			if len(unitDef) == 2:
				n, d = unitDef
				if isinstance(n, str) and n in unitDict:
					n = unitDict[n]
				if isinstance(d, str) and d in unitDict:
					d = unitDict[d]
				if isinstance(d, TranslatorProperty):
					d = d(source)
				elif isinstance(d, type):
					d = d(1)
				if hasattr(d, 'value'):
					d = d.value
				comboCls = unitDict['special'][typeString][n, type(d)]
				return lambda value: comboCls(value, d, **kwargs)
		if typeString is not None and unitDef is not None:
			if isinstance(unitDef, str):
				cls = unitDict['str']
				return lambda value: cls(value, **kwargs)

		return lambda value: value
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
		return self.get('abbreviation', None)

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


# class Category(tuple):
# 	__separator: str = '.'
#
# 	def __new__(cls, value: Union[tuple, list, str]):
# 		if isinstance(value, str):
# 			value = value.split(cls.__separator)
# 		if not value:
# 			value = ()
# 		if len(value) >= 2 and value[-2] == value[-1]:
# 			value = value[:-1]
# 		return super(Category, cls).__new__(cls, value)
#
# 	def __init__(self, value: Union[tuple, list, str], separator: Optional[str] = None):
# 		if separator is not None:
# 			self.__separator = separator
#
# 		if value:
# 			if isinstance(value, str):
# 				value = value.split(self.__separator)
# 			if len(value) >= 2 and value[-2] == value[-1]:
# 				value.pop(-1)
# 		else:
# 			value = ()
#
# 		# super(Category, self).__init__(value)
#
# 	def isSubcategory(self, other: 'Category'):
# 		return str(other) in str(self)
#
# 	def __str__(self):
# 		return self.__separator.join(self)
#
# 	def __contains__(self, item):
# 		# item in subcategory of self:
# 		try:
# 			return self == item[:len(self)]
# 		except IndexError:
# 			return False
#
# 	@property
# 	def super(self):
# 		return Category(self[:-1])


class Category(str):
	super: 'Category'
	sub: set['Category']
	source: Optional[Any]

	def __init__(self, value: str, super: Optional['Category'] = None, sub: Optional['Category'] = None, source: Any = None):
		if '.' in value:
			split = value.index('.')
			value, sub = value[:split], value[split + 1:]
			self._sub = Category(sub, super=self)
		super().__init__(value)
		self.super = super
		self.sub = sub
		self.source = source

	def __eq__(self, other):
		if str.__eq__(other, '*') or str.__eq__(self, '*'):
			return True
		return str.__eq__(self, other)

	def __ne__(self, other):
		return not self == other

	def __hash__(self):
		return hash(str(self)) + hash(self.level)

	@cached_property
	def level(self) -> int:
		if self.super is None:
			return 0
		return self.super.level + 1

	@property
	def super(self):
		return self._super

	@super.setter
	def super(self, value):
		self._super = value
		clearCacheAttr(self, 'level')

	@property
	def sub(self) -> set['Category']:
		return self._sub

	@sub.setter
	def sub(self, value):
		self._sub.intersection_update(value)

	def removeSub(self, value):
		if isinstance(value, str):
			pass


class CategoryItem(tuple):
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
				valueArray.extend(i.group() for i in re.finditer(r"[\w|*]+", value, re.MULTILINE))
			else:
				valueArray.extend(value)
		source = tuple(source) if isinstance(source, list) else (source,)
		id = hash((*tuple(valueArray), *source))
		if id in cls.__existing__:
			return cls.__existing__[id]
		kwargs['id'] = id
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
		return any([str(item) == '*' for item in tuple(self)])

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
		if len(self) == 0:
			return ''
		elif len(self) == 1:
			return self[0]
		elif len(self) == 2:
			return self[1]
		else:
			name = str(self[1])
			for item in self[2:]:
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
			# log.warning('CategoryItem is empty')
			return '.'
		return f'\33[2m\33[35m{leading}.\33[1m\33[36m{key}\33[36m\33[0m'

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
			other = CategoryItem(other)
		if self.isRoot or other.isRoot:
			return False
		if self.hasWildcard or other.hasWildcard:
			return subsequenceCheck(list(self), list(other), strict=True)
		if self.source is not None and other.source is not None:
			return hash(self) == hash(other) and self.source == other.source
		return hash(self) == hash(other)

	def __add__(self, other):
		return CategoryItem([*self, *other])

	# 	if isinstance(other, str):
	# 		other = CategoryItem(other)
	# 	start = 0
	# 	m = min(len(self), len(other))
	# 	while (self and other) and start < m and self[start] == other[start]:
	# 		start += 1
	# 	other = other[start:]
	# 	trimmed = self[start:]
	# 	if not other:
	# 		final = trimmed
	# 	elif not trimmed:
	# 		final = other
	# 	else:
	# 		final = [*trimmed, *other]
	# # while final and final[0] == '*':
	# # 	final = final[1:]
	# return CategoryItem(final, self.__separator)

	# def __radd__(self, other):
	# 	if other is root or self is root:
	# 		value = CategoryItem((*root, *self))
	# 		while value[0] == '*':
	# 			value = value[1:]
	# 	return self.__add__(other)

	def __sub__(self, other):
		if self.isRoot:
			return other

		if isinstance(other, str):
			other = CategoryItem(other)
		if other.isRoot:
			return self

		start = 0
		for x, y in zip(self, other):
			if x == y or '*' in (x, y):
				start += 1
		return CategoryItem(self[start:], separator=self.__separator)

	def __and__(self, other):
		if isinstance(other, str):
			other = CategoryItem(other)
		if other.isRoot:
			return self[0]
		value = [x for x, y in zip(self, other) if x == y or '*' in (x, y)]
		return CategoryItem(value, separator=self.__separator)
		end = 0
		m = min(len(self), len(other)) - 1
		value = list(self)
		otherValue = list(other)
		newValue
		while (self and other) and end < m and self[end] == other[end] or (self[end] == '*' or other[end] == '*'):
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

	def toJSON(self):
		return str(self)


root = CategoryItem(':')


class CategoryDict(dict):
	_cache = {}

	def __init__(self, parent: dict = None, source: dict = None, category: str = None):
		self._parent = parent
		# if not isinstance(parent, CategoryDict) and hasattr(self._parent, 'signals'):
		# 	for action in self._parent.signals._values():
		# 		action.added.connect(self.keyAdded)
		self._category = CategoryItem(category)
		self._source = source
		for k in [i for i in source.keys() if not isinstance(i, CategoryItem)]:
			source[CategoryItem(k)] = source.pop(k)

	# toConvert = {key for key in self._source.keys() if isinstance(key, str) and '.' in key}
	# for key in toConvert:
	# 	self._source[CategoryItem(key)] = self._source.pop(key)

	@Slot(dict)
	def keyAdded(self, value: 'Container'):
		key = value.key

	# self._dict[key]

	def refresh(self):
		clearCacheAttr(self, '_dict')
		clearCacheAttr(self, '_keys')
		clearCacheAttr(self, 'flatDict')

	# for value in self._values():
	# 	if isinstance(value, CategoryDict):
	# 		value.refresh()

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

	# def __repr__(self):
	# 	return dict.__repr__(self._source)

	def __len__(self):
		return len(self._dict)

	@cached_property
	def level(self):
		if not isinstance(self._parent, CategoryDict):
			return 0
		return self._parent.level + 1

	# try:
	# 	self[item[0]][str(item - item[0])]
	# except KeyError:
	# 	return self[item[0]][item - item[0]]

	# else:
	# 	raise KeyError(item)

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

	def update(self, values: dict):
		values = {CategoryItem(k): UnitMetaData(k, v) if isinstance(v, dict) else v for k, v in values.items()}
		# for key, value in _values.items():
		# 	if isinstance(value, UnitMetaData):
		# 		pass
		# 	elif isinstance(value, dict):
		# 		_values[key] = UnitMetaData(key, value)
		# 	else:
		# 		pass
		super(CategoryDict, self).update(values)

	def __contains__(self, item):
		if not isinstance(item, CategoryItem):
			item = CategoryItem(item)
		return item in super(CategoryDict, self).keys() or item in (keys := self.keys()) or any(item in self.category + key for key in keys)

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

	def subValues(self, level: int = None):
		if level is None:
			return self.flatDict.values()
		level = self.level + level
		return [v for k, v in self.flatDict.items() if len(k) == level]

	def subItems(self, level: int = None):
		if level is None:
			return self.flatDict.items()
		level = self.level + level
		return [(k, v) for k, v in self.flatDict.items() if len(k) == level]

	def subKeys(self, level: int = None):
		if level is None:
			return self.flatDict.keys()
		level = self.level + level
		return [k for k, v in self.flatDict.items() if len(k) == level]

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
			values = {k / category if category.hasWildcard else k: v for k, v in values.items() if k in self.category}
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
		if len(item) == 1:

			items = {key: value for key, value in dict.items(self) if key in self.category + item}
			if len(items) == 1:
				return items.popitem()[1]
			elif len(items) == 0:
				items = {key: value for key, value in dict.items(self) if self.category in key}
				if len(items) == 1:
					return items.popitem()[1][str(item)]
				if len(items) == 0:
					raise KeyError(item)
				return SubCategory(self, items, item)
			else:
				return SubCategory(self, items, item)
		else:
			value = self._dict[item - self.category]
			return value
			if isinstance(value, SubCategory):
				return value
			else:
				return value[item[1]]

	@property
	def category(self):
		if self._parent is not None and self._parent.category is not None and str(self._parent.category) != '*':
			return self._parent.category + self._category
		else:
			return self._category
		return None


class ValueNotFound(Exception):
	pass


if __name__ == '__main__':
	from src.observations.weatherFlow import unitDefinitions as ud

	A = ud
	a = CategoryDict(A)
	b = a['time.time']
	b = a['time']._dict
	print(a)
