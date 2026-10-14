"""Read CSS keywords from `.levity` values.

Qt-free, like the rest of the package. The stack and grid code in the frontend calls these
and turns a `ValueError` into an error tile, so a typo names the word and the allowed ones.
"""

from enum import Enum

from .types import Alignment, ContentAlign, ItemAlign, Wrap

__all__ = ['parse_alignment', 'parse_content_align', 'parse_item_align', 'parse_wrap']


def parse_alignment(text: str | Enum, kind: type[Enum]) -> Alignment:
	"""`center`, `flex-end` or `safe center`, read as a member of `kind`.

	Spaces, underscores and case do not matter: `Space_Between` is `space-between`.
	"""
	if isinstance(text, kind):
		return Alignment(text)
	words = str(text).strip().casefold().replace('_', '-').split()
	safe = False
	if len(words) == 2 and words[0] in ('safe', 'unsafe'):
		safe = words[0] == 'safe'
		words = words[1:]
	if len(words) == 1:
		for member in kind:
			if member.value == words[0]:
				return Alignment(member, safe)
	allowed = ', '.join(member.value for member in kind)
	raise ValueError(f'{text!r} is not one of: {allowed} (optionally after safe or unsafe)')


def parse_content_align(text: str | ContentAlign) -> Alignment:
	"""A `justify-content` or `align-content` value."""
	return parse_alignment(text, ContentAlign)


def parse_item_align(text: str | ItemAlign) -> Alignment:
	"""An `align-items`, `align-self`, `justify-items` or `justify-self` value."""
	return parse_alignment(text, ItemAlign)


def parse_wrap(text: str | bool | Wrap) -> Wrap:
	"""`nowrap`, `wrap` or `wrap-reverse`. `true` is `wrap` and `false` is `nowrap`."""
	if isinstance(text, Wrap):
		return text
	if isinstance(text, bool):
		return Wrap.wrap if text else Wrap.nowrap
	word = str(text).strip().casefold().replace('_', '-')
	for member in Wrap:
		if member.value == word:
			return member
	raise ValueError(f'{text!r} is not one of: {", ".join(member.value for member in Wrap)}')
