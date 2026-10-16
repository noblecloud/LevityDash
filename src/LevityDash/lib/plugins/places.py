"""Places: where a reading was taken.

A place is a dotted path such as ``home.upstairs.bedroom``. Nothing declares
a place; it exists when a device or a connection uses it. Asking for a parent
matches everything under it, so ``home.upstairs`` matches the bedroom and the
office. Matching is on whole segments: ``home.up`` does not match
``home.upstairs``.

See ``docs/tasks/data-model-spec.md``, section 6.
"""
import re
from typing import Dict, Iterable, List, Optional

__all__ = ['PLACE_PATTERN', 'normalizePlace', 'placeContains', 'placesOf', 'identitiesAt']

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


def placesOf(plugins: Iterable) -> Dict[str, str]:
	"""Every ``{identity: place}`` the plugins publish.

	A plugin that knows where its devices are has a ``places`` mapping from
	each device's ``#identity`` to its place. Plugins without one are skipped.
	Each display reads this from its own loaded plugins, so a display in
	remote mode needs the same device config as its backend.
	"""
	found: Dict[str, str] = {}
	for plugin in plugins:
		for identity, place in (getattr(plugin, 'places', None) or {}).items():
			found.setdefault(identity, place)
	return found


def identitiesAt(query: str, plugins: Iterable) -> List[str]:
	"""The identities whose place is ``query`` or sits under it, in a stable order."""
	query = normalizePlace(query)
	if query is None:
		return []
	return sorted(identity for identity, place in placesOf(plugins).items() if placeContains(query, place))
