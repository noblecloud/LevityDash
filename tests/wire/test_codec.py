"""Codec round-trip tests for the Phase 4 wire protocol (lib/wire/codec.py).

Every value type the codec claims to handle gets pushed through a genuine
json.dumps/json.loads round-trip, not just encode/decode called back to
back in memory - that's the actual thing 4.1 needs proven.
"""
import json

import WeatherUnits as wu

# Import something from LevityDash BEFORE `datetime` - LevityDash/__init__.py
# installs shims/_datetime_shim (sys.modules['datetime'] gets replaced with a
# datetime.datetime subclass that fixes %-d/%#d strftime portability), so
# `datetime` constructed before that install() runs is a *different, real*
# class than what every codec.py-internal `isinstance(value, datetime)` check
# compares against post-install. Importing LevityDash first, like every real
# in-package caller implicitly does, keeps this test file's `datetime` the
# same class the rest of the app uses.
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.wire.codec import (
	decode_category_item, decode_datetime, decode_measurement, decode_timeseries_values, decode_value,
	encode_category_item, encode_datetime, encode_measurement, encode_timeseries_values, encode_value, WIRE_VERSION,
)
from datetime import datetime, timezone
from types import SimpleNamespace


def roundtrip(value):
	payload = json.dumps(encode_value(value))
	return decode_value(json.loads(payload))


# --- CategoryItem ---

def test_category_item_str_roundtrip():
	item = CategoryItem('environment.temperature.temperature')
	assert decode_category_item(encode_category_item(item)) == item


def test_category_item_with_source_does_not_roundtrip_yet():
	# Documents a real, currently-open gap (see codec.py's module docstring):
	# CategoryItem.__str__ emits 'source:path', but the single-string
	# constructor's tokenizer doesn't treat ':' as a delimiter and silently
	# folds the source into the path atoms instead. Not a codec bug to fix
	# here - MultiSourceContainer/dispatcher keys are anonymous today, and
	# proper source-in-key round-tripping is Phase 3.5's job. This test
	# exists so a future CategoryItem fix flips it, rather than the gap
	# going unnoticed.
	item = CategoryItem('environment.temperature.temperature', source=['OpenMeteo'])
	result = roundtrip(item)
	assert isinstance(result, CategoryItem)
	assert result != item
	assert result.source != item.source


def test_category_item_wire_envelope_shape():
	item = CategoryItem('environment.humidity.humidity')
	encoded = encode_value(item)
	assert encoded == {'__type__': 'category_item', 'value': str(item)}


# --- Measurement ---

def test_measurement_roundtrip_preserves_value_and_class():
	original = wu.Temperature.Fahrenheit(72.5)
	result = roundtrip(original)
	assert isinstance(result, wu.Temperature.Fahrenheit)
	assert float(result) == 72.5


def test_measurement_roundtrip_preserves_unit():
	original = wu.Pressure.Hectopascal(1013.25)
	result = roundtrip(original)
	assert result.unit == original.unit


def test_decode_measurement_restores_ts_when_present():
	# Concrete WeatherUnits units (Fahrenheit.__new__(cls, value)) don't
	# accept a timestamp through their public constructor, so this exercises
	# encode_measurement's optional 'ts' field and decode_measurement's
	# restoration of it directly, at the payload level, rather than trying
	# to build a live Measurement with a timestamp.
	ts = datetime(2026, 3, 5, 14, 30, tzinfo=timezone.utc)
	payload = {'value': 68.0, 'unit': 'f', 'cls': 'Fahrenheit', 'ts': ts.isoformat()}
	result = decode_measurement(payload)
	assert result.timestamp == ts


def test_encode_measurement_omits_ts_when_absent():
	encoded = encode_measurement(wu.Temperature.Fahrenheit(68))
	assert 'ts' not in encoded


def test_measurement_unknown_unit_degrades_to_plain_float_not_exception():
	# A payload claiming a class/unit this WeatherUnits version doesn't
	# recognize (e.g. a frontend running behind a newer backend) must not
	# take down the whole message - see decode_measurement's docstring.
	payload = {'value': 42.0, 'unit': 'not-a-real-unit', 'cls': 'NotARealClass'}
	assert decode_measurement(payload) == 42.0


def test_measurement_wire_envelope_has_version_independent_shape():
	encoded = encode_measurement(wu.Temperature.Fahrenheit(72))
	assert set(encoded) >= {'value', 'unit', 'cls'}
	assert encoded['cls'] == 'Fahrenheit'


# --- datetime ---

def test_datetime_roundtrip_preserves_instant():
	original = datetime(2026, 7, 12, 9, 15, 30, tzinfo=timezone.utc)
	result = roundtrip(original)
	assert isinstance(result, datetime)
	assert result == original


def test_naive_datetime_roundtrip_is_timezone_aware_on_decode():
	# encode_datetime attaches the local tz to a naive datetime before
	# converting to UTC - decode always returns an aware datetime, so a
	# RemoteContainer never has to guess whether a pushed timestamp is
	# naive or not.
	naive = datetime(2026, 7, 12, 9, 15, 30)
	result = roundtrip(naive)
	assert result.tzinfo is not None


def test_datetime_wire_value_is_iso_string():
	encoded = encode_value(datetime(2026, 1, 1, tzinfo=timezone.utc))
	assert encoded['__type__'] == 'datetime'
	assert isinstance(encoded['value'], str)
	assert decode_datetime(encoded['value']) == datetime(2026, 1, 1, tzinfo=timezone.utc)


# --- passthrough / plain JSON-safe values ---

def test_plain_scalars_pass_through_unchanged():
	for value in ('clear-day', 42, 3.14, True, None):
		assert roundtrip(value) == value


def test_plain_dict_passes_through_unchanged():
	value = {'a': 1, 'b': 'two'}
	assert roundtrip(value) == value


def test_wire_version_is_a_positive_int():
	assert isinstance(WIRE_VERSION, int)
	assert WIRE_VERSION >= 1


def test_derived_unit_generic_cls_uses_symbol():
	# Derived/rate units register their GENERIC class under 'wind' etc., and
	# the generic constructor can't build from a bare number - the symbol
	# ('mph') resolves the specialized class that can. This was the
	# degrade-to-float path that made remote wind values unitless.
	payload = json.loads(json.dumps(encode_measurement(wu.Wind.MilesPerHour(5.5))))
	assert payload['cls'] == 'MilesPerHour'
	result = decode_measurement(payload)
	assert isinstance(result, wu.Wind.MilesPerHour)
	assert float(result) == 5.5

	# same unit arriving with the GENERIC class name (e.g. values whose
	# runtime type is the parametrized generic) must not degrade either
	generic_payload = {'value': 5.5, 'unit': 'mph', 'cls': 'Wind'}
	result = decode_measurement(generic_payload)
	assert isinstance(result, wu.Wind.MilesPerHour)
	assert float(result) == 5.5


def test_ambiguous_symbol_prefers_cls_name():
	# '%' is shared by several dimensions, so the class name must win
	humidity = encode_measurement(wu.Humidity(66))
	assert decode_measurement(json.loads(json.dumps(humidity))) == wu.Humidity(66)


# --- columnar timeseries values (encode_timeseries_values/decode_timeseries_values) ---

def _item(value, timestamp):
	# TimeSeriesItem duck-typing - encode_timeseries_values only reads
	# .value/.timestamp, so a bare namespace exercises that without pulling
	# in observation.py's real class.
	return SimpleNamespace(value=value, timestamp=timestamp)


def test_timeseries_values_roundtrip_preserves_class_and_values():
	items = [
		_item(wu.Temperature.Fahrenheit(70.0), datetime(2026, 7, 22, 12, tzinfo=timezone.utc)),
		_item(wu.Temperature.Fahrenheit(72.5), datetime(2026, 7, 22, 13, tzinfo=timezone.utc)),
	]
	payload = json.loads(json.dumps(encode_timeseries_values(items)))
	decoded = decode_timeseries_values(payload)
	assert [ts for ts, _ in decoded] == [i.timestamp for i in items]
	assert isinstance(decoded[0][1], wu.Temperature.Fahrenheit)
	assert float(decoded[0][1]) == 70.0
	assert float(decoded[1][1]) == 72.5


def test_timeseries_values_unit_and_cls_appear_once_not_per_point():
	# The entire reason for the columnar shape over repeating
	# encode_measurement per point - a compactness regression guard.
	items = [_item(wu.Temperature.Fahrenheit(v), datetime(2026, 1, 1, tzinfo=timezone.utc)) for v in (60.0, 61.0, 62.0)]
	payload = encode_timeseries_values(items)
	assert payload['cls'] == 'Fahrenheit'
	assert payload['unit'] == wu.Temperature.Fahrenheit(60.0).unit
	assert set(payload) == {'v', 'unit', 'cls', 'timestamps', 'values'}
	assert len(payload['timestamps']) == len(payload['values']) == 3


def test_empty_timeseries_encodes_to_none():
	assert encode_timeseries_values([]) is None
	assert decode_timeseries_values(None) == []


def test_timeseries_values_unresolvable_unit_degrades_point_to_float():
	payload = {'v': WIRE_VERSION, 'unit': 'not-a-real-unit', 'cls': 'NotARealClass', 'timestamps': [0.0], 'values': [42.0]}
	decoded = decode_timeseries_values(payload)
	assert len(decoded) == 1
	assert decoded[0][1] == 42.0


def test_timeseries_values_plain_float_items_have_no_unit_metadata():
	items = [_item(21.0, datetime(2026, 1, 1, tzinfo=timezone.utc))]
	payload = encode_timeseries_values(items)
	assert payload['unit'] is None
	assert payload['cls'] is None
	decoded = decode_timeseries_values(json.loads(json.dumps(payload)))
	assert decoded[0][1] == 21.0


def test_parametrized_derived_unit_survives_the_round_trip():
	"""A precipitation rate must come back as a Measurement, not a bare float.

	Derived units get a class generated per numerator/denominator pair
	('PrecipitationRate[in/hr]'). That generated name isn't in the registry
	and its composed 'in/hr' symbol isn't a registered symbol, so both
	lookups missed and the value degraded to a plain float - which has no
	precision/max/unit, so the frontend rendered raw float64 digits. Seen
	live in mode=remote: a precipitation rate displayed as
	'0.041649606299212590' sprawling across the dashboard.
	"""
	rate = wu.Precipitation.Hourly(wu.Length.Inch(0.0416496062992126))
	decoded = decode_measurement(json.loads(json.dumps(encode_measurement(rate))))

	assert not isinstance(decoded, float) or isinstance(decoded, wu.Measurement), \
		f'degraded to a bare float: {decoded!r}'
	# Asserts the reconstructed TYPE, not a rendered string - how it renders
	# depends on the app's [UnitProperties] config (precision/max/leadingZero),
	# which is a formatting concern covered by WeatherUnits' own suite.
	assert decoded.unit == 'in/hr'
	assert abs(float(decoded) - 0.0416496062992126) < 1e-9


def test_parametrized_derived_unit_metric_variant():
	rate = wu.Precipitation.Hourly(wu.Length.Millimeter(1.0577))
	decoded = decode_measurement(json.loads(json.dumps(encode_measurement(rate))))
	assert decoded.unit == 'mm/hr'
	assert abs(float(decoded) - 1.0577) < 1e-9


def test_unresolvable_parametrized_name_still_degrades_to_float():
	# The reconstruction only reaches units whose generic is registered;
	# everything else keeps the pre-existing degrade-to-float contract.
	payload = {'value': 42.0, 'unit': 'zz/yy', 'cls': 'NotARealThing[zz/yy]'}
	assert decode_measurement(payload) == 42.0
