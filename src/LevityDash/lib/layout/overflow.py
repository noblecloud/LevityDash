"""Overflow and scrolling: what a stack does with content that is larger than its box.

`overflow:` on a stack (CSS `overflow`, css-overflow-3): `visible` (default; content spills out, as today), `clip` and
`hidden` (cut at the stack's edge; `hidden` can still be moved by code, `clip` cannot), `scroll` (cut, and the
user can move it; the scroll bar is always drawn) and `auto` (the same, but only when the content is larger than
the box). The scroll axis is the stack's main axis: a vertical stack scrolls up and down, a horizontal one sideways.

Pure Python and Qt-free. Positions are pixels inside the stack's padding box; an offset is how far the content has
moved up (or left): 0 shows the start, `max_offset` shows the end.
"""
from typing import Iterable, Optional

from .spec import implements
from .types import Rect

__all__ = ['MODES', 'parse', 'clips', 'scrolls', 'content_end', 'max_offset', 'clamp', 'shift', 'thumb', 'step']

MODES = ('visible', 'hidden', 'clip', 'scroll', 'auto')


@implements('css-overflow-3', 'Scrollable overflow: the overflow properties', None, status='done')
def parse(value) -> str:
	"""The overflow mode written as `value`. None is `visible`. Anything else is an error that names the choices."""
	if value is None:
		return 'visible'
	mode = str(value).strip().casefold()
	if mode not in MODES:
		raise ValueError(f'overflow is {value!r}; it is {", ".join(MODES)}')
	return mode


def clips(mode: str) -> bool:
	"""Whether content outside the box is cut off."""
	return mode != 'visible'


def scrolls(mode: str) -> bool:
	"""Whether the user can move the content."""
	return mode in ('scroll', 'auto')


def content_end(rects: Iterable[Rect], vertical: bool) -> float:
	"""How far the content reaches along the scroll axis, from the start of the box (0 for no content)."""
	return max((r.y + r.height if vertical else r.x + r.width for r in rects), default=0.0)


def max_offset(end: float, view: float) -> float:
	"""The furthest the content can move: how much of it is past the end of the box. 0 when it fits."""
	return max(0.0, end - view)


def clamp(offset: float, limit: float) -> float:
	return min(max(0.0, offset), limit)


def shift(rects: list[Rect], offset: float, vertical: bool) -> list[Rect]:
	"""The rects moved back by `offset` along the scroll axis."""
	if not offset:
		return list(rects)
	return [Rect(r.x, r.y - offset, r.width, r.height) if vertical else Rect(r.x - offset, r.y, r.width, r.height) for r in rects]


def thumb(offset: float, limit: float, view: float, minimum: float = 12.0) -> Optional[tuple[float, float]]:
	"""(position, length) of the scroll bar's thumb in a track of length `view`, or None when nothing scrolls.

	The thumb is as long as the share of the content that shows, and never shorter than `minimum`.
	"""
	if limit <= 0 or view <= 0:
		return None
	length = min(view, max(minimum, view * view / (view + limit)))
	return (offset / limit) * (view - length), length


def step(delta: float, view: float) -> float:
	"""Pixels to move for one wheel notch of `delta` (120 is one notch): a fifth of the box, as browsers roughly do."""
	return -delta / 120.0 * view / 5.0
