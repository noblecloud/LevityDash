"""LEVITYDASH_SCHEMA_DEBUG — loud-failure dev mode for silent schema fallbacks.

The schema engine fuzzy-matches and falls back silently in production so a
schema typo degrades to a cosmetic oddity instead of a crash. These pin that
the opt-in debug flag surfaces those events loudly *and* — crucially — that it
changes nothing about what the fallbacks actually return.
"""
from types import SimpleNamespace

import pytest

import LevityDash.lib.plugins.schema as sm


@pytest.fixture
def alerts(monkeypatch):
	"""Capture the ERROR-level messages the schema-debug alert emits.

	The existing (default) fallback logs use ``log.warning``; only
	``_schema_debug_alert`` uses ``log.error``, so this captures exactly the
	loud-mode alerts and nothing else.
	"""
	captured = []
	monkeypatch.setattr(sm.log, "error", lambda msg, *a, **k: captured.append(str(msg)))
	return captured


# --- the gate every fallback site funnels through --------------------------

def test_alert_is_noop_when_flag_off(monkeypatch, alerts):
	monkeypatch.setattr(sm, "SCHEMA_DEBUG", False)
	sm._schema_debug_alert("a fuzzy match happened")
	assert alerts == []


def test_alert_is_loud_when_flag_on(monkeypatch, alerts):
	monkeypatch.setattr(sm, "SCHEMA_DEBUG", True)
	sm._schema_debug_alert("a fuzzy match happened")
	assert len(alerts) == 1
	assert alerts[0].startswith("SCHEMA-DEBUG:")
	assert "a fuzzy match happened" in alerts[0]


# --- findTimeKey: a real fallback site, wired to the alert -----------------

TS_SCHEMA = {'timestamp': {'sourceKey': 'ts'}}


def _find_time_key(data):
	# call the raw (pre-lru_cache) function against a lightweight stand-in self
	fake = SimpleNamespace(schema=TS_SCHEMA)
	return sm.LevityDatagram.findTimeKey.__wrapped__(fake, frozenset(data))


def test_findtimekey_fuzzy_match_is_loud_in_debug(monkeypatch, alerts):
	monkeypatch.setattr(sm, "SCHEMA_DEBUG", True)
	# 'ts' isn't present, but 'time' is close enough to 'timestamp' (ratio > 0.5)
	assert _find_time_key({'time', 'x'}) == 'time'  # behaviour unchanged
	assert any("fuzzy-matched 'time'" in a for a in alerts)


def test_findtimekey_default_fallback_is_loud_in_debug(monkeypatch, alerts):
	monkeypatch.setattr(sm, "SCHEMA_DEBUG", True)
	# nothing close to 'timestamp' -> silent default in production
	assert _find_time_key({'aaa', 'bbb'}) == 'timestamp'  # behaviour unchanged
	assert any("defaulting to 'timestamp'" in a for a in alerts)


def test_findtimekey_is_silent_and_unchanged_with_flag_off(monkeypatch, alerts):
	monkeypatch.setattr(sm, "SCHEMA_DEBUG", False)
	# identical returns, but no loud alerts
	assert _find_time_key({'time', 'x'}) == 'time'
	assert _find_time_key({'aaa', 'bbb'}) == 'timestamp'
	assert alerts == []
