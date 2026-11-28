"""The saved history: what a plugin's log writes to disk and gets back after a restart (lib/plugins/history.py)."""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from LevityDash.lib.plugins import history
from LevityDash.lib.plugins.categories import CategoryItem

KEY = CategoryItem('environment.temperature.temperature')


@pytest.fixture
def db(tmp_path, monkeypatch):
	path = tmp_path / 'history.sqlite3'
	monkeypatch.setenv('LEVITYDASH_HISTORY_DB', str(path))
	monkeypatch.delenv('LEVITYDASH_HISTORY', raising=False)
	history._forget()
	yield path
	history._forget()


def _plugin(monkeypatch):
	"""A logged plugin with fixed values, built the way the Fixture builds itself."""
	from LevityDash.lib.plugins.builtin import Fixture as F
	monkeypatch.setenv(F.ENV_VAR, 'house-day')

	class Logged(F.Fixture, realtime=True, hourly=True, logged=True):
		name = 'Logged'

	plugin = Logged()
	plugin.publish()
	return plugin


def test_the_store_round_trips_entries_oldest_first(db):
	store = history.historyStore()
	now = datetime.now(timezone.utc)
	store.write('A', now - timedelta(hours=1), {'a.b.c': 1.5})
	store.write('A', now - timedelta(hours=3), {'a.b.c': 0.5, 'a.b.d': 'x'})
	store.write('B', now - timedelta(hours=2), {'a.b.c': 9})
	entries = store.read('A')
	assert [values for _, values in entries] == [{'a.b.c': 0.5, 'a.b.d': 'x'}, {'a.b.c': 1.5}]
	assert entries[0][0] < entries[1][0]
	assert [values for _, values in store.read('B')] == [{'a.b.c': 9}]


def test_rows_older_than_the_retention_are_deleted_when_the_file_opens(db):
	store = history.historyStore()
	store.write('A', datetime.now(timezone.utc) - timedelta(days=40), {'k.k.k': 1})
	store.write('A', datetime.now(timezone.utc) - timedelta(hours=1), {'k.k.k': 2})
	history._forget()
	assert [v for _, v in history.historyStore().read('A', since=datetime.now(timezone.utc) - timedelta(days=9))] == [{'k.k.k': 2}]


def test_a_plugin_is_written_once_a_minute(db):
	store = history.historyStore()
	assert store.due('A')
	store.write('A', datetime.now(timezone.utc), {'k.k.k': 1})
	assert not store.due('A')
	assert store.due('B')


def test_history_off_stores_nothing(db, monkeypatch):
	monkeypatch.setenv('LEVITYDASH_HISTORY', 'off')
	history._forget()
	assert history.historyStore() is None
	assert history.restoreLog(object()) == 0


def test_a_file_that_cannot_be_opened_never_raises(tmp_path, monkeypatch):
	blocker = tmp_path / 'file'
	blocker.write_text('not a directory')
	monkeypatch.setenv('LEVITYDASH_HISTORY_DB', str(blocker / 'h.sqlite3'))
	history._forget()
	store = history.historyStore()
	store.write('A', datetime.now(timezone.utc), {'k.k.k': 1})
	assert store.read('A') == []


def test_a_restart_gets_the_log_back_at_the_times_it_was_written(db, monkeypatch):
	plugin = _plugin(monkeypatch)
	earlier = datetime.now(timezone.utc) - timedelta(hours=2)
	assert history.recordLog(plugin, plugin.realtime.archived.items(), when=earlier) > 0

	history._forget()  # a restart: a new process opens the file again
	again = _plugin(monkeypatch)
	assert len(again.log.timeseries) == 0
	assert history.restoreLog(again) == 1

	((when, entry),) = again.log.timeseries.items()
	assert abs((when.value - earlier).total_seconds()) < 301  # the log rounds to its 5 minute period
	restored, original = entry[KEY], plugin.realtime.archived[KEY]
	assert float(restored.value) == pytest.approx(float(original.value))
	assert type(restored.value).__name__ == type(original.value).__name__
	assert abs((restored.timestamp - earlier).total_seconds()) <= 30  # a value's time is rounded to the minute


def test_restoring_with_nothing_stored_changes_nothing(db, monkeypatch):
	plugin = _plugin(monkeypatch)
	assert history.restoreLog(plugin) == 0


def test_a_plugin_that_logs_its_values_writes_them_to_the_file(db, monkeypatch):
	import asyncio
	plugin = _plugin(monkeypatch)
	asyncio.run(plugin.logValues())
	entries = history.historyStore().read(plugin.name)
	assert len(entries) == 1
	assert str(KEY) in entries[0][1]
	assert isinstance(entries[0][1][str(KEY)], (int, float))
	# Straight after, the one-a-minute limit holds the next write back.
	asyncio.run(plugin.logValues())
	assert len(history.historyStore().read(plugin.name)) == 1


def test_a_plugin_without_a_log_is_snapshotted_in_its_own_stream(db, monkeypatch):
	plugin = _plugin(monkeypatch)
	assert history.recordRealtime(plugin) > 0
	store = history.historyStore()
	assert [v for _, v in store.read(plugin.name, stream='realtime')]
	assert store.read(plugin.name) == []  # the log stream is untouched
	assert history.recordRealtime(plugin) == 0  # snapshots are spaced by [History] snapshot-every


def test_a_response_is_kept_once_per_interval_and_read_back(db):
	class P:
		name = 'Rest'

	body = {'hourly': {'temperature_2m': [1.5, 2.5]}, 'note': 'ünï "code"'}
	assert history.recordRaw(P, 'forecast', body)
	assert not history.recordRaw(P, 'forecast', {'newer': 1})  # inside raw-every
	assert history.recordRaw(P, 'other', {'x': 1})  # another endpoint has its own clock
	when, kept = history.latestRaw(P, 'forecast')
	assert kept == body
	assert abs((datetime.now(timezone.utc) - when).total_seconds()) < 5
	assert history.latestRaw(P, 'missing') is None
	assert history.latestRaw(P, 'forecast', within=timedelta(seconds=-1)) is None


def test_a_response_too_big_to_keep_is_left_out(db):
	class P:
		name = 'Big'

	assert not history.recordRaw(P, 'huge', {'blob': 'x' * (history.MAX_RAW_BYTES + 1)})
	assert history.latestRaw(P, 'huge') is None


def test_the_extent_of_a_key_comes_from_the_store(db):
	class P:
		name = 'E'

	now = datetime.now(timezone.utc)
	store = history.historyStore()
	store.write('E', now - timedelta(hours=3), {'a.b.c': 10.0})
	store.write('E', now - timedelta(hours=1), {'a.b.c': 30.0})
	extent = history.extentOf(P, 'a.b.c', now - timedelta(days=1))
	assert (extent.count, extent.minimum, extent.maximum) == (2, 10.0, 30.0)


def test_rest_uses_the_stored_response_only_until_it_has_had_a_good_one(db):
	from types import SimpleNamespace
	from LevityDash.lib.plugins.web.rest import REST

	messages = []
	plugin = SimpleNamespace(name='Weather', pluginLog=SimpleNamespace(warning=messages.append))
	plugin._REST__rawName = lambda endpoint: REST._REST__rawName(plugin, endpoint)
	endpoint = SimpleNamespace(name='forecast')
	assert REST._REST__storedData(plugin, endpoint) is None  # nothing stored yet
	REST._REST__rememberData(plugin, endpoint, {'hourly': [1, 2]})
	plugin._goodFetches.clear()  # a restart: this run has fetched nothing yet
	assert REST._REST__storedData(plugin, endpoint) == {'hourly': [1, 2]}
	assert messages and 'could not be fetched' in messages[0]
	REST._REST__rememberData(plugin, endpoint, {'hourly': [3]})
	assert REST._REST__storedData(plugin, endpoint) is None  # a good fetch this run: no stale fallback
