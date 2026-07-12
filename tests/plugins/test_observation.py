"""Tests for two live bugs found in lib/plugins/observation.py while wiring
up the OpenWeatherMap plugin against a real API response.

Uses lightweight stand-ins for Schema/ObservationDict rather than a full
Plugin bootstrap - same rationale as tests/wire/test_containers.py: these
tests are precise about the exact surface the fixed code reads, rather than
fighting the real schema/plugin bootstrap machinery for something a stub
covers exactly as well.
"""
import pytest

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
