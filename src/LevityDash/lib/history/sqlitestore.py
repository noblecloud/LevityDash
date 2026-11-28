"""The embedded backend: one SQLite file. The default fallback, and the only backend that needs nothing installed."""
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from .base import Extent, HistoryBackend, Sample, toTimestamp
import json

__all__ = ['SQLiteBackend']

log = logging.getLogger('LevityDash.history')

_SCHEMA = """
create table if not exists samples (
	plugin text not null,
	stream text not null,
	ts real not null,
	key text not null,
	value text not null,
	number real,
	fetched real not null,
	primary key (plugin, stream, ts, key)
) without rowid
"""


class SQLiteBackend(HistoryBackend):
	name = 'sqlite'

	def __init__(self, path: Path | str):
		self.path = Path(path)
		self._lock = threading.RLock()
		self._db: Optional[sqlite3.Connection] = None
		self._failed = False

	def _connection(self) -> Optional[sqlite3.Connection]:
		if self._db is not None or self._failed:
			return self._db
		try:
			self.path.parent.mkdir(parents=True, exist_ok=True)
			db = sqlite3.connect(self.path, check_same_thread=False, timeout=5)
			db.execute('pragma journal_mode=wal')
			db.execute(_SCHEMA)
			self._migrate(db)
			db.commit()
			self._db = db
		except Exception:
			self._failed = True
			log.exception(f'{self.path} could not be opened; the plugins run without saved history')
		return self._db

	@staticmethod
	def _migrate(db: sqlite3.Connection) -> None:
		"""The first version of the file held only the realtime log, in a table named `log`."""
		if db.execute("select 1 from sqlite_master where type = 'table' and name = 'log'").fetchone():
			db.execute(
				"insert or ignore into samples (plugin, stream, ts, key, value, number, fetched) "
				"select plugin, 'log', ts, key, value, null, ts from log"
			)
			db.execute('drop table log')

	@property
	def healthy(self) -> bool:
		return not self._failed

	def write(self, samples: Iterable[Sample]) -> None:
		rows = [(s.plugin, s.stream, s.ts, s.key, s.encoded(), s.number, s.fetched) for s in samples]
		if not rows:
			return
		with self._lock:
			if (db := self._connection()) is None:
				return
			try:
				db.executemany('insert or replace into samples (plugin, stream, ts, key, value, number, fetched) values (?, ?, ?, ?, ?, ?, ?)', rows)
				db.commit()
			except Exception:
				log.exception('the history could not be written')

	def read(self, plugin: str, stream: str, since, until=None, key: str | None = None) -> List[Sample]:
		query = 'select ts, key, value, number, fetched from samples where plugin = ? and stream = ? and ts >= ?'
		args: list = [plugin, stream, toTimestamp(since)]
		if until is not None:
			query += ' and ts <= ?'
			args.append(toTimestamp(until))
		if key is not None:
			query += ' and key = ?'
			args.append(key)
		with self._lock:
			if (db := self._connection()) is None:
				return []
			try:
				rows = db.execute(query + ' order by ts, key', args).fetchall()
			except Exception:
				log.exception(f'{plugin}: the history could not be read')
				return []
		out = []
		for ts, k, value, number, fetched in rows:
			try:
				out.append(Sample(plugin, stream, k, ts, json.loads(value), fetched, number))
			except ValueError:
				log.warning(f'{plugin}: a stored value for {k} is not readable; it is skipped')
		return out

	def extent(self, plugin: str, stream: str, key: str, since, until=None) -> Extent:
		query = 'select count(number), min(number), max(number), avg(number) from samples where plugin = ? and stream = ? and key = ? and ts >= ?'
		args: list = [plugin, stream, key, toTimestamp(since)]
		if until is not None:
			query += ' and ts <= ?'
			args.append(toTimestamp(until))
		with self._lock:
			if (db := self._connection()) is None:
				return Extent(0, None, None, None)
			try:
				count, low, high, mean = db.execute(query, args).fetchone()
			except Exception:
				log.exception(f'{plugin}: the history could not be read')
				return Extent(0, None, None, None)
		return Extent(count or 0, low, high, mean)

	def latest(self, plugin: str, stream: str, key: str | None = None) -> Optional[Sample]:
		query = 'select ts, key, value, number, fetched from samples where plugin = ? and stream = ?'
		args: list = [plugin, stream]
		if key is not None:
			query += ' and key = ?'
			args.append(key)
		with self._lock:
			if (db := self._connection()) is None:
				return None
			try:
				row = db.execute(query + ' order by ts desc limit 1', args).fetchone()
			except Exception:
				log.exception(f'{plugin}: the history could not be read')
				return None
		if row is None:
			return None
		ts, k, value, number, fetched = row
		return Sample(plugin, stream, k, ts, json.loads(value), fetched, number)

	def prune(self, stream: str | None, before) -> None:
		with self._lock:
			if (db := self._connection()) is None:
				return
			try:
				if stream is None:
					db.execute('delete from samples where ts < ?', (toTimestamp(before),))
				else:
					db.execute('delete from samples where stream = ? and ts < ?', (stream, toTimestamp(before)))
				db.commit()
			except Exception:
				log.exception('the history could not be pruned')

	def close(self) -> None:
		with self._lock:
			if self._db is not None:
				self._db.close()
				self._db = None
