"""The Studio's rhythm checks: spacing off the theme's scale, and panels on different baselines."""
from types import SimpleNamespace as NS

from LevityDash.devtools import _studio_rhythm as rhythm
from LevityDash.devtools._studio_tiers import NOTE

SIZES = {'unit': '2mm', 'space_1': '1mm', 'space_2': '2mm', 'space_3': '4mm', 'space_4': '6mm', 'space_5': '8mm', 'space_6': '12mm', 'type_value': '125%'}


class Rect:
	def __init__(self, top, height):
		self._top, self._height = top, height

	def top(self):
		return self._top

	def height(self):
		return self._height

	def bottom(self):
		return self._top + self._height


def test_scale_keeps_only_spacing_steps_in_millimetres():
	assert rhythm.scale(SIZES) == {'space_1': 1.0, 'space_2': 2.0, 'space_3': 4.0, 'space_4': 6.0, 'space_5': 8.0, 'space_6': 12.0}


def test_lengths_on_the_scale_and_relative_values_are_fine():
	nodes = [((), {'spacing': '4mm', 'grid': {'gap': ['1mm', '0.4cm', '48px']}}), ((0,), {'spacing': '$space_3', 'margin': ['2%', 'auto', 0]}), ((1,), {'padding': 'calc(100% - 2mm)'})]
	assert rhythm.check_spacing(nodes, rhythm.scale(SIZES)) == []


def test_a_length_off_the_scale_names_the_item_and_the_nearest_steps():
	[found] = rhythm.check_spacing([((2, 1), {'spacing': '3mm'})], rhythm.scale(SIZES))
	assert found.severity == NOTE and found.path == (2, 1)
	assert '[2][1]' in found.message and '3mm' in found.message and '2mm or 4mm' in found.message


def test_flex_and_grid_settings_are_read_and_children_are_left_to_the_walk():
	nodes = [((), {'flex': {'margin': ['5mm', 0]}, 'items': [{'spacing': '7mm'}]})]
	found = rhythm.check_spacing(nodes, rhythm.scale(SIZES))
	assert len(found) == 1 and 'margin 5mm' in found[0].message


def test_no_theme_scale_means_no_findings():
	assert rhythm.check_spacing([((), {'spacing': '3mm'})], {}) == []


def member(path, top, height=20, font=18):
	return NS(path=path, rect=Rect(top, height), font=font)


def group(*members):
	return NS(unresolved=None, members=list(members))


def test_first_rows_that_are_a_few_pixels_apart_are_named():
	found = rhythm.check_baselines([group(member((0,), 10), member((1,), 14), member((0,), 60), member((1,), 64))])
	assert len(found) == 1 and '[0] and [1]' in found[0].message and '4px' in found[0].message


def test_first_rows_on_one_baseline_or_far_apart_or_of_other_sizes_are_not_named():
	assert rhythm.check_baselines([group(member((0,), 10), member((1,), 10))]) == []
	assert rhythm.check_baselines([group(member((0,), 10), member((1,), 100))]) == []
	assert rhythm.check_baselines([group(member((0,), 10, font=18), member((1,), 14, font=30))]) == []
