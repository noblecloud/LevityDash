"""Anchor positioning math, and the checks on what `align-to:` may say."""
import pytest

from LevityDash.lib.layout.anchor import Anchor, AnchorError, place


def test_centre_on_centre_is_the_default():
	a = Anchor.decode('a')
	assert place(a, (100, 50, 200, 100), (40, 20), (0, 0)) == (180.0, 90.0)


def test_below_and_centred_with_an_offset():
	a = Anchor.decode({'to': 'a', 'x': 'center', 'y': 'bottom', 'self-y': 'top'})
	assert place(a, (100, 50, 200, 100), (40, 20), (0, 0), (0, 5)) == (180.0, 155.0)


def test_right_edge_to_left_edge_and_an_axis_left_out_stays():
	a = Anchor.decode({'to': 'a', 'x': 'left', 'self-x': 'right'})
	assert place(a, (100, 50, 200, 100), (40, 20), (7, 9)) == (60.0, 9)


@pytest.mark.parametrize('spec, words', [
	({}, 'to'), ({'to': 'a', 'x': 'middle'}, 'middle'), ({'to': 'a', 'nope': 1}, 'nope'),
	({'to': 'a', 'self-x': 'left'}, 'self-x'), ({'to': 'a', 'offset': 5}, 'offset'), (5, 'sibling'),
])
def test_wrong_specs_say_why(spec, words):
	with pytest.raises(AnchorError, match=words):
		Anchor.decode(spec)
