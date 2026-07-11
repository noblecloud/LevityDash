"""StateProperty, Stateful, StatefulMixin, StatefulMetaclass.

The declarative core of statekit. This is one module, not the
property.py/mixin.py split the original plan sketched, because they're a
genuinely bidirectional strongly-connected unit: StateProperty calls into
Stateful/StatefulMetaclass at ~20 call sites (isinstance/issubclass checks,
default resolution, factory construction), and StatefulMetaclass.__new__ /
StatefulMixin.__state_items__ call back into StateProperty just as often.
Splitting them would mean scattering deferred imports across dozens of call
sites for no real decoupling benefit - they only make sense together.

StatefulMetaclass here is pure `type`-based (no Qt). LevityDash.lib.stateful
composes it with Shiboken's QObjectType to get a Qt-compatible variant -
that composition was verified in isolation (real signal/slot behavior,
subclassing) before this module was built. See LevityDash.lib.stateful for
the Qt facade and the domain-specific YAML loaders that stay there.
"""
from collections import ChainMap

import os
from abc import abstractmethod
from builtins import isinstance
from copy import copy, deepcopy
from enum import Enum
from functools import cached_property, lru_cache, partial
from inspect import get_annotations, getsource, getsourcefile, getsourcelines, currentframe, getfullargspec
from operator import attrgetter
from rich.box import SIMPLE_HEAVY
from rich.console import Console, Group
from rich.panel import Panel
from rich.pretty import Pretty
from rich.repr import auto as auto_rich_repr
from rich.syntax import Syntax
from shutil import get_terminal_size
from sys import _getframe as getframe
from tempfile import TemporaryFile
from traceback import extract_stack
from types import GenericAlias, UnionType, FunctionType
from typing import (
	Any, Callable, ClassVar, Dict, Final, Generic, get_args, get_origin,
	get_type_hints, Hashable, Iterable, List, Literal, Mapping, Sequence, Set, Sized, Text, Tuple, Type, TypeAlias,
	TypeVar, Union, Iterator,
)
try:
	from typing import _GenericAlias, _UnionGenericAlias
except ImportError:
	from typing import _GenericAlias
	from typing import _UnionGenericAlias

import logging
from warnings import warn, warn_explicit
import yaml
from yaml import Dumper, MappingNode, ScalarNode

from qolkit import (
	classproperty, clearCacheAttr, DeepChainMap, DotDict, get, guarded_cached_property, OrderedSet, OrUnset,
	recursiveRemove, remove_empty_dicts, sortDict, Unset,
)
from .actions import ActionPool
from .defaults import (
	Default, DefaultGroup, DefaultState, DefaultValue, SourceType, UnsetDefault, UnsetExisting,
)
from .introspect import (
	Conditions, FrameIterator, makeType, makeTypedIterable, ownerParentClass, TypedIterable,
)
from .yaml import StatefulDumper, StatefulLoader

def PASS_FUNC():
	pass

PASS_FUNC = PASS_FUNC.__code__.co_code

STATEFUL_DEBUG = int(os.environ.get("STATEFUL_DEBUG", 0))

console = Console(
	soft_wrap=True,
	tab_size=2,
	no_color=False,
	force_terminal=True,
	width=get_terminal_size((100, 20)).columns - 5,
	log_time_format="%H:%M:%S",
)

log = logging.getLogger("statekit")


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

StatefulReturnType = TypeVar("StatefulReturnType")
StatefulAcceptsType = TypeVar("StatefulAcceptsType")
StatefulEncodesToType = TypeVar("StatefulEncodesToType")
StatefulDecodesFromType = TypeVar("StatefulDecodesFromType")
StatefulDecodedType = TypeVar("StatefulDecodedType")
StatefulEncodedType = TypeVar("StatefulEncodedType")

_Parse_Return_Type = Union[_T, Type | TypedIterable | Iterable[_T]]
Parse_Return_Type: TypeAlias = _Parse_Return_Type[_Parse_Return_Type[_Parse_Return_Type]]
Parse_Special_Type: TypeAlias = Type | GenericAlias | _UnionGenericAlias | _GenericAlias | Iterable[Type | GenericAlias | _UnionGenericAlias | _GenericAlias]
GET_SET = Literal["get", "set", '*']


class InvalidArguments(SyntaxError):
	pass


""" 
TODO
---- 

- Add hooks or one time after functions that can be added from another StateProperty
- hooks can be added to:
	- first, next, or every access
	- first, next, or every set

This item would allow for other stateful items to be updated when a stateful item is accessed or set

"""


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

	__instances__: ClassVar[DotDict] = DotDict()

	def __varifyKwargs(self, kwargs):
		incorrect = []

		if not kwargs.get("allowNone", True) and ("default" not in kwargs or self.class_default(type(self)) is UnsetDefault):
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
						f"{getsourcefile(self.fget)}:{getsourcelines(self.fget)[1]}\n"
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
	def __new__(cls, fget=None, **kwargs) -> "StateProperty":
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
		match kwargs.pop("after", None):
			case FunctionType() as func:
				kwargs["after.func"] = func
			case {"func": func, **rest}:
				kwargs["after.func"] = func
				match rest:
					case {'args': args, 'kwargs': kwargs}:
						kwargs["after.args"] = args
						kwargs["after.kwargs"] = kwargs
					case {"args": args, **kwargs}:
						kwargs["after.args"] = args
					case {"kwargs": kwargs}:
						kwargs["after.kwargs"] = kwargs
					case {}:
						pass
			# case StateProperty() as prop if prop is not self:
			# 	if isinstance(prop_after := prop.options["after"], ChainMap):
			# 		kwargs['after'] = prop_after.new_child(self)
			# 	else:
			# 		kwargs['after'] = ChainMap(DotDict({}), prop_after)

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
		:type repr bool:wex
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
	def __get__(self, obj: 'Stateful', objtype=None) -> Any:
		if obj is None:
			return self
		if self.key not in obj._user_set_state_items_:
			try:
				obj_sources = obj._state_item_sources
				if obj_sources.get(self, Unset) is SourceType.ItemDefault:
					return self.get_item_default(obj)

			except AttributeError:
				pass
		if self.fget is None:
			raise AttributeError("unreadable attribute")
		try:
			return self.fget(obj)
		except AttributeError as e:
			# the object does not have the property set
			if (factory := self.__options.get("factory.func", None)) is not None:
				# try to build from factory
				value = factory(obj)
				obj._state_item_sources[self] = SourceType.Factory
				self.__existingValues__[self.cacheKey(obj)] = value
				self.fset(obj, value)
				try:
					value.__state_key__ = self
				except AttributeError:
					pass
				return value
			elif not self.allowNone:
				# the property is not allowed to be None but the object has no value
				if not self.hasDefault(objtype):
					# the property does not have a default value
					raise SyntaxError(f"Property {self} has no default value and is not set")
		return self.default(type(obj), obj, update_source=True)

	@staticmethod
	def checkType(instance: Any, type_: Type | _GenericAlias | GenericAlias | _UnionGenericAlias):
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

	def __decode__(self, obj, value) -> StatefulAcceptsType:
		decoder = self.__options.get("decode", {})

		if isinstance(decoder, Callable):
			func = decoder
		elif not (func := decoder.get("func", False)):
			return value

		message = f"Decoding {self.key} for {obj.__class__.__name__} from {type(value).__name__}"

		expectedType = get_type_hints(func).get("return", Unset)
		if isinstance(expectedType, str):
			expectedType = None
		if not self.checkType(value, expectedType):
			existing = self.existing(obj)
			if existing is not UnsetExisting and isinstance(existing, Stateful):
				StateProperty.setItemState(existing, value)
				return existing

			parameters = func.__code__.co_varnames[: func.__code__.co_argcount]
			if getattr(func, '__self__', obj) is not obj:
				parameters = parameters[1:]
			match parameters:
				case ["self", *_]:
					value = func(obj, value)
				case ['cls']:
					breakpoint("Should never get here, if you did, something is wrong, fix it")
					value = func(type(obj), value)
				case [var]:
					value = func(value)
				case [self.key | self.name, *args]:
					value = func(value)
				case _:
					raise TypeError(f"Invalid arguments for {func.__name__}: {parameters}")
		message = f"{message} -> {type(value).__name__}"
		log.debug(message)
		return value

	# Section .__set__
	def __set__(self, owner: 'Stateful', value: StatefulAcceptsType, **kwargs):

		_source = SourceType.UserConfig

		if (fset := self.fset) is None:
			raise AttributeError("can't set attribute")

		if isinstance(value, Default):
			if isinstance(value, DefaultValue):
				value = value.value
		elif value is None and not self.__options.get("allowNone", True):
			if "default" not in self.__options:
				raise AttributeError(f"{repr(self)} is not allowed to be None but no default was set")
			value = self.default(type(owner), owner, update_source=True)
			try:
				value = copy(value)
			except TypeError as e:
				if STATEFUL_DEBUG:
					log.exception(e)
				warn(f"A default value was requested but is not a copyable type! There will be dragons!")

			_source = SourceType.Default

		if isinstance(value, DefaultGroup):
			_source = SourceType.Default
			value = value.value

		if self.conditions and not self.testConditions(value, owner, "set"):
			return

		value = self.__decode__(owner, value)

		if (after_pool := kwargs.get('afterPool', None)) is None:
			after_pool = getattr(owner, "action_pool", None)
			if after_pool is None:
				after_pool = getattr(value, "action_pool", None)

		if isinstance(value, Stateful):
			value.__state_key__ = self
			value.__statefulParent = owner

		self.fset(owner, value)

		try:
			owner_sources = owner._state_item_sources
			if owner_sources.get(self, Unset) is SourceType.ItemDefault:
				owner_sources[self] = _source

		except AttributeError:
			pass

		self.schedule_after_func(owner, afterPool=after_pool)

		self.__existingValues__.pop(self.cacheKey(owner), None)
		owner._set_state_items_.add(self.name)

	def schedule_after_func(self, owner: 'Stateful', afterPool: 'ActionPool' = None, **kwargs):
		if after := self.__options.get("after", False):
			args = after.get("args", ())
			kwargs = {**after.get("kwargs", {}), **kwargs}
			if (func := after.get("func", None)) is not None:

				if isinstance(get_annotations(func).get("return", Unset), Callable):
					func = func(owner)

				if isinstance(afterPool, ActionPool):
					if (after_pool_instance := afterPool.instance) is not owner:
						hashable_owner = owner
						while not isinstance(hashable_owner, Hashable):
							hashable_owner = hashable_owner.statefulParent
						if hashable_owner is after_pool_instance:
							pass
						else:
							afterPool = owner.action_pool

					if afterPool.can_execute:
						func(owner, *args, **kwargs)
					elif afterPool.running and len(afterPool) > 0:
						log.debug(f"Adding after function for {self.key} to running after pool")
						afterPool.add(func, caller=self, args=args, kwargs=kwargs)
					else:
						log.debug(f"Adding after function for {self.key} to after pool")
						afterPool.add(func, caller=self, args=args, kwargs=kwargs)
				else:
					log.debug(f"Executing after method for {owner}")

					func(owner, *args, **kwargs)

	# Section .__delete__
	def __delete__(self, obj):
		if self.fdel is None:
			raise AttributeError("can't delete attribute")
		self.fdel(obj)

	def __preGetter(self, func, **kwargs):
		if "match" in kwargs:
			self.optionsFromInit["match"] = kwargs.pop("match")
		self.getter(func, _kwargs=kwargs)

	def getter(self, fget: Callable[[], StatefulReturnType], _kwargs: dict = None) -> 'StateProperty':
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
		if func.__code__.co_code == PASS_FUNC:
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

	def setter(self, fset: Callable[[StatefulAcceptsType], None]) -> 'StateProperty':
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
	def fget(self) -> Callable[[], StatefulReturnType]:
		func = self._get
		if func is None or func.__code__.co_code == PASS_FUNC:
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
	def fset(self) -> Callable[['Stateful', StatefulAcceptsType], None]:
		func = self._set
		if func is None or func.__code__.co_code == PASS_FUNC:
			return getattr(self.parentCls, "fset", None)
		return self._set

	@cached_property
	def fdel(self):
		func = self._del
		if func is None or func.__code__.co_code == PASS_FUNC:
			return getattr(self.parentCls, "fdel", None)
		return self._del

	@cached_property
	def annotations(self):
		annotations = getattr(self.fget, "__annotations__", {})
		annotations.update(getattr(self._get, "__annotations__", {}))
		return annotations

	@cached_property
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

	@cached_property
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

	# Section .default(owner)
	@lru_cache()
	def class_default(self, owner: Type['Stateful']) -> Any | Literal[UnsetDefault]:
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

	def default(
		self,
		owner: Type['Stateful'],
		instance: 'Stateful' = None,
		update_source: bool = True,
		encode: bool = False,
	) -> Any | Literal[UnsetDefault]:
		if instance is not None and (instanceDefault := self.get_item_default(instance)) is not UnsetDefault:
			if update_source:
				instance._state_item_sources[self] = SourceType.ItemDefault
			return instanceDefault
		return self.class_default(owner)

	def _is_decoded_value(self, value: Any) -> bool:
		if (encoded_type := self.returnsFilter(value)) and encoded_type is not UnsetReturn:
			return False
		return True

	def is_default(self, instance: 'Stateful') -> bool:
		default = self.default(type(instance), instance, update_source=False)
		instance_value = self.fget(instance)
		if not self._is_decoded_value(default):
			default = self.__decode__(instance, default)
		if instance_value is None and self.allowNone:
			return True
		if not self._is_decoded_value(instance_value):
			instance_value = self.__decode__(instance, instance_value)

		return default == instance_value or instance_value == default

	@lru_cache()
	def hasDefault(self, owner: Type['Stateful']) -> bool:
		ownerDefaults = getattr(owner, "__defaults__", {})

		if self.has_item_default:
			return True

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

	@property
	def has_item_default(self) -> bool:
		if (item_default := self.__options.get("item_default", None)) is None:
			return False
		if item_default.get("func", None) is None:
			return False
		return True

	def cacheKey(self, obj) -> str:
		return f"{self.key}.{id(obj):x}"

	# Section .existing(owner)
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
						owner._state_item_sources[self] = SourceType.Factory
					except Exception as eF:
						if STATEFUL_DEBUG:
							log.exception(e)
							log.exception(eF)
							raise eF
					else:
						self.fset(owner, fromOwner)
		if fromOwner is not Unset:
			self.__existingValues__[cacheKey] = fromOwner
			return fromOwner
		return fromCache

	@property
	def allowNone(self):
		return self.__options.get("allowNone", True)

	def __testCondition(self, value: Any, owner: Any, condition: DotDict) -> bool:
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
		if STATEFUL_DEBUG:
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
		if (conditions := self.__options.maps[0].get('conditions', None)) is None:
			self.__options["conditions"] = conditions = Conditions(self)
			inheritedConditions = next((i['conditions'] for i in self.options.maps if 'conditions' in i), [])
			conditions.extend(inheritedConditions)
		return conditions

	@cached_property
	def __options(self):
		parentOptions = getattr(self.parentCls, "options", Unset)
		ownOptions = self.optionsFromInit
		ownOptions["conditions"] = Conditions(self)
		if parentOptions is Unset:
			return DeepChainMap(origin=self, origin_map=DotDict(ownOptions))
		return parentOptions.new_child(self, child_map=ownOptions)

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

	def condition(self, func: Callable = Unset, *args, method: str | Iterable[str] = Unset, **kwargs) -> 'StateProperty':
		# if the function is not set
		if func is Unset:
			# check if there is a method/function in args
			if (func_from_args := next((isinstance(i, Callable) for i in args), Unset)) is not Unset:
				func = func_from_args

			elif method is Unset:
				raise TypeError("Must provide a function to condition or use as a decorator")

		if isinstance(method, str):
			method = {method}
		elif isinstance(method, (list, tuple)):
			method = set(method)

		conditions = self.conditions

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

	def after(self, func: Callable[[], None]) -> 'StateProperty':
		self.__options["after.func"] = func
		return self

	def update(self, func) -> 'StateProperty':
		self.__options["update.func"] = func
		return self

	# Section .encode
	def encode(self, *args, **kwargs) -> 'StateProperty':  # TODO: Add warning when function is improperly named
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
	def decode(self, *args, **kwargs) -> 'StateProperty':
		"""Decorator for receiving the decode function

		Note: Decoding should never return a Stateful object

		Parameters
		----------
		func : Callable[[StatefulAcceptsType], StatefulDecodedType]
			The function to decode the value with.
		*args : List[Any]
			Arguments to pass to the decode function.
		**kwargs : Dict[str, Any]
			Keyword arguments to pass to the decode function.
		"""

		if args:
			func, *args = args
		else:
			func = None
		if args or kwargs:
			self.__options["decode.args"] = (func, *args)
			self.__options["decode.kwargs"] = kwargs

		# TODO: Add syntax warning if decode is used on a Stateful item.  Decoding should be
		# handled by the Stateful item's class instead.

		self.__options["decode.func"] = func

		return self

	# Section .factory
	def factory(self, func: Callable[[], StatefulReturnType]) -> 'StateProperty':
		"""Decorator for receiving the factory function

		Parameters
		----------
		func : Callable[[], StatefulReturnType]
			The function to use to create a new value for this property.
		"""
		self.__options["factory.func"] = func
		return self

	def from_factory(self, obj: 'Stateful', update_source: bool = True) -> StatefulReturnType | UnsetReturn:
		if (factory := self.__options.get("factory.func", None)) is not None:
			try:
				value = factory(obj)
				if update_source:
					obj._state_item_sources[self] = SourceType.Factory
				self.__existingValues__[self.cacheKey(obj)] = value

				try:
					value.__state_key__ = self
				except AttributeError:
					pass

			except Exception as e:
				if STATEFUL_DEBUG:
					log.exception(e)
				raise e

			return value
		return UnsetReturn

	@cached_property
	def has_factory(self) -> bool:
		return (factory := self.__options.get("factory.func", None)) is not None and callable(factory)


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
		return self.optionsFromInit.get("key", None)

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
				# if value.is_default(value.default_state):
				# 	return "_", None
			default = self.default(type(owner), owner, update_source=False)

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
			decoder_data = self.__options["decode"]
			match decoder_data:
				case {"func": decoder, **rest}:
					pass
				case FunctionType as decoder:
					pass
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
		if isinstance(expected, _GenericAlias | GenericAlias):
			origin = get_origin(expected)
			if issubclass(origin, Iterable) and expected.__args__:
				return makeTypedIterable(expected)
			else:
				return origin

		# Enum/Flag classes are themselves Iterable (over their members), and
		# a composite/canonical Flag member decomposes via __iter__ too (a
		# single-bit member yields itself) - falling into the generic
		# iterable-of-types check below would recurse into that
		# self-referential iteration forever. Bail out here the same way
		# parse_return_type already does for the class case; also guard
		# instances (e.g. a Flag member reached via recursion) the same way.
		if isinstance(expected, type) and issubclass(expected, Enum):
			return expected,
		if isinstance(expected, Enum):
			return type(expected),

		# The logic here is really dumb...
		# TODO: optimize logic
		if isinstance(expected, Iterable) and not isinstance(expected, str):
			is_valid = True

			# Ensure all the items in the iterable are types
			# Doing this in a list comprehension causes a recursion error
			for t in expected:
				try:
					if not isinstance(t, Type | GenericAlias | _UnionGenericAlias | _GenericAlias | Iterable):
						is_valid = False
						break
				except Exception:
					is_valid = False
					break

			if is_valid:
				return tuple(StateProperty.parse_return_type_special(exp) if not isinstance(exp, _GenericAlias) else exp for exp in expected)

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
							if not isinstance(state, Mapping):
								state = self.decodeValue(state, owner)
							existing.setItemState(state)
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
						self.schedule_after_func(owner, afterPool)
						return
					except Exception as e:
						log.exception(e)
						log.error(f"Unable to set state for {existing}")
						raise e
				elif existing is None:
					# Construct stateful item from factory if it exists
					if self.has_factory and self.isStatefulReference and isinstance(from_factory := self.from_factory(owner), Stateful):
						self.fset(owner, from_factory)
						return self.setState(owner, state, afterPool=afterPool)

		self.__set__(owner, state, afterPool=afterPool)

	@staticmethod
	def setDefault(self, owner):
		if default := self.class_default(type(owner)) is None:
			raise ValueError("Default value is not set")
		self._set(owner, copy(default))

	def item_default(self, *args, **kwargs) -> 'StateProperty':
		"""
		Decorator used to set the item_fault function for a StateProperty.
		This default is instance-specific rather than class specific

		Example
		-------
		>>> class Example(Stateful):
		...
		...     @StateProperty
		...     def var(self) -> StateType:
		...         ...
		...
		...     @var.item_default
		...     def var(self) -> StateType:
		...         ...
		"""

		if args:
			func, *args = args
		else:
			func = None
		if args or kwargs:
			self.__options["item_default.args"] = (func, *args)
			self.__options["item_default.kwargs"] = kwargs
		self.__options["item_default.func"] = func

		return self

	def get_item_default(self, item: 'Stateful') -> UnsetDefault | Any:
		if (item_default := self.__options.get("item_default", None)) is None:
			return UnsetDefault
		if (func := item_default.get("func", None)) is None:
			return UnsetDefault
		args = item_default.get("args", ())
		kwargs = item_default.get("kwargs", {})

		arg_spec = getfullargspec(func)
		if 'self' in arg_spec.args:
			args = (item, *args)

		return func(*args, **kwargs)

	@cached_property
	def docstring(self) -> str:
		return 'shit'
		strings = [self.fget.__doc__ or '']

		def extract_doc_string(func_data: DotDict | FunctionType) -> str:
			match func_data:
				case {'doc': str(doc_string)}:
					return doc_string
				case {'doc': FunctionType() as func} if func.__doc__:
					return func.__doc__
				case {'func': FunctionType() as func} if func.__doc__:
					return func.__doc__
				case FunctionType() as func if func.__doc__:
					return func.__doc__
				case _:
					return ''

		if decoder_func := self.__options.get('decode', {}):
			strings.append('Decoder\n-------')
			strings.append(extract_doc_string(decoder_func))
		if encoder_func := self.__options.get('encode', {}):
			strings.append('Encoder\n-------')
			strings.append(extract_doc_string(encoder_func))
		return '\n'.join(strings)



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


class StatefulMixin:
	"""
	This is a base class for making mixins that add commonly used StatefulProperties to a class.

	Since a Stateful instance can manage itself or other items, Mixins and Submixins should only modify the
	internal state of the instance and any method in a `StatefulMixin` that modifies the presentation or behaviour
	of the item must remain declared as an abstract method until the mixin is mixed into a true Stateful class.

	Example Usage
	-------------

	```python
	class NameMixin(StatefulMixin):
		# Define the methods needed to modify the target item since they will be most
		# likely used as the 'after' argument in a StateProperty
		@abstractmethod
		def do_something(self):
				# Custom implementation based on the requirements of NameMixin
				pass

		@StateProperty(key='name', default='John Doe', after=do_something)
		def name(self) -> str:
				return self._name

		@name.setter
		def name(self, value: str):
				self._name = value

	class Person(NameMixin):
		@abstractmethod
		def do_something(self):
			# Custom implementation based on the requirements of the submixin
			# This method is redeclared as an abstract method
			pass
	
	# Valid Usage
	class Employee(Person, Stateful):
		# The do_something method is no longer abstract since it is defined in Person
		# and must be defined
		def do_something(self):
			# Custom implementation based on the requirements of the submixin
			pass
	
	# Invalid Usage
	# Any method in a StatefulMixin that modifies the item must remain abstract until 
	# the mixin is used with a Stateful class.
	class Customer(Person):
		def do_something(self):
			...
	
	```
	"""

	__state_items__: ClassVar[ChainMap]

	@classmethod
	def __get_abstract_methods__(cls) -> Set[str]:
		abstract_methods = set()
		for parent in cls.__mro__[1:]:
			if hasattr(parent, "__abstractmethods__"):
				abstract_methods |= parent.__abstractmethods__
			else:
				parent_abstract_methods = {k for k, v in parent.__dict__.items() if getattr(v, "__isabstractmethod__", False)}
				abstract_methods |= parent_abstract_methods
		return abstract_methods

	@classmethod
	def __init_subclass__(cls, **kwargs):
		super().__init_subclass__(**kwargs)
		if not issubclass(cls, Stateful):
			abstract_methods = cls.__get_abstract_methods__()
			not_abstract_but_should_be = {k: v for k, v in cls.__dict__.items() if isinstance(v, Callable) and k in abstract_methods and not getattr(v, "__isabstractmethod__", False)}
			if not_abstract_but_should_be:
				raise TypeError(
					f"Class {cls.__name__} must be a subclass of Stateful or all abstract methods must be declared as abstract."
					f"Ensure there is no logic and add the `@abstractmethod` decorator to {', '.join(not_abstract_but_should_be)}", not_abstract_but_should_be
				)

	@classproperty
	def __state_items__(cls):
		return dict(ChainMap(
			*[{k: v for k, v in dict(i.__dict__).items() if isinstance(v, StateProperty)} for i in
				(i for i in cls.__mro__
				 if issubclass(i, StatefulMixin)
				 and i is not StatefulMixin)
				]
		))


# Section StatefulMeta
class StatefulMetaclass(type):
	__state_items__: ChainMap
	__tags__: Set[str] = set()  # TODO: Change this to a Dict[str, Type[Stateful]]
	__sub_tags__: Set[str] = set()
	__loader__ = StatefulLoader
	__dumper__ = StatefulDumper
	__default_states__: Dict[Type['Stateful'], DefaultState]

	def __new__(mcs, name, bases, attrs, **kwargs):
		log.debug(f"Creating stateful class {name}")
		global _typeCache

		if not bases:
			# The true root Stateful class (zero bases - Python's class
			# machinery doesn't include the implicit `object`). Checking the
			# literal name "Stateful" here used to be equivalent, back when
			# there was only ever one class with that name - but the Qt
			# facade's own `class Stateful(statekit.Stateful,
			# metaclass=StatefulMetaclass)` also happens to be named
			# "Stateful", and it has a real base, so `not bases` is the only
			# unambiguous way to tell "this is the actual bootstrap" apart
			# from "this is a subclass that happens to share the name."
			items = {k: v for k, v in attrs.items() if isinstance(v, StateProperty)}
			attrs["__state_items__"] = ChainMap(items)
			newMcs = super().__new__(mcs, name, bases, attrs, **kwargs)
			for item in set(type(i) for i in items.values()):
				item.__owner__ = newMcs
				item.__ownerClass__ = newMcs
			return newMcs

		_bases, bases, mixins = bases, [], []

		for base in _bases:
			if issubclass(base, StatefulMixin) and not issubclass(base, Stateful):
				mixins.append(base)
			else:
				bases.append(base)
		else:
			bases = tuple(bases)
			mixins = tuple(mixins)

		parentCls = Stateful
		statefulParents = [b for b in bases if issubclass(b, (Stateful, StatefulMixin))]
		for base in statefulParents:
			parentCls = base

		if len(statefulParents) == 1:
			items = parentCls.__state_items__.new_child({v.key: v for v in attrs.values() if isinstance(v, StateProperty)})
		elif len(statefulParents) > 1:
			i = [i.__state_items__ for i in statefulParents]
			items = ChainMap({v.key: v for v in attrs.values() if isinstance(v, StateProperty)}, *i)
		else:
			raise TypeError(f"Stateful class {name} must inherit from Stateful")

		propName = f"{name}StateProperty"

		if mixins:
			for mixin in reversed(mixins):
				items.maps.insert(0, mixin.__state_items__)

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

		attrs["__state_items__"] = items
		attrs["__repr_keys__"] = [prop for prop in items.values() if prop.includeInRepr]

		cls = super().__new__(mcs, name, (*mixins, *bases), attrs)

		for propType in {type(v) for v in items.maps[0].values()}:
			if (ownerClass := getattr(propType, "__ownerClass__", None)) is not cls:
				if ownerClass is not None:
					continue
				propType.__ownerClass__ = cls

		if tag := kwargs.get("tag", None):
			if isinstance(tag, str) and '.' in tag:
				parent_tag, tag = tag.split('.', 1)
				assert parent_tag == parentCls.__tag__

				# check to see if the parent has a __tags__ attribute
				if (parent_sub_tags := parentCls.__dict__.get('__sub_tags__', None)) is None:
					parent_sub_tags = parentCls.__sub_tags__ = set()

				assert tag not in parent_sub_tags
				assert issubclass(cls, parentCls)
				parent_sub_tags.add(tag)

				setattr(parentCls, tag.title(), cls)

				tag = f'{parent_tag}.{tag}'

			mcs.__tags__.add(tag)
			cls.__tag__ = tag

		if (representer := attrs.get('representer', None)) is not None:
			dumper = getattr(cls, '__dumper__', None) or StatefulDumper
			if isinstance(cls.__dumper__, list):
				for d in dumper:
					d.add_representer(cls, representer)
			else:
				dumper.add_representer(cls, representer)

		cls.__statePropertyClass__.__ownerClass__ = cls

		log.debug(f"Created stateful class {name}")
		return cls

	@property
	def statefulItems(self) -> Dict[str, StateProperty]:
		if not isinstance(self, type):
			self = type(self)
		return dict(sorted(self.__state_items__.items(), key=lambda x: x[1].sortOrder(self)))

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
	_set_state_items_: set = cached_property(lambda self: set())
	_user_set_state_items_: set = cached_property(lambda self: set())
	_unset_keys_: set = None
	_rawItemState: Dict[str, Any]
	_state_item_sources: Dict[StateProperty, SourceType] = cached_property(lambda self: {})

	statefulItems = StatefulMetaclass.statefulItems
	statefulKeys = StatefulMetaclass.statefulKeys

	statefulParent: "Stateful"
	__statefulParent = None

	def _afterSetState(self):
		pass

	def is_default(self, state_data: Mapping = None) -> bool:
		# TODO: Implement this
		return False

	@property
	def statefulParent(self) -> 'Stateful':
		return self.__statefulParent

	@statefulParent.setter
	def statefulParent(self, value):
		"""
		Setter for stateful_parent.
		This method ensures the child's action pool is moved from an existing stateful_parent
		to the new parent's action pool when the stateful parent is set.
		"""

		if value is not None and not isinstance(value, Stateful):
			raise TypeError(f"statefulParent must be a Stateful, not {type(value)}")
		parent_action_pool: ActionPool = getattr(value, 'action_pool', None)

		if parent_action_pool is not None:
			if (own_action_pool := getattr(self, '_action_pool', None)) is not None:
				own_action_pool.move_to(parent_action_pool)
				assert own_action_pool.up is (parent_action_pool if value is not None else own_action_pool)
			else:
				self._action_pool = parent_action_pool.new(self)
		else:
			if (own_action_pool := getattr(self, '_action_pool', None)) is not None:
				own_action_pool.move_to(None)
				assert own_action_pool.up is own_action_pool

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
		loading = self.is_loading
		if (stateful_parent := self.statefulParent) is not None:
			if stateful_parent is self:
				return loading
			parent_loading = stateful_parent.state_is_loading
		else:
			parent_loading = False
		return loading | parent_loading

	@property
	def action_pool(self) -> ActionPool:

		if (existing := getattr(self, '_action_pool', None)) is None:
			if (parent := self.statefulParent) is not None:
				self._action_pool = existing = parent.action_pool.new(self)
			else:
				self._action_pool = existing = ActionPool(self)
		return existing

		# pool = existing
		# parent_action_pool: ActionPool = getattr(parent := self.statefulParent, 'action_pool', None)
		# assert pool.up is (parent_action_pool if parent is not None else pool)
		# return pool

	# Section .shared
	@StateProperty(key="shared", default=DeepChainMap(), sortOrder=0, repr=False)
	def shared(self) -> DeepChainMap:
		shared = getattr(self, "_shared", None)
		if shared is None:
			parent = self.statefulParent
			if parent is None:
				self._shared = shared = DeepChainMap(origin=self)
			elif (parentShared := getattr(parent, 'shared', None)) is not None:
				ownKeys = set(self.statefulItems) - {'shared'}

				if (key := getattr(self, '__state_key__', None)) is not None and key.key in parentShared:
					localShared = parentShared[key.key]
				else:
					localShared = {}

				localShared.update({k: v for k, v in parentShared.items() if k in ownKeys})
				assert isinstance(parentShared, DeepChainMap)
				self._shared = shared = parentShared.new_child(origin=self, child_map=localShared)
			else:
				self._shared = shared = DeepChainMap(origin=self)
		return shared

	@shared.setter
	def shared(self, value: dict):
		if value.pop('~clear', False):
			self._shared = DeepChainMap(origin=self)
		self.shared.update(value)

	@shared.condition(method={'get'})
	def shared(self, value: DeepChainMap):
		return len(value.originMap) > 0

	@shared.encode
	def shared(self, value: DeepChainMap) -> dict:
		# originMap can hold nested DeepChainMap objects as values (e.g.
		# inherited from a parent's shared map via new_child()/localShared) -
		# flatten those down to plain dicts, otherwise they reach the YAML
		# dumper's generic object fallback and get silently stringified via
		# repr(), corrupting the save file.
		return DeepChainMap(origin_map=value.originMap).to_dict()

	@property
	def ownShared(self) -> dict:
		return recursiveRemove(dict(self._shared.originMap.items()), self._shared_values)

	@StateProperty(key="type")
	def type(self) -> str:
		return type(self).__tag__

	@type.condition(method='get')
	def type(self, value: str) -> bool:
		return value not in {..., None, Stateful, 'Stateful'}

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

		if isinstance(state, DeepChainMap):
			state = state.to_dict()

		shared = getattr(self, 'shared', Unset) or DeepChainMap()
		afterPool: ActionPool = self._action_pool
		unwraps = []
		for prop in items.values():

			# Set state item source
			if prop not in self._state_item_sources:
				# TODO: Add better conditions for this.  I believe Currently items added in
				#  the prep_kwargs stage are flagged as user config here?
				if prop.key in state:
					self._state_item_sources[prop] = SourceType.UserConfig
				else:
					self._state_item_sources[prop] = SourceType.Default

			if prop.unwrappedKeys:
				if prop.key not in prop.unwrappedKeys:
					pass
				elif prop.unwraps and prop.isStatefulReference and (sub_prop_keys := prop.unwrappedKeys) & set(state.keys()) - {prop.key}:
					return_type = prop.returnsFilter(Stateful)
					unwraps.append(prop)
					if len(state) == 1:
						self._unset_keys_.clear()
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
					# Update the item with the shared value if it is the same type
					sharedType = type(sharedValue)
					sharedType = sharedType if not issubclass(sharedType, DeepChainMap) else dict
					if isinstance(value, sharedType):
						self._state_item_sources[prop] = SourceType.Shared
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
							subProp = statefulType.findPropForType(type(value))
							if isinstance(sharedValue, DeepChainMap) and subProp is not None:
								self._state_item_sources[subProp] = SourceType.Shared
								value = sharedValue.to_dict({subProp.key: value})

				prop.setState(self, value, afterPool=afterPool)
				value: Stateful
				self._unset_keys_.discard(prop)
		match len(unwraps):
			case 0:
				pass
			case 1:
				prop = unwraps[0]
				if isinstance(prop_value := prop.fget(self), Stateful):
					prop_value.setItemState(state, afterPool=afterPool)
				elif isinstance(state, Mapping):
					prop.setState(self, state, afterPool=afterPool)
				else:

					raise NotImplementedError(f"Unable to set state for type '{type(self).__name__}' with state: {state}")
				self._unset_keys_.discard(prop)
			case _:
				raise ValueError("Multiple unwrapped properties found", unwraps, state)

		assert len(self._unset_keys_) == 0, f"Unable to set state for {self} with {state}"
		self._unset_keys_.clear()

		if afterPool.can_execute:
			afterPool.execute()
		return

	# Section .getItemState
	def getItemState(self, encode: bool = True, add_values: dict = None, remove_values: dict = None, **kwargs):
		add_values = add_values or {}
		remove_values = remove_values or {}
		exclude = get(kwargs, "exclude", "remove", "hide", default=set(), castVal=True, expectedType=set)
		exclude = exclude | getattr(self, "__exclude__", set())

		if (parent := self.statefulParent) is not None:
			exclude = exclude | getattr(parent, "__child_exclude__", set())

		items = {k: v for k, v in self.statefulItems.items() if v.actions & {"get"}}
		items = sorted_items = dict(sorted(items.items(), key=lambda i: (i[1].sortOrder(type(self)), i[0])))

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
			if (sharedValue := shared.get(key, None)) is not None:
				if not isinstance(value, Stateful):
					if isinstance(sharedValue, DeepChainMap):
						sharedValue = sharedValue.to_dict()
					if isinstance(value, type(sharedValue)) and value == sharedValue:
						continue
					if prop.checkType(sharedValue, prop.decodesTo):
						encodedValue = prop.encodeValue(value, self)
						if sharedValue == encodedValue:
							continue
					else:
						raise TypeError(f'Failed parsing Shared Value')
				elif isinstance(value, Stateful) and value.state == sharedValue:
					continue
				elif sharedValue is not None and prop.encodeValue(sharedValue, self) == value:
					continue
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

		if add_values:
			should_resort = False
			if isinstance(add_values, Mapping):
				if set(add_values.keys()) & set(s.keys()) != set(add_values.keys()):
					should_resort = True
				s.update(add_values)
			if should_resort:
				s = {k: s[k] for k in sorted_items.keys() if k in s}
		return s

	@property
	def state(self) -> Dict[str, Any]:
		state = self.getItemState()
		return state

	def encodedState(self, exclude: Set[str] = None, deep_exclude: bool | Set[str] = False, exclude_value_map: dict = None) -> Dict[str, str | int | float | bool | None]:
		exclude = exclude or set()
		exclude_value_map = exclude_value_map or {}
		state = self.getItemState(exclude=exclude)
		tag = self.__tag__
		match deep_exclude:
			case bool() if deep_exclude:
				deep_exclude = exclude
			case str():
				deep_exclude = {deep_exclude}
			case _:
				deep_exclude = None

		if isinstance(state, Mapping):
			state = {
				k: v.encodedState(exclude=deep_exclude, deep_exclude=deep_exclude, exclude_value_map=exclude_value_map.get(k, None)) if isinstance(v, Stateful) else v
				for k, v in state.items() if v != exclude_value_map.get(k, Unset)
			}
			# remove all the keys that have mapped to empty dictionaries
			return remove_empty_dicts(state)
		elif isinstance(state, type(self).singleStatefulItemTypes):
			return state
		raise TypeError(f"Unable to encode state for {self} with {state}")

	def encodedYAMLState(self, exclude: Set[str] = None, state_override: dict = None, sort: bool = False) -> dict:
		exclude = exclude or set()
		with TemporaryFile(mode="w+", encoding='utf-8') as f:
			try:
				state = state_override or self.getItemState(exclude=exclude)
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
		with self.action_pool:
			self.setItemState(state)
		self._afterSetState()

	@classmethod
	def representer(cls, dumper: Dumper, data):
		if isinstance(data, cls):
			state = data.state
		else:
			state = data
		# tag = getattr(type(data), "__tag__", None)
		# if tag is not None:
		# 	subtag = getattr(data, "subtag", None)
		# 	if subtag is not None and not tag.endswith(subtag):
		# 		tag = f"{tag}.{subtag}"
		match state:
			case bool(d):
				return dumper.represent_bool(d)
			case dict(d):
				# if tag not in {..., "Stateful"}:
				# 	d = {"type": tag, **d}
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
	@lru_cache(maxsize=128)
	def default(cls) -> DefaultState:
		return DefaultState(
			{
				v.name: d
				for v in cls.__state_items__.values()
				if (d := v.class_default(cls)) is not UnsetDefault and not v.excludedFrom(cls) or v.required
			}
		)

	@property
	def default_state(self) -> DefaultState:
		cls_defaults = type(self).default()
		cls_defaults.update({
			prop.name: d for prop in self._item_defaults().values() if (d := prop.get_item_default(self)) is not UnsetDefault
		})
		return DefaultState(cls_defaults)

	@classmethod
	@lru_cache()
	def _defaults(cls) -> dict[str, StateProperty]:
		"""
		Returns a dictionary of all the stateful properties that have defaults
		"""
		return {i.key: i for i in cls.__state_items__.values() if not i.allowNone and i.hasDefault(cls) and not i.excludedFrom(cls)}

	def _item_defaults(self) -> dict[str, StateProperty]:
		cls_defaults = self._defaults()
		cls_defaults.update({i.key: i for i in self.__state_items__.values() if not i.allowNone and i.get_item_default(self) is not UnsetDefault})
		return cls_defaults

	@classmethod
	@lru_cache()
	def findTag(cls, tag: str) -> Type['Stateful'] | None:
		if tag is Ellipsis:
			return None
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
		return {v: v.class_default(type(self)) for v in self.statefulItems.values() if v.singleVal}

	@classmethod
	def set_stateful_info_for_instance(
		cls,
		instance: 'Stateful',
		/,
		parent: 'Stateful' = None,
		key: str | StateProperty = None,
		relationship: str = None,
		args: tuple = None,
		kwargs: dict = None
	) -> None:

		if relationship == 'child':
			if isinstance(parent, Stateful):
				instance.statefulParent = parent
				return
			raise TypeError(f"Stateful instance must be a Stateful, not {type(parent)} if relationship is 'child'")

		args = args or ()
		kwargs = kwargs or {}

		if isinstance(key, str):
			key = getattr(type(parent), key, None)
		if isinstance(key, StateProperty):
			if not isinstance(instance, key.returns):
				raise TypeError(f"Stateful instance must be of type {key.returns}, not {type(instance)}")

		m = {'parent': parent, 'key': key}

		# search the frame stack for the first instance of a Stateful object
		# outerFrames = inspect.getouterframes()
		count = 0

		for frame in FrameIterator(currentframe(), info=False):
			if 'self' in frame.f_locals:
				if m['parent'] is None and isinstance(frame.f_locals['self'], Stateful):
					statefulParent = frame.f_locals['self']
					if statefulParent is not instance:
						m['parent'] = statefulParent
				elif m['key'] is None and isinstance(frame.f_locals['self'], StateProperty):
					key = frame.f_locals['self']
					if key is getattr(type(m['parent']), key.name, None):
						if not isinstance(instance, key.returns):
							continue
						m['key'] = key
				elif frame.f_locals['self'] is m['parent'] and m['key'] is None and m['parent'] is not None:
					count += 1
					if count > 2:
						break
			if all(i is not None for i in m.values()):
				break

		instance.statefulParent = m['parent']
		instance.__state_key__ = m['key']

	# Section .prep_init
	def prep_init(
		self,
		args: tuple = None,
		kwargs: dict = None,
		stateful_parent: 'Stateful' = None,
		stateful_key: str = None,
		relationship: str = None,
	) -> None:
		self._set_state_items_ = set()
		Stateful.set_stateful_info_for_instance(
			self, parent=stateful_parent, key=stateful_key, args=args, kwargs=kwargs, relationship=relationship
		)

	def add_defaults_to_state(self, kwargs: dict) -> dict:

		code = type(self).__init__.__code__
		initVars = set(code.co_varnames[: code.co_argcount])
		for key, prop in self._item_defaults().items():
			# if prop.returns is not UnsetReturn and not isinstance(default, prop.returns):
			# 	default = prop.decodeValue(default, self)
			if key in initVars:
				continue
			elif key not in kwargs:
				default = prop.default(type(self), self, update_source=True)
				if prop.isStatefulReference:
					if isinstance(default, Mapping) and not isinstance(default, DefaultState):
						value = DeepChainMap(default).to_dict()
					else:
						value = {}
				else:
					value = default
			elif kwargs[key] is UnsetDefault or kwargs[key] is None:
				default = prop.default(type(self), self, update_source=True)
				value = default
				self._set_state_items_.add(key)
				self._user_set_state_items_.discard(key)
			else:
				value = kwargs[key]
				self._set_state_items_.add(key)
				self._user_set_state_items_.add(key)
				self._state_item_sources[prop] = SourceType.UserConfig

			if (d := getattr(value, "default", UnsetDefault)) is not UnsetDefault:
				if isinstance(d, Callable) and d.__code__.co_argcount <= 1:
					value = d()
				else:
					value = d
				self._user_set_state_items_.discard(key)
				self._set_state_items_.add(key)

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
		if self._action_pool.up is not self._action_pool:
			self._action_pool.up.remove(self._action_pool)

	def __rich_repr__(self, exclude: set = None):

		exclude = exclude or set()
		for i in sorted(self.__repr_keys__, key=lambda x: x.sortOrder(type(self))):
			key = i.key
			if key in exclude:
				continue

			try:
				default = i.default(type(self), self, update_source=False)
			except Exception as e:
				default = UnsetDefault

			try:
				yield key, i.fget(self), default
			except Exception as e:
				yield key, Unset, default

	def print_suggested_config(self, console: Console = None, **added_items):
		console = console or Console(
			soft_wrap=True,
			tab_size=2,
			no_color=False,
			force_terminal=True,
			width=get_terminal_size((100, 20)).columns - 5,
			record=True,
		)

		state = self.getItemState(add_values=added_items)

		state = self.parent.encodedYAMLState(state_override=state)

		yamlStr = yaml.dump(state, Dumper=StatefulDumper, default_flow_style=False, allow_unicode=True)
		width = max(len(line) for line in yamlStr.split('\n')) + 2
		pretty = Syntax(yamlStr, 'yaml', tab_size=2, background_color='default')
		panel = Panel(pretty, box=SIMPLE_HEAVY, title=f'Example Config', width=width, padding=0)
		previous_record, console.record = console.record, True
		with console.capture() as capture:
			console.print(panel)
		console.record = previous_record
		return capture.get()

