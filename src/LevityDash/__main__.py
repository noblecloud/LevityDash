#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import platform
import signal
import sys
import time
from locale import LC_ALL, setlocale
from pathlib import Path
from sys import exit

from PySide6.QtWidgets import QApplication

from qolkit.hotkeys import CTRL_R, HotkeyListener, restart_process

setlocale(LC_ALL, 'en_US.UTF-8')

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


def main():

	from LevityDash import LevityDashboard

	LevityDashboard.parse_args()

	if LevityDashboard.parsed_args.reset_config:
		reset_config()

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
