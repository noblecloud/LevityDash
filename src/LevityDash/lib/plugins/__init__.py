import asyncio
import pkgutil
from typing import Any, ClassVar, Dict, Iterator, List, Optional

from LevityDash.lib.log import LevityPluginLog as pluginLog
from LevityDash.lib.plugins.utils import *
from LevityDash.lib.config import pluginConfig
from LevityDash.lib.plugins import categories
from LevityDash.lib.plugins import translator
from LevityDash.lib.plugins import observation
from LevityDash.lib.plugins.plugin import Plugin


class Singleton(type):
	instances: Dict[str, Any] = {}

	def __new__(cls, name, bases, attrs):
		if name not in cls.instances:
			cls.instances[name] = super().__new__(cls, name, bases, attrs)()
		return cls.instances[name]


class Plugins(metaclass=Singleton):
	instance: ClassVar['Plugins'] = None
	__plugins: Dict[str, Plugin] = {}

	def __init__(self):
		# find all the plugins that are enabled in the config
		enabledPlugins = set(pluginConfig.enabledPlugins)
		enabledPlugins.intersection_update(self.allPlugins())
		pluginsToInit = {name: self.__loadPlugin(name) for name in enabledPlugins}

		for name, plugin in pluginsToInit.items():
			if plugin is None:
				continue
			try:
				pluginInstance = plugin.__plugin__()
				self.__plugins[name] = pluginInstance
				pluginLog.info(f'Loaded plugin {name}')
			except Exception as e:
				pluginLog.debug(f'Unable to load {name} due to exception --> {e}')
		pluginLog.info(f'Loaded {len(self.__plugins)} plugins')

	def start(self):
		if pluginConfig['Options'].getboolean('enabled'):
			print('--------------------- Starting plugins ---------------------')
			asyncio.gather(*[plugin.asyncStart() for plugin in self])

	# for plugin in self:
	# 	print(f'Starting plugin {plugin.name}')
	# 	plugin.asyncStart()
	# asyncio.get_event_loop().run_in_executor(None, plugin.start)

	# print('---------------------Plugins started ---------------------')

	@staticmethod
	def allPlugins() -> Iterator[str]:
		def search(paths: List[str]) -> Iterator:
			plugins = (i for i in pkgutil.iter_modules(paths))
			for _, name, ispkg in plugins:
				print(f'Found plugin {name}')
				yield name

		from LevityDash import __lib__
		pluginDirs = [f'{__lib__}/plugins/builtin']

		return search(pluginDirs)

	def __loadPlugin(self, name: str) -> Optional[Plugin]:
		from LevityDash import __lib__
		if name in self.__plugins:
			return self.__plugins[name]
		builtinNamespace = f'LevityDash.lib.plugins.builtin'
		try:
			exec(f'from {builtinNamespace} import {name}')
		except Exception as e:
			pluginLog.error(f'Failed to load plugin {name}: {e}')
			return
		return locals()[name]

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


def __getattr__(item: str) -> Plugin:
	return getattr(Plugins, item, None) or super().__getattribute__(item)
