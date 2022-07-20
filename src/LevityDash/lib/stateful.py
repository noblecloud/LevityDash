from collections import ChainMap
from contextlib import contextmanager
from copy import copy
from datetime import timedelta
from functools import lru_cache, cached_property, partial
from inspect import Traceback, getframeinfo, getsource, getsourcefile, getsourcelines
from operator import attrgetter
from shutil import get_terminal_size
from types import SimpleNamespace, GenericAlias
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
	TypeVar,
	Generic,
	Iterable,
	Union,
	get_args,
	get_origin,
	get_type_hints,
	_GenericAlias,
	_UnionGenericAlias, Text,
)
from re import search
from warnings import warn, warn_explicit

from builtins import isinstance
from sys import _getframe as getframe
from PySide2.QtCore import QObject
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

from LevityDash.lib.log import LevityLogger, debug
from LevityDash.lib.utils import Unset, get, OrUnset, levenshtein
from LevityDash.lib.utils.shared import _Panel, clearCacheAttr, DotDict
from LevityDash.lib.plugins.categories import CategoryItem

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
		return other in self.values

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
		return next((i for i in self.values if i is not None), None)

	@property
	def types(self):
		return set(type(i) for i in self.values)


UnsetDefault: Final = Literal["UnsetDefault"]
UnsetExisting: Final = Literal["UnsetExisting"]


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
	def __init__(self, frame=None):
		self.level = 0
		self.frame = frame or getframe(1)

	def __iter__(self):
		return self

	def __next__(self) -> tuple[Traceback, object]:
		self.level += 1
		if self.level > 10:
			raise StopIteration
		self.frame = self.frame.f_back
		return getframeinfo(self.frame), self.frame


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


ForcedSingleVal = Literal["force"]
StateAction = Literal["get", "set"]
UnsetReturn: Final = Literal["UnsetReturn"]
_T = TypeVar("_T")


class InvalidArguments(SyntaxError):
	pass


class StateProperty(property):
	__owner__: ClassVar[Type]
	__ownerParentClass__: ClassVar[Type]
	_set: Callable[[Any, Any], None] | None
	_get: Callable[[Any], Any] | None
	_del: Callable[[Any], None] | None
	__state: Callable[[Any], Any] | None
	__options: DotDict
	__existingValues__: ClassVar[Dict[int, Any]]
	__alternate_keys__: ClassVar[Dict[str, "StateProperty"]] = {}
	doc: str | None

	__instances__: ClassVar[DotDict] = DotDict()

	def __varifyKwargs(self, kwargs):
		incorrect = []
		if not kwargs.get("allowNone", True) and ("default" not in kwargs or self.default is UnsetDefault):
			log.critical(f"{self.__class__.__name__} {self.name} has no default value and allowNone is False")
			incorrect.append("- allowNone without default")
		if sort := kwargs.get("sort", False) and not self._checkReturnType(Iterable, func=issubclass):
			log.critical(f"{self.__class__.__name__} {self.name} cannot be sorted because it returns a non-iterable")
			incorrect.append("- sort without iterable return")
		if incorrect:
			errors = "\n".join(incorrect)
			raise InvalidArguments(f"{self.__class__.__name__} {self.name} has invalid arguments: \n{errors}")

	def __new__(cls, *args, **kwargs):
		global _typeCache

		inheritFrom = kwargs.pop("inheritFrom", None)
		if inheritFrom is not None:
			cls = type(inheritFrom)
		owner = kwargs.pop("owner", Unset)
		attrs = {"__existingValues__": DotDict()}
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

		cls = makeType(name, (cls,), attrs)

		if altKey := kwargs.pop("altKey", None):
			cls.__alternate_keys__[cls] = altKey
		prop = property.__new__(cls)
		prop.__pre_init__(**kwargs)
		if kwargs:
			return prop.getter
		return prop

	def __pre_init__(self, fget=None, fset=None, fdel=None, doc=None, **kwargs):
		self._get = fget
		self._set = fset
		self._del = fdel
		self.doc = doc
		if (after := kwargs.pop("after", None)) is not None:
			if isinstance(after, Callable):
				kwargs["after.func"] = after
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

	def __repr__(self):
		owner = type(self).__owner__
		return f"@{owner}.{self.key}"

	def __rich_repr__(self):
		yield self.__repr__()
		if self.key != self.name:
			yield "key", self.key
		yield "returns", self.returns[0] if len(self.returns) == 1 else list(self.returns)
		yield "default", self.default
		yield "options", self.options

	def __get__(self, obj, objtype=None):
		if obj is None:
			return self
		if self.fget is None:
			raise AttributeError("unreadable attribute")
		try:
			return self.fget(obj)
		except Exception as e:
			if (factory := self.__options.get("factory.func", None)) is not None:
				value = factory()
			elif not self.allowNone:
				raise e
		return self.default(obj)

	def __decode__(self, obj, value):
		decoder = self.__options.get("decode", {})

		if not (decodeFunc := decoder.get("func", False)):
			return value

		message = f"Decoding {self.key} for {obj.__class__.__name__} from {type(value).__name__}"

		expectedType = decodeFunc.__annotations__.get("return", Unset)
		if isinstance(expectedType, str):
			expectedType = None
		if not isinstance(value, self.parse_return_type(expectedType)):
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

	def __set__(self, owner, value, **kwargs):
		if (fset := self.fset) is None:
			raise AttributeError("can't set attribute")

		if isinstance(value, Default):
			if isinstance(value, DefaultValue):
				value = value.value
		elif value is None and not self.__options.get("allowNone", True):
			if "default" not in self.__options:
				raise AttributeError(f"{repr(self)} is not allowed to be None but no default was set")
			value = self.default(owner)
			try:
				value = copy(value)
			except TypeError:
				warn(f"A default value was requested but is not a copyable type! There will be dragons!")

		if self.conditions and not self.testConditions(value, owner, "set"):
			return

		value = self.__decode__(owner, value)

		self.fset(owner, value)
		self.__existingValues__.pop(f"{self.key}.{id(owner):x}", None)
		owner._set_state_items_.add(self.name)

		if after := self.__options.get("after", False):
			if (func := after.get("func", None)) is not None:
				if (pool := kwargs.get("afterPool", None)) is not None:
					log.verbose(f"Adding function to after pool", verbosity=5)
					pool.append((func, owner))
				else:
					log.verbose(f"Executing after method for {owner}", verbosity=5)
					func(owner)

	def __delete__(self, obj):
		if self.fdel is None:
			raise AttributeError("can't delete attribute")
		self.fdel(obj)

	def __preGetter(self, func, **kwargs):
		self.__varifyKwargs(kwargs)
		if "match" in kwargs:
			self.__options["match"] = kwargs.pop("match")
		self.getter(func)

	def getter(self, fget) -> property:
		if fget is None:
			return self
		clearCacheAttr(self, "fget")
		self._get = fget
		self.__doc__ = fget.__doc__

		options = getattr(self, "optionsFromInit", None)
		if options is None:
			options = self.__options

		if "type" not in options and "return" in fget.__annotations__:
			options["type"] = fget.__annotations__["return"]

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

	def default(self, owner) -> Any | Literal[UnsetDefault]:
		ownerDefaults = getattr(owner, "__defaults__", {})

		if (ownerDefault := ownerDefaults.get(self.key, UnsetDefault)) is not UnsetDefault:
			return ownerDefault

		if (default := self.options.maps[0].get("default", UnsetDefault)) is not UnsetDefault:
			if default is Stateful and (returned := self.returnsFilter(Stateful, func=issubclass)) is not UnsetReturn:
				if (existing := self.existing(owner)) is not UnsetExisting and issubclass(type(existing), returned):
					return existing.default()
				return returned.default()
			if isinstance(default, DefaultGroup):
				return default.value

			return default

		if (
			ownerParentDefault := getattr(ownerDefaults, "parents", {}).get(self.key, UnsetDefault)
		) is not UnsetDefault:
			return ownerParentDefault

		if (parentDefault := self.options.parents.get("default", UnsetDefault)) is not UnsetDefault:
			return parentDefault

		return UnsetDefault

	def existing(self, owner) -> Any | Literal[UnsetExisting]:
		cacheKey = f"{self.key}.{id(owner):x}"
		fromCache = self.__existingValues__.get(cacheKey, UnsetExisting)
		fromOwner = Unset
		if fromCache is UnsetExisting:
			try:
				fromOwner = self.fget(owner)
				if not isinstance(fromOwner, self.returns):
					raise TypeError(f"{self} returned {type(fromOwner)} instead of {self.returns}")
			except Exception as e:
				try:
					if (factory := self.__options.get("factory.func", None)) is not None:
						fromOwner = factory(owner)
						self.fset(owner, fromOwner)
				except Exception as e:
					pass
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

	def testConditions(self, value: Any, owner: _Panel, method: str) -> bool:
		conditions = [i for i in self.options.get("conditions", []) if i.get("method", {}) & {method, "*"}]
		if not conditions:
			return True
		if debug and log.VERBOSITY == 5 and value != self.default(owner):
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
		if "conditions" not in self.__options.maps[0]:
			self.__options["conditions"] = Conditions(self)
		con = DotDict()
		self.__options["conditions"].append(con)
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

	def encode(self, *args, **kwargs):  # TODO: Add warning when function is improperly named
		if args:
			func, *args = args
		else:
			func = None
		if args or kwargs:
			self.__options["encode.args"] = (func, *args)
			self.__options["encode.kwargs"] = kwargs
		self.__options["encode.func"] = func

		return self

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

	def factory(self, func: Callable[[], "Stateful"]):
		self.__options["factory.func"] = func
		return self

	def isDefault(self, _for) -> bool:
		return self.default(_for) == self._get(_for)

	@lru_cache(maxsize=128)
	def sortOrder(self, ownerType):
		typeSortOrder = len([i for i in ownerType.__mro__ if issubclass(i, Stateful)])
		fromOptions = self.__options.get("sortOrder", Unset)
		if fromOptions is not Unset and fromOptions < 0:
			fromOptions = 100 - fromOptions
		sort = fromOptions << OrUnset >> typeSortOrder + 1
		return sort

	@cached_property
	def key(self):
		return self.__options.get("key", None) or self.name

	@property
	def name(self):
		return getattr(self, "_name_", None) or self.__findName()

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
		try:
			return self._checkReturnType(Stateful, issubclass)
		except TypeError:
			return False

	def getState(self, owner, encode: bool = True):
		options = self.__options
		key = self.key
		encoder = options.get("encode", {})

		if self.__state is not None:
			value = self.__state(owner)
		else:
			value = self.fget(owner)

		if encode and (encodeFunc := encoder.get("func", False)):
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

		# check default
		if not self.required:
			default = self.default(owner)
			if value == default:
				return "_", None
			if isinstance(default, Default) and isinstance(value, Stateful):
				if value.testDefault(default):
					return "_", None

		# check conditions
		if not self.testConditions(value, owner, "get"):
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
			if not self._checkReturnType(Iterable, func=issubclass):
				log.warning(f"{self} is marked to be sorted, the return type is not iterable")
			if isinstance(sort, Callable):
				return partial(sorted, key=sort)
			elif isinstance(sort, str):
				return partial(sorted, key=attrgetter(sort))
			else:
				return sorted

	@staticmethod
	def getItemState(owner, **kwargs):
		exclude = get(kwargs, "exclude", "remove", "hide", default=set(), castVal=True, expectedType=set)
		exclude = exclude | getattr(owner, "__exclude__", set())

		items = {k: v for k, v in owner.statefulItems.items() if v.actions & {"get"}}
		items = dict(sorted(items.items(), key=lambda i: (i[1].sortOrder(type(owner)), i[0])))

		values_ = [prop.getState(owner, encode=True) for prop in items.values()]
		state = dict(values_)
		state.pop("_", None)

		stateKeys = set(state.keys())

		items = {kk.pop(): v for k, v in items.items() if (kk := {v.name, v.key} & stateKeys)}

		s = {}
		for prop, (key, value) in zip(items.values(), state.items()):
			if key in exclude or prop.excluded:
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
			if isinstance(value, Sized) and len(value) == 0 and not prop.required:
				continue
			s[key] = value

		return s

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

	@property
	def returns(self) -> tuple[type] | UnsetReturn:
		expected = get_type_hints(self._get).get("return", None) or get_type_hints(self.fget).get("return", UnsetReturn)
		expected = self.parse_return_type(expected)
		expectedCombined = set()
		for e in expected:
			if isinstance(e, tuple):
				expectedCombined.update(e)
			else:
				expectedCombined.add(e)
		return tuple(expectedCombined) or (UnsetReturn,)

	@staticmethod
	def parse_return_type(expected) -> tuple[type]:
		if isinstance(expected, (_UnionGenericAlias)):
			expected = get_args(expected)
			expected = tuple(StateProperty.parse_return_type(e) for e in expected)
		elif isinstance(expected, (GenericAlias, _GenericAlias)):
			expected = get_origin(expected)
		if not isinstance(expected, Iterable):
			expected = (expected,)
		return expected

	def _checkReturnType(self, _type: _T, func: Callable[[Any, type], bool] = isinstance) -> bool:
		for _t in self.returns:
			if isinstance(_t, (GenericAlias, _GenericAlias)):
				_t = get_origin(_t)
			if isinstance(_t, tuple):
				return any(func(_t, _type) for _t in _t)
			if func(_t, _type):
				return True
		return False

	def returnsFilter(self, _type: _T, func: Callable[[Any, type], bool] = None) -> _T | UnsetReturn:
		if func is None:
			func = issubclass if isinstance(_type, type) else isinstance
		try:
			return next((i for i in self.returns if func(i, _type)), UnsetReturn)
		except TypeError:
			return UnsetReturn

	def setState(self, owner, state, afterPool: list = None):
		if UnsetReturn not in self.returns:
			if (existing := self.existing(owner)) is not UnsetExisting:
				if updateFunc := self.__options.get("update.func", False):
					updateFunc(owner, state)
					return
				if (stateVar := getattr(type(existing), "state", None)) and (
					fset := getattr(stateVar, "fset", None)
				) is not None:
					try:
						fset(existing, state)
						return
					except Exception as e:
						log.exception(e)
						log.error(f"Unable to set state for {existing}")
						raise e

		self.__set__(owner, state, afterPool=afterPool)

	@staticmethod
	def setItemState(owner: "Stateful", state: Mapping[str, Any], *args, **kwargs):
		if isinstance(state, Stateful):
			state = state.state

		if not isinstance(state, Mapping):
			acceptedSingleValueTypes = tuple(
				i for j in (p.returns for p in owner.statefulItems.values() if p.singleVal) for i in j
			)
			if isinstance(state, acceptedSingleValueTypes):
				# try:
				item = [
					v
					for v in owner.statefulItems.values()
					if v.actions & {"set"} and v.singleVal and isinstance(state, v.returns)
				].pop()
				item.setState(owner, state, afterPool=kwargs.get("afterPool", []))
				return owner
			# except Exception as e:
			# 	log.exception(e)
			# 	log.error(f"Unable to set state for {state}")
			# 	return
			raise TypeError(f"Unable to set state for {owner} with {state}")

		items = {
			k: v
			for k, v in owner.statefulItems.items()
			if bool(v.actions & {"set"}) and (v.key in state or v.name in state or v.unwraps or v.singleVal)
		}
		getOnlyItems = {
			v.key
			for v in owner.statefulItems.values()
			if "set" not in v.actions and not v._checkReturnType(Stateful, issubclass)
		}

		if isinstance(state, dict) and getOnlyItems:
			for i in getOnlyItems & set(state.keys()):
				state.pop(i, None)

		afterPool = []
		match state:
			case dict():
				unwraps = []
				setKeys = set()
				for prop in items.values():
					if prop.unwraps:
						unwraps.append(prop)
						if len(state) == 1:
							break
						continue
					propKey = prop.key
					if propKey not in state:
						continue
					else:
						prop.setState(owner, state.pop(propKey), afterPool=afterPool)
					setKeys.add(propKey)
				if len(unwraps) == 1:
					prop = unwraps[0]
					prop.setState(owner, state)
				elif len(unwraps) > 1:
					raise ValueError("Multiple unwrapped properties found", unwraps, state)

			case list():
				if prop := [i for i in items.values() if i.options.get("singleVal", False) == "force"]:
					prop[0].setState(owner, state)

		afterPool: List[Tuple[Callable, Stateful]]
		if afterPool:
			log.verbose(f"Executing {len(afterPool)} items in afterPool for {owner.__class__.__name__}", verbosity=5)
			funcs = [partial(f, owner) for f, _ in afterPool]
			for f in funcs:
				f()

		return

	def setDefault(self, owner):
		if default := self.default(owner) is None:
			raise ValueError("Default value is not set")
		self._set(owner, copy(default))


QObjectType = type(QObject)


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


class StatefulMetaclass(QObjectType, type):
	__state_items__: ChainMap
	__tags__: Set[str] = set()
	__loader__ = StatefulLoader
	__dumper__ = StatefulDumper

	def __new__(mcs, name, bases, attrs, **kwargs):
		log.verbose(f"Creating stateful class {name}", verbosity=5)
		global _typeCache

		if name == "Stateful":
			attrs["__state_items__"] = ChainMap(attrs.get("__state_items__", {}))
			return super().__new__(mcs, name, bases, attrs, **kwargs)

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

		# Create exclusions and inherit parent's exclusions
		exclude = set(attrs.get("__exclude__", {}))
		if ... in exclude or not exclude:
			exclude.discard(...)
			exclude |= getattr(parentCls, "__exclude__", set())
		attrs["__exclude__"] = exclude

		__ownerParentClass__ = getattr(parentCls, "__ownerParentClass__", Stateful)
		propParentClass = getattr(parentCls, "__statePropertyClass__", StateProperty)
		propAttrs = {"__owner__": name, "__ownerParentClass__": __ownerParentClass__, "__existingValues__": {}}

		propClass = makeType(propName, (propParentClass,), propAttrs)
		attrs["__statePropertyClass__"] = propClass

		props = items.new_child({k: v for k, v in attrs.items() if isinstance(v, StateProperty)})

		attrs["__state_items__"] = props

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
	def statefulItems(self) -> Dict[str, StateProperty]:
		return dict(sorted(self.__state_items__.items(), key=lambda x: x[1].setOrder))

	@property
	def annotations(self):
		return {k: v.annotations for k, v in self.__state_items__.items()}


# Section Stateful
@auto_rich_repr
class Stateful(metaclass=StatefulMetaclass):
	__state_items__: ClassVar[ChainMap[Text, StateProperty]]
	__defaults__: ClassVar[ChainMap[str, Any]]
	__tag__: ClassVar[str] = "Stateful"
	_set_state_items_: set

	def __init__(self, parent: Any, *args, **kwargs):
		pass

	def _afterSetState(self):
		pass

	def testDefault(self, other):
		if isinstance(other, DefaultState):
			items = [i for i in self.statefulItems.values() if i.key in other or i.name in other]
			for item in items:
				if not item.isStatefulReference:
					key, ownValue = item.getState(self, False)
					if key != "_":
						otherValue = other.get(item.name, None)
						if not ownValue == otherValue:
							return False
				else:
					ownValue = item.fget(self)
					otherValue = other.get(item.name, UnsetDefault)
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
	def state(self) -> Dict[str, Any]:
		return StateProperty.getItemState(self)

	@state.setter
	def state(self, state: Dict[str, Any]) -> None:
		if (tag := getattr(type(self), "__tag__", ...)) is not ... and isinstance(state, dict):
			state.pop("type", None)
		StateProperty.setItemState(self, state)
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

	@property
	def statefulItems(self) -> Dict[str, StateProperty]:
		return type(self).statefulItems

	@classmethod
	def default(cls) -> DefaultState:
		return DefaultState(
			{
				v.name: d
				for v in cls.__state_items__.values()
				if (d := v.default(cls)) is not UnsetDefault and not v.excludedFrom(cls) or v.required
			}
		)

	def defaultSingles(self) -> Dict[str, Any]:
		return {v: v.default(self) for k, v in self.statefulItems.items() if v.singleVal}

	def prep_init(self, kwargs):
		code = type(self).__init__.__code__
		self._set_state_items_ = set()
		initVars = set(code.co_varnames[: code.co_argcount])
		for key, prop in (
			(i.key, i) for i in self.__state_items__.values() if not i.allowNone and i.default(self) is not UnsetDefault
		):
			if key in initVars:
				continue
			elif key not in kwargs:
				value = {} if prop.isStatefulReference else prop.default(self)
			elif kwargs[key] is UnsetDefault or kwargs[key] is None:
				value = prop.default(self)
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

	def __rich_repr__(self, exclude: set = None):
		exclude = exclude or set()
		for i in sorted(self.__state_items__.values(), key=lambda x: x.sortOrder(type(self))):
			excludeKey = {i, i.name, i.key} & i.excludedFrom(self, exclude) if i.includeInRepr is None else not i.includeInRepr
			if excludeKey:
				continue
			if i.existing(self) is UnsetExisting:
				continue
			yield i.key, i.fget(self), i.default(self)
