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
