"""ActionPool - batches StateProperty side-effects until a Stateful object
finishes loading.

Unlike qolkit's generic utilities, this is a genuine statekit concept, not
a general-purpose tool: ActionPoolItemInstance requires is_loading/
state_is_loading, which only mean something for a Stateful object mid
construction/deserialization. Built on qolkit's OrderedSet (the pool's own
membership/iteration order) but the batching semantics themselves are
state-management specific.
"""
import logging
from collections import defaultdict
from contextlib import contextmanager
from enum import Enum, IntEnum
from functools import cached_property, partial, wraps
from types import FunctionType, MethodType
from typing import Callable, ClassVar, Dict, Hashable, Iterable, List, Protocol, Set, Tuple, TypeVar, Union, runtime_checkable
from uuid import UUID, uuid4

from qolkit import OrderedSet

log = logging.getLogger("statekit")


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
