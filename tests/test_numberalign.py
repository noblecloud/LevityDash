"""Where a printed number is cut for column alignment. The text is never changed."""
import pytest

from LevityDash.lib.ui import numberalign


@pytest.mark.parametrize('text, mode, head, tail', [
	('72.4°', 'decimal', '72', '.4°'),
	('44%', 'decimal', '44', '%'),
	('0', 'decimal', '0', ''),
	('0.0', 'decimal', '0', '.0'),
	('.02', 'decimal', '', '.02'),
	('19.4 mi', 'decimal', '19', '.4 mi'),
	('1,234.5', 'decimal', '1,234', '.5'),
	('1,5', 'decimal', '1', ',5'),
	('1,234', 'decimal', '1,234', ''),
	('-3.5°', 'decimal', '-3', '.5°'),
	('72.4°', 'end', '72.4', '°'),
	('11 mph', 'end', '11', ' mph'),
	('WSW', 'decimal', 'WSW', ''),
	('', 'decimal', '', ''),
	('-', 'end', '-', ''),
])
def test_split(text, mode, head, tail):
	assert numberalign.split(text, mode) == (head, tail)
	assert ''.join(numberalign.split(text, mode)) == text


@pytest.mark.parametrize('text, mode, head, tail', [
	# a character: the first one, the Nth, the last
	('9:41', 'char::', '9', ':41'),
	('12:05', 'char::', '12', ':05'),
	('1:02:03', 'char::@2', '1:02', ':03'),
	('1:02:03', 'char::@-1', '1:02', ':03'),
	('72.4°', 'char:°', '72.4', '°'),
	('12.5 %', 'char:%', '12.5 ', '%'),
	# the Nth character, from either end
	('72.4°', 'nth:1', '', '72.4°'),
	('72.4°', 'nth:3', '72', '.4°'),
	('72.4°', 'nth:-1', '72.4', '°'),
	('1,234.5', 'nth:-2', '1,234', '.5'),
	# the Nth special character; a leading sign does not count
	('72.4°', 'special:1', '72', '.4°'),
	('72.4°', 'special:2', '72.4', '°'),
	('-3.5°', 'special:1', '-3', '.5°'),
	('-3.5°', 'special:-1', '-3.5', '°'),
	('1,234.5', 'special:2', '1,234', '.5'),
	('19.4 mi', 'special:1', '19', '.4 mi'),
	# no such anchor: back to the end of the digits, or the whole text
	('44%', 'char:.', '44', '%'),
	('44', 'special:1', '44', ''),
	('44', 'nth:9', '44', ''),
	('WSW', 'special:1', 'WSW', ''),
	('', 'special:1', '', ''),
])
def test_split_anchor(text, mode, head, tail):
	assert numberalign.split(text, mode) == (head, tail)
	assert ''.join(numberalign.split(text, mode)) == text


@pytest.mark.parametrize('spec, canonical', [
	('decimal', 'decimal'), ('END', 'end'), (' end ', 'end'),
	('char:.', 'char:.'), ('char:.@1', 'char:.'), ('char:.@-1', 'char:.@-1'), ('char: ', 'char: '),
	('nth:3', 'nth:3'), ('NTH:-1', 'nth:-1'), ('special:2', 'special:2'),
	({'char': ':'}, 'char::'), ({'char': ':', 'occurrence': 2}, 'char::@2'),
	({'nth': 4}, 'nth:4'), ({'special': -1}, 'special:-1'),
])
def test_parse(spec, canonical):
	assert numberalign.parse(spec) == canonical


@pytest.mark.parametrize('spec', ['', 'middle', 'char:', 'char:ab', 'nth:0', 'nth:x', 'special:0', 'char:.@0', {}, {'char': 'ab'}, {'nth': 1, 'char': '.'}, 5])
def test_parse_refuses(spec):
	with pytest.raises(ValueError):
		numberalign.parse(spec)


def test_anchored():
	assert numberalign.anchored('7', 'decimal')
	assert not numberalign.anchored('WSW', 'special:1')
	assert numberalign.anchored('Mon.', 'char:.')
	assert numberalign.anchored('44', 'char:.'), 'digits fall back to the end of the digits'
