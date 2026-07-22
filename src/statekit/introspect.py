"""Frame/type introspection helpers used by StateProperty.

Pure Python - no Qt. `ownerParentClass` needs the real `Stateful` class at
call time (not import time) to resolve a property's owning class from source
context, so it imports it lazily from .core to avoid a circular import at
module-load time (see core.py's module docstring for why StateProperty and
Stateful/StatefulMetaclass live together in one module).
"""
import logging
from functools import lru_cache
from re import search
from sys import _getframe as getframe
from types import FrameType, GenericAlias
from typing import Any, Callable, Iterable, Iterator, Optional, Set, Type, TypeVar
from inspect import FrameInfo, getframeinfo, getsource, getsourcelines, Traceback

try:
	from typing import _GenericAlias
except ImportError:
	from typing import _GenericAlias

from rich.console import Console
from rich.syntax import Syntax

log = logging.getLogger("statekit")

console = Console(
	soft_wrap=True,
	tab_size=2,
	no_color=False,
	force_terminal=True,
	log_time_format="%H:%M:%S",
)


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
		log.debug(f"Creating type {name}")
		_typeCache[name] = type(name, bases, attrs, **kwargs)
	return _typeCache[name]


class FrameIterator:
	_show_info: bool = True
	_current_frame: Optional[FrameType]
	_current_level: int
	max_depth: int

	def __init__(
		self,
		frame: Optional[FrameType] = None,
		info: bool = True,
		max_depth: int = 10,
	):
		self._show_info = info
		self._current_frame: FrameType = frame or getframe(0).f_back
		self.max_depth = max_depth

		# if the self in the current frame is this instance
		# then we need to go up one more frame
		if (
			self._current_frame is not None
			and self._current_frame.f_locals.get("self", None) is self
		):
			self._current_frame = self._current_frame.f_back

		self._current_level = 0

	def __iter__(self) -> Iterator[FrameType]:
		return self

	def __next__(self) -> FrameType | tuple[tuple[Traceback, Traceback], FrameType]:
		if self._current_frame is None:
			raise StopIteration

		next_frame = self._current_frame.f_back
		if next_frame is not None:
			self._current_frame = next_frame
			self._current_level += 1
		else:
			raise StopIteration

		if self._current_level >= self.max_depth:
			raise StopIteration

		if self._show_info:
			return getframeinfo(self._current_frame), self._current_frame
		else:
			return self._current_frame


def search_stack(
	*, name: Optional[str] = None,
	attr: Optional[str] = None,
	frame: Optional[FrameType] = None,
	expected_type: Type[Any] = Any,
	guard: Optional[Callable[[Any], bool]] = None,
) -> Any:
	stack = FrameIterator(frame=frame, info=False)
	for frame in stack:
		obj = frame.f_locals.get(name)
		if obj is not None:
			if attr is None:
				if isinstance(obj, expected_type) and (guard is None or guard(obj)):
					return obj
				found_items = {}
				for attribute_name, attribute_value in obj.__dict__.items():
					if isinstance(attribute_value, expected_type) and (guard is None or guard(attribute_value)):
						return attribute_value
					found_items[attribute_name] = attribute_value
				if found_items:
					return found_items
			else:
				if hasattr(obj, attr):
					attribute_value = getattr(obj, attr)
					if isinstance(attribute_value, expected_type) and (guard is None or guard(attribute_value)):
						return attribute_value
					found_items = {}
					for attribute_name, attribute_value in attribute_value.__dict__.items():
						if isinstance(attribute_value, expected_type) and (guard is None or guard(attribute_value)):
							return attribute_value
						found_items[attribute_name] = attribute_value
					if found_items:
						return found_items
	return None


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
						# A parameterised base like `list[Foo]` evals to a GenericAlias,
						# not a class; issubclass() rejects that (hard error since 3.14).
						# Unwrap to its origin and guard against non-types.
						base = item if isinstance(item, type) else getattr(item, "__origin__", None)
						if isinstance(base, type):
							# Deferred to right before use (not module top)
							# since this branch is only reached for a
							# bracketed-generic base - most calls, including
							# ones from within Stateful's own still-executing
							# class body, never take it. A module-top import
							# would also be circular: core.py imports this
							# module.
							from .core import Stateful
							if issubclass(base, Stateful):
								return item
					if item != "Stateful" and item in _frame.f_locals:
						return _frame.f_locals[item]
	return object


class Conditions(list):
	def __init__(self, prop: 'StateProperty'):
		self.prop = prop
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
