"""Tests for WeatherFlow's schema (lib/plugins/builtin/WeatherFlow/__init__.py).

Same no-normalizeData shape as OpenMeteo/PirateWeather, but the most
structurally distinct of the three: WeatherFlow's real-time observations
arrive as positional arrays (`{"type": "obs_st", "obs": [[<18 or 22 values>]]}`),
not named fields - `Schema.keyMaps` maps array position -> schema key, keyed
off message `"type"` (`Schema.getKeyMap`, `lib/plugins/schema/__init__.py:750`,
flattens every key *and value* in the raw payload and matches any that equal
a `keyMaps` name - so a sample must include `'type': 'obs_st'` for the
positional mapping to engage at all; omitting it silently produces an empty
datagram rather than an error, confirmed empirically while building this
fixture). It also exercises `device.@deviceSerial.*` - a dynamic per-device
key substituted from the payload's own `serial_number`/`hub_sn` field, not a
fixed schema path.
"""
import copy
import time

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.builtin.WeatherFlow import schema as raw_schema
from LevityDash.lib.plugins.schema import LevityDatagram, Schema, Subdatagram


class FakePlugin:
	name = 'WeatherFlow'

	def __hash__(self):
		return hash(self.name)

	def __contains__(self, item):
		return False


def make_schema():
	return Schema(plugin=FakePlugin(), source=copy.deepcopy(raw_schema))


NOW = int(time.time())
SERIAL = 'ST-00012345'

# The 18-element obs_st layout per keyMaps['obs_st']['obs'][18]:
# [timestamp, lull, avg, gust, direction, wind_sample_interval, pressure,
#  temperature, humidity, illuminance, uv, irradiance, precip, precip_type,
#  lightning_distance, lightning_count, battery, report_interval]
OBS_ST_18 = [NOW, 0.5, 2.1, 3.4, 180, 3, 1015.2, 22.0, 55, 5000, 4, 300.0, 0.0, 0, None, 0, 2.7, 1]


def obs_st_response(obs=None, serial=SERIAL) -> dict:
	return {'type': 'obs_st', 'obs': [obs if obs is not None else list(OBS_ST_18)], 'serial_number': serial}


def build(response: dict) -> LevityDatagram:
	schema = make_schema()
	return LevityDatagram(response, schema=schema, dataMap=schema.dataMaps.get('obs_st', {}))


def test_positional_obs_st_array_resolves_to_schema_keys():
	dg = build(obs_st_response())
	realtime = dg['realtime']
	assert isinstance(realtime, Subdatagram)
	assert realtime[CategoryItem('environment.temperature.temperature')] == 22.0
	assert realtime[CategoryItem('environment.humidity.humidity')] == 55
	assert realtime[CategoryItem('environment.pressure.pressure')] == 1015.2
	assert realtime[CategoryItem('environment.wind.speed.speed')] == 2.1
	assert realtime[CategoryItem('environment.wind.speed.lull')] == 0.5
	assert realtime[CategoryItem('environment.wind.speed.gust')] == 3.4
	assert realtime[CategoryItem('environment.wind.direction.direction')] == 180
	assert realtime[CategoryItem('environment.light.uvi')] == 4
	assert realtime[CategoryItem('environment.precipitation.precipitation')] == 0.0


def test_message_without_a_type_field_produces_nothing_not_an_error():
	# Documents real, current behavior discovered while writing this test:
	# getKeyMap can't identify which keyMap to apply without a 'type' field
	# matching a keyMaps name anywhere in the payload's keys/values - it
	# degrades to an empty datagram rather than raising. Not something to
	# fix here (tests-only task) - just pinned so a future engine change
	# doesn't silently start raising instead, or vice versa.
	no_type = {'obs': [list(OBS_ST_18)], 'serial_number': SERIAL}
	dg = build(no_type)
	assert dict(dg) == {}


def test_dynamic_device_serial_key_uses_the_payload_serial_number():
	# device.@deviceSerial.* isn't a fixed path - @deviceSerial is
	# substituted from the payload's own serial_number/hub_sn field.
	dg = build(obs_st_response(serial='ST-99999999'))
	realtime = dg['realtime']
	assert realtime[CategoryItem('device.ST-99999999.battery')] == 2.7
	assert realtime[CategoryItem('device.ST-99999999.sampleInterval.wind')] == 3
	assert realtime[CategoryItem('device.ST-99999999.sampleInterval.report')] == 1
	assert CategoryItem('device.ST-00012345.battery') not in realtime


def test_missing_optional_lightning_distance_does_not_crash():
	# index 14 (lightning distance) is None in OBS_ST_18 - a real Tempest
	# reports this only when lightning was actually detected recently.
	dg = build(obs_st_response())
	realtime = dg['realtime']
	assert CategoryItem('environment.lightning.distance') not in realtime
	assert realtime[CategoryItem('environment.lightning.lightning')] == 0


def test_ignored_fields_are_dropped():
	# 'air_density' etc. are in the schema's explicit ignored list even
	# though WeatherFlow's real payloads sometimes include them under other
	# message types - confirm the ignored set itself is what's declared.
	schema = make_schema()
	assert 'air_density' in schema._ignored
	assert 'wind_direction_cardinal' in schema._ignored
	assert 'raining_minutes' in schema._ignored


def test_condition_icon_aliases_include_all_forecast_conditions():
	schema = make_schema()
	aliases = schema.aliases['@conditionIcon']
	# WeatherFlow's forecast `icon` field uses these condition strings
	# (see the plugin's better_forecast endpoint docs).
	expected_subset = {
		'clear-day', 'clear-night', 'cloudy', 'foggy',
		'partly-cloudy-day', 'partly-cloudy-night',
		'possibly-rainy-day', 'possibly-rainy-night',
		'possibly-sleet-day', 'possibly-sleet-night',
		'possibly-snow-day', 'possibly-snow-night',
		'possibly-thunderstorm-day', 'possibly-thunderstorm-night',
		'rainy', 'sleet', 'snow', 'thunderstorm', 'windy',
	}
	assert expected_subset <= set(aliases.keys())
