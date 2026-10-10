"""CSS Flexible Box Layout, one line or many.

Spec: https://www.w3.org/TR/css-flexbox-1/ Section 9, "Flex Layout Algorithm".

The functions follow the order of the spec. `layout_flex` calls them in that order. The
steps are separate so each can be tested against the examples in the spec text.

Pure functions. No Qt. Sizes are pixels. See `types.py` for the conventions.

Where this module differs from the spec text, the difference is in the docstring of the
function concerned. In short: margins are passed in with the sizes, the container's own
min and max cross sizes are not modelled (`FlexContainer` has none), and percentages are
already resolved by the caller.
"""

from dataclasses import dataclass, field

from .spec import implements
from .types import Alignment, ContentAlign, Direction, Edge, Gap, INF, ItemAlign, Measure, Rect, Wrap

__all__ = ['FlexItem', 'FlexContainer', 'FlexLine', 'collect_flex_lines', 'flex_base_and_hypothetical_size', 'resolve_flexible_lengths', 'resolve_auto_margins', 'cross_sizes', 'align_main_axis', 'align_cross_axis', 'layout_flex']

_ROW_DIRECTIONS = (Direction.row, Direction.row_reverse)
_BASELINE = ('baseline', 'last baseline')
_STRETCH = ('stretch', 'normal')


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


def _fixed(edge: Edge) -> float:
	"""The sum of the non-auto parts of a margin pair. An `auto` side counts as zero."""
	return (edge.start or 0.0) + (edge.end or 0.0)


def _main_gap(container: FlexContainer) -> float:
	return container.gap.column if container.direction in _ROW_DIRECTIONS else container.gap.row


def _cross_gap(container: FlexContainer) -> float:
	return container.gap.row if container.direction in _ROW_DIRECTIONS else container.gap.column


def _clamp_main(value: float, item: FlexItem) -> float:
	"""Clamp to the used min and max main size. The minimum wins over the maximum, and the
	content box is not negative (§4.5 and §9.2 step 3)."""
	return max(0.0, max(_min_main(item), min(value, item.max_main)))


def _min_main(item: FlexItem) -> float:
	"""The used minimum main size. `None` is the automatic minimum (§4.5): the smaller of the
	content size and a definite specified size."""
	if item.min_main is not None:
		return item.min_main
	if item.main is not None:
		return min(item.content_min_main, item.main)
	return item.content_min_main


def _hypothetical_main(item: FlexItem) -> float:
	return flex_base_and_hypothetical_size(item, None)[1]


def _alignment_name(alignment: Alignment) -> str:
	"""The keyword of an alignment value, e.g. `'flex-start'`."""
	return alignment.value.value


def _self_alignment(item: FlexItem, container: FlexContainer) -> tuple[str, bool]:
	"""The `align-self` keyword that applies to `item`, and whether it is `safe`.

	`auto` takes the container's `align-items`. Only the container's value carries `safe`.
	"""
	if item.align_self is not ItemAlign.auto:
		return item.align_self.value, False
	return _alignment_name(container.align_items), container.align_items.safe


def _cross_size(item: FlexItem, main: float) -> float:
	"""The cross size an item has when it is not stretched: `measure(main)`, else `cross`,
	else its content size, clamped to the cross min and max."""
	if item.measure is not None:
		size = item.measure(main)
	elif item.cross is not None:
		size = item.cross
	else:
		size = item.content_cross
	return max(item.min_cross, min(size, item.max_cross))


def _distribute(free: float, count: int, alignment: Alignment) -> tuple[float, float]:
	"""Split `free` space among `count` boxes. Returns `(leading, between)`.

	This is the content distribution of `justify-content` and `align-content` (§9.5, §9.6).
	It duplicates the rule that `align.distribute_content` will hold once Box Alignment is
	ported; the two should be merged then.
	"""
	name = _alignment_name(alignment)
	safe = alignment.safe
	if name in ('end', 'flex-end'):
		if safe and free < 0:
			return 0.0, 0.0
		return free, 0.0
	if name == 'center':
		if safe and free < 0:
			return 0.0, 0.0
		return free / 2, 0.0
	if name == 'space-between':
		if count <= 1 or free < 0:
			return 0.0, 0.0
		return 0.0, free / (count - 1)
	if name == 'space-around':
		if count <= 1 or free < 0:
			return _distribute(free, count, Alignment(ContentAlign.center, safe))
		each = free / count
		return each / 2, each
	if name == 'space-evenly':
		if count <= 1 or free < 0:
			return _distribute(free, count, Alignment(ContentAlign.center, safe))
		each = free / (count + 1)
		return each, each
	return 0.0, 0.0  # start, flex-start, normal, stretch


@implements('css-flexbox-1', 'Line Length Determination: flex base size and hypothetical main size', '9.2', status='done')
def flex_base_and_hypothetical_size(item: FlexItem, container_main: float | None) -> tuple[float, float]:
	"""Return `(flex_base_size, hypothetical_main_size)` for one item.

	Step 3 of §9.2. The base size comes from `basis`, else `main`, else the content size. The
	hypothetical size is the base size clamped by the item's min and max main size.

	`container_main` is accepted for the signature in the spec. Sizes here are already in
	pixels, so nothing in it is needed to resolve a percentage.
	"""
	if item.basis is not None:
		base = item.basis
	elif item.main is not None:
		base = item.main
	else:
		base = item.content_main
	return base, _clamp_main(base, item)


@implements('css-flexbox-1', 'Collect flex items into flex lines', '9.3', status='done')
def collect_flex_lines(items: list[FlexItem], container: FlexContainer) -> list[FlexLine]:
	"""Step 5 of §9.3. One line for `nowrap`. For `wrap`, break before an item whose
	hypothetical size would not fit, counting the gaps. `wrap-reverse` reverses the cross
	order of the lines (done in `align_cross_axis`, not here).

	An indefinite main size never breaks a line. The first item of a line is always kept, even
	when it does not fit on its own.
	"""
	if not items:
		return []
	available = container.main if container.main is not None else INF
	gap = _main_gap(container)
	single_line = container.wrap is Wrap.nowrap
	lines: list[FlexLine] = []
	used = 0.0
	for index in sorted(range(len(items)), key=lambda i: items[i].order):
		hypothetical = _hypothetical_main(items[index])
		if not lines:
			lines.append(FlexLine(items=[index]))
			used = hypothetical
		elif single_line or used + gap + hypothetical <= available:
			lines[-1].items.append(index)
			used += gap + hypothetical
		else:
			lines.append(FlexLine(items=[index]))
			used = hypothetical
	return lines


@implements('css-flexbox-1', 'Resolving Flexible Lengths', '9.7', status='done')
def resolve_flexible_lengths(items: list[FlexItem], available_main: float, gap: float) -> list[float]:
	"""The freeze loop of §9.7 for the items of one line. Returns the used main size of each.

	Pick grow or shrink from the sum of hypothetical sizes against `available_main` (steps 1
	and 2), freeze inflexible items, distribute free space in proportion to `grow`, or to
	`shrink * base size` (scaled shrink factor), clamp, and freeze violators (steps 3 to 6),
	repeating until nothing is left to freeze. `gap` is subtracted per item boundary.

	`available_main` is the inner main size less the non-auto margins of the items. Auto margins
	count as zero here; `resolve_auto_margins` gives them what is left.
	"""
	count = len(items)
	if count == 0:
		return []
	spare_gaps = gap * (count - 1)

	bases = [0.0] * count
	hypothetical = [0.0] * count
	for i, item in enumerate(items):
		bases[i], hypothetical[i] = flex_base_and_hypothetical_size(item, available_main)

	grow = sum(hypothetical) + spare_gaps < available_main

	def factor(item: FlexItem) -> float:
		return item.grow if grow else item.shrink

	target = list(bases)
	frozen = [False] * count
	for i, item in enumerate(items):
		inflexible = factor(item) == 0
		clamped_by_max = grow and bases[i] > hypothetical[i]
		clamped_by_min = not grow and bases[i] < hypothetical[i]
		if inflexible or clamped_by_max or clamped_by_min:
			frozen[i] = True
			target[i] = hypothetical[i]

	def free_space() -> float:
		return available_main - spare_gaps - sum(target[i] if frozen[i] else bases[i] for i in range(count))

	initial_free = free_space()
	while not all(frozen):
		unfrozen = [i for i in range(count) if not frozen[i]]
		for i in unfrozen:
			target[i] = bases[i]

		remaining = free_space()
		factor_sum = sum(factor(items[i]) for i in unfrozen)
		if factor_sum < 1:
			scaled = initial_free * factor_sum
			if abs(scaled) < abs(remaining):
				remaining = scaled

		if remaining != 0:
			if grow:
				total = sum(items[i].grow for i in unfrozen)
				for i in unfrozen:
					target[i] = bases[i] + remaining * items[i].grow / total
			else:
				scaled_shrink = {i: items[i].shrink * bases[i] for i in unfrozen}
				total = sum(scaled_shrink.values())
				for i in unfrozen:
					ratio = scaled_shrink[i] / total if total > 0 else 0.0
					target[i] = bases[i] - abs(remaining) * ratio

		raw = {i: target[i] for i in unfrozen}
		clamped = {i: _clamp_main(raw[i], items[i]) for i in unfrozen}
		total_violation = sum(clamped[i] - raw[i] for i in unfrozen)
		if total_violation == 0:
			to_freeze = unfrozen
		elif total_violation > 0:
			to_freeze = [i for i in unfrozen if clamped[i] > raw[i]]
		else:
			to_freeze = [i for i in unfrozen if clamped[i] < raw[i]]
		for i in to_freeze:
			frozen[i] = True
			target[i] = clamped[i]

	return target


@implements('css-flexbox-1', 'Aligning with auto margins', '8.1', status='done')
def resolve_auto_margins(items: list[FlexItem], sizes: list[float], available_main: float, gap: float) -> list[Edge]:
	"""Distribute positive free space to `auto` main-axis margins equally (§8.1).

	Returns the resolved main margins of each item. When any item has an auto margin,
	`justify-content` has no effect on that line. This is the CSS "push to the end" trick and
	replaces the unsized `spacer` workaround.

	`available_main` is the inner main size of the container. `sizes` are the used main sizes
	of the items on the line, in the same order as `items`. Auto margins with no free space
	to take become zero. The returned edges have no `None`.
	"""
	auto_count = 0
	used = gap * max(0, len(items) - 1)
	for item, size in zip(items, sizes):
		used += size + _fixed(item.margin_main)
		auto_count += int(item.margin_main.start is None) + int(item.margin_main.end is None)
	free = available_main - used
	share = free / auto_count if auto_count and free > 0 else 0.0
	resolved = []
	for item in items:
		start, end = item.margin_main
		resolved.append(Edge(share if start is None else start, share if end is None else end))
	return resolved


@implements('css-flexbox-1', 'Cross Size Determination', '9.4', status='done')
def cross_sizes(lines: list[FlexLine], items: list[FlexItem], container: FlexContainer) -> list[float]:
	"""Steps 7 to 11 of §9.4. Returns the cross size of each line.

	Each item's cross size comes from `measure(used_main)` where set. A single-line container
	with a definite cross size uses it for the line. `align-content: stretch` shares the
	leftover cross space equally among the lines.

	Baseline-aligned items share one baseline group, as step 8 of §9.4 describes. Lines are not
	clamped to the container's min and max cross size: `FlexContainer` does not carry them.
	"""
	gap = _cross_gap(container)
	sizes: list[float] = []
	for line in lines:
		if container.wrap is Wrap.nowrap and container.cross is not None:
			sizes.append(container.cross)
		else:
			sizes.append(_content_line_cross(line, items, container))

	if container.cross is not None and _alignment_name(container.align_content) == 'stretch' and sizes:
		free = container.cross - sum(sizes) - gap * (len(sizes) - 1)
		if free > 0:
			sizes = [size + free / len(sizes) for size in sizes]
	return sizes


def _content_line_cross(line: FlexLine, items: list[FlexItem], container: FlexContainer) -> float:
	"""Step 8 and 9 of §9.4 for one line: the largest outer hypothetical cross size, or the
	baseline group if that is larger."""
	largest = 0.0
	above = 0.0
	below = 0.0
	for index, main in zip(line.items, line.main_sizes):
		item = items[index]
		start, end = item.margin_cross
		outer = _cross_size(item, main) + _fixed(item.margin_cross)
		if _self_alignment(item, container)[0] in _BASELINE and start is not None and end is not None:
			distance = (item.baseline or 0.0) + start
			above = max(above, distance)
			below = max(below, outer - distance)
		else:
			largest = max(largest, outer)
	return max(largest, above + below, 0.0)


@implements('css-flexbox-1', 'Main-Axis Alignment', '9.5', status='done')
def align_main_axis(sizes: list[float], margins: list[Edge], available_main: float, gap: float, justify: Alignment) -> list[float]:
	"""Main-axis offsets of the items in one line, from `justify-content` (§9.5).

	Returns the offset of each item's border box, after its start margin. Uses the same
	distribution as `align.distribute_content` for the leftover space after sizes, margins and
	gaps.
	"""
	count = len(sizes)
	if not count:
		return []
	used = sum(sizes) + sum(_fixed(m) for m in margins) + gap * (count - 1)
	leading, between = _distribute(available_main - used, count, justify)
	offsets = []
	position = leading
	for size, margin in zip(sizes, margins):
		position += margin.start or 0.0
		offsets.append(position)
		position += size + (margin.end or 0.0) + gap + between
	return offsets


@implements('css-flexbox-1', 'Cross-Axis Alignment', '9.6', status='done')
def align_cross_axis(lines: list[FlexLine], items: list[FlexItem], container: FlexContainer) -> list[tuple[float, float]]:
	"""Cross offset and cross size of every item, in item order (§9.6).

	`align-self` (or the container's `align-items` for `auto`) picks `flex-start`, `flex-end`,
	`center`, `baseline` or `stretch`. `stretch` grows an item whose cross size is `auto` to
	fill its line, within `min_cross` and `max_cross`. Lines are placed by `align-content`.

	Needs `line.cross` and `line.main_sizes` set. Sets `line.cross_offset`, which is the offset
	of each line's cross-start edge. For `wrap-reverse` the lines and items are mirrored in the
	cross axis after placement.

	A cross margin that is `auto` takes the free space of its line first, as §8.1 says. When
	there is none, the start margin becomes zero and the end margin takes the rest.
	"""
	result: list[tuple[float, float]] = [(0.0, 0.0)] * len(items)
	if not lines:
		return result
	gap = _cross_gap(container)
	count = len(lines)

	free = container.cross - sum(line.cross for line in lines) - gap * (count - 1) if container.cross is not None else 0.0
	leading, between = _distribute(free, count, container.align_content)
	position = leading
	for line in lines:
		line.cross_offset = position
		position += line.cross + gap + between

	placed: dict[int, tuple[float, float]] = {}
	for line in lines:
		baseline_max = 0.0
		for index, main in zip(line.items, line.main_sizes):
			item = items[index]
			if _self_alignment(item, container)[0] in _BASELINE and None not in item.margin_cross:
				baseline_max = max(baseline_max, (item.baseline or 0.0) + (item.margin_cross.start or 0.0))

		for index, main in zip(line.items, line.main_sizes):
			item = items[index]
			name, safe = _self_alignment(item, container)
			has_auto = None in item.margin_cross
			stretch = name in _STRETCH and item.cross is None and not has_auto
			if stretch:
				size = max(item.min_cross, min(line.cross - _fixed(item.margin_cross), item.max_cross))
				start, end = item.margin_cross.start or 0.0, item.margin_cross.end or 0.0
			else:
				size = _cross_size(item, main)
				start, end = _resolve_cross_margins(item, size, line.cross)

			if name in _BASELINE and not has_auto:
				offset = line.cross_offset + baseline_max - (item.baseline or 0.0)
			else:
				free_self = line.cross - (size + start + end)
				if name in ('end', 'flex-end'):
					inner = free_self
				elif name == 'center':
					inner = 0.0 if safe and free_self < 0 else free_self / 2
				else:
					inner = 0.0
				offset = line.cross_offset + start + inner
			placed[index] = (offset, size)

	if container.wrap is Wrap.wrap_reverse:
		extent = container.cross if container.cross is not None else max(
			(line.cross_offset + line.cross for line in lines), default=0.0)
		for line in lines:
			line.cross_offset = extent - line.cross_offset - line.cross
		for index, (offset, size) in placed.items():
			placed[index] = (extent - offset - size, size)

	for index, value in placed.items():
		result[index] = value
	return result


def _resolve_cross_margins(item: FlexItem, size: float, line_cross: float) -> tuple[float, float]:
	"""The cross margins of one item, with `auto` resolved (§9.6, "resolve cross-axis auto
	margins"). Returns `(start, end)`."""
	start, end = item.margin_cross
	if start is not None and end is not None:
		return start, end
	auto_count = int(start is None) + int(end is None)
	free = line_cross - size - _fixed(item.margin_cross)
	if free > 0:
		share = free / auto_count
		return (share if start is None else start), (share if end is None else end)
	start = 0.0 if start is None else start
	if end is None:
		end = line_cross - size - start
	return start, end


@implements('css-flexbox-1', 'Flex Layout Algorithm', '9', status='done')
def layout_flex(items: list[FlexItem], container: FlexContainer) -> list[Rect]:
	"""Lay out `items` in `container`. Returns one `Rect` per item, in the order given.

	Rects are relative to the container's padding edge. This is the whole of §9 in order:
	sort by `order`, find base sizes, collect lines, resolve lengths, resolve auto margins,
	find cross sizes, align both axes, then map main/cross to x/y by `direction`.
	`*-reverse` directions mirror the main axis after layout.

	Must reduce to the legacy `Stack` result for `legacy.stack_as_flex`; see `legacy.py`.

	With an indefinite main size the items keep their hypothetical sizes and there is no free
	space to distribute. `justify-content` then has no effect.
	"""
	if not items:
		return []
	gap = _main_gap(container)
	lines = collect_flex_lines(items, container)

	main_offsets: dict[int, float] = {}
	for line in lines:
		members = [items[i] for i in line.items]
		if container.main is None:
			line.main_sizes = [_hypothetical_main(item) for item in members]
			margins = [Edge(item.margin_main.start or 0.0, item.margin_main.end or 0.0) for item in members]
			available = sum(line.main_sizes) + sum(_fixed(m) for m in margins) + gap * (len(members) - 1)
		else:
			fixed = sum(_fixed(item.margin_main) for item in members)
			line.main_sizes = resolve_flexible_lengths(members, container.main - fixed, gap)
			margins = resolve_auto_margins(members, line.main_sizes, container.main, gap)
			available = container.main
		offsets = align_main_axis(line.main_sizes, margins, available, gap, container.justify_content)
		for index, offset in zip(line.items, offsets):
			main_offsets[index] = offset

	for line, size in zip(lines, cross_sizes(lines, items, container)):
		line.cross = size
	placements = align_cross_axis(lines, items, container)

	if container.direction in (Direction.row_reverse, Direction.column_reverse):
		for line in lines:
			extent = container.main if container.main is not None else max(
				main_offsets[i] + size for i, size in zip(line.items, line.main_sizes))
			for index, size in zip(line.items, line.main_sizes):
				main_offsets[index] = extent - main_offsets[index] - size

	rects: list[Rect] = []
	for index, item in enumerate(items):
		size_main = _used_main(lines, index)
		cross_offset, size_cross = placements[index]
		if container.direction in _ROW_DIRECTIONS:
			rects.append(Rect(main_offsets[index], cross_offset, size_main, size_cross))
		else:
			rects.append(Rect(cross_offset, main_offsets[index], size_cross, size_main))
	return rects


def _used_main(lines: list[FlexLine], index: int) -> float:
	for line in lines:
		if index in line.items:
			return line.main_sizes[line.items.index(index)]
	raise IndexError(index)
