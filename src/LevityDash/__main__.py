#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import platform
import signal
import sys
import time
from locale import LC_ALL, Error as LocaleError, setlocale
from pathlib import Path
from sys import exit

from PySide6.QtWidgets import QApplication

from qolkit.hotkeys import CTRL_R, HotkeyListener, restart_process

try:
	setlocale(LC_ALL, 'en_US.UTF-8')
except LocaleError:
	# Hosts without the en_US locale (minimal Linux images, CI) keep the C locale.
	pass

#: Whether the Ctrl+R hotkey is actually listening - False when stdin is not a
#: TTY, in which case the Ctrl+C hint should not advertise it.
_hotkeys_active = False

exit_signals = {signal.SIGINT, signal.SIGTERM}

#: Seconds a first Ctrl+C stays 'armed' before the count resets.
CONFIRM_QUIT_WINDOW = 3.0

#: Set by the Ctrl+R hotkey; consumed by main() once the Qt loop has returned.
#: Restarting from the reader thread would mean exec()ing out from under a live
#: event loop, so the flag is deferred to a clean exit instead.
_restart_requested = False


def install_signals():

	def signalQuit(sig, frame) -> None:
		try:
			from LevityDash.lib.log import LevityLogger as log
		except ImportError:
			from logging import getLogger
			log = getLogger('LevityDash')
		# Confirm-to-quit: one press warns, a second within the window quits.
		# The window is a COOLDOWN, not a running total - an interrupt hours
		# after an earlier one starts over rather than silently counting as
		# the second half of a confirmation nobody remembers giving.
		#
		# This used to read `if debug or signalQuit.count > 2`, and `debug` is
		# False in a normal run, so it took THREE presses and looked broken.
		now = time.monotonic()
		if now - signalQuit.last > CONFIRM_QUIT_WINDOW:
			signalQuit.count = 0
		signalQuit.last = now
		signalQuit.count += 1

		if signalQuit.count == 1:
			# stderr, not the logger: this has to be visible immediately in the
			# terminal the user is pressing Ctrl+C in.
			hint = f'\nPress Ctrl+C again within {CONFIRM_QUIT_WINDOW:.0f}s to quit LevityDash'
			hint += ', or Ctrl+R to restart.' if _hotkeys_active else '.'
			print(hint, file=sys.stderr, flush=True)
			return

		log.info(f'Caught signal {sig}, closing...')
		if signalQuit.count == 2:
			QApplication.instance().quit()
		elif signalQuit.count == 3:
			# The event loop is not coming back - close the windows out from
			# under it so exec_() returns.
			log.warning('Still closing - forcing the window shut')
			for window in QApplication.instance().topLevelWindows():
				window.close()
		else:
			log.warning('Exiting immediately')
			os._exit(1)

	def requestRestart() -> None:
		# Runs on the hotkey reader thread. Only armed inside the same window a
		# second Ctrl+C would quit in, so Ctrl+R is a *substitute* for that
		# second press rather than a always-live restart key.
		if signalQuit.count < 1 or (time.monotonic() - signalQuit.last) > CONFIRM_QUIT_WINDOW:
			return
		global _restart_requested
		_restart_requested = True
		print('\nRestarting LevityDash...', file=sys.stderr, flush=True)
		QApplication.instance().quit()

	signalQuit.count = 0
	signalQuit.last = 0.0

	global _hotkeys_active
	listener = HotkeyListener()
	listener.bind(CTRL_R, requestRestart)
	_hotkeys_active = listener.start()

	if platform.system() != 'Windows':
		os.nice(10)
		exit_signals.add(signal.SIGQUIT)

	for s in exit_signals:
		signal.signal(s, signalQuit)


#: Returned by `_handOffOrResolveDashboard` when a running window took the file and this process is done.
_HANDED_OFF = object()

#: The exit statuses this file returns itself, matching `control.EXIT_CODES` (a launch error is not a reply).
_NOT_FOUND = 3
_BAD_REQUEST = 4


def _fail(message: str, code: int) -> None:
	"""Report a launch this process will not carry out, and exit with the status the protocol would use."""
	print(f'levitydash: {message}', file=sys.stderr)
	raise SystemExit(code)


def _resolveDashboard(dashboard):
	"""Resolve `--dashboard PATH` against this process's working directory; None when no flag was given.

	Resolved here, not in the running window: that window has its own working directory.
	"""
	text = dashboard.parsed_args.dashboard
	if not text:
		return None
	from LevityDash.lib.ui.frontends.PySide.control import resolveDashboardArgument

	path = resolveDashboardArgument(text)
	if not path.is_file():
		print(f'levitydash: --dashboard {path} is not a file', file=sys.stderr)
		raise SystemExit(3)  # not_found
	return path


def _handOffOrResolveDashboard(dashboard):
	"""Resolve `--dashboard PATH`, handing it to a running window first.

	Returns the path when this process has to show it itself, None when no `--dashboard` was given (the
	configured dashboard loads, as before), and `_HANDED_OFF` when a running window took the file and this
	process should exit instead of starting a second one.
	"""
	path = _resolveDashboard(dashboard)
	if path is None:
		return None
	from LevityDash.lib.ui.frontends.PySide.control import exitCode, handOff

	reply = handOff({'cmd': 'open', 'dashboard': str(path), 'window': 'current'})
	if reply is None:
		return path
	if reply.get('ok'):
		print(f"levitydash: {path.name} is showing in the running window ({reply.get('window')})")
		return _HANDED_OFF
	failure = reply.get('error')
	message = failure.get('message') if isinstance(failure, dict) else failure
	print(f'levitydash: the running window refused {path}: {message}', file=sys.stderr)
	raise SystemExit(exitCode(reply))


def _slug(text: str) -> str:
	"""A socket-safe name: lowercase, letters and digits, single dashes, short enough for an AF_UNIX path.

	The implementation is `workspace.slug`, so the id a workspace file writes is the id its child's socket
	carries without either side slugging it differently.
	"""
	from LevityDash.lib.ui.frontends.PySide.workspace import slug

	return slug(text)


def _configuredDashboard():
	"""`[Display] dashboard`, read without starting anything. None when it cannot be read."""
	try:
		from LevityDash.lib.config import userConfig
		return userConfig.dashboardPath
	except Exception:  # noqa: BLE001 - an unreadable config is not a reason to fail a launch
		return None


def _windowId(dashboard, windowId: str | None = None) -> str:
	"""The id a second window's socket carries: `--window-id`, else the dashboard's file name, else `w<pid>`."""
	if windowId:
		return _slug(windowId)
	for candidate in (dashboard, _configuredDashboard()):
		if candidate is not None and (stem := Path(str(candidate)).stem):
			return _slug(stem)
	return f'w{os.getpid()}'


def _liveMode() -> bool:
	"""Whether the plugins run in this process (mode=live). Nothing readable means live: the default."""
	try:
		from LevityDash.lib.plugins.dispatcher import backend_mode
		return backend_mode() == 'live'
	except Exception:  # noqa: BLE001 - a warning is better guessed than skipped
		return True


def warnSecondInstance(socketPath: str) -> None:
	"""The one line a `--new-instance` window prints in mode=live: two of everything, and that is allowed."""
	message = (
		f'--new-instance: a second window on {socketPath}. In mode=live it loads the plugins a second time and '
		f'polls every API twice; mode=remote shares an already-running backend instead.'
	)
	print(f'levitydash: {message}', file=sys.stderr, flush=True)


def _workspaceText(args) -> str | None:
	"""`--workspace`, else `[Display] workspace` — read only when no other flag names what to show."""
	if text := getattr(args, 'workspace', None):
		return str(text)
	if getattr(args, 'window', None) or getattr(args, 'dashboard', None):
		# A flag is an explicit answer to "what do I show"; the configured workspace is only the default.
		return None
	try:
		from LevityDash.lib.config import userConfig
		return userConfig.get('Display', 'workspace', fallback=None) or None
	except Exception:  # noqa: BLE001 - an unreadable config is not a reason to fail a launch
		return None


def _resolveWorkspace(dashboard):
	"""The layout this launch opens, or None when it is an ordinary one-window launch.

	`--workspace` (or `[Display] workspace`) is a file of windows; repeated `--window` is the same thing built
	in memory. Both at once is refused: one file and a list of paths cannot both be the layout.
	"""
	from LevityDash.lib.ui.frontends.PySide import workspace

	args = dashboard.parsed_args
	if getattr(args, 'workspace', None) and getattr(args, 'window', None):
		_fail('--workspace and --window cannot be used together: a workspace file already names its windows', _BAD_REQUEST)
	if paths := getattr(args, 'window', None):
		from LevityDash.lib.ui.frontends.PySide.control import resolveDashboardArgument

		try:
			return workspace.fromPaths([resolveDashboardArgument(text) for text in paths])
		except workspace.WorkspaceError as error:
			_fail(f'--window: {error}', _BAD_REQUEST)
	text = _workspaceText(args)
	if not text:
		return None
	path = workspace.resolve(text)
	if not path.is_file():
		_fail(f'--workspace {text!r}: {path} is not a file', _NOT_FOUND)
	try:
		return workspace.load(path)
	except workspace.WorkspaceError as error:
		_fail(f'--workspace {text!r}: {error}', _BAD_REQUEST)


def _openWorkspace(active) -> None:
	"""Window 1 in this process, one child per remaining window, and the one theme the layout uses.

	`[Display] dashboard` is not read and not written: a workspace is what this run shows.
	"""
	from LevityDash import LevityDashboard
	from LevityDash.lib.ui.frontends.PySide import workspace

	first = active.windows[0]
	workspace.setActive(active)
	workspace.setLaunch(workspace.Launch.fromWindow(first))
	# Only a theme the file names is forced on every window. Without one, each window is a process of its own and
	# resolves the theme its own dashboard asks for: forcing window 1's theme on the others broke any board that
	# writes a token only its own theme defines (`$cloud`).
	workspace.setTheme(active.theme)
	LevityDashboard.dashboardOverride = workspace.dashboardPath(first.dashboard)
	rest = active.windows[1:]
	print(f'levitydash: workspace {active.name!r}: window {first.id!r} here, {len(rest)} more window(s)', flush=True)
	for window in rest:
		workspace.spawn(window, workspacePath=active.path)


def _workspaceEntry(args) -> None:
	"""A workspace child: the file's entry for its id, or what its flags say when the file has none."""
	from LevityDash.lib.ui.frontends.PySide import workspace

	active = workspace.active()
	entry = active.window(getattr(args, 'window_id', None)) if active is not None else None
	plan = workspace.Launch.fromWindow(entry) if entry is not None else workspace.Launch.fromFlags(args)
	if plan is not None:
		workspace.setLaunch(plan)


def main():

	from LevityDash import LevityDashboard

	LevityDashboard.parse_args()
	args = LevityDashboard.parsed_args

	if args.reset_config:
		reset_config()

	from LevityDash.lib.ui.frontends.PySide import workspace

	if workspace.attachFromEnvironment() is not None:
		# A workspace child: one window of a file that is already open, its entry named by --window-id.
		LevityDashboard.dashboardOverride = _resolveDashboard(LevityDashboard)
		workspace.setTheme(workspace.themeFromEnvironment())
		_workspaceEntry(args)
	elif (active := _resolveWorkspace(LevityDashboard)) is not None:
		# A workspace is a layout, not a file to hand to a running window: it opens here.
		_openWorkspace(active)
	elif args.new_instance:
		# No handoff: this process *is* the second window, so `--dashboard` is a file it shows itself.
		LevityDashboard.dashboardOverride = _resolveDashboard(LevityDashboard)
		workspace.setLaunch(workspace.Launch.fromFlags(args))
	else:
		dashboard = _handOffOrResolveDashboard(LevityDashboard)
		if dashboard is _HANDED_OFF:
			return
		LevityDashboard.dashboardOverride = dashboard
		plan = workspace.Launch.fromFlags(args)
		if plan is not None:
			workspace.setLaunch(plan)

	if args.new_instance:
		from LevityDash.lib.ui.frontends.PySide.control import setSocketId, socketId, socketPath
		# The window that is already running keeps the primary socket; this one answers on its own.
		setSocketId(_windowId(LevityDashboard.dashboardOverride, args.window_id))
		if (plan := workspace.launch()) is not None:
			# The id a client writes is the id this window answers to, however the file or the flag spelled it.
			plan.windowId = socketId() or plan.windowId
		if _liveMode():
			warnSecondInstance(socketPath())
		else:
			print(f'levitydash: second window, control socket {socketPath()}')

	# git describe (when run from source) is a complete version string
	# (tag-commitsSince-gHash[-dirty]); fall back to the static version otherwise.
	_ver = LevityDashboard.revision or LevityDashboard.__version__
	print(f'Starting LevityDash {_ver} on {platform.system()}')

	install_signals()

	LevityDashboard.init()
	LevityDashboard.app: QApplication
	LevityDashboard.app.processEvents()

	LevityDashboard.plugins.load_all()

	LevityDashboard.app.start()

	if _restart_requested:
		restart_process()


def reset_config():
	from LevityDash import LevityDashboard
	from rich import prompt
	import shutil
	config_dir = Path(LevityDashboard.paths.config)

	if platform.system() != 'Windows':
		user_home = Path.home()
		if config_dir.is_relative_to(user_home):
			config_dir = config_dir.relative_to(user_home)
			config_dir = f'~/{config_dir}'
	else:
		app_data_path = Path("%APPDATA%")
		if config_dir.is_relative_to(app_data_path):
			config_dir = config_dir.relative_to(app_data_path)
			config_dir = f'%APPDATA%\\{config_dir}'
	if not isinstance(config_dir, Path):
		config_dir = Path(config_dir)

	prompt_message = f"""
[bold][underline][green]LevityDash Configuration Reset[/underline][/bold][/green]
	
[bold red]WARNING[/bold red]: This will delete all your configuration files and reset them to default.
Are you sure you want to continue? [bold red]This cannot be undone![/bold red]

Config Directory: [bold blue]{config_dir}[/bold blue]
"""

	if prompt.Confirm.ask(
		prompt_message,
		default=False,
	):
		print(f'Removing {config_dir}...')
		shutil.rmtree(config_dir)
		if config_dir.exists():
			print(f'Failed to remove {config_dir}')
		else:
			print('Config directory reset!')
	else:
		print('\nConfig reset canceled...')

	if not prompt.Confirm.ask(
		'Continue to [bold][green]LevityDash[/bold][/green]?',
		default=True,
	):
		exit(0)


if __name__ == '__main__':

	if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
		from os import chdir
		from multiprocessing import freeze_support
		freeze_support()
		chdir(sys._MEIPASS)

	try:
		from LevityDash import __version__
	except ImportError:

		from sys import path
		path.append(os.curdir)

		cwd = Path()
		local_module = cwd / 'src/LevityDash/__main__.py'
		if local_module.exists():
			print('Running from source')
			os.chdir((cwd / 'src').as_posix())

		try:
			from LevityDash import __version__
		except ImportError:
			print('Failed to import LevityDash')
			print(f'Current working directory: {cwd.absolute()}')
			print(f'Python path: {path}')
			exit(1)

	main()
