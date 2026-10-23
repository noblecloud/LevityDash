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
