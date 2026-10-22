"""Tests for the computed-key engine's bookkeeping (lib/plugins/computed.py).

Only the parts that are hard to see from a running dashboard: refcounting,
and that a malformed expression never raises into dashboard load. The
evaluation path and the wire round trip are checked by running the real
backend and frontend (see the value-sources brief).
"""
import logging

import pytest
from PySide6.QtCore import QObject, Signal

from LevityDash.lib.plugins import computed
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.computed import ComputedEngine, acquireValueSource, releaseValueSource

TEXT = 'max(environment.temperature.temperature, today)'


class StubDispatcher(QObject):
	"""The slice of PluginValueDirectory the engine touches. No containers,
	so every computation finds its inputs missing."""

	new_keys_signal = Signal(object)

	def __init__(self):
		super().__init__()
		self.connected = []
		self.remote = None

	def connect_plugin(self, plugin):
		self.connected.append(plugin)
		return True

	def getContainer(self, key, default=None):
		return default


@pytest.fixture
def engine(monkeypatch):
	engine = ComputedEngine(StubDispatcher())
	monkeypatch.setattr(computed, '_engine', engine)
	monkeypatch.setattr(computed, '_remote', lambda: None)
	return engine


def test_register_and_release_are_refcounted(engine):
	first = acquireValueSource(TEXT)
	# Different spacing, same expression: one computed key, one computation.
	second = acquireValueSource('max( environment.temperature.temperature ,today )')
	assert first == second
	assert first[0] == 'computed'
	assert engine.refcount(first) == 2

	releaseValueSource(TEXT)
	assert first in engine
	releaseValueSource(TEXT)
	assert first not in engine
	# A release with nothing left to release is harmless.
	releaseValueSource(TEXT)
	assert engine.refcount(first) == 0


def test_plain_key_registers_nothing(engine):
	key = acquireValueSource('environment.temperature.temperature')
	assert key == CategoryItem('environment.temperature.temperature')
	assert key not in engine
	assert not engine._entries


@pytest.mark.parametrize('text', ['max(environment.temperature.temperature,', 'open(a.b)', 'value * 2', None, ''])
def test_malformed_expression_returns_none_without_raising(engine, caplog, text):
	with caplog.at_level(logging.ERROR):
		assert acquireValueSource(text) is None
		releaseValueSource(text)
	assert not engine._entries
	assert any(repr(text) in record.getMessage() for record in caplog.records)


# -- places ----------------------------------------------------------------------

class _Reading:
	def __init__(self, value, taken):
		self.value = value
		self.timestamp = taken


class _Container:
	"""What `getContainer(key).value.value` reads: one reading."""

	def __init__(self, value, taken):
		self.value = type('Latest', (), {'value': _Reading(value, taken)})()

	def __bool__(self):
		return True


class _PlacedDispatcher(StubDispatcher):
	def __init__(self, readings):
		super().__init__()
		self.readings = readings

	def getContainer(self, key, default=None):
		return self.readings.get(str(key), default)


def _wait(engine, entry, timeout=5.0):
	import time
	from PySide6.QtCore import QCoreApplication
	end = time.monotonic() + timeout
	while time.monotonic() < end:
		QCoreApplication.processEvents()
		if entry.state == 'idle':
			return
		time.sleep(0.01)
	raise AssertionError('the computation did not finish')


class _Placed:
	def __init__(self, **places):
		self.places = places


def test_an_aggregate_over_a_place_publishes_its_value_and_a_member_count(monkeypatch):
	from datetime import datetime, timedelta
	from LevityDash import LevityDashboard
	from WeatherUnits.temperature import Fahrenheit
	from LevityDash.lib.plugins.expressions import Expression

	fresh, old = datetime.now().astimezone(), datetime.now().astimezone() - timedelta(hours=2)
	readings = {
		'indoor.temperature.temperature#bedroom': _Container(Fahrenheit(20), fresh),
		'indoor.temperature.temperature#office': _Container(Fahrenheit(24), fresh),
		'indoor.temperature.temperature#attic': _Container(Fahrenheit(99), old),
	}
	plugins = [_Placed(bedroom='home.upstairs.bedroom', office='home.upstairs.office', attic='home.upstairs.attic', garage='home.garage')]
	monkeypatch.setattr(type(LevityDashboard.plugins), '__iter__', lambda self: iter(plugins))

	engine = ComputedEngine(_PlacedDispatcher(readings))
	expression = Expression.parse('avg(indoor.temperature.temperature, where=home.upstairs)')
	engine.register(expression)
	entry = engine._entries[expression.key]
	_wait(engine, entry)

	# The old attic reading is left out: 2 of the 3 devices there.
	assert engine.source[expression.key].value.rawValue == Fahrenheit(22)
	countKey = CategoryItem([*expression.key, computed.COUNT_ATOM])
	assert engine.source[countKey].value.rawValue == 2
	# The three upstairs devices are watched, and the garage is not.
	assert {str(k) for k in engine._memberKeys(entry)} == set(list(readings))
	assert all(expression.key in engine._dependents[CategoryItem(k)] for k in readings)

	engine.release(expression.key)
	assert not engine._dependents


class _SourceReading:
	def __init__(self, value):
		self.value = value


class _Multi(dict):
	"""Containers by source name; `.value` is the preferred source's container, as in MultiSourceContainer."""

	def __init__(self, preferred, **containers):
		super().__init__(containers)
		self._preferred = preferred

	@property
	def value(self):
		return self[self._preferred]


class _SourceDispatcher(StubDispatcher):
	def __init__(self, containers):
		super().__init__()
		self.containers = containers

	def getContainer(self, key, default=None):
		return self.containers.get(str(key.path) if hasattr(key, 'path') else '.'.join(key), default)


def test_a_key_with_a_source_reads_that_source_not_the_preferred_one():
	from WeatherUnits.temperature import Fahrenheit

	class _Box:
		def __init__(self, degrees):
			self.value = _SourceReading(Fahrenheit(degrees))

	multi = _Multi('OpenMeteo', OpenMeteo=_Box(70), PirateWeather=_Box(75))
	engine = ComputedEngine(_SourceDispatcher({'environment.temperature.high': multi}))
	from LevityDash.lib.plugins.expressions import Expression
	expression = Expression.parse('max(OpenMeteo:environment.temperature.high, PirateWeather:environment.temperature.high)')
	engine.register(expression)
	_wait(engine, engine._entries[expression.key])
	assert engine.source[expression.key].value.rawValue == Fahrenheit(75)

	spread = Expression.parse('PirateWeather:environment.temperature.high - OpenMeteo:environment.temperature.high')
	engine.register(spread)
	_wait(engine, engine._entries[spread.key])
	assert engine.source[spread.key].value.rawValue == 5
