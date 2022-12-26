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

	if LevityDashboard.isCompiled:
		from os import chdir
		chdir(sys._MEIPASS)

	print(f'Starting LevityDash {LevityDashboard.__version__} on {platform.system()}')

	install_signals()

	LevityDashboard.init()
	LevityDashboard.app.processEvents()

	LevityDashboard.lib.plugins.load_all()

	LevityDashboard.app.start()


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
