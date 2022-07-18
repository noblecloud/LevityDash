import os
import platform
import re
from configparser import ConfigParser, SectionProxy, ParsingError, ExtendedInterpolation
from datetime import timedelta
from functools import cached_property
from logging import getLogger, Logger
from pathlib import Path, PosixPath, PurePath
from re import search
from shutil import copytree
from typing import Union, Callable, Any, ClassVar

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QInputDialog, QWidget, QMessageBox, QLineEdit
from pytz import timezone
from qasync import QApplication

from .EasyPath import EasyPathFile, EasyPath

_backupLogger = getLogger('LevityConfig')


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
			path.par
			subpath = path.joinpath(dir)
			if not subpath.exists():
				subpath.mkdir()


unsetConfig = object()

DATETIME_NO_ZERO_CHAR = '#' if platform.system() == 'Windows' else '-'


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

		from LevityDash import __dirs__
		dirs = __dirs__

		userPath = Path(dirs.user_config_dir)
		if not userPath.exists():
			self.log.info(f'Creating user config directory: {userPath}')
			copytree(self.rootPath['example-config'].path, userPath)

		self.userPath = userPath

		if path is not None:
			self.path = self.userPath[path]
			self.read(self.path.path)

		for sectionName, section in self._sections.items():
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
		message = value['message']
		if askType == 'askChoose':
			choices = value['value']
			choices = re.findall(r'\w+', choices)
		elif (default := value['value']) is not None:
			choices = [default]
		else:
			choices = None
		if askType == 'askInput':
			message = message or ''
			default = choices[0] if choices is not None else ''
			if valueType is bool:
				default = default.lower() in ('true', 't', '1', 'y', 'yes')
				result = QMessageBox(QWidget()).question(QWidget(),
					self.path.name,
					message,
					QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes if default else QMessageBox.No,
				) == QMessageBox.Yes
				return result
			if valueType is str:
				return QInputDialog.getText(QWidget(), self.path.name, message, QLineEdit.Normal, default)[0]
			if valueType is int:
				try:
					default = int(default)
				except ValueError:
					pass
				return QInputDialog.getInt(QWidget(), self.path.name, message, default)[0]
			if valueType is float:
				try:
					default = float(default)
				except ValueError:
					pass
				return QInputDialog.getDouble(QWidget(), self.path.name, message, default)[0]
		elif askType == 'askChoose':
			message = message or ''
			if choices is not None:
				return QInputDialog.getItem(QWidget(), self.path.name, message, choices, 0, 'custom' in choices)[0]

		print(value)

	@classmethod
	@property
	def log(cls):
		return getattr(cls, '_log', None)

	@classmethod
	def setLogger(cls, value):
		cls._log = value

	@cached_property
	def rootPath(self) -> EasyPath:
		from LevityDash import __lib__
		return EasyPath(__lib__.parent)

	def save(self):
		with self.path.path.open('w') as f:
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
				section = self._defaults
			else:
				section = self[section]
		except KeyError:
			self.add_section(section)

		if getter == self.getboolean:
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
				return _val*1024
			case 'm' | 'mb' | 'megabyte' | 'megabytes':
				return _val*1024 ** 2
			case 'g' | 'gb' | 'gigabyte' | 'gigabytes':
				return _val*1024 ** 3
			case '_val' | 'tb' | 'terabyte' | 'terabytes':
				return _val*1024 ** 4
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
	fileName: str = 'plugins/plugins.ini'

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
			if '.ini' in name and name != 'plugins.ini':
				result[name.strip('.ini')] = LevityConfig(path=pluginDir.path)
			elif isinstance(pluginDir, dict) and 'config.ini' in pluginDir.keys():
				result[name] = LevityConfig(path=pluginDir['config.ini'].path)

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

	def __init__(self, *args, **kwargs):
		self.__plugin = kwargs.pop('plugin', None)
		self.log = self.__plugin.pluginLog.getChild('Config')
		super(PluginConfig, self).__init__(*args, **kwargs, default_section='Config')

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
				mainConfig = userConfig.plugins[self.__plugin.name]
				if key in mainConfig:
					value = mainConfig[key]
			except KeyError:
				pass
		if value == '':
			self.log.critical(f'No value for {key} in config for {self.__plugin.name}')
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
				value = Prompt.ask(f'{self.__plugin.name} requires \'{key}\' to continue.  Please enter a value.\n{key}')
			self[self.default_section][key] = value
			self.save()

	@cached_property
	def defaultFor(self):
		if 'defaultFor' in self.defaults():
			return set(re.findall(rf"[\w|\-]+", self['defaultFor']))
		return set()

	@property
	def plugin(self) -> 'Plugin':
		return self.__plugin


class Config(LevityConfig):
	fileName: str = 'config.ini'

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
			lat, lon, tz = guessLocation()
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
		if path in userSaves:
			return userSaves[path].path.absolute()
		return Path(path).absolute()

	@dashboardPath.setter
	def dashboardPath(self, path: Path):
		userSaves = self.userPath['saves']['dashboards'].path
		if str(path.absolute()).startswith(str(userSaves)):
			path = path.relative_to(userSaves)
		self['Display']['dashboard'] = str(path)
		with open(self.path.path, 'w') as f:
			self.write(f)

userConfig = Config()
pluginConfig = userConfig.plugins
os.environ['WU_CONFIG_PATH'] = str(userConfig.path.absolute())

__all__ = ['userConfig', 'pluginConfig']
