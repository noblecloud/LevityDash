"""The history database as one more thing the supervisor keeps running.

Stdlib only and Qt-free, like the rest of the supervisor: it reads `[History]` from the real config without
importing LevityDash, and turns it into the command that runs the server bare, as a plain process (no container).

`serverCommand(section)` is pure, so it is tested without a database. It returns None, and says why, when there is
nothing for the supervisor to start: history is off, the backend is SQLite, the server lives on another machine, a
token means someone else manages it, `manage = no`, or the program is not installed.

- InfluxDB 3 Core: `influxdb3 serve`, bound to 127.0.0.1 without auth (nothing else can reach it), with its
  usage upload to InfluxData switched off, data under the app's data folder. Install it with `brew install influxdb3-core`, or from influxdata.com and set `binary`.
- QuestDB: only started when `command` is given in `[History]`, since QuestDB's own launcher forks into the
  background and cannot be supervised as it is. A wrapper script that runs it in the foreground works.
"""
import configparser
import os
import shlex
import shutil
from pathlib import Path
from typing import Callable, Dict, List, Mapping, NamedTuple, Optional, Tuple

__all__ = ['Server', 'readHistoryConfig', 'serverCommand']

DEFAULT_PORTS = {'influxdb': 8181, 'questdb': 9000}
LOCAL = ('localhost', '127.0.0.1', '::1', '')
INFLUX_PATHS = ('/opt/homebrew/bin/influxdb3', '/usr/local/bin/influxdb3', '~/.influxdb/influxdb3', '~/.local/bin/influxdb3')


class Server(NamedTuple):
	name: str
	argv: List[str]
	host: str
	port: int


def _configDir() -> Path:
	from appdirs import AppDirs
	return Path(AppDirs(appname='LevityDash', appauthor='LevityDash.app').user_config_dir)


def _dataDir() -> Path:
	from appdirs import AppDirs
	return Path(AppDirs(appname='LevityDash', appauthor='LevityDash.app').user_data_dir)


def readHistoryConfig(configDir: Optional[Path] = None) -> Dict[str, str]:
	"""`[History]` of the real config as strings, from `config.toml` or, until it is migrated, `config.ini`."""
	found: Dict[str, str] = {}
	try:
		configDir = configDir or _configDir()
		toml = configDir / 'config.toml'
		if toml.exists():
			import tomllib
			section = tomllib.loads(toml.read_text(encoding='utf-8')).get('History', {})
			found = {str(k): str(v) for k, v in section.items()}
		elif (ini := configDir / 'config.ini').exists():
			parser = configparser.ConfigParser(interpolation=None)
			parser.optionxform = str
			parser.read(ini, encoding='utf-8')
			if parser.has_section('History'):
				found = dict(parser.items('History'))
	except Exception as e:  # noqa: BLE001 - a damaged config must not stop the launcher
		print(f'[run] could not read [History] ({e}); no database to supervise')
		return {'enabled': 'no'}
	if os.environ.get('LEVITYDASH_HISTORY', '').strip().lower() in ('off', '0', 'false', 'no'):
		found['enabled'] = 'no'
	if (named := os.environ.get('LEVITYDASH_HISTORY_BACKEND', '').strip().lower()):
		found['backend'] = named
	if os.environ.get('LEVITYDASH_HISTORY_DB', '').strip():
		found['backend'] = 'sqlite'
	return found


def _off(value: Optional[str], default: bool = False) -> bool:
	if value is None or str(value).strip() == '':
		return default
	return str(value).strip().lower() in ('0', 'false', 'no', 'off')


def serverCommand(
	section: Mapping[str, str],
	which: Callable[[str], Optional[str]] = shutil.which,
	exists: Callable[[Path], bool] = lambda p: p.is_file(),
	dataDir: Optional[Path] = None,
) -> Tuple[Optional[Server], str]:
	"""`(server, why not)`: what to start for `section`, or None and the reason in a few words."""
	if _off(section.get('enabled')):
		return None, 'history is off'
	backend = (section.get('backend') or 'influxdb').strip().lower()
	if backend not in DEFAULT_PORTS:
		return None, f'backend {backend} needs no server'
	if _off(section.get('manage')):
		return None, 'manage is off'
	host = (section.get('host') or 'localhost').strip()
	if host not in LOCAL:
		return None, f'{host} is another machine'
	try:
		port = int(section.get('port') or DEFAULT_PORTS[backend])
	except ValueError:
		port = DEFAULT_PORTS[backend]
	if (command := (section.get('command') or '').strip()):
		return Server(backend, shlex.split(command), 'localhost', port), ''
	if backend != 'influxdb':
		return None, f'{backend} is started by its own launcher (set command to supervise it)'
	if (section.get('token') or '').strip():
		return None, 'a token means the server is managed elsewhere'
	binary = (section.get('binary') or '').strip() or which('influxdb3')
	if not binary:
		binary = next((str(p) for p in (Path(c).expanduser() for c in INFLUX_PATHS) if exists(p)), None)
	if not binary:
		return None, 'influxdb3 is not installed (brew install influxdb3-core, or set binary)'
	data = (Path(section['data-dir']).expanduser() if section.get('data-dir') else (dataDir or _dataDir()) / 'history' / 'influxdb')
	argv = [
		binary, 'serve', '--node-id', 'levitydash', '--object-store', 'file', '--data-dir', str(data),
		'--http-bind', f'127.0.0.1:{port}', '--without-auth', '--disable-telemetry-upload',
	]
	return Server('history', argv, '127.0.0.1', port), ''
