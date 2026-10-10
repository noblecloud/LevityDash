"""CSS Grid Layout: tracks, placement and the track sizing algorithm.

Spec: https://www.w3.org/TR/css-grid-1/ Sections 7, 8 and 12.

Pure functions. No Qt. Sizes are pixels. See `types.py` for the conventions.
Out of scope: `subgrid`, named areas by string art, masonry, intrinsic sizing from
wrapped text. Do not add them without asking.
"""

from dataclasses import dataclass, field
from enum import Enum

from .spec import implements
from .types import Alignment, ContentAlign, Gap, INF, ItemAlign, Rect

__all__ = [
	'Fr', 'Keyword', 'TrackSize', 'Repeat', 'GridContainer', 'GridItem', 'Placement', 'Track',
	'parse_track_list', 'expand_repeat', 'place_items', 'initialize_track_sizes',
	'resolve_intrinsic_track_sizes', 'maximize_tracks', 'expand_flexible_tracks',
	'stretch_auto_tracks', 'layout_grid',
]


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


@implements('css-grid-1', 'Explicit Track Sizing: the grid-template-rows and grid-template-columns properties', '7.2')
def parse_track_list(value: str | list) -> list[TrackSize | Repeat]:
	"""Parse a track list from a `.levity` value such as `[1fr, 2fr]`, `'200px 1fr'`,
	`'repeat(3, 1fr)'` or `'repeat(auto-fit, minmax(16rem, 1fr))'`.

	Accept lengths with the units `parseSize` already takes. Reject anything else with a
	`ValueError` that names the bad token; a bad value becomes a red error tile.
	"""
	raise NotImplementedError


@implements('css-grid-1', 'Repeat-to-fill: auto-fill and auto-fit repetitions', '7.2.3.2')
def expand_repeat(tracks: list[TrackSize | Repeat], available: float | None, gap: float) -> list[TrackSize]:
	"""Expand every `Repeat` into plain tracks. For `auto-fill` and `auto-fit` the count is the
	largest that fits `available` with `gap`; at least one. `auto-fit` collapses repetitions
	that hold no items once placement is known (call again after `place_items`).
	"""
	raise NotImplementedError


@implements('css-grid-1', 'Grid Item Placement Algorithm', '8.5')
def place_items(items: list[GridItem], container: GridContainer, columns: int, rows: int) -> list[tuple[int, int, int, int]]:
	"""Return `(column, row, column_span, row_span)` for each item, 0-based, in item order.

	Process in the order of §8.5: definite positions first, then definite-row items, then
	auto-placement with the cursor, `sparse` or `dense`. Adds implicit tracks when an item
	falls outside the explicit grid; the caller reads the new track counts from the result.
	"""
	raise NotImplementedError


@implements('css-grid-1', 'Initialize Track Sizes', None)
def initialize_track_sizes(tracks: list[Track], available: float | None) -> None:
	"""Step 1 of the Grid Layout Algorithm track sizing: set each track's base size and growth
	limit from its min and max sizing functions. A length gives itself. `auto`, `min-content`
	and `max-content` give 0 for the base and INF for the limit. `fr` as a max gives INF.
	"""
	raise NotImplementedError


@implements('css-grid-1', 'Resolve Intrinsic Track Sizes', None)
def resolve_intrinsic_track_sizes(tracks: list[Track], items: list[GridItem], spans: list[tuple[int, int]], gap: float) -> None:
	"""Step 2: grow `base` and `limit` from the sizes of the items, in order of span count.

	Items that span one track first; then items that span several, with the extra space shared
	among the spanned tracks. Items that span a flexible track are handled by
	`expand_flexible_tracks`. `spans[i]` is `(start_track, span)` for item `i` on this axis.
	"""
	raise NotImplementedError


@implements('css-grid-1', 'Maximize Tracks', None)
def maximize_tracks(tracks: list[Track], available: float, gap: float) -> None:
	"""Step 3: if free space is positive, raise each track's base size toward its growth limit,
	equally, until the space is gone or every base equals its limit."""
	raise NotImplementedError


@implements('css-grid-1', 'Expand Flexible Tracks', None)
def expand_flexible_tracks(tracks: list[Track], available: float | None, gap: float) -> None:
	"""Step 4: size the `fr` tracks. Find the size of an `fr` by the spec's "find the size of an
	fr" procedure (treat a flex factor sum below 1 as 1), freeze tracks whose base size is
	larger than their share, and repeat.
	"""
	raise NotImplementedError


@implements('css-grid-1', 'Stretch auto Tracks', None)
def stretch_auto_tracks(tracks: list[Track], available: float, gap: float, align: Alignment) -> None:
	"""Step 5: when `justify-content` or `align-content` is `normal` or `stretch`, share the
	remaining free space equally among tracks whose max sizing function is `auto`."""
	raise NotImplementedError


@implements('css-grid-1', 'Grid Layout Algorithm', '12')
def layout_grid(items: list[GridItem], container: GridContainer) -> list[Rect]:
	"""Lay out `items` in `container`. Returns one `Rect` per item, in the order given.

	Calls, in order: `expand_repeat`, `place_items`, then the five sizing steps for columns and
	then rows, then positions tracks with the gaps and `justify-content` / `align-content`, and
	places each item in its area with `justify-self` / `align-self` (see `align.py`).
	"""
	raise NotImplementedError
