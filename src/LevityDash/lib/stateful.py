import inspect
import os
from abc import abstractmethod
from collections import ChainMap
from collections.abc import MutableSequence
from contextlib import contextmanager
from copy import copy, deepcopy
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from functools import lru_cache, cached_property, partial
from inspect import Traceback, getframeinfo, getsource, getsourcefile, getsourcelines, get_annotations
from operator import attrgetter
from shutil import get_terminal_size
from tempfile import TemporaryFile
from traceback import extract_stack
from types import SimpleNamespace, GenericAlias, UnionType
from typing import (
	Any,
	ClassVar,
	Type,
	Callable,
	Dict,
	Sized,
	Set,
	List,
	Tuple,
	Mapping,
	Final,
	Literal,
	TypeAlias, TypeVar,
	Generic,
	Iterable,
	Union,
	get_args,
	get_origin,
	get_type_hints,
	_GenericAlias,
	_UnionGenericAlias, Text, Sequence, Hashable,
)
from re import search
from warnings import warn, warn_explicit
from builtins import isinstance
from sys import _getframe as getframe

import yaml
from PySide2.QtCore import QObject, QThread
from rich.panel import Panel
from yaml import SafeDumper, Dumper, ScalarNode, MappingNode
from yaml.composer import Composer
from yaml.constructor import SafeConstructor
from rich.syntax import Syntax
from rich.pretty import Pretty
from rich.console import Console, Group
from rich.repr import auto as auto_rich_repr
from yaml.parser import Parser
from yaml.reader import Reader
from yaml.resolver import Resolver
from yaml.scanner import Scanner
from difflib import get_close_matches

from LevityDash.lib.log import LevityLogger, debug
from LevityDash.lib.utils import Unset, get, OrUnset, levenshtein
from LevityDash.lib.utils.shared import (
	_Panel, ActionPool, clearCacheAttr, DotDict, DeepChainMap, ExecThread, OrderedSet,
	recursiveRemove, sortDict, guarded_cached_property
)
from LevityDash.lib.plugins.categories import CategoryItem

STATEFUL_DEBUG = int(os.environ.get("STATEFUL_DEBUG", 0))

console = Console(
	soft_wrap=True,
	tab_size=2,
	no_color=False,
	force_terminal=True,
	width=get_terminal_size((100, 20)).columns - 5,
	log_time_format="%H:%M:%S",
)

log = LevityLogger.getChild("Cerial")

DefaultType = TypeVar("DefaultType", str, int, float, bool, None, dict, list, tuple, set, frozenset)

DefaultNone: Final[DefaultType] = None
DefaultTrue: Final[DefaultType] = True
DefaultFalse: Final[DefaultType] = False

def isA(t: Type[Any] | str, value: Any) -> bool:
	if isinstance(t, str):
		typestr = type(value).__name__.casefold()
		return t.casefold() in typestr or get_close_matches(typestr, [t.casefold()], cutoff=0.8)
	return isinstance(value, t)

__builtins__["isA"] = isA

class DefaultMeta(type):
	def __new__(mcs, name, bases, attrs, **kwargs):
		subType = next((i for i in bases if issubclass(i, DefaultType.__constraints__)), object)
		attrs["__subtype__"] = subType
		return super().__new__(mcs, name, bases, attrs)


class Default(Generic[DefaultType], metaclass=DefaultMeta):
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
				case int(value):
					return DefaultInt.__new__(DefaultInt, value)
				case float(value):
					return DefaultFloat.__new__(DefaultFloat, value)
				case bool(value):
					return DefaultTrue if value else DefaultFalse
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


class TypedIterable(type):

	__subtype__: Type[Any]

	def __subclasscheck__(self, subclass: _GenericAlias):
		if isinstance(subclass, (GenericAlias, _GenericAlias)):
			return issubclass(subclass, Iterable) and issubclass(subclass[0], self.__subtype__)
		return any(issubclass(s, self.__subtype__) for s in subclass.__args__)

	def __instancecheck__(self, instance):
		if isinstance(instance, str) or not isinstance(instance, Iterable):
			return False
		try:
			return all(isinstance(i, self.__subtype__) for i in instance)
		except TypeError:
			return isinstance(instance, self.__subtype__)

	def __repr__(cls):
		return f"TypedIterable[{cls.__subtype__}]"


def makeTypedIterable(subtype: Type[Any]) -> Type[Any]:
	if isinstance(subtype, (GenericAlias, _GenericAlias)):
		subtype = subtype.__args__
	return TypedIterable("TypedIterable", (), {"__subtype__": subtype})



def tryAndLog(func):
	def wrapper(*args, **kwargs):
		try:
			return func(*args, **kwargs)
		except Exception as e:
			log.error(f"{func.__name__} failed with {e}")
			log.exception(e)

	return wrapper


_typeCache = {}


def makeType(*args, **kwargs):
	global _typeCache
	name, bases, attrs = args
	if cls := _typeCache.get(name, None):
		for key, value in ((k, v) for k, v in attrs.items() if k not in cls.__dict__):
			setattr(cls, key, value)
	else:
		log.verbose(f"Creating type {name}", verbosity=5)
		_typeCache[name] = type(name, bases, attrs, **kwargs)
	return _typeCache[name]


@lru_cache(maxsize=8)
def ownerParentClass(ownerName, frame=None):
	for f_info, _frame in FrameIterator(frame):
		if context := getattr(f_info, "code_context", None):
			contextString = "\n".join(context)
			if result := search(rf"(?<=class {ownerName}\().*(?=\):)\n?", contextString):
				result = result.group().split(",")
				for item in (i.strip() for i in result):
					if item.count("[") == item.count("]") != 0:
						# This isn't ideal...  This whole thing needs to be reworked, I'm sure there is a better way to do this
						item = eval(item, _frame.f_locals)
						if issubclass(item, Stateful):
							return item
					if item != "Stateful" and item in _frame.f_locals:
						return _frame.f_locals[item]
	return object


class FrameIterator:
	def __init__(self, frame=None, info: bool = True):
		self.level = 0
		self.info = info
		self.frame = frame or getframe(1)

	def __iter__(self):
		return self

	def __next__(self) -> tuple[Traceback, object]:
		self.level += 1
		if self.level > 10:
			raise StopIteration
		self.frame = self.frame.f_back
		if self.info:
			return getframeinfo(self.frame), self.frame
		return self.frame


class Conditions(list):
	def __init__(self, prop):
		self.prop: StateProperty = prop
		super().__init__()

	def prettyPrint(self):
		funcs = [getsource(i["func"]).split("\n") for i in self]
		funcs = [i.replace("\t", "", 1) for j in funcs for i in j]

		funcs = [getsource(i["func"]) for i in self]
		v = f"\n".join(funcs)
		tabCount = min(i.count("\t") if "\t" in i else 100 for i in v)
		v = Syntax(v, "python")
		with console.capture() as captured:
			title = getsource(self.prop.owningClass).split("\n")[0] + "\n\t..."
			console.print(
				Syntax(
					title,
					"python",
					dedent=True,
					tab_size=2,
					line_numbers=True,
					start_line=getsourcelines(self.prop.owningClass)[1],
				)
			)
			for i in self:
				func = i["func"]
				v = getsource(func).strip("\n")
				v = Syntax(v, "python", tab_size=2, line_numbers=True, start_line=getsourcelines(func)[1])
				console.print(v, "\n")
		g = captured.get().replace("\n\n", "\n")
		return g

	def __repr__(self):
		return repr([getsource(i["func"]).split("\n")[-2].strip("\t") for i in self])


class SingletonConstant(_GenericAlias, _root=True):
	__instances__: ClassVar[Set['SingletonConstant']] = set()
	__slots__ = ("_name",)

	def __new__(cls, name: str = None):
		if name is None:
			_, _, _, text = extract_stack()[-2]
			name = text[:text.find('=')].strip().split(':')[0].strip()
		if name in cls.__instances__:
			raise ValueError(f"SingletonConstant name {name!r} is already in use")
		self = super().__new__(cls)
		self._name = name
		cls.__instances__.add(self)
		return self

	def __subclasscheck__(self, subclass):
		if subclass is self:
			return True
		return False

	def __instancecheck__(self, instance):
		if instance is self:
			return True
		return False

	def __init__(self, name: str = None):
		super().__init__(self, ())

	def __repr__(self):
		return self._name

	def __hash__(self):
		return hash(self._name)


ForcedSingleVal = Literal["force"]
StateAction = Literal["get", "set"]
UnsetReturn: Final = Literal["UnsetReturn"]
_T = TypeVar("_T", bound=type)

_Parse_Return_Type = Union[_T, Type | TypedIterable | Iterable[_T]]
Parse_Return_Type: TypeAlias = _Parse_Return_Type[_Parse_Return_Type[_Parse_Return_Type]]


class InvalidArguments(SyntaxError):
	pass

existingFsetCount = 0



class StateProperty(property):
	__owner__: ClassVar[Type]
	__ownerParentClass__: ClassVar[Type]
	_set: Callable[[Any, Any], None] | None
	_get: Callable[[Any], Any] | None
	_del: Callable[[Any], None] | None
	__state: Callable[[Any], Any] | None
	__options: DotDict
	__existingValues__: ClassVar[Dict[str, Any]]
	__alternate_keys__: ClassVar[Dict[str, "StateProperty"]] = {}
	doc: str | None
	thread: QThread | None = None

	__instances__: ClassVar[DotDict] = DotDict()

	def __varifyKwargs(self, kwargs):
		incorrect = []

		if not kwargs.get("allowNone", True) and ("default" not in kwargs or self.default(type(self)) is UnsetDefault):
			log.critical(f"{self.__class__.__name__} {self.name} has no default value and allowNone is False")
			incorrect.append("- allowNone without default")

		if sort := kwargs.get("sort", False) and not self._varifyReturnType(Iterable):
			log.critical(f"{self.__class__.__name__} {self.name} cannot be sorted because it returns a non-iterable")
			incorrect.append("- sort without iterable return")

		default = kwargs.get("default", UnsetDefault)
		# if self.isStatefulReference and isinstance(default, Mapping):
		# 	pass
		if default is not Unset and default is not UnsetDefault and not isinstance(default, type):
			if (accepts := self.accepts) is not Unset:
				try:
					accepts = isinstance(default, accepts)
				except TypeError:
					accepts = False
			else:
				accepts = False
			if not isinstance(default, DefaultGroup) and not accepts:
				if not self._varifyReturnType(type(default)):
					acceptedTypesString = '\n - '.join([i.__name__ for i in self.returns])
					log.critical(
						f"{inspect.getsourcefile(self.fget)}:{inspect.getsourcelines(self.fget)[1]}\n"
						f"{self!r} has a default value {type(default).__name__}({default}) that is not of the correct type."
						f"\nAccepted types are:\n"
						f" - {acceptedTypesString}"
						f"\n"
					)

		# TODO: add support for default groups

		if incorrect:
			errors = "\n".join(incorrect)

	# raise InvalidArguments(f"{self.__class__.__name__} {self.name} has invalid arguments: \n{errors}")

	# Section StateProperty
	def __new__(cls, fget=None, **kwargs):
		if kwargs and fget is None:
			return partial(cls, **kwargs)

		global _typeCache

		attrs = {"__existingValues__": DotDict()}

		inheritFrom = kwargs.get("inheritFrom", None)
		if inheritFrom is not None:
			cls = type(inheritFrom)

		owner = kwargs.pop("owner", Unset)
		if owner is Unset:
			frame = getframe(1)
			ownerName = frame.f_locals["__qualname__"]
			attrs.update({"__owner__": ownerName, "__ownerParentClass__": ownerParentClass(ownerName, frame)})
			name = f"{ownerName}StateProperty"
		else:
			name = f"{owner.__name__}StateProperty"
			attrs.update(
				{"__owner__": owner.__name__, "__ownerClass__": owner, "__ownerParentClass__": owner.__bases__[0]}
			)
		try:
			cls = attrs['__ownerParentClass__'].__statePropertyClass__
		except AttributeError:
			pass
		except KeyError:
			pass

		cls = makeType(name, (cls,), attrs)

		if altKey := kwargs.pop("altKey", None):
			cls.__alternate_keys__[cls] = altKey
		prop = property.__new__(cls)
		prop.__pre_init__(fget, **kwargs)
		return prop

	def __pre_init__(self, fget=None, fset=None, fdel=None, doc=None, **kwargs):
		self._get = fget
		self._set = fset
		self._del = fdel
		self.doc = doc
		if (after := kwargs.pop("after", None)) is not None:
			if isinstance(after, Callable):
				kwargs["after.func"] = after
		if (encode := kwargs.pop("encoder", None)) is not None:
			if isinstance(encode, Callable):
				kwargs["encode.func"] = encode
		if (decode := kwargs.pop("decoder", None)) is not None:
			if isinstance(decode, Callable):
				kwargs["decode.func"] = decode
		self.optionsFromInit = DotDict(kwargs)
		self.__state = kwargs.pop("state", None)

	def __init__(self, fget=None, fset=None, fdel=None, **kwargs) -> None:
		"""
		Create a Stateful property with the given getter, setter, and deleter.

		Parameters
		----------
		:param fget: The function to use as the property's getter.
		:type fget: Callable[[Stateful], Any]
		:param fset: The function to use as the property's setter.
		:type fset: Callable[[Stateful, Any], None]
		:param fdel: The function to use as the property's deleter.
		:type fdel: Callable[[Stateful], None]

		Keyword Arguments
		-----------------
		:keyword doc: the docstring for the property
		:type doc str:
		:keyword key: the key to use for the property in the item's state
		:type key str:
		:keyword default: the default value to use if the property is not set
		:type default Any:
		:keyword allowNone: Whether to allow the property to have no Value
		:type allowNone bool:
		:keyword sort: Whether to sort the property's value when it is returned
		:type sort bool | Callable[[Any] int] | str:
		:keyword singleValue: When set to true, and it is the only value within the generated state, it will be returned as a single value instead of a dict.	If the set to 'force', it will always be returned as a single value
		:type singleValue bool: | ForcedSingleVal
		:keyword match: When true, the value is included in the classes __match_args__
		:type match bool:
		:keyword sortOrder: The position the property should be in the generated state
		:type sortOrder int:
		:keyword inheritFrom: A Stateful class or object to inherit from
		:type inheritFrom Stateful | Type[Stateful]
		:keyword actions: A set of strings that tell the property to be included in the item's state
		:type actions set[StateAction]
		:keyword unwrap: When true, the property will be unwrapped from the item's state
		:type unwrap bool:
		:keyword extend: When true, the value's state will be included in the item's state instead of the value itself
		:type extend bool:
		:keyword repr: Include the value in the repr of the item
		:type repr bool:
		:keyword dependencies: A set of other keys that the value depends on being already set
		:type dependencies set[str]

		:return: None
		:rtype: NoneType
		"""
		super().__init__()
		self.__preGetter(fget, fset=fset, fdel=fdel, **kwargs)

	def __call__(self, fget=None, **kwargs) -> property:
		self.__preGetter(fget, **kwargs)
		return self

	def __set_name__(self, owner, name):
		self._name_ = name

	# Section .__repr__
	def __repr__(self):
		owner = type(self).__owner__
		return f"@{owner}.{self.key}"

	def __rich_repr__(self):
		yield self.__repr__()
		if self.key != self.name:
			yield "key", self.key
		yield "returns", self.returns[0] if len(self.returns) == 1 else list(self.returns)
		# yield "options", self.options

	# Section .__get__
	def __get__(self, obj, objtype=None):
		if obj is None:
			return self
		if self.fget is None:
			raise AttributeError("unreadable attribute")
		try:
			return self.fget(obj)
		except AttributeError as e:
			if (factory := self.__options.get("factory.func", None)) is not None:
				value = factory(obj)
				self.__existingValues__[self.cacheKey(obj)] = value
				self.fset(obj, value)
				try:
					value.__state_key__ = self
				except AttributeError:
					pass
				return value
			elif not self.allowNone:
				raise e
		return self.default(type(obj))

	@staticmethod
	def checkType(instance: Any, type_: Type | _GenericAlias | GenericAlias| _UnionGenericAlias):
		if type_ is UnsetReturn:
			return False
		if isinstance(type_, _UnionGenericAlias):
			return any(StateProperty.checkType(instance, t) for t in type_.__args__)
		if isinstance(type_, _GenericAlias | GenericAlias):
			origin = get_origin(type_)
			if issubclass(origin, Iterable):
				type_ = makeTypedIterable(type_)
			elif origin is type:
				type_ = get_args(type_)
				return isinstance(instance, type) and issubclass(instance, type_)
		try:
			return isinstance(instance, type_)
		except TypeError:
			return False

	def __decode__(self, obj, value):
		decoder = self.__options.get("decode", {})

		if not (decodeFunc := decoder.get("func", False)):
			return value

		message = f"Decoding {self.key} for {obj.__class__.__name__} from {type(value).__name__}"

		expectedType = get_type_hints(decodeFunc).get("return", Unset)
		if isinstance(expectedType, str):
			expectedType = None
		if not self.checkType(value, expectedType):
			existing = self.existing(obj)
			if existing is not UnsetExisting and isinstance(existing, Stateful):
				StateProperty.setItemState(existing, value)
				return existing

			parameters = decodeFunc.__code__.co_varnames[: decodeFunc.__code__.co_argcount]
			match parameters:
				case ["self", _]:
					value = decodeFunc(obj, value)
				case [var] if var != "self":
					value = decodeFunc(value)
				case var:
					raise NotImplementedError(var)
		message = f"{message} -> {type(value).__name__}"
		log.verbose(message, verbosity=5)
		return value

	# Section .__set__
	def __set__(self, owner, value, **kwargs):
		if (fset := self.fset) is None:
			raise AttributeError("can't set attribute")

		if isinstance(value, Default):
			if isinstance(value, DefaultValue):
				value = value.value
		elif value is None and not self.__options.get("allowNone", True):
			if "default" not in self.__options:
				raise AttributeError(f"{repr(self)} is not allowed to be None but no default was set")
			value = self.default(type(owner))
			try:
				value = copy(value)
			except TypeError as e:
				if STATEFUL_DEBUG:
					log.exception(e)
				warn(f"A default value was requested but is not a copyable type! There will be dragons!")

		if isinstance(value, DefaultGroup):
			value = value.value

		if self.conditions and not self.testConditions(value, owner, "set"):
			return

		value = self.__decode__(owner, value)

		if isinstance(value, Stateful):
			value.__state_key__ = self
			value.__statefulParent = owner

		self.fset(owner, value)

		self.__existingValues__.pop(self.cacheKey(owner), None)
		owner._set_state_items_.add(self.name)

		if after := self.__options.get("after", False):
			if (func := after.get("func", None)) is not None:
				if (pool := kwargs.get("afterPool", None)) is not None:
					if pool.instance is not owner:
						pool = pool.new(owner)
					log.verbose(f"Adding function to after pool", verbosity=5)
					pool.add(func)
				else:
					log.verbose(f"Executing after method for {owner}", verbosity=5)
					func(owner)

	# Section .__delete__
	def __delete__(self, obj):
		if self.fdel is None:
			raise AttributeError("can't delete attribute")
		self.fdel(obj)

	def __preGetter(self, func, **kwargs):
		if "match" in kwargs:
			self.optionsFromInit["match"] = kwargs.pop("match")
		self.getter(func, _kwargs=kwargs)

	def getter(self, fget, _kwargs: dict = None) -> property:
		if fget is None:
			return self
		elif fget is ...:
			fget = self.parentCls.fget
		clearCacheAttr(self, "fget")
		self._get = fget
		self.__doc__ = fget.__doc__

		options = getattr(self, "optionsFromInit", None)
		if options is None:
			options = self.__options

		if "type" not in options and "return" in fget.__annotations__:
			options["type"] = fget.__annotations__["return"]

		# self.__varifyKwargs(_kwargs)

		return self

	def __checkInheritance(self, func, method: str):
		if func is None:
			return func
		if func.__code__.co_code == b"d\x00S\x00":
			parent = getattr(self.__ownerParentClass__, func.__name__)
			match method:
				case "get":
					func = parent.fget
				case "set":
					func = parent.fset
				case "del":
					func = parent.fdel
				case "doc":
					func = parent.__doc__
				case "options":
					func = parent.__options
				case "key":
					func = parent.key
				case _:
					pass
		return func

	def setter(self, fset):
		clearCacheAttr(self, "fget")
		self._set = self.__checkInheritance(fset, "set")
		fset.__name__ = f'{fset.__name__}.setter'
		return self

	def deleter(self, fdel):
		clearCacheAttr(self, "fget")
		self._del = self.__checkInheritance(fdel, "del")
		return self

	def state(self, func):
		self.__state = func
		return self

	@cached_property
	def fget(self):
		func = self._get
		if func is None or func.__code__.co_code == b"d\x00S\x00":
			func = getattr(self.parentCls, "fget", None)
		if func is not None and "return" not in func.__annotations__:
			warn_explicit(
				f"\nThe return type of {self} is not set",
				filename=func.__code__.co_filename,
				module=func.__module__,
				lineno=func.__code__.co_firstlineno + 1,
				category=SyntaxWarning,
			)
		return func

	@cached_property
	def fset(self):
		func = self._set
		if func is None or func.__code__.co_code == b"d\x00S\x00":
			return getattr(self.parentCls, "fset", None)
		return self._set

	@cached_property
	def fdel(self):
		func = self._del
		if func is None or func.__code__.co_code == b"d\x00S\x00":
			return getattr(self.parentCls, "fdel", None)
		return self._del

	@cached_property
	def annotations(self):
		annotations = getattr(self.fget, "__annotations__", {})
		annotations.update(getattr(self._get, "__annotations__", {}))
		return annotations

	@property
	def owningClass(self):
		owncls = type(self)
		if not hasattr(owncls, "__ownerClass__"):
			classes = type(self).__ownerParentClass__.__subclasses__()
			for cls in classes:
				if cls.__name__ == type(self).__owner__:
					owncls.__ownerClass__ = cls
					break
			else:
				return object
		return owncls.__ownerClass__

	@property
	def parentCls(self):
		if parentClass := getattr(type(self), "__parentClass__", False):
			return parentClass
		if self.name:
			if hasattr(self, "__ownerParentClass__"):
				return getattr(type(self).__ownerParentClass__, self.name, Unset)
			if hasattr(self, "__ownerClass__"):
				self.__ownerParentClass__ = self.__ownerClass__.__bases__[0]
				return getattr(type(self).__ownerParentClass__, self.name, Unset)
		return Unset

	def doFuncInThread(self, func, *args, **kwargs):
		if self.thread is None:
			self.thread = QThread()

		# if not self.thread.isFinished():
		# 	while
		self.thread = QThread()
		self.exec_thread = ExecThread()

		self.exec_thread.args = args
		self.exec_thread.kwargs = kwargs
		self.exec_thread.func = func
		self.exec_thread.moveToThread(self.thread)
		self.thread.started.connect(self.exec_thread.run)
		self.exec_thread.finished.connect(self.thread.quit)
		self.thread.start()

	# Section .default(owner)
	@lru_cache()
	def default(self, owner: Type['Stateful']) -> Any | Literal[UnsetDefault]:
		ownerDefaults = getattr(owner, "__defaults__", {})

		if (ownerDefault := ownerDefaults.get(self.key, UnsetDefault)) is not UnsetDefault:
			return ownerDefault

		if (default := self.options.maps[0].get("default", UnsetDefault)) is not UnsetDefault:
			if default is Stateful and (returned := self.returnsFilter(Stateful, func=issubclass)) is not UnsetReturn:
				return returned.default()

			if isinstance(default, DefaultGroup):
				return default
			return default

		if (
			ownerParentDefault := getattr(ownerDefaults, "parents", {}).get(self.key, UnsetDefault)
		) is not UnsetDefault:
			return ownerParentDefault

		if (parentDefault := self.options.parents.get("default", UnsetDefault)) is not UnsetDefault:
			return parentDefault

		return UnsetDefault

	@lru_cache()
	def hasDefault(self, owner) -> bool:
		ownerDefaults = getattr(owner, "__defaults__", {})

		if (ownerDefault := ownerDefaults.get(self.key, UnsetDefault)) is not UnsetDefault:
			return True

		if (default := self.options.maps[0].get("default", UnsetDefault)) is not UnsetDefault:
			return True

		if (
			ownerParentDefault := getattr(ownerDefaults, "parents", {}).get(self.key, UnsetDefault)
		) is not UnsetDefault:
			return True

		if (parentDefault := self.options.parents.get("default", UnsetDefault)) is not UnsetDefault:
			return True

		return False

	def cacheKey(self, obj) -> str:
		return f"{self.key}.{id(obj):x}"

	# Section .existing(owner)
	##@profile
	def existing(self, owner) -> Any | Literal[UnsetExisting]:
		if isinstance(owner, StatefulMetaclass):
			return UnsetExisting
		cacheKey = self.cacheKey(owner)
		fromCache = self.__existingValues__.get(cacheKey, UnsetExisting)
		fromOwner = Unset
		if fromCache is UnsetExisting:
			try:
				fromOwner = self.fget(owner)
				if fromOwner is None:
					if not self.allowNone:
						fromOwner = Unset
				elif not isinstance(fromOwner, self.returns) and fromOwner is not Unset:
					raise TypeError(f"{self} returned {type(fromOwner)} instead of {self.returns}")
			except AttributeError as e:
				if (factory := self.__options.get("factory.func", None)) is not None:
					try:
						fromOwner = factory(owner)

					except Exception as eF:
						if STATEFUL_DEBUG:
							log.exception(e)
							log.exception(eF)
					else:
						self.fset(owner, fromOwner)
		if fromOwner is not Unset:
			self.__existingValues__[cacheKey] = fromOwner
			return fromOwner
		return fromCache

	@property
	def allowNone(self):
		return self.__options.get("allowNone", True)

	def __testCondition(self, value: Any, owner: _Panel, condition: DotDict) -> bool:
		func = get(condition, "func", "function", default=lambda _: _)
		args = get(condition, "args", "arguments", default=())
		kwargs = get(condition, "kwargs", "keyword arguments", default={})
		namedArgs = list(func.__code__.co_varnames)

		if name := {"owner", "self"} & set(func.__code__.co_varnames):
			namedArgs[namedArgs.index(name.pop())] = owner
		if "value" in func.__code__.co_varnames:
			namedArgs[namedArgs.index("value")] = value

		namedArgs = namedArgs[: func.__code__.co_argcount]

		args = [arg for arg in args if arg not in namedArgs]

		if (result := func(*namedArgs, *args, **kwargs)) is None:
			log.warning(
				f"A condition for {self} returned {str(None if result is None else type(result))}."
				f"  Conditions should always return a bool!"
				f"\n{getsourcefile(func):s}:{str(getsourcelines(func)[1])}"
				f"\n{getsource(func)}"
			)

		return result

	def testConditions(self, value: Any, owner: 'Stateful', method: str) -> bool:
		conditions = [i for i in self.options.get("conditions", []) if i.get("method", {}) & {method, "*"}]
		if not conditions:
			return True
		if debug and log.VERBOSITY == 5:
			g = []
			result = True
			for condition in conditions:
				test = self.__testCondition(value, owner, condition)
				result = result and test
				if not test:
					func = condition["func"]
					c = getsource(func).strip("\n")
					v = Panel(Pretty(value), title="value")
					c = Syntax(
						c, "python", dedent=True, tab_size=2, line_numbers=True, start_line=getsourcelines(func)[1]
					)
					g.append(c)
					g.append(v)
			if g:
				p = Panel(Group(*g), title=repr(self), subtitle=owner.__class__.__name__)
				console.print(p)
			return result
		return all(self.__testCondition(value, owner, condition) for condition in conditions)

	def setOption(self, **kwargs):
		self.__options.update(kwargs)
		return self

	@property
	def options(self):
		return self.__options

	@cached_property
	def conditions(self) -> Conditions:
		return self.__options.get("conditions")

	@cached_property
	def __options(self):
		parentOptions = getattr(self.parentCls, "options", Unset)
		ownOptions = self.optionsFromInit
		ownOptions["conditions"] = Conditions(self)
		if parentOptions is Unset:
			return ChainMap(DotDict(ownOptions))
		return parentOptions.new_child(ownOptions)

	@cached_property
	def dependencies(self) -> Set[str]:
		deps = self.__options.get("dependencies", set())
		if ... in deps or not deps:
			deps.discard(...)
			deps |= getattr(self.parentCls, "dependencies", set())
		return deps

	@cached_property
	def setOrder(self) -> Tuple[int, int]:
		if (parentOrder := getattr(self.__ownerParentClass__, self.name, Unset)) is not Unset and isinstance(
			parentOrder, StateProperty
		):
			inheritBased = parentOrder.setOrder[0] + 1
		else:
			mro = type(self).__ownerClass__.mro()
			inheritBased = (
				len([i for i in mro if issubclass(i, Stateful) and i not in {self.__ownerClass__, Stateful}]) + 1
			)
		dependencyBased = len(self.dependencies)
		return inheritBased, dependencyBased

	@property
	def hasConditions(self) -> bool:
		return bool(self.__options.get("conditions", False))

	def condition(self, *args, **kwargs):
		method = kwargs.pop("method", Unset)
		if isinstance(method, str):
			method = {method}
		elif isinstance(method, (list, tuple)):
			method = set(method)
		if args:
			func, *args = args
		else:
			func = Unset

		if (conditions := self.__options.maps[0].get('conditions', None)) is None:
			self.__options["conditions"] = conditions = Conditions(self)
			inheritedConditions = next((i['conditions'] for i in self.options.maps if 'conditions' in i), [])
			conditions.extend(inheritedConditions)

		con = DotDict()
		conditions.append(con)
		con["method"] = method or {"get"}
		if func is Unset:
			def continueCondition(func):
				con["func"] = func
				return self

			con["func"] = func
			if kwargs:
				con["kwargs"] = kwargs
			return continueCondition

		con["func"] = func
		if isinstance(con["func"], Callable):
			con["preview"] = getsource(con["func"])
		return self

	def after(self, func):
		self.__options["after.func"] = func
		return self

	def update(self, func):
		self.__options["update.func"] = func
		return self

	# Section .encode
	def encode(self, *args, **kwargs):  # TODO: Add warning when function is improperly named
		"""Encode the value of this property for storage in the database."""
		if args:
			func, *args = args
		else:
			func = None
		if args or kwargs:
			self.__options["encode.args"] = (func, *args)
			self.__options["encode.kwargs"] = kwargs
		self.__options["encode.func"] = func

		return self

	# Section .decode
	def decode(self, *args, **kwargs):
		if args:
			func, *args = args
		else:
			func = None
		if args or kwargs:
			self.__options["decode.args"] = (func, *args)
			self.__options["decode.kwargs"] = kwargs
		self.__options["decode.func"] = func

		return self

	# Section .factory
	def factory(self, func: Callable[[], "Stateful"]):
		self.__options["factory.func"] = func
		return self

	def score(self, func: Callable[[Any], float] = None, **kwargs):
		if kwargs:
			return partial(self.score, **kwargs)
		kwargs['func'] = func
		self.__options["score"] = kwargs
		return self

	def scoreValue(self, owner, value) -> float:
		if scoreFunc := self.__options.get("score.func", None):
			varNames = scoreFunc.__code__.co_varnames[: scoreFunc.__code__.co_argcount]
			match varNames:
				case ["self", "value"]:
					return scoreFunc(owner, value)
				case ["self"]:
					return scoreFunc(owner)
				case [var] if var != "self":
					return scoreFunc(value)
				case _:
					pass
		ownerValue = getattr(owner, self.name)
		try:
			return int(ownerValue == value)
		except TypeError:
			return 0

	@cached_property
	def unwrappedKeys(self) -> Set[str]:
		if not self.unwraps:
			return set()
		elif self.isStatefulReference:
			statefulType = self.returnsFilter(Stateful)
			return statefulType.statefulKeys
		return set()

	@lru_cache(maxsize=128)
	def sortOrder(self, ownerType):
		typeSortOrder = len([i for i in ownerType.__mro__ if issubclass(i, Stateful)])
		fromOptions = self.__options.get("sortOrder", Unset)
		if fromOptions is not Unset and fromOptions < 0:
			fromOptions = 100 - fromOptions
		sort = fromOptions << OrUnset >> typeSortOrder + 1
		return sort

	@property
	def name(self):
		return getattr(self, "_name_", None) or self.__findName()

	@guarded_cached_property(guardFunc=lambda x: x is not None, default=name)
	def key(self):
		return self.__options.get("key", None)

	def __findName(self):
		if self._get is not None:
			name = self._get.__name__
		elif self._set is not None:
			name = self._set.__name__
		else:
			name = None
		self._name_ = name
		return name

	@cached_property
	def singleVal(self) -> bool:
		return self.__options.get("singleVal", False)

	@cached_property
	def unwraps(self) -> bool:
		return self.__options.get("unwrap", False)

	@cached_property
	def excluded(self) -> bool:
		exclude = self.__options.get("exclude", False)
		return exclude

	def excludedFrom(self, owner, exclude: set = None) -> bool:
		if exclude is None:
			exclude = set()
		exclude = exclude | getattr(owner, "__exclude__", set())
		return {self.key, self.name} & exclude

	@cached_property
	def expands(self) -> bool:
		return self.__options.get("expand", False)

	@cached_property
	def required(self) -> bool:
		return self.__options.get("required", False)

	@cached_property
	def includeInRepr(self) -> bool | None:
		return self.__options.get('repr', None)

	@cached_property
	def isStatefulReference(self) -> bool:
		if self.__options.get("link", False):
			return True
		if (d := self.__options.get("default", None)) and isinstance(d, type) and issubclass(d, Stateful):
			return True
		try:
			if repr(self) == '@Stateful.shared':
				return True
			return self._varifyReturnType(Stateful)
		except TypeError:
			return False

	def encodeValue(self, value, owner):
		encoder = self.__options.get("encode", {})
		if encodeFunc := encoder.get("func", False):
			varNames = encodeFunc.__code__.co_varnames[: encodeFunc.__code__.co_argcount]
			match varNames:
				case ["self", "value"]:
					value = encodeFunc(owner, value)
				case ["self"]:
					value = encodeFunc(owner)
				case [var] if var != "self":
					value = encodeFunc(value)
				case _:
					value = encodeFunc()
		if isinstance(value, Stateful):
			return value
		decodesTo = self.decodesTo
		if (encoded := getattr(value, 'encoded_state', None)) is not None:
			if isinstance(encoded, Callable):
				encoded = encoded()
			value = encoded

		elif (state := getattr(value, "state", None)) is not None and decodesTo is not UnsetReturn:
			if isinstance(state, self.decodesTo):
				value = state

		return value

	def decodeValue(self, value, owner):
		decoder = self.__options.get("decode", {})
		if decodeFunc := decoder.get("func", False):
			varNames = decodeFunc.__code__.co_varnames[: decodeFunc.__code__.co_argcount]
			match varNames:
				case "self", "value":
					value = decodeFunc(owner, value)
				case "self", *rest:
					if rest:
						rest = value,
					value = decodeFunc(owner, *rest)
				case ["cls", *rest]:
					if rest:
						rest = value,
					value = decodeFunc(*rest)
				case [var] if var not in {"self", "cls"}:
					value = decodeFunc(value)
				case _:
					value = decodeFunc()
		return value

	# Section .getState()
	def getState(self, owner, encode: bool = True):
		options = self.__options
		key = self.key

		if self.__state is not None:
			value = self.__state(owner)
		else:
			try:
				value = self.fget(owner)
			except AttributeError:
				return '_', None

		# check conditions
		if not self.testConditions(value, owner, "get"):
			return "_", None

		rawValue = value
		if encode:
			value = self.encodeValue(value, owner)

		# check default
		if not self.required:
			if isinstance(value, Stateful):
				if value.state == {}:
					return "_", None
				if value.testDefault(value.default()):
					return "_", None
			default = self.default(type(owner))

			if isinstance(default, DefaultGroup) or default is UnsetDefault:
				pass
			elif encode and isinstance(default, self.returns):
				default = self.encodeValue(default, owner)
			elif not encode and not isinstance(default, self.returns):
				default = self.decodeValue(default, owner)

			if default is UnsetDefault:
				pass
			elif isinstance(default, DefaultGroup):
				if value == default:
					return "_", None
			if value == default or rawValue == default:# or (encode and value == self.encodeValue(default, owner)):
				return "_", None

		if sortFunc := self.sortFunc:
			try:
				if isinstance(value, Mapping) and (keyFunc := sortFunc.keywords.get("key", None)):
					varNames = set(keyFunc.__code__.co_varnames)
					if not varNames - {"value", "v"}:
						value = sortFunc(value.values())
					elif not varNames - {"key", "k"}:
						value = sortFunc(value)
					elif not varNames - {"item"}:
						value = dict(sortFunc(value.items()))
					else:
						log.warning(
							f'Only "value", "key", or "item" are supported argument names for sorting dictionaries by a supplied sorting key function'
						)
						raise TypeError
				else:
					value = sortFunc(value)
			except Exception as e:
				log.warning(f"{self} tried to sort it's value, but contents are not comparable")
				log.exception(e)
		return key, value

	@cached_property
	def sortFunc(self) -> Callable[[Iterable], Iterable] | None:
		if sort := self.__options.get("sort", False):
			if sortFunc := self.__options.get("sortKey"):
				sort = sortFunc
			if not self._varifyReturnType(Iterable):
				log.warning(f"{self} is marked to be sorted, the return type is not iterable")
			if isinstance(sort, Callable):
				return partial(sorted, key=sort)
			elif isinstance(sort, str):
				return partial(sorted, key=attrgetter(sort))
			else:
				return sorted

	@property
	def actions(self) -> Set[str]:
		actions = set()
		if getattr(self, "fget", False):
			actions.add("get")
		if getattr(self, "fset", False):
			actions.add("set")
		if self.isStatefulReference:
			actions |= {"get", "set"}
		if actions == {"get", "set"}:
			actions.add("*")
		if getattr(self, "fdel", False):
			actions.add("del")
		if self.__options.get("match", False):
			actions.add("match")
		return actions

	@cached_property
	def returns(self) -> Tuple[Type | UnsetReturn, ...]:
		expected = get_type_hints(self._get).get("return", None) or get_type_hints(self.fget).get("return", UnsetReturn)
		expected = self.parse_return_type(expected)
		expectedCombined = set()
		for e in expected:
			if isinstance(e, tuple):
				expectedCombined.update(e)
			else:
				expectedCombined.add(e)
		return tuple(expectedCombined) or (UnsetReturn,)

	@property
	def returnsContents(self) -> Dict[Type, Type]:
		expected = get_type_hints(self._get).get("return", None) or get_type_hints(self.fget).get("return", UnsetReturn)
		d = {}
		for t in expected:
			if issubclass(t, Iterable) and not issubclass(t, str):
				d[get_origin(t)] = get_args(t)
		return d

	@cached_property
	def returnsSpecial(self) -> Tuple[Type | TypedIterable, ...]:
		expected = get_type_hints(self._get).get("return", None) or get_type_hints(self.fget).get("return", UnsetReturn)
		expected = self.parse_return_type_special(expected)
		return expected

	@cached_property
	def decodesTo(self) -> Tuple[Type, ...] | UnsetReturn:
		try:
			decoder = self.__options["decode"]['func']
			annotations = get_annotations(decoder).get("return", None) or get_type_hints(decoder).get("return", UnsetReturn)
			if annotations is not UnsetReturn:
				return self.parse_return_type_special(annotations)
			return UnsetReturn
		except KeyError:
			return UnsetReturn

	@property
	def accepts(self) -> Tuple[Type, ...]:
		accepts = self.__options.get("accepts", [])
		if not isinstance(accepts, tuple | list):
			accepts = [accepts]
		if (decoder := self.__options.get('decoder', None)) is not None and (decoder := decoder.get('func', None)) is not None:
			hints = get_type_hints(decoder)
		return tuple(accepts) or Unset

	@staticmethod
	@lru_cache
	def parse_return_type(expected) -> tuple[type]:
		if isinstance(expected, (_UnionGenericAlias, UnionType)):
			expected = get_args(expected)
			expected = tuple(StateProperty.parse_return_type(e) for e in expected)
		elif isinstance(expected, (GenericAlias, _GenericAlias)):
			expected = get_origin(expected)
		if isinstance(expected, type) and issubclass(expected, Enum):
			return expected,
		if not isinstance(expected, Iterable):
			expected = (expected,)
		return expected

	@staticmethod
	def parse_return_type_special(expected: Type | GenericAlias | _UnionGenericAlias | _GenericAlias | Iterable[Type | GenericAlias | _UnionGenericAlias | _GenericAlias]) -> Parse_Return_Type:
		if isinstance(expected, _UnionGenericAlias):
			return tuple(StateProperty.parse_return_type_special(t) for t in get_args(expected))
		elif isinstance(expected, Iterable) and not isinstance(expected, str) and all(isinstance(t, Type | GenericAlias | _UnionGenericAlias | _GenericAlias | Iterable) for t in expected):
			return tuple(StateProperty.parse_return_type_special(t) for t in expected)
		if isinstance(expected, _GenericAlias | GenericAlias):
			origin = get_origin(expected)
			if issubclass(origin, Iterable) and expected.__args__:
				return makeTypedIterable(expected)
		return expected

	def _varifyReturnType(self, _type: _T, func: Callable[[_T, type], bool] = issubclass) -> bool:
		if (returns := self.returns) is UnsetReturn:
			return False
		for _t in returns:
			if isinstance(_t, (GenericAlias, _GenericAlias)):
				_t = get_origin(_t)
			if isinstance(_t, UnionType):
				_t = get_args(_t)
			if isinstance(_t, tuple):
				if any(func(_t, _type) for _t in _t):
					return True
				continue
			if func(_t, _type):
				return True
			try:
				if func(_type, _t):
					return True
			except TypeError:
				continue
		return False

	def returnsFilter(self, _type: _T, func: Callable[[Any, type], bool] = None) -> _T | UnsetReturn:
		if func is None:
			func = issubclass if isinstance(_type, type) else isinstance
		try:
			return next((i for i in self.returns if func(i, _type)), UnsetReturn)
		except TypeError:
			return UnsetReturn

	# Section .setState()
	##@profile
	def setState(self, owner, state, afterPool: OrderedSet = None):
		if UnsetReturn not in self.returns:
			if (existing := self.existing(owner)) is not UnsetExisting and existing is not state:
				if updateFunc := self.__options.get("update.func", False):
					# TODO: Add option for passing existing item to update function
					owner._rawItemState = deepcopy(state)
					updateFunc(owner, state)
					return
				if (
					stateVar := getattr(type(existing), "state", None)) and (
					fset := getattr(stateVar, "fset", None)
				) is not None:
					try:

						if isinstance(state, self.returns):
							# TODO: Look in to removing this
							# TODO: Bad code smell
							state = state.state

						if isinstance(existing, Stateful):
							existing._rawItemState = deepcopy(state)
							if not isinstance(state, Mapping):
								state = self.decodeValue(state, owner)
						else:
							annotations = get_annotations(fset)
							if len(annotations) == 1:
								expected = list(annotations.values())[0]
								if not isinstance(state, expected):
									state = self.decodeValue(state, owner)
						fset(existing, state)
						if isinstance(existing, Stateful):
							try:
								existing.__state_key__ = self
								existing.__statefulParent = owner
							except AttributeError:
								pass
						return
					except Exception as e:
						log.exception(e)
						log.error(f"Unable to set state for {existing}")
						raise e

		self.__set__(owner, state, afterPool=afterPool)

	@staticmethod

	def setDefault(self, owner):
		if default := self.default(type(owner)) is None:
			raise ValueError("Default value is not set")
		self._set(owner, copy(default))


class StatefulReferenceProperty(property):
	_isStatefulReference = True

	def __init__(self, ref, ownerType: Type['Stateful'], ownerProp: StateProperty):
		self.ref = ref
		self.ownerType = ownerType
		self.ownerProp = ownerProp

	def __get__(self, owner, ownerType=None):
		print('test')

	def __set__(self, owner, value):
		print('set')

	def __set_name__(self, owner, name):
		self.name = name



# Section YAML
class StatefulConstructor(SafeConstructor):
	node_stack: List["Stateful"]
	currentNode: "Stateful"

	def construct_object(self, node, deep=False):
		return super().construct_object(node, deep=deep)

	def construct_mapping(self, node, deep=False):
		return super().construct_mapping(node, deep=deep)

	def loadGraphs(parent, items, parentItems, **kwargs):
		from LevityDash.lib.ui.frontends.PySide.Modules import GraphPanel

		parentItems = parentItems or getattr(parent, "items", [])
		existing = [i for i in parentItems if isinstance(i, GraphPanel)]
		while items:
			item = items.pop(0)
			if not GraphPanel.validate(item):
				log.error("Invalid state for graph:", item)
			ns = SimpleNamespace(**item)

			match existing:
				case [graph]:
					graph.state = item
				case [GraphPanel(geometry=ns.geometry) as graph, *existing]:
					graph.state = item
				case []:
					return GraphPanel(parent=parent, **item, cacheInitArgs=True)
				case [*existing]:
					graph = sorted(
						existing,
						key=lambda g: (g.geometry.scoreSimilarity(ns.geometry), abs(len(ns.figures) - len(g.figures))),
					)[0]
					existing.remove(graph)

	def loadRealtime(parent, items, parentItems, **kwargs):
		from LevityDash.lib.ui.frontends.PySide.Modules import Realtime

		parentItems = parentItems or getattr(parent, "items", [])
		existing: [Realtime] = [i for i in parentItems if isinstance(i, Realtime)]
		pop = getattr(type(items), "popitem", None) or getattr(type(items), "pop", Unset)
		while items:
			item = pop(items)
			if not Realtime.validate(item):
				log.error("Invalid state for existingItem:", item)
			item["key"] = CategoryItem(item["key"])
			ns = SimpleNamespace(**item)
			match existing:
				case []:
					Realtime(parent=parent, **item, cacheInitArgs=True)
				case [existingItem]:
					existing.remove(existingItem)
					existingItem.state = item
				case [Realtime(key=ns.key, geometry=ns.geometry) as existingItem, *_]:
					existing.remove(existingItem)
					existingItem.state = item
				case [*_]:
					existingItem = sorted(
						existing,
						key=lambda g: (g.geometry.scoreSimilarity(ns.geometry), levenshtein(str(ns.key), str(g.key))),
					)[0]
					existing.remove(existingItem)
					existingItem.state = item
				case _:
					print("fail")
		for i in existing:
			i.scene().removeItem(i)

	def loadClock(parent, items, parentItems, **kwargs):
		from LevityDash.lib.ui.frontends.PySide.Modules import Clock

		parentItems = parentItems or getattr(parent, "items", [])
		existing = [i for i in parentItems if isinstance(i, Clock)]
		while items:
			item = items.pop(0)
			if not Clock.validate(item):
				log.error("Invalid state for clock:", item)
			ns = SimpleNamespace(**item)
			match existing:
				case [clock]:
					clock.state = item
				case [Clock(geometry=ns.geometry) as clock, *existing]:
					clock.state = item
				case []:
					Clock(parent=parent, **item, cacheInitArgs=True)
				case [*existing]:
					clock = sorted(
						existing,
						key=lambda g: (g.geometry.scoreSimilarity(ns.geometry), levenshtein(ns.format, g.format)),
					)[0]
					existing.remove(clock)

	def loadPanels(parent, items, parentItems, **kwargs):
		from LevityDash.lib.ui.frontends.PySide.Modules import Panel

		parentItems = parentItems or getattr(parent, "items", [])
		existing = [i for i in parentItems if type(i) is Panel]
		while items:
			item = items.pop(0)
			if not Panel.validate(item):
				log.error("Invalid state for panel:", item)
			ns = SimpleNamespace(**item)
			match existing:
				case [panel]:
					existing.remove(panel)
					panel.state = item
				case [Panel(geometry=ns.geometry) as panel, *_]:
					existing.remove(panel)
					panel.state = item
				case []:
					Panel(parent=parent, **item, cacheInitArgs=True)
				case [*_]:
					panel = sorted(existing, key=lambda g: g.geometry.scoreSimilarity(ns.geometry))[0]
					existing.remove(panel)
		for i in existing:
			i.scene().removeItem(i)

	def loadLabels(parent, items, parentItems, **kwargs):
		from LevityDash.lib.ui.frontends.PySide.Modules import EditableLabel

		parentItems = parentItems or getattr(parent, "items", [])
		existing = [i for i in parentItems if isinstance(i, EditableLabel)]
		while items:
			item = items.pop(0)
			if not EditableLabel.validate(item):
				log.error("Invalid state for label:", item)
				continue
			ns = SimpleNamespace(**item)
			match existing:
				case [label]:
					existing.remove(label)
					label.state = item
				case [EditableLabel(text=ns.text, geometry=ns.geometry) as label, *_]:
					existing.remove(label)
					label.state = item
				case [EditableLabel(geometry=ns.geometry) as label, *_]:
					existing.remove(label)
					label.state = item
				case [EditableLabel(text=ns.text) as label, *_]:
					existing.remove(label)
					label.state = item
				case []:
					EditableLabel(parent=parent, **item)
				case [*_]:
					label = sorted(existing, key=lambda g: (g.geometry.scoreSimilarity(ns.geometry)))[0]
					existing.remove(label)
		for i in existing:
			i.scene().removeItem(i)

	def loadMoon(parent, items, parentItems, **kwargs):
		from LevityDash.lib.ui.frontends.PySide.Modules import Moon

		parentItems = parentItems or getattr(parent, "items", [])
		existing = [i for i in parentItems if isinstance(i, Moon)]
		while items:
			item = items.pop(0)
			ns = SimpleNamespace(**item)
			match existing:
				case [moon]:
					existing.remove(moon)
					moon.state = item
				case [Moon(geometry=ns.geometry) as moon, *_]:
					existing.remove(moon)
					moon.state = item
				case []:
					Moon(parent=parent, **item)
				case [*_]:
					moon = sorted(existing, key=lambda g: g.geometry.scoreSimilarity(ns.geometry))[0]
					existing.remove(moon)
					moon.state = item
		for i in existing:
			i.scene().removeItem(i)

	def itemLoader(parent, unsortedItems: list[dict], parentItems: list = None, **kwargs):
		"""
		Loads an item from a dictionary or list of dictionaries.
		Parameters

		item = {
						"realtime.text": [list of items...],
						"graph": [list of items...],
		}
						or
		kwargs['type'], [list of items...] and

		----------
		parent : Union[LevityDash.lib.ui.frontends.PySide.Modules.CentralPanel.CentralPanel, LevityDash.lib.ui.frontends.PySide.Modules.DateTime.Clock, LevityDash.lib.ui.frontends.PySide.Modules.Panel.Panel]
		item : Dict[str, str]
		parentItems : Union[List, List[LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph.GraphPanel], None, List[LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime.Realtime], List[LevityDash.lib.ui.frontends.PySide.Modules.Label.EditableLabel], None, None]
		kwargs :

		Returns
		-------
		Union[LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph.GraphPanel, None, LevityDash.lib.ui.frontends.PySide.Modules.Displays.Moon.Moon, LevityDash.lib.ui.frontends.PySide.Modules.DateTime.Clock, LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime.Realtime, LevityDash.lib.ui.frontends.PySide.Modules.Panel.Panel, LevityDash.lib.ui.frontends.PySide.Modules.Label.EditableLabel]
		"""
		if not unsortedItems:
			return
		if parentItems is None:
			parentItems = []

		sortedItems = dict()

		for i in unsortedItems:
			_type = i.get("type", Unset)
			if _type is Unset:
				if "key" in i:
					_type = "realtime.text"
				else:
					_type = "group"
				i["type"] = _type
			_type = _type.split(".")[0]
			if _type not in sortedItems:
				sortedItems[_type] = []
			sortedItems[_type].append(i)

		for _type, group in sortedItems.items():
			match _type:
				case "graph":
					loadGraphs(parent, group, parentItems, **kwargs)
				case "realtime":
					# continue
					loadRealtime(parent, group, parentItems, **kwargs)
				case "clock":
					loadClock(parent, group, parentItems, **kwargs)
				case "group":
					# continue
					loadPanels(parent, group, parentItems, **kwargs)
				case "text" | "label":
					# continue
					loadLabels(parent, group, parentItems, **kwargs)
				case "moon":
					loadMoon(parent, group, parentItems, **kwargs)
				case _:
					continue


class StatefulDumper(SafeDumper):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.add_representer(timedelta, self.represent_timedelta)

	def represent_timedelta(self, dumper, data):
		data = data.total_seconds()
		weeks = int(data/(60*60*24*7))
		data -= weeks*60*60*24*7
		days = int(data/(60*60*24))
		data -= days*60*60*24
		hours = int(data/(60*60))
		data -= hours*60*60
		minutes = int(data/60)
		data -= minutes*60
		seconds = int(data)
		result = {}
		if weeks > 0:
			result["weeks"] = weeks
		if days > 0:
			result["days"] = days
		if hours > 0:
			result["hours"] = hours
		if minutes > 0:
			result["minutes"] = minutes
		if seconds > 0:
			result["seconds"] = seconds
		return dumper.represent_dict(result)

	def ignore_aliases(self, data):
		return True


class StatefulLoader(Reader, Scanner, Parser, Composer, StatefulConstructor, Resolver):
	node_stack: List["Stateful"] = []

	def __init__(self, stream):
		Reader.__init__(self, stream)
		Scanner.__init__(self)
		Parser.__init__(self)
		Composer.__init__(self)
		StatefulConstructor.__init__(self)
		Resolver.__init__(self)

	@contextmanager
	def dive(self, node):
		self.node_stack.append(node)
		yield self
		self.node_stack.pop()

	@property
	def currentNode(self):
		return self.node_stack[-1]


QObjectType = type(QObject)

T = TypeVar('T', str, int, float, tuple, dict, list)


class StateData:
	stateParent: 'Stateful'

	__conversions = {}

	@staticmethod
	def _convertItem(item: T) -> T:
		if (convertTo := StateData.__conversions.get(type(item), None)) is not None:
			item = convertTo(item)
		elif isinstance(item, tuple(StateData.__conversions.keys())):
			matches = list(set(type(item).mro()) & set(StateData.__conversions.keys()))
			matchedType = matches.pop()
			item = matchedType(item)
		return item

	@classmethod
	def registerConverstion(cls, key: Type, value: Type['StateData']):
		cls.__conversions[key] = value


class StateStr(StateData, str):
	pass


class StateInt(StateData, int):
	pass


class StateFloat(StateData, float):
	...


class StateDict(StateData, dict):

	def __new__(cls, *args, **kwargs):
		for arg in (*args, kwargs):
			for key, value in arg.items():
				arg[key] = cls._convertItem(value)
		return super().__new__(*args, **kwargs)

	def __setitem__(self, key, value):
		value = self._convertItem(value)
		super().__setitem__(key, value)


class StateList(MutableSequence, StateData, list):

	def __setitem__(self, key, value):
		value = self._convertItem(value)
		super().__setitem__(key, value)


class StateTuple(Sequence, StateData, tuple):

	def __new__(cls, *args, **kwargs):
		args = [cls._convertItem(i) for i in args]
		return super().__new__(*args, **kwargs)


StateData.registerConverstion(str, StateStr)
StateData.registerConverstion(int, StateInt)
StateData.registerConverstion(float, StateFloat)
StateData.registerConverstion(dict, StateDict)
StateData.registerConverstion(list, StateList)
StateData.registerConverstion(tuple, StateTuple)


@dataclass
class StateData:
	state: Any
	parent: 'Stateful'


def gendoc(name: str, props: Iterable[StateProperty], cls_doc: str = '') -> str:
	if not cls_doc.endswith('\n'):
		cls_doc += '\n'

	def genKeywordAguments() -> str:
		items = []
		for prop in props:
			prop_doc_string = getattr(prop, "__doc__", "")
			items.append(f':key {prop.key}: {prop_doc_string if prop_doc_string else ""}')
			returns = tuple(i if i is not type(None) else None for i in prop.returns if i is not UnsetReturn)
			if returns is not UnsetReturn:
				items.append(f':type {prop.key}: {" | ".join((getattr(i, "__name__", str(i)) for i in returns))}')
		return '\n'.join(items)

	body = f"""
{name}
{cls_doc}
Keyword arguments:
{genKeywordAguments()}
"""

	return body

# Section StatefulMeta
class StatefulMetaclass(QObjectType, type):
	__state_items__: ChainMap
	__tags__: Set[str] = set()
	__loader__ = StatefulLoader
	__dumper__ = StatefulDumper
	__default_states__: Dict[Type['Stateful'], DefaultState]

	def __new__(mcs, name, bases, attrs, **kwargs):
		log.verbose(f"Creating stateful class {name}", verbosity=5)
		global _typeCache

		if name == "Stateful":
			items = {k: v for k, v in attrs.items() if isinstance(v, StateProperty)}
			attrs["__state_items__"] = ChainMap(items)
			newMcs = super().__new__(mcs, name, bases, attrs, **kwargs)
			for item in set(type(i) for i in items.values()):
				item.__owner__ = newMcs
				item.__ownerClass__ = newMcs
			return newMcs

		parentCls = Stateful
		statefulParents = [b for b in bases if issubclass(b, Stateful)]
		for base in statefulParents:
			parentCls = base

		if len(statefulParents) == 1:
			items = parentCls.__state_items__.new_child()
		elif len(statefulParents) > 1:
			i = [i.__state_items__ for i in statefulParents]
			items = ChainMap({}, *i)
		else:
			raise TypeError(f"Stateful class {name} must inherit from Stateful")

		propName = f"{name}StateProperty"

		# Create defaults and inherit parent's defaults
		defaults = attrs.get("__defaults__", {})
		superDefaults = getattr(parentCls, "__defaults__", ChainMap())
		if not isinstance(superDefaults, ChainMap):
			superDefaults = ChainMap(superDefaults)
			parentCls.defaults = superDefaults
		defaults = {k: v for k, v in defaults.items() if superDefaults.get(k, Unset) != v}
		defaults = superDefaults.new_child(defaults)
		attrs["__defaults__"] = defaults
		attrs["__default_states__"] = {}

		# Create exclusions and inherit parent's exclusions
		exclude = set(attrs.get("__exclude__", {}))
		if ... in exclude or not exclude:
			exclude.discard(...)
			for base in bases:
				exclude |= getattr(base, "__exclude__", set())
		attrs["__exclude__"] = exclude

		__ownerParentClass__ = getattr(parentCls, "__ownerParentClass__", Stateful)
		propParentClass = getattr(parentCls, "__statePropertyClass__", StateProperty)
		propAttrs = {"__owner__": name, "__ownerParentClass__": __ownerParentClass__, "__existingValues__": {}}

		propClass = makeType(propName, (propParentClass,), propAttrs)
		attrs["__statePropertyClass__"] = propClass

		props = items.new_child({v.key: v for v in attrs.values() if isinstance(v, StateProperty)})

		attrs["__state_items__"] = props
		attrs["__repr_keys__"] = [prop for prop in props.values() if prop.includeInRepr]

		cls = super().__new__(mcs, name, bases, attrs)

		for propType in {type(v) for v in props.maps[0].values()}:
			if (ownerClass := getattr(propType, "__ownerClass__", None)) is not cls:
				if ownerClass is not None:
					continue
				propType.__ownerClass__ = cls

		if tag := kwargs.get("tag", None):
			mcs.__tags__.add(tag)
			cls.__tag__ = tag
			if isinstance(cls.__dumper__, list):
				for dumper in cls.__dumper__:
					dumper.add_representer(cls, cls.representer)
			else:
				cls.__dumper__.add_representer(cls, cls.representer)

		cls.__statePropertyClass__.__ownerClass__ = cls

		log.verbose(f"Created stateful class {name}", verbosity=5)
		return cls

	@property
	def __doc__(cls) -> str:
		name = cls.__name__
		props = cls.statefulItems
		return gendoc(name, props.values())

	@property
	def statefulItems(self) -> Dict[str, StateProperty]:
		return dict(sorted(self.__state_items__.items(), key=lambda x: x[1].setOrder))

	@property
	def statefulKeys(self) -> Set[str]:
		return set(i.key for i in self.__state_items__.values())

	@property
	def singleStatefulItems(cls) -> Dict[str, StateProperty]:
		return {k: v for k, v in cls.statefulItems.items() if v.singleVal}

	@property
	def singleStatefulItemTypes(cls) -> Tuple[Type, ...]:
		return tuple(i for j in (p.returns for p in cls.statefulItems.values() if p.singleVal) for i in j)

	def __subclasses__(self: Type['Stateful'], deep: bool = True) -> List[Type['Stateful']]:
		if not deep:
			return super().__subclasses__()
		subclasses = []
		for sub in super().__subclasses__():
			subclasses.append(sub)
			subclasses.extend(sub.__subclasses__(deep=deep))
		return subclasses

# Section Stateful
@auto_rich_repr
class Stateful(metaclass=StatefulMetaclass):
	__state_items__: ClassVar[ChainMap[Text, StateProperty]]
	__defaults__: ChainMap[str, Any]
	__tag__: ClassVar[str] = "Stateful"
	_set_state_items_: set
	_unset_keys_: set = None
	_rawItemState: Dict[str, Any]

	statefulItems = StatefulMetaclass.statefulItems
	statefulKeys = StatefulMetaclass.statefulKeys

	statefulParent: "Stateful"
	__statefulParent = None

	def _afterSetState(self):
		pass

	def testDefault(self, other):
		if isinstance(other, DefaultState):
			items = [i for i in self.statefulItems.values() if i.key in other or i.name in other]
			for item in items:
				if not item.isStatefulReference:
					key, ownValue = item.getState(self, True)
					if key == 'shared':
						key, ownValue = item.getState(self, True)
					if key != "_":
						otherValue = other.get(item.name, None)
						if not ownValue == otherValue:
							return False
				else:
					ownValue = item.fget(self)
					otherValue = other.get(item.name if item.name in other else item.key, UnsetDefault)
					if not ownValue.testDefault(otherValue):
						return False
			return True

		ownState = self.state
		if isinstance(ownState, dict):
			for k, v in other.items():
				if k not in ownState:
					continue
				ownValue = ownState[k]
				prop = self.__state_items__[k]
				if isinstance(ownValue, Stateful):
					if not ownValue.testDefault(v):
						return False
				elif ownValue != v:
					return False
			return True
		defaultSingles = self.defaultSingles()
		matchedType = [
			default for prop, default in defaultSingles.items() if isinstance(ownState, (type(default), *prop.returns))
		]
		match matchedType:
			case []:
				return False
			case [default]:
				return ownState == default
			case _:
				return ownState in defaultSingles

	@property
	def statefulParent(self) -> 'Stateful':
		return self.__statefulParent

	@statefulParent.setter
	def statefulParent(self, value):
		self.__statefulParent = value

	@property
	def stateful_level(self) -> int:
		try:
			p = self.statefulParent
			if p is None:
				return 0
			return p.stateful_level + 1
		except AttributeError:
			return 0

	@property
	def is_loading(self) -> bool:
		return bool(self._unset_keys_)

	@property
	def state_is_loading(self) -> bool:
		if self.statefulParent is None:
			return self.is_loading or False
		return self.is_loading or self.statefulParent.state_is_loading

	@cached_property
	def _actionPool(self) -> ActionPool:
		try:
			return self.statefulParent._actionPool.new(self)
		except AttributeError:
			return ActionPool(self, trace='acton')

	# Section .shared
	@StateProperty(key="shared", default=DeepChainMap(), sortOrder=0, repr=False)
	def shared(self) -> DeepChainMap:
		shared = getattr(self, "_shared", None)
		if shared is None:
			parent = self.statefulParent
			if parent is None:
				self._shared = shared = DeepChainMap(origin=self)
			else:
				parentShared = getattr(parent, 'shared', None)
				ownKeys = set(self.statefulItems) - {'shared'}
				if (key := getattr(self, '__state_key__', None)) is not None and key.key in parentShared:
					localShared = parentShared[key.key]
				else:
					localShared = {}

				localShared.update({k: v for k, v in parentShared.items() if k in ownKeys})
				maps = []
				if localShared:
					maps.append(localShared)
				if parentShared:
					maps.append(parentShared)
				self._shared = shared = DeepChainMap(*maps, origin=self)
		return shared

	@shared.setter
	def shared(self, value: dict):
		if value.pop('~clear', False):
			self._shared = DeepChainMap()
		self.shared.update(value)

	@shared.condition(method={'get'})
	def shared(self, value: DeepChainMap):
		return len(value.originMap) > 0

	@shared.encode
	def shared(self, value: DeepChainMap) -> dict:
		return value.originMap

	@property
	def ownShared(self) -> dict:
		return recursiveRemove(dict(self._shared.originMap.items()), self._shared_values)

	# Section .setItemState
	def setItemState(self, state: Mapping[str, Any] | List, *args, **kwargs):
		if isinstance(state, Stateful):
			state = state.state

		try:
			self._rawItemState = deepcopy(state)
		except Exception:
			pass

		if state is Unset or state is UnsetDefault:
			return

		if not isinstance(state, Mapping):
			acceptedSingleValueTypes = tuple(
				i for j in (p.returns for p in self.statefulItems.values() if p.singleVal) for i in j
			)
			if isinstance(state, acceptedSingleValueTypes):
				# try:
				prop = [
					v
					for v in self.statefulItems.values()
					if v.actions & {"set"} and v.singleVal and isinstance(state, v.returns)
				].pop()
				state = {prop.key: state}
			else:
				raise TypeError(f"Unable to set state for {self} with {state}")

		items: Dict[str, StateProperty] = {
			k: v
			for k, v in self.statefulItems.items()
			if bool(v.actions & {"set"}) and (v.key in state or v.name in state or v.unwraps or v.singleVal)
		}
		getOnlyItems = {
			k
			for k, v in self.statefulItems.items()
			if "set" not in v.actions and not v._varifyReturnType(Stateful)
		}

		self._unset_keys_ = set(items.values())

		if isinstance(state, dict) and getOnlyItems:
			for i in getOnlyItems & set(state.keys()):
				state.pop(i, None)

		shared = getattr(self, 'shared', Unset) or DeepChainMap()
		afterPool: ActionPool = self._actionPool
		unwraps = []
		for prop in items.values():
			if prop.unwrappedKeys:
				if prop.key not in prop.unwrappedKeys:
					pass
				elif prop.unwraps:
					unwraps.append(prop)
					if len(state) == 1:
						break
					continue
			elif prop.unwraps:
				unwraps.append(prop)
				if len(state) == 1:
					break
				continue

			propKey = prop.key
			if propKey not in state:
				self._unset_keys_.discard(prop)
				continue
			else:
				value = state.pop(propKey)
				if (sharedValue := shared.get(propKey, Unset)) is not Unset:
					sharedType = type(sharedValue)
					sharedType = sharedType if not issubclass(sharedType, DeepChainMap) else dict
					if isinstance(value, sharedType):
						match sharedValue:
							case dict():
								value = DeepChainMap(value, sharedValue).to_dict()
							case DeepChainMap():
								value = sharedValue.to_dict(value)
							case _:
								value = sharedValue
					else:
						statefulType = prop.returnsFilter(Stateful)
						if (
							prop.isStatefulReference
							and isinstance(value, statefulType.singleStatefulItemTypes)
							and statefulType is not UnsetReturn
						):
							statefulType: Type[Stateful]
							subProp = statefulType.findPropForType(type(value))
							if isinstance(sharedValue, DeepChainMap) and subProp is not None:
								value = sharedValue.to_dict({subProp.key: value})

				prop.setState(self, value, afterPool=afterPool)
				self._unset_keys_.discard(prop)
		if len(unwraps) == 1:
			prop = unwraps[0]
			prop.setState(self, state)
			self._unset_keys_.discard(prop)
		elif len(unwraps) > 1:
			raise ValueError("Multiple unwrapped properties found", unwraps, state)

		if afterPool.can_execute:
			afterPool.execute()
		return

	# Section .getItemState
	def getItemState(self, encode: bool = True, **kwargs):
		exclude = get(kwargs, "exclude", "remove", "hide", default=set(), castVal=True, expectedType=set)
		exclude = exclude | getattr(self, "__exclude__", set())

		if (parent := self.statefulParent) is not None:
			exclude = exclude | getattr(parent, "__child_exclude__", set())

		items = {k: v for k, v in self.statefulItems.items() if v.actions & {"get"}}
		items = dict(sorted(items.items(), key=lambda i: (i[1].sortOrder(type(self)), i[0])))

		values = []
		for prop in items.values():
			k, v = prop.getState(self, encode=encode)
			values.append((k, v))

		shared = self.shared

		state = dict(values)
		state.pop("_", None)

		stateKeys = set(state.keys())

		items = {kk.pop(): v for k, v in items.items() if (kk := {v.name, v.key} & stateKeys)}

		s = {}
		for prop, (key, value) in zip(items.values(), state.items()):
			if key in exclude or prop.excluded:
				continue
			if (sharedValue := shared.get(key, None)) is not None and not isinstance(value, Stateful):
				if isinstance(sharedValue, DeepChainMap):
					sharedValue = sharedValue.to_dict()
				if isinstance(value, type(sharedValue)) and value == sharedValue:
					continue
				if prop.checkType(sharedValue, prop.decodesTo):
					encodedValue = prop.encodeValue(value, self)
					if sharedValue == encodedValue:
						continue
				else:
					breakpoint()
			elif sharedValue is not None and prop.encodeValue(sharedValue, self) == value:
				continue
			if prop.expands:
				value = value.state
			if prop.unwraps:
				if (expected := prop.returnsFilter(Stateful, func=issubclass)) is not UnsetReturn:
					if not isinstance(value, dict):
						value = value.state
					else:
						i = [
							p
							for _, p in expected.__state_items__.items()
							if p.singleVal and isinstance(value, p.returns)
						]
						if i:
							value = {i[0].key: value}
						else:
							e = TypeError(f"Unable to determine key for {value} when unwrapping {prop}")
							log.exception(e)
							raise e
				if isinstance(value, Mapping):
					s.update(value)
					continue

			if prop.singleVal:  # TODO: Add support for 'singleForceCondition'
				if prop.singleVal == "force":
					return value
				if len(state) == 1:
					return value

			# if the value has nothing, don't include it unless required
			if isinstance(value, Sized) and not isinstance(value, Stateful) and len(value) == 0 and not prop.required:
				continue
			# elif isinstance(value, Stateful) and isinstance(s := value.getItemState(encode=False), Sized) and len(s) == 0 and not prop.required:
			# 	continue
			s[key] = value
		return s

	@property
	def state(self) -> Dict[str, Any]:
		state = self.getItemState()
		return state

	def encodedState(self, exclude: Set[str] = None, deepExclude: bool | Set[str] = False) -> Dict[str, str | int | float | bool | None]:
		exclude = exclude or set()
		state = self.getItemState(exclude=exclude)
		tag = self.__tag__
		match deepExclude:
			case bool() if deepExclude:
				deepExclude = exclude
			case str():
				deepExclude = {deepExclude}
			case _:
				deepExclude = None
		match state:
			case dict():
				if tag is not ... and tag != 'Stateful' and isinstance(state, Mapping):
					state = {'type': tag, **state}
		state = {
			k: v.encodedState(exclude=deepExclude, deepExclude=deepExclude) if isinstance(v, Stateful) else v
			for k, v in state.items()
		}
		return state

	def encodedYAMLState(self, exclude: Set[str] = None, sort: bool = False) -> dict:
		exclude = exclude or set()
		with TemporaryFile(mode="w+", encoding='utf-8') as f:
			try:
				state = self.getItemState(exclude=exclude)
				yaml.dump(state, f, Dumper=StatefulDumper, default_flow_style=False, allow_unicode=True)
				f.seek(0)
				loader = type(self).__loader__(f.read())
				if sort:
					return sortDict(loader.get_data())
				return loader.get_data()
			except Exception as e:
				log.exception(e)
				raise e

	@state.setter
	def state(self, state: Dict[str, Any]) -> None:
		if (tag := getattr(type(self), "__tag__", ...)) is not ... and isinstance(state, dict):
			state.pop("type", None)
		if isinstance(state, dict) and (shared := state.pop("shared", None)) is not None:
			self.shared = shared
		self.setItemState(state)
		self._afterSetState()

	@classmethod
	def representer(cls, dumper: Dumper, data):
		state = data.state
		tag = getattr(type(data), "__tag__", None)
		if tag is not None:
			subtag = getattr(data, "subtag", None)
			if subtag is not None:
				tag = f"{tag}.{subtag}"
		match state:
			case bool(d):
				return dumper.represent_bool(d)
			case dict(d):
				if tag not in {..., "Stateful"}:
					d = {"type": tag, **d}
				return dumper.represent_dict(d.items())
			case str(d):
				return dumper.represent_str(d)
			case int(d):
				return dumper.represent_int(d)
			case float(d):
				return dumper.represent_float(d)
			case list(d):
				return dumper.represent_list(d)
			case tuple(d):
				return dumper.represent_tuple(d)
			case set(d):
				return dumper.represent_set(d)
			case _:
				raise NotImplementedError

	@classmethod
	def loader(cls, loader: StatefulLoader, data):
		match data:
			case ScalarNode() as d:
				value = loader.construct_yaml_bool(d)
			case MappingNode() as d:
				item = cls(parent=loader.currentNode)
				with loader.dive(item) as childLoader:
					item.state = childLoader.construct_mapping(d, deep=True)
				return item
			case _:
				raise NotImplementedError

	def loadState(self, state):
		yield self

	@classmethod
	def findPropForType(cls, type_: Type) -> StateProperty:
		return next((v for v in cls.singleStatefulItems.values() if v._varifyReturnType(type_, issubclass)), None)

	@classmethod
	def default(cls) -> DefaultState:
		try:
			return cls.__default_states__[cls]
		except KeyError:
			cls.__default_states__[cls] = default = DefaultState(
				{
					v.name: d
					for v in cls.__state_items__.values()
					if (d := v.default(cls)) is not UnsetDefault and not v.excludedFrom(cls) or v.required
				}
			)
			return default

	@classmethod
	@lru_cache()
	def _defaults(cls) -> dict:
		return {i.key: i for i in cls.__state_items__.values() if not i.allowNone and i.hasDefault(cls)}

	@classmethod
	@lru_cache()
	def findTag(cls, tag: str) -> Type['Stateful'] | None:
		tag, *sub_tag = tag.split('.', 1)
		subclasses = sorted(
			(
				i
				for i in (cls, *cls.__subclasses__(deep=True))
				if getattr(i, "__tag__", "_") == tag or i.__name__.casefold() == tag.casefold()
			),
			key=lambda i: len(i.__mro__),
		)
		return next(iter(subclasses), None)

	@cached_property
	def defaultSingles(self) -> Dict[str, Any]:
		return {v: v.default(type(self)) for v in self.statefulItems.values() if v.singleVal}

	# Section .prep_init
	##@profile
	def prep_init(self, kwargs):
		m = {'parent': kwargs.pop('stateParent', None), 'key': kwargs.pop('stateKey', None)}

		# search the frame stack for the first instance of a Stateful object
		# outerFrames = inspect.getouterframes()
		for frame in FrameIterator(inspect.currentframe(), info=False):
			if 'self' in frame.f_locals:
				if m['parent'] is None and isinstance(frame.f_locals['self'], Stateful):
					statefulParent = frame.f_locals['self']
					if statefulParent is not self:
						m['parent'] = statefulParent
				elif frame.f_locals['self'] is m['parent'] and m['key'] is None and m['parent'] is not None:
					break
				elif m['key'] is None and isinstance(frame.f_locals['self'], StateProperty):
					key = frame.f_locals['self']
					if key is getattr(type(m['parent']), key.name, None):
						m['key'] = key
			if all(i is not None for i in m.values()):
				break

		self.statefulParent = m['parent']
		self.__state_key__ = m['key']
		code = type(self).__init__.__code__
		self._set_state_items_ = set()
		initVars = set(code.co_varnames[: code.co_argcount])
		for key, prop in type(self)._defaults().items():
			default = prop.default(type(self))
			if key in initVars:
				continue
			elif key not in kwargs:
				if prop.isStatefulReference:
					if isinstance(default, Mapping) and not isinstance(default, DefaultState):
						value = DeepChainMap(default).to_dict()
					else:
						value = {}
				else:
					value = default
			elif kwargs[key] is UnsetDefault or kwargs[key] is None:
				value = default
			else:
				value = kwargs[key]
			if (d := getattr(value, "default", UnsetDefault)) is not UnsetDefault:
				if isinstance(d, Callable) and d.__code__.co_argcount <= 1:
					value = d()
				else:
					value = d

			if prop.unwraps and isinstance(value, Mapping):
				kwargs.update(value)
			else:
				kwargs[key] = value

		return kwargs

	def rateConfig(self, config: Mapping[str, Any]) -> float:
		props = {p.key: p for p in self.statefulItems.values() if p.key in config}
		score = 0
		for key, value in config.items():
			prop = props[key]
			ownValue = prop.fget(self)
			if prop.isStatefulReference and isinstance(ownValue, Stateful):
				score += ownValue.rateConfig(value)
			else:
				value = prop.decodeValue(value)
				score += prop.scoreValue(self, value)
		return score

	def __del__(self):
		if self._actionPool.up is not self._actionPool:
			self._actionPool.up.remove(self._actionPool)

	def __rich_repr__(self, exclude: set = None):

		exclude = exclude or set()
		for i in sorted(self.__repr_keys__, key=lambda x: x.sortOrder(type(self))):
			if i.key in exclude:
				continue
			try:
				yield i.key, i.fget(self)
			except Exception as e:
				continue


class QStatefulMetaclass(StatefulMetaclass, QObjectType):
	pass


class QStateful(QObject, Stateful, metaclass=QStatefulMetaclass):
	pass


OptionType = TypeVar('OptionType')


class SharedOption(Stateful, tag='SharedOption'):
	key: ClassVar[str]
	value: OptionType = None

	def __init_subclass__(cls):
		super().__init_subclass__()
		key = cls.__name__.replace('Shared', '')
		cls.key = key
		cls.__tag__ = f"Shared{key.title()}"
		cls.__loader__.add_constructor(f"{cls.__tag__}", cls.loader)

	# if optionType is not Unset:
	# 	cls.__annotations__['value'] = optionType

	@classmethod
	def loader(cls, loader: StatefulLoader, data):
		data = loader.construct_mapping(data)
		return cls(**data)

	def __init__(self, value: OptionType = Unset, default: Any = Unset):
		self.value = value
		self.default = default
		super().__init__()

	@StateProperty(default=Unset)
	def value(self) -> OptionType:
		return self._value

	@value.setter
	def value(self, value: OptionType):
		changed = value != self._value
		self._value = value
		if changed:
			self.valueChanged()

	@abstractmethod
	def valueChanged(self):
		pass
