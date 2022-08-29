import asyncio
from configparser import SectionProxy
import os
import shutil

import bleak
import webbrowser
from collections import deque
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

import shiboken2
from sys import argv, gettrace

from .config import userConfig

import logging
from typing import ClassVar

from LevityDash import __lib__, __dirs__
import qasync
from rich.console import Console
from rich.logging import RichHandler

suppressedModules = [qasync, asyncio, bleak, shiboken2]

def levelFilter(level: int):
	def filter(record):
		return record.levelno >= level

	return filter


class RichRotatingLogHandlerProxy(RotatingFileHandler, RichHandler):
	"""
	RichRotatingLogHandler is a subclass of RotatingFileHandler that uses Rich's Log Handler and Console to format the record.
	"""

	def __init__(self, *args, **kwargs):
		RotatingFileHandler.__init__(self, **{kwarg: value for kwarg, value in kwargs.items() if kwarg in RotatingFileHandler.__init__.__code__.co_varnames})
		RichHandler.__init__(self, **{kwarg: value for kwarg, value in kwargs.items() if kwarg in RichHandler.__init__.__annotations__})
		self.console.file = self.stream
		self._log_render.level_width = 9

	def emit(self, record: logging.LogRecord):
		try:
			if self.shouldRollover(record):
				self.doRollover()
				self.console.file = self.stream
			RichHandler.emit(self, record)
		except Exception as e:
			RichHandler.handleError(self, record)


class _LevityLogger(logging.Logger):

	__initiated__: ClassVar[bool] = False
	__config__: ClassVar[SectionProxy] = userConfig["Logging"]
	logDir: ClassVar[Path] = Path(__dirs__.user_log_dir)
	errorLogDir: ClassVar[Path]
	logPath: ClassVar[Path]

	fileHandler: ClassVar[RichHandler]
	consoleHandler: ClassVar[RichHandler]

	LOGGING_DEFAULT_CONFIG: ClassVar[dict] = {
		"Logging": {
			"level":                   "INFO",
			"verbosity":               "0",
			"encoding":                "utf-8",
			"logFileFormat":           "%Y-%m-%d_%H-%M-%S",
			"logTimeFormat":           "%H:%M:%S",
			"logFileWidth":            "120",
			"maxLogFolderSize":        "200mb",
			"maxLogAge":               timedelta(days=7),
			"prettyErrors":            "False",
			"maxPrettyErrorTotalSize": "50mb",
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

	def __init__(self, name: str, level: int | str = None):
		level = level or self.determineLogLevel()
		super().__init__(name, level=level)
		self.addFilter(self.duplicateFilter)

	@classmethod
	def install(cls) -> None:
		if not userConfig.has_section("Logging"):
			userConfig.read_dict(cls.LOGGING_DEFAULT_CONFIG)
			userConfig.save()

		os.environ["PYTHONIOENCODING"] = 'utf-8'

		logging.addLevelName(5, "VERBOSE")
		logging.addLevelName(4, "VERBOSE@1")
		logging.addLevelName(3, "VERBOSE@2")
		logging.addLevelName(2, "VERBOSE@3")
		logging.addLevelName(1, "VERBOSE@4")

		_LevityLogger.errorLogDir = cls.logDir.joinpath("prettyErrors")
		cls.__ensureFoldersExists()
		cls.getFile()
		columns = shutil.get_terminal_size((120, 20)).columns - 5
		fileColumns = userConfig.getOrSet('Logging', 'logFileWidth', '120', userConfig.getint)
		timeFormat = userConfig.getOrSet('Logging', 'logTimeFormat', '%H:%M:%S', str)

		consoleFile = Console(
			tab_size=2,
			soft_wrap=True,
			no_color=True,
			width=fileColumns,
			record=True,
		)
		consoleHandler = RichHandler(
			console=Console(
				soft_wrap=True,
				force_terminal=True,
				tab_size=2,
				width=columns,
				log_time_format=timeFormat,
			),
			log_time_format=timeFormat,
			tracebacks_show_locals=True,
			tracebacks_suppress=suppressedModules,
			locals_max_length=15,
			locals_max_string=200,
			show_path=False,
			tracebacks_width=columns,
			rich_tracebacks=True,
		)

		richRotatingFileHandler = RichRotatingLogHandlerProxy(
			encoding=userConfig.getOrSet('Logging', 'encoding', 'utf-8', str),
			console=consoleFile,
			show_path=False,
			log_time_format=timeFormat,
			rich_tracebacks=True,
			omit_repeated_times=True,
			level=5 - cls.verbosity(5),
			tracebacks_suppress=suppressedModules,
			tracebacks_show_locals=True,
			tracebacks_width=fileColumns,
			locals_max_string=200,
			filename=cls.logPath,
			maxBytes=int(userConfig.getOrSet('Logging', 'rolloverSize', '10mb', userConfig.configToFileSize)),
			backupCount=int(userConfig.getOrSet('Logging', 'rolloverCount', '5', userConfig.getint)),
		)
		cls.propagate = True
		cls.cleanupLogFolder()

		richRotatingFileHandler.setLevel(1)

		cls.fileHandler = richRotatingFileHandler
		cls.consoleHandler = consoleHandler

		logging.setLoggerClass(_LevityLogger)
		logging.basicConfig(handlers=[cls.consoleHandler, cls.fileHandler], format="%(message)s")

	@classmethod
	def __ensureFoldersExists(cls):
		if not cls.logDir.exists():
			cls.logDir.mkdir(parents=True)
		if not cls.errorLogDir.exists():
			cls.errorLogDir.mkdir(parents=True)

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
			level = 5
		elif debugSum and debugSum > inDebug:
			level = 10
		elif debugSum:
			level = 10 - (5 if verboseSum else 0 + max(envVerbose, argvVerbose, configVerbose))
		else:
			level = logging.getLevelName(self.__config__['level'].upper())
		level -= self.verbosity(level)
		return logging.getLevelName(level)

	@property
	def VERBOSE(self):
		return logging.getLevelName('VERBOSE')

	@property
	def VERBOSITY(self):
		return logging.getLevelName('VERBOSE') - self.verbosity(5)

	@classmethod
	def verbosity(cls, forLevel: str | int = 20) -> int:
		if isinstance(forLevel, str):
			forLevel = logging.getLevelName(forLevel.upper())
		if forLevel > 5:
			return 0
		verb = _LevityLogger.__config__.getint('verbosity', None)
		if verb is None:
			verb = 5 - forLevel
			cls.__config__['verbosity'] = str(verb)
			cls.__config__.parser.save()
		return verb

	def verbose(self, msg: str, verbosity: int = 0, *args, **kwargs):
		self._log(self.VERBOSE - verbosity, msg, args, **kwargs)

	@classmethod
	def getFile(cls):
		_format = cls.__config__["logFileFormat"]
		logFile = Path(cls.logDir, 'LevityDash.log')
		_LevityLogger.logPath = logFile

	@classmethod
	def openLog(cls):
		webbrowser.open(cls.logPath.as_uri())

	@classmethod
	def folderSize(cls, path, level=None, excludeFolders: bool = False) -> int:
		if level is not None:
			if level <= 0:
				return 0
			level -= 1
		totalFolderSize = 0
		for file in path.iterdir():
			if file.is_dir():
				if excludeFolders:
					continue
				totalFolderSize += cls.folderSize(file, level)
			else:
				totalFolderSize += file.stat().st_size
		return totalFolderSize

	@classmethod
	def allFiles(cls, path: Path, level=None, excludeFolders: bool = False) -> iter:
		if level is not None:
			if level <= 0:
				return []
			level -= 1

		for file in path.iterdir():
			if file.is_dir():
				if excludeFolders:
					continue
				for f in cls.allFiles(file, level):
					yield f
			else:
				yield file

	@classmethod
	def removeOldestFile(cls, path):
		files = list(cls.allFiles(path, 1))
		files = sorted(files, key=lambda x: x.stat().st_mtime)
		if len(files) > 0:
			files[0].unlink()

	@classmethod
	def removeOlderThan(cls, path, delta):
		cutoff = datetime.now() - delta
		for file in cls.allFiles(path):
			if datetime.fromtimestamp(file.stat().st_mtime) < cutoff:
				os.remove(file)

	@classmethod
	def cleanupLogFolder(cls):
		maxLogFolderSize = int(userConfig.getOrSet('Logging', 'maxLogFolderSize', '200mb', userConfig.configToFileSize))
		maxAge: timedelta = userConfig.getOrSet('Logging', 'maxLogAge', '7 days', userConfig.configToTimeDelta)
		maxPrettyErrorsSize = int(userConfig.getOrSet('Logging', 'maxPrettyErrorsFolderSize', '50mb', userConfig.configToFileSize))

		if cls.folderSize(cls.logDir, 1) > maxLogFolderSize:
			cls.removeOldestFileToFitSize(cls.logDir, maxLogFolderSize)

		if cls.folderSize(cls.errorLogDir) > maxPrettyErrorsSize:
			cls.removeOldestFileToFitSize(cls.errorLogDir, maxPrettyErrorsSize)

		cls.removeOlderThan(cls.logDir, maxAge)
		cls.removeOlderThan(cls.errorLogDir, maxAge)

	@classmethod
	def removeOldestFileToFitSize(cls, path, maxSize):
		def filesToRemoveToFitSize(path_, amountToFree_):
			files = list(cls.allFiles(path_, excludeFolders=True))
			files = sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)
			total = 0
			while total < amountToFree_ and files:
				file = files.pop()
				total += file.stat().st_size
				yield file

		if (amountToFree := cls.folderSize(path, excludeFolders=True) - maxSize) > 0:
			list(map(os.remove, filesToRemoveToFitSize(path, amountToFree)))

	def genPrettyErrorFileName(self, _type, value, *_) -> Path:
		timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
		fileName = f"{timestamp}_{_type.__name__}_{value.__class__.__name__}_{value.__class__.__module__}.html"
		return self.errorLogDir.joinpath(fileName)

	def prettyErrorLogger(self, _type, value, tb) -> None:
		self.exception(
			f"Uncaught exception: {_type.__name__}", exc_info=(_type, value, tb)
		)
		if self.savePrettyErrors:
			console = self.fileHandler.console
			console.save_html(path=self.genPrettyErrorFileName(_type, value, tb), inline_styles=False)

	def setLevel(self, level: int | str) -> None:
		self.verbose(
			f"Log {self.name} set to level {logging.getLevelName(level) if isinstance(level, int) else level}",
			verbosity=5
		)
		super().setLevel(level)
		self.consoleHandler.setLevel(level)

	def setVerbosity(self, level: int):
		self.fileHandler.setLevel(5 - level)
		self.__config__['verbosity'] = str(level)
		self.__config__.parser.save()
		self.verbose(
			f"Log {self.name} set to verbosity {level}",
			verbosity=5
		)


weatherUnitsLog = logging.getLogger("WeatherUnits")
weatherUnitsLogUtils = weatherUnitsLog.getChild("utils")
weatherUnitsLogConfig = weatherUnitsLog.getChild("config")
weatherUnitsLogUtils.setLevel(logging.INFO)
weatherUnitsLogConfig.setLevel(logging.INFO)
weatherUnitsLog.setLevel(logging.INFO)

logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
logging.getLogger("bleak").setLevel(logging.ERROR)

_LevityLogger.install()
LevityLogger: _LevityLogger = _LevityLogger('Levity')

LevityPluginLog = LevityLogger.getChild("Plugins")
LevityUtilsLog = LevityLogger.getChild("Utils")
userConfig.setLogger(LevityLogger.getChild('LevityConfig'))

debug = LevityLogger.level <= logging.DEBUG

__all__ = ["LevityLogger", "LevityPluginLog", "LevityUtilsLog", 'debug']
