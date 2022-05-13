import os
import shutil
from collections import deque
from sys import argv, gettrace

import logging

from rich.console import Console
from rich.logging import RichHandler


class _LevityLogger(logging.Logger):
	VERBOS = 5

	class DuplicateFilter(logging.Filter):
		previousLogs = deque([[] for _ in range(5)], maxlen=5)

		def filter(self, record):
			current_log = (record.module, record.levelno, record.msg)
			if current_log in self.previousLogs:
				return False
			self.previousLogs.append(current_log)
			return True

	def __init__(self, name):
		logging.Logger.__init__(self, name, logging.WARNING)
		columns = shutil.get_terminal_size((160, 20)).columns
		console = Console(soft_wrap=True, width=columns, record=False, log_time_format="%H:%M:%S")
		handler = RichHandler(

			console=console,
			log_time_format="%H:%M:%S"

		)
		self.addHandler(handler)
		self.propagate = False
		self.addFilter(_LevityLogger.DuplicateFilter())

	def verboseDebug(self, msg, *args, **kwargs):
		if self.isEnabledFor(_LevityLogger.VERBOS):
			self._log(_LevityLogger.VERBOS, msg, args, **kwargs)

	def getChild(self, name):
		child = super().getChild(name)
		child.setLevel(self.level)
		return child


logging.setLoggerClass(_LevityLogger)
debug = bool(int(os.environ.get('DEBUG', 0))) or bool(gettrace()) or '--debug' in argv
logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)

LevityLogger = logging.getLogger("Levity")
LevityLogger.setLevel(logging.DEBUG if debug else logging.INFO)
LevityLogger.info(f"Log set to {logging.getLevelName(LevityLogger.level)}")

weatherUnitsLog = logging.getLogger('WeatherUnits')
weatherUnitsLogUtils = weatherUnitsLog.getChild('utils')
weatherUnitsLogUtils.setLevel(logging.INFO)
weatherUnitsLog.setLevel(logging.INFO)

urllog = logging.getLogger('urllib3')
urllogPool = logging.getLogger('urllib3.connectionpool')
urllog.setLevel(logging.ERROR)
urllogPool.setLevel(logging.ERROR)

LevityGUILog = LevityLogger.getChild('GUI')
LevityPluginLog = LevityLogger.getChild('Plugins')
# LevityPluginLog.setLevel(logging.INFO)

__all__ = ['LevityLogger', 'LevityPluginLog', 'LevityGUILog']
