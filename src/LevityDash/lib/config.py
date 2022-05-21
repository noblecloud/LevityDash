import os
import re
from configparser import ConfigParser
from functools import cached_property
from pathlib import Path, PosixPath, PurePath
from shutil import copy, copytree
from typing import Union

from pytz import timezone

from . import EasyPath as EasyPath


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


def guessLocation() -> tuple[str, str, str]:
	from LevityDash.lib.utils.shared import simpleRequest

	location = simpleRequest('https://ipapi.co/json/')

	log.info(f'Location fetched from IP: {location["city"]}, {location["region"]}, {location["country"]}, lat: {location["latitude"]},  lon: {location["longitude"]}')
	return location['latitude'], location['longitude'], location['timezone']


class LevityConfig(ConfigParser):
	fileName: str

	def __init__(self, *args, **kwargs):
		path = getattr(self, 'fileName', None) or kwargs.pop('fileName', None) or kwargs.pop('path', None) or None
		configSection = kwargs.pop('fromSection', None) or kwargs.pop('section', None) or kwargs.pop('config', None) or None
		super(LevityConfig, self).__init__(allow_no_value=True, *args, **kwargs)
		self.optionxform = str
		from LevityDash import __dirs__
		dirs = __dirs__

		userPath = Path(dirs.user_config_dir)
		if not userPath.exists():
			# log.info(f'Creating user config directory: {userPath}')
			copytree(self.rootPath['example-config'].path, userPath)

		self.userPath = userPath

		if path is not None:
			self.path = self.userPath[path]
			if not self.path.exists():
				example = self.rootPath[self.exampleFileName]
				if not example.exists():
					raise FileNotFoundError(f'Example file not found: {example}')
				copy(example, self.path)
			self.read(self.path.path)
		elif configSection is not None:
			self.read_dict({'Config': dict(configSection)})

	@cached_property
	def rootPath(self) -> EasyPath.EasyPath:
		from LevityDash import __lib__
		return EasyPath.EasyPath(__lib__.parent)

	def save(self):
		with self.path.path.open('w') as f:
			self.write(f)

	@property
	def userPath(self):
		return self.__userPath

	@userPath.setter
	def userPath(self, value):
		match value:
			case EasyPath.EasyPath():
				pass
			case str() | Path() | PosixPath() | PurePath():
				value = EasyPath.EasyPath(value)
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


class PluginsConfig(LevityConfig):
	fileName: str = 'plugins/plugins.ini'

	@property
	def enabledPlugins(self):
		enabled = set()
		for plugin in self.sections():
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
		# x = {name: LevityConfig(path=pluginDir['config.ini'].path if isinstance(pluginDir, dict) else LevityConfig(path=pluginDir.path)) for name, pluginDir in configsDir.items() if 'config.ini' in pluginDir or '.ini' in name}
		for name, pluginDir in configsDir.items():
			if '.ini' in name and name != 'plugins.ini':
				result[name.strip('.ini')] = LevityConfig(path=pluginDir.path)
			elif isinstance(pluginDir, dict) and 'config.ini' in pluginDir.keys():
				result[name] = LevityConfig(path=pluginDir['config.ini'].path)

		return result

	@property
	def userPlugins(self) -> dict[str, dict[str, EasyPath.EasyPath] | EasyPath.EasyPathFile]:
		pluginsDir = self.userPath['plugins'].asDict(depth=1)
		result = {}

		for name, pluginDir in pluginsDir.items():
			if '.py' in name and name != 'plugins.py':
				result[name.strip('.py')] = pluginDir
			elif isinstance(pluginDir, dict) and '__init__.py' in pluginDir.keys():
				result[name] = pluginDir['__init__.py']

		return result

	@property
	def userPluginsDir(self) -> EasyPath.EasyPath:
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
		return self.__parseValue(value)

	def __getattr__(self, item):
		if item != '_defaults':
			validKeys = super(PluginConfig, self).defaults()
			if item in validKeys:
				return self[item]
		return super(PluginConfig, self).__getattribute__(item)

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

	def __init__(self, *args, **kwargs):
		super(Config, self).__init__(*args, **kwargs)

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
	def dashboardPath(self) -> Path:
		path = self['Display']['dashboard']
		userSaves = self.userPath['saves']['dashboards']
		if path in userSaves:
			return userSaves[path].path.absolute()
		return Path(path).absolute()

	@dashboardPath.setter
	def dashboardPath(self, path: Path):
		userSaves = self.userPath['saves']['dashboards'].path
		if str(path.absolute()).startswith(str(userSaves)):
			path = path.relative_to(userSaves)
		self['Display']['dashboard'] = path
		with open(self.path.path, 'w') as f:
			self.write(f)


userConfig = Config()
pluginConfig = userConfig.plugins
os.environ['WU_CONFIG_PATH'] = str(userConfig.path.absolute())

__all__ = ['userConfig', 'pluginConfig']
