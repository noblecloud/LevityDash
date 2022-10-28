import pkgutil
from dataclasses import dataclass, field
from importlib import import_module
from types import ModuleType
from typing import Any, ClassVar, Dict, Hashable, Iterator, Optional, Type

from PySide2.QtNetwork import QNetworkConfigurationManager

from LevityDash import LevityDashboard
from LevityDash.lib.config import pluginConfig
from LevityDash.lib.log import LevityPluginLog as pluginLog
from LevityDash.lib.plugins import categories, errors, observation, schema
from LevityDash.lib.plugins.utils import Request, GuardedRequest
from LevityDash.lib.plugins.observation import Container
from LevityDash.lib.plugins.plugin import AnySource, Plugin, SomePlugin
from LevityDash.lib.plugins.dispatcher import PluginValueDirectory
from LevityDash.lib.utils import PluginPool, PluginThread, UnsetKwarg

Plugins: 'PluginsLoader'

@dataclass
class PluginData:
	name: str = field(hash=True)
	instance: Plugin = field(repr=False)
	thread: PluginThread = field(default=None, hash=False, repr=False, init=False)
	requires: Optional[Dict[str, Any]] = field(default_factory=dict, hash=False, repr=False)

	def __post_init__(self):
		self.thread = self.instance.thread


class GlobalSingleton(type):
	instances: ClassVar[Dict[str, Any]] = {}
	__root: ClassVar[ModuleType]

	def __new__(mcs, clsName, bases, attrs, **kwargs):
		name = kwargs.get('name', None) or clsName
		if name not in mcs.instances:
			instance = super().__new__(mcs, name, bases, attrs)()
			if (root := mcs.root) is not None:
				root.__setattr__(name, instance)
			setattr(LevityDashboard, name, instance)
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


class PluginsLoader(metaclass=GlobalSingleton, name='plugins'):
	instance: ClassVar['Plugins'] = None
	network_available: bool
	network_manager = QNetworkConfigurationManager()
	network_changed = network_manager.onlineStateChanged
	plugins_thread_pool: ClassVar[PluginPool] = PluginPool()

	_plugin_workers: ClassVar[Dict[Plugin, PluginThread]] = {}

	__plugin_instances: Dict[str, Plugin] = {}
	__plugins: Dict[str, Type[Plugin]] = {}
	__defaultConfigs: ClassVar[Dict[Plugin, Any]] = {}

	def __init__(self):
		self.dispatcher = PluginValueDirectory(self)

	def load_all(self):
		for name in self.allPlugins():
			try:
				plugin_ = self._loadPluginModule(name)
			except errors.PluginDisabled as e:
				continue
			except errors.PluginError as e:
				pluginLog.exception(e)
				continue
			if plugin_ is None:
				continue
			try:
				pluginInstance = plugin_()
				pluginInstance.manager = self
				self.dispatcher.connect_plugin(pluginInstance)
				self.__plugin_instances[name] = pluginInstance
				statusColor = 'green' if pluginInstance.enabled else 'red'
				pluginLog.info(f'Loaded plugin [{statusColor}]{name}[/{statusColor}]')
			except ImportError as e:
				pluginLog.debug(f'Unable to load {name} due to exception --> {e}')
				continue
		pluginLog.info(f'Loaded {len(self.__plugin_instances)} plugins')

	def start(self):
		pluginLog.info(' Starting Plugins '.center(80, '-'))
		plugin_threads = [i for i in self if i.enabled]
		for plugin_ in plugin_threads:
			plugin_.thread.start()
		pluginLog.info(' Thread Pool Started '.center(80, '-'))

	def stop(self):
		pluginLog.info('--------------------- Stopping plugins ---------------------')
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

		pluginDirs = [str(LevityDashboard.paths.builtin_plugins.absolute())]

		return (i.name for i in pkgutil.iter_modules(pluginDirs))

	def _loadPluginModule(self, name: str) -> Type[Plugin] | errors.PluginError:
		if name in self.__plugin_instances:
			pluginLog.debug(f'Plugin {name} already loaded')
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
			raise e

		except errors.PluginDisabled as e:
			pluginLog.info(f'Plugin {name} is disabled')
			pluginLog.debug(f"{name} tried to load but was disabled with the '__disabled' attribute")
			raise e

		except Exception as e:
			e = errors.PluginError.mix_in_error(e)
			if pluginLog.level <= 10:
				pluginLog.exception(e)
			pluginLog.error(f'Failed to load plugin {name}: {e}')
			raise e

	def __getitem__(self, item: str) -> Plugin:
		return self.__plugin_instances[item]

	def get(self, item: Hashable | str, default: Any = UnsetKwarg) -> Plugin:
		if item == 'any' or item is AnySource or item is SomePlugin:
			return AnySource
		if default is not UnsetKwarg:
			return self.__plugin_instances.get(item, default)
		return self.__plugin_instances.get(item)

	def __iter__(self) -> Iterator[Plugin]:
		return iter(self.__plugin_instances.values())

	def __len__(self) -> int:
		return len(self.__plugin_instances)

	def __contains__(self, item: str) -> bool:
		return item in self.__plugin_instances or item == 'any' or item is SomePlugin

	def __getattr__(self, item: str) -> Plugin:
		if item in self.__plugin_instances:
			return self.__plugin_instances[item]
		return super().__getattribute__(item)

	def __dir__(self) -> Iterator[str]:
		return iter(self.__plugin_instances.keys())

	@property
	def plugins(self) -> Dict[str, Plugin]:
		return self.__plugin_instances

	@property
	def enabled_plugins(self):
		return {p for p in self.__plugin_instances.values() if p.enabled}


def __getattr__(item: str) -> Plugin:
	return getattr(LevityDashboard.plugins, item, None) or locals()[item]
