"""Grid layout, checked against the examples and worked rules in css-grid-1 (sections 7.2, 7.2.3.2, 8.5, 12).

Lengths are pixels. A test's numbers are worked out by hand from the spec text, not copied from a browser.
"""
import pytest

from LevityDash.lib.layout.grid import (
	Fr, GridContainer, GridItem, Keyword, Placement, Repeat, Track, TrackSize,
	expand_repeat, layout_grid, parse_track_list, place_items,
	initialize_track_sizes, resolve_intrinsic_track_sizes, maximize_tracks,
)
from LevityDash.lib.layout.types import Gap
from LevityDash.lib.layout.types import ItemAlign


def item(**kwargs) -> GridItem:
	return GridItem(**kwargs)


def at(column=None, row=None, column_span=1, row_span=1, **kwargs) -> GridItem:
	return GridItem(placement=Placement(column, column_span, row, row_span), **kwargs)


# --- 7.2: track lists ----------------------------------------------------------------------

def test_parse_track_list_brackets_and_commas():
	assert parse_track_list('[1fr, 2fr]') == [TrackSize(Keyword.auto, Fr(1)), TrackSize(Keyword.auto, Fr(2))]


def test_parse_track_list_lengths_and_fr_in_a_string():
	assert parse_track_list('200px 1fr') == [TrackSize(200.0, 200.0), TrackSize(Keyword.auto, Fr(1))]


def test_parse_track_list_repeat():
	assert parse_track_list('repeat(3, 1fr)') == [Repeat(3, (TrackSize(Keyword.auto, Fr(1)),))]


def test_parse_track_list_auto_fit_with_a_unit_resolver():
	result = parse_track_list('repeat(auto-fit, minmax(16rem, 1fr))', to_px=lambda v, u: v * 16 if u == 'rem' else None)
	assert result == [Repeat('auto-fit', (TrackSize(256.0, Fr(1)),))]


def test_parse_track_list_keywords_and_fit_content():
	assert parse_track_list('auto min-content fit-content(120px)') == [
		TrackSize(Keyword.auto, Keyword.auto),
		TrackSize(Keyword.min_content, Keyword.min_content),
		TrackSize(Keyword.auto, Keyword.max_content, limit=120.0),
	]


@pytest.mark.parametrize('text, bad', [
	('10%', '10%'),  # % needs the container, the caller resolves it
	('-5px', '-5px'),
	('2xy 1fr', '2xy'),  # unit with no resolver
	('minmax(1fr, 2px)', '1fr'),  # fr is only a max
	('repeat(0, 1fr)', '0'),
])
def test_parse_track_list_names_the_bad_token(text, bad):
	with pytest.raises(ValueError, match=bad):
		parse_track_list(text)


# --- 7.2.3.2: repeat to fill ---------------------------------------------------------------

def test_auto_fill_fits_as_many_as_the_width_allows():
	# repeat(auto-fill, minmax(100px, 1fr)) in 350px: three columns, the remainder shared by fr.
	tracks = [Repeat('auto-fill', (TrackSize(100.0, Fr(1)),))]
	assert len(expand_repeat(tracks, 350.0, 0.0)) == 3


def test_auto_fill_counts_the_gutters_between_repeated_tracks():
	tracks = [Repeat('auto-fill', (TrackSize(100.0, Fr(1)),))]
	assert len(expand_repeat(tracks, 350.0, 10.0)) == 3  # 3*100 + 2*10 = 320 fits, 4*100 + 3*10 = 430 does not
	assert len(expand_repeat(tracks, 430.0, 10.0)) == 4  # exactly fits


def test_auto_fill_is_one_repetition_when_it_would_overflow_or_is_indefinite():
	tracks = [Repeat('auto-fill', (TrackSize(100.0, Fr(1)),))]
	assert len(expand_repeat(tracks, 50.0, 0.0)) == 1
	assert len(expand_repeat(tracks, None, 0.0)) == 1


def test_auto_fill_repeats_the_whole_track_list():
	# one repetition is 100 + 50 = 150px; 400px holds two of them
	tracks = [Repeat('auto-fill', (TrackSize(100.0, 100.0), TrackSize(50.0, 50.0)))]
	assert [t.min for t in expand_repeat(tracks, 400.0, 0.0)] == [100.0, 50.0, 100.0, 50.0]


# --- 8.5: placement ------------------------------------------------------------------------

def test_placement_spec_example_adds_an_implicit_column():
	# §8.5: repeat(5, 100px), an item at grid-column 4 / span 3 needs 6 columns.
	container = GridContainer()
	result = place_items([at(column=4, column_span=3)], container, 5, 1)
	assert result == [(3, 0, 3, 1)]
	assert max(5, result[0][0] + result[0][2]) == 6


def test_sparse_auto_placement_skips_occupied_cells():
	container = GridContainer()
	items = [at(column=2), item()]  # A is pinned to column 2, B is auto
	assert place_items(items, container, 3, 1) == [(1, 0, 1, 1), (2, 0, 1, 1)]


def test_dense_auto_placement_goes_back_to_the_start():
	container = GridContainer(dense=True)
	items = [at(column=2), item()]
	assert place_items(items, container, 3, 1) == [(1, 0, 1, 1), (0, 0, 1, 1)]


def test_auto_placement_wraps_to_a_new_row():
	container = GridContainer()
	result = place_items([at(column_span=2), at(column_span=2), item()], container, 3, 1)
	assert result == [(0, 0, 2, 1), (0, 1, 2, 1), (2, 1, 1, 1)]


def test_column_flow_fills_down_first():
	container = GridContainer(auto_flow='column')
	assert place_items([item(), item()], container, 3, 2) == [(0, 0, 1, 1), (0, 1, 1, 1)]


# --- 12: track sizing ----------------------------------------------------------------------

def _grid(width=None, height=None, **kwargs) -> GridContainer:
	return GridContainer(width=width, height=height, **kwargs)


def test_fr_tracks_share_the_leftover_space():
	container = _grid(300.0, 10.0, columns=[TrackSize(Keyword.auto, Fr(1)), TrackSize(Keyword.auto, Fr(2))],
		rows=[TrackSize(10.0, 10.0)])
	first, second = layout_grid([at(), at(column=2)], container)
	assert (first.x, first.width) == (0.0, 100.0)
	assert (second.x, second.width) == (100.0, 200.0)


def test_fixed_then_fr():
	container = _grid(400.0, 10.0, columns=parse_track_list('[100px, 1fr, 2fr]'), rows=[TrackSize(10.0, 10.0)])
	widths = [r.width for r in layout_grid([at(column=1), at(column=2), at(column=3)], container)]
	assert widths == [100.0, 100.0, 200.0]


def test_fr_factors_below_one_leave_space_unfilled():
	# §7.2.3 text: 0.5fr and 0.25fr take what they ask for, the rest stays empty. Flex sum below 1 counts as 1.
	container = _grid(300.0, 10.0, columns=parse_track_list('[0.5fr, 0.25fr]'), rows=[TrackSize(10.0, 10.0)])
	widths = [r.width for r in layout_grid([at(column=1), at(column=2)], container)]
	assert widths == [150.0, 75.0]


def test_auto_tracks_grow_to_content_then_stretch():
	# No spanning items. Base = min-content, limit = max-content. Maximize to the limits, then stretch.
	container = _grid(300.0, 10.0, columns=[TrackSize(), TrackSize()], rows=[TrackSize(10.0, 10.0)])
	items = [
		at(column=1, min_content=(50.0, 10.0), max_content=(80.0, 10.0)),
		at(column=2, min_content=(30.0, 10.0), max_content=(120.0, 10.0)),
	]
	first, second = layout_grid(items, container)
	assert (first.width, second.width) == (130.0, 170.0)


def test_a_spanning_item_splits_its_growth_equally():
	# §12.5 phase 5: max-content 300 over two auto tracks with base 100 each -> limits 150 each.
	tracks = [Track(TrackSize()), Track(TrackSize())]
	items = [at(column=1, column_span=2, min_content=(200.0, 10.0), max_content=(300.0, 10.0))]
	initialize_track_sizes(tracks, 300.0)
	resolve_intrinsic_track_sizes(tracks, items, [(0, 2)], 0.0)
	assert [t.base for t in tracks] == [100.0, 100.0]
	assert [t.limit for t in tracks] == [150.0, 150.0]
	maximize_tracks(tracks, 300.0, 0.0)
	assert [t.base for t in tracks] == [150.0, 150.0]


def test_gutters_go_between_tracks_not_around_them():
	container = _grid(300.0, 10.0, columns=parse_track_list('[100px, 100px]'), rows=[TrackSize(10.0, 10.0)],
		gap=Gap(0.0, 10.0))
	first, second = layout_grid([at(column=1), at(column=2)], container)
	assert (first.x, second.x) == (0.0, 110.0)


def test_stretch_fills_the_item_area_by_default():
	container = _grid(200.0, 40.0, columns=[TrackSize(100.0, 100.0)], rows=[TrackSize(40.0, 40.0)])
	rect, = layout_grid([at(min_content=(20.0, 10.0), max_content=(60.0, 10.0))], container)
	assert (rect.width, rect.height) == (100.0, 40.0)


def test_start_alignment_fits_the_item_to_its_content():
	container = _grid(200.0, 40.0, columns=[TrackSize(100.0, 100.0)], rows=[TrackSize(40.0, 40.0)])
	rect, = layout_grid([at(min_content=(20.0, 10.0), max_content=(60.0, 10.0),
		justify_self=ItemAlign.start, align_self=ItemAlign.start)], container)
	assert (rect.x, rect.width, rect.height) == (0.0, 60.0, 10.0)


def test_auto_fit_tracks_collapse_when_empty():
	# §7.2.3.2: auto-fit in 400px gives four 100px columns; only two hold items, so the other two go.
	container = _grid(400.0, 10.0, columns=[Repeat('auto-fit', (TrackSize(100.0, 100.0),))],
		rows=[TrackSize(10.0, 10.0)])
	first, second = layout_grid([at(column=1, row=1), at(column=2, row=1)], container)
	assert (first.x, first.width) == (0.0, 100.0)
	assert (second.x, second.width) == (100.0, 100.0)


def test_auto_fill_keeps_its_empty_tracks():
	container = _grid(400.0, 10.0, columns=[Repeat('auto-fill', (TrackSize(100.0, 100.0),))],
		rows=[TrackSize(10.0, 10.0)])
	rects = layout_grid([at(column=1, row=1)], container)
	assert len(rects) == 1
	# the four columns exist; the item sits in the first one
	assert rects[0].x == 0.0 and rects[0].width == 100.0
