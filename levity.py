#!/usr/bin/env python
import os
import signal
import sys

import asyncio
import qasync
import shiboken2
from pathlib import Path
from rich.traceback import install

install(show_locals=True, width=120)
qasync.logger.setLevel('ERROR')

os.environ['WU_CONFIG_PATH'] = f'{Path.home()}/.config/levity/config.ini'

signal.signal(signal.SIGINT, signal.SIG_DFL)


def init_app():
	from PySide2.QtCore import Qt
	from PySide2.QtGui import QIcon
	# QApplication.setAttribute(Qt.AA_UseDesktopOpenGL, True)
	# QApplication.setAttribute(Qt.AA_UseOpenGLES, True)
	qasync.QApplication.setAttribute(Qt.AA_DontUseNativeMenuBar, False)
	# QApplication.setAttribute(Qt.AA_CompressHighFrequencyEvents, False)

	icon = QIcon(Path('src/ui/icon.png').as_posix())
	qasync.QApplication.setWindowIcon(icon)
	qasync.QApplication.setApplicationName('LevityDash')


async def main():
	from functools import partial
	import asyncio
	import src

	init_app()

	window = src.ui.frontends.PySide.LevityMainWindow()

	def close_future(future, loop):
		print('####### close_future #######')
		loop.call_later(10, future.cancel)
		future.cancel()

	loop = asyncio.get_event_loop()
	future = asyncio.Future()
	if hasattr(qasync.QApplication.instance(), "aboutToQuit"):
		getattr(qasync.QApplication.instance(), "aboutToQuit").connect(
			partial(close_future, future, loop)
		)
	src.plugins.start()

	window.show()
	await future
	return True


if __name__ == '__main__':
	try:
		qasync.run(main())
	except asyncio.exceptions.CancelledError:
		sys.exit(0)
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
