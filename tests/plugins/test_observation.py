"""Tests for two live bugs found in lib/plugins/observation.py while wiring
up the OpenWeatherMap plugin against a real API response.

Uses lightweight stand-ins for Schema/ObservationDict rather than a full
Plugin bootstrap - same rationale as tests/wire/test_containers.py: these
tests are precise about the exact surface the fixed code reads, rather than
fighting the real schema/plugin bootstrap machinery for something a stub
covers exactly as well.
"""
import pytest

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.errors import InvalidData
from LevityDash.lib.plugins.observation import ObservationDict, ObservationValue


class FakeSchema:
	"""Stands in for Schema.getUnitMetaData - returns None for any key,
	matching what a real Schema returns when a plugin emits a key with no
	matching schema entry (see Schema.getUnitMetaData, schema/__init__.py)."""

	def getUnitMetaData(self, key, source):
		return None


class FakeSource:
	schema = FakeSchema()
	__sourceKeyMap__ = {}


def test_observation_value_raises_invaliddata_for_unmapped_key():
	# Regression: source.schema.getUnitMetaData(key, source) can return None
	# when a plugin emits an extra/unmapped key. Previously this crashed with
	# `TypeError: 'NoneType' object is not subscriptable` on the very next
	# line - a real plugin's update() would die entirely on any one stray
	# key. It must now fail with a clear, catchable error instead.
	with pytest.raises(InvalidData, match="unmapped-key"):
		ObservationValue(value=42, key='unmapped-key', source=FakeSource(), container=None)


class FakeSchemaWithDewpoint:
	def __init__(self, declares_dewpoint):
		self._declares_dewpoint = declares_dewpoint

	def get(self, key, default=None):
		if key == 'environment.temperature.dewpoint':
			return self._declares_dewpoint
		return default


def _bindCalculateMissingFor(obs):
	"""calculateMissing delegates to `self._calculateMissingFor` per identity.

	These stand-ins are plain dicts called through an unbound
	ObservationDict.calculateMissing, so that attribute has to be bound onto
	them explicitly.
	"""
	obs._calculateMissingFor = ObservationDict._calculateMissingFor.__get__(obs)


class FakeObservation(dict):
	"""Minimal stand-in for the parts of ObservationDict that
	calculateMissing actually reads/writes - a plain dict plus a `.schema`
	and `._calculatedKeys`, exercised via an unbound call to the real
	ObservationDict.calculateMissing (same technique as
	test_openweathermap.py's unbound normalizeData call)."""

	def __init__(self, temperature, humidity, schema):
		super().__init__({
			'environment.temperature.temperature': temperature,
			'environment.humidity.humidity': humidity,
		})
		self.schema = schema
		self._calculatedKeys = set()
		_bindCalculateMissingFor(self)


class FakeTemperature:
	def __init__(self, sourceUnitValue, timestamp):
		self.timestamp = timestamp
		self.sourceUnitValue = sourceUnitValue


class FakeHumidity:
	def __init__(self, value):
		self.value = value


def test_calculate_missing_skips_dewpoint_when_schema_does_not_declare_it():
	# Regression: unlike the heatIndex branch right below it (which guards
	# with `self.schema.get('environment.temperature.heatIndex', None)`),
	# the dewpoint branch computed and stored a dewpoint unconditionally,
	# with no check that the plugin's schema actually declares
	# 'environment.temperature.dewpoint'. Storing it then blows up
	# downstream when ObservationValue looks up metadata for the
	# undeclared key (see test above). It must now be guarded the same way
	# heatIndex already is.
	class Temp:
		def dewpoint(self, humidity):
			raise AssertionError('dewpoint() should not be called when the schema does not declare it')

	temperature = FakeTemperature(Temp(), timestamp=None)
	humidity = FakeHumidity(50)
	schema = FakeSchemaWithDewpoint(declares_dewpoint=None)
	obs = FakeObservation(temperature, humidity, schema)

	ObservationDict.calculateMissing(obs, keys=set(obs.keys()))

	assert 'environment.temperature.dewpoint' not in obs
	assert 'environment.temperature.dewpoint' not in obs._calculatedKeys


def test_calculate_missing_computes_dewpoint_when_schema_declares_it():
	import WeatherUnits as wu

	temperature = FakeTemperature(wu.Temperature.Fahrenheit(75), timestamp=None)
	humidity = FakeHumidity(50)
	schema = FakeSchemaWithDewpoint(declares_dewpoint=True)
	obs = FakeObservation(temperature, humidity, schema)

	ObservationDict.calculateMissing(obs, keys=set(obs.keys()))

	assert 'environment.temperature.dewpoint' in obs
	assert 'environment.temperature.dewpoint' in obs._calculatedKeys


class FakeIndoorObservation(dict):
	"""Like FakeObservation but keyed by identity-scoped indoor keys.

	The indoor branch has no schema guard, so no schema stub is needed.
	"""

	def __init__(self, readings):
		super().__init__(readings)
		self.schema = FakeSchemaWithDewpoint(declares_dewpoint=None)
		self._calculatedKeys = set()
		_bindCalculateMissingFor(self)


def _indoor(base, identity):
	return CategoryItem(base).withIdentity(identity)


def test_calculate_missing_derives_per_identity():
	# Regression: identity participates in hashing, so the bare literal
	# 'indoor.temperature.temperature' matched none of the identity-scoped
	# keys and the whole indoor branch was skipped - both Govee thermometers
	# showed a permanent placeholder where the dewpoint should be.
	import WeatherUnits as wu

	obs = FakeIndoorObservation({
		_indoor('indoor.temperature.temperature', 'bedroom'): FakeTemperature(wu.Temperature.Fahrenheit(70), timestamp=None),
		_indoor('indoor.humidity.humidity', 'bedroom'): FakeHumidity(40),
		_indoor('indoor.temperature.temperature', 'terrarium'): FakeTemperature(wu.Temperature.Fahrenheit(85), timestamp=None),
		_indoor('indoor.humidity.humidity', 'terrarium'): FakeHumidity(75),
	})

	ObservationDict.calculateMissing(obs, keys=set(obs.keys()))

	bedroom = _indoor('indoor.temperature.dewpoint', 'bedroom')
	terrarium = _indoor('indoor.temperature.dewpoint', 'terrarium')
	assert bedroom in obs, 'bedroom dewpoint was not derived'
	assert terrarium in obs, 'terrarium dewpoint was not derived'

	# Each identity must be derived from its *own* pair, never merged: the
	# warmer, wetter terrarium has to come out with the higher dewpoint.
	assert float(obs[terrarium].value) > float(obs[bedroom].value)


def test_calculate_missing_does_not_cross_identities():
	"""A lone reading derives nothing - it must not borrow another device's."""
	import WeatherUnits as wu

	obs = FakeIndoorObservation({
		_indoor('indoor.temperature.temperature', 'bedroom'): FakeTemperature(wu.Temperature.Fahrenheit(70), timestamp=None),
		_indoor('indoor.humidity.humidity', 'terrarium'): FakeHumidity(75),
	})

	ObservationDict.calculateMissing(obs, keys=set(obs.keys()))

	assert _indoor('indoor.temperature.dewpoint', 'bedroom') not in obs
	assert _indoor('indoor.temperature.dewpoint', 'terrarium') not in obs


def test_calculate_missing_still_handles_unscoped_keys_alongside_identities():
	"""Outdoor keys carry no identity; they must survive the per-identity loop."""
	import WeatherUnits as wu

	obs = FakeIndoorObservation({
		'indoor.temperature.temperature': FakeTemperature(wu.Temperature.Fahrenheit(72), timestamp=None),
		'indoor.humidity.humidity': FakeHumidity(50),
		_indoor('indoor.temperature.temperature', 'bedroom'): FakeTemperature(wu.Temperature.Fahrenheit(70), timestamp=None),
		_indoor('indoor.humidity.humidity', 'bedroom'): FakeHumidity(40),
	})

	ObservationDict.calculateMissing(obs, keys=set(obs.keys()))

	assert 'indoor.temperature.dewpoint' in obs
	assert _indoor('indoor.temperature.dewpoint', 'bedroom') in obs
