import json
import platform

import requests
from datetime import datetime

import logging
import sys

BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)

RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"


def formatter_message(message, use_color=True):
	if use_color:
		message = message.replace("$RESET", RESET_SEQ).replace("$BOLD", BOLD_SEQ)
	else:
		message = message.replace("$RESET", "").replace("$BOLD", "")
	return message


def sendPushoverMessage(title, message):
	requests.post(
		url="https://api.pushover.net/1/messages.json",
		headers={
			"Content-Type": "application/json; charset=utf-8",
		},
		data=json.dumps({
			"token":   "aa8117x992f39wwn81q2vmmmpc5xh6",
			"user":    "u4JC51U1StTeAyqUbrnJajX21nyrUf",
			"title":   f"{platform.node()}: {title}",
			"message": message
		}),
		timeout=5
	)


class DuplicateFilter(logging.Filter):
	def filter(self, record):
		# add other fields if you need more granular comparison, depends on your app
		current_log = (record.module, record.levelno, record.msg)
		if current_log != getattr(self, "last_log", None):
			self.last_log = current_log
			return True
		return False


COLORS = {
	'WARNING':  YELLOW,
	'INFO':     WHITE,
	'DEBUG':    BLUE,
	'CRITICAL': YELLOW,
	'ERROR':    RED
}

COLOR_SEQs = {
	'RED':     "\033[1;31m",
	'GREEN':   "\033[1;32m",
	'YELLOW':  "\033[1;33m",
	'BLUE':    "\033[1;34m",
	'MAGENTA': "\033[1;35m",
	'CYAN':    "\033[1;36m",
	'WHITE':   "\033[1;39m",
}


class LogFormatter(logging.Formatter):
	LOGGERNAME = "$BOLD%(name)s$RESET"
	LEVEL = "$BOLD%(levelname)-10s$RESET"
	FILE = "$BOLD%(filename)s:%(lineno)s$RESET"
	FUNC = "$BOLD%(funcName)s$RESET"
	ARGS = "$BOLD%(args)s$RESET"
	FIRST = f"[{LOGGERNAME}.{FUNC}{ARGS}][{LEVEL}]\t\t\t"
	FORMAT = f"{FIRST}\t%(message)s"

	def __init__(self):
		logging.Formatter.__init__(self, '%(message)s')

	def format(self, record):
		levelname = record.levelname
		levelname_color = COLOR_SEQ%(30 + COLORS[levelname]) + levelname + RESET_SEQ
		record.levelname = levelname_color
		return logging.Formatter.format(self, record)

	def formatMessage(self, record):
		time = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
		funcName = record.funcName
		if funcName.startswith("_"):
			func = ""
		else:
			func = f'.{funcName}{record.args}'
		name = f'{COLOR_SEQs["WHITE"]}[{BOLD_SEQ}{record.name}{func}]{RESET_SEQ}'
		fileLocation = f'{COLOR_SEQs["CYAN"]}[{record.filename}:{record.lineno}]{RESET_SEQ}'
		level = f'[{BOLD_SEQ}{record.levelname}{RESET_SEQ}]'
		return f'[{time:<8}]{name:<60}{fileLocation}{level}\t{record.msg}'


class Logger(logging.Logger):
	VERBOS = 5

	def __init__(self, name):
		logging.Logger.__init__(self, name, logging.WARNING)
		color_formatter = LogFormatter()
		console = logging.StreamHandler()
		console.setFormatter(color_formatter)
		self.addHandler(console)
		self.propagate = False
		self.addFilter(DuplicateFilter())
		return

	def verboseDebug(self, msg, *args, **kwargs):
		if self.isEnabledFor(Logger.VERBOS):
			self._log(Logger.VERBOS, msg, args, **kwargs)


logging.setLoggerClass(Logger)
debug = sys.gettrace()
logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)

weatherUnitsLog = logging.getLogger('WeatherUnits')
weatherUnitsLogUtils = logging.getLogger('WeatherUnits.utils')
weatherUnitsLogUtils.setLevel(logging.INFO)
weatherUnitsLog.setLevel(logging.INFO)
# # weatherUnitsLog.getChild('WeatherUnits').setLevel(logging.DEBUG)
urllog = logging.getLogger('urllib3')
urllogPool = logging.getLogger('urllib3.connectionpool')
urllog.setLevel(logging.ERROR)
urllogPool.setLevel(logging.ERROR)
guiLog = logging.getLogger('Display')
apiLog = logging.getLogger('API')
apiLog.setLevel(logging.INFO)
