#!/usr/bin/env python

import signal
import sys

try:
	import PySide2
except ImportError:
	sys.path.append('/usr/lib/python3/dist-packages')
	import PySide2

# These attributes have to be set before the application is created.
from PySide2.QtWidgets import QApplication
from PySide2.QtCore import Qt

QApplication.setAttribute(Qt.AA_UseDesktopOpenGL, True)
QApplication.setAttribute(Qt.AA_UseOpenGLES, True)
QApplication.setAttribute(Qt.AA_DontUseNativeMenuBar, False)

import asyncio
import qasync
from pathlib import Path

qasync.logger.setLevel('ERROR')


def signalQuit(sig, frame):
	if sig == signal.SIGINT:
		print('Closing...')
		qasync.QApplication.instance().quit()
		remainingFutures = len(asyncio.tasks.all_tasks(asyncio.get_event_loop()))
		print(f'Waiting for {remainingFutures} tasks to finish...')


signal.signal(signal.SIGINT, signalQuit)


def init_app():
	from PySide2.QtGui import QIcon
	path = Path(__file__).parent.joinpath('lib', 'ui', 'icon.icns')
	icon = QIcon(path.as_posix())
	qasync.QApplication.setWindowIcon(icon)
	qasync.QApplication.setApplicationName('LevityDash')
	qasync.QApplication.setApplicationDisplayName('LevityDash')


async def main():
	from functools import partial
	import asyncio
	init_app()
	import LevityDash.lib as lib

	window = lib.ui.frontends.PySide.LevityMainWindow()

	def close_future(future, loop):
		loop.call_later(10, future.cancel)
		future.cancel()

	loop = asyncio.get_event_loop()
	future = asyncio.Future()
	if hasattr(qasync.QApplication.instance(), "aboutToQuit"):
		getattr(qasync.QApplication.instance(), "aboutToQuit").connect(
			partial(close_future, future, loop)
		)
	lib.plugins.start()

	window.show()
	await future
	return True


def run():
	try:
		qasync.run(main())
	except asyncio.exceptions.CancelledError:
		sys.exit(0)


if __name__ == '__main__':
	run()
