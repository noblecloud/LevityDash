"""CSS Grid Layout: tracks, placement and the track sizing algorithm.

Spec: https://www.w3.org/TR/css-grid-1/ Sections 7, 8 and 12.

Pure functions. No Qt. Sizes are pixels. See `types.py` for the conventions.
Out of scope: `subgrid`, named areas by string art, masonry, intrinsic sizing from
wrapped text. Do not add them without asking.

Simplifications, each also noted where it is made:
- Item contributions are numbers on `GridItem` and are not re-run against the track sizes.
  §12 repeats steps 2 and 3 for wrapped content; that repetition is not done.
- A container sized under a min-content or max-content constraint is not modelled. A
  container with `width=None` has no free space to hand out.
- Indefinite free space in `expand_flexible_tracks` uses the tracks only, not the item
  terms of §12.7.1.
- Content and self alignment other than `start`, `stretch` and `normal` go to `align.py`.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from math import floor, isinf

from .align import distribute_content, align_offset
from .spec import implements
from .types import Alignment, ContentAlign, Gap, INF, ItemAlign, Rect

__all__ = [
	'Fr', 'Keyword', 'TrackSize', 'Repeat', 'GridContainer', 'GridItem', 'Placement', 'Track',
	'parse_track_list', 'expand_repeat', 'place_items', 'initialize_track_sizes',
	'resolve_intrinsic_track_sizes', 'maximize_tracks', 'expand_flexible_tracks',
	'stretch_auto_tracks', 'layout_grid',
]

_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class Fr:
	"""A flexible length: `1fr` is `Fr(1)`."""
	value: float


class Keyword(Enum):
	auto = 'auto'
	min_content = 'min-content'
	max_content = 'max-content'


Breadth = float | Fr | Keyword  # a pixel length, `fr`, or a keyword


@dataclass(frozen=True, slots=True)
class TrackSize:
	"""A track sizing function: `minmax(min, max)`. A plain length `L` is `TrackSize(L, L)`.

	`auto` is `minmax(auto, auto)`. `1fr` is `minmax(auto, 1fr)`. `fit-content(L)` is
	`minmax(auto, max-content)` clamped to `L`; use `limit` for `L`.
	"""
	min: Breadth = Keyword.auto
	max: Breadth = Keyword.auto
	limit: float | None = None


@dataclass(frozen=True, slots=True)
class Repeat:
	"""`repeat(count, tracks)`. `count` is an int, `'auto-fill'` or `'auto-fit'`."""
	count: int | str
	tracks: tuple[TrackSize, ...]


@dataclass(slots=True)
class Track:
	"""A track while it is being sized. Mirrors the spec's "base size" and "growth limit"."""
	size: TrackSize
	base: float = 0.0
	limit: float = 0.0  # growth limit; INF is infinite
	frozen: bool = False
	infinitely_growable: bool = False  # §12.5: a growth limit that went from infinite to finite


@dataclass(frozen=True, slots=True)
class Placement:
	"""A grid item's lines. `None` is `auto`. Lines are 1-based, as in CSS. `span` counts tracks."""
	column_start: int | None = None
	column_span: int = 1
	row_start: int | None = None
	row_span: int = 1


@dataclass(slots=True)
class GridItem:
	placement: Placement = Placement()
	min_content: tuple[float, float] = (0.0, 0.0)  # (width, height)
	max_content: tuple[float, float] = (0.0, 0.0)
	min_size: tuple[float | None, float | None] = (None, None)  # None is the automatic minimum
	justify_self: ItemAlign = ItemAlign.auto
	align_self: ItemAlign = ItemAlign.auto


@dataclass(slots=True)
class GridContainer:
	columns: list[TrackSize | Repeat] = field(default_factory=list)
	rows: list[TrackSize | Repeat] = field(default_factory=list)
	auto_columns: TrackSize = TrackSize()
	auto_rows: TrackSize = TrackSize()
	auto_flow: str = 'row'  # `grid-auto-flow`: 'row' or 'column'
	dense: bool = False
	gap: Gap = Gap()
	justify_content: Alignment = field(default_factory=lambda: Alignment(ContentAlign.normal))
	align_content: Alignment = field(default_factory=lambda: Alignment(ContentAlign.normal))
	justify_items: Alignment = field(default_factory=lambda: Alignment(ItemAlign.stretch))
	align_items: Alignment = field(default_factory=lambda: Alignment(ItemAlign.stretch))
	width: float | None = None
	height: float | None = None


# --- helpers -------------------------------------------------------------------------------

def _fixed(breadth: Breadth) -> bool:
	return isinstance(breadth, (int, float))


def _flexible(breadth: Breadth) -> bool:
	return isinstance(breadth, Fr)


def _intrinsic(breadth: Breadth) -> bool:
	return isinstance(breadth, Keyword)


def _is_flex(track: Track) -> bool:
	return _flexible(track.size.max)


def _fit(track: Track) -> float | None:
	return track.size.limit


def _any(track: Track) -> bool:
	return True


def _one(track: Track) -> float:
	return 1.0


def _share(space: float, members: list[int], room: dict[int, float], weights: dict[int, float] | None = None) -> dict[int, float]:
	"""Share `space` among `members`, each taking at most `room[m]`, equally or by `weights`.

	A member that reaches its room is frozen and the rest keep sharing. Returns the increase
	for each member.
	"""
	inc = {m: 0.0 for m in members}
	active = list(members)
	left = space
	while left > _EPS and active:
		weight = {m: weights[m] if weights else 1.0 for m in active}
		total = sum(weight.values())
		capped, used = [], 0.0
		for m in active:
			share = left * weight[m] / total
			grant = min(share, max(0.0, room[m] - inc[m]))
			inc[m] += grant
			used += grant
			if grant < share - _EPS:
				capped.append(m)
		left -= used
		if not capped:
			break
		active = [m for m in active if m not in capped]
	return inc


def _size(track: Track, growth: bool) -> float:
	"""The affected size: the base, or the growth limit when it is finite (infinite counts as the base)."""
	if growth and not isinf(track.limit):
		return track.limit
	return track.base


def _room(track: Track, growth: bool, current: float) -> float:
	"""How far the affected size may grow before it reaches its limit."""
	if not growth:
		limit = track.limit if _fit(track) is None else min(track.limit, _fit(track))
		return max(0.0, limit - track.base)
	if not isinf(track.limit) and not track.infinitely_growable:
		limit = track.limit
	elif _fit(track) is not None:
		limit = _fit(track)
	else:
		return INF
	return max(0.0, limit - current)


def _settle(tracks: list[Track]) -> None:
	"""Clamp growth limits by `fit-content()` and never let a limit fall below its base."""
	for track in tracks:
		if _fit(track) is not None:
			track.limit = min(track.limit, _fit(track))
		if track.limit < track.base:
			track.limit = track.base


def _accommodate(tracks: list[Track], group: list[int], spans: list[tuple[int, int]], gap: float, *,
		contribution, affected, prefer, growth: bool, include=_any, weight=_one) -> None:
	"""Spec §12.5 "Distributing Extra Space Across Spanned Tracks".

	For each item in `group`, spread what its contribution needs beyond the tracks it spans:
	first to the affected tracks, then to the other spanned tracks, then past the limits to the
	preferred affected tracks. Planned increases are applied after the whole group, so the
	result does not depend on item order. `growth` picks growth limits over base sizes.
	"""
	planned: dict[int, float] = {}
	touched: set[int] = set()
	for i in group:
		start, span = spans[i]
		members = list(range(start, start + span))
		current = {t: _size(tracks[t], growth) for t in members}
		space = contribution(i) - sum(current.values()) - gap * (span - 1)
		hit = [t for t in members if include(tracks[t]) and affected(tracks[t])]
		if space <= _EPS or not hit:
			continue
		room = {t: _room(tracks[t], growth, current[t]) for t in members}
		weights = {t: weight(tracks[t]) for t in members}
		inc = _share(space, hit, room, weights)
		left = space - sum(inc.values())
		others = [t for t in members if t not in hit and include(tracks[t])]
		if left > _EPS and others:
			extra = _share(left, others, room, weights)
			inc.update(extra)
			left -= sum(extra.values())
		if left > _EPS:
			preferred = [t for t in hit if prefer(tracks[t])] or hit
			extra = _share(left, preferred, {t: INF for t in preferred}, weights)
			for t, value in extra.items():
				inc[t] = inc.get(t, 0.0) + value
		for t, value in inc.items():
			planned[t] = max(planned.get(t, 0.0), value)
		touched.update(hit)
	for t in planned.keys() | touched:
		track = tracks[t]
		add = planned.get(t, 0.0)
		if not growth:
			track.base += add
		elif t in touched and isinf(track.limit):
			track.limit = track.base + add
			track.infinitely_growable = True
		elif not isinf(track.limit):
			track.limit += add


def _split(text: str, separators: str) -> list[str]:
	"""Split `text` at `separators` that are outside parentheses. Empty pieces are dropped."""
	parts, buf, depth = [], '', 0
	for ch in text:
		if ch == '(':
			depth += 1
		elif ch == ')':
			depth -= 1
			if depth < 0:
				raise ValueError(f'unbalanced ")" in {text!r}')
		if depth == 0 and ch in separators:
			if buf.strip():
				parts.append(buf.strip())
			buf = ''
		else:
			buf += ch
	if depth:
		raise ValueError(f'unbalanced "(" in {text!r}')
	if buf.strip():
		parts.append(buf.strip())
	return parts


_NUMBER = re.compile(r'(\d*\.?\d+)([a-zA-Z%]*)')
_KEYWORDS = {'auto': Keyword.auto, 'min-content': Keyword.min_content, 'max-content': Keyword.max_content}


def _breadth(token: str, to_px, *, maximum: bool) -> Breadth:
	if token in _KEYWORDS:
		return _KEYWORDS[token]
	match = _NUMBER.fullmatch(token)
	if not match:
		raise ValueError(f'not a track size: {token!r}')
	value, unit = float(match[1]), match[2].lower()
	if unit == 'fr':
		if not maximum:
			raise ValueError(f'fr is only valid as a max track size: {token!r}')
		return Fr(value)
	if unit in ('', 'px'):
		return value
	if unit == '%':
		raise ValueError(f'{token!r}: % needs the container size, so resolve it to px first')
	if to_px is None:
		raise ValueError(f'{token!r}: unit {unit!r} needs a to_px function')
	return float(to_px(value, unit))


def _track(token: str, to_px) -> TrackSize | Repeat:
	if token.startswith('repeat(') and token.endswith(')'):
		count, sep, rest = token[7:-1].partition(',')
		count = count.strip()
		if not sep:
			raise ValueError(f'repeat needs a count and tracks: {token!r}')
		if count in ('auto-fill', 'auto-fit'):
			repeat_count: int | str = count
		elif count.isdigit() and int(count) >= 1:
			repeat_count = int(count)
		else:
			raise ValueError(f'bad repeat count in {token!r}')
		tracks = tuple(_track(t, to_px) for t in _split(rest, ' \t,'))
		if not tracks or not all(isinstance(t, TrackSize) for t in tracks):
			raise ValueError(f'repeat takes plain track sizes: {token!r}')
		return Repeat(repeat_count, tracks)
	if token.startswith('minmax(') and token.endswith(')'):
		low, sep, high = token[7:-1].partition(',')
		if not sep:
			raise ValueError(f'minmax needs two arguments: {token!r}')
		return TrackSize(min=_breadth(low.strip(), to_px, maximum=False), max=_breadth(high.strip(), to_px, maximum=True))
	if token.startswith('fit-content(') and token.endswith(')'):
		limit = _breadth(token[12:-1].strip(), to_px, maximum=False)
		if not _fixed(limit):
			raise ValueError(f'fit-content takes a length: {token!r}')
		return TrackSize(min=Keyword.auto, max=Keyword.max_content, limit=limit)
	length = _breadth(token, to_px, maximum=True)
	if _flexible(length):
		return TrackSize(min=Keyword.auto, max=length)
	return TrackSize(min=length, max=length)


def _expand(tracks: list[TrackSize | Repeat], available: float | None, gap: float) -> tuple[list[TrackSize], list[bool]]:
	"""Expand repeats. The flags say which tracks came from `auto-fit`, for later collapsing."""
	out, fit = [], []
	for entry in tracks:
		if isinstance(entry, Repeat):
			for _ in range(_repeat_count(entry, available, gap)):
				out.extend(entry.tracks)
				fit.extend([entry.count == 'auto-fit'] * len(entry.tracks))
		else:
			out.append(entry)
			fit.append(False)
	return out, fit


def _repeat_count(repeat: Repeat, available: float | None, gap: float) -> int:
	if isinstance(repeat.count, int):
		return repeat.count
	if available is None:
		return 1
	sizes = []
	for track in repeat.tracks:
		if _fixed(track.max) and _fixed(track.min):
			sizes.append(max(track.min, track.max))
		elif _fixed(track.max):
			sizes.append(track.max)
		elif _fixed(track.min):
			sizes.append(track.min)
		else:
			return 1
	pitch = max(sum(sizes) + gap * (len(sizes) - 1) + gap, 1.0)  # UA floor of 1px
	return max(1, floor((available + gap) / pitch + _EPS))


def _place_rows(placements: list[Placement], explicit_columns: int, dense: bool) -> list[tuple[int, int, int, int]]:
	"""§8.5 with `grid-auto-flow: row`. Returns zero-based `(column, row, column_span, row_span)`."""
	for p in placements:
		if (p.column_start is not None and p.column_start < 1) or (p.row_start is not None and p.row_start < 1):
			raise ValueError('grid lines are 1-based')
	n = len(placements)
	spans = [(p.column_span, p.row_span) for p in placements]
	pos: list[tuple[int, int] | None] = [None] * n
	occupied: set[tuple[int, int]] = set()

	def free(col: int, row: int, cs: int, rs: int) -> bool:
		return all((r, c) not in occupied for r in range(row, row + rs) for c in range(col, col + cs))

	def put(i: int, col: int, row: int) -> None:
		pos[i] = (col, row)
		cs, rs = spans[i]
		occupied.update((r, c) for r in range(row, row + rs) for c in range(col, col + cs))

	# Step 1: both lines given.
	for i, p in enumerate(placements):
		if p.column_start is not None and p.row_start is not None:
			put(i, p.column_start - 1, p.row_start - 1)

	# Step 2: row given, column automatic. Sparse packing keeps moving right within each row.
	row_cursor: dict[int, int] = {}
	for i, p in enumerate(placements):
		if p.row_start is None or p.column_start is not None:
			continue
		row = p.row_start - 1
		cs, rs = spans[i]
		rows = range(row, row + rs)
		col = 0 if dense else max(row_cursor.get(r, 0) for r in rows)
		while not free(col, row, cs, rs):
			col += 1
		put(i, col, row)
		for r in rows:
			row_cursor[r] = col + cs

	# Step 3: the implicit columns. They must hold every definite column and the widest auto span.
	count = explicit_columns
	for i, p in enumerate(placements):
		if pos[i] is not None:
			count = max(count, pos[i][0] + spans[i][0])
		elif p.column_start is not None:
			count = max(count, p.column_start - 1 + spans[i][0])
	widest = max((spans[i][0] for i, p in enumerate(placements) if pos[i] is None and p.column_start is None), default=0)
	count = max(count, widest)

	# Step 4: the rest, in order, with the auto-placement cursor.
	cur_row = cur_col = 0
	for i, p in enumerate(placements):
		if pos[i] is not None:
			continue
		cs, rs = spans[i]
		if p.column_start is not None:
			col = p.column_start - 1
			if dense:
				cur_row = 0
			elif col < cur_col:
				cur_row += 1
			cur_col = col
			row = cur_row
			while not free(col, row, cs, rs):
				row += 1
			cur_row = row
			put(i, col, row)
		else:
			if dense:
				cur_row = cur_col = 0
			while True:
				while cur_col + cs <= count and not free(cur_col, cur_row, cs, rs):
					cur_col += 1
				if cur_col + cs <= count:
					break
				cur_row += 1
				cur_col = 0
			put(i, cur_col, cur_row)

	return [(pos[i][0], pos[i][1], spans[i][0], spans[i][1]) for i in range(n)]


def _distribute(free: float, count: int, content: Alignment) -> tuple[float, float]:
	if content.value in (ContentAlign.normal, ContentAlign.stretch, ContentAlign.start, ContentAlign.flex_start):
		return 0.0, 0.0
	return distribute_content(free, count, content)


def _track_starts(sizes: list[float], gap: float, available: float | None, content: Alignment) -> list[float]:
	if not sizes:
		return []
	free = 0.0 if available is None else available - sum(sizes) - gap * (len(sizes) - 1)
	leading, between = _distribute(free, len(sizes), content)
	starts, x = [], leading
	for size in sizes:
		starts.append(x)
		x += size + gap + between
	return starts


def _box(start: float, area: float, low: float, high: float, alignment: Alignment) -> tuple[float, float]:
	"""Position and size of one item in its area. `low` and `high` are its min and max content."""
	if alignment.value in (ItemAlign.stretch, ItemAlign.normal):
		return start, area
	size = max(low, min(high, area))  # fit-content: max(min-content, min(max-content, available))
	if alignment.value in (ItemAlign.start, ItemAlign.flex_start, ItemAlign.baseline, ItemAlign.last_baseline):
		return start, size
	return start + align_offset(area - size, alignment), size


def _resolve_self(value: ItemAlign, default: Alignment) -> Alignment:
	return default if value is ItemAlign.auto else Alignment(value)


def _kept(fit: list[bool], used: set[int]) -> list[int]:
	return [i for i, is_fit in enumerate(fit) if not (is_fit and i not in used)]


def _pad(tracks: list[TrackSize], fit: list[bool], auto: TrackSize, count: int) -> tuple[list[TrackSize], list[bool]]:
	extra = count - len(tracks)
	return tracks + [auto] * extra, fit + [False] * extra


def _size_axis(tracks: list[TrackSize], items: list[GridItem], spans: list[tuple[int, int]], gap: float,
		available: float | None, axis: int, content: Alignment) -> list[float]:
	"""The five steps of §12 for one axis. Returns the base size of each track."""
	sized = [Track(size=t) for t in tracks]
	initialize_track_sizes(sized, available)
	resolve_intrinsic_track_sizes(sized, items, spans, gap, axis=axis)
	if available is not None:
		maximize_tracks(sized, available, gap)
	expand_flexible_tracks(sized, available, gap)
	if available is not None:
		stretch_auto_tracks(sized, available, gap, content)
	return [track.base for track in sized]


# --- public API ----------------------------------------------------------------------------

@implements('css-grid-1', 'Explicit Track Sizing: the grid-template-rows and grid-template-columns properties', '7.2', status='done')
def parse_track_list(value: str | list, to_px=None) -> list[TrackSize | Repeat]:
	"""Parse a track list from a `.levity` value such as `[1fr, 2fr]`, `'200px 1fr'`,
	`'repeat(3, 1fr)'` or `'repeat(auto-fit, minmax(16rem, 1fr))'`.

	Bare numbers and `px` are pixels. Other units need `to_px(value, unit) -> px`, which the
	caller supplies, so this stays free of Qt. `%` is refused: the caller resolves it against
	the container first. Anything else raises `ValueError` naming the bad token; a bad value
	becomes a red error tile.
	"""
	text = ' '.join(str(v) for v in value) if isinstance(value, list) else value
	text = text.strip().strip('\'"').strip()
	if text.startswith('[') and text.endswith(']'):
		text = text[1:-1]
	tracks = [_track(token, to_px) for token in _split(text, ' \t,')]
	if not tracks:
		raise ValueError('empty track list')
	return tracks


@implements('css-grid-1', 'Repeat-to-fill: auto-fill and auto-fit repetitions', '7.2.3.2', status='done')
def expand_repeat(tracks: list[TrackSize | Repeat], available: float | None, gap: float) -> list[TrackSize]:
	"""Expand every `Repeat` into plain tracks. For `auto-fill` and `auto-fit` the count is the
	largest that fits `available` with `gap`; at least one. `available` is the definite inner
	size, or None when it is indefinite (then one repetition). The minimum-size rule of §7.2.3.2
	needs a second size and is not modelled.

	`auto-fit` tracks are returned like any others. Collapsing the empty ones needs the
	placement, so `layout_grid` does it.
	"""
	return _expand(tracks, available, gap)[0]


@implements('css-grid-1', 'Grid Item Placement Algorithm', '8.5', status='done')
def place_items(items: list[GridItem], container: GridContainer, columns: int, rows: int) -> list[tuple[int, int, int, int]]:
	"""Return `(column, row, column_span, row_span)` for each item, 0-based, in item order.

	Process in the order of §8.5: definite positions first, then definite-row items, then
	auto-placement with the cursor, `sparse` or `dense`. Adds implicit tracks when an item
	falls outside the explicit grid; the caller reads the new track counts from the result.
	`columns` and `rows` are the explicit track counts. With `grid-auto-flow: column` the
	algorithm runs on the transposed grid.
	"""
	placements = [item.placement for item in items]
	if container.auto_flow != 'column':
		return _place_rows(placements, columns, container.dense)
	flipped = [Placement(p.row_start, p.row_span, p.column_start, p.column_span) for p in placements]
	return [(row, col, rs, cs) for col, row, cs, rs in _place_rows(flipped, rows, container.dense)]


@implements('css-grid-1', 'Initialize Track Sizes', None, status='done')
def initialize_track_sizes(tracks: list[Track], available: float | None) -> None:
	"""Step 1 of the Grid Layout Algorithm track sizing: set each track's base size and growth
	limit from its min and max sizing functions. A length gives itself. `auto`, `min-content`
	and `max-content` give 0 for the base and INF for the limit. `fr` as a max gives INF.

	`available` is not used: lengths are already in pixels. It stays so that a caller with a
	percentage track can pass the container size later.
	"""
	for track in tracks:
		low, high = track.size.min, track.size.max
		track.base = low if _fixed(low) else 0.0
		track.limit = high if _fixed(high) else INF
		if track.limit < track.base:
			track.limit = track.base


@implements('css-grid-1', 'Resolve Intrinsic Track Sizes', None, status='done')
def resolve_intrinsic_track_sizes(tracks: list[Track], items: list[GridItem], spans: list[tuple[int, int]], gap: float, axis: int = 0) -> None:
	"""Step 2: grow `base` and `limit` from the sizes of the items, in order of span count.

	Items that span one track first; then items that span several, with the extra space shared
	among the spanned tracks. Items that span a flexible track are handled by
	`expand_flexible_tracks`. `spans[i]` is `(start_track, span)` for item `i` on this axis.
	`axis` picks the width (0) or the height (1) of each item's contributions.
	"""

	def minimum(i: int) -> float:
		size = items[i].min_size[axis]
		return items[i].min_content[axis] if size is None else size

	def smallest(i: int) -> float:
		return items[i].min_content[axis]

	def largest(i: int) -> float:
		return items[i].max_content[axis]

	def phases(group: list[int], include=_any, weight=_one) -> None:
		common = {'include': include, 'weight': weight}
		intrinsic_max = lambda t: _intrinsic(t.size.max)
		_accommodate(tracks, group, spans, gap, contribution=minimum, growth=False, **common,
			affected=lambda t: _intrinsic(t.size.min), prefer=intrinsic_max)
		_accommodate(tracks, group, spans, gap, contribution=smallest, growth=False, **common,
			affected=lambda t: t.size.min in (Keyword.min_content, Keyword.max_content), prefer=intrinsic_max)
		_accommodate(tracks, group, spans, gap, contribution=largest, growth=False, **common,
			affected=lambda t: t.size.min is Keyword.max_content, prefer=lambda t: t.size.max is Keyword.max_content)
		_settle(tracks)
		_accommodate(tracks, group, spans, gap, contribution=smallest, growth=True, **common,
			affected=intrinsic_max, prefer=_any)
		_accommodate(tracks, group, spans, gap, contribution=largest, growth=True, **common,
			affected=lambda t: _intrinsic(t.size.max), prefer=_any)
		_settle(tracks)

	# Single-track items: size each intrinsic track to its own items.
	for t, track in enumerate(tracks):
		if _is_flex(track):
			continue
		members = [i for i, (start, span) in enumerate(spans) if span == 1 and start == t]
		if not members:
			continue
		if track.size.min is Keyword.min_content:
			track.base = max(track.base, max(smallest(i) for i in members))
		elif track.size.min is Keyword.max_content:
			track.base = max(track.base, max(largest(i) for i in members))
		elif _intrinsic(track.size.min):
			track.base = max(track.base, max(minimum(i) for i in members))
		if _intrinsic(track.size.max):
			value = max(smallest(i) for i in members) if track.size.max is Keyword.min_content else max(largest(i) for i in members)
			track.limit = value if isinf(track.limit) else max(track.limit, value)
	_settle(tracks)

	# Spanning items that do not touch a flexible track, smallest span first.
	multi = [i for i, (start, span) in enumerate(spans) if span > 1 and not any(_is_flex(tracks[t]) for t in range(start, start + span))]
	for span in sorted({spans[i][1] for i in multi}):
		phases([i for i in multi if spans[i][1] == span])

	# Spanning items that touch a flexible track: only the flexible tracks grow.
	flexed = [i for i, (start, span) in enumerate(spans) if any(_is_flex(tracks[t]) for t in range(start, start + span))]
	if flexed:
		phases(flexed, include=_is_flex, weight=lambda t: t.size.max.value)

	for track in tracks:
		if isinf(track.limit):
			track.limit = track.base


@implements('css-grid-1', 'Maximize Tracks', None, status='done')
def maximize_tracks(tracks: list[Track], available: float, gap: float) -> None:
	"""Step 3: if free space is positive, raise each track's base size toward its growth limit,
	equally, until the space is gone or every base equals its limit."""
	if not tracks:
		return
	free = available - sum(t.base for t in tracks) - gap * (len(tracks) - 1)
	if free <= _EPS:
		return
	room = {i: max(0.0, t.limit - t.base) for i, t in enumerate(tracks)}
	for i, value in _share(free, list(range(len(tracks))), room).items():
		tracks[i].base += value


def _find_fr(tracks: list[Track], space: float) -> float:
	"""§12.7.1 "Find the Size of an fr". The largest fr that fits `space` without any flexible
	track going under its base size."""
	inflexible: set[int] = set()
	while True:
		flexible = [i for i, t in enumerate(tracks) if _is_flex(t) and i not in inflexible]
		if not flexible:
			return 0.0
		leftover = space - sum(t.base for i, t in enumerate(tracks) if i not in flexible)
		total = sum(tracks[i].size.max.value for i in flexible)
		hypothetical = leftover / max(total, 1.0)
		too_small = [i for i in flexible if hypothetical * tracks[i].size.max.value < tracks[i].base]
		if not too_small:
			return hypothetical
		inflexible.update(too_small)


@implements('css-grid-1', 'Expand Flexible Tracks', None, status='done')
def expand_flexible_tracks(tracks: list[Track], available: float | None, gap: float) -> None:
	"""Step 4: size the `fr` tracks. Find the size of an `fr` by the spec's "find the size of an
	fr" procedure (treat a flex factor sum below 1 as 1), freeze tracks whose base size is
	larger than their share, and repeat.

	With `available=None` the flex fraction comes from the tracks alone (see the module note).
	"""
	flexible = [t for t in tracks if _is_flex(t)]
	if not flexible:
		return
	gutters = gap * (len(tracks) - 1)
	if available is None:
		fraction = max(
			(t.base / t.size.max.value if t.size.max.value > 1 else t.base) for t in flexible
		)
	else:
		if available - gutters - sum(t.base for t in tracks) <= _EPS:
			return
		fraction = _find_fr(tracks, available - gutters)
	for t in flexible:
		t.base = max(t.base, fraction * t.size.max.value)


@implements('css-grid-1', 'Stretch auto Tracks', None, status='done')
def stretch_auto_tracks(tracks: list[Track], available: float, gap: float, align: Alignment) -> None:
	"""Step 5: when `justify-content` or `align-content` is `normal` or `stretch`, share the
	remaining free space equally among tracks whose max sizing function is `auto`."""
	if align.value not in (ContentAlign.normal, ContentAlign.stretch):
		return
	free = available - sum(t.base for t in tracks) - gap * (len(tracks) - 1)
	autos = [t for t in tracks if t.size.max is Keyword.auto]
	if free <= _EPS or not autos:
		return
	for t in autos:
		t.base += free / len(autos)


@implements('css-grid-1', 'Grid Layout Algorithm', '12', status='done')
def layout_grid(items: list[GridItem], container: GridContainer) -> list[Rect]:
	"""Lay out `items` in `container`. Returns one `Rect` per item, in the order given.

	Calls, in order: `expand_repeat`, `place_items`, then the five sizing steps for columns and
	then rows, then positions tracks with the gaps and `justify-content` / `align-content`, and
	places each item in its area with `justify-self` / `align-self` (see `align.py`).

	Empty `auto-fit` tracks collapse after placement, as §7.2.3.2 says: they are removed and the
	gutters around them go with them. Rects are relative to the container's content box.
	"""
	col_tracks, col_fit = _expand(container.columns, container.width, container.gap.column)
	row_tracks, row_fit = _expand(container.rows, container.height, container.gap.row)
	placed = place_items(items, container, len(col_tracks), len(row_tracks))

	count_cols = max([len(col_tracks)] + [c + cs for c, _, cs, _ in placed])
	count_rows = max([len(row_tracks)] + [r + rs for _, r, _, rs in placed])
	col_tracks, col_fit = _pad(col_tracks, col_fit, container.auto_columns, count_cols)
	row_tracks, row_fit = _pad(row_tracks, row_fit, container.auto_rows, count_rows)

	used_cols = {c + k for c, _, cs, _ in placed for k in range(cs)}
	used_rows = {r + k for _, r, _, rs in placed for k in range(rs)}
	keep_cols = _kept(col_fit, used_cols)
	keep_rows = _kept(row_fit, used_rows)
	new_col = {old: new for new, old in enumerate(keep_cols)}
	new_row = {old: new for new, old in enumerate(keep_rows)}
	placed = [(new_col[c], new_row[r], cs, rs) for c, r, cs, rs in placed]
	col_tracks = [col_tracks[i] for i in keep_cols]
	row_tracks = [row_tracks[i] for i in keep_rows]

	col_spans = [(c, cs) for c, _, cs, _ in placed]
	row_spans = [(r, rs) for _, r, _, rs in placed]
	col_sizes = _size_axis(col_tracks, items, col_spans, container.gap.column, container.width, 0, container.justify_content)
	row_sizes = _size_axis(row_tracks, items, row_spans, container.gap.row, container.height, 1, container.align_content)
	col_starts = _track_starts(col_sizes, container.gap.column, container.width, container.justify_content)
	row_starts = _track_starts(row_sizes, container.gap.row, container.height, container.align_content)

	rects = []
	for item, (c, r, cs, rs) in zip(items, placed):
		x0 = col_starts[c]
		area_w = col_starts[c + cs - 1] + col_sizes[c + cs - 1] - x0
		y0 = row_starts[r]
		area_h = row_starts[r + rs - 1] + row_sizes[r + rs - 1] - y0
		x, w = _box(x0, area_w, item.min_content[0], item.max_content[0], _resolve_self(item.justify_self, container.justify_items))
		y, h = _box(y0, area_h, item.min_content[1], item.max_content[1], _resolve_self(item.align_self, container.align_items))
		rects.append(Rect(x, y, w, h))
	return rects
