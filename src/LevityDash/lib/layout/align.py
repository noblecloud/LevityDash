"""CSS Box Alignment: gaps, content distribution, self-alignment, baselines.

Used by `flex.py` and `grid.py`. Spec: https://www.w3.org/TR/css-align-3/
"""

from .spec import implements
from .types import Alignment, Gap

__all__ = ['resolve_gap', 'distribute_content', 'align_offset', 'baseline_shifts']


@implements('css-align-3', 'Gaps Between Boxes', None)
def resolve_gap(row: float | None, column: float | None) -> Gap:
	"""Resolve `row-gap` and `column-gap`, where `None` is `normal`.

	`normal` is 0 in flex and grid. One value in the `gap` shorthand sets both, so the caller
	passes the same number twice. The legacy `Stack.spacing` is `gap` with one axis in use.
	"""
	raise NotImplementedError


@implements('css-align-3', 'Content Distribution: the justify-content and align-content properties', None)
def distribute_content(free_space: float, count: int, align: Alignment) -> tuple[float, float]:
	"""Split `free_space` among `count` boxes. Returns `(leading, between)`.

	`leading` is the offset of the first box. `between` is the extra space added to each gap.
	Cover `start`, `end`, `center`, `space-between`, `space-around`, `space-evenly`. `stretch`
	adds no offset here; the caller grows the boxes instead.

	Negative `free_space`: `safe` falls back to `start`. Unsafe values may go negative.
	`space-between` with one box falls back to `flex-start`; `space-around` and `space-evenly`
	fall back to `center`.
	"""
	raise NotImplementedError


@implements('css-align-3', 'Self-Alignment: the justify-self and align-self properties', None)
def align_offset(free_space: float, align: Alignment) -> float:
	"""Offset of one box inside its slot for `start`, `end`, `center` (and the flex- forms).

	`stretch` and `baseline` return 0; the caller handles them. A `safe` value with negative
	`free_space` returns 0. This is the one place the "safe center" rule from good-css lives.
	"""
	raise NotImplementedError


@implements('css-align-3', 'Baseline Alignment Terminology and Preferences', None)
def baseline_shifts(baselines: list[float], *, last: bool = False) -> list[float]:
	"""Offsets that put the given first (or last) baselines on one line.

	`baselines[i]` is the distance from the top of box `i` to its baseline. Returns the shift
	to apply to each box so every baseline sits at the largest one. Used for a hero value and
	its unit on one baseline (see docs/tasks/text-baseline-alignment.md).
	"""
	raise NotImplementedError
