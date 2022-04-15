import pkgutil

import logging

pluginLog = logging.getLogger(f'Plugins')

from typing import Any, Dict, Iterator, List, Type
import importlib as imp

from src import config
from src.plugins.plugin import *


class Singleton(type):
	__instances: Dict[str, Any] = {}

	def __new__(cls, name, bases, attrs):
		if name not in cls.__instances:
			cls.__instances[name] = super().__new__(cls, name, bases, attrs)
		return cls.__instances[name]


class Plugins(metaclass=Singleton):
	pluginConfig = config.plugins
	__instance: 'Plugins'
	__plugins: Dict[str, Plugin] = {}

	def __init__(self):
		# find all the plugins that are enabled in the config
		enabledPlugins = set(self.pluginConfig.enabledPlugins)
		enabledPlugins.intersection_update(self.allPlugins())
		pluginsToInit = {name: self.__loadPlugin(name) for name in enabledPlugins}
		for name, plugin in pluginsToInit.items():
			if plugin is None:
				continue
			pluginInstance = plugin.__plugin__()
			self.__plugins[name] = pluginInstance
			pluginLog.info(f'Loaded plugin {name}')
		pluginLog.info(f'Loaded {len(self.__plugins)} plugins')

	def start(self):
		if self.pluginConfig.getboolean('Options', 'enabled'):
			print('--------------------- Starting plugins ---------------------')
			for plugin in self:
				plugin.start()
			print('---------------------Plugins started ---------------------')

	@staticmethod
	def allPlugins() -> Iterator:
		def recursiveSearch(paths: List[str]) -> Iterator:
			plugins = (i for i in pkgutil.iter_modules(paths))
			for _, name, ispkg in plugins:
				# if ispkg:
				# 	yield from recursiveSearch([f'{path}/{name}' for path in paths])
				# else:
				yield name

		pluginDirs = []
		pluginDirs.append(__path__[0] + '/builtin')
		userPluginDir = config.userPath.joinpath('plugins')
		if userPluginDir.exists():
			pluginDirs.append(str(userPluginDir))

		return recursiveSearch(pluginDirs)

	def __loadPlugin(self, name: str) -> Plugin:
		if name in self.__plugins:
			return self.__plugins[name]
		try:
			name = f'src.plugins.builtin.{name}'
			plugin = imp.import_module(name, f'{__path__[0]}/builtin/{name}.py')
		except FileNotFoundError:
			plugin = imp.import_module(name, f'{config.userPath.joinpath("plugins")}/{name}.py')
		except Exception as e:
			pluginLog.error(f'Failed to load plugin {name}: {e}')
			return None
		return plugin

	def __getitem__(self, item: str) -> Plugin:
		return self.__plugins[item]

	def __iter__(self) -> Iterator[Plugin]:
		return iter(self.__plugins.values())

	def __len__(self) -> int:
		return len(self.__plugins)

	def __contains__(self, item: str) -> bool:
		return item in self.__plugins

	def __getattr__(self, item: str) -> Plugin:
		if item in self.__plugins:
			return self.__plugins[item]
		return super().__getattribute__(item)

	def __dir__(self) -> Iterator[str]:
		return iter(self.__plugins.keys())


Plugins = Plugins()
