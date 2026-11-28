"""Everything LevityDash pulls, kept so a restart does not empty the graphs.

`HistoryBackend` (`base.py`) is the interface: rows in (`Sample`), rows out, the range of one key. Three backends
implement it, picked by `[History] backend`:

- `influxdb` (default): InfluxDB 3, a real time-series database run as a plain process (the supervisor starts it).
- `questdb`: QuestDB, the drop-in alternative.
- `sqlite`: one file in the cache folder. Needs nothing installed; it is also what the app falls back to when the
  server cannot be reached at start-up, so a display never waits on a database.

`lib/plugins/history.py` is what plugins call; it turns plugin values into `Sample`s and back. Nothing else needs
to know which backend is in use.

Settings are read in one place, `settings()` (the `[History]` section of the config). To add a backend: subclass
`HistoryBackend` (or `QueuedBackend` for a server), and add it to `_BACKENDS`.
"""
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional

from .base import Extent, HistoryBackend, Sample, fromTimestamp, numberOf, toTimestamp
from .influxdb import InfluxDBBackend
from .questdb import QuestDBBackend
from .sqlitestore import SQLiteBackend

__all__ = [
	'Extent', 'HistoryBackend', 'Sample', 'Settings', 'settings', 'settingsFrom', 'openBackend',
	'InfluxDBBackend', 'QuestDBBackend', 'SQLiteBackend', 'numberOf', 'toTimestamp', 'fromTimestamp',
]

log = logging.getLogger('LevityDash.history')

SECTION = 'History'
DEFAULT_PORTS = {'influxdb': 8181, 'questdb': 9000}


def _unquoted(value):
	"""`"influxdb"` and `influxdb` are the same setting: the config is TOML now, and an INI file may still carry quotes."""
	if isinstance(value, str) and len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
		return value[1:-1]
	return value


def _flag(text, default: bool) -> bool:
	if text is None or str(text).strip() == '':
		return default
	return str(text).strip().lower() not in ('0', 'false', 'no', 'off')


def _number(text, default: float, low: float = 0) -> float:
	try:
		value = float(str(text).strip())
	except (TypeError, ValueError):
		return default
	return value if value >= low else default


@dataclass(frozen=True)
class Settings:
	enabled: bool = True
	backend: str = 'influxdb'
	fallback: str = 'sqlite'
	host: str = 'localhost'
	port: int = 0
	database: str = 'levitydash'
	token: str = ''
	username: str = ''
	password: str = ''
	path: str = ''
	#: Days a row is kept.
	retention: float = 30
	#: Days read back into the plugins at start-up (the plugins' own logs hold two days).
	restore: float = 2
	#: Keep the body of every response a plugin fetches.
	raw: bool = True
	#: At most one body per plugin and endpoint this often, in minutes.
	rawEvery: float = 15
	#: Forecast snapshots (hourly, daily, minutely endpoints) and realtime snapshots.
	snapshots: bool = True
	#: Minutes between snapshots of one plugin.
	snapshotEvery: float = 5

	@property
	def servicePort(self) -> int:
		return self.port or DEFAULT_PORTS.get(self.backend, 0)


def settingsFrom(section: Optional[Mapping[str, str]], env: Optional[Mapping[str, str]] = None) -> Settings:
	"""`Settings` from the `[History]` mapping and the environment. A value that cannot be read keeps its default."""
	env = os.environ if env is None else env
	section = section or {}
	get = lambda key, default='': (_unquoted(section.get(key)) if section.get(key) not in (None, '') else default)
	backend = str(get('backend', Settings.backend)).strip().lower()
	if backend not in _BACKENDS:
		log.warning(f'[History] backend = {backend!r} is not one of {", ".join(_BACKENDS)}; using {Settings.backend}')
		backend = Settings.backend
	fallback = str(get('fallback', Settings.fallback)).strip().lower()
	if fallback not in ('sqlite', 'none', 'off'):
		fallback = 'sqlite'
	path = str(get('path', '')).strip()
	enabled = _flag(get('enabled', None), True)
	# The environment outranks the file, as it does for the rest of the app.
	if (named := env.get('LEVITYDASH_HISTORY_DB', '').strip()):
		backend, path = 'sqlite', named
	if (named := env.get('LEVITYDASH_HISTORY_BACKEND', '').strip().lower()) in _BACKENDS:
		backend = named
	if env.get('LEVITYDASH_HISTORY', '').strip().lower() in ('off', '0', 'false', 'no'):
		enabled = False
	port = int(_number(get('port', 0), 0))
	return Settings(
		enabled=enabled, backend=backend, fallback=fallback,
		host=str(get('host', Settings.host)).strip(), port=port, database=str(get('database', Settings.database)).strip(),
		token=str(get('token', '')).strip(), username=str(get('username', '')).strip(), password=str(get('password', '')),
		path=path, retention=_number(get('retention', Settings.retention), Settings.retention, 0.01),
		restore=_number(get('restore', Settings.restore), Settings.restore, 0),
		raw=_flag(get('raw', None), True), rawEvery=_number(get('raw-every', Settings.rawEvery), Settings.rawEvery, 0),
		snapshots=_flag(get('snapshots', None), True), snapshotEvery=_number(get('snapshot-every', Settings.snapshotEvery), Settings.snapshotEvery, 0),
	)


def settings() -> Settings:
	"""The user's `[History]` settings. The only place the config is read."""
	try:
		from LevityDash.lib.config import userConfig
		section = userConfig[SECTION] if userConfig.has_section(SECTION) else {}
	except Exception:  # noqa: BLE001 - no config yet: the defaults
		section = {}
	return settingsFrom(section)


def _sqlitePath(s: Settings) -> Path:
	if s.path:
		return Path(s.path).expanduser()
	from LevityDash import LevityDashboard
	return Path(LevityDashboard.paths.cache) / 'history.sqlite3'


def _influx(s: Settings) -> HistoryBackend:
	backend = InfluxDBBackend(s.host, s.servicePort, s.database, s.token, max(int(s.retention), 1))
	return backend if backend.connect() else None


def _quest(s: Settings) -> HistoryBackend:
	backend = QuestDBBackend(s.host, s.servicePort, s.username, s.password)
	return backend if backend.connect() else None


def _sqlite(s: Settings) -> HistoryBackend:
	return SQLiteBackend(_sqlitePath(s))


_BACKENDS: Dict[str, Callable[[Settings], Optional[HistoryBackend]]] = {'influxdb': _influx, 'questdb': _quest, 'sqlite': _sqlite}


def openBackend(s: Settings) -> Optional[HistoryBackend]:
	"""The backend to use, or None when history is off. A server that cannot be reached is replaced by the fallback."""
	if not s.enabled:
		return None
	if (backend := _BACKENDS[s.backend](s)) is not None:
		return backend
	if s.fallback == 'sqlite':
		log.warning(f'{s.backend} is not reachable at {s.host}:{s.servicePort}; keeping history in {_sqlitePath(s)} instead')
		return _sqlite(s)
	log.warning(f'{s.backend} is not reachable at {s.host}:{s.servicePort}; running without saved history')
	return None
