"""Box Alignment (css-align-3): gaps, content distribution, self-alignment, baselines.

The cases follow the normative rules of the spec: §4.3 distributed alignment and its fallbacks,
§4.4 `safe` and `unsafe` overflow, §5 self-alignment, §4.2 and §5.4 baselines.
"""
import pytest

from LevityDash.lib.layout import align
from LevityDash.lib.layout.spec import REGISTRY
from LevityDash.lib.layout.types import Alignment, ContentAlign, Gap, ItemAlign


def content(value: ContentAlign, *, safe: bool = False) -> Alignment:
	return Alignment(value, safe)


def item(value: ItemAlign, *, safe: bool = False) -> Alignment:
	return Alignment(value, safe)


def test_the_align_stubs_are_marked_done():
	for name in ('resolve_gap', 'distribute_content', 'align_offset', 'baseline_shifts'):
		section = REGISTRY[f'LevityDash.lib.layout.align.{name}']
		assert section.status == 'done', name
		assert section.spec == 'css-align-3', name


# Gaps: `normal` is 0 in flex and grid (spec 8).

def test_normal_gap_is_zero():
	assert align.resolve_gap(None, None) == Gap(0.0, 0.0)


def test_one_gap_value_sets_its_axis_only():
	assert align.resolve_gap(10, None) == Gap(10.0, 0.0)
	assert align.resolve_gap(None, 4) == Gap(0.0, 4.0)


def test_gap_shorthand_sets_both_axes():
	assert align.resolve_gap(8, 8) == Gap(8.0, 8.0)


def test_a_negative_gap_is_invalid():
	with pytest.raises(ValueError):
		align.resolve_gap(-1, None)


# Content distribution (spec 4.1 to 4.3).

@pytest.mark.parametrize('value', [ContentAlign.start, ContentAlign.flex_start])
def test_start_has_no_leading_offset(value):
	assert align.distribute_content(50, 3, content(value)) == (0.0, 0.0)


def test_end_pushes_all_free_space_to_the_leading_edge():
	assert align.distribute_content(50, 3, content(ContentAlign.end)) == (50.0, 0.0)


def test_center_splits_free_space_either_side():
	assert align.distribute_content(50, 3, content(ContentAlign.center)) == (25.0, 0.0)


def test_safe_end_falls_back_to_start_when_it_overflows():
	# §4.4: a safe alignment that overflows is aligned as flex-start.
	assert align.distribute_content(-20, 3, content(ContentAlign.end, safe=True)) == (0.0, 0.0)


def test_unsafe_center_overflows_both_edges():
	assert align.distribute_content(-20, 3, content(ContentAlign.center)) == (-10.0, 0.0)


def test_safe_center_falls_back_to_start_when_it_overflows():
	assert align.distribute_content(-20, 3, content(ContentAlign.center, safe=True)) == (0.0, 0.0)


def test_space_between_puts_equal_space_between_boxes():
	# Three boxes, 40 free: two gaps of 20, no leading space.
	assert align.distribute_content(40, 3, content(ContentAlign.space_between)) == (0.0, 20.0)


def test_space_between_with_one_box_falls_back_to_flex_start():
	assert align.distribute_content(40, 1, content(ContentAlign.space_between)) == (0.0, 0.0)


def test_space_between_with_negative_space_falls_back_to_flex_start():
	assert align.distribute_content(-40, 3, content(ContentAlign.space_between)) == (0.0, 0.0)


def test_space_around_gives_half_space_at_each_end():
	# Two boxes, 40 free: each box has 10 either side, so the middle gap is 20.
	leading, between = align.distribute_content(40, 2, content(ContentAlign.space_around))
	assert (leading, between) == (10.0, 20.0)
	assert leading + between + leading == 40


def test_space_around_with_one_box_centres_it():
	assert align.distribute_content(40, 1, content(ContentAlign.space_around)) == (20.0, 0.0)


def test_space_around_with_negative_space_falls_back_to_center_safely():
	assert align.distribute_content(-40, 2, content(ContentAlign.space_around)) == (0.0, 0.0)


def test_space_evenly_makes_every_slot_equal():
	# Three boxes, 40 free: four equal slots of 10 (both ends and the two gaps).
	assert align.distribute_content(40, 3, content(ContentAlign.space_evenly)) == (10.0, 10.0)


def test_space_evenly_with_one_box_centres_it():
	assert align.distribute_content(40, 1, content(ContentAlign.space_evenly)) == (20.0, 0.0)


def test_stretch_and_normal_add_no_offset():
	assert align.distribute_content(40, 3, content(ContentAlign.stretch)) == (0.0, 0.0)
	assert align.distribute_content(40, 3, content(ContentAlign.normal)) == (0.0, 0.0)


def test_no_boxes_means_no_offset():
	assert align.distribute_content(40, 0, content(ContentAlign.space_between)) == (0.0, 0.0)


# Self-alignment (spec 5).

def test_start_and_flex_start_put_the_box_at_the_start():
	assert align.align_offset(30, item(ItemAlign.start)) == 0.0
	assert align.align_offset(30, item(ItemAlign.flex_start)) == 0.0


def test_end_puts_the_box_at_the_end():
	assert align.align_offset(30, item(ItemAlign.end)) == 30.0
	assert align.align_offset(30, item(ItemAlign.flex_end)) == 30.0


def test_center_puts_the_box_in_the_middle():
	assert align.align_offset(30, item(ItemAlign.center)) == 15.0


def test_safe_center_with_negative_space_returns_zero():
	# The "safe center" rule: an overflowing centred box is pinned to the start.
	assert align.align_offset(-10, item(ItemAlign.center, safe=True)) == 0.0


def test_unsafe_center_with_negative_space_overflows_both_edges():
	assert align.align_offset(-10, item(ItemAlign.center)) == -5.0


def test_safe_end_with_negative_space_returns_zero():
	assert align.align_offset(-10, item(ItemAlign.end, safe=True)) == 0.0


@pytest.mark.parametrize('value', [ItemAlign.stretch, ItemAlign.baseline, ItemAlign.last_baseline, ItemAlign.auto])
def test_stretch_and_baseline_return_zero_for_the_caller_to_handle(value):
	assert align.align_offset(30, item(value)) == 0.0


def test_a_distributed_value_is_not_a_self_alignment():
	with pytest.raises(ValueError):
		align.align_offset(30, content(ContentAlign.space_between))


# Baselines (spec 4.2 and 5.4).

def test_first_baselines_line_up_on_the_furthest_from_the_top():
	# Box 1 has its baseline 14 below its top, so it sets the line. Box 0 moves down 4, box 2 down 2.
	assert align.baseline_shifts([10, 14, 12]) == [4.0, 0.0, 2.0]


def test_last_baselines_line_up_on_the_furthest_from_the_bottom():
	# Distances from the bottom edge. Box 1 sets the line, so box 0 moves up 4.
	assert align.baseline_shifts([3, 7], last=True) == [4.0, 0.0]


def test_one_box_needs_no_shift():
	assert align.baseline_shifts([9]) == [0.0]


def test_no_boxes_needs_no_shift():
	assert align.baseline_shifts([]) == []
