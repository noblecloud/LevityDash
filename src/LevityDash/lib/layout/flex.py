"""CSS Flexible Box Layout, one line or many.

Spec: https://www.w3.org/TR/css-flexbox-1/ Section 9, "Flex Layout Algorithm".

The functions follow the order of the spec. `layout_flex` calls them in that order. The
steps are separate so each can be tested against the examples in the spec text.

Pure functions. No Qt. Sizes are pixels. See `types.py` for the conventions.
"""

from dataclasses import dataclass, field

from .spec import implements
from .types import Alignment, ContentAlign, Direction, Edge, Gap, INF, ItemAlign, Measure, Rect, Wrap

__all__ = ['FlexItem', 'FlexContainer', 'FlexLine', 'collect_flex_lines', 'flex_base_and_hypothetical_size', 'resolve_flexible_lengths', 'resolve_auto_margins', 'cross_sizes', 'align_main_axis', 'align_cross_axis', 'layout_flex']


@dataclass(slots=True)
class FlexItem:
	"""One flex item. Defaults are the CSS initial values: `flex: 0 1 auto`."""
	grow: float = 0.0  # flex-grow
	shrink: float = 1.0  # flex-shrink
	basis: float | None = None  # flex-basis; None is `auto` (use `main` or the content size)
	main: float | None = None  # width or height along the main axis; None is `auto`
	cross: float | None = None  # size along the cross axis; None is `auto`
	min_main: float | None = None  # None is `auto`: the automatic minimum size (§4.5)
	max_main: float = INF
	min_cross: float = 0.0
	max_cross: float = INF
	content_main: float = 0.0  # max-content size along the main axis
	content_min_main: float = 0.0  # min-content size along the main axis
	measure: Measure | None = None  # cross size for a given main size; None uses `cross` or `content_cross`
	content_cross: float = 0.0
	align_self: ItemAlign = ItemAlign.auto
	order: int = 0
	margin_main: Edge = Edge()
	margin_cross: Edge = Edge()
	baseline: float | None = None  # distance from the cross-start edge to the first baseline


@dataclass(slots=True)
class FlexContainer:
	"""A flex container. Defaults are the CSS initial values."""
	direction: Direction = Direction.row
	wrap: Wrap = Wrap.nowrap
	justify_content: Alignment = field(default_factory=lambda: Alignment(ContentAlign.flex_start))
	align_items: Alignment = field(default_factory=lambda: Alignment(ItemAlign.stretch))
	align_content: Alignment = field(default_factory=lambda: Alignment(ContentAlign.stretch))
	gap: Gap = Gap()
	main: float | None = None  # inner main size; None is indefinite
	cross: float | None = None  # inner cross size; None is indefinite
	padding_main: Edge = Edge()
	padding_cross: Edge = Edge()


@dataclass(slots=True)
class FlexLine:
	"""A flex line: the indices of its items (in `order`-modified document order) and its sizes."""
	items: list[int] = field(default_factory=list)
	main_sizes: list[float] = field(default_factory=list)  # used main size of each item
	cross: float = 0.0  # line cross size
	cross_offset: float = 0.0


@implements('css-flexbox-1', 'Line Length Determination: flex base size and hypothetical main size', '9.2')
def flex_base_and_hypothetical_size(item: FlexItem, container_main: float | None) -> tuple[float, float]:
	"""Return `(flex_base_size, hypothetical_main_size)` for one item.

	Step 3 of §9.2. The base size comes from `basis`, else `main`, else the content size. The
	hypothetical size is the base size clamped by the item's min and max main size.
	"""
	raise NotImplementedError


@implements('css-flexbox-1', 'Collect flex items into flex lines', '9.3')
def collect_flex_lines(items: list[FlexItem], container: FlexContainer) -> list[FlexLine]:
	"""Step 5 of §9.3. One line for `nowrap`. For `wrap`, break before an item whose
	hypothetical size would not fit, counting the gaps. `wrap-reverse` reverses the cross
	order of the lines (done in `align_content`, not here).
	"""
	raise NotImplementedError


@implements('css-flexbox-1', 'Resolving Flexible Lengths', '9.7')
def resolve_flexible_lengths(items: list[FlexItem], available_main: float, gap: float) -> list[float]:
	"""The freeze loop of §9.7 for the items of one line. Returns the used main size of each.

	Pick grow or shrink from the sum of hypothetical sizes against `available_main` (steps 1
	and 2), freeze inflexible items, distribute free space in proportion to `grow`, or to
	`shrink * base size` (scaled shrink factor), clamp, and freeze violators (steps 3 to 6),
	repeating until nothing is left to freeze. `gap` is subtracted per item boundary.
	"""
	raise NotImplementedError


@implements('css-flexbox-1', 'Aligning with auto margins', '8.1')
def resolve_auto_margins(items: list[FlexItem], sizes: list[float], available_main: float, gap: float) -> list[Edge]:
	"""Distribute positive free space to `auto` main-axis margins equally (§8.1).

	Returns the resolved main margins of each item. When any item has an auto margin,
	`justify-content` has no effect on that line. This is the CSS "push to the end" trick and
	replaces the unsized `spacer` workaround.
	"""
	raise NotImplementedError


@implements('css-flexbox-1', 'Cross Size Determination', '9.4')
def cross_sizes(lines: list[FlexLine], items: list[FlexItem], container: FlexContainer) -> list[float]:
	"""Steps 7 to 11 of §9.4. Returns the cross size of each line.

	Each item's cross size comes from `measure(used_main)` where set. A single-line container
	with a definite cross size uses it for the line. `align-content: stretch` shares the
	leftover cross space equally among the lines.
	"""
	raise NotImplementedError


@implements('css-flexbox-1', 'Main-Axis Alignment', '9.5')
def align_main_axis(sizes: list[float], margins: list[Edge], available_main: float, gap: float, justify: Alignment) -> list[float]:
	"""Main-axis offsets of the items in one line, from `justify-content` (§9.5).

	Uses `align.distribute_content` for the leftover space after sizes, margins and gaps.
	"""
	raise NotImplementedError


@implements('css-flexbox-1', 'Cross-Axis Alignment', '9.6')
def align_cross_axis(lines: list[FlexLine], items: list[FlexItem], container: FlexContainer) -> list[tuple[float, float]]:
	"""Cross offset and cross size of every item, in item order (§9.6).

	`align-self` (or the container's `align-items` for `auto`) picks `flex-start`, `flex-end`,
	`center`, `baseline` or `stretch`. `stretch` grows an item whose cross size is `auto` to
	fill its line, within `min_cross` and `max_cross`. Lines are placed by `align-content`.
	"""
	raise NotImplementedError


@implements('css-flexbox-1', 'Flex Layout Algorithm', '9')
def layout_flex(items: list[FlexItem], container: FlexContainer) -> list[Rect]:
	"""Lay out `items` in `container`. Returns one `Rect` per item, in the order given.

	Rects are relative to the container's padding edge. This is the whole of §9 in order:
	sort by `order`, find base sizes, collect lines, resolve lengths, resolve auto margins,
	find cross sizes, align both axes, then map main/cross to x/y by `direction`.
	`*-reverse` directions mirror the main axis after layout.

	Must reduce to the legacy `Stack` result for `legacy.stack_as_flex`; see `legacy.py`.
	"""
	raise NotImplementedError
