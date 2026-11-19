"""The real sky: catalogue, sidereal time and the projection (Qt-free)."""
import math
from datetime import datetime, timezone

import ephem
import numpy as np
import pytest

from LevityDash.lib import skymap

WHEN = datetime(2026, 12, 21, 2, 0, tzinfo=timezone.utc)


def test_catalogue_is_the_stars_to_magnitude_8_brightest_first():
	import numpy as np
	ra, dec, mag, bv = skymap.catalog()
	assert 40000 < len(mag) < 43000 and mag.max() <= 8.0
	assert np.all(np.diff(mag) >= 0)
	assert mag[0] == pytest.approx(-1.44, abs=0.03)  # Sirius
	assert math.degrees(ra[0]) == pytest.approx(101.29, abs=0.02) and math.degrees(dec[0]) == pytest.approx(-16.72, abs=0.02)
	assert bv[0] == pytest.approx(0.0, abs=0.05)


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
	x, y, mag, _ = skymap.project(40.7, -74.0, WHEN, 4.0)
	assert 200 < len(mag) < 700
	assert (mag <= 4.0).all() and (np.hypot(x, y) <= 1.05).all()
	assert len(skymap.project(40.7, -74.0, WHEN, 5.5)[2]) > len(mag)


def test_the_sky_turns_through_the_night():
	a = {round(m, 2): (x, y) for x, y, m, _ in zip(*skymap.project(40.7, -74.0, WHEN, 1.5))}
	later = skymap.project(40.7, -74.0, datetime(2026, 12, 21, 8, 0, tzinfo=timezone.utc), 1.5)
	b = {round(m, 2): (x, y) for x, y, m, _ in zip(*later)}
	assert a != b


def test_colour_follows_temperature_and_stays_nearly_white():
	hot, cool = skymap.color(12000), skymap.color(3500)
	assert hot[2] > hot[0] and cool[0] > cool[2]
	assert min(hot + cool) > 150
	assert skymap.color(0) == skymap.color(6000)
	assert skymap.kelvin(-0.3) > skymap.kelvin(0.65) > skymap.kelvin(1.8)  # blue, sun-like, red
	assert skymap.kelvin(0.65) == pytest.approx(5800, rel=0.05)


def test_moon_light_is_zero_when_it_is_down_and_bounded():
	values = [skymap.moonlight(40.7, -74.0, datetime(2026, 12, 21, h, tzinfo=timezone.utc)) for h in range(0, 24, 3)]
	assert all(0 <= v <= 1 for v in values) and 0.0 in values


def test_galactic_coordinates():
	import numpy as np
	l, b = skymap.galactic(np.radians(266.405), np.radians(-28.936))  # the galactic centre
	assert (math.degrees(float(l)) + 180) % 360 - 180 == pytest.approx(0, abs=0.2) and math.degrees(float(b)) == pytest.approx(0, abs=0.2)
	_, b = skymap.galactic(np.radians(192.859), np.radians(27.128))  # the north galactic pole
	assert math.degrees(float(b)) == pytest.approx(90, abs=0.01)


def test_the_chart_inverts():
	import numpy as np
	lst, lat = 1.3, math.radians(40.7)
	ra, dec = np.array([0.4, 2.0, 5.1]), np.array([0.3, 0.9, -0.1])
	alt, az = skymap.horizontal(ra, dec, lst, lat)
	x, y = skymap.chart(alt, az)
	back, backDec, backAlt = skymap.unchart(x, y, lat, lst)
	assert np.allclose(np.cos(back), np.cos(ra)) and np.allclose(np.sin(back), np.sin(ra)) and np.allclose(backDec, dec) and np.allclose(backAlt, alt)


def test_airmass():
	assert skymap.airmass(math.pi / 2) == pytest.approx(1.0, abs=0.01)
	assert skymap.airmass(math.radians(30)) == pytest.approx(2.0, abs=0.02)
	assert 30 < skymap.airmass(0.0) < 45


def test_galactic_chart_puts_the_galactic_centre_low_in_the_south_on_a_summer_night():
	import numpy as np
	# 23:30 EDT in mid July from New York: Sagittarius is about 20 degrees up, due south (straight down on the chart)
	when = datetime(2026, 7, 15, 3, 30, tzinfo=timezone.utc)
	ys = np.linspace(0.0, 1.0, 201)
	l, b, alt = skymap.galacticChart(40.7, -74.0, when, np.zeros_like(ys), ys)
	nearest = np.argmin(np.hypot((l + 180) % 360 - 180, b))
	assert math.degrees(alt[nearest]) == pytest.approx(20, abs=6)
