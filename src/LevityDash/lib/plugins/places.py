"""Places: where a reading was taken.

A place is a dotted path such as ``home.upstairs.bedroom``. Nothing declares
a place; it exists when a device or a connection uses it. Asking for a parent
matches everything under it, so ``home.upstairs`` matches the bedroom and the
office. Matching is on whole segments: ``home.up`` does not match
``home.upstairs``.

See ``docs/tasks/data-model-spec.md``, section 6.
"""
import re
from typing import Optional

__all__ = ['PLACE_PATTERN', 'normalizePlace', 'placeContains']

#: Letters, digits, ``_`` and ``-`` in each segment, segments joined by ``.``.
PLACE_PATTERN = re.compile(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*')


def normalizePlace(value) -> Optional[str]:
	"""The place as written, trimmed and lower-cased, or ``None`` when it is empty.

	Raises ``ValueError`` for text that is not a dotted path, so a typo such as
	``home..bedroom`` is an error where it is written and not a silent miss.
	"""
	if value is None:
		return None
	text = str(value).strip().lower()
	if not text:
		return None
	if PLACE_PATTERN.fullmatch(text) is None:
		raise ValueError(f'{value!r} is not a place: use words joined by dots, like home.upstairs.bedroom')
	return text


def placeContains(query: str, place: str) -> bool:
	"""True when ``place`` is ``query`` or sits under it, by whole segments."""
	return place == query or place.startswith(query + '.')
