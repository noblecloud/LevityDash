"""A doubly-linked-list-backed insertion-ordered set."""
from collections.abc import MutableSet
from dataclasses import dataclass, field
from functools import cached_property
from typing import Hashable, Iterable, Optional, TypeVar

T = TypeVar("T")


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

