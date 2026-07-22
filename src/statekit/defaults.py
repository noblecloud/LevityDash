"""Default-value wrappers and the source-type enum used by StateProperty.

Pure Python - no Qt, no LevityDash-domain imports.
"""
from copy import copy
from difflib import get_close_matches
from enum import Enum
from typing import Any, ClassVar, Final, Generic, Hashable, Literal, Type, TypeVar
from warnings import warn

# Explicit class tuple: Python 3.14 keeps a literal `None` in
# TypeVar.__constraints__ (3.11 coerced it to NoneType), which breaks the
# issubclass() check in DefaultMeta below - so drive that check off this tuple
# (which uses type(None)) rather than off __constraints__.
_DEFAULT_TYPES = (str, int, float, bool, type(None), dict, list, tuple, set, frozenset)
DefaultType = TypeVar("DefaultType", *_DEFAULT_TYPES)

DefaultNone: Final[DefaultType] = None
DefaultTrue: Final[DefaultType] = True
DefaultFalse: Final[DefaultType] = False


def isA(t: Type[Any] | str, value: Any) -> bool:
	if isinstance(t, str):
		typestr = type(value).__name__.casefold()
		return t.casefold() in typestr or get_close_matches(typestr, [t.casefold()], cutoff=0.8)
	return isinstance(value, t)


__builtins__["isA"] = isA


class SourceType(Enum):
	Default = "default"
	Factory = "factory"
	ItemDefault = "item_default"
	UserConfig = "user_config"
	Shared = "shared"


class DefaultMeta(type):
	def __new__(mcs, name, bases, attrs, **kwargs):
		subType = next((i for i in bases if issubclass(i, _DEFAULT_TYPES)), object)
		attrs["__subtype__"] = subType
		return super().__new__(mcs, name, bases, attrs)


class Default(Generic[DefaultType], metaclass=DefaultMeta):
	__subtype__: ClassVar[Type[Any]]

	def __new__(cls, value, **kwargs):
		if cls is Default:
			match value:
				case dict(value):
					return DefaultDict.__new__(DefaultDict, value)
				case list(value):
					return DefaultList.__new__(DefaultList, value)
				case set(value):
					return DefaultSet.__new__(DefaultSet, value)
				case tuple(value):
					return DefaultTuple.__new__(DefaultTuple, value)
				case str(value):
					return DefaultString.__new__(DefaultString, value)
				# bool must come before int - bool is an int subclass, so
				# `case int(value)` would otherwise always match first and
				# this branch would be unreachable dead code.
				case bool(value):
					return DefaultTrue if value else DefaultFalse
				case int(value):
					return DefaultInt.__new__(DefaultInt, value)
				case float(value):
					return DefaultFloat.__new__(DefaultFloat, value)
				case None:
					return DefaultNone
				case _:
					return DefaultValue.__new__(DefaultValue, value, **kwargs)
		else:
			return getattr(cls, "__subtype__", cls).__new__(cls, value, **kwargs)

	def __set__(self, instance, value):
		if isinstance(value, self.__subtype__):
			self.__value = value
		else:
			raise TypeError(f"{self.__subtype__} expected")

	def __get__(self, instance, owner):
		return copy(self)


class DefaultDict(Default, dict):
	pass


class DefaultState(Default, dict):
	def __getitem__(self, item):
		item = super().__getitem__(item)
		try:
			return copy(item)
		except TypeError:
			warn(f"{item} was accessed from a DefaultState, but is not a copyable type! There will be dragons!")
			return item


class DefaultList(Default, list):
	pass


class DefaultTuple(Default, tuple):
	pass


class DefaultSet(Default, set):
	pass


class DefaultString(Default, str):
	pass


class DefaultInt(Default, int):
	pass


class DefaultFloat(Default, float):
	pass


class DefaultValue(Default):
	__slots__ = "value"

	def __init__(self, value: Any):
		self.value = value

	def __getattr__(self, item):
		return getattr(self.value, item)


class DefaultGroup:
	def __init__(self, *values):
		try:
			values = set(values)
		except TypeError:
			pass
		self.values = values

	def __eq__(self, other):
		if isinstance(other, Hashable):
			return other in self.values
		return other in list(self.values)

	def __contains__(self, item):
		return item in self.values

	def __iter__(self):
		return iter(self.values)

	def __repr__(self):
		return self.values.__repr__()

	def __rich_repr__(self):
		for i in self.values:
			yield i

	@property
	def value(self) -> Any:
		value = next((i for i in self.values if i is not None), None)
		try:
			value = copy(value)
		except TypeError:
			warn(f"A default value was requested but is not a copyable type! There will be dragons!")
		return value

	@property
	def types(self):
		return set(type(i) for i in self.values)


UnsetDefault: Final = Literal["UnsetDefault"]
UnsetExisting: Final = Literal["UnsetExisting"]
