import pytest

from LevityDash.lib.plugins.builtin.Aircraft import (
	AIRCRAFT_KEYS, SLOTS_MAX, bearingDistance, feedUrl, parseAircraft, slotValues,
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
	assert feedUrl('adsb.lol', 40.0, -75.0, 49.2) == 'https://api.adsb.lol/v2/point/40.0000/-75.0000/50'
	assert feedUrl('airplanes.live', 40.0, -75.0, 900).endswith('/250')
	assert feedUrl('http://pi.local:8080/data/aircraft.json', 0, 0, 1) == 'http://pi.local:8080/data/aircraft.json'
	with pytest.raises(ValueError):
		feedUrl('file:///etc/passwd', 0, 0, 1)
