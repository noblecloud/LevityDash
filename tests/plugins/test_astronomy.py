from datetime import datetime

from LevityDash.lib.plugins.builtin.Astronomy import sunValues

NEW_YORK = (40.71, -74.0)


def test_daylight_counts_down_and_is_zero_at_night():
	noon = datetime(2026, 10, 7, 12, 0).astimezone()
	night = datetime(2026, 10, 7, 3, 0).astimezone()
	hour, remaining = sunValues(*NEW_YORK, noon)
	assert hour == 12.0
	assert 0 <= remaining <= 1440
	assert sunValues(*NEW_YORK, night)[0] == 3.0


def test_polar_summer_is_all_day():
	hour, remaining = sunValues(78.0, 15.0, datetime(2026, 6, 21, 12, 0).astimezone())
	assert remaining == 1440


def test_polar_winter_is_none():
	hour, remaining = sunValues(78.0, 15.0, datetime(2026, 12, 21, 12, 0).astimezone())
	assert remaining == 0
