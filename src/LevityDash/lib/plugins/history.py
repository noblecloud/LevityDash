"""The recorded history of every logged plugin, kept across restarts.

A plugin with a log (`logged=True`) copies its realtime values into the log once a minute or so.
The log lives in memory, so a restart empties every graph until the plugin has run for a while.
This module writes each log entry to a small SQLite file in the cache directory and reads the
last two days back when the plugins start.

- Only the log is stored. The current value of a key is not restored: the realtime layer stamps a
  late value with the time it arrives, so a restored reading would look fresh. A value from the
  log keeps its own time, so a graph shows it where it belongs and the freshness check sees how old it is.
- A plugin is written at most once a minute, however often it logs.
- Rows older than two days (the length the log keeps) are deleted when the file opens and once an hour.
- Nothing here raises into a plugin. A file that cannot be opened or written is logged once and the
  plugins run without history.
- `LEVITYDASH_HISTORY=off` turns it off. `LEVITYDASH_HISTORY_DB` names another file.

What is stored is the raw reading in the source's own unit (`60.5` for a Fahrenheit key), not the
converted measurement. A restored entry goes through the same unit conversion as a live one, so
a unit setting changed since the restart still applies. Dates use the wire codec (`lib/wire/codec.py`).
"""
import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Dict, Iterable, List, Optional, Tuple

__all__ = ['HistoryStore', 'KEEP_FOR', 'WRITE_EVERY', 'historyStore', 'recordLog', 'restoreLog']

log = logging.getLogger('LevityDash.history')

#: How far back a restart reads, and how long a row is kept. The same as `ObservationLog.removeOldObservations`.
KEEP_FOR = timedelta(days=2)
#: A plugin is written at most this often.
WRITE_EVERY = timedelta(minutes=1)

_SCHEMA = """
create table if not exists log (
	plugin text not null,
	ts real not null,
	key text not null,
	value text not null,
	primary key (plugin, ts, key)
) without rowid
"""


def _enabled() -> bool:
	return os.environ.get('LEVITYDASH_HISTORY', '').strip().lower() not in ('off', '0', 'false', 'no')


class HistoryStore:
	"""One SQLite file. Safe to call from any thread."""

	def __init__(self, path: Path | str):
		self.path = Path(path)
		self._lock = threading.Lock()
		self._lastWrite: Dict[str, float] = {}
		self._lastPrune = 0.0
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
			db.commit()
			self._db = db
			self._prune(db)
		except Exception:
			self._failed = True
			log.exception(f'{self.path} could not be opened; the plugins run without saved history')
		return self._db

	def _prune(self, db: sqlite3.Connection) -> None:
		cutoff = (datetime.now(timezone.utc) - KEEP_FOR).timestamp()
		db.execute('delete from log where ts < ?', (cutoff,))
		db.commit()
		self._lastPrune = monotonic()

	def due(self, plugin: str) -> bool:
		"""True when `plugin` has not been written within `WRITE_EVERY`."""
		return monotonic() - self._lastWrite.get(plugin, float('-inf')) >= WRITE_EVERY.total_seconds()

	def write(self, plugin: str, when: datetime, values: Dict[str, Any]) -> None:
		"""Store `values` ({key text: JSON-safe value}) for `plugin` at `when`."""
		with self._lock:
			db = self._connection()
			if db is None:
				return
			try:
				ts = when.astimezone(timezone.utc).timestamp()
				db.executemany(
					'insert or replace into log (plugin, ts, key, value) values (?, ?, ?, ?)',
					[(plugin, ts, key, json.dumps(value)) for key, value in values.items()],
				)
				db.commit()
				self._lastWrite[plugin] = monotonic()
				if monotonic() - self._lastPrune > 3600:
					self._prune(db)
			except Exception:
				log.exception(f'{plugin}: the history could not be written')

	def read(self, plugin: str, since: Optional[datetime] = None) -> List[Tuple[datetime, Dict[str, Any]]]:
		"""The stored entries of `plugin`, oldest first, as `(time, {key text: value})`."""
		with self._lock:
			db = self._connection()
			if db is None:
				return []
			since = since or datetime.now(timezone.utc) - KEEP_FOR
			try:
				rows = db.execute(
					'select ts, key, value from log where plugin = ? and ts >= ? order by ts', (plugin, since.timestamp())
				).fetchall()
			except Exception:
				log.exception(f'{plugin}: the history could not be read')
				return []
		entries: Dict[float, Dict[str, Any]] = {}
		for ts, key, value in rows:
			try:
				entries.setdefault(ts, {})[key] = json.loads(value)
			except ValueError:
				log.warning(f'{plugin}: a stored value for {key} is not readable; it is skipped')
		return [(datetime.fromtimestamp(ts, timezone.utc), values) for ts, values in sorted(entries.items())]

	def close(self) -> None:
		with self._lock:
			if self._db is not None:
				self._db.close()
				self._db = None


_store: Optional[HistoryStore] = None
_storeLock = threading.Lock()


def historyStore() -> Optional[HistoryStore]:
	"""The process's store, or None when history is off."""
	global _store
	if not _enabled():
		return None
	with _storeLock:
		if _store is None:
			if (named := os.environ.get('LEVITYDASH_HISTORY_DB', '').strip()):
				path = Path(named).expanduser()
			else:
				from LevityDash import LevityDashboard
				path = Path(LevityDashboard.paths.cache) / 'history.sqlite3'
			_store = HistoryStore(path)
		return _store


def _forget() -> None:
	"""Close the process's store so the next call opens the file again. For tests."""
	global _store
	with _storeLock:
		if _store is not None:
			_store.close()
		_store = None


def _encodeValue(value: Any) -> Any:
	from LevityDash.lib.wire.codec import encode_value
	return encode_value(value)


def recordLog(plugin: Any, archive: Iterable[Tuple[Any, Any]], when: Optional[datetime] = None) -> int:
	"""Store the entries a plugin just copied into its log. Returns how many were written.

	`archive` is the realtime archive: `(key, ArchivedObservationValue)` pairs. A value that
	cannot be encoded is skipped, never raised.
	"""
	store = historyStore()
	if store is None or not store.due(plugin.name):
		return 0
	values: Dict[str, Any] = {}
	times = []
	for key, item in archive:
		try:
			raw = getattr(item, 'rawValue', item)
			encoded = _encodeValue(getattr(raw, 'value', raw))
			json.dumps(encoded)
		except Exception:
			continue
		if encoded is None:
			continue
		values[str(key)] = encoded
		if (timestamp := getattr(item, 'timestamp', None)) is not None:
			times.append(timestamp)
	if not values:
		return 0
	when = when or (max(times) if times else datetime.now(timezone.utc))
	store.write(plugin.name, when, values)
	return len(values)


def restoreLog(plugin: Any) -> int:
	"""Put the stored history of `plugin` back into its log. Returns how many entries were restored.

	Never raises. A plugin with no log, or with nothing stored, restores nothing.
	"""
	try:
		store = historyStore()
		if store is None or getattr(plugin, 'log', None) is None:
			return 0
		entries = store.read(plugin.name)
		if not entries:
			return 0
		restored = [entry for entry in (_archivedEntry(plugin, when, values) for when, values in entries) if entry is not None]
		if restored:
			plugin.log.update({'data': restored})
		log.info(f'{plugin.name}: restored {len(restored)} history entries')
		return len(restored)
	except Exception:
		log.exception(f'{getattr(plugin, "name", plugin)}: the saved history could not be restored; it starts empty')
		return 0


class _Origin:
	"""Stands in for the live value an `ArchivedObservationValue` is normally copied from.

	The log rebuilds a value from `rawValue` and `metadata` alone; `value` only has to exist.
	"""

	def __init__(self, raw, metadata, source, timestamp):
		from LevityDash.lib.plugins.observation import TimeSeriesItem
		self.value = raw
		self.metadata = metadata
		self.source = source
		self.timestamp = timestamp
		self.rawValue = TimeSeriesItem(raw, timestamp)
		self.sourceUnitValue = raw


def _archivedEntry(plugin: Any, when: datetime, values: Dict[str, Any]):
	from LevityDash.lib.plugins.categories import CategoryItem
	from LevityDash.lib.plugins.observation import ArchivedObservation, ArchivedObservationValue
	from LevityDash.lib.wire.codec import decode_value

	entry = ArchivedObservation()
	entry.__dict__['_source'] = plugin
	items = {}
	for text, stored in values.items():
		try:
			key = CategoryItem(text)
			value = decode_value(stored)
			metadata = plugin.schema.getUnitMetaData(key, plugin)
			if metadata is None:
				continue
			items[key] = ArchivedObservationValue(_Origin(value, metadata, plugin.realtime, when))
		except Exception:
			log.debug(f'{plugin.name}: {text} could not be restored', exc_info=True)
	if not items:
		return None
	entry.timestamp = when
	dict.update(entry, items)
	return entry
