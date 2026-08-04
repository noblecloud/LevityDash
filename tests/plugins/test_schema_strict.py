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


# --- getUnitMetaData: fuzzy-match SUGGESTS instead of SUBSTITUTES in debug ---

def _make_schema(self_keys=(), source_keys=None, exact_for=()):
	"""Lightweight Schema stand-in for Schema.getUnitMetaData.

	The fuzzy branch is reached when ``key`` is present in ``self`` (so it
	passes the ``key not in self`` gate) but ``getExact`` returns None — which
	happens when the key has no real UnitMetaData entry in ``self._source``. We
	model that by holding the requested (typo) key in ``self`` and the correct
	near-key in ``self._source`` (where ``getExact`` resolves it).
	"""
	class FakeSchema(dict):
		def __init__(self):
			super().__init__({k: object() for k in self_keys})
			self.sourceKeyMap = {}
			self._source = {k: object() for k in (source_keys if source_keys is not None else self_keys)}
			self.getExact = lambda k: object() if k in exact_for else None
			# expose the real method (bound to this instance) so the production
			# fuzzy-recursion path works the same way it does on a real Schema
			self.getUnitMetaData = sm.Schema.getUnitMetaData.__wrapped__.__get__(self)
	return FakeSchema()


def _get_unit_metadata(fake, key, src):
	# bypass lru_cache (which can't hash the lightweight fake) to exercise the
	# real body directly
	return sm.Schema.getUnitMetaData.__wrapped__(fake, key, src)


def test_getunitmetadata_fuzzy_does_not_substitute_in_debug(monkeypatch, alerts):
	"""In SCHEMA_DEBUG a mistyped key must NOT silently bind to the near key.

	This is the core behaviour change: production returns the fuzzy match so a
	typo degrades gracefully; debug returns None and screams, so the developer
	sees the mismatch instead of a wrong unit.
	"""
	monkeypatch.setattr(sm, "SCHEMA_DEBUG", True)
	monkeypatch.setattr(sm, "_SCHEMA_DEBUG_UNMAPPED", {})
	src = SimpleNamespace(name="TestPlugin")
	# 'tempurature' is a typo of 'temperature'; both live in the schema so the
	# key resolves into self but getExact(None) -> None, triggering fuzzy
	fake = _make_schema(self_keys=['tempurature', 'temperature'], source_keys=['temperature'], exact_for=['temperature'])
	result = _get_unit_metadata(fake, 'tempurature', src)
	assert result is None
	assert any("nearest is" in a for a in alerts)
	# and it was recorded for the summary
	assert sm._SCHEMA_DEBUG_UNMAPPED[("TestPlugin", "tempurature")] == "fuzzy"


def test_getunitmetadata_fuzzy_still_substitutes_when_flag_off(monkeypatch, alerts):
	"""Production behaviour is byte-identical: typo binds to the nearest key."""
	monkeypatch.setattr(sm, "SCHEMA_DEBUG", False)
	src = SimpleNamespace(name="TestPlugin")
	fake = _make_schema(self_keys=['tempurature', 'temperature'], source_keys=['temperature'], exact_for=['temperature'])
	# fuzzy resolves to 'temperature' and getUnitMetaData recurses into it
	result = _get_unit_metadata(fake, 'tempurature', src)
	assert result is not None
	assert alerts == []


def test_getunitmetadata_missing_recorded_for_summary(monkeypatch, alerts):
	monkeypatch.setattr(sm, "SCHEMA_DEBUG", True)
	monkeypatch.setattr(sm, "_SCHEMA_DEBUG_UNMAPPED", {})
	src = SimpleNamespace(name="Govee")
	fake = _make_schema(self_keys=[], source_keys=[])
	assert _get_unit_metadata(fake, 'nonexistent.key', src) is None
	assert sm._SCHEMA_DEBUG_UNMAPPED[("Govee", "nonexistent.key")] == "missing"


def test_summarize_unmapped_emits_one_line(monkeypatch, alerts):
	monkeypatch.setattr(sm, "SCHEMA_DEBUG", True)
	monkeypatch.setattr(sm, "_SCHEMA_DEBUG_UNMAPPED", {("P", "a"): "missing", ("P", "b"): "fuzzy"})
	sm.summarize_unmapped()
	assert any("unmapped-key summary (2)" in a for a in alerts)
	# idempotent: a second call is quiet
	before = len(alerts)
	sm.summarize_unmapped()
	assert len(alerts) == before


def test_summarize_unmapped_is_silent_with_flag_off(monkeypatch, alerts):
	monkeypatch.setattr(sm, "SCHEMA_DEBUG", False)
	monkeypatch.setattr(sm, "_SCHEMA_DEBUG_UNMAPPED", {("P", "a"): "missing"})
	sm.summarize_unmapped()
	assert alerts == []
