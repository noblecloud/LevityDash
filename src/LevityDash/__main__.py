#!/usr/bin/env python
from platform import system
from signal import SIGINT, signal

from sys import path, exit

from locale import setlocale, LC_ALL

setlocale(LC_ALL, 'en_US.UTF-8')

try:
	import PySide2
except ImportError:
	path.append('/usr/lib/python3/dist-packages')
	import PySide2

import asyncio
import qasync
from pathlib import Path

qasync.logger.setLevel('ERROR')


def init_app():
	from PySide2.QtGui import QIcon
	iconPath = Path(__file__).parent.joinpath('lib', 'ui', 'icon.icns')
	icon = QIcon(iconPath.as_posix())
	qasync.QApplication.setWindowIcon(icon)
	qasync.QApplication.setApplicationName('LevityDash')
	qasync.QApplication.setApplicationDisplayName('LevityDash')
	qasync.QApplication.setApplicationVersion('0.1.0-beta.8')
	qasync.QApplication.setOrganizationName('LevityDash')
	qasync.QApplication.setOrganizationDomain('LevityDash.app')


async def main():
	from functools import partial
	import asyncio
	init_app()

	# Secret key for clearing config.
	from PySide2.QtCore import Qt
	if qasync.QApplication.queryKeyboardModifiers() & (Qt.ShiftModifier | Qt.AltModifier):
		print('Removing config in...', end='')
		for i in range(5, 0, -1):
			print(i, end=' ')
			await asyncio.sleep(1)
			if not qasync.QApplication.queryKeyboardModifiers() & (Qt.ShiftModifier | Qt.AltModifier):
				print('Cancelled')
				break
		if qasync.QApplication.queryKeyboardModifiers() & (Qt.ShiftModifier | Qt.AltModifier):
			from shutil import rmtree
			from LevityDash import __dirs__
			configDir = Path(__dirs__.user_config_dir)
			rmtree(configDir.as_posix(), ignore_errors=True)
			print('Config cleared!')
		else:
			print('Config not cleared')

	import LevityDash.lib as lib

	window = lib.ui.LevityMainWindow()

	def signalQuit(sig, frame):
		signalQuit.count += 1
		if sig == SIGINT:
			print('Closing...')
			from LevityDash.lib.log import debug
			if debug or signalQuit.count > 1:
				quit()
			qasync.QApplication.instance().quit()
			remainingFutures = len(asyncio.tasks.all_tasks(asyncio.get_event_loop()))
			print(f'Waiting for {remainingFutures} tasks to finish...')

	signalQuit.count = 0

	signal(SIGINT, signalQuit)

	def close_future(future, loop):
		loop.call_later(10, future.cancel)
		future.cancel()

	loop = asyncio.get_event_loop()

	def stopAndDisconnect():
		lib.plugins.stop()
		if (aboutToQuit_ := getattr(qasync.QApplication.instance(), "aboutToQuit", None)) is not None:
			try:
				aboutToQuit_.disconnect(stopAndDisconnect)
			except Exception as e:
				print(e)

	future = asyncio.Future()
	if (aboutToQuit := getattr(qasync.QApplication.instance(), "aboutToQuit", None)) is not None:
		aboutToQuit.connect(stopAndDisconnect)
		aboutToQuit.connect(partial(close_future, future, loop))
	lib.plugins.start()

	window.show()
	await future
	return True


def run():
	try:
		qasync.run(main())
	except asyncio.exceptions.CancelledError:
		exit(0)


if __name__ == '__main__':
	run()
