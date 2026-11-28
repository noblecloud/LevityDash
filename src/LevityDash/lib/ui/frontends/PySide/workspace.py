"""A workspace: one YAML file naming the windows of a multi-window layout.

One process per window, as `--new-instance` already works: the process that opens the file shows window 1 and
spawns one child per remaining window (`spawn`), each with its own control socket. A workspace never changes
what `[Display] dashboard` means; `[Display] workspace` may name one to open when no flag is given, and
`--workspace NAME_OR_PATH` opens one for this run only.

The file lives in `<config>/workspaces/<name>.yaml`::

	name: desk                                  # optional; the file's stem by default
	theme: night                                # optional; forced on every window, else each follows its dashboard
	windows:
	  - id: main                                # stable, unique in the file; the window's control socket id
	    dashboard: home.levity                  # <config>/saves/dashboards, then cwd, or absolute
	    screen: {name: "DELL U2720Q", fallback: primary}
	    geometry: {x: 0, y: 0, width: 100%, height: 100%}   # fractions of that screen's availableGeometry
	    mode: windowed                          # windowed | fullscreen | kiosk

Validation is strict: an unknown key is an error that names the key, never a silent default. `geometry`
takes a fraction (`0.5`) or a percentage (`50%`) and defaults to the whole screen; `mode` defaults to
`windowed`; `screen.fallback` is `primary` or another screen name, and a name that is not attached falls back
without being rewritten, so the file still names the monitor the layout was written for.

This module is Qt-free: the file half runs before any `QApplication` exists (a child is spawned with nothing
of the sort), and the parts that do read a window take it as a duck-typed object. The one piece of Qt that
matters — which `QScreen` a name means — is `chooseScreen`, which answers a name from a list of names.

Geometry is written back on quit, one entry at a time: each process re-reads the file, patches its own
window's `screen` and `geometry`, and writes it out. Nothing else in the file is added, removed or reordered.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence, cast

import yaml

#: Set on a child: the workspace file it belongs to (its argv is the documented `--new-instance` one).
WORKSPACE_ENV = 'LEVITYDASH_WORKSPACE'
#: Set on a child: the one theme the whole layout uses, chosen by the primary from the file or window 1.
THEME_ENV = 'LEVITYDASH_WORKSPACE_THEME'

#: A workspace is YAML; both spellings are accepted when resolving a bare name.
SUFFIXES = ('.yaml', '.yml')

#: The three window modes. `kiosk` is frameless at the screen's full geometry; `fullscreen` keeps the frame
#: (the menu bar and the way out) and takes the screen's *available* area.
MODES = ('windowed', 'fullscreen', 'kiosk')

_ROOT_KEYS = ('name', 'theme', 'windows')
_WINDOW_KEYS = ('id', 'dashboard', 'screen', 'geometry', 'mode')
_SCREEN_KEYS = ('name', 'fallback')
_GEOMETRY_KEYS = ('x', 'y', 'width', 'height')


class WorkspaceError(Exception):
	"""A workspace file that cannot be used. `key` names the offending key when one is to blame."""

	def __init__(self, message: str, key: str | None = None):
		super().__init__(message)
		self.key = key


def log(message: str) -> None:
	"""One line on stderr, in the `levitydash:` form every launch message uses."""
	print(f'levitydash: {message}', file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------------------------------------------------
# Values


def slug(text: str, limit: int = 24) -> str:
	"""A socket-safe name: lowercase, letters and digits, single dashes, short enough for an AF_UNIX path."""
	slugged = ''.join(character if (character.isascii() and character.isalnum()) else '-' for character in str(text).lower())
	while '--' in slugged:
		slugged = slugged.replace('--', '-')
	return slugged.strip('-')[:limit].strip('-') or 'window'


def _rect(value) -> tuple[int, int, int, int]:
	"""`(x, y, width, height)` for a tuple or anything shaped like a `QRect` — this module never imports Qt."""
	if isinstance(value, (tuple, list)) and len(value) == 4:
		return int(value[0]), int(value[1]), int(value[2]), int(value[3])
	box = cast(Any, value)
	return int(box.left()), int(box.top()), int(box.width()), int(box.height())


@dataclass
class Screen:
	"""The monitor a window goes on, and where to go when it is not attached."""

	name: str
	fallback: str | None = None

	def asDict(self) -> dict:
		data = {'name': self.name}
		if self.fallback is not None:
			data['fallback'] = self.fallback
		return data


@dataclass
class Geometry:
	"""Fractions of a screen's available geometry."""

	x: float = 0.0
	y: float = 0.0
	width: float = 1.0
	height: float = 1.0

	def pixels(self, available) -> tuple[int, int, int, int]:
		"""The pixel rectangle on `available` (`(x, y, width, height)` or a `QRect`).

		Clamped to the available area: a layout written on a bigger monitor still lands on screen instead of
		hanging off the bottom-right corner.
		"""
		ax, ay, aw, ah = _rect(available)
		aw = max(aw, 1)
		ah = max(ah, 1)
		width = min(max(round(self.width * aw), 1), aw)
		height = min(max(round(self.height * ah), 1), ah)
		x = min(ax + round(self.x * aw), ax + aw - width)
		y = min(ay + round(self.y * ah), ay + ah - height)
		return x, y, width, height

	def asDict(self) -> dict:
		return {'x': self.x, 'y': self.y, 'width': self.width, 'height': self.height}

	def spec(self) -> str:
		"""The `--geometry` token: the same four values, comma separated."""
		return ','.join(_number(value) for value in (self.x, self.y, self.width, self.height))

	@classmethod
	def fractions(cls, rect, available) -> 'Geometry':
		"""`rect` (pixels) as fractions of `available` — what the window currently is, for the write-back."""
		rx, ry, rw, rh = _rect(rect)
		ax, ay, aw, ah = _rect(available)
		aw = max(aw, 1)
		ah = max(ah, 1)
		return cls(
			x=round((rx - ax) / aw, 6),
			y=round((ry - ay) / ah, 6),
			width=round(rw / aw, 6),
			height=round(rh / ah, 6),
		)


def _number(value: float) -> str:
	"""A float without trailing zeros: 0.5 stays `0.5`, 1.0 becomes `1`."""
	text = f'{value:.6f}'.rstrip('0').rstrip('.')
	return text or '0'


def _fraction(value: Any, key: str, where: str) -> float:
	"""One geometry value: a fraction between 0 and 1, or a percentage string."""
	original = value
	if isinstance(value, str):
		text = value.strip()
		percent = text.endswith('%')
		try:
			value = float(text[:-1] if percent else text)
		except ValueError:
			raise WorkspaceError(f'{where}: {key} {original!r} is not a number or a percentage such as "50%"', key) from None
		if percent:
			value = value / 100
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		raise WorkspaceError(f'{where}: {key} must be a fraction (0.5) or a percentage ("50%"), not {original!r}', key)
	number = float(value)
	if not 0 <= number <= 1:
		raise WorkspaceError(
			f'{where}: {key} is {original!r}; write a fraction between 0 and 1, or a percentage such as "50%"', key
		)
	return round(number, 6)


def parseGeometry(text: str) -> Geometry:
	"""`--geometry x,y,width,height`, each a fraction or a percentage."""
	parts = [part for part in str(text).replace(' ', '').split(',') if part != '']
	if len(parts) != 4:
		raise WorkspaceError(f'--geometry {text!r} needs four values: x,y,width,height as fractions or percentages', 'geometry')
	values = [_fraction(part, key, '--geometry') for part, key in zip(parts, _GEOMETRY_KEYS)]
	return Geometry(*values)


# ---------------------------------------------------------------------------------------------------------------------
# The file


@dataclass
class Window:
	"""One window of a layout."""

	dashboard: str
	id: str | None = None
	screen: Screen | None = None
	geometry: Geometry | None = None
	#: None means the file did not say, so nothing is passed on and the window is placed as usual.
	mode: str | None = None

	@property
	def modeName(self) -> str:
		return self.mode or 'windowed'

	def asDict(self) -> dict:
		data: dict[str, Any] = {}
		if self.id is not None:
			data['id'] = self.id
		data['dashboard'] = self.dashboard
		if self.screen is not None:
			data['screen'] = self.screen.asDict()
		if self.geometry is not None:
			data['geometry'] = self.geometry.asDict()
		if self.mode is not None:
			data['mode'] = self.mode
		return data


@dataclass
class Workspace:
	"""A parsed layout: the file's windows, in the order they are opened."""

	windows: list[Window]
	name: str = ''
	theme: str | None = None
	#: The file this came from; None for a workspace built in memory from `--window`.
	path: Path | None = None

	def window(self, id: str | None) -> Window | None:
		"""The entry `id` names, by exact id or by the socket-safe form of it."""
		if not id:
			return None
		for window in self.windows:
			if window.id == id:
				return window
		for window in self.windows:
			if window.id is not None and slug(window.id) == slug(id):
				return window
		return None

	def asDict(self) -> dict:
		data: dict[str, Any] = {'name': self.name}
		if self.theme is not None:
			data['theme'] = self.theme
		data['windows'] = [window.asDict() for window in self.windows]
		return data


def _mapping(value, where: str, known: Sequence[str], key: str | None = None) -> dict:
	if not isinstance(value, dict):
		raise WorkspaceError(f'{where} must be a mapping with {", ".join(known)}, not {type(value).__name__}', key)
	for name in value:
		if name not in known:
			raise WorkspaceError(f'{where}: unknown key {name!r}; known: {", ".join(known)}', str(name))
	return value


def _screen(value, where: str) -> Screen:
	if isinstance(value, str):
		# `screen: "DELL U2720Q"` — the same thing as the mapping, without the fallback.
		return Screen(name=value)
	data = _mapping(value, f'{where}.screen', _SCREEN_KEYS, 'screen')
	name = data.get('name')
	if not isinstance(name, str) or not name.strip():
		raise WorkspaceError(f'{where}.screen: name must be the screen name as the system spells it', 'screen')
	fallback = data.get('fallback')
	if fallback is not None and (not isinstance(fallback, str) or not fallback.strip()):
		raise WorkspaceError(f'{where}.screen: fallback must be a screen name or "primary"', 'fallback')
	return Screen(name=name, fallback=fallback)


def _geometry(value, where: str) -> Geometry:
	if isinstance(value, str):
		try:
			return parseGeometry(value)
		except WorkspaceError as e:
			raise WorkspaceError(f'{where}.geometry: {e}', 'geometry') from None
	data = _mapping(value, f'{where}.geometry', _GEOMETRY_KEYS, 'geometry')
	values = {key: _fraction(data[key], key, f'{where}.geometry') for key in _GEOMETRY_KEYS if key in data}
	return Geometry(**{**{'x': 0.0, 'y': 0.0, 'width': 1.0, 'height': 1.0}, **values})


def _window(value, where: str) -> Window:
	data = _mapping(value, where, _WINDOW_KEYS)
	dashboard = data.get('dashboard')
	if not isinstance(dashboard, str) or not dashboard.strip():
		raise WorkspaceError(f'{where}.dashboard must be a dashboard file (relative to <config>/saves/dashboards, cwd, or absolute)', 'dashboard')
	id = data.get('id')
	if id is not None and (not isinstance(id, str) or not id.strip()):
		raise WorkspaceError(f'{where}.id must be a short name such as "main"; it is the control socket id', 'id')
	if id is None:
		raise WorkspaceError(f'{where}: id is required; it names the window and its control socket', 'id')
	mode = data.get('mode')
	if mode is not None and mode not in MODES:
		raise WorkspaceError(f'{where}.mode is {mode!r}; write one of {", ".join(MODES)}', 'mode')
	return Window(
		dashboard=dashboard,
		id=id,
		screen=_screen(data['screen'], where) if 'screen' in data else None,
		geometry=_geometry(data['geometry'], where) if 'geometry' in data else None,
		mode=mode,
	)


def parse(data: Any, *, name: str = '', path: Path | None = None) -> Workspace:
	"""Validate a loaded document. Every problem names the key it is about."""
	where = str(path) if path is not None else 'workspace'
	if not isinstance(data, dict):
		raise WorkspaceError(f'{where}: the top level must be a mapping with a windows: list, not {type(data).__name__}')
	for key in data:
		if key not in _ROOT_KEYS:
			raise WorkspaceError(f'{where}: unknown key {key!r}; known: {", ".join(_ROOT_KEYS)}', str(key))
	windowsData = data.get('windows')
	if not isinstance(windowsData, list) or not windowsData:
		raise WorkspaceError(f'{where}: windows must be a non-empty list of windows', 'windows')
	title = data.get('name', name)
	if title is not None and not isinstance(title, str):
		raise WorkspaceError(f'{where}: name must be a string', 'name')
	theme = data.get('theme')
	if theme is not None and (not isinstance(theme, str) or not theme.strip()):
		raise WorkspaceError(f'{where}: theme must be a theme name from resources/themes', 'theme')
	windows: list[Window] = []
	seen: set[str] = set()
	for index, entry in enumerate(windowsData):
		window = _window(entry, f'{where}: windows[{index}]')
		if window.id in seen:
			raise WorkspaceError(f'{where}: windows[{index}].id {window.id!r} is used twice; ids must be unique in one file', 'id')
		seen.add(str(window.id))
		windows.append(window)
	return Workspace(windows=windows, name=title or '', theme=theme, path=path)


def load(path: str | Path, *, name: str | None = None) -> Workspace:
	"""Read and validate a workspace file. Raises `WorkspaceError` with the key named."""
	path = Path(path).expanduser()
	try:
		text = path.read_text(encoding='utf-8')
	except OSError as e:
		raise WorkspaceError(f'{path} could not be read: {e}') from e
	try:
		data = yaml.safe_load(text)
	except yaml.YAMLError as e:
		raise WorkspaceError(f'{path} is not YAML: {e}') from e
	workspace = parse(data, name=path.stem if name is None else name, path=path.absolute())
	workspace.name = workspace.name or path.stem
	return workspace


def fromPaths(paths: Iterable[str | Path], *, name: str = '') -> Workspace:
	"""A workspace built in memory from repeated `--window`: no geometry, no ids, in the order given."""
	windows = [Window(dashboard=str(path)) for path in paths]
	if not windows:
		raise WorkspaceError('--window needs at least one dashboard path')
	return Workspace(windows=windows, name=name or 'windows')


def dump(workspace: Workspace) -> str:
	"""The file's text. `default_flow_style=None` keeps `geometry` and `screen` on one line, as written."""
	return yaml.safe_dump(workspace.asDict(), sort_keys=False, default_flow_style=None, allow_unicode=True)


def write(workspace: Workspace) -> Path:
	"""Write the whole file, atomically: a half-written workspace must never be read by the next window."""
	path = workspace.path
	if path is None:
		raise WorkspaceError('a workspace built with --window has no file to write')
	path.parent.mkdir(parents=True, exist_ok=True)
	temporary = path.with_name(path.name + '.tmp')
	temporary.write_text(dump(workspace), encoding='utf-8')
	temporary.replace(path)
	return path


def directory() -> Path | None:
	"""`<config>/workspaces`, or None when the config cannot be read."""
	try:
		from LevityDash.lib.config import userConfig

		return Path(userConfig.userPath.path) / 'workspaces'
	except Exception:  # noqa: BLE001 - a workspace name that cannot be resolved is reported by the caller
		return None


def resolve(text: str) -> Path:
	"""`desk`, `desk.yaml`, `./desk.yaml` or an absolute path, as the path on disk."""
	path = Path(text).expanduser()
	looksLikePath = path.is_absolute() or path.suffix.lower() in SUFFIXES or os.sep in text or (os.altsep and os.altsep in text)
	if looksLikePath:
		return path if path.is_absolute() else path.absolute()
	base = directory()
	if base is None:
		return path.absolute()
	for suffix in ('.yaml', *SUFFIXES[1:]):
		candidate = base / f'{text}{suffix}'
		if candidate.is_file():
			return candidate
	return base / f'{text}{SUFFIXES[0]}'


def savesDirectory() -> Path | None:
	"""`<config>/saves/dashboards`, the directory a workspace's relative dashboard path starts in."""
	try:
		from LevityDash.lib.config import userConfig

		return Path(userConfig.userPath.path) / 'saves' / 'dashboards'
	except Exception:  # noqa: BLE001 - without a config, cwd is the only answer left
		return None


def dashboardPath(text: str, saves: Path | None = None) -> Path:
	"""A window's `dashboard`: absolute, else `<config>/saves/dashboards`, else relative to cwd."""
	path = Path(text).expanduser()
	if path.is_absolute():
		return path
	saves = savesDirectory() if saves is None else saves
	if saves is not None:
		candidate = Path(saves) / path
		if candidate.is_file():
			return candidate.absolute()
	here = (Path.cwd() / path).absolute()
	if here.is_file():
		return here
	return (Path(saves) / path).absolute() if saves is not None else here


def childArgv(window: Window, *, python: str | None = None, saves: Path | None = None) -> list[str]:
	"""The command that opens `window` as its own process, exactly as `docs/config/dashboard/opening.md` says."""
	argv = [python or sys.executable, '-m', 'LevityDash', '--new-instance']
	if window.id is not None:
		argv += ['--window-id', window.id]
	argv += ['--dashboard', str(dashboardPath(window.dashboard, saves))]
	if window.screen is not None:
		# The fallback is not passed: a child reads its own entry from the file, and the flag list here is the
		# documented one a person can retype.
		argv += ['--screen-name', window.screen.name]
	if window.geometry is not None:
		argv += ['--geometry', window.geometry.spec()]
	if window.mode is not None:
		argv += ['--mode', window.mode]
	return argv


def chooseScreen(selection: Screen | None, names: Sequence[str]) -> str | None:
	"""Which screen name to open on: the exact name, then the fallback, then `primary`.

	`primary` is answered as itself; the caller maps it to the primary `QScreen`. A name that is not attached
	is *not* replaced from here: the file keeps it (see `saveFromWindow`), so the layout still says which
	monitor it was written for.
	"""
	if selection is None:
		return None
	if selection.name in names:
		return selection.name
	fallback = selection.fallback or 'primary'
	if fallback == 'primary' or fallback in names:
		return fallback
	return 'primary'


def describe(window: Window, *, pid: int | None = None, screen: str | None = None) -> dict:
	"""One window as the `workspace` control command reports it."""
	return {
		'id': window.id,
		'pid': pid,
		'screen': screen if screen is not None else (window.screen.name if window.screen is not None else None),
		'geometry': window.geometry.asDict() if window.geometry is not None else None,
		'mode': window.modeName,
	}


def dashboardTheme(path: str | Path | None) -> str | None:
	"""The theme a dashboard file names at its root, when it names one as a plain string."""
	if path is None:
		return None
	try:
		data = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
	except (OSError, yaml.YAMLError):
		return None
	if not isinstance(data, dict):
		return None
	theme = data.get('theme')
	if isinstance(theme, str):
		return theme
	if isinstance(theme, dict) and isinstance(theme.get('extends'), str):
		return theme['extends']
	return None


# ---------------------------------------------------------------------------------------------------------------------
# This process's launch: the entry it opened, where it goes, and the file it writes back to


@dataclass
class Launch:
	"""Where this process's window goes, and which workspace entry it is."""

	windowId: str | None = None
	screen: Screen | None = None
	geometry: Geometry | None = None
	mode: str | None = None

	@classmethod
	def fromWindow(cls, window: Window) -> 'Launch':
		return cls(windowId=window.id, screen=window.screen, geometry=window.geometry, mode=window.mode)

	def describe(self) -> dict:
		return {
			'id': self.windowId,
			'screen': self.screen.name if self.screen is not None else None,
			'geometry': self.geometry.asDict() if self.geometry is not None else None,
			'mode': self.mode or 'windowed',
		}

	@classmethod
	def fromFlags(cls, args) -> 'Launch | None':
		"""`--screen-name/--screen-fallback/--geometry/--mode`, for a window no file describes."""
		name = getattr(args, 'screen_name', None)
		fallback = getattr(args, 'screen_fallback', None)
		screen = Screen(name=str(name or fallback), fallback=fallback if name else None) if (name or fallback) else None
		text = getattr(args, 'geometry', None)
		geometry = parseGeometry(text) if text else None
		mode = getattr(args, 'mode', None)
		if screen is None and geometry is None and mode is None:
			return None
		return cls(windowId=getattr(args, 'window_id', None), screen=screen, geometry=geometry, mode=mode)


_ACTIVE: Workspace | None = None
_LAUNCH: Launch | None = None
_THEME: str | None = None
_CHILDREN: dict[str, subprocess.Popen] = {}


def setActive(workspace: Workspace | None) -> Workspace | None:
	global _ACTIVE
	_ACTIVE = workspace
	return workspace


def active() -> Workspace | None:
	return _ACTIVE


def setLaunch(launch: Launch | None) -> None:
	global _LAUNCH
	_LAUNCH = launch


def launch() -> Launch | None:
	return _LAUNCH


def setTheme(name: str | None) -> None:
	"""The theme the workspace file forces on every window, or None to let each window follow its own dashboard."""
	global _THEME
	_THEME = name or None


def themeName() -> str | None:
	return _THEME


def ownWindow() -> Window | None:
	"""The file entry this process opened, when there is one."""
	if _ACTIVE is None or _LAUNCH is None:
		return None
	return _ACTIVE.window(_LAUNCH.windowId)


def attachFromEnvironment() -> Workspace | None:
	"""A workspace child: it learns the file it belongs to from the environment, not from its argv."""
	text = os.environ.get(WORKSPACE_ENV)
	if not text:
		return None
	try:
		return setActive(load(Path(text)))
	except WorkspaceError as e:
		log(f'{e}')
		return None


def themeFromEnvironment() -> str | None:
	return os.environ.get(THEME_ENV) or None


def applyTheme() -> None:
	"""Force the layout's one theme, whatever this window's dashboard asks for.

	Called once the app exists and before the first dashboard loads. A window whose own dashboard names a
	different theme says so in one line and uses the layout's: never switch theme on focus, never half a
	layout in one theme and half in another.
	"""
	if not _THEME:
		return
	from LevityDash.lib.ui.colors import theme

	try:
		theme.set_override(_THEME)
	except theme.ThemeError as e:
		log(f'workspace theme {_THEME!r} could not be used: {e}')
		return
	window = ownWindow()
	own = dashboardTheme(dashboardPath(window.dashboard)) if window is not None else None
	if own and own != _THEME:
		log(f'{own} theme ignored: the workspace uses {_THEME}')


def spawn(window: Window, *, python: str | None = None, workspacePath: str | Path | None = None, saves: Path | None = None) -> subprocess.Popen:
	"""Open one window as its own process, and report it once when it exits."""
	argv = childArgv(window, python=python, saves=saves)
	env = {**os.environ}
	if workspacePath is not None:
		env[WORKSPACE_ENV] = str(Path(workspacePath).absolute())
	if _THEME:
		env[THEME_ENV] = _THEME
	process = subprocess.Popen(argv, env=env)
	# The key is the id the child's control socket will answer on: `--window-id` when there is one, else the
	# dashboard's file name, which is what the child derives it from.
	_CHILDREN[slug(window.id or Path(window.dashboard).stem)] = process
	log(f'window {window.id or window.dashboard} started as pid {process.pid}')
	_watch(process, window.id or window.dashboard)
	return process


def _watch(process: subprocess.Popen, id: str) -> None:
	"""One line when a child exits; it is never restarted, so its geometry is simply not written again."""

	def run():
		try:
			code = process.wait()
		except Exception:  # noqa: BLE001 - a watcher that cannot report must not take the thread down loudly
			return
		log(f'window {id} exited ({code}); it is not restarted')

	threading.Thread(target=run, daemon=True, name=f'workspace-{slug(str(id))}').start()


def children() -> dict[str, subprocess.Popen]:
	return dict(_CHILDREN)


def childPid(id: str | None) -> int | None:
	"""The pid of the child this process started for `id`, while it is alive."""
	process = _CHILDREN.get(slug(id or ''))
	if process is None or process.poll() is not None:
		return None
	return process.pid


def closeChildren(timeout: float = 3.0) -> list[str]:
	"""Ask every window this process started to close, and give it `timeout` seconds before leaving it.

	The children are the ones that write their own geometry back, so they are asked *before* the primary
	saves its own entry. A window that does not answer in time is left running and named in the reply.
	"""
	from .control import request, socketPath

	pending = dict(_CHILDREN)
	for id in pending:
		request({'cmd': 'close'}, path=socketPath(id=id), timeout=1.0, wait=0.05)
	deadline = time.monotonic() + timeout
	left = []
	for id, process in pending.items():
		while process.poll() is None and time.monotonic() < deadline:
			time.sleep(0.02)
		if process.poll() is None:
			left.append(id)
			log(f'window {id} did not close within {timeout:.0f}s; leaving it')
	_CHILDREN.clear()
	return left


def saveWindow(path: str | Path, id: str | None, *, screen: str | None = None, geometry: Geometry | None = None) -> bool:
	"""Write one window's `screen` and `geometry` back into the file. False when there is nothing to write.

	Only the fields given are touched: the file's windows, their order and their `dashboard` are never
	changed here.
	"""
	workspace = load(path)
	window = workspace.window(id)
	if window is None:
		log(f'{path} has no window {id!r}; its geometry was not written back')
		return False
	if screen is not None:
		window.screen = Screen(name=screen, fallback=window.screen.fallback if window.screen is not None else None)
	if geometry is not None:
		window.geometry = geometry
	write(workspace)
	if _ACTIVE is not None and _ACTIVE.path is not None and Path(_ACTIVE.path) == Path(workspace.path or path):
		setActive(workspace)
	return True


def saveFromWindow(window) -> bool:
	"""On quit: this window's current screen and geometry, back into the workspace file it came from.

	Nothing to do for a window that came from `--window` (no file) or from no workspace at all. A file that
	was deleted meanwhile is reported in one line, and nothing is written.
	"""
	if _ACTIVE is None or _ACTIVE.path is None or _LAUNCH is None or _LAUNCH.windowId is None:
		return False
	record = getattr(window, 'workspaceRecord', None)
	if record is None:
		return False
	try:
		data = record()
	except Exception as e:  # noqa: BLE001 - a write-back that fails must not hold up quitting
		log(f'this window could not describe its geometry: {e}')
		return False
	if not data:
		return False
	path = Path(_ACTIVE.path)
	if not path.is_file():
		log(f'{path} is gone; this window\'s geometry was not written back')
		return False
	try:
		return saveWindow(path, _LAUNCH.windowId, screen=data.get('screen'), geometry=data.get('geometry'))
	except WorkspaceError as e:
		log(f'{e}')
		return False


def clear() -> None:
	"""Forget everything this process knew about a workspace. For tests, and for a launch that failed."""
	global _ACTIVE, _LAUNCH, _THEME
	_ACTIVE = None
	_LAUNCH = None
	_THEME = None
	_CHILDREN.clear()


__all__ = (
	'Geometry', 'Launch', 'MODES', 'SUFFIXES', 'Screen', 'THEME_ENV', 'WORKSPACE_ENV', 'Window', 'Workspace', 'WorkspaceError',
	'active', 'applyTheme', 'attachFromEnvironment', 'childArgv', 'childPid', 'children', 'chooseScreen', 'clear',
	'closeChildren', 'dashboardPath', 'dashboardTheme', 'describe', 'directory', 'dump', 'fromPaths', 'launch', 'load',
	'log', 'ownWindow', 'parse', 'parseGeometry', 'resolve', 'saveFromWindow', 'saveWindow', 'savesDirectory', 'setActive',
	'setLaunch', 'setTheme', 'slug', 'spawn', 'themeFromEnvironment', 'themeName', 'write',
)
