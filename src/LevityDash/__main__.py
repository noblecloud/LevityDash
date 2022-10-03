#!/usr/bin/env python
from locale import LC_ALL, setlocale
from signal import SIGINT, signal, SIGQUIT, SIGTERM

from sys import exit, path

setlocale(LC_ALL, 'en_US.UTF-8')

os.environ['LEVITY_DATETIME_NO_ZERO_CHAR'] = '#' if platform.system() == 'Windows' else '-'

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

	log = lib.log.LevityLogger

	window = lib.ui.LevityMainWindow()

	def signalQuit(sig, frame):
		log.info(f'Caught signal {sig}, exiting...')
		signalQuit.count += 1
		if sig in (SIGINT, SIGTERM, SIGQUIT):
			log.info('Closing...')
			from LevityDash.lib.log import debug
			if debug or signalQuit.count > 2:
				qasync.QApplication.instance().quit()
			remainingFutures = len(asyncio.tasks.all_tasks(asyncio.get_event_loop()))
			log.info(f'Waiting for {remainingFutures} tasks to finish...')

	signalQuit.count = 0

	signal(SIGINT, signalQuit)
	signal(SIGTERM, signalQuit)
	signal(SIGQUIT, signalQuit)

	def close_future(future, loop):
		loop.call_later(10, future.cancel)
		future.cancel()

	def handel_exception(loop_, context):
		from LevityDash.lib.log import LevityLogger

		LevityLogger.exception(context["exception"])

	loop = asyncio.get_event_loop()
	loop.set_exception_handler(handel_exception)

	def stopAndDisconnect():
		lib.plugins.stop()
		if (aboutToQuit_ := getattr(qasync.QApplication.instance(), "aboutToQuit", None)) is not None:
			lib.utils.disconnectSignal(aboutToQuit_, stopAndDisconnect)
			lib.utils.disconnectSignal(aboutToQuit_, lib.utils.Pool.shutdown_all)

	future = asyncio.Future()
	if (aboutToQuit := getattr(qasync.QApplication.instance(), "aboutToQuit", None)) is not None:
		lib.utils.connectSignal(aboutToQuit, stopAndDisconnect)
		lib.utils.connectSignal(aboutToQuit, lib.utils.Pool.shutdown_all)
		lib.utils.connectSignal(aboutToQuit, partial(close_future, future, loop))
	lib.plugins.start()

	await future
	return True


def run():
	try:
		qasync.run(main())
	except asyncio.exceptions.CancelledError:
		exit(0)


if __name__ == '__main__':
	run()
