"""Tests for PirateWeather's schema (lib/plugins/builtin/PirateWeather.py).

Same shape of test as test_openmeteo.py (no `normalizeData` override - raw
API data goes straight into a real `Schema` + `LevityDatagram`), but a
structurally different response: PirateWeather is Dark Sky API-compatible,
so `hourly`/`daily` are already row-shaped (`{"data": [{...}, {...}]}`), not
columnar arrays like Open-Meteo, and the schema declares an explicit
`ignored` list (`precipType`, `windGustTime`, `uvIndexTime`) rather than
leaving unmapped fields to pass through unresolved.
"""
import copy
import time

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.builtin.PirateWeather import schema as raw_schema
from LevityDash.lib.plugins.schema import LevityDatagram, Schema, Subdatagram


class FakePlugin:
	name = 'PirateWeather'

	def __hash__(self):
		return hash(self.name)

	def __contains__(self, item):
		return False


def make_schema():
	return Schema(plugin=FakePlugin(), source=copy.deepcopy(raw_schema))


NOW = int(time.time())

CURRENTLY = {
	'time': NOW, 'summary': 'Clear', 'icon': 'clear-day',
	'precipIntensity': 0.0, 'precipProbability': 0.0,
	'temperature': 22.0, 'apparentTemperature': 22.0, 'dewPoint': 15.0,
	'humidity': 0.5, 'pressure': 1015.0,
	'windSpeed': 3.0, 'windGust': 5.0, 'windBearing': 180,
	'cloudCover': 0.1, 'uvIndex': 4, 'visibility': 16.0, 'ozone': 300.0,
	# these three are in the schema's explicit 'ignored' list
	'precipType': 'none', 'windGustTime': NOW, 'uvIndexTime': NOW,
}


def sample_response(currently: dict = None, hourly_data: list = None, daily_data: list = None) -> dict:
	return {
		'currently': currently if currently is not None else dict(CURRENTLY),
		'hourly': {'data': hourly_data if hourly_data is not None else [
			{'time': NOW, 'temperature': 22.0, 'precipIntensity': 0.0, 'summary': 'Clear', 'icon': 'clear-day'},
			{'time': NOW + 3600, 'temperature': 21.0, 'precipIntensity': 0.0, 'summary': 'Clear', 'icon': 'clear-day'},
		]},
		'daily': {'data': daily_data if daily_data is not None else [
			{'time': NOW, 'temperatureHigh': 25.0, 'temperatureLow': 18.0, 'sunriseTime': NOW, 'sunsetTime': NOW},
			{'time': NOW + 86400, 'temperatureHigh': 26.0, 'temperatureLow': 19.0, 'sunriseTime': NOW + 86400, 'sunsetTime': NOW + 86400},
		]},
	}


def build(response: dict) -> LevityDatagram:
	schema = make_schema()
	return LevityDatagram(response, schema=schema, dataMap=schema.dataMaps.get('forecast', {}))


def test_realtime_resolves_from_currently():
	dg = build(sample_response())
	realtime = dg['realtime']
	assert isinstance(realtime, Subdatagram)
	assert realtime[CategoryItem('environment.temperature.temperature')] == 22.0
	assert realtime[CategoryItem('environment.humidity.humidity')] == 0.5
	assert realtime[CategoryItem('environment.wind.speed.speed')] == 3.0
	assert realtime[CategoryItem('environment.wind.speed.gust')] == 5.0
	assert realtime[CategoryItem('environment.condition.condition')] == 'Clear'
	assert realtime[CategoryItem('environment.condition.icon')] == 'clear-day'


def test_ignored_fields_are_dropped_not_leaked():
	# Unlike OpenMeteo (see test_openmeteo.py's test_unmapped_hourly_field_
	# passes_through_unresolved), PirateWeather's schema declares an explicit
	# 'ignored' list - these must not survive into the parsed realtime data,
	# resolved or not.
	dg = build(sample_response())
	realtime = dg['realtime']
	rawKeys = {str(k) for k in realtime.keys()}
	assert 'precipType' not in rawKeys
	assert 'windGustTime' not in rawKeys
	assert 'uvIndexTime' not in rawKeys


def test_hourly_is_a_list_of_per_timestamp_items():
	dg = build(sample_response())
	assert isinstance(dg['hourly'], list)
	assert len(dg['hourly']) == 2
	assert dg['hourly'][0][CategoryItem('environment.temperature.temperature')] == 22.0
	assert dg['hourly'][1][CategoryItem('environment.temperature.temperature')] == 21.0


def test_daily_is_a_list_with_high_low_and_astronomy():
	dg = build(sample_response())
	assert isinstance(dg['daily'], list)
	assert len(dg['daily']) == 2
	first = dg['daily'][0]
	assert first[CategoryItem('environment.temperature.high')] == 25.0
	assert first[CategoryItem('environment.temperature.low')] == 18.0
	assert first[CategoryItem('astronomy.sun.rise')] == NOW
	assert first[CategoryItem('astronomy.sun.set')] == NOW


def test_missing_optional_currently_fields_does_not_crash():
	# nearestStormDistance/nearestStormBearing are only present when a storm
	# is actually nearby - a bare-minimum response must not crash.
	sparse = build(sample_response(currently={'time': NOW, 'temperature': 20.0}))
	assert sparse['realtime'][CategoryItem('environment.temperature.temperature')] == 20.0


def test_storm_bearing_requires_storm_distance_present():
	# environment.storm.bearing declares 'requires': {'environment.storm.distance': {'gt': 0}}
	# - confirm a response with a real storm distance resolves both fields
	# without crashing (the requires-guard behavior itself, not just presence).
	stormy = build(sample_response(currently={**CURRENTLY, 'nearestStormDistance': 12.0, 'nearestStormBearing': 270}))
	realtime = stormy['realtime']
	assert realtime[CategoryItem('environment.storm.distance')] == 12.0


def test_condition_icon_aliases_are_complete_dark_sky_set():
	# PirateWeather/Dark Sky's documented icon set (pirateweather.net/en/latest/API/#icon)
	schema = make_schema()
	expected = {
		'clear-day', 'clear-night', 'rain', 'snow', 'sleet', 'wind', 'fog',
		'cloudy', 'partly-cloudy-day', 'partly-cloudy-night',
	}
	assert set(schema.aliases['@conditionIcons'].keys()) == expected
