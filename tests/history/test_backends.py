"""The history backends (lib/history): settings, the SQLite file, line protocol, and the servers when one is running.

A server test runs only when `LEVITYDASH_TEST_INFLUXDB` or `LEVITYDASH_TEST_QUESTDB` names `host:port`, since CI has no
database. Both run the same checks, so a new backend only has to be added to `SERVERS`.
"""
import os
import sqlite3
import time

import pytest

from LevityDash.lib import history as H
from LevityDash.lib.history import Sample, SQLiteBackend, settingsFrom
from LevityDash.lib.history import influxdb, questdb


def test_defaults_are_influxdb_with_sqlite_as_the_fallback():
	s = settingsFrom({}, env={})
	assert (s.enabled, s.backend, s.fallback, s.servicePort) == (True, 'influxdb', 'sqlite', 8181)
	assert (s.retention, s.restore, s.raw) == (30, 2, True)


def test_settings_are_read_and_a_bad_value_keeps_the_default():
	s = settingsFrom({'backend': 'questdb', 'retention': 'lots', 'restore': '5', 'raw': 'off', 'raw-every': '3'}, env={})
	assert (s.backend, s.servicePort, s.retention, s.restore, s.raw, s.rawEvery) == ('questdb', 9000, 30, 5, False, 3)
	assert settingsFrom({'backend': 'oracle'}, env={}).backend == 'influxdb'


def test_quoted_values_are_the_same_as_bare_ones():
	s = settingsFrom({'backend': '"questdb"', 'host': "'nas.local'"}, env={})
	assert (s.backend, s.host) == ('questdb', 'nas.local')


def test_the_environment_outranks_the_file():
	assert settingsFrom({'enabled': 'true'}, env={'LEVITYDASH_HISTORY': 'off'}).enabled is False
	s = settingsFrom({'backend': 'influxdb'}, env={'LEVITYDASH_HISTORY_DB': '/tmp/x.sqlite3'})
	assert (s.backend, s.path) == ('sqlite', '/tmp/x.sqlite3')
	assert settingsFrom({}, env={'LEVITYDASH_HISTORY_BACKEND': 'questdb'}).backend == 'questdb'


def test_off_opens_nothing():
	assert H.openBackend(settingsFrom({'enabled': 'no'}, env={})) is None


def test_an_unreachable_server_falls_back_to_sqlite(tmp_path):
	s = settingsFrom({'backend': 'influxdb', 'port': '1', 'path': str(tmp_path / 'f.sqlite3')}, env={})
	backend = H.openBackend(s)
	assert backend.name == 'sqlite'


def test_the_fallback_can_be_turned_off(tmp_path):
	assert H.openBackend(settingsFrom({'backend': 'influxdb', 'port': '1', 'fallback': 'none'}, env={})) is None


def test_line_protocol_escapes_what_it_must():
	sample = Sample('Govee bed,room', 'raw:a=b', 'x.y', 1700000000.25, 'say "hi"\nnow\\', fetched=1700000001.0, number=None)
	for line in (influxdb.lineOf(sample), questdb.lineOf(sample)):
		assert '\n' not in line
		assert 'plugin=Govee\\ bed\\,room' in line
		assert 'stream=raw:a\\=b' in line
		assert r'value="\"say \\\"hi\\\"\\nnow\\\\\""' in line
		assert 'number=' not in line
		assert line.endswith('1700000000250000000')


def test_a_non_number_has_no_number():
	assert Sample('p', 's', 'k', 1.0, 'cold').number is None
	assert Sample('p', 's', 'k', 1.0, True).number is None
	assert Sample('p', 's', 'k', 1.0, {'__type__': 'measurement', 'value': 3.5, 'unit': 'C'}).number == 3.5
	assert Sample('p', 's', 'k', 1.0, float('nan')).number is None


@pytest.fixture
def sqlite(tmp_path):
	backend = SQLiteBackend(tmp_path / 'h.sqlite3')
	yield backend
	backend.close()


def _suite(backend, plugin='T'):
	"""What every backend must do."""
	now = time.time()
	backend.write([
		Sample(plugin, 'log', 'a.b', now - 120, 1.5),
		Sample(plugin, 'log', 'a.b', now - 60, {'__type__': 'measurement', 'value': 4.0, 'unit': 'C'}),
		Sample(plugin, 'log', 'note', now - 60, 'a "quoted"\nline, with = signs'),
		Sample(plugin, 'hourly', 'a.b', now + 3600, 9.0),
	])
	backend.write([Sample(plugin, 'log', 'a.b', now - 120, 2.5)])  # same plugin, stream, key and time: replaces
	backend.flush()
	rows = backend.read(plugin, 'log', now - 3600)
	assert [(r.key, r.value if r.key == 'note' else r.number) for r in rows] == [('a.b', 2.5), ('a.b', 4.0), ('note', 'a "quoted"\nline, with = signs')]
	assert [r.key for r in backend.read(plugin, 'log', now - 3600, key='note')] == ['note']
	assert [r.ts for r in backend.read(plugin, 'log', now - 3600, now - 90)] == [pytest.approx(now - 120, abs=1e-3)]
	assert backend.read(plugin, 'hourly', now - 3600)[0].number == 9.0
	assert backend.read('Nobody', 'log', now - 3600) == []
	extent = backend.extent(plugin, 'log', 'a.b', now - 3600)
	assert (extent.count, extent.minimum, extent.maximum, extent.mean) == (2, 2.5, 4.0, pytest.approx(3.25))
	assert backend.extent(plugin, 'log', 'note', now - 3600).minimum is None
	assert backend.extent('Nobody', 'log', 'a.b', now - 3600).count == 0
	assert backend.latest(plugin, 'log').key in ('a.b', 'note')
	assert backend.latest(plugin, 'log', 'a.b').number == 4.0
	assert backend.latest('Nobody', 'log') is None


def test_sqlite_does_what_every_backend_does(sqlite):
	_suite(sqlite)


def test_sqlite_prunes_by_stream_and_age(sqlite):
	now = time.time()
	sqlite.write([Sample('P', 'log', 'k', now - 86400 * 5, 1.0), Sample('P', 'raw:x', 'x', now - 86400 * 5, 2.0), Sample('P', 'log', 'k', now - 60, 3.0)])
	sqlite.prune('raw:x', now - 86400)
	assert len(sqlite.read('P', 'raw:x', now - 86400 * 9)) == 0 and len(sqlite.read('P', 'log', now - 86400 * 9)) == 2
	sqlite.prune(None, now - 86400)
	assert [r.number for r in sqlite.read('P', 'log', now - 86400 * 9)] == [3.0]


def test_sqlite_moves_the_first_versions_log_table_over(tmp_path):
	path = tmp_path / 'old.sqlite3'
	db = sqlite3.connect(path)
	db.execute('create table log (plugin text not null, ts real not null, key text not null, value text not null, primary key (plugin, ts, key)) without rowid')
	now = time.time()
	db.execute('insert into log values (?, ?, ?, ?)', ('Old', now - 30, 'a.b.c', '1.5'))
	db.commit()
	db.close()
	backend = SQLiteBackend(path)
	assert [(r.key, r.value, r.stream) for r in backend.read('Old', 'log', now - 3600)] == [('a.b.c', 1.5, 'log')]
	backend.close()
	assert not sqlite3.connect(path).execute("select 1 from sqlite_master where name = 'log'").fetchone()


SERVERS = {
	'influxdb': ('LEVITYDASH_TEST_INFLUXDB', lambda host, port: H.InfluxDBBackend(host, port, 'levity')),
	'questdb': ('LEVITYDASH_TEST_QUESTDB', lambda host, port: H.QuestDBBackend(host, port)),
}


@pytest.mark.parametrize('name', sorted(SERVERS))
def test_a_server_does_what_every_backend_does(name):
	variable, make = SERVERS[name]
	where = os.environ.get(variable)
	if not where:
		pytest.skip(f'{variable}=host:port names a running {name}')
	host, _, port = where.partition(':')
	backend = make(host, int(port))
	assert backend.connect()
	try:
		_suite(backend, plugin=f'T{int(time.time() * 1000)}')
	finally:
		backend.close()


@pytest.mark.parametrize('make', [lambda: H.InfluxDBBackend(port=1, timeout=0.5), lambda: H.QuestDBBackend(port=1, timeout=0.5)])
def test_a_server_that_is_down_never_raises_and_keeps_the_rows(make):
	backend = make()
	assert backend.connect() is False
	now = time.time()
	backend.write([Sample('P', 'log', 'k', now, 1.0)])
	assert backend.read('P', 'log', now - 60) == []
	assert backend.extent('P', 'log', 'k', now - 60).count == 0
	assert backend.latest('P', 'log') is None
	assert len(backend._queue) + backend._inflight >= 1
	backend._stop = True
