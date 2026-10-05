"""The change record handed to a StateProperty observer.

Pure Python. No Qt, no LevityDash.
"""
from dataclasses import dataclass
from typing import Any

from qolkit import Unset

__all__ = ["Change", "differs"]


@dataclass(frozen=True, slots=True)
class Change:
	"""One real change of a property value. `old` is Unset on the first set."""
	name: str
	old: Any
	new: Any
	owner: Any


def differs(old: Any, new: Any) -> bool:
	"""True when `new` is not the same value as `old`."""
	if old is Unset:
		return True
	if old is new:
		return False
	try:
		return bool(old != new)
	except Exception:
		# Array-like values refuse bool(); treat an unreadable comparison as a change.
		return True
