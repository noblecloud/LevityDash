from src import logging
from configparser import ConfigParser
from functools import cached_property
from pathlib import Path
from shutil import copy
from typing import Union

from pytz import timezone


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


class LevityConfig(ConfigParser):
	fileName: str

	def __init__(self, *args, **kwargs):
		super(LevityConfig, self).__init__(allow_no_value=True, *args, **kwargs)
		self.userPath = Path.home().joinpath('.config', 'levity')
		if not self.userPath.exists():
			self.userPath.mkdir(parents=True)
		if hasattr(self, 'fileName'):
			self.path = self.userPath.joinpath(self.fileName)
			if not self.path.exists():
				example = self.rootPath.path.joinpath(self.exampleFileName)
				if not example.exists():
					raise FileNotFoundError(f'Example file not found: {example}')
				copy(example, self.path)
		self.read(self.path)

	@property
	def exampleFileName(self):
		l = self.fileName.split('.')
		l[-2] = f'{l[-2]}-example'
		return '.'.join(l)

	@cached_property
	def rootPath(self) -> 'EasyPath':
		from src.utils import EasyPath
		path = Path(__file__).parent
		while path is not None and not 'levity.py' in [x.name for x in path.iterdir()]:
			if path.parent.owner() == 'root':
				return path
			path = path.parent
		return EasyPath(path)


class PluginsConfig(LevityConfig):
	fileName: str = 'plugins.ini'

	@property
	def enabledPlugins(self):
		enabled = []
		for plugin in self.sections():
			if self[plugin].getboolean('enabled'):
				enabled.append(plugin)
		return enabled

	@property
	def wf(self):
		return self['WeatherFlow']

	@property
	def aw(self):
		return self['AmbientWeather']

	@property
	def tmrrow(self):
		return self['TomorrowIO']

	@property
	def solcast(self):
		return self['Solcast']


class Config(LevityConfig):
	fileName: str = 'config.ini'

	def __init__(self, *args, **kwargs):
		super(Config, self).__init__(*args, **kwargs)
		## make directories
		baseDirectory = self.userPath
		directories = {'saves': ['dashboards', 'panels'], 'templates': ['dashboards', 'panels']}
		buildDirectories(baseDirectory, directories)

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
			logging.error('Unable load timezone from config\n', e)

	@property
	def loc(self):
		return float(self['Location']['lat']), float(self['Location']['lon'])

	@property
	def locStr(self):
		return f"{float(self['Location']['lat'])}, {float(self['Location']['lon'])}"

	@property
	def lat(self):
		return float(self['Location']['lat'])

	@property
	def lon(self):
		return float(self['Location']['lon'])

	@property
	def dashboardPath(self):
		path = self['MetaData']['filepath']
		if path is not None:
			return Path(path).expanduser()
		return None

	@dashboardPath.setter
	def dashboardPath(self, path: Path):
		user = Path('~/').expanduser()
		self['MetaData']['filepath'] = str(path).replace(str(user), '~')
		with open(self.path, 'w') as f:
			self.write(f)


config = Config()
