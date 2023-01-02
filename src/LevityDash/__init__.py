import argparse
import os
from argparse import ArgumentParser
from types import ModuleType
from typing import Type, TYPE_CHECKING, ClassVar

from . import shims

import builtins

import sys
from functools import cached_property
from pathlib import Path
from appdirs import AppDirs

__version__ = "0.2.0-beta.2"

if sys.version_info < (3, 10, 0):
	sys.exit(
		"Python 3.10 or later is required. "
		"See https://LevityDash.app/gettinhg-started"
		"for installation instructions."
	)

if TYPE_CHECKING:
	from PySide6.QtCore import QThread


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


class _LevityArgParser(ArgumentParser):

	def __init__(self, *args, **kwargs):
		kwargs.update(
			{
				'prog': "levitydash-cli",
				'epilog': "For more information, see https://LevityDash.app",
				'exit_on_error': False,
			}
		)
		super(_LevityArgParser, self).__init__(*args, **kwargs)
		self.__add_args()
		self.__add_logging_parsers()
		self.parse_known_args()

	def __add_args(self):
		self.add_argument('--reset-config', action='store_true', help='Reset the configuration directory to default')
		self.add_argument('--version', action='version', version=f'%(prog)s {__version__}')

	def __add_logging_parsers(self):
		self.logging_group = self.add_argument_group('logging', 'Logging options')


class _LevityDashboard(object):
	args: _LevityArgParser = _LevityArgParser()
	parsed_args: argparse.Namespace = args.parse_known_args()

	__version__ = __version__
	__slots__ = ('app', '__lib', 'config', 'pluginConfig', 'plugins', 'dispatcher',
							 'log', 'get_channel', 'get_container', 'clock', 'status_bar', 'splash',
							 'main_window', 'view', 'plugin_config', 'pluginPool', 'pluginThread',
							 'main_action_pool', 'main_thread_pool', 'CENTRAL_PANEL', 'scene',
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
	isBuilding: bool = os.getenv("LEVITY_BUILDING", "FALSE") == "TRUE"

	if not isBuilding and isCompiled:
		root = Path(sys._MEIPASS) / 'LevityDash'
		from datetime import datetime
		compile_date = datetime.now()
		__version__ = f'{__version__} (Compiled {compile_date:%X on %x})'
	else:
		root = Path(__file__).parent

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

	@classmethod
	def parse_args(cls):
		cls.parsed_args = cls.args.parse_known_args()[0]

	def update_args(self):
		self.args.parse_args()

	def build_imports(self):
		import LevityDash.lib.plugins.builtin
		print("Builtins loaded")



LevityDashboard = _LevityDashboard()
builtins.LevityDashboard = LevityDashboard

__all__ = ["__version__", "LevityDashboard"]
del AppDirs, Path, sys, cached_property, builtins
