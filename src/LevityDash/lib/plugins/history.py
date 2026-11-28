"""What LevityDash pulls, kept across restarts.

The storage itself is `LevityDash.lib.history` (a time-series database, or SQLite as the fallback; see its
docstring and `[History]` in the config). This module is what plugins call, and it keeps three things:

- **The log** (`log` stream). A plugin with a log (`logged=True`) copies its realtime values into it about once a
  minute. The log lives in memory, so a restart used to empty every graph. Each entry is written here, and the last
  `restore` days (two by default, the length the log keeps) are read back when the plugins start.
- **Realtime snapshots** (`realtime` stream) of every plugin that has no log (aircraft, host vitals, ...), written by a
  recorder thread every few minutes, so what any plugin showed stays queryable.
- **Responses** (`raw` stream): the body of every REST response, as fetched, once per `raw-every` minutes per endpoint.
  `latestRaw` hands the newest back, and `REST.getData` uses it when the network is down at start-up, so a display
  that boots before its wifi still shows the last forecast.

- Only the log is put back into a plugin. The current value of a key is not restored: the realtime layer stamps a
  late value with the time it arrives, so a restored reading would look fresh. A value from the log keeps its own
  time, so a graph shows it where it belongs and the freshness check sees how old it is.
- Nothing here raises into a plugin. A backend that cannot be reached is logged once and the plugins run without history.
- `LEVITYDASH_HISTORY=off` turns it off, `LEVITYDASH_HISTORY_DB` names a SQLite file, `LEVITYDASH_HISTORY_BACKEND` picks a backend.

What is stored is the raw reading in the source's own unit (`60.5` for a Fahrenheit key), not the
converted measurement. A restored entry goes through the same unit conversion as a live one, so
a unit setting changed since the restart still applies. Dates use the wire codec (`lib/wire/codec.py`).
"""
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any, Dict, Iterable, List, Optional, Tuple

from LevityDash.lib import history as backends
from LevityDash.lib.history import Extent, HistoryBackend, Sample, fromTimestamp, toTimestamp

__all__ = [
	'HistoryStore', 'KEEP_FOR', 'WRITE_EVERY', 'historyStore', 'recordLog', 'restoreLog', 'recordRealtime', 'recordRaw',
	'latestRaw', 'extentOf', 'startRecorder', 'stopRecorder',
]

log = logging.getLogger('LevityDash.history')

#: How long the plugins' own logs are (`ObservationLog.removeOldObservations`); the default of `[History] restore`.
KEEP_FOR = timedelta(days=2)
#: A plugin's log is written at most this often.
WRITE_EVERY = timedelta(minutes=1)
#: A response body is not kept past this size.
MAX_RAW_BYTES = 2 * 1024 * 1024

LOG, REALTIME, RAW = 'log', 'realtime', 'raw'


class HistoryStore:
	"""The process's view of the backend: throttles, retention and the plugin-shaped reads. Safe to call from any thread."""

	def __init__(self, backend: HistoryBackend, settings: backends.Settings):
		self.backend = backend
		self.settings = settings
		self._lock = threading.Lock()
		self._lastWrite: Dict[Tuple[str, str], float] = {}
		self._lastPrune = 0.0
		self.prune()

	@property
	def path(self):
		return getattr(self.backend, 'path', None)

	def prune(self) -> None:
		self.backend.prune(None, datetime.now(timezone.utc) - timedelta(days=self.settings.retention))
		self._lastPrune = monotonic()

	def due(self, plugin: str, stream: str = LOG, every: Optional[timedelta] = None) -> bool:
		"""True when `plugin` has not written `stream` within `every` (a minute by default)."""
		every = WRITE_EVERY if every is None else every
		return monotonic() - self._lastWrite.get((plugin, stream), float('-inf')) >= every.total_seconds()

	def put(self, samples: List[Sample]) -> None:
		if not samples:
			return
		self.backend.write(samples)
		with self._lock:
			now = monotonic()
			for key in {(s.plugin, s.stream) for s in samples}:
				self._lastWrite[key] = now
			if now - self._lastPrune > 3600:
				self.prune()

	def write(self, plugin: str, when: datetime, values: Dict[str, Any], stream: str = LOG) -> None:
		"""Store `values` ({key text: JSON-safe value}) for `plugin` at `when`."""
		ts = toTimestamp(when)
		self.put([Sample(plugin, stream, key, ts, value) for key, value in values.items()])

	def read(self, plugin: str, since: Optional[datetime] = None, stream: str = LOG) -> List[Tuple[datetime, Dict[str, Any]]]:
		"""The stored entries of `plugin`, oldest first, as `(time, {key text: value})`."""
		since = since or datetime.now(timezone.utc) - timedelta(days=self.settings.restore)
		entries: Dict[float, Dict[str, Any]] = {}
		for sample in self.backend.read(plugin, stream, since):
			entries.setdefault(sample.ts, {})[sample.key] = sample.value
		return [(fromTimestamp(ts), values) for ts, values in sorted(entries.items())]

	def close(self) -> None:
		self.backend.close()


_store: Optional[HistoryStore] = None
_storeLock = threading.Lock()


def historyStore() -> Optional[HistoryStore]:
	"""The process's store, or None when history is off."""
	global _store
	with _storeLock:
		if _store is None:
			settings = backends.settings()
			if (backend := backends.openBackend(settings)) is None:
				return None
			_store = HistoryStore(backend, settings)
		return _store


def _forget() -> None:
	"""Close the process's store so the next call opens the backend again. For tests."""
	global _store
	stopRecorder()
	with _storeLock:
		if _store is not None:
			_store.close()
		_store = None


def _encodeValue(value: Any) -> Any:
	from LevityDash.lib.wire.codec import encode_value
	return encode_value(value)


def _collect(archive: Iterable[Tuple[Any, Any]]) -> Tuple[Dict[str, Any], list]:
	"""`({key text: JSON-safe value}, [timestamps])` of a realtime archive. A value that cannot be encoded is skipped."""
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
	return values, times


def _record(plugin: Any, archive: Iterable[Tuple[Any, Any]], when: Optional[datetime], stream: str, every: Optional[timedelta]) -> int:
	try:
		store = historyStore()
		if store is None or not store.due(plugin.name, stream, every):
			return 0
		values, times = _collect(archive)
		if not values:
			return 0
		store.write(plugin.name, when or (max(times) if times else datetime.now(timezone.utc)), values, stream)
		return len(values)
	except Exception:
		log.exception(f'{getattr(plugin, "name", plugin)}: the history could not be recorded')
		return 0


def recordLog(plugin: Any, archive: Iterable[Tuple[Any, Any]], when: Optional[datetime] = None) -> int:
	"""Store the entries a plugin just copied into its log. Returns how many were written.

	`archive` is the realtime archive: `(key, ArchivedObservationValue)` pairs. A value that
	cannot be encoded is skipped, never raised.
	"""
	return _record(plugin, archive, when, LOG, None)


def recordRealtime(plugin: Any, when: Optional[datetime] = None) -> int:
	"""Snapshot what `plugin` shows now, in the `realtime` stream. For a plugin that keeps no log."""
	store = historyStore()
	if store is None or not store.settings.snapshots:
		return 0
	try:
		archive = list(plugin.realtime.archived.items())
	except Exception:
		return 0
	return _record(plugin, archive, when, REALTIME, timedelta(minutes=store.settings.snapshotEvery))


def recordRaw(plugin: Any, name: str, body: Any) -> bool:
	"""Keep a response body (JSON-safe) of `plugin`'s endpoint `name`. At most one every `raw-every` minutes."""
	try:
		store = historyStore()
		if store is None or not store.settings.raw:
			return False
		stream = f'{RAW}:{name}'[:120]
		if not store.due(plugin.name, stream, timedelta(minutes=store.settings.rawEvery)):
			return False
		text = json.dumps(body, separators=(',', ':'))
		if len(text) > MAX_RAW_BYTES:
			log.debug(f'{plugin.name}: the {name} response is {len(text)} bytes; not kept')
			return False
		store.put([Sample(plugin.name, stream, name[:120], datetime.now(timezone.utc).timestamp(), body)])
		return True
	except Exception:
		log.exception(f'{getattr(plugin, "name", plugin)}: a response could not be kept')
		return False


def latestRaw(plugin: Any, name: str, within: Optional[timedelta] = None) -> Optional[Tuple[datetime, Any]]:
	"""The newest kept response of `plugin`'s endpoint `name` as `(when it was fetched, body)`, or None.

	`within` limits how old it may be (default: `[History] restore` days).
	"""
	try:
		store = historyStore()
		if store is None:
			return None
		sample = store.backend.latest(plugin.name, f'{RAW}:{name}'[:120], name[:120])
		if sample is None:
			return None
		when = fromTimestamp(sample.ts)
		if datetime.now(timezone.utc) - when > (within if within is not None else timedelta(days=store.settings.restore)):
			return None
		return when, sample.value
	except Exception:
		log.exception(f'{getattr(plugin, "name", plugin)}: a kept response could not be read')
		return None


def extentOf(plugin: Any, key: Any, since: datetime, until: Optional[datetime] = None, stream: str = LOG) -> Extent:
	"""Count, minimum, maximum and mean of `key` over a span, for a high/low that outlives the in-memory log."""
	store = historyStore()
	if store is None:
		return Extent(0, None, None, None)
	return store.backend.extent(plugin.name, stream, str(key), since, until)


class _Recorder(threading.Thread):
	"""Writes the realtime snapshots of the plugins that keep no log."""

	def __init__(self, plugins):
		super().__init__(name='History-Recorder', daemon=True)
		self.plugins = plugins
		self.stopped = threading.Event()

	def run(self):
		while not self.stopped.wait(60.0):
			for plugin in list(self.plugins):
				if self.stopped.is_set():
					return
				if getattr(plugin, 'log', None) is None and getattr(plugin, 'enabled', False) and hasattr(plugin, 'realtime'):
					recordRealtime(plugin)


_recorder: Optional[_Recorder] = None


def startRecorder(plugins) -> None:
	"""Start the snapshot thread over `plugins` (the plugin list; read each round). Does nothing when history is off."""
	global _recorder
	if _recorder is not None or historyStore() is None:
		return
	_recorder = _Recorder(plugins)
	_recorder.start()


def stopRecorder() -> None:
	global _recorder
	if _recorder is not None:
		_recorder.stopped.set()
		_recorder = None


def restoreLog(plugin: Any) -> int:
	"""Put the stored history of `plugin` back into its log. Returns how many entries were restored.

	Never raises. A plugin with no log, or with nothing stored, restores nothing.
	"""
	try:
		store = historyStore()
		if store is None or getattr(plugin, 'log', None) is None:
			return 0
		entries = store.read(plugin.name, stream=LOG)
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
