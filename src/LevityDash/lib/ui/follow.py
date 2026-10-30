"""What every bound setting shares: a value source that feeds a setting, and the bookkeeping to let go of it.

A *bound* setting is a mapping in place of a plain value (``color: {scale, of}``, ``opacity: {of, from, to}``).
Its ``of`` names a key or expression; each new value goes through the bound spec's ``resolve`` and the result is
handed to the setting. The colour (`colors/bound.py`) and number (`bound_number.py`) bindings differ only in what
``resolve`` makes, so they share this and nothing else.
"""
from typing import Any, Callable, Protocol

__all__ = ('Bound', 'Followers', 'ValueFollower')


class Bound(Protocol):
	"""The part of a bound spec a follower needs."""
	of: Any
	fallback: Any

	def resolve(self, value: Any) -> Any:
		"""The setting for ``value``, or None when it has no setting to give (no number yet)."""


class ValueFollower:
	"""Holds a bound spec's value source and hands each new setting to ``apply`` (on the GUI thread).

	``close()`` releases the source. With no source, or before a value arrives, ``apply`` is not called: the
	item keeps what it was given (the spec's fallback).
	"""

	def __init__(self, bound: Bound, apply: Callable[[Any], None], label: str = 'setting'):
		from LevityDash.lib.valuesource import openValueSource
		from LevityDash.lib.stateful import Binding

		self._bound = bound
		self._apply = apply
		self._binding = None
		if (source := openValueSource(bound.of, f'{label} value', 'it keeps its fallback')) is not None:
			self._binding = Binding(source, self._deliver)

	def _deliver(self, value: Any) -> None:
		setting = self._bound.resolve(value)
		if setting is None:
			if self._bound.fallback is not None:
				self._apply(self._bound.fallback)
			return
		self._apply(setting)

	def close(self) -> None:
		if self._binding is not None:
			self._binding.unlink()
			self._binding = None


class Followers:
	"""The open followers of one item, grouped by the element (``owner``) and setting (``name``) that opened them."""

	def __init__(self):
		self._followers: dict[Any, dict[Any, ValueFollower]] = {}

	def _attach(self, owner: Any, name: Any, follower: ValueFollower) -> None:
		self._release(owner, name)
		self._followers.setdefault(owner, {})[name] = follower

	def _release(self, owner: Any, name: Any) -> None:
		if (follower := self._followers.get(owner, {}).pop(name, None)) is not None:
			follower.close()

	def release(self, owner: Any = None) -> None:
		"""Let go of the value sources one element opened."""
		for follower in self._followers.pop(owner, {}).values():
			follower.close()

	def releaseAll(self) -> None:
		for owner in list(self._followers):
			self.release(owner)
