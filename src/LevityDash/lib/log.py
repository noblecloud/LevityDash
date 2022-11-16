import argparse
import asyncio
import logging
import os
import shutil
import webbrowser
from collections import deque
from configparser import NoOptionError, SectionProxy
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import ClassVar, Dict, List

import shiboken2
from dotty_dict import Dotty as Dotty_
from PySide2.QtWidgets import QApplication, QStatusBar
from rich.console import Console
from rich.logging import RichHandler
from rich.style import Style
from rich.text import Text as RichText
from rich.theme import Theme
from sys import gettrace

from . import LevityDashboard as lvdash

suppressedModules = [asyncio, shiboken2]

class Dotty(Dotty_):

	# def __init__(self, dictionary = None, separator='.', esc_char='\\', no_list=False):
	# 	dictionary = self._recursive_to_dotty(dictionary or {})
	# 	super().__init__(dictionary, separator, esc_char, no_list)
	#
	# def _recursive_to_dotty(self, value: dict) -> dict:
	# 	for k, v in value.items():
	# 		if isinstance(v, dict):
	# 			value[k] = Dotty(v)
	# 	return value

	def __getattr__(self, item):
		return self[item]


try:
	import bleak
	suppressedModules.append(bleak)
except ImportError:
	pass

logging_levels = logging._nameToLevel

def install_sentry():
	try:
		endpoint = lvdash.config.get('Logging', 'sentry_endpoint')
		if endpoint:
			import sentry_sdk
			sentry_sdk.init(
				dsn=endpoint,
				traces_sample_rate=1.0
			)
	except ImportError:
		logging.warning("Sentry SDK not installed. Install with `pip install sentry-sdk` or `pip install LevityDash[monitoring]`")
	except AttributeError:
		pass
	except NoOptionError:
		try:
			import sentry_sdk
			print(f"Sentry is installed but Logging.sentry_endpoint not set in config")
		except ImportError:
			pass


def install_log_tail(handlers_: List[logging.Handler], level: int = logging.DEBUG):
	try:
		token = os.environ.get("LOGTAIL_SOURCE_TOKEN", None) or lvdash.config.get('Logging', 'logtail_token')
		if token:
			from logtail import LogtailHandler
			handlers_.append(LogtailHandler(source_token=token, level=level, include_extra_attributes=True))
	except ImportError:
		logging.warning("Logtail not installed. Install with `pip install logtail-python` or `pip install LevityDash[monitoring]`")
	except NoOptionError:
		try:
			import logtail
			print(f"Logtail is installed but no token was found. Set Logging.logtail_token in config or set LOGTAIL_SOURCE_TOKEN environment variable")
		except ImportError:
			pass


def levelFilter(level: int):
	def filter(record):
		return record.levelno >= level

	return filter


class StatusBarHandler(logging.Handler):

	def emit(self, record):
		if record.levelno < 1:
			return
		try:
			self.statusBar.showMessage(f'{datetime.fromtimestamp(int(record.created)):%X} | {record.getMessage()}')
		except Exception:
			pass

	@property
	def statusBar(self) -> QStatusBar:
		return getattr(lvdash, 'status_bar', None) or QApplication.instance().activeWindow().statusBar()



class LevityHandler(RichHandler):
	__level = 0

	def get_level_text(self, record: logging.LogRecord) -> RichText:
		"""Get the level name from the record.

		Args:
				record (LogRecord): LogRecord instance.

		Returns:
				Text: A tuple of the style and level name.
		"""
		level_name = record.levelname
		level_text = RichText.styled(
			level_name.ljust(9), f"logging.level.{level_name.lower()}"
		)
		return level_text

	@property
	def level(self):
		return self.__level

	@level.setter
	def level(self, value):
		self.__level = value


class RichRotatingLogHandlerProxy(RotatingFileHandler, LevityHandler):
	"""
	RichRotatingLogHandler is a subclass of RotatingFileHandler that uses Rich's Log Handler and Console to format the record.
	"""

	def __init__(self, *args, **kwargs):
		RotatingFileHandler.__init__(self, **{kwarg: value for kwarg, value in kwargs.items() if kwarg in RotatingFileHandler.__init__.__code__.co_varnames})
		RichHandler.__init__(self, **{kwarg: value for kwarg, value in kwargs.items() if kwarg in RichHandler.__init__.__annotations__})
		self.console.file = self.stream
		self._log_render.level_width = 10

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
	__config__: ClassVar[SectionProxy] = lvdash.config["Logging"]
	logDir: ClassVar[Path] = Path(lvdash.paths.user_log_dir)
	errorLogDir: ClassVar[Path]
	logPath: ClassVar[Path]

	_description_to_level: ClassVar[Dict[str, int]] = {
		'verbose': 0,
		'very-verbose': 1,
		'extra-verbose': 2,
		'extremely-verbose': 3,
		'obnoxiously-verbose': 4,
		'spam': 5,
	}

	fileHandler: ClassVar[RichHandler]
	consoleHandler: ClassVar[RichHandler]

	LOGGING_DEFAULT_CONFIG: ClassVar[dict] = {
		"Logging": {
			"level":                   "INFO",
			"verbosity":               "0",
			"encoding":                "utf-8",
			"logTimeFormat":           "%m/%d/%y %H:%M:%S",
			"logFileWidth":            "120",
		}
	}


	class DuplicateFilter(logging.Filter):
		previousLogs = deque([[] for _ in range(5)], maxlen=5)

		def filter(self, record):
			if (path := record.pathname).endswith("__init__.py"):
				record.pathname = path.replace("__init__.py", "")
			p = Path(record.pathname)
			if p.is_relative_to(libPath := Path(lvdash.paths.lib)):
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
		level = level or self.root.level
		super().__init__(name, level=level)
		self.addFilter(self.duplicateFilter)

	@classmethod
	def _test_log_level_name(cls, level: str) -> bool:
		level = level.upper().split('@', 1)[0]
		return level in logging._nameToLevel

	@classmethod
	def install(cls) -> None:
		if not lvdash.config.has_section("Logging"):
			lvdash.config.read_dict(cls.LOGGING_DEFAULT_CONFIG)
			lvdash.config.save()

		os.environ["PYTHONIOENCODING"] = 'utf-8'

		logging.addLevelName(5, "VERBOSE")
		logging.addLevelName(4, "VERBOSE@1")
		logging.addLevelName(3, "VERBOSE@2")
		logging.addLevelName(2, "VERBOSE@3")
		logging.addLevelName(1, "VERBOSE@4")
		logging.addLevelName(0, "SPAM")

		theme = Theme(
			{
				"logging.level.verbose":   Style(color="#0b67b2"),
				"logging.level.verbose@1": Style(color="#0b7ece"),
				"logging.level.verbose@2": Style(color="#28835f"),
				"logging.level.verbose@3": Style(color="#105e17"),
				"logging.level.verbose@4": Style(color="#115016"),
				"logging.level.spam":      Style(color="#0d4813"),
			}
		)

		level = cls.determineLogLevel()
		console_level = cls.determineLogLevel('console', default=level)
		file_level = cls.determineLogLevel('file', default=1)
		status_bar_level = cls.determineLogLevel('status-bar', default=4)
		logtail_level = cls.determineLogLevel('logtail', default=1)

		handlers = []

		if cls._parse_bool(os.environ.get('LEVITY_TELEMETRY', '0')):
			install_sentry()
			install_log_tail(handlers, logtail_level)

		cls.__ensureFoldersExists()
		cls.logPath = Path(cls.logDir, 'LevityDash.log')
		columns = shutil.get_terminal_size((200, 20)).columns - 2
		fileColumns = lvdash.config.getOrSet('Logging', 'logFileWidth', '120', lvdash.config.getint)
		timeFormat = lvdash.config.getOrSet('Logging', 'logTimeFormat', '%m/%d/%y %H:%M:%S', str)

		consoleFile = Console(
			tab_size=2,
			soft_wrap=True,
			no_color=True,
			width=fileColumns,
		)
		consoleHandler = LevityHandler(
			console=Console(
				soft_wrap=True,
				force_terminal=True,
				no_color=False,
				force_interactive=True,
				tab_size=2,
				width=columns,
				log_time_format=timeFormat,
				theme=theme,
			),
			log_time_format=timeFormat,
			tracebacks_show_locals=True,
			tracebacks_suppress=suppressedModules,
			locals_max_length=5,
			locals_max_string=200,
			markup=True,
			show_path=False,
			tracebacks_width=columns,
			rich_tracebacks=True,
			omit_repeated_times=False,
			level=console_level,
			#! change the trace backs to true!!
		)

		richRotatingFileHandler = RichRotatingLogHandlerProxy(
			encoding=lvdash.config.getOrSet('Logging', 'encoding', 'utf-8', str),
			console=consoleFile,
			show_path=False,
			markup=True,
			log_time_format=timeFormat,
			rich_tracebacks=True,
			omit_repeated_times=False,
			tracebacks_suppress=suppressedModules,
			tracebacks_show_locals=True,
			tracebacks_width=fileColumns,
			locals_max_string=200,
			filename=cls.logPath,
			maxBytes=int(lvdash.config.getOrSet('Logging', 'rolloverSize', '10mb', lvdash.config.configToFileSize)),
			backupCount=int(lvdash.config.getOrSet('Logging', 'rolloverCount', '5', lvdash.config.getint)),
		)
		cls.propagate = True

		richRotatingFileHandler.setLevel(file_level)

		cls.fileHandler = richRotatingFileHandler
		cls.consoleHandler = consoleHandler
		cls.console = consoleHandler.console
		cls.statusBarHandler = StatusBarHandler()
		cls.statusBarHandler.setLevel(status_bar_level)

		handlers += [consoleHandler, richRotatingFileHandler, cls.statusBarHandler]

		logging.setLoggerClass(_LevityLogger)

		logging.basicConfig(handlers=handlers, format="%(message)s", level=level)

	@classmethod
	def __ensureFoldersExists(cls):
		if not cls.logDir.exists():
			cls.logDir.mkdir(parents=True)

	@classmethod
	def determineLogLevel(
		cls,
		prefix: str = '',
		env_prefix: str = None,
		arg_prefix: str = None,
		config_prefix: str = None,
		default: str = None,
	) -> str:

		if prefix not in {'', 'console', 'status_bar', 'file', 'logtail'}:
			key = ''

		# Priority: args > config > env > default

		keys = cls._make_keys(arg_prefix, config_prefix, env_prefix, prefix)

		level: int = -1
		verbosity = None

		inDebug = bool(gettrace())

		# --- args ---

		# determine verbosity level from args
		args = cls._make_argparse(keys)
		if args.verbosity is not None:
			verbosity = cls._parse_verbosity(args.verbosity)

		# parse -v flag
		if (v := getattr(args, 'v', None)) is not None:
			if verbosity is not None:
				verbosity = max(v, verbosity)
			else:
				verbosity = v

		# determine level from args
		if args.verbose or (v is not None):
			level = 5
		elif args.debug:
			level = 10
		elif args.level is not None:
			level = cls._parse_level(args.level)

		# --- config ---
		# determine level from config
		if level == -1 and keys.config.level in cls.__config__:
			level = cls.__config__[keys.config.level]
			if isinstance(level, str):
				if level.isdigit():
					level = int(level)
				elif level.upper() in logging_levels:
					level = logging_levels[level.upper()]
			elif isinstance(level, int):
				level = sorted((0, level, 50))[0]

		# determine verbosity from config
		if verbosity is None and keys.config.verbosity in cls.__config__:
			verbosity = cls._parse_verbosity(cls.__config__[keys.config.verbosity])

		# --- env ---
		# determine verbosity from env
		if verbosity is None and keys.env.verbosity in os.environ:
			verbosity = cls._parse_verbosity(os.environ[keys.env.verbosity])

		# determine level from env
		if level == -1:
			# determine verbose from env
			if env_verbose := os.environ.get(keys.env.verbose, False):
				env_verbose = cls._parse_bool(env_verbose)
				if env_verbose:
					level = 5
			# determine debug from env
			elif env_debug := os.environ.get(keys.env.debug, False):
				env_debug = cls._parse_bool(env_debug)
				if env_debug:
					level = 10
			elif (level_env := os.environ.get(keys.env.level, None)) is not None:
				level = cls._parse_level(level_env)

		if verbosity is None or not isinstance(verbosity, int):
			verbosity = 0

		if level == -1 and default is not None:
			if isinstance(default, str):
				default = logging_levels.get(default.upper(), 20)
			level = default

		if verbosity and -1 < level <= 5:
			level -= verbosity

		return logging.getLevelName(level)

	@classmethod
	def _parse_verbosity(cls, verbosity_value: str | int) -> int:
		if isinstance(verbosity_value, str):
			if verbosity_value.isdigit():
				return int(verbosity_value)
			elif verbosity_value.upper() in logging_levels:
				verbosity = verbosity_value.split('@')
				if len(verbosity) == 1:
					return 0 if verbosity[0].upper() == 'VERBOSE' else 5
				else:
					_, verbosity = *verbosity, 0
					return int(verbosity)
			elif (l := verbosity_value.lower()) in cls._description_to_level:
				return cls._description_to_level[l]
		elif isinstance(verbosity_value, int):
			return verbosity_value
		return 0

	@staticmethod
	def _parse_bool(value: str | int) -> bool | None:
		if isinstance(value, str):
			value = value.lower()
			if value in {'1', 'true', 't', 'yes', 'y', 'on'}:
				return True
			elif value in {'0', 'false', 'f', 'no', 'n', 'off'}:
				return False
			else:
				return None
		elif isinstance(value, int):
			return bool(value)

	@classmethod
	def _parse_level(cls, level: str | int) -> int:
		if isinstance(level, str):
			if level.isdigit():
				return int(level)
			elif level.upper() in logging_levels:
				return logging_levels[level.upper()]
		elif isinstance(level, int):
			return sorted((0, level, 50))[0]
		return 20

	@classmethod
	def _make_keys(cls, arg_prefix, config_prefix, env_prefix, prefix) -> Dotty:
		keys = Dotty({
			'prefix': prefix,
			'args': Dotty({}),
			'config': Dotty({}),
			'env': Dotty({}),
		})

		if arg_prefix is None:
			arg_prefix = prefix
		if arg_prefix and not arg_prefix.endswith('-'):
			arg_prefix += '-'
		keys.args.debug = f"--{arg_prefix}debug"
		keys.args.verbose = f"--{arg_prefix}verbose"
		keys.args.verbosity = f"--{arg_prefix}verbosity"
		keys.args.level = f"--{arg_prefix}level"

		if config_prefix is None:
			config_prefix = prefix
		if config_prefix and not config_prefix.endswith('-'):
			config_prefix += '-'
		keys.config.level = f"{config_prefix}level"
		keys.config.verbosity = f"{config_prefix}verbosity"

		if env_prefix is None:
			env_prefix = prefix.upper()
		if env_prefix and not env_prefix.endswith('_'):
			env_prefix += '_'
		keys.env.debug = f"LEVITY_{env_prefix}DEBUG"
		keys.env.verbose = f"LEVITY_{env_prefix}VERBOSE"
		keys.env.level = f"LEVITY_{env_prefix}LOG_LEVEL"
		keys.env.verbosity = f"LEVITY_{env_prefix}VERBOSITY"

		return keys

	@classmethod
	def _make_argparse(cls, keys: Dotty) -> argparse.Namespace:
		args_namespace = argparse.Namespace()
		parser = argparse.ArgumentParser()

		debug_flags = [keys.args.debug]
		level_flags = [keys.args.level]

		if keys.prefix == '':
			parser.add_argument('-v', action='count')
			level_flags.append('-l')
			debug_flags.append('-d')

		parser.add_argument(keys.args.verbose, action='store', default=None, dest='verbose')
		parser.add_argument(keys.args.verbosity, action='store', default=None, dest='verbosity')
		parser.add_argument(*debug_flags, action='store_true', default=None, dest='debug')
		parser.add_argument(*level_flags, type=str, default=None, dest='level')
		try:
			log_args = parser.parse_args(namespace=args_namespace)
		except Exception as e:
			print(e)
			return args_namespace
		return log_args

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
		self._log(max(self.VERBOSE - verbosity, 0), msg, args, **kwargs)

	@classmethod
	def openLog(cls):
		webbrowser.open(cls.logPath.as_uri())

	def setLevel(self, level: int | str, *handler: str) -> None:
		self.verbose(
			f"Log {handler or self.name} set to level {logging.getLevelName(level) if isinstance(level, int) else level}",
			verbosity=5
		)
		if not handler:
			super().setLevel(level)
		if 'console' in handler:
			self.console.setLevel(level)
		if 'file' in handler:
			self.file.setLevel(level)
		if 'status-bar' in handler:
			self.status_bar.setLevel(level)
		if 'all' in handler:
			self.setLevel(level, 'console', 'file', 'status-bar')

	def setVerbosity(self, level: int):
		self.fileHandler.setLevel(5 - level)
		self.__config__['verbosity'] = str(level)
		self.__config__.parser.save()
		self.verbose(
			f"Log {self.name} set to verbosity {level}",
			verbosity=5
		)


class PrettyErrorLogger(_LevityLogger):


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
		maxLogFolderSize = int(lvdash.config.getOrSet('Logging', 'maxLogFolderSize', '200mb', lvdash.config.configToFileSize))
		maxAge: timedelta = lvdash.config.getOrSet('Logging', 'maxLogAge', '7 days', lvdash.config.configToTimeDelta)
		maxPrettyErrorsSize = int(lvdash.config.getOrSet('Logging', 'maxPrettyErrorsFolderSize', '50mb', lvdash.config.configToFileSize))

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
		# if self.savePrettyErrors:
		# 	console = self.fileHandler.console
		# 	console.save_html(path=self.genPrettyErrorFileName(_type, value, tb), inline_styles=False)

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
lvdash.config.setLogger(LevityLogger.getChild('LevityConfig'))

debug = LevityLogger.level <= logging.DEBUG

__builtins__['DEBUG']: bool = debug
__builtins__['console'] = _LevityLogger.consoleHandler.console

__all__ = ["LevityLogger", "LevityPluginLog", "LevityUtilsLog", 'debug']
