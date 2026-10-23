"""Scrolling maths: how far content can move, and where the bar's thumb sits."""
import pytest

from LevityDash.lib.layout import overflow
from LevityDash.lib.layout.types import Rect


def rows(n, height=40.0, gap=0.0):
	return [Rect(0, i * (height + gap), 100, height) for i in range(n)]


def test_modes_and_their_meaning():
	assert overflow.parse(None) == 'visible' and overflow.parse(' Auto ') == 'auto'
	with pytest.raises(ValueError, match='visible, hidden, clip, scroll, auto'):
		overflow.parse('overlay')
	assert [overflow.clips(m) for m in overflow.MODES] == [False, True, True, True, True]
	assert [overflow.scrolls(m) for m in overflow.MODES] == [False, False, False, True, True]


def test_the_limit_is_what_is_past_the_end_of_the_box():
	r = rows(5)
	assert overflow.content_end(r, True) == 200
	assert overflow.max_offset(200, 120) == 80
	assert overflow.max_offset(100, 120) == 0
	assert overflow.content_end([], True) == 0


def test_offset_is_kept_inside_the_content_and_shifts_the_rects():
	assert overflow.clamp(-5, 80) == 0 and overflow.clamp(500, 80) == 80
	moved = overflow.shift(rows(2), 30, True)
	assert [r.y for r in moved] == [-30, 10]
	assert [r.x for r in overflow.shift([Rect(50, 0, 10, 10)], 20, False)] == [30]
	assert overflow.shift(rows(1), 0, True) == rows(1)


def test_thumb_is_the_visible_share_and_reaches_the_end():
	assert overflow.thumb(0, 0, 120) is None
	start, length = overflow.thumb(0, 120, 120)
	assert start == 0 and length == pytest.approx(60)
	end, length = overflow.thumb(120, 120, 120)
	assert end + length == pytest.approx(120)
	assert overflow.thumb(0, 100000, 100)[1] == 12  # never thinner than a finger can find


def test_a_wheel_notch_moves_a_fifth_of_the_box():
	assert overflow.step(-120, 200) == 40  # wheel towards you scrolls down
	assert overflow.step(120, 200) == -40
