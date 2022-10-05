import asyncio
import pkgutil
from importlib import import_module
from types import ModuleType
from typing import Any, ClassVar, Dict, Hashable, Iterator, Optional

import builtins
from PySide2.QtCore import Qt
from PySide2.QtNetwork import QNetworkConfigurationManager

from LevityDash.lib.config import pluginConfig
from LevityDash.lib.log import LevityPluginLog as pluginLog
from LevityDash.lib.plugins import categories, errors, observation, schema
from LevityDash.lib.plugins.observation import Container
from LevityDash.lib.plugins.plugin import AnySource, Plugin, SomePlugin
from LevityDash.lib.plugins.utils import *
from LevityDash.lib.utils import Pool, UnsetKwarg

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
			setattr(builtins, name, instance)
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
	network_available: bool
	network_manager = QNetworkConfigurationManager()
	network_changed = network_manager.onlineStateChanged
	plugins_thread_pool: ClassVar[Pool] = Pool()

	__plugins: Dict[str, Plugin] = {}
	__defaultConfigs: ClassVar[Dict[Plugin, Any]] = {}

	def __init__(self):
		# find all the plugins that are enabled in the config
		allPlugins = self.allPlugins()
		pluginsToInit = {name: self._loadPlugin(name) for name in allPlugins}
		self._plugin_workers: Dict[str, PluginWorker] = {}

		for name, plugin_ in pluginsToInit.items():
			if plugin_ is None:
				continue
			try:
				pluginInstance = plugin_()
				pluginInstance.manager = self
				self.__plugins[name] = pluginInstance
				statusColor = 'green' if pluginInstance.enabled else 'red'
				pluginLog.info(f'Loaded plugin [{statusColor}]{name}[/{statusColor}]')
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
			pluginLog.info('Starting Plugins')
			asyncio.gather(*(plugin_.asyncStart() for plugin_ in self if plugin_.enabled))

	def stop(self):
		print('--------------------- Stopping plugins ---------------------')
		for plugin in self:
			if plugin.running:
				plugin.stop()

	@property
	def network_available(self) -> bool:
		return PluginsLoader.network_manager.isOnline()

	def on_network_availility_change(self, available: bool):
		if available and pluginConfig['Options'].getboolean('enabled') and self.network_available is None:
			asyncio.gather(*(plugin_.asyncStart() for plugin_ in self if plugin_.enabled))
		print(f'plugins Network availability changed to {available}')

	@staticmethod
	def allPlugins() -> Iterator[str]:

		from LevityDash import __lib__
		pluginDirs = [f'{__lib__}/plugins/builtin']

		return (i.name for i in pkgutil.iter_modules(pluginDirs))

	def _loadPlugin(self, name: str) -> Optional[Plugin]:
		if name in self.__plugins:
			return self.__plugins[name]
		try:
			pluginModule = import_module(f'LevityDash.lib.plugins.builtin.{name}')

			if hasattr(pluginModule, '__disabled__'):
				raise errors.PluginDisabled(f'Plugin {name} is disabled')

			if (plugin_ := getattr(pluginModule, '__plugin__', None)) is None:
				raise errors.MissingPluginDeclaration

			if (defaultConfig := getattr(pluginModule, 'defaultConfig', None)) is not None:
				self.__defaultConfigs[plugin_] = defaultConfig

			return plugin_

		except errors.MissingPluginDeclaration as e:
			pluginLog.error(
				f'Unable to load {name} because it is missing the __plugin__ declaration.  '
				f'Please ensure that the plugin uses __plugin__ as a reference to the plugin class.'
			)
		except errors.PluginDisabled as e:
			pluginLog.info(f'Plugin {name} is disabled')

		except Exception as e:
			if pluginLog.level <= 10:
				pluginLog.exception(e)
			pluginLog.error(f'Failed to load plugin {name}: {e}')

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
