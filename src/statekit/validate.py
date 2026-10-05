"""Validation errors and the ordered decoder.

A StateProperty can reject a proposed value with a reason by raising
StateError. `Stateful.setItemState` catches it per property, logs the item and
the reason, and skips that property. The other properties of the item still
load.

Pure Python. No Qt, no LevityDash.
"""
from typing import Any, Callable

__all__ = ["StateError", "ConditionFailed", "firstOf"]


class StateError(Exception):
	"""A value is not acceptable for a property. `reason` says why."""

	def __init__(self, reason: str, *, prop: Any = None, value: Any = None):
		super().__init__(reason)
		self.reason = reason
		self.prop = prop
		self.value = value


class ConditionFailed(StateError):
	"""A bool `condition` returned False. Carries only a generic reason."""


def firstOf(*forms: Callable[[Any], Any]) -> Callable[[Any], Any]:
	"""Build a decoder that tries each form in order. The first form that accepts wins.

	A form accepts a value by returning a result. It rejects the value by
	raising StateError, ValueError, TypeError or KeyError. If every form
	rejects the value, the decoder raises one StateError that lists each reason.

	>>> parse = firstOf(float, lambda text: text.strip("{}"))
	"""

	def decode(value):
		reasons = []
		for form in forms:
			try:
				return form(value)
			except (StateError, ValueError, TypeError, KeyError) as e:
				name = getattr(form, "__name__", repr(form))
				reasons.append(f"{name}: {getattr(e, 'reason', None) or e}")
		raise StateError(f"{value!r} matched none of the accepted forms ({'; '.join(reasons)})", value=value)

	return decode
