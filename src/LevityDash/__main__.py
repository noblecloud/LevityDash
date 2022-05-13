#!/usr/bin/env python

import os
import signal
import sys

try:
	import PySide2
except ImportError:
	sys.path.append('/usr/lib/python3/dist-packages')
	import PySide2

import asyncio
import qasync
from pathlib import Path
from rich.traceback import install

install(show_locals=False, width=120, )
qasync.logger.setLevel('ERROR')

os.environ['WU_CONFIG_PATH'] = f'{Path.home()}/.config/levity/config.ini'


def signalQuit(sig, frame):
	if sig == signal.SIGINT:
		print('Closing...')
		qasync.QApplication.instance().quit()
		remainingFutures = len(asyncio.tasks.all_tasks(asyncio.get_event_loop()))
		print(f'Waiting for {remainingFutures} tasks to finish...')


signal.signal(signal.SIGINT, signalQuit)


def init_app():
	from PySide2.QtCore import Qt
	from PySide2.QtGui import QIcon
	# QApplication.setAttribute(Qt.AA_UseDesktopOpenGL, True)
	# QApplication.setAttribute(Qt.AA_UseOpenGLES, True)
	qasync.QApplication.setAttribute(Qt.AA_DontUseNativeMenuBar, False)
	# QApplication.setAttribute(Qt.AA_CompressHighFrequencyEvents, False)
	path = Path(__file__).parent.joinpath('lib', 'ui', 'icon.icns')
	icon = QIcon(path.as_posix())
	qasync.QApplication.setWindowIcon(icon)
	qasync.QApplication.setApplicationName('LevityDash')
	qasync.QApplication.setApplicationDisplayName('LevityDash')


async def main():
	from functools import partial
	import asyncio
	import LevityDash.lib as lib

	init_app()

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
# except KeyboardInterrupt:
# 	print('####### KeyboardInterrupt #######')
# 	asyncio.get_event_loop().stop()
# 	sys.exit(0)
# except Exception as e:
# 	print(e)
# 	asyncio.get_event_loop().stop()
# 	raise e
# finally:
# 	print('####### finally #######')
# 	asyncio.get_event_loop().stop()
# 	sys.exit(0)
