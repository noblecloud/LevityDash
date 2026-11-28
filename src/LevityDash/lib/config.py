import os
import platform
import re
import tomllib
from textwrap import dedent
from configparser import ConfigParser, ExtendedInterpolation, ParsingError
from datetime import timedelta
from functools import cached_property
from io import StringIO
from logging import getLogger, Logger
from pathlib import Path, PosixPath, PurePath
from re import search
from shutil import copy2, copytree
from typing import Callable, ClassVar, Optional, Text, Union

from pytz import timezone
from rich import prompt

from . import LevityDashboard
from .EasyPath import EasyPath, EasyPathFile
from .configfile import dumpToml, fromToml, migrateConfigDir, readToml
from ._descriptors import classproperty

_backupLogger = getLogger('LevityConfig')

DATETIME_NO_ZERO_CHAR = '#' if platform.system() == 'Windows' else '-'

def buildDirectories(path: Path, dirs: Union[list, str, dict[str, Union[str, list]]]) -> None:
	'''
	Builds a directory tree for the given path and the given dict of directories.
	:param path: The path to build the directory tree for.
	:type path: Path
	:param dirs: The directories to build.
	:type dirs: Union[list, str, dict[str, Union[str, list]]]
	:return: None
	:rtype: None
	'''
	if not path.exists():
		path.mkdir(parents=True)
	if dirs is None:
		return
	if isinstance(dirs, str):
		dirs = [dirs]
	if isinstance(dirs, dict):
		for key, value in dirs.items():
			subpath = path.joinpath(key)
			buildDirectories(subpath, value)
	else:
		for dir in dirs:
			subpath = path.joinpath(dir)
			if not subpath.exists():
				subpath.mkdir()


unsetConfig = object()


def guessLocation() -> tuple[str, str, str]:
	from LevityDash.lib.utils.shared import simpleRequest

	location = simpleRequest('https://ipapi.co/json/')

	from LevityDash.lib.log import LevityLogger as log
	log.info(f'Location fetched from IP: {location["city"]}, {location["region"]}, {location["country"]}, lat: {location["latitude"]},  lon: {location["longitude"]}')
	return location['latitude'], location['longitude'], location['timezone']


class LevityConfig(ConfigParser):
	fileName: str
	_log: ClassVar[Logger] = _backupLogger

	def __init__(self, *args, **kwargs):
		path = getattr(self, 'fileName', None) or kwargs.pop('fileName', None) or kwargs.pop('path', None) or None
		super(LevityConfig, self).__init__(
			allow_no_value=True,
			interpolation=ExtendedInterpolation(),
			strict=False,
			**kwargs
		)
		self.optionxform = str

		dirs = LevityDashboard.paths

		userPath = Path(dirs.config)
		if not userPath.exists() or len(os.listdir(userPath)) == 0:
			self.log.warning(f'Creating user config directory: {userPath}')
			buildDirectories(userPath, {'fonts': [], 'saves': ['dashboards', 'panels']})
			copytree(LevityDashboard.paths.resources / 'example-config', userPath, dirs_exist_ok=True)

		self.userPath = userPath

		# An INI file from before the move to TOML becomes a .toml (the old one kept as a .bak) on first run.
		migrateConfigDir(userPath)

		if path is not None:
			# A config folder missing the file (a folder from an older release, or one that was tidied) gets the shipped one.
			shipped = LevityDashboard.paths.resources / 'example-config' / str(path)
			wanted = userPath / str(path)
			if not Path(str(path)).is_absolute() and shipped.is_file() and not wanted.exists() and not wanted.with_suffix('.ini').exists():
				copy2(shipped, wanted)
			self.path = self.userPath[path]
			if self.path.path.suffix == '.toml' and not self.path.path.exists():
				# Not migrated (read-only folder, unreadable file): keep working from the INI.
				legacy = self.path.path.with_suffix('.ini')
				if legacy.is_file():
					self.log.warning(f'Reading {legacy.name}; it could not be moved to {self.path.path.name}')
					self.path = self.userPath[str(legacy)]
			self.read(self.path.path)

		self._check_on_boardings()

	def _check_on_boardings(self):
		for sectionName, section in {**self._sections, 'defaults': self._defaults}.items():
			if (enabled := section.get('enabled', None)) is not None and enabled.startswith('@ask'):
				enabled = self.askValue(enabled)
				section['enabled'] = str(enabled)
				self.save()
			if enabled is not None and not self.BOOLEAN_STATES.get(str(enabled).lower(), False):
				continue
			for key, value in section.items():
				if value and str(value).startswith('@ask'):
					value = self.askValue(value)
					section[key] = str(value)
					self.save()

	def askValue(self, value: str):
		value = re.search(r'@(?P<action>\w+)(\((?P<options>(?P<type>\w+)(:(?P<value>.*?))?)\))?(\.message\((?P<message>.+?)\))?', value)
		if (value_ := value.groupdict() if value is not None else None) is None:
			raise ParsingError
		elif 'action' in value_:
			value = value_
			del value_
		else:
			raise KeyError
		match value['action']:
			case 'ask':
				askType = 'askInput'
			case 'askChoose':
				askType = 'askChoose'
			case _:
				askType = 'askInput'
		valueType = value['type']
		match valueType:
			case None:
				raise TypeError
			case 'bool':
				valueType = bool
			case 'str':
				valueType = str
			case 'int':
				valueType = int
			case 'float':
				valueType = float
		if message := value['message']:
			message = message.replace('\\n', '\n')
		if askType == 'askChoose':
			choices = value['value']
			choices = re.findall(r'\w+', choices)
		elif (default := value['value']) is not None:
			choices = [default]
		else:
			choices = None

		if choices is not None and choices != ['']:
			default = choices[0]
			kwargs = {'choices': choices, 'default': default}
		else:
			default = ''
			kwargs = {}

		# non-interactive sessions (no TTY) can't prompt; take the default
		import sys
		if not (sys.stdin and sys.stdin.isatty()):
			self.log.warning(f'Non-interactive session; using default {default!r} for prompt {message!r}')
			if valueType is bool:
				return str(default).lower() in ('true', 't', '1', 'y', 'yes')
			if valueType is int:
				try:
					return round(float(default))
				except (TypeError, ValueError):
					return 0
			if valueType is float:
				try:
					return float(default)
				except (TypeError, ValueError):
					return 0.0
			return default

		if askType == 'askInput':
			message = message or ''

			if valueType is bool:
				default = default.lower() in ('true', 't', '1', 'y', 'yes')
				# result = QMessageBox(QWidget()).question(QWidget(),
				# 	self.path.name,
				# 	message,
				# 	QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes if default else QMessageBox.No,
				# ) == QMessageBox.Yes

				# Switch to using Rich for this

				return prompt.Confirm.ask(message, default=default)
			if valueType is str:
				# return QInputDialog.getText(QWidget(), self.path.name, message, QLineEdit.Normal, default)[0]
				return prompt.Prompt.ask(message, **kwargs)
			if valueType is int:
				try:
					default = int(default)
				except ValueError:
					pass
				# return QInputDialog.getInt(QWidget(), self.path.name, message, default)[0]
				fails = 0
				while fails < 3:
					result = prompt.Prompt.ask(message, **kwargs)
					fails += 1
					try:
						result = round(float(result))
					except ValueError:
						continue
					return result
				raise ValueError
			if valueType is float:
				try:
					default = float(default)
				except ValueError:
					pass
				# return QInputDialog.getDouble(QWidget(), self.path.name, message, default)[0]
				while True:
					result = prompt.Prompt.ask(message, **kwargs)
					try:
						result = float(result)
					except ValueError:
						continue
		elif askType == 'askChoose':
			message = message or ''
			if choices is not None:
				# return QInputDialog.getItem(QWidget(), self.path.name, message, choices, 0, 'custom' in choices)[0]
				return prompt.Prompt.ask(message, **kwargs)

	@classproperty
	def log(cls):
		return getattr(cls, '_log', None)

	@classmethod
	def setLogger(cls, value):
		cls._log = value

	@cached_property
	def rootPath(self) -> EasyPath:
		return EasyPath(LevityDashboard.paths.config)

	def read(self, filenames, encoding=None):
		"""Reads a file: TOML for a `.toml`, anything else as INI (the pre-TOML format)."""
		if isinstance(filenames, (str, bytes, os.PathLike)):
			filenames = [filenames]
		done = []
		for filename in filenames:
			if Path(filename).suffix.lower() != '.toml':
				done += super().read(filename, encoding)
				continue
			try:
				data = readToml(filename)
			except OSError:
				continue
			self._load(data)
			done.append(filename)
		return done

	def _load(self, data: dict[str, dict[str, str]]) -> None:
		for name, values in data.items():
			if name == self.default_section:
				target = self._defaults
			else:
				if name not in self._sections:
					self.add_section(name)
				target = self._sections[name]
			for key, value in values.items():
				target[self.optionxform(key)] = value  # raw, as an INI read does: `$` is not checked

	@property
	def _asIni(self) -> bool:
		path = getattr(self, 'path', None)
		path = getattr(path, 'path', path)
		return path is not None and Path(path).suffix.lower() == '.ini'

	def write(self, fp, *args, **kwargs):
		"""Writes TOML, or INI when this config was loaded from an INI file it could not move."""
		if self._asIni:
			return super().write(fp, *args, **kwargs)
		sections = []
		if self._defaults:
			sections.append((self.default_section, self._defaults))
		sections.extend(self._sections.items())
		fp.write(dumpToml(sections))

	def save(self):
		with self.path.path.open('w', encoding='utf-8') as f:
			self.write(f)

	@property
	def userPath(self):
		return self.__userPath

	@userPath.setter
	def userPath(self, value):
		match value:
			case EasyPath():
				pass
			case str() | Path() | PosixPath() | PurePath():
				value = EasyPath(value)
			case _:
				from LevityDash.lib.log import LevityUtilsLog as log
				log = log.getChild('config')
				log.critical(f'User path \'{value}\' is not a valid path.')
				raise TypeError(f'User config path must be a String, PosixPath or EasyPath, not {type(value)}')
		if not value.path.exists():
			from LevityDash.lib.log import LevityUtilsLog as log
			log = log.getChild('config')
			log.critical(f'User path \'{value}\' does not exist')
			raise FileNotFoundError(f'{value} does not exist')
		self.__userPath = value

	def getOrSet(self, section: str, key: str, default: str, getter: Callable | None = None) -> str:
		try:
			if section == self.default_section:
				section = self._proxies[self.default_section]
			else:
				section = self[section]
		except KeyError:
			self.add_section(section)
			section = self[section]

		if getter == self.getboolean or getter == bool:
			if (value := section.getboolean(key)) is None:
				section[key] = str(default)
				self.save()
				return default
			return value
		elif getter == self.getint:
			if (value := section.getint(key)) is None:
				section[key] = str(default)
				self.save()
				return default
			return value
		elif getter == self.getfloat:
			if (value := section.getfloat(key)) is None:
				section[key] = f'{default:g}'
				self.save()
				return default
			return value

		try:
			value = section[key]
		except KeyError:
			section[key] = value = str(default)
			self.save()
		if getter is not None:
			return getter(value)
		return value

	@staticmethod
	def configToFileSize(value: str) -> int | float:
		if value.isdigit():
			return int(value)

		_val = search(r'\d+', value)
		if _val is None:
			raise AttributeError(f"{value} is not a valid file size")
		else:
			_val = _val.group(0)
		unit = value[len(_val):].lower()
		_val = float(_val)

		match unit:
			case 'b' | 'byte' | 'bytes':
				return int(_val)
			case 'k' | 'kb' | 'kilobyte' | 'kilobytes':
				return _val * 10e2
			case 'm' | 'mb' | 'megabyte' | 'megabytes':
				return _val* 10e5
			case 'g' | 'gb' | 'gigabyte' | 'gigabytes':
				return _val * 10e8
			case '_val' | 'tb' | 'terabyte' | 'terabytes':
				return _val * 10e11
			case _:
				raise AttributeError(f'Unable to parse maxSize: {value}')

	@staticmethod
	def configToTimeDelta(value: str) -> timedelta:
		if value.isdigit():
			return timedelta(seconds=int(value))
		elif value.startswith("{") and value.endswith("}"):
			value = LevityConfig.strToDict(value)
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

	@staticmethod
	def strToDict(value: str) -> dict:
		def parse(_value):
			if _value.startswith('{') and _value.endswith('}'):
				_value = _value.strip('{}').split(',')
				return {k.strip(' "\''): float(v.strip(' "\'')) for k, v in map(lambda x: x.split(':'), _value)}
			else:
				return _value

		return parse(value)


class PluginsConfig(LevityConfig):
	fileName: str = 'plugins/plugins.toml'

	@property
	def enabledPlugins(self):
		enabled = set()
		for plugin in self.sections():
			if plugin == 'Options':
				continue
			if self[plugin].getboolean('enabled'):
				enabled.add(plugin)
		for name, plugin in self.userConfigs.items():
			try:
				if plugin['Config'].getboolean('enabled'):
					enabled.add(name)
				else:
					enabled.discard(name)
			except KeyError:
				pass
		return enabled

	@property
	def userConfigs(self):
		configsDir = self.userPath['plugins'].asDict(depth=3)
		result = {}
		for name, pluginDir in configsDir.items():
			if name.endswith(('.toml', '.ini')) and name not in ('plugins.toml', 'plugins.ini'):
				stem = name.rsplit('.', 1)[0]
				if name.endswith('.ini') and f'{stem}.toml' in configsDir:
					continue
				result[stem] = LevityConfig(path=pluginDir.path)
			elif isinstance(pluginDir, dict):
				for fileName in ('config.toml', 'config.ini'):
					if fileName in pluginDir.keys():
						result[name] = LevityConfig(path=pluginDir[fileName].path)
						break

		return result

	@property
	def userPlugins(self) -> dict[str, dict[str, EasyPath] | EasyPathFile]:
		pluginsDir = self.userPath['plugins'].asDict(depth=1)
		result = {}

		for name, pluginDir in pluginsDir.items():
			if '.py' in name and name != 'plugins.py':
				result[name.strip('.py')] = pluginDir
			elif isinstance(pluginDir, dict) and '__init__.py' in pluginDir.keys():
				result[name] = pluginDir['__init__.py']

		return result

	@property
	def userPluginsDir(self) -> EasyPath:
		return self.userPath['plugins']


class PluginConfig(LevityConfig):
	_plugin: 'Plugin'
	__log: 'Logger' = None

	def __init__(self, *args, **kwargs):
		self.plugin = kwargs.pop('plugin', None)
		super(PluginConfig, self).__init__(*args, **kwargs, default_section='plugin')

	@classmethod
	def readString(cls, string: Text, **context):
		"""A config from text: TOML, or the older INI text a plugin outside this repo may still ship."""
		path = context.pop('path', None)
		config = cls(**context)
		config.path = path
		text = dedent(string)
		try:
			data = fromToml(tomllib.loads(text))
		except tomllib.TOMLDecodeError:
			config.read_file(StringIO(text))
		else:
			config._load(data)

		if config.path is not None:
			config._check_on_boardings()
			config.save()
		return config

	def __getitem__(self, key):
		value = unsetConfig
		if key in self.sections():
			value = super(PluginConfig, self).__getitem__(key)
		elif key == self.plugin.name:
			return self.defaults()
		elif key in self.defaults():
			value = self.defaults()[key]
		else:
			try:
				mainConfig = userConfig.plugins[self._plugin.name]
				if key in mainConfig:
					value = mainConfig[key]
			except KeyError:
				pass
		if value == '':
			self.log.critical(f'No value for {key} in config for {self._plugin.name}')
		elif value is unsetConfig:
			raise KeyError
		if isinstance(value, str):
			return self.__parseValue(value)
		return value

	def __contains__(self, key):
		return key in self.sections() or key in self.defaults()

	def __parseValue(self, value):
		if value.lower() in self.BOOLEAN_STATES:
			return self.BOOLEAN_STATES[value.lower()]

		try:
			value = float(value)
			if value.is_integer():
				return int(value)
			return value
		except ValueError:
			pass
		return value

	def __repr__(self):
		return f'<PluginConfig: {self.plugin.name} {"✅" if self["enabled"] else "❌"}>'

	def validate(self, key: str):
		# TODO: Finish this
		try:
			value = self[self.default_section][key]
		except KeyError:
			value = unsetConfig
		if value is unsetConfig or value == '':
			value = ''
			from rich.prompt import Prompt
			while value == '':
				value = Prompt.ask(f'{self._plugin.name} requires \'{key}\' to continue.  Please enter a value.\n{key}')
			self[self.default_section][key] = value
			self.save()

	@cached_property
	def defaultFor(self):
		if 'defaultFor' in self.defaults():
			return set(re.findall(rf"[\w|\-]+", self['defaultFor']))
		return set()

	@cached_property
	def priority(self) -> float:
		"""How strongly this plugin is preferred when several publish the same key.

		Higher wins. ``priority = N`` in the plugin's own config overrides the plugin class's
		``sourcePriority`` (0 unless the plugin says otherwise). Explicit ``defaultFor`` matches
		still come first; priority orders the rest, and ties between them.
		"""
		raw = self.defaults().get('priority') if 'priority' in self.defaults() else None
		try:
			return float(raw)
		except (TypeError, ValueError):
			return float(getattr(type(self.plugin), 'sourcePriority', 0))

	@cached_property
	def maxAge(self) -> Optional[timedelta]:
		"""How old a realtime reading may be before the source stops being preferred for it.

		``maxAge = N`` (minutes) in the plugin's config overrides the plugin class's ``sourceMaxAge``
		(a timedelta, or None for never). 0 turns the check off. A stale source is not removed: it
		still answers when nothing fresher publishes the key.
		"""
		raw = self.defaults().get('maxAge') if 'maxAge' in self.defaults() else None
		try:
			minutes = float(raw)
		except (TypeError, ValueError):
			return getattr(type(self.plugin), 'sourceMaxAge', None)
		return timedelta(minutes=minutes) if minutes > 0 else None

	@property
	def plugin(self) -> 'Plugin':
		return self._plugin

	@plugin.setter
	def plugin(self, value: 'Plugin'):
		self._plugin = value
		try:
			self.__log = self._plugin.pluginLog.getChild('Config')
		except AttributeError:
			pass

	@property
	def log(self) -> 'Logger':
		return self.__log or self._log


class Config(LevityConfig):
	fileName: str = 'config.toml'

	@cached_property
	def plugins(self):
		return PluginsConfig()

	@property
	def units(self):
		return self['Units']

	@property
	def tz(self):
		try:
			return timezone(self['Location']['timezone'])
		except Exception as e:
			from LevityDash.lib.log import LevityUtilsLog as log
			log = log.getChild('config')
			log.error('Unable load timezone from config\n', e)

	_placeholders: frozenset = frozenset()

	def write(self, fp, *args, **kwargs):
		"""Writes the config without the placeholder location, so a stand-in never reaches the file."""
		held = {k: self['Location'].pop(k) for k in self._placeholders if 'Location' in self.sections() and k in self['Location']}
		try:
			return super().write(fp, *args, **kwargs)
		finally:
			if held:
				self['Location'].update(held)

	#: False while the location is a placeholder because it is neither in the config nor guessable.
	locationKnown: bool = True
	_lastGuessFailure: float = 0.0

	def _guessLocationWithRetries(self, log, attempts: int = 3):
		"""The location from the IP address, retried, or None. Backs off for a minute after a failure."""
		import time
		if time.monotonic() - self._lastGuessFailure < 60 and self._lastGuessFailure:
			return None
		error = None
		for attempt in range(attempts):
			try:
				return guessLocation()
			except Exception as e:
				error = e
				time.sleep(1 + attempt)
		self._lastGuessFailure = time.monotonic()
		log.error(
			f'LOCATION UNKNOWN: [Location] is not set in the config and the IP lookup failed {attempts} times ({error}). '
			f'Weather will not be fetched until you set latitude, longitude and timezone under [Location] in the config.'
		)
		return None

	@property
	def loc(self):
		noLocationSection = 'Location' not in self.sections()
		latitude = self.get('Location', 'latitude', fallback=None)
		longitude = self.get('Location', 'longitude', fallback=None)
		timezone = self.get('Location', 'timezone', fallback=None)
		if noLocationSection or not latitude or not longitude or not timezone:
			from LevityDash.lib.log import LevityUtilsLog as log
			log = log.getChild('config')
			log.info('No location set in config.  Guessing location based on IP address.')
			guessed = self._guessLocationWithRetries(log)
			if guessed is None:
				# Not saved, so a network blip never persists a place. But 0,0 is the Gulf of
				# Guinea, and weather for it looks real, so say plainly that nothing is known.
				self.locationKnown = False
				self._placeholders = {k for k, v in (('latitude', latitude), ('longitude', longitude), ('timezone', timezone)) if not v}
				self['Location'] = {
					'timezone': timezone or hostZoneName() or 'UTC',
					'latitude': latitude or '0.0',
					'longitude': longitude or '0.0',
				}
				return float(self['Location']['latitude']), float(self['Location']['longitude'])
			lat, lon, tz = guessed
			self['Location'] = {'timezone': timezone or tz, 'latitude': latitude or lat, 'longitude': longitude or lon}
			self.save()
		return float(self['Location']['latitude']), float(self['Location']['longitude'])

	@property
	def locStr(self):
		lat, lon = self.loc
		return f"{lat: .6f}, {lon:.6f}"

	@property
	def lat(self):
		return self.loc[0]

	@property
	def lon(self):
		return self.loc[1]

	@property
	def dashboardPath(self) -> Path | None:
		path = self['Display']['dashboard']
		if not path:
			return None
		userSaves = self.userPath['saves']['dashboards']
		p = Path(path)
		if p.parent == Path():
			p = userSaves.path / path
		return p.absolute()

	@dashboardPath.setter
	def dashboardPath(self, path: Path):
		userSaves = self.userPath['saves']['dashboards'].path
		if str(path.absolute()).startswith(str(userSaves)):
			path = path.relative_to(userSaves)
		self['Display']['dashboard'] = str(path)
		with open(self.path.path, 'w') as f:
			self.write(f)

def hostZoneName() -> str | None:
	"""The IANA name of the zone this machine's clock is set to (`America/New_York`), or None."""
	if (name := os.environ.get('TZ', '').lstrip(':')) and 'zoneinfo/' not in name:
		return name
	try:
		target = os.path.realpath('/etc/localtime')
	except OSError:
		return None
	_, found, name = target.partition('zoneinfo/')
	return name if found and name else None


userConfig = Config()
pluginConfig = userConfig.plugins
os.environ['UNITCORN_CONFIG_PATH'] = str(userConfig.path.absolute())


def _applyUnitsConfig() -> None:
	"""Make unitcorn use this config, whatever was imported first.

	unitcorn reads `UNITCORN_CONFIG_PATH` once, when it is first imported. If anything
	imported it before the line above, it kept its own default file, and whether a
	value came out in the units this config asks for depended on import order and
	thread timing. Reading the file explicitly removes the order from it.
	"""
	from unitcorn.config import config as unitsConfig
	path = str(userConfig.path.absolute())
	if str(unitsConfig.path) != path:
		unitsConfig.read(path)


_applyUnitsConfig()

__all__ = ['userConfig', 'pluginConfig']
