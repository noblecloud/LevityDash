"""Small dependency-free utilities lifted out of LevityDash's lib/utils/shared.py.

That module is a large grab-bag that imports Qt at the top (for unrelated
helpers living elsewhere in it), so StateProperty/Stateful couldn't import
these pieces from it directly without dragging Qt into statekit's import
graph - defeating the entire point of the extraction. Each class/function
here was individually verified to have no Qt references before moving.

LevityDash.lib.utils.shared re-exports these so no consumer file changes.
"""
import logging
import re
from collections import ChainMap, defaultdict
from collections.abc import MutableSet
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from functools import cached_property, lru_cache, partial, wraps
from types import FunctionType, MethodType
from typing import (
	Any, Callable, ClassVar, Dict, get_args, Hashable, Iterable, List, Mapping, Optional, Protocol, Set, Tuple, Type,
	TypeVar, Union, runtime_checkable,
)
from uuid import UUID, uuid4

log = logging.getLogger("statekit")

T = TypeVar("T")


@runtime_checkable
class ActionPoolItemInstance(Protocol, Hashable):

	@property
	def is_loading(self) -> bool:
		...

	@property
	def state_is_loading(self) -> bool:
		...

	@cached_property
	def action_pool(self) -> 'ActionPool':
		...


class classproperty:
	"""Read-only computed class-level attribute.

	Replaces the ``@classmethod`` + ``@property`` decorator stack, which
	Python 3.13 removed (chaining classmethod over another descriptor no
	longer works). Works uniformly for access via a class, an instance, or a
	metaclass: the getter always receives the owning class.

	Deliberately duplicated (not imported) from LevityDash.lib._descriptors -
	that module is kept import-free so it can load very early (before the
	utils/log chain exists); re-pointing it at statekit would risk that.
	"""

	def __init__(self, fget: Callable):
		self.fget = fget
		self.__doc__ = getattr(fget, '__doc__', None)

	def __set_name__(self, owner, name):
		self.__name__ = name

	def __get__(self, obj, owner=None):
		if owner is None:
			owner = type(obj)
		return self.fget(owner)


class IgnoreOr(object):

	def __init__(self, name: str):
		self.__name__ = name

	def copy(self):
		return self

	def __copy__(self):
		return self

	def __repr__(self):
		return f'<{self.__name__}>'

	def __or__(self, other):
		return other

	def __ror__(self, other):
		return other

	def __bool__(self):
		return False

	def __neg__(self):
		return self

	def __invert__(self):
		return self

	def __eq__(self, other):
		return self is other

	def __ne__(self, other):
		return self is not other

	def __hash__(self):
		return hash((self.__name__, type(self)))

	def __instancecheck__(self, instance):
		return self is instance

	def get(self, *args, **kwargs):
		return self


Unset = IgnoreOr('Unset')
UnsetKwarg = IgnoreOr('UnsetKwarg')


class Infix:
	def __init__(self, function):
		self.function = function

	def __ror__(self, other):
		return Infix(lambda x, self=self, other=other: self.function(other, x))

	def __or__(self, other):
		return self.function(other)

	def __rlshift__(self, other):
		return Infix(lambda x, self=self, other=other: self.function(other, x))

	def __rshift__(self, other):
		return self.function(other)

	def __call__(self, value1, value2):
		return self.function(value1, value2)

	def __rmatmul__(self, other):
		return Infix(lambda x, self=self, other=other: self.function(other, x))

	def __matmul__(self, other):
		return self.function(other)


def _or(a, b):
	if isinstance(a, IgnoreOr):
		return b
	elif isinstance(b, IgnoreOr):
		return a
	return a


OrUnset = Infix(_or)


def __get(obj: Mapping, key, default=UnsetKwarg):
	"""getter for mappings"""
	if default is not UnsetKwarg:
		return obj.get(key, default)
	return obj.get(key)


def get(
	obj: Mapping | object,
	*keys: [Hashable, ...],
	default: Any = UnsetKwarg,
	expectedType: Type | Any = object,
	castVal: bool = False,
	getter: Callable = __get,
) -> Any:
	"""
	Gets the value of a given key or iterable of keys from an object or mapping.
	Can also cast the value to a specified type and return a default value if
	the key is not found. An expected type can be specified for determining
	the correct value if there are multiple keys.
	"""
	values = tuple(r for key in keys if (r := getter(obj, key, Unset)) is not Unset)
	match len(values):
		case 0:
			if default is Unset:
				raise KeyError(f'{keys} not found in {obj}')
			return default
		case 1:
			value = values[0]
			if castVal:
				try:
					return expectedType(value)
				except TypeError as e:
					log.warning(f'Could not cast {value} to {expectedType}', exc_info=e)
			return value
		case _:
			log.warning(f'Multiple values found for {keys} in {obj}, returning first value.')
			for value in (k for key in keys if isinstance(k := getter(obj, key, Unset), expectedType) or (castVal and k is not Unset)):
				if castVal:
					return expectedType(value)
				return value


class DotDict(dict):

	def __init__(self, *args, **kwargs):
		args = list(args)
		self.parent = kwargs.get('parent', Unset)
		self.key = kwargs.get('key', Unset)
		dicts = [args.pop(i) for i, item in enumerate(list(args)) if isinstance(item, dict)]
		super(DotDict, self).__init__(*args, **kwargs)
		for d in dicts:
			self.update(d)

	@property
	def key(self):
		if self.parent is not Unset:
			return '.'.join([self.parent.key, self.__key])
		return self.__key or ':'

	@key.setter
	def key(self, value):
		value = self.makeKey(value)
		if self.parent:
			parentKey = self.parent.key
		else:
			parentKey = ()
		if len(value) > 1 and value[:-1] == parentKey:
			value = value[-1]
		self.__key = value

	@staticmethod
	@lru_cache(maxsize=1024)
	def makeKey(key: str) -> tuple:
		if isinstance(key, tuple):
			return key
		elif not isinstance(key, str) and isinstance(key, Hashable):
			return key,
		return tuple(re.findall(rf"[\w|\-|\_]+", key), )

	def __setitem__(self, key, value):
		key = self.makeKey(key)
		if len(key) == 1:
			dict.__setitem__(self, key[0], value)
		else:
			if key[0] not in self:
				self[key[0]] = DotDict(key=key[0], parent=self)
			dict.__getitem__(self, key[0]).__setitem__(key[1:], value)

	def __contains__(self, key):
		key = self.makeKey(key)
		if len(key) == 1:
			return dict.__contains__(self, key[0])
		else:
			if key[0] not in self:
				return False
			return dict.__getitem__(self, key[0]).__contains__(key[1:])

	def popValue(self):
		return self.popitem()[1]

	def __getitem__(self, item):
		key = self.makeKey(item)
		if len(key) == 1:
			return dict.__getitem__(self, key[0])
		else:
			if key[0] not in self:
				raise KeyError(key)
			return dict.__getitem__(self, key[0]).__getitem__(key[1:])

	def get(self, key, default: Any = UnsetKwarg):
		key = self.makeKey(key)
		if key in self:
			return self[key]
		else:
			if default is UnsetKwarg:
				raise KeyError
			return default

	def update(self, data: dict):
		for key, value in data.items():
			self[key] = value


def recursiveRemove(existingDict: dict, subtracting: dict) -> dict:
	for key, subtractingValue in subtracting.items():
		existing = existingDict.get(key, None)
		if existing is None:
			continue
		if isinstance(subtractingValue, dict):
			if isinstance(existing, dict):
				if existing == subtractingValue:
					existingDict.pop(key)
				else:
					existingDict[key] = recursiveRemove(existingDict.get(key, {}), subtractingValue)
					if not existingDict[key]:
						existingDict.pop(key)
			elif subtractingValue:
				existingDict[key] = subtractingValue
			else:
				existingDict.pop(key, None)
			continue
		if existing == subtractingValue:
			existingDict.pop(key, None)
	return existingDict


def remove_empty_dicts(d: dict) -> dict:
	return {k: remove_empty_dicts(v) if isinstance(v, dict) else v for k, v in d.items() if v != {}}


class DeepChainMap(ChainMap):
	"""A recursive subclass of ChainMap"""

	def __init__(self, *maps: Mapping, origin: Any = None, origin_map: Mapping = None):
		self._originMap = origin_map or {}
		self.origin = origin
		super().__init__(self._originMap, *maps)

	def __getitem__(self, key):
		submaps = [mapping for mapping in self.maps if key in mapping]
		if not submaps:
			return self.__missing__(key)
		if isinstance(submaps[0][key], Mapping):
			return DeepChainMap(*(submap[key] for submap in submaps))
		return super().__getitem__(key)

	def to_dict(self, d: dict | Mapping = None) -> dict:
		d = d or {}
		for mapping in reversed(self.maps):
			if type(mapping) is not dict:
				mapping = dict(mapping)
			self._depth_first_update(d, mapping)
		return d

	def _depth_first_update(self, target: dict, source: Mapping) -> None:
		if isinstance(source, DeepChainMap):
			source = source.to_dict()
		for key, src_val in source.items():
			if not isinstance(src_val, Mapping):
				target[key] = src_val
				continue
			if key not in target:
				target[key] = {}
			target_val = target.get(key, {})
			if isinstance(target_val, Mapping):
				self._depth_first_update(target_val, src_val)
			else:
				target[key] = src_val

	@property
	def originMap(self) -> dict:
		return self._originMap

	def new_child(self, origin: 'Stateful' = None, child_map: Mapping = None) -> 'DeepChainMap':
		return self.__class__(*self.maps, origin=origin, origin_map=child_map)


def sortDict(d: dict, reverse: bool = False) -> dict:
	return {key: value for key, value in sorted(d.items(), key=lambda x: x[0], reverse=reverse)}


class guarded_cached_property(cached_property):

	def __new__(cls, *args, guardFunc: Callable[[Any], bool] = None, default: Any = None):
		if not args:
			return partial(guarded_cached_property, guardFunc=guardFunc, default=default)
		return cached_property.__new__(cls)

	def _guardFunc(self, instance):
		return instance is not None

	def __init__(self, *args, guardFunc: Callable[[Any], bool] = None, default: Any = None):
		super().__init__(*args)
		self.guardFunc = guardFunc or self._guardFunc
		self.default = default

	def __call__(self, *args, **kwargs):
		pass

	def __get__(self, instance, owner=None):
		value = super().__get__(instance, owner)
		if self.guardFunc(value):
			return value
		else:
			instance.__dict__.pop(self.attrname, None)
			if isinstance(defaultFunc := self.default, Callable):
				if 'self' in get_args(defaultFunc):
					return defaultFunc(instance)
				return self.default()
			elif isinstance(defaultFunc, property):
				return defaultFunc.__get__(instance, owner)
			return self.default


def clearCacheAttr(obj: object, *attr: str):
	for a in attr:
		try:
			del obj.__dict__[a]
			continue
		except AttributeError:
			pass
		except KeyError:
			pass


@dataclass(slots=True)
class Index:

	value: Hashable | None = field(hash=True)
	previous: Optional['Index'] = field(hash=False, compare=False, default=None)
	next: Optional['Index'] = field(hash=False, compare=False, default=None)

	def __post_init__(self):
		if self.previous is None:
			self.previous = self
		if self.next is None:
			self.next = self

	def __iter__(self):
		yield self.value
		yield self.previous
		yield self.next

	def link_after(self, index: 'Index'):
		self.next = index.next
		self.previous = index
		index.next.previous = self
		index.next = self

	def link_before(self, index: 'Index'):
		self.previous = index.previous
		self.next = index
		index.previous.next = self
		index.previous = self


class OrderedSet(MutableSet[T]):

	map = cached_property(lambda self: {})

	def __init__(self, iterable: Iterable[T] = None):
		self.end = end = Index(None)

		if iterable is not None:
			self |= iterable

	def __len__(self):
		return len(self.map)

	def __contains__(self, key: T):
		return key in self.map

	def add(self, key: T, at_beginning: bool = False) -> bool:
		if key not in self.map:
			end = self.end
			if at_beginning:
				curr = end.previous
				curr.next = end.previous = self.map[key] = Index(key, curr, end)
			else:
				curr = end.next
				curr.previous = end.next = self.map[key] = Index(key, end, curr)
			return True
		return False

	def discard(self, key):
		if key in self.map:
			key, prev, nxt = self.map.pop(key)
			prev.next = nxt
			nxt.previous = prev

	def remove(self, key):
		if key not in self.map:
			raise KeyError(key)
		self.discard(key)

	def __iter__(self):
		end = self.end
		curr = end.next
		while curr is not end:
			yield curr.value
			curr = curr.next

	def __reversed__(self):
		end = self.end
		curr = end.previous
		while curr is not end:
			yield curr.value
			curr = curr.previous

	def pop(self, last=True):
		if not self:
			raise KeyError('set is empty')
		key = next(reversed(self)) if last else next(iter(self))
		self.discard(key)
		return key

	def clear(self) -> None:
		self.map.clear()
		self.end = end = Index(None)

	def __repr__(self):
		if not self:
			return f'{self.__class__.__name__}()'
		return f'{self.__class__.__name__}({list(self)!r})'

	def __eq__(self, other):
		if isinstance(other, OrderedSet):
			return len(self) == len(other) and list(self) == list(other)
		return set(self) == set(other)

	def __del__(self):
		self.clear()  # remove circular references

	def __reduce__(self):
		return self.__class__, (list(self),)


SubActionPool = TypeVar('SubActionPool', bound='ActionPool')


class ActionPool(OrderedSet[Callable, SubActionPool]):

	all_pools: ClassVar[Dict[int, 'ActionPool']] = {}

	up: 'ActionPool'
	__len: int = cached_property(lambda self: 0)
	__contextLevel: int = cached_property(lambda self: 0)
	__callbacks: List[Tuple[Callable, Tuple, Dict]] = cached_property(lambda self: [])
	__called_by: Dict[Callable | SubActionPool, Set['StateProperty']] = cached_property(lambda self: defaultdict(set))
	__last_called_by: Dict[Callable | SubActionPool, Set['StateProperty']] = cached_property(lambda self: defaultdict(set))
	sub_maps: Dict[int, SubActionPool] = cached_property(lambda self: {})
	__item_lookup: Dict[ActionPoolItemInstance, Union[SubActionPool, Callable]] = cached_property(lambda self: {})
	__context: Dict[Callable, Tuple[tuple, dict]] = cached_property(lambda self: {})
	uuid: UUID = cached_property(lambda self: uuid4())

	class Status(Enum):
		Idle = 0
		Queued = 1
		Running = 2
		Finished = 3
		Canceled = 4
		Failed = 5
		Removed = 6

	class Priority(IntEnum):
		Low = -1
		Normal = 0
		High = 1

	def __new__(
		cls,
		instance: ActionPoolItemInstance,
		up: 'ActionPool' = None,
		root: 'ActionPool' = None,
		priority: Priority = Priority.Normal,
		trace=None
	):
		if (existing := cls.all_pools.get(id(instance), None)) is None:
			cls.all_pools[id(instance)] = existing = super().__new__(cls)
			return existing
		return existing

	def __init__(
		self,
		instance: ActionPoolItemInstance,
		up: 'ActionPool' = None,
		root: 'ActionPool' = None,
		priority: Priority = None,
		trace=None
	):
		self.status = self.Status.Idle
		self.instance = instance
		self.root = root if root is not None else self
		self.up = up if up is not None else self
		self.priority = priority
		super().__init__()

	@property
	def context(self) -> Dict[Callable, Tuple[tuple, dict]]:
		return self.__context

	@property
	def priority(self) -> Priority:
		return self._priority

	@priority.setter
	def priority(self, value: Priority):
		self._priority = value

	@property
	def up(self):
		return self._up

	@up.setter
	def up(self, value):
		self._up = value

	def _raise_context_level(self):
		self.__contextLevel += 1

	def __enter__(self):
		self.__contextLevel += 1
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self._lower_context_level()

	def _lower_context_level(self):
		self.__contextLevel -= 1
		if self.__contextLevel <= 0:
			self.__contextLevel = 0
			if self.can_execute:
				self._unsafe_execute()
			match self.status:
				case ActionPool.Status.Finished:
					self.status = ActionPool.Status.Idle
				case ActionPool.Status.Running:
					if bool(self) and self.up.status is self.Status.Running:
						self.status = ActionPool.Status.Queued
					else:
						self.status = ActionPool.Status.Failed
				case ActionPool.Status.Queued:
					if self.can_execute:
						match self.up.status:
							case ActionPool.Status.Running | ActionPool.Status.Queued:
								pass
							case _:
								raise NotImplementedError(
									f"ActionPool exited with status {self.status} with items remaining"
									f" but exiting with a parent status of {self.up.status} is not implemented"
								)
				case ActionPool.Status.Idle:
					if self:
						if not self.can_execute:
							self.status = ActionPool.Status.Queued
						else:
							raise RuntimeError(f'ActionPool exited with status {self.status} with items remaining')
				case _:
					raise RuntimeError(f'ActionPool exited with status {self.status}')

	@property
	def context_level(self) -> int:
		if self is self.up:
			return self.__contextLevel
		return self.up.context_level + self.__contextLevel

	@property
	def own_context_level(self) -> int:
		return self.__contextLevel

	def _trickle_up_execute(self):
		up = self.up
		if len(up) and up.status is self.Status.Idle:
			up.execute()

	def __getitem__(self, item: ActionPoolItemInstance | int) -> SubActionPool:
		if (sub_pool := self.sub_maps.get(id(item), None)) is not None:
			return sub_pool
		raise TypeError("ActionPool only supports indexing by ActionPoolItemInstance")

	def __contains__(self, item: Union[SubActionPool, Callable]) -> bool:
		if isinstance(item, ActionPool):
			return id(item.instance) in self.sub_maps
		return super().__contains__(item)

	def __iter__(self):
		sub_pools: Dict['ActionPool.Priority', ActionPoolItemInstance | 'ActionPool'] = defaultdict(list)
		for item in super().__iter__():
			if isinstance(item, ActionPool):
				sub_pools[item.priority].append(item)
			else:
				yield item
		for priority in sorted(sub_pools.keys(), reverse=True):
			for item in sub_pools[priority]:
				yield item

	def __repr__(self):
		return f'{self.__class__.__name__}({type(self.instance).__name__} items: {len(list(self))}, total: {self.total_length})'

	def stats(self):
		name = f'{self.__class__.__name__}({type(self.instance).__name__}'
		stats = {
			'item count': len(list(self)),
			'items': list(self),
			'total': self.total_length,
			'status': self.status.name,
			'callbacks': len(self.__callbacks),
			'callers': self.__called_by
		}
		return name, stats

	def __hash__(self):
		return self.uuid.int

	def __len__(self):
		return self.__len

	def __true_len__(self):
		return super().__len__()

	def __bool__(self) -> bool:
		return bool(self.__len) or any(bool(p) for p in self.sub_maps.values())

	def iter_up(self) -> Iterable['ActionPool']:
		current = self
		while (up := current.up) not in {self, None}:
			yield up
			current = up

	def new(self, instance: ActionPoolItemInstance, at_beginning: bool = False, priority: Priority = Priority.Normal) -> 'ActionPool':
		instance_id = id(instance)
		if (existing := self.sub_maps.get(instance_id, None)) is not None:
			assert existing.up is self
			existing.priority = priority
			return existing
		else:
			self.add((a := ActionPool(instance, trace='new', up=self, root=self.root, priority=priority)), at_beginning=at_beginning)
		return a

	def move_to(self, dest: 'ActionPool'):
		if self.up is dest:
			return
		if self.up is not self:
			self.up.remove(self)

		if dest is self or dest is None:
			self.up = self
			self.root = self
		else:
			dest.add(self)

	def get_context(self, action: Callable) -> Tuple[tuple, dict]:
		return self.__context.get(action, ((), {}))

	def set_context(self, action: Callable, args: tuple = None, kwargs: dict = None):
		self.__context[action] = (args, kwargs)

	def update_context(self, action: Callable, args: tuple = None, kwargs: dict = None):
		# replaces the args and updates the kwargs
		_, e_kwargs = self.__context.get(action, ((), {}))
		e_kwargs.update(kwargs)
		self.__context[action] = (args, e_kwargs)

	def add(
		self,
		action: Callable | SubActionPool,
		at_beginning: bool = False,
		caller: Hashable = None,
		kwargs: dict = None,
		update_kwargs: bool = False,
		args: tuple = None,
		append_args: bool = False,
	) -> bool:
		added = super().add(action, at_beginning=at_beginning)
		match action:
			case FunctionType() | MethodType() | partial():
				self.__called_by[action].add(caller)

				e_args, e_kwargs = self.__context.get(action, ((), {}))
				if update_kwargs:
					e_kwargs.update(kwargs)
				else:
					e_kwargs = kwargs if kwargs is not None else e_kwargs

				if append_args:
					e_args = (*e_args, *args)

				self.__context[action] = (e_args, e_kwargs)

			case ActionPool():
				action.up = self
				action.root = self.root
				self.sub_maps[id(action.instance)] = action

			case _:
				raise TypeError()

		self.__len = self.__true_len__()
		return added

	def discard(self, other):
		super().discard(other)
		if isinstance(other, ActionPool):
			other.up = other
			other.root = other
			self.sub_maps.pop(id(other.instance), None)
		else:
			self.__called_by.pop(other, None)
			self.__context.pop(other, None)

		self.__len = self.__true_len__()

	def clear(self):
		list(map(ActionPool.clear, self.sub_maps.values()))
		self.sub_maps.clear()
		super().clear()
		self.__called_by.clear()
		self.__context.clear()
		self.__callbacks.clear()
		self.__last_called_by.clear()
		self.__len = 0

	def pop(self, last=True):
		popped = super().pop(last)

		if isinstance(popped, ActionPool):
			self.sub_maps.pop(id(popped.instance))
			popped.up = popped
			popped.root = popped
		else:
			self.__called_by.pop(popped, None)
			self.__context.pop(popped, None)

		self.__len = self.__true_len__()
		return popped

	def remove(self, key):
		super().remove(key)

		if isinstance(key, ActionPool):
			sub_pool = self.sub_maps.pop(id(key.instance))
			sub_pool.up = sub_pool
			sub_pool.root = sub_pool
		else:
			self.__called_by.pop(key, None)
			self.__context.pop(key, None)

		self.__len = self.__true_len__()

	@property
	def total_length(self) -> int:
		return sum(sub_map.total_length for sub_map in self.sub_maps.values()) + (self.__true_len__() - len(self.sub_maps))

	@property
	def can_execute(self) -> bool:
		if self.up is self:
			return not self.context_level and not self.instance.is_loading and all(sub_map.can_execute for sub_map in self.sub_maps.values())
		return not self.context_level and not self.instance.state_is_loading and all(sub_map.can_execute for sub_map in self.sub_maps.values())

	@property
	def running(self) -> bool:
		return self.status == self.Status.Running

	def execute(self):
		log.debug(f"Executing {len(self)} items in afterPool for {self.__class__.__name__}")

		with self:
			self._unsafe_execute()

		log.debug(f"Finished executing {len(self)} items in afterPool for {self.__class__.__name__}")

	def _unsafe_execute(self):
		self.status = self.Status.Running
		for action in self:
			# Note: This for loop should handle changes in length during execution
			#       since OrderedSet.__iter__ uses a while loop

			self.__last_called_by[action] = last_called_by = tuple(self.__called_by[action])
			args, kwargs = self.get_context(action)
			args = args or ()
			kwargs = kwargs or {}
			if isinstance(action, ActionPool):
				if not action.own_context_level:
					action.execute()
			elif isinstance(action, partial):
				action()
				self.discard(action)
			else:
				if action.__code__.co_argcount:
					if getattr('action', '__self__', None) is not None:
						action(*args, **kwargs)
					elif isinstance(action, MethodType):
						action(*args, **kwargs)
					else:
						action(self.instance, *args, **kwargs)
				else:
					action()
				self.discard(action)
		while self.__callbacks:
			callback, args, kwargs = self.__callbacks.pop(0)
			callback(*args, **kwargs)
		self.status = self.Status.Finished

	def delete(self):
		self.__delete__(self)

	def __delete__(self, instance):
		self.status = self.Status.Canceled
		for pool in list(self.sub_maps.values()):
			pool.__del__()
		self.up.discard(self)
		try:
			instance.discard(self)
		except Exception:
			pass
		self.clear()

	def add_callback(self, callback: Callable, *args, **kwargs):
		self.__callbacks.append((callback, args, kwargs))


@contextmanager
def block_pools(*pools: ActionPool):
	for pool in pools:
		pool._raise_context_level()
	try:
		yield
	finally:
		for pool in pools:
			pool._lower_context_level()


def defer(func: Callable = None, /, pool_attr='action_pool'):
	if func is None:
		return partial(defer, pool_attr=pool_attr)

	@wraps(func)
	def deferred_wrapper(self, *args, **kwargs):
		if (pool := getattr(self, pool_attr, None)) is not None:
			pool: ActionPool
			if pool.can_execute:
				func(self, *args, **kwargs)
			else:
				if pool.instance is not self:
					pool.add(getattr(self, func.__name__), args=args, kwargs=kwargs)
				else:
					pool.add(func, args=args, kwargs=kwargs)
		else:
			func(self, *args, **kwargs)

	return deferred_wrapper
