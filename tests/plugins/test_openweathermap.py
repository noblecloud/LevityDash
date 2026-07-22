"""Tests for OpenWeatherMap's normalizeData (lib/plugins/builtin/OpenWeatherMap.py).

Pure-function test against a captured, sanitized shape of a real Current
Weather Data (data/2.5/weather) response - the free-tier endpoint this
plugin targets, not the paid One Call API. No network, no API key, no
Plugin bootstrap: normalizeData is a plain method that only reads its
argument, so it's tested directly rather than through the full plugin
lifecycle (which needs a loaded config).
"""
from LevityDash.lib.plugins.builtin.OpenWeatherMap import OpenWeatherMap, schema

# Captured shape from a real api.openweathermap.org/data/2.5/weather response
# (values changed, structure preserved) - see the module docstring.
SAMPLE_RESPONSE = {
	'coord': {'lon': -76.2802, 'lat': 36.8531},
	'weather': [{'id': 804, 'main': 'Clouds', 'description': 'overcast clouds', 'icon': '04d'}],
	'base': 'stations',
	'main': {
		'temp': 24, 'feels_like': 24.83, 'temp_min': 23.33, 'temp_max': 25,
		'pressure': 1017, 'humidity': 91, 'sea_level': 1017, 'grnd_level': 1016,
	},
	'visibility': 10000,
	'wind': {'speed': 1.34, 'deg': 271, 'gust': 1.79},
	'clouds': {'all': 100},
	'dt': 1783858891,
	'sys': {'type': 2, 'id': 2107214, 'country': 'US', 'sunrise': 1783850130, 'sunset': 1783902335},
	'timezone': -14400,
	'id': 4776222,
	'name': 'Norfolk',
	'cod': 200,
}


def normalize(rawData):
	# normalizeData doesn't touch `self` - call it unbound rather than
	# constructing a real Plugin (which needs a loaded config file).
	return OpenWeatherMap.normalizeData(None, rawData)


def test_normalize_flattens_nested_subobjects():
	result = normalize(SAMPLE_RESPONSE)
	assert result['temp'] == 24
	assert result['feels_like'] == 24.83
	assert result['humidity'] == 91
	assert result['pressure'] == 1017
	assert result['wind_speed'] == 1.34
	assert result['wind_deg'] == 271
	assert result['wind_gust'] == 1.79
	assert result['clouds'] == 100
	assert result['weather_description'] == 'overcast clouds'
	assert result['weather_icon'] == '04d'
	assert result['sunrise'] == 1783850130
	assert result['sunset'] == 1783902335
	assert result['dt'] == 1783858891


def test_normalize_drops_unmapped_weather_fields():
	# weather[0]['id']/['main'] have no schema entry - including them would
	# crash ObservationValue.__init__ downstream (see the comment in
	# normalizeData). This is the actual regression this test guards.
	result = normalize(SAMPLE_RESPONSE)
	assert 'weather_id' not in result
	assert 'weather_main' not in result


def test_normalize_every_key_has_a_schema_source_key():
	# Every key normalizeData emits must be resolvable by the schema, or it
	# reaches ObservationValue.__init__ with no metadata and crashes - see
	# the schema-pipeline review. dt/timestamp are exempt (handled by the
	# top-level 'timestamp' schema entry keyed on tsk.metaData, not a plain
	# sourceKey lookup).
	sourceKeys = {v['sourceKey'] for v in schema.values() if isinstance(v, dict) and 'sourceKey' in v}
	result = normalize(SAMPLE_RESPONSE)
	unmapped = set(result.keys()) - sourceKeys - {'dt'}
	assert not unmapped, f'normalizeData emits keys with no schema sourceKey: {unmapped}'


def test_normalize_handles_missing_optional_subobjects():
	# wind/clouds are absent in some conditions (e.g. calm, clear) per
	# OpenWeatherMap's docs - normalizeData must not crash, just omit them.
	sparse = {'main': {'temp': 20}, 'weather': [{'description': 'clear sky', 'icon': '01d'}], 'dt': 123}
	result = normalize(sparse)
	assert result['temp'] == 20
	assert result['wind_speed'] is None
	assert result['clouds'] is None


def test_normalize_handles_missing_weather_list():
	# Defensive: an empty/missing 'weather' array shouldn't IndexError.
	result = normalize({'main': {'temp': 20}, 'dt': 123})
	assert result['weather_description'] is None
	assert result['weather_icon'] is None


def test_condition_icon_aliases_cover_all_owm_icon_codes():
	# OpenWeatherMap has exactly these icon codes (openweathermap.org/weather-conditions).
	owmCodes = {f'{n:02d}{suffix}' for n in (1, 2, 3, 4, 9, 10, 11, 13, 50) for suffix in ('d', 'n')}
	aliasTable = schema['aliases']['@conditionIcons']
	assert owmCodes == set(aliasTable.keys())
