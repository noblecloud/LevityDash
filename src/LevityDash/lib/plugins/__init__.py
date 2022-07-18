import asyncio
import pkgutil
from types import ModuleType
from typing import Any, ClassVar, Dict, Iterator, List, Optional, Hashable

from PySide2.QtCore import Qt

from LevityDash.lib.plugins.utils import *
from LevityDash.lib.plugins import errors
from LevityDash.lib.log import LevityPluginLog as pluginLog
from LevityDash.lib.config import pluginConfig
from LevityDash.lib.plugins import categories
from LevityDash.lib.plugins import schema
from LevityDash.lib.plugins import observation
from LevityDash.lib.plugins.observation import Container
from LevityDash.lib.plugins.plugin import Plugin, AnySource, SomePlugin
from LevityDash.lib.utils import UnsetKwarg

Plugins: 'PluginsLoader' = None


class GlobalSingleton(type):
	instances: ClassVar[Dict[str, Any]] = {}
	__root: ClassVar[ModuleType]

	def __new__(mcs, clsName, bases, attrs, **kwargs):
		name = kwargs.get('name', None) or clsName
		if name not in mcs.instances:
			instance = super().__new__(mcs, name, bases, attrs)()
			if (root := mcs.root) is not None:
				root.__setattr__(name, instance)
			globals()[name] = instance
			mcs.instances[name] = instance
		return mcs.instances[name]

	@classmethod
	@property
	def root(mcs):
		try:
			return mcs.__root
		except AttributeError:
			try:
				import LevityDash as root
				mcs.__root = root
				root.singletons = mcs
				return mcs.__root
			except ImportError:
				return None


class PluginsLoader(metaclass=GlobalSingleton, name='Plugins'):
	instance: ClassVar['Plugins'] = None
	__plugins: Dict[str, Plugin] = {}
	Plugin = Plugin

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
			except ImportError as e:
				pluginLog.debug(f'Unable to load {name} due to exception --> {e}')
				continue
		pluginLog.info(f'Loaded {len(self.__plugins)} plugins')

	def start(self):
		keyboardModifiers = qApp.queryKeyboardModifiers()
		if keyboardModifiers & Qt.AltModifier:
			print('Alt is pressed, skipping plugins')
			return
		if pluginConfig['Options'].getboolean('enabled'):
			print('--------------------- Starting plugins ---------------------')
			asyncio.gather(*(plugin.asyncStart() for plugin in self))

	def stop(self):
		print('--------------------- Stopping plugins ---------------------')
		# asyncio.gather(*(plugin.asyncStop() for plugin in self))
		for plugin in self:
			plugin.stop()

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

	def get(self, item: Hashable | str, default: Any = UnsetKwarg) -> Plugin:
		if item == 'any' or item is AnySource or item is SomePlugin:
			return AnySource
		if default is not UnsetKwarg:
			return self.__plugins.get(item, default)
		return self.__plugins.get(item)

	def __iter__(self) -> Iterator[Plugin]:
		return iter(self.__plugins.values())

	def __len__(self) -> int:
		return len(self.__plugins)

	def __contains__(self, item: str) -> bool:
		return item in self.__plugins or item == 'any' or item is SomePlugin

	def __getattr__(self, item: str) -> Plugin:
		if item in self.__plugins:
			return self.__plugins[item]
		return super().__getattribute__(item)

	def __dir__(self) -> Iterator[str]:
		return iter(self.__plugins.keys())

	@property
	def plugins(self) -> Dict[str, Plugin]:
		return self.__plugins

def __getattr__(item: str) -> Plugin:
	return getattr(Plugins, item, None) or locals()[item]
