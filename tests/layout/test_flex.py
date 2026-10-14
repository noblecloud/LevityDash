"""Flexbox §9 tests. Each case states the rule of the spec section it checks.

The spec gives rules, not numbered examples, for the freeze loop and alignment. The numbers
below follow those rules by hand, so a failure names the rule that broke.
"""
import math

import pytest

from LevityDash.lib.layout import flex
from LevityDash.lib.layout.flex import FlexContainer, FlexItem
from LevityDash.lib.layout.types import Alignment, ContentAlign, Direction, Edge, Gap, INF, ItemAlign, Rect, Wrap


def approx(values):
	return pytest.approx(values, abs=1e-6)


def item(**kwargs):
	return FlexItem(**kwargs)


# §9.2: flex base size and hypothetical main size

def test_base_size_prefers_basis_then_main_then_content():
	assert flex.flex_base_and_hypothetical_size(item(basis=50, main=120, content_main=75), None)[0] == 50
	assert flex.flex_base_and_hypothetical_size(item(main=120, content_main=75), None)[0] == 120
	assert flex.flex_base_and_hypothetical_size(item(content_main=75), None)[0] == 75


def test_hypothetical_size_is_base_clamped_by_min_and_max():
	assert flex.flex_base_and_hypothetical_size(item(basis=150, max_main=100), None) == (150, 100)
	assert flex.flex_base_and_hypothetical_size(item(basis=10, min_main=40), None) == (10, 40)


def test_min_wins_over_max_and_size_is_not_negative():
	assert flex.flex_base_and_hypothetical_size(item(basis=50, min_main=80, max_main=60), None)[1] == 80
	assert flex.flex_base_and_hypothetical_size(item(basis=-20), None)[1] == 0


# §9.7: resolving flexible lengths

def test_grow_shares_free_space_in_proportion_to_flex_grow():
	items = [item(grow=1, basis=0), item(grow=2, basis=0)]
	assert flex.resolve_flexible_lengths(items, 300, 0) == approx([100, 200])


def test_grow_takes_gaps_out_of_the_free_space():
	items = [item(grow=1, basis=0), item(grow=1, basis=0)]
	assert flex.resolve_flexible_lengths(items, 210, 10) == approx([100, 100])


def test_inflexible_item_keeps_its_hypothetical_size():
	items = [item(grow=0, basis=50), item(grow=1, basis=0)]
	assert flex.resolve_flexible_lengths(items, 200, 0) == approx([50, 150])


def test_grow_factor_below_one_leaves_space_unused():
	# Spec step: a sum of grow factors under one scales the free space down.
	assert flex.resolve_flexible_lengths([item(grow=0.25, basis=0)], 400, 0) == approx([100])


def test_shrink_is_weighted_by_flex_shrink_times_base_size():
	# 100 and 300 with equal shrink: the scaled factors are 1:3, overflow 200 splits 50 and 150.
	items = [item(basis=100), item(basis=300)]
	assert flex.resolve_flexible_lengths(items, 200, 0) == approx([50, 150])


def test_shrink_stops_at_min_and_redistributes_the_rest():
	# A is clamped to its min of 90 and frozen; B takes the rest of the overflow.
	items = [item(basis=100, min_main=90), item(basis=100)]
	assert flex.resolve_flexible_lengths(items, 150, 0) == approx([90, 60])


def test_grow_stops_at_max_and_redistributes_the_rest():
	items = [item(grow=1, basis=0, max_main=100), item(grow=1, basis=0)]
	assert flex.resolve_flexible_lengths(items, 300, 0) == approx([100, 200])


# §9.3: collecting flex lines

def test_nowrap_is_always_one_line():
	container = FlexContainer(wrap=Wrap.nowrap, main=100)
	lines = flex.collect_flex_lines([item(basis=80), item(basis=80), item(basis=80)], container)
	assert [line.items for line in lines] == [[0, 1, 2]]


def test_wrap_breaks_before_an_item_that_does_not_fit_counting_gaps():
	container = FlexContainer(wrap=Wrap.wrap, main=250, gap=Gap(0, 10))
	lines = flex.collect_flex_lines([item(basis=100), item(basis=100), item(basis=100)], container)
	assert [line.items for line in lines] == [[0, 1], [2]]


def test_wrap_keeps_an_oversized_first_item_on_its_own_line():
	container = FlexContainer(wrap=Wrap.wrap, main=50)
	lines = flex.collect_flex_lines([item(basis=100), item(basis=10)], container)
	assert [line.items for line in lines] == [[0], [1]]


def test_order_changes_the_line_order_but_not_the_indices():
	container = FlexContainer(wrap=Wrap.nowrap)
	lines = flex.collect_flex_lines([item(order=2), item(order=1), item(order=0)], container)
	assert lines[0].items == [2, 1, 0]


# §8.1: auto margins

def test_auto_margin_takes_positive_free_space():
	items = [item(margin_main=Edge(None, 0)), item()]
	margins = flex.resolve_auto_margins(items, [100, 100], 500, 0)
	assert margins[0] == Edge(300, 0)
	assert margins[1] == Edge(0, 0)


def test_auto_margins_split_free_space_equally_and_become_zero_when_negative():
	items = [item(margin_main=Edge(None, None))]
	assert flex.resolve_auto_margins(items, [100], 300, 0) == [Edge(100, 100)]
	assert flex.resolve_auto_margins(items, [400], 300, 0) == [Edge(0, 0)]


# §9.5: main-axis alignment

@pytest.mark.parametrize('name, expected', [
	('flex-start', [0, 100]),
	('end', [300, 400]),
	('center', [150, 250]),
	('space-between', [0, 400]),
	('space-around', [75, 325]),
	('space-evenly', [100, 300]),
])
def test_justify_content_places_two_items_in_300_of_free_space(name, expected):
	# Two 100px items in a 500px line: 300px free, no margins, no gap.
	offsets = flex.align_main_axis([100, 100], [Edge(0, 0), Edge(0, 0)], 500, 0, Alignment(ContentAlign(name)))
	assert offsets == approx(expected)


def test_safe_center_with_negative_space_starts_at_zero():
	offsets = flex.align_main_axis([300], [Edge(0, 0)], 200, 0, Alignment(ContentAlign.center, safe=True))
	assert offsets == approx([0])


# §9.4: cross sizes

def test_single_line_with_definite_cross_size_uses_the_container_cross():
	container = FlexContainer(cross=80)
	lines = flex.collect_flex_lines([item(content_cross=30)], container)
	lines[0].main_sizes = [10]
	assert flex.cross_sizes(lines, [item(content_cross=30)], container) == approx([80])


def test_multi_line_cross_size_is_the_largest_outer_cross_size():
	items = [item(cross=20, margin_cross=Edge(5, 5)), item(cross=40)]
	container = FlexContainer(wrap=Wrap.wrap)
	lines = flex.collect_flex_lines(items, container)
	lines[0].main_sizes = [10, 10]
	assert flex.cross_sizes(lines, items, container) == approx([40])


def test_align_content_stretch_shares_leftover_cross_space_among_lines():
	container = FlexContainer(wrap=Wrap.wrap, cross=100, align_content=Alignment(ContentAlign.stretch))
	lines = [flex.FlexLine(items=[0], main_sizes=[0.0]), flex.FlexLine(items=[1], main_sizes=[0.0])]
	sizes = flex.cross_sizes(lines, [item(content_cross=20), item(content_cross=30)], container)
	assert sizes == approx([45, 55])  # 20 and 30, plus an equal share of the 50px left


# §9.6: cross-axis alignment

def run_cross(align, cross=100, size=40, margin=Edge(0, 0), cross_size=None):
	"""Place one item of cross size `size` in a line of cross size `cross`; returns (offset, size)."""
	items = [item(cross=cross_size, content_cross=size, margin_cross=margin, align_self=ItemAlign(align))]
	container = FlexContainer(cross=cross)
	lines = flex.collect_flex_lines(items, container)
	lines[0].main_sizes = [10]
	lines[0].cross = cross
	return flex.align_cross_axis(lines, items, container)[0]


@pytest.mark.parametrize('align, offset', [('flex-start', 0), ('center', 30), ('flex-end', 60)])
def test_align_self_places_an_item_in_its_line(align, offset):
	assert run_cross(align)[0] == approx(offset)


def test_stretch_grows_an_auto_cross_size_to_the_line():
	assert run_cross('stretch', cross_size=None) == approx((0, 100))


def test_auto_cross_margins_centre_an_item_when_there_is_room():
	assert run_cross('stretch', margin=Edge(None, None), cross_size=40) == approx((30, 40))


# §9: the whole algorithm

def test_three_items_row_with_gap_and_fixed_size():
	container = FlexContainer(direction=Direction.row, main=400, gap=Gap(0, 10))
	items = [item(basis=100, grow=0), item(basis=0, grow=1), item(basis=0, grow=1)]
	rects = flex.layout_flex(items, container)
	# 400 - 100 - two 10px gaps = 280 free, split 140 and 140.
	assert [r.width for r in rects] == approx([100, 140, 140])
	assert [r.x for r in rects] == approx([0, 110, 260])


def test_column_maps_main_to_y_and_cross_to_x():
	container = FlexContainer(direction=Direction.column, main=200, cross=50)
	items = [item(basis=50, grow=0, cross=None), item(basis=0, grow=1)]
	rects = flex.layout_flex(items, container)
	assert rects[0] == Rect(0, 0, 50, 50)
	assert rects[1] == Rect(0, 50, 50, 150)


def test_row_reverse_mirrors_the_main_axis():
	container = FlexContainer(direction=Direction.row_reverse, main=300)
	items = [item(basis=100, grow=0), item(basis=100, grow=0)]
	rects = flex.layout_flex(items, container)
	assert [r.x for r in rects] == approx([200, 100])


def test_indefinite_main_keeps_hypothetical_sizes():
	container = FlexContainer(main=None)
	rects = flex.layout_flex([item(basis=30, grow=5), item(basis=70, grow=5)], container)
	assert [r.width for r in rects] == approx([30, 70])


def test_empty_container_returns_no_rects():
	assert flex.layout_flex([], FlexContainer()) == []


def test_wrap_reverse_puts_the_first_line_at_the_cross_end():
	# Lines of 20 and 30 are stretched to 45 and 55 (align-content: stretch). Line one is at
	# the bottom, line two above it. In a wrap-reverse line, flex-start is the bottom edge.
	container = FlexContainer(wrap=Wrap.wrap_reverse, main=100, cross=100, direction=Direction.row)
	items = [item(basis=80, cross=20), item(basis=80, cross=30)]
	rects = flex.layout_flex(items, container)
	assert rects[0].y == approx(80)
	assert rects[1].y == approx(25)
