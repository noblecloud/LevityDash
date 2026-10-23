import pytest

from LevityDash.lib.ticks import formatTick, niceTicks


@pytest.mark.parametrize('low, high, count, expected', [
	(0, 100, 3, [0, 50, 100]),
	(0, 100, 5, [0, 25, 50, 75, 100]),
	(63, 99, 4, [70, 80, 90]),
	(-12, 31, 4, [0, 20]),
	(0, 0.4, 3, [0, 0.2, 0.4]),
])
def test_ticks_are_round_and_inside_the_span(low, high, count, expected):
	assert niceTicks(low, high, count) == pytest.approx(expected)


@pytest.mark.parametrize('low, high', [(5, 5), (9, 3), (0, float('inf')), (float('nan'), 1)])
def test_a_span_with_no_room_has_no_ticks(low, high):
	assert niceTicks(low, high) == []


def test_a_zero_count_has_no_ticks():
	assert niceTicks(0, 10, 0) == []


@pytest.mark.parametrize('value, spec, step, text', [
	(70.0, None, 10, '70'),
	(0.25, None, 0.25, '0.25'),
	(0.2, None, 0.2, '0.2'),
	(70, '{:.0f}°', 10, '70°'),
	(2.5, '.2f', 2.5, '2.50'),
])
def test_tick_text(value, spec, step, text):
	assert formatTick(value, spec, step) == text
