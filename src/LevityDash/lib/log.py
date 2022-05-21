import asyncio
import os
import shutil
import sys
import webbrowser
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from re import findall, search
from sys import argv, gettrace

import logging
from typing import ClassVar

logging.addLevelName(5, "VERBOSE")
from LevityDash import __lib__
import qasync
from appdirs import AppDirs
from rich.console import Console
from rich.logging import RichHandler


def levelFilter(level: int):
	def filter(record):
		return record.levelno >= level

	return filter


class _LevityLogger(logging.Logger):
	__config__: ClassVar[dict]
	logDir: ClassVar[Path]
	errorLogDir: ClassVar[Path]
	logPath: ClassVar[Path]

	fileHandler: ClassVar[RichHandler]
	consoleHandler: ClassVar[RichHandler]

	LOGGING_DEFAULT_CONFIG: ClassVar[dict] = {
		"Logging": {
			"level":           "INFO",
			"maxLogSize":      "50mb",
			"maxErrorLogAge":  '30 days',
			"maxErrorLogSize": "200mb",
			"logFileFormat":   "%%Y-%%m-%%d_%%H-%%M-%%S",
			"logFileWidth":    200,
			"prettyErrors":    True,
		}
	}

	class DuplicateFilter(logging.Filter):
		previousLogs = deque([[] for _ in range(5)], maxlen=5)

		def filter(self, record):
			if (path := record.pathname).endswith("__init__.py"):
				record.pathname = path.replace("__init__.py", "")
			p = Path(record.pathname)
			if p.is_relative_to(libPath := Path(__lib__).parent):
				record.pathname = str(p.relative_to(libPath)).replace("/", ".").rstrip(".py")
			else:
				record.pathname = str(p)
			current_log = (record.module, record.levelno, record.msg)
			if current_log in self.previousLogs:
				return False
			self.previousLogs.append(current_log)
			return True

	duplicateFilter: ClassVar[DuplicateFilter] = DuplicateFilter()

	def __init__(self, name):
		from LevityDash.lib.config import userConfig
		super().__init__(name, level=1)
		self.addFilter(_LevityLogger.duplicateFilter)

		if not userConfig.has_section("Logging"):
			userConfig.read_dict(self.LOGGING_DEFAULT_CONFIG)
			userConfig.save()

		if not hasattr(self, "__config__"):
			_LevityLogger.__config__ = userConfig["Logging"]
			self.initClassVars()

	def initClassVars(self) -> None:
		_LevityLogger.logDir = Path(AppDirs("LevityDash", "LevityDash").user_log_dir)
		_LevityLogger.errorLogDir = self.logDir.joinpath("prettyErrors")
		self.__ensureFoldersExists()

		columns = shutil.get_terminal_size((160, 20)).columns
		fileColumns = int(self.__config__['logFileWidth'])
		consoleFile = Console(
			tab_size=2,
			soft_wrap=True,
			width=fileColumns,
			record=True,
			file=self.getFile(),
		)
		fileHandler = RichHandler(
			console=consoleFile,
			log_time_format="D%j|%H:%M:%S",
			rich_tracebacks=True,
			omit_repeated_times=False,
			level=1,
			tracebacks_suppress=[qasync, asyncio],
			tracebacks_show_locals=True,
			tracebacks_width=fileColumns,
			locals_max_string=500,
			markup=True,
		)
		fileHandler.setLevel(1)
		console = Console(
			soft_wrap=True,
			tab_size=2,
			width=columns,
			record=False,
			log_time_format="%H:%M:%S",
		)
		consoleHandler = RichHandler(
			console=console,
			level=self.determineLogLevel(),
			log_time_format="%H:%M:%S",
			rich_tracebacks=True,
			markup=True,
		)
		consoleHandler.setLevel(self.determineLogLevel())
		consoleHandler.addFilter(levelFilter(consoleHandler.level))
		self.addHandler(consoleHandler)
		self.addHandler(fileHandler)
		# self.propagate = False
		self.cleanupLogFolder()
		sys.excepthook = self.prettyErrorLogger

		_LevityLogger.fileHandler = fileHandler
		_LevityLogger.consoleHandler = consoleHandler

	def __ensureFoldersExists(self):
		if not self.logDir.exists():
			self.logDir.mkdir(parents=True)
		if not self.errorLogDir.exists():
			self.errorLogDir.mkdir(parents=True)

	def determineLogLevel(self) -> str:
		inDebug = int(bool(gettrace()))

		env = int(os.environ.get("DEBUG", 0))
		argvDebug = int(any("debug" in arg for arg in argv))
		configDebug = int(self.__config__['level'].upper() == "DEBUG")
		debugSum = env + argvDebug + configDebug

		envVerbose = int(os.environ.get("VERBOSE", 0))
		argvVerbose = int(any("verbose" in arg for arg in argv))
		configVerbose = int(self.__config__['level'].upper() == "VERBOSE")
		verboseSum = envVerbose + argvVerbose + configVerbose
		if verboseSum and verboseSum > debugSum:
			print(f"determineLogLevel found: {verboseSum}")
			return 'VERBOSE'
		elif debugSum and debugSum > inDebug:
			print(f"determineLogLevel found: {debugSum}")
			return 'DEBUG'
		else:
			print(f"determineLogLevel found: {self.__config__['level'].upper()}")
			return self.__config__['level'].upper()

	@property
	def VERBOSE(self):
		return logging.getLevelName('VERBOSE')

	@classmethod
	def getFile(cls):
		_format = cls.__config__["logFileFormat"]
		logFile = Path(cls.logDir, 'LevityDash.log')
		if logFile.exists():
			timestamp = datetime.fromtimestamp(logFile.stat().st_ctime)
			newFileName = logFile.with_stem(f"LevityDash_{timestamp.strftime(_format)}")
			logFile.rename(newFileName)
		_LevityLogger.logPath = logFile
		return open(logFile, "w")

	@classmethod
	def openLog(cls):
		webbrowser.open(cls.logPath.as_uri())

	def verbose(self, msg, *args, **kwargs):
		if self.isEnabledFor(self.VERBOSE):
			self._log(self.VERBOSE, msg, args, **kwargs)

	def getChild(self, name):
		child = super().getChild(name)
		child.setLevel(self.level)
		return child

	def folderSize(self, path, level=None, excludeFolders: bool = False) -> int:
		if level is not None:
			if level <= 0:
				return 0
			level -= 1
		totalFolderSize = 0
		for file in path.iterdir():
			if file.is_dir():
				if excludeFolders:
					continue
				totalFolderSize += self.folderSize(file, level)
			else:
				totalFolderSize += file.stat().st_size
		return totalFolderSize

	def allFiles(self, path: Path, level=None, excludeFolders: bool = False) -> iter:
		if level is not None:
			if level <= 0:
				return []
			level -= 1

		for file in path.iterdir():
			if file.is_dir():
				if excludeFolders:
					continue
				for f in self.allFiles(file, level):
					yield f
			else:
				yield file

	def removeOldestFile(self, path):
		files = list(self.allFiles(path, 1))
		files = sorted(files, key=lambda x: x.stat().st_mtime)
		if len(files) > 0:
			files[0].unlink()

	def removeOlderThan(self, path, delta):
		cutoff = datetime.now() - delta
		for file in self.allFiles(path):
			if datetime.fromtimestamp(file.stat().st_mtime) < cutoff:
				os.remove(file)

	def cleanupLogFolder(self):
		maxLogSize = configToFileSize(self.__config__["maxLogSize"])
		maxErrorsAge = configToTimeDelta(self.__config__["maxErrorLogAge"])
		maxPrettyErrorsSize = configToFileSize(self.__config__["maxErrorLogSize"])
		if self.folderSize(self.logDir, 1) > maxLogSize:
			self.removeOldestFileToFitSize(self.logDir, maxLogSize)
		self.removeOlderThan(self.errorLogDir, maxErrorsAge)
		if self.folderSize(self.errorLogDir) > maxPrettyErrorsSize:
			self.removeOldestFileToFitSize(self.errorLogDir, maxPrettyErrorsSize)

	def removeOldestFileToFitSize(self, path, maxSize):
		def filesToRemoveToFitSize(path, amountToFree):
			files = list(self.allFiles(path, excludeFolders=True))
			files = sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)
			total = 0
			while total < amountToFree and files:
				file = files.pop()
				total += file.stat().st_size
				yield file

		if (amountToFree := self.folderSize(path, excludeFolders=True) - maxSize) > 0:
			list(map(os.remove, filesToRemoveToFitSize(path, amountToFree)))

	def genPrettyErrorFileName(self, _type, value, *_) -> Path:
		timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
		fileName = f"{timestamp}_{_type.__name__}_{value.__class__.__name__}_{value.__class__.__module__}.html"
		return self.errorLogDir.joinpath(fileName)

	def prettyErrorLogger(self, _type, value, tb) -> None:
		console = self.fileHandler.console
		self.exception(
			f"Uncaught exception: {_type.__name__}", exc_info=(_type, value, tb)
		)
		console.save_html(path=self.genPrettyErrorFileName(_type, value, tb), inline_styles=False)

	def setLevel(self, level: int | str) -> None:
		# super().setLevel(level)
		self.consoleHandler.setLevel(level)
		self.fileHandler.setLevel('VERBOSE')
		self.verbose(f"Log {self.name} set to level {logging.getLevelName(level) if isinstance(level, int) else level}")


def configToFileSize(value: str) -> int | float:
	if value.isdigit():
		return int(value)

	_val = search(r'\d+', value)
	if _val is None:
		raise AttributeError(f"{value} is not a valid file size")
	else:
		_val = _val.group(0)
	unit = value[len(_val):]
	_val = float(_val)

	match unit:
		case 'b' | 'byte' | 'bytes':
			return int(_val)
		case 'k' | 'kb' | 'kilobyte' | 'kilobytes':
			return _val*1024
		case 'm' | 'mb' | 'megabyte' | 'megabytes':
			return _val*1024 ** 2
		case 'g' | 'gb' | 'gigabyte' | 'gigabytes':
			return _val*1024 ** 3
		case '_val' | 'tb' | 'terabyte' | 'terabytes':
			return _val*1024 ** 4
		case _:
			raise AttributeError(f'Unable to parse maxSize: {value}')


def configToTimeDelta(value: str) -> timedelta:
	if value.isdigit():
		return timedelta(seconds=int(value))
	elif value.startswith("{") and value.endswith("}"):
		value = strToDict(value)
		return timedelta(**value)

	_val = search(r'\d+', value)
	if _val is None:
		raise AttributeError(f"{value} is not a valid file size")
	else:
		_val = _val.group(0)
	unit = value[len(_val):].strip(' ')
	_val = float(_val)
	match unit:
		case 's' | 'sec' | 'second' | 'seconds':
			return timedelta(seconds=_val)
		case 'm' | 'min' | 'minute' | 'minutes':
			return timedelta(minutes=_val)
		case 'h' | 'hour' | 'hours':
			return timedelta(hours=_val)
		case 'd' | 'day' | 'days':
			return timedelta(days=_val)
		case 'w' | 'week' | 'weeks':
			return timedelta(weeks=_val)
		case 'mo' | 'month' | 'months':
			return timedelta(days=_val*30)
		case 'y' | 'year' | 'years':
			return timedelta(days=_val*365)
		case _:
			raise AttributeError(f'Unable to parse maxSize: {value}')


def strToDict(value: str) -> dict:
	isDict = lambda x: x.startswith('{') and x.endswith('}')

	def parse(value):
		if isDict(value):
			value = value.strip('{}').split(',')
			return {k.strip(' "\''): float(v.strip(' "\'')) for k, v in map(lambda x: x.split(':'), value)}
		else:
			return value

	return parse(value)


logging.setLoggerClass(_LevityLogger)
LevityLogger = logging.getLogger("Levity")
LevityLogger.setLevel(LevityLogger.determineLogLevel())

# LevityLogger.setLevel(logging.DEBUG if debug else logging.INFO)
LevityLogger.info(f"Log set to {logging.getLevelName(LevityLogger.level)}")

weatherUnitsLog = logging.getLogger("WeatherUnits")
weatherUnitsLogUtils = weatherUnitsLog.getChild("utils")
weatherUnitsLogUtils.setLevel(logging.INFO)
weatherUnitsLog.setLevel(logging.INFO)

urllog = logging.getLogger("urllib3")
urllogPool = logging.getLogger("urllib3.connectionpool")
urllog.setLevel(logging.ERROR)
urllogPool.setLevel(logging.ERROR)

bleaklog = logging.getLogger("bleak")
bleaklog.setLevel(logging.ERROR)

LevityGUILog = LevityLogger.getChild("GUI")
LevityPluginLog = LevityLogger.getChild("Plugins")
LevityUtilsLog = LevityLogger.getChild("Utils")
# LevityPluginLog.setLevel(logging.INFO)

__all__ = ["LevityLogger", "LevityPluginLog", "LevityGUILog", "LevityUtilsLog"]
