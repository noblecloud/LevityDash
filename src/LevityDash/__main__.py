#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import platform

import sys
from locale import LC_ALL, setlocale
import signal
from pathlib import Path

from PySide2.QtWidgets import QApplication
from sys import exit, path as PYTHONPATH
import builtins

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


APP_STATE = 'LOADING'

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

	try:
		from LevityDash import __version__
	except ImportError:
		cwd = Path()
		local_module = cwd / 'src/LevityDash/__main__.py'
		if local_module.exists():
			print('Running from source')
			os.chdir((cwd / 'src').as_posix())
			PYTHONPATH.append(os.curdir)

	main()
