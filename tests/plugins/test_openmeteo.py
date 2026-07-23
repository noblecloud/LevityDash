"""Tests for OpenMeteo's schema (lib/plugins/builtin/OpenMeteo.py).

Unlike OpenWeatherMap, OpenMeteo has no `normalizeData` override (the base
class's is an identity passthrough, `lib/plugins/web/__init__.py:385`) - raw
API data goes straight into a real `Schema` + `LevityDatagram` construction
(the same call `REST.getData` makes, `lib/plugins/web/rest.py:54-59`), so
that's what's tested directly here rather than a plain-dict-in/plain-dict-out
function. No network, no full `Plugin` bootstrap: a minimal `FakePlugin`
stands in for the one real `Plugin` needs to provide - a name (for
`Schema.__schemas__` registration) and hashability (`Schema.__hash`) - and,
importantly, a working `__contains__` (`Plugin.__contains__`,
`lib/plugins/plugin.py:518-520`, converts to `CategoryItem` and checks
observation membership). Properties.__init__ stores `{'plugin': plugin}`
directly in itself (`lib/plugins/schema/__init__.py:499`), and `sourceKeys`
later does `'sourceKey' in value` against every stored value including that
one - so a `FakePlugin` without `__contains__` raises `TypeError: argument of
type 'FakePlugin' is not a container`. That's not a schema-engine bug (real
`Plugin` already satisfies this), just a test-double fidelity requirement,
verified against the real `Plugin.__contains__` before writing these tests.
"""
import copy

import pytest

from LevityDash.lib.plugins.builtin.OpenMeteo import basicParams, schema as raw_schema, WMOCodes
from LevityDash.lib.plugins.schema import LevityDatagram, Schema


class FakePlugin:
	name = 'OpenMeteo'

	def __hash__(self):
		return hash(self.name)

	def __contains__(self, item):
		return False


def make_schema():
	# Schema.__init__ mutates its `source` dict via .pop() (keyMaps, dataMaps,
	# calculations, aliases, ignored) - always pass a deep copy, never the
	# live module-level `schema` dict, or every test after the first one runs
	# against an already-stripped schema.
	return Schema(plugin=FakePlugin(), source=copy.deepcopy(raw_schema))


# Values for every basicParams field - a realistic single-hour Open-Meteo
# forecast response shape: {"hourly": {"time": [...], "<param>": [...], ...}}.
HOURLY_VALUES = {
	'temperature_2m': 72.0, 'relativehumidity_2m': 55, 'dewpoint_2m': 55.0,
	'apparent_temperature': 74.0, 'pressure_msl': 1015.0, 'surface_pressure': 1013.0,
	'cloudcover': 20, 'windspeed_10m': 5.5, 'winddirection_10m': 180, 'windgusts_10m': 9.0,
	'shortwave_radiation': 300.0, 'direct_radiation': 200.0, 'diffuse_radiation': 100.0,
	'precipitation': 0.0, 'rain': 0.0, 'showers': 0.0, 'snowfall': 0.0, 'weathercode': 3,
	'snow_depth': 0.0, 'soil_moisture_0_1cm': 0.2,
}


def sample_response(hourly: dict = None, daily: dict = None) -> dict:
	return {
		'hourly': {'time': ['2026-07-22T00:00'], **{k: [v] for k, v in (hourly if hourly is not None else HOURLY_VALUES).items()}},
		'daily': {'time': ['2026-07-22'], **{k: [v] for k, v in (daily or {'shortwave_radiation_sum': 15.2}).items()}},
	}


def build(response: dict) -> LevityDatagram:
	schema = make_schema()
	return LevityDatagram(response, schema=schema, dataMap=schema.dataMaps.get('forecast', {}))


def test_every_basic_param_resolves_to_a_schema_key():
	# Confirms basicParams (the plugin's own "typical request" field list) is
	# fully covered by the schema - every field produces a resolved
	# CategoryItem-keyed value, nothing silently dropped.
	dg = build(sample_response())
	item = dg['hourly'][0]
	resolvedKeys = {str(k) for k in item.keys()}
	expected = {
		'environment.temperature.temperature', 'environment.humidity.humidity', 'environment.temperature.dewpoint',
		'environment.temperature.feelsLike', 'environment.pressure.pressure', 'environment.pressure.surface',
		'environment.clouds.cover.cover', 'environment.wind.speed.speed', 'environment.wind.direction.direction',
		'environment.wind.speed.gust', 'environment.light.irradiance.irradiance', 'environment.light.irradiance.direct',
		'environment.light.irradiance.diffuse', 'environment.precipitation.precipitation',
		'environment.condition.weatherCode', 'environment.soil.moisture.moisture',
	}
	assert expected <= resolvedKeys, f'missing: {expected - resolvedKeys}'


def test_hourly_and_daily_are_lists_of_per_timestamp_items():
	dg = build(sample_response())
	assert isinstance(dg['hourly'], list) and len(dg['hourly']) == 1
	assert isinstance(dg['daily'], list) and len(dg['daily']) == 1


def test_timestamp_metadata_is_attached_per_item():
	dg = build(sample_response())
	item = dg['hourly'][0]
	assert item.metaData.get('@timestamp') == '2026-07-22T00:00'


def test_derived_condition_and_icon_come_from_weathercode():
	# environment.condition.icon/.condition have no sourceKey of their own -
	# they're derived from environment.condition.weatherCode via `dataKey`
	# (see the schema's `'dataKey': 'environment.condition.weatherCode'`).
	dg = build(sample_response(hourly={**HOURLY_VALUES, 'weathercode': 61}))
	item = dg['hourly'][0]
	from LevityDash.lib.plugins.categories import CategoryItem
	assert item[CategoryItem('environment.condition.weatherCode')] == 61
	assert item[CategoryItem('environment.condition.condition')] == 61
	assert item[CategoryItem('environment.condition.icon')] == 61


def test_missing_optional_hourly_fields_does_not_crash():
	# A real Open-Meteo request can ask for a subset of basicParams - fields
	# not requested simply aren't in the response at all.
	sparse = build(sample_response(hourly={'temperature_2m': 68.0}))
	item = sparse['hourly'][0]
	from LevityDash.lib.plugins.categories import CategoryItem
	assert item[CategoryItem('environment.temperature.temperature')] == 68.0


def test_sparse_daily_does_not_crash():
	dg = build(sample_response(daily={}))
	assert dg['daily'] == [] or isinstance(dg['daily'], list)


def test_unmapped_hourly_field_passes_through_unresolved():
	# Documents real, current behavior discovered while writing this test -
	# NOT something to fix here (this task is tests-only; report, don't
	# patch the schema engine). Unlike OpenWeatherMap's custom normalizeData
	# (which explicitly drops fields with no schema entry - see that file's
	# test_normalize_drops_unmapped_weather_fields), OpenMeteo goes through
	# the generic Schema/LevityDatagram path with no such filtering: a field
	# with no schema entry survives as a plain string key, not a CategoryItem,
	# sitting in the same dict as properly-resolved values. If Open-Meteo's
	# API ever adds a field ahead of this plugin's schema being updated for
	# it, this is what would happen - worth a follow-up if the schema engine
	# is ever revisited, not urgent today since basicParams/allParams already
	# cover Open-Meteo's real documented fields.
	dg = build(sample_response(hourly={**HOURLY_VALUES, 'some_future_field_not_in_schema': 999}))
	item = dg['hourly'][0]
	assert 'some_future_field_not_in_schema' in item
	assert item['some_future_field_not_in_schema'] == 999


def test_condition_icon_aliases_cover_all_wmo_codes():
	schema = make_schema()
	# .aliases, not schema['aliases'] - Schema.__init__ pops 'aliases' out of
	# the source dict into this plain attribute (lib/plugins/schema/__init__.py
	# ~L664); dict-style access falls through CategoryDict.__getitem__'s
	# wildcard-matching branch instead, which is currently broken (a missing
	# `TimeAwareValue` import in categories.py raises NameError) - a real,
	# separate latent bug, flagged rather than fixed here.
	iconAliases = schema.aliases['@conditionIcon']
	conditionAliases = schema.aliases['@condition']
	assert set(WMOCodes.keys()) == set(iconAliases.keys())
	assert set(WMOCodes.keys()) == set(conditionAliases.keys())
	for code, expected in WMOCodes.items():
		assert iconAliases[code] == expected['icon']
		assert conditionAliases[code] == expected['description']
