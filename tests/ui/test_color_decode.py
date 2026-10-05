"""The plain colour forms `Color.decode` promises: hex, colour names, channel numbers, lists and dicts."""
import pytest

from LevityDash.lib.ui.colors import Color


@pytest.mark.parametrize('value,expected', [
	# names whose letters include hex digits, which the old hex search misread
	('red', '#ff0000'),
	('black', '#000000'),
	('green', '#008000'),
	('aliceblue', '#f0f8ff'),
	# hex; short forms double each digit, as CSS does
	('#ff8800', '#ff8800'),
	('ff8800', '#ff8800'),
	('0xFF8800', '#ff8800'),
	('#f80', '#ff8800'),
	('#f808', '#ff880088'),
	('#ff880080', '#ff880080'),
	# channel numbers
	('255 136 0', '#ff8800'),
	('255, 136, 0, 128', '#ff880080'),
	('1.0 0.5 0', '#ff8000'),
	# lists
	((255, 136, 0), '#ff8800'),
	([1.0, 0.0, 0.0], '#ff0000'),
	([255, 136, 0, 128], '#ff880080'),
	# dicts, short and long keys
	({'r': 255, 'g': 136, 'b': 0}, '#ff8800'),
	({'red': 0, 'green': 128, 'blue': 255, 'alpha': 128}, '#0080ff80'),
])
def test_decode(value, expected):
	assert Color.decode(value).hex == expected


def test_decode_leaves_the_mapping_alone():
	value = {'r': 255, 'g': 0, 'b': 0, 'name': 'alarm'}
	color = Color.decode(value)
	assert color.name == 'alarm'
	assert value == {'r': 255, 'g': 0, 'b': 0, 'name': 'alarm'}


def test_unknown_string_raises():
	with pytest.raises(ValueError):
		Color.decode('nonsense')
