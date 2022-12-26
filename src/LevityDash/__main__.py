#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import platform
import signal
import sys
from locale import LC_ALL, setlocale
from pathlib import Path
from sys import exit

from PySide2.QtWidgets import QApplication

setlocale(LC_ALL, 'en_US.UTF-8')

exit_signals = {signal.SIGINT, signal.SIGTERM}


def install_signals():

	def signalQuit(sig, frame) -> None:
		try:
			from LevityDash.lib.log import LevityLogger as log
		except ImportError:
			from logging import getLogger
			log = getLogger('LevityDash')
		log.info(f'Caught signal {sig}, exiting...')
		signalQuit.count += 1
		log.info('Closing...')
		from LevityDash.lib.log import debug
		if debug or signalQuit.count > 2:
			QApplication.instance().quit()
		if signalQuit.count > 4:
			os._exit(1)

	signalQuit.count = 0

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

	print(f'Starting LevityDash {LevityDashboard.__version__} on {platform.system()}')

	install_signals()

	LevityDashboard.init()
	LevityDashboard.app.processEvents()

	LevityDashboard.lib.plugins.load_all()

	LevityDashboard.app.start()


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
