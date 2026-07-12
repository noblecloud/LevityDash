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
	decode_category_item, decode_datetime, decode_measurement, decode_value,
	encode_category_item, encode_datetime, encode_measurement, encode_value, WIRE_VERSION,
)
from datetime import datetime, timezone


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
