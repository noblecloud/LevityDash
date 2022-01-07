from copy import copy, deepcopy
from datetime import datetime
from functools import cached_property
from typing import Any, Optional, Union

from PySide2.QtCore import QObject, Signal

from src.utils import clearCacheAttr


class KeyCategory:
	key: str
	category: list[str]

	def __init__(self, key: str, category: str):
		self.key = key
		self.category = category.split('.')

	def __eq__(self, other):
		return self.key == other.key and self.category == other.category

	def findShared(self, other):
		if isinstance(other, str):
			other = other.split('.')
		elif isinstance(other, list):
			pass
		elif isinstance(other, KeyCategory):
			other = other.category.copy()

		own = self.category.copy()
		shared = None
		while own[0] == other[0]:
			shared = own[0]
			own.pop(0)
			other.pop(0)

		return shared

	def inSubcategory(self, subcategory: str):
		if isinstance(subcategory, str):
			subcategory = subcategory.split('.')
		return subcategory == self.category[:len(subcategory)] or self.category[:len(subcategory)] == subcategory


class UnitMetaData(dict):

	def __init__(self, key: str, value):
		super(UnitMetaData, self).__init__(value)
		self['key'] = key

	def __repr__(self):
		return self['sourceKey']

	def __hash__(self):
		return hash(self['sourceKey'])

	@property
	def title(self):
		return self.get('title', None)

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
		return self.get('unit', None)

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


class CategoryItem(tuple):
	__separator: str = '.'

	def __new__(cls, value: Union[tuple, list, str], separator: Optional[str] = None):
		if separator is not None:
			cls.__separator = separator
		if isinstance(value, str):
			value = value.split(cls.__separator)
		value = list(value)
		# while value and not value[0] and value is not root:
		# 	value.pop(0)
		while value and not value[-1]:
			value.pop(-1)
		# if not value:
		# 	raise ValueError('CategoryItem must not be empty')
		return super(CategoryItem, cls).__new__(cls, value)

	# def __init__(self, value: Union[tuple, list, str], separator: Optional[str] = None):

	def __hash__(self):
		return hash(self.__separator.join(self))

	def __str__(self):
		return self.__separator.join(self)

	def __repr__(self):
		return f'{self.__class__.__name__}({self.__separator.join(self)})'.lstrip('root')

	def __contains__(self, item):
		# item in subcategory of self:
		try:
			return self == item[:len(self)]
		except IndexError:
			return False

	def __add__(self, other):
		if other is root:
			return CategoryItem((*root, *self))
		if self is root:
			return CategoryItem((*root, *other))
		if isinstance(other, str):
			other = CategoryItem(other)
		start = 0
		m = min(len(self), len(other))
		while (self and other) and start < m and self[start] == other[start]:
			start += 1
		other = other[start:]
		trimmed = self[start:]
		if not other:
			final = trimmed
		elif not trimmed:
			final = other
		else:
			final = trimmed + other
		return CategoryItem(final)

	def __radd__(self, other):
		if other is root:
			return CategoryItem((*root, *self))
		if self is root:
			return CategoryItem((*root, *other))
		return self.__add__(other)

	def __sub__(self, other):
		if other is root:
			return self
		if self is root:
			return other
		if isinstance(other, str):
			other = CategoryItem(other)
		end = 0
		m = min(len(self), len(other))
		while (self and other) and end < m and self[end] == other[end]:
			end += 1
		return CategoryItem(self[end:])

	def __and__(self, other):
		if isinstance(other, str):
			other = CategoryItem(other)
		end = 1
		m = min(len(self), len(other))
		while (self and other) and end < m and self[end] == other[end]:
			end += 1
		return CategoryItem(self[:end])


root = CategoryItem('root')


class ValueWrapper(QObject):
	value: Any
	_value: Any = None
	key: str
	unit: str
	category: str
	timestamp: datetime
	title: str
	valueChanged = Signal(dict)

	def __init__(self, value: Any, key: str = None, **kwargs):
		"""
		:param value: The value to wrap
		:type value: Any
		:param key: The key of the value
		:type key: str
		:Keyword Arguments:
        * *unit* (``str``) --
          Unit of measurement
        * *category* (``Category | str``) --
          Category of measurement
				* *timestamp* (``datetime.datetime``) --
				  Timestamp of measurement
				* *title* (``str``) --
				  Title of measurement
				* *metaData* (``UnitMetaData``) --
				  Metadata of measurement
				* *description* (``str``) --
				  Description of measurement
		"""
		super(ValueWrapper, self).__init__()

		unit = kwargs.get('unit', None)
		metaData = kwargs.get('metaData', None)
		category = kwargs.get('category', None)
		title = kwargs.get('title', None)
		timestamp = kwargs.get('timestamp', None)
		description = kwargs.get('description', None)
		if metaData:
			unit = metaData.unit if metaData.unit is not None else unit
			key = metaData.key if metaData.key is not None else key
			title = metaData.title if metaData.title is not None else title
			category = metaData.category if metaData.category is not None else category
			description = metaData.description if metaData.description is not None else None
		self.key = key
		self.unit = unit
		self.category = category
		self.timestamp = timestamp
		self.title = title
		self.description = description
		self.value = value

	@property
	def value(self):
		return QObject.__getattribute__(self, '_value')

	@value.setter
	def value(self, value):
		if value != self._value:
			self._value = value
			self.valueChanged.emit(self.toDict())

	def toDict(self):
		return {
			'value':       self.value,
			'key':         self.key,
			'unit':        self.unit,
			'category':    self.category,
			'timestamp':   self.timestamp,
			'title':       self.title,
			'description': self.description
		}

	def __getattr__(self, item):
		if item == '_value':
			return QObject.__getattribute__(self, '_value')
		if hasattr(self.value, item):
			value = super(ValueWrapper, self).__getattr__('value')
			attr = getattr(value, item)
			if attr is not None:
				return attr
		return super(ValueWrapper, self).__getattr__(item)

	def __str__(self):
		return str(self.value)

	def __repr__(self):
		return str(self.value)

	def __add__(self, other):
		return ValueWrapper(value=self.value + other, key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __sub__(self, other):
		return ValueWrapper(value=self.value - other, key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __mul__(self, other):
		return ValueWrapper(value=self.value + other, key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __truediv__(self, other):
		return ValueWrapper(value=self.value / other, key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __floordiv__(self, other):
		return ValueWrapper(value=self.value // other, key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __mod__(self, other):
		return ValueWrapper(value=self.value % other, key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __pow__(self, other):
		return ValueWrapper(value=self.value ** other, key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __neg__(self):
		return ValueWrapper(value=-self.value, key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __pos__(self):
		return ValueWrapper(value=+self.value, key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __abs__(self):
		return ValueWrapper(value=abs(self.value), key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __invert__(self):
		return self.value.__invert__()

	def __lt__(self, other):
		self.value.__lt__(other)

	def __le__(self, other):
		self.value.__le__(other)

	def __eq__(self, other):
		self.value.__eq__(other)

	def __ne__(self, other):
		self.value.__ne__(other)

	def __gt__(self, other):
		self.value.__gt__(other)

	def __ge__(self, other):
		self.value.__ge__(other)

	def __and__(self, other):
		self.value.__and__(other)

	def __or__(self, other):
		self.value.__or__(other)

	def __xor__(self, other):
		self.value.__xor__(other)

	def __lshift__(self, other):
		self.value.__lshift__(other)

	def __rshift__(self, other):
		self.value.__rshift__(other)

	def __radd__(self, other):
		return ValueWrapper(value=other + self.value, key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __rsub__(self, other):
		return ValueWrapper(value=other - self.value, key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __rmul__(self, other):
		return ValueWrapper(value=other * self.value, key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __rtruediv__(self, other):
		return ValueWrapper(value=other / self.value, key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __rfloordiv__(self, other):
		return ValueWrapper(value=other // self.value, key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __rmod__(self, other):
		return ValueWrapper(value=other % self.value, key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __rpow__(self, other):
		return ValueWrapper(value=other ** self.value, key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __rlshift__(self, other):
		return ValueWrapper(value=other << self.value, key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __rrshift__(self, other):
		return ValueWrapper(value=other >> self.value, key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __iadd__(self, other):
		self.value += other
		return self

	def __isub__(self, other):
		self.value -= other
		return self

	def __imul__(self, other):
		self.value *= other
		return self

	def __itruediv__(self, other):
		self.value /= other
		return self

	def __ifloordiv__(self, other):
		self.value //= other
		return self

	def __imod__(self, other):
		self.value %= other
		return self

	def __ipow__(self, other):
		self.value **= other
		return self

	def __ilshift__(self, other):
		self.value <<= other
		return self

	def __irshift__(self, other):
		self.value >>= other
		return self

	def __iand__(self, other):
		self.value &= other
		return self

	def __ior__(self, other):
		self.value |= other
		return self

	def __ixor__(self, other):
		self.value ^= other
		return self

	# def __getitem__(self, key):
	# 	return self._value[key]
	#
	# def __setitem__(self, key, _value):
	# 	self._value[key] = _value
	#
	# def __delitem__(self, key):
	# 	del self._value[key]

	def __len__(self):
		return len(self.value)

	def __contains__(self, item):
		return item in self.value

	def __iter__(self):
		return iter(self.value)

	def __reversed__(self):
		return reversed(self.value)

	def __repr__(self):
		return repr(self.value)

	def __str__(self):
		return str(self.value)

	def __format__(self, format_spec):
		return format(self.value, format_spec)

	def __copy__(self):
		return ValueWrapper(value=copy(self.value), key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __deepcopy__(self, memo):
		return ValueWrapper(value=deepcopy(self.value, memo), key=self.key, unit=self.unit, category=self.category, timestamp=self.timestamp, title=self.title)

	def __reduce__(self):
		return ValueWrapper, (self.value, self.key, self.unit, self.category, self.timestamp, self.title)

	def __getstate__(self):
		return self.value, self.key, self.unit, self.category, self.timestamp, self.title

	def __setstate__(self, state):
		self.value, self.key, self.unit, self.category, self.timestamp, self.title = state


class CategoryDict(dict):

	def __init__(self, values: dict = None, category: str = None):
		self._parent = None
		self._category = category

		if values:
			self.update(values)

	def __getitem__(self, item):
		if not isinstance(item, CategoryItem):
			item = CategoryItem(item)
		try:
			return super(CategoryDict, self).__getitem__(item)
		except KeyError:
			pass
		if len(item) == 1:
			items = {key: value for key, value in dict.items(self) if key in item}
			if len(items) == 1:
				return items.popitem()[1]
			else:
				return SubCategory(self, items, item)
			# return self._dict[item]
			# if item in self:
			return SubCategory(self, item)
		else:
			value = self[item[0]]
			if len(item) > 2:
				return value[item[1]][item[2:]]
			if isinstance(item, SubCategory):
				return value[item - item[0]]
			else:
				return value[item[1]]
		# try:
		# 	self[item[0]][str(item - item[0])]
		# except KeyError:
		# 	return self[item[0]][item - item[0]]

	# else:
	# 	raise KeyError(item)

	def __setitem__(self, key, value):
		if not isinstance(key, CategoryItem):
			key = root + CategoryItem(key)
		super(CategoryDict, self).__setitem__(key, value)
		clearCacheAttr(self, '_keys')

	def update(self, values: dict):
		values = {CategoryItem(k): UnitMetaData(k, v) if isinstance(v, dict) else v for k, v in values.items()}
		# for key, value in values.items():
		# 	if isinstance(value, UnitMetaData):
		# 		pass
		# 	elif isinstance(value, dict):
		# 		values[key] = UnitMetaData(key, value)
		# 	else:
		# 		pass
		super(CategoryDict, self).update(values)

	def __contains__(self, item):
		if not isinstance(item, CategoryItem):
			item = CategoryItem(item)
		return item in super(CategoryDict, self).keys() or item in (keys := self.keys()) or any(item in key for key in keys)

	@property
	def category(self) -> CategoryItem:
		return tuple()

	@cached_property
	def _keys(self):
		return {self.category + CategoryItem(b[0]) for b in super(CategoryDict, self).keys()}

	@cached_property
	def _dict(self):
		cats = {str(k): [] for k in self._keys}
		for key, value in dict.items(self):
			newKey = key - self.category
			cats[newKey[0]].append(key)
		cats2 = {}
		for key, value in cats.items():
			key = CategoryItem(key)
			if any(isinstance(v, CategoryItem) for v in value):
				values = {k: self[k] for k in cats[str(key)]}
				cats2[key] = SubCategory(self, values, key)
			else:
				cats2[key] = value
		return cats2

	@property
	def parent(self):
		return self._parent

	def keys(self, subitems: bool = False):
		if subitems:
			return dict.keys(self)
		return self._dict.keys()

	def items(self, subitems: bool = False):
		if subitems:
			return dict.items(self)
		return self._dict.items()

	def values(self, subitems: bool = False):
		if subitems:
			return dict.values(self)
		return self._dict.values()


class SubCategory(CategoryDict):

	def __init__(self, parent, values, category: str):
		self._parent = parent
		self._category = category
		dict.__init__(self, values)

	@cached_property
	def _dict(self) -> dict:
		keys = {(b - self.category)[0] for b in dict.keys(self)}
		cats = {str(k): [] for k in keys}
		for key, value in dict.items(self):
			newKey = key - self.category
			cats[newKey[0]].append(key)
		cats2 = {}
		raw = dict(self)
		for key, value in cats.items():
			key = CategoryItem(key)
			if len(value) == 1:
				cats2[key] = raw[value[0]]
			elif any(isinstance(v, CategoryItem) for v in value):
				values = {k: raw[k] for k in cats[str(key)]}
				cats2[key] = SubCategory(self, values, key)
			else:
				cats2[key] = value
		return cats2

	def __repr__(self):
		return f'SubCategory({self.keys()})'

	def __getitem__(self, item):
		if not isinstance(item, CategoryItem):
			item = CategoryItem(item)
		try:
			return dict.__getitem__(self, item)
		except KeyError:
			pass
		if len(item) == 1:
			items = {key: value for key, value in dict.items(self) if key in self.category + item}
			if len(items) == 1:
				return items.popitem()[1]
			elif len(items) == 0:
				items = {key: value for key, value in dict.items(self) if key in self.category + self._category}
				if len(items) == 1:
					return items.popitem()[1][str(item)]
				if len(items) == 0:
					raise KeyError(item)
				return SubCategory(self, items, item)
			else:
				return SubCategory(self, items, item)
		else:
			value = self[item[0]]
			if isinstance(item, SubCategory):
				return value[item - item[0]]
			else:
				return value[item[1]]

	@property
	def category(self):
		if self._parent is not None and self._parent.category is not None:
			return self._parent.category + self._category
		else:
			return self._category
		return None


class ValueNotFound(Exception):
	pass
