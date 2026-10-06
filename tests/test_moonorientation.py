from datetime import datetime, timezone

import numpy as np
import pytest

from LevityDash.lib.moonorientation import _sunMoon, brightLimbFromZenith

PLACES = [(40.7, -74.0), (-33.9, 151.2), (51.5, 0.0), (64.1, -21.9), (-1.3, 36.8)]
TIMES = [datetime(2026, 10, d, h, tzinfo=timezone.utc) for d, h in ((2, 18), (6, 2), (19, 0), (26, 5))]


def _unit(az, alt):
	return np.array([np.sin(az)*np.cos(alt), np.cos(az)*np.cos(alt), np.sin(alt)])


def _fromHorizon(lat, lon, when):
	"""Same angle from alt/az vectors alone: the Sun's direction in the Moon's tangent plane against zenith."""
	_, moon, sun = _sunMoon(lat, lon, when)
	m, s = _unit(float(moon.az), float(moon.alt)), _unit(float(sun.az), float(sun.alt))
	up = np.array([0, 0, 1.0])
	up = up - up.dot(m)*m
	up /= np.linalg.norm(up)
	left = np.cross(up, m)
	toSun = s - s.dot(m)*m
	return float(np.degrees(np.arctan2(toSun.dot(left), toSun.dot(up))))%360


@pytest.mark.parametrize('lat,lon', PLACES)
@pytest.mark.parametrize('when', TIMES)
def test_matches_horizon_geometry(lat, lon, when):
	diff = (brightLimbFromZenith(lat, lon, when) - _fromHorizon(lat, lon, when) + 180)%360 - 180
	assert abs(diff) < 0.01


def test_waxing_crescent_in_the_evening_is_lit_on_the_right():
	# 2026-10-19 00:00 UTC, New York: waxing crescent, Moon in the south-west, Sun below the western horizon
	angle = brightLimbFromZenith(40.7, -74.0, datetime(2026, 10, 19, 0, tzinfo=timezone.utc))
	assert 225 < angle < 270
