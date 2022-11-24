import os
from types import ModuleType
from typing import Type, TYPE_CHECKING

from . import shims

import builtins

import sys
from functools import cached_property
from pathlib import Path
from appdirs import AppDirs

__version__ = "0.2.0-beta.1"

if sys.version_info < (3, 10, 0):
	sys.exit(
		"Python 3.10 or later is required. "
		"See https://LevityDash.app/gettinhg-started"
		"for installation instructions."
	)

if TYPE_CHECKING:
	from PySide2.QtCore import QThread


class _LevityAppDirs(AppDirs):
	root: Path
	lib: Path
	resources: Path
	shims: Path

	if CONFIG_DEBUG := int(os.environ.get("LEVITYDASH_CONFIG_DEBUG", 0)):

		from tempfile import TemporaryDirectory

		user_data_temp_dir = TemporaryDirectory(prefix="levitydash-user-data-")
		data: Path = Path(user_data_temp_dir.name)

		config_temp_dir = TemporaryDirectory(prefix="levitydash-config-")
		config: Path = Path(config_temp_dir.name)

		cache_temp_dir = TemporaryDirectory(prefix="levitydash-cache-")
		cache: Path = Path(cache_temp_dir.name)

		log: Path = AppDirs.user_log_dir

		site_data_temp_dir = TemporaryDirectory(prefix="levitydash-site-data-")
		site_data: Path = Path(site_data_temp_dir.name)

		site_config_temp_dir = TemporaryDirectory(prefix="levitydash-site-config-")
		site_config: Path = Path(site_config_temp_dir.name)

	else:
		data: Path = AppDirs.user_data_dir
		config: Path = AppDirs.user_config_dir
		cache: Path = AppDirs.user_cache_dir
		log: Path = AppDirs.user_log_dir
		site_data: Path = AppDirs.site_data_dir
		site_config: Path = AppDirs.site_config_dir

	def __init__(self, root: Path):
		super().__init__(appname="LevityDash", appauthor="LevityDash.app")
		self.root = root
		self.lib = root / "lib"
		self.resources = root / "resources"
		self.shims = self.lib / "shims"
		self.user_plugins = Path(self.site_data) / "plugins"
		self.builtin_plugins = self.lib / "plugins" / "builtin"


class _LevityDashboard(object):

	__version__ = __version__
	__slots__ = ('app', '__lib', 'config', 'pluginConfig', 'plugins', 'dispatcher',
							 'log', 'get_channel', 'get_container', 'clock', 'status_bar', 'splash',
							 'main_window', 'view', 'plugin_config', 'pluginPool', 'pluginThread',
							 'main_action_pool', 'main_thread_pool', 'CENTRAL_PANEL','scene',
							 'load_dashboard', 'main_thread')

	plugins: 'LevityDashboard.lib.PluginsLoader'
	dispatcher: 'LevityDashboard.lib.PluginValueDirectory'
	config: 'LevityDashboard.lib.config.Config'
	plugin_config: 'LevityDashboard.lib.config.PluginConfig'
	log: Type['LevityDashboard.lib.log.LevityLogger']
	app: 'LevityDashboard.lib.ui.PySide.LevityDashApp'
	splash: 'LevityDashboard.lib.ui.PySide.SplashScreen'
	main_thread_pool: 'LevityDashboard.lib.utils.shared.Pool'
	main_thread: 'QThread'

	__lib: ModuleType

	isCompiled: bool = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
	root = Path(__file__).parent.parent if isCompiled else Path(__file__).parent
	paths = _LevityAppDirs(root)

	resources = paths.resources
	shims = shims

	def __setattr__(self, key, value):
		if key in self.__slots__:
			try:
				getattr(self, key)
			except AttributeError:
				return super().__setattr__(key, value)
		raise TypeError("LevityDashboard is immutable")

	def init(self):
		import LevityDash.lib
		object.__setattr__(self, '_LevityDashboard__lib', LevityDash.lib)

	@property
	def lib(self):
		return self.__lib


LevityDashboard = _LevityDashboard()
builtins.LevityDashboard = LevityDashboard

__all__ = ["__version__", "LevityDashboard"]
del AppDirs, Path, sys, cached_property, builtins
