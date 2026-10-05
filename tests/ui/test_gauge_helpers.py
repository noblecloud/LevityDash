"""Pure helpers behind the gauge clock, wrap scale and duration text."""
import pytest

from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Gauge import (
	clockTurn, formatDuration, parseClockTime, shortestDelta,
)


@pytest.mark.parametrize('current, target, expected', [
	(350, 10, 20),
	(10, 350, -20),
	(0, 180, 180),
	(90, 100, 10),
	(370, 10, 0),
])
def test_shortest_delta_crosses_the_join(current, target, expected):
	assert shortestDelta(current, target, 360) == pytest.approx(expected)


def test_clock_hands_turn_once_round_the_dial():
	assert clockTurn('hour', 12, 0, 0) == 0
	assert clockTurn('hour', 3, 0, 0) == pytest.approx(0.25)
	assert clockTurn('minute', 7, 30, 0) == pytest.approx(0.5)
	assert clockTurn('second', 0, 0, 15) == pytest.approx(0.25)
	assert clockTurn('day', 18, 0, 0) == pytest.approx(0.75)
	with pytest.raises(ValueError):
		clockTurn('week', 0, 0, 0)


def test_parse_clock_time():
	assert parseClockTime('10:08') == (10, 8, 0.0)
	assert parseClockTime('10:08:36') == (10, 8, 36.0)
	with pytest.raises(ValueError):
		parseClockTime('25:00')


def test_format_duration():
	assert formatDuration(289) == '4h 49m'
	assert formatDuration(45) == '45m'
	assert formatDuration(None) == '⋯'
