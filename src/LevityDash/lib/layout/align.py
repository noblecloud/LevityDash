"""CSS Box Alignment: gaps, content distribution, self-alignment, baselines.

Used by `flex.py` and `grid.py`. Spec: https://www.w3.org/TR/css-align-3/
"""

from .spec import implements
from .types import Alignment, ContentAlign, Gap, ItemAlign

__all__ = ['resolve_gap', 'distribute_content', 'align_offset', 'baseline_shifts']

# Positional values: they place the group or box at one edge or the middle, no distribution.
_START = {ContentAlign.start, ContentAlign.flex_start, ItemAlign.start, ItemAlign.flex_start}
_END = {ContentAlign.end, ContentAlign.flex_end, ItemAlign.end, ItemAlign.flex_end}
_CENTER = {ContentAlign.center, ItemAlign.center}
_DISTRIBUTED = {ContentAlign.space_between, ContentAlign.space_around, ContentAlign.space_evenly}
# No offset here: the caller decides (stretch grows boxes, baseline lines them up on another axis).
_NO_OFFSET = {
	ItemAlign.auto, ItemAlign.normal, ItemAlign.stretch, ItemAlign.baseline, ItemAlign.last_baseline,
	ContentAlign.normal, ContentAlign.stretch,
}


@implements('css-align-3', 'Gaps Between Boxes', None, status='done')
def resolve_gap(row: float | None, column: float | None) -> Gap:
	"""Resolve `row-gap` and `column-gap`, where `None` is `normal`.

	`normal` is 0 in flex and grid. One value in the `gap` shorthand sets both, so the caller
	passes the same number twice. The legacy `Stack.spacing` is `gap` with one axis in use.
	"""
	for value in (row, column):
		if value is not None and value < 0:
			raise ValueError(f'a gap cannot be negative, got {value}')
	return Gap(0.0 if row is None else row, 0.0 if column is None else column)


@implements('css-align-3', 'Content Distribution: the justify-content and align-content properties', None, status='done')
def distribute_content(free_space: float, count: int, align: Alignment) -> tuple[float, float]:
	"""Split `free_space` among `count` boxes. Returns `(leading, between)`.

	`leading` is the offset of the first box. `between` is the extra space added to each gap.
	Cover `start`, `end`, `center`, `space-between`, `space-around`, `space-evenly`. `stretch`
	adds no offset here; the caller grows the boxes instead.

	Negative `free_space`: `safe` falls back to `start`. Unsafe values may go negative.
	`space-between` with one box falls back to `flex-start`; `space-around` and `space-evenly`
	fall back to `center`.
	"""
	if count <= 0:
		return 0.0, 0.0
	value = align.value
	overflow = free_space < 0

	if value in _DISTRIBUTED:
		# Spec 4.3: when space cannot be distributed, the value takes its fallback. space-between
		# falls back to safe flex-start; space-around and space-evenly to safe center. A safe
		# fallback with a negative leftover is the start edge.
		if value is ContentAlign.space_between:
			if count == 1 or overflow:
				return 0.0, 0.0
			return 0.0, free_space / (count - 1)
		if overflow:
			return 0.0, 0.0
		if count == 1:
			return free_space / 2, 0.0
		if value is ContentAlign.space_around:
			return free_space / (2 * count), free_space / count
		return free_space / (count + 1), free_space / (count + 1)

	if value in _START or value in (ContentAlign.normal, ContentAlign.stretch):
		return 0.0, 0.0
	if value in _END:
		return (0.0 if align.safe and overflow else free_space), 0.0
	if value in _CENTER:
		return (0.0 if align.safe and overflow else free_space / 2), 0.0
	raise ValueError(f'{value!r} is not a content distribution value')


@implements('css-align-3', 'Self-Alignment: the justify-self and align-self properties', None, status='done')
def align_offset(free_space: float, align: Alignment) -> float:
	"""Offset of one box inside its slot for `start`, `end`, `center` (and the flex- forms).

	`stretch` and `baseline` return 0; the caller handles them. A `safe` value with negative
	`free_space` returns 0. This is the one place the "safe center" rule from good-css lives.
	"""
	value = align.value
	overflow = align.safe and free_space < 0
	if value in _START or value in _NO_OFFSET:
		return 0.0
	if value in _END:
		return 0.0 if overflow else free_space
	if value in _CENTER:
		return 0.0 if overflow else free_space / 2
	raise ValueError(f'{value!r} is not a self-alignment value; use distribute_content for {value!r}')


@implements('css-align-3', 'Baseline Alignment Terminology and Preferences', None, status='done')
def baseline_shifts(baselines: list[float], *, last: bool = False) -> list[float]:
	"""Offsets that put the given first (or last) baselines on one line.

	First baselines (the default): `baselines[i]` is the distance from the top of box `i` to its
	baseline. The box whose baseline is furthest from the top sets the line. Each shift is how far
	to move that box down, so every baseline lands on the line.

	Last baselines (`last=True`): `baselines[i]` is the distance from the bottom of box `i` to its
	last baseline. The baseline furthest from the bottom sets the line, and each shift is how far
	to move that box up. Last-baseline groups align to the end edge (spec 5.4).

	Used for a hero value and its unit on one baseline (see docs/tasks/text-baseline-alignment.md).
	"""
	if not baselines:
		return []
	reference = max(baselines)
	return [reference - baseline for baseline in baselines]
