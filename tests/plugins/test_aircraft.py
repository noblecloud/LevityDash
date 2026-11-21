import pytest

from LevityDash.lib.plugins.builtin.Aircraft import (
	AIRCRAFT_KEYS, SLOTS_MAX, Aircraft, bearingDistance, closingSpeed, feedUrl, lookoutRadius, nextInterval,
	parseAircraft, retryDelay, slotValues,
)

HOME = (40.0, -75.0)


def plane(lat, lon, **extra):
	return {'hex': 'abc123', 'flight': 'UAL123 ', 'lat': lat, 'lon': lon, 'alt_baro': 12000, 'gs': 250.4,
	        'track': 91.6, 'baro_rate': -640, 't': 'B738', **extra}


def test_bearing_and_distance_follow_the_compass():
	north, dn = bearingDistance(*HOME, 41.0, -75.0)
	east, de = bearingDistance(*HOME, 40.0, -74.0)
	assert north == pytest.approx(0, abs=0.01) and dn == pytest.approx(60, abs=0.5)
	assert east == pytest.approx(90, abs=0.5) and de == pytest.approx(46, abs=1)
	assert bearingDistance(*HOME, 39.0, -76.0)[0] == pytest.approx(218, abs=1)


def test_nearest_first_and_fields_are_cleaned():
	far, near = plane(41.0, -75.0, flight='FAR1'), plane(40.1, -75.0)
	rows = parseAircraft({'ac': [far, near]}, *HOME, radius=100)
	assert [r['callsign'] for r in rows] == ['UAL123', 'FAR1']
	assert rows[0]['altitude'] == 12000 and rows[0]['speed'] == 250 and rows[0]['heading'] == 92
	assert rows[0]['climb'] == -640 and rows[0]['type'] == 'B738'


def test_left_out_without_a_position_beyond_the_radius_or_on_the_ground():
	data = {'ac': [{'hex': 'x'}, plane(45.0, -75.0), plane(40.1, -75.0, alt_baro='ground', flight='GND')]}
	assert parseAircraft(data, *HOME, radius=50) == []
	rows = parseAircraft(data, *HOME, radius=50, ground=True)
	assert [r['callsign'] for r in rows] == ['GND'] and rows[0]['altitude'] == 0


def test_a_receivers_file_reads_like_a_public_feed():
	rows = parseAircraft({'aircraft': [{'hex': 'a1b2c3', 'lat': 40.2, 'lon': -75.0, 'altitude': 3000, 'track': 10}]}, *HOME, radius=50)
	assert rows[0]['callsign'] == 'a1b2c3' and rows[0]['altitude'] == 3000 and rows[0]['heading'] == 10


def test_slots_fill_nearest_first_and_blank_the_ones_that_emptied():
	rows = parseAircraft({'ac': [plane(40.1, -75.0), plane(40.2, -75.0, flight='B')]}, *HOME, radius=50)
	out = slotValues(rows, slots=3, previous=0)
	assert out['aircraft.count'] == 2 and out['aircraft.2.callsign'] == 'B'
	assert 'aircraft.3.callsign' not in out
	gone = slotValues(rows[:1], slots=3, previous=2)
	assert gone['aircraft.2.callsign'] == '' and gone['aircraft.2.distance'] == 0
	assert 'aircraft.3.callsign' not in gone
	assert slotValues(rows * 30, slots=99)['aircraft.count'] == 60 and f'aircraft.{SLOTS_MAX + 1}.callsign' not in slotValues(rows * 30, slots=99)


def test_every_published_key_is_declared():
	rows = parseAircraft({'ac': [plane(40.1, -75.0)] * SLOTS_MAX}, *HOME, radius=50)
	assert set(slotValues(rows, SLOTS_MAX)) <= set(AIRCRAFT_KEYS)


def test_feed_urls():
	assert feedUrl('adsb.fi', 40.0, -75.0, 49.2) == 'https://opendata.adsb.fi/api/v3/lat/40.0000/lon/-75.0000/dist/50'
	assert feedUrl('ADSB.FI', 40.0, -75.0, 900).endswith('/dist/250')
	assert feedUrl('adsb.lol', 40.0, -75.0, 49.2) == 'https://api.adsb.lol/v2/point/40.0000/-75.0000/50'
	assert feedUrl('airplanes.live', 40.0, -75.0, 900).endswith('/250')
	assert feedUrl('http://pi.local:8080/data/aircraft.json', 0, 0, 1) == 'http://pi.local:8080/data/aircraft.json'
	with pytest.raises(ValueError):
		feedUrl('file:///etc/passwd', 0, 0, 1)


def test_the_default_source_is_adsb_fi():
	defaults = Aircraft.__defaultConfig__
	assert isinstance(defaults, str) and 'source = adsb.fi' in defaults


def test_a_capped_feed_waits_for_its_own_reset():
	class Capped(Exception):
		headers = {'x-ratelimit-reset': '24631'}

	assert retryDelay(Capped(), 10) == 24631
	assert retryDelay(Capped(), 30000) == 30000          # never shorter than the interval
	assert retryDelay(Capped(), 90000) == 86400          # never longer than a day
	assert retryDelay(ValueError('no headers'), 10) == 10

	class Soon(Exception):
		headers = {'Retry-After': '2'}
	assert retryDelay(Soon(), 10) == 10


def _traffic(distance, bearing, heading, speed):
	return {'distance': distance, 'bearing': bearing, 'heading': heading, 'speed': speed}


def test_the_poll_rate_follows_what_is_closing_on_you():
	head_on = _traffic(8.0, 90, 270, 120)   # due east of you, flying west, straight at you
	crossing = _traffic(8.0, 90, 0, 120)    # northbound across your view
	away = _traffic(8.0, 90, 90, 120)       # eastbound, gone
	assert closingSpeed(head_on) == pytest.approx(120)
	assert closingSpeed(crossing) == pytest.approx(0, abs=1e-9)
	assert closingSpeed(away) == pytest.approx(-120)

	radius, idle, fast = 2.5, 120.0, 5.0
	# 5.5 nmi left at 120 kt is 165 s of flying; polled a quarter of the way there is 41 s.
	assert nextInterval([head_on], radius, idle, fast) == pytest.approx(5.5 / 120 * 3600 / 4)
	assert nextInterval([head_on], 2.5, 30.0, fast) == 30.0, 'never slower than the idle interval'
	assert nextInterval([crossing], radius, idle, fast) == idle
	assert nextInterval([away], radius, idle, fast) == idle
	assert nextInterval([], radius, idle, fast) == idle
	assert nextInterval([_traffic(1.0, 0, 0, 100)], radius, idle, fast) == fast  # already overhead: as often as allowed


def test_the_wait_stays_between_the_fast_and_idle_intervals():
	assert nextInterval([_traffic(3.0, 90, 270, 480)], 2.5, 30.0, 5.0) == 5.0    # a quarter of 3.75 s is under the floor
	assert nextInterval([_traffic(9.0, 90, 270, 60)], 2.5, 30.0, 5.0) == 30.0     # 390 s away: no faster than idle
	assert nextInterval([_traffic(2.0, 90, 270, 120)], 2.5, 30.0, 5.0) == 5.0     # inside the radius


def test_the_lookout_ring_grows_with_the_idle_interval():
	assert lookoutRadius(2.2, 30) == pytest.approx(2.2 + 500 * 30 / 3600)
	assert lookoutRadius(2.2, 60) > lookoutRadius(2.2, 30), 'a slower idle poll must watch further out'
	assert lookoutRadius(240, 3600) == 250, 'the public feeds cap the ring at 250 nmi'
	assert lookoutRadius(2.2, 0) == 2.2, 'a zero idle interval watches no further than the radius'


def test_overhead_counts_inside_the_radius_and_under_the_ceiling():
	from LevityDash.lib.plugins.builtin.Aircraft import overhead
	rows = [{'distance': 3, 'altitude': 2000}, {'distance': 8, 'altitude': 30000}, {'distance': 20, 'altitude': 1000}]
	assert overhead(rows, 10) == 2
	assert overhead(rows, 10, ceiling=10000) == 1
	assert overhead([], 10) == 0


def test_active_holds_after_the_last_plane_leaves_and_then_drops():
	from LevityDash.lib.plugins.builtin.Aircraft import holdActive
	assert holdActive(2, 100.0, None, 60) == (1, 100.0)
	assert holdActive(0, 130.0, 100.0, 60) == (1, 100.0)   # 30 s after: still on
	assert holdActive(0, 161.0, 100.0, 60) == (0, 100.0)   # 61 s after: off
	assert holdActive(0, 5.0, None, 60) == (0, None)       # never seen


def test_max_altitude_drops_high_aircraft_but_keeps_military():
	low = plane(40.1, -75.0, flight='LOW', alt_baro=3000)
	jet = plane(40.11, -75.0, flight='JET', alt_baro=36000)
	mil = plane(40.12, -75.0, flight='MIL', alt_baro=36000, dbFlags=1)
	rows = parseAircraft({'ac': [low, jet, mil]}, *HOME, radius=50, maxAltitude=10000)
	assert {r['callsign'] for r in rows} == {'LOW', 'MIL'}
	rows = parseAircraft({'ac': [low, jet, mil]}, *HOME, radius=50, maxAltitude=10000, military=False)
	assert {r['callsign'] for r in rows} == {'LOW'}
	assert len(parseAircraft({'ac': [low, jet, mil]}, *HOME, radius=50)) == 3
