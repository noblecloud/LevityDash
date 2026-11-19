"""The real sky: catalogue, sidereal time and the projection (Qt-free)."""
import math
from datetime import datetime, timezone

import ephem
import pytest

from LevityDash.lib import skymap

WHEN = datetime(2026, 12, 21, 2, 0, tzinfo=timezone.utc)


def test_catalogue_is_the_bright_stars_brightest_first():
	stars = skymap.catalog()
	assert 3500 < len(stars) < 5000
	assert [s[2] for s in stars] == sorted(s[2] for s in stars)
	assert stars[0][2] == pytest.approx(-1.46)  # Sirius


@pytest.mark.parametrize('name', ['Sirius', 'Vega', 'Betelgeuse', 'Polaris', 'Capella'])
@pytest.mark.parametrize('lat,lon', [(40.7, -74.0), (-33.9, 151.2)])
def test_positions_agree_with_ephem(name, lat, lon):
	star = ephem.star(name)
	observer = ephem.Observer()
	observer.lat, observer.lon, observer.pressure = str(lat), str(lon), 0
	observer.date = WHEN.replace(tzinfo=None)
	star.compute(observer)
	ra, dec = math.radians(float(star._ra) * 180 / math.pi), float(star._dec)
	# ephem's coordinates are for the epoch of date; J2000 ones come from a_ra/a_dec
	ra, dec = skymap._precess(float(star.a_ra), float(star.a_dec), (skymap.julianDay(WHEN) - skymap.J2000_JD) / 365.25)
	alt, az = skymap.horizontal(ra, dec, skymap.localSiderealTime(WHEN, lon), math.radians(lat))
	assert math.degrees(alt) == pytest.approx(math.degrees(float(star.alt)), abs=0.5)
	if math.degrees(float(star.alt)) > 2:
		diff = abs((math.degrees(az) - math.degrees(float(star.az)) + 180) % 360 - 180)
		assert diff < 0.5


def test_the_chart_puts_the_zenith_in_the_middle_and_the_horizon_on_the_unit_circle():
	assert skymap.chart(math.pi / 2, 0) == pytest.approx((0, 0), abs=1e-9)
	x, y = skymap.chart(0, math.pi / 2)  # due east at the horizon: left
	assert (x, y) == pytest.approx((-1, 0), abs=1e-9)
	x, y = skymap.chart(0, 0)  # north: up
	assert (x, y) == pytest.approx((0, -1), abs=1e-9)


def test_only_stars_above_the_horizon_and_brighter_than_the_limit():
	shown = skymap.project(40.7, -74.0, WHEN, 4.0)
	assert 200 < len(shown) < 700
	assert all(mag <= 4.0 and math.hypot(x, y) <= 1.05 for x, y, mag, _ in shown)
	assert len(skymap.project(40.7, -74.0, WHEN, 5.5)) > len(shown)


def test_the_sky_turns_through_the_night():
	a = {round(m, 2): (x, y) for x, y, m, _ in skymap.project(40.7, -74.0, WHEN, 1.5)}
	later = skymap.project(40.7, -74.0, datetime(2026, 12, 21, 8, 0, tzinfo=timezone.utc), 1.5)
	b = {round(m, 2): (x, y) for x, y, m, _ in later}
	assert a != b


def test_colour_follows_temperature_and_stays_nearly_white():
	hot, cool = skymap.color(12000), skymap.color(3500)
	assert hot[2] > hot[0] and cool[0] > cool[2]
	assert min(hot + cool) > 150
	assert skymap.color(0) == skymap.color(6000)


def test_moon_light_is_zero_when_it_is_down_and_bounded():
	values = [skymap.moonlight(40.7, -74.0, datetime(2026, 12, 21, h, tzinfo=timezone.utc)) for h in range(0, 24, 3)]
	assert all(0 <= v <= 1 for v in values) and 0.0 in values
