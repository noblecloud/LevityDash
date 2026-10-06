import re
from copy import deepcopy
from datetime import datetime
from functools import cached_property
from pathlib import Path
from shutil import copyfile
from tempfile import NamedTemporaryFile
from typing import Any, List

import yaml
from PySide6.QtCore import QRect, Qt, Slot
from PySide6.QtWidgets import QFileDialog, QGraphicsItem, QMessageBox
from time import perf_counter

from LevityDash import LevityDashboard
from LevityDash.lib.config import userConfig
from LevityDash.lib.EasyPath import EasyPathFile
from LevityDash.lib.log import debug
from LevityDash.lib.stateful import StatefulDumper, StateProperty
from LevityDash.lib.variables import resolveVariables, retemplate
from LevityDash.lib.ui.colors import theme
from LevityDash.lib.ui.frontends.PySide.Modules.Menus import CentralPanelContextMenu
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
from LevityDash.lib.utils import BusyContext, ActionPool
from WeatherUnits import Time
from .. import UILogger as guiLog

log = guiLog.getChild(__name__)


class CentralPanel(Panel, tag="dashboard"):
	_keepInFrame = True

	__exclude__ = {'geometry', 'movable', 'resizable', 'locked', 'frozen'}

	__defaults__ = {
		'movable':    False,
		'resizable':  False,
		'locked':     True,
		'fillParent': True,
		'geometry':   {'fillParent': True},
		'margins':    ('0px', '0px', '0px', '0px'),
	}

	def prep_init(self, *args, **kwargs):
		self._set_state_items_ = set()
		self.statefulParent = None

	def __init__(self, parent: 'LevityScene'):
		self._parent = parent
		self._action_pool = ActionPool(self, trace='CentralPanel')
		self.__boundingRect = QRect(-2000, -2000, 6000, 6000)
		self._scene = parent
		super(CentralPanel, self).__init__(None)

		self.setAcceptedMouseButtons(Qt.AllButtons)

		defaultDashboardPath = userConfig.dashboardPath
		try:
			if defaultDashboardPath is not None:
				if not defaultDashboardPath.exists():
					# copy the file from _determine_default_dashboard to defaultDashboardPath
					defaultDashboardPath.parent.mkdir(parents=True, exist_ok=True)
					copyfile(str(self._determine_default_dashboard()), str(defaultDashboardPath))
				self.filePath = EasyPathFile(defaultDashboardPath)
			else:
				self.filePath = None
		except FileNotFoundError:
			self._determine_default_dashboard()
		self.loadedFile: Any = None

		self.setFlag(QGraphicsItem.ItemStopsClickFocusPropagation, False)
		self.setFlag(QGraphicsItem.ItemStopsFocusHandling, False)
		self.setFlag(QGraphicsItem.ItemHasNoContents)
		self.resizeHandles.setVisible(False)
		self.resizeHandles.setEnabled(False)
		self.setFlag(self.GraphicsItemFlag.ItemClipsChildrenToShape, False)
		self.setFlag(self.GraphicsItemFlag.ItemClipsToShape, False)
		self.setFlag(self.GraphicsItemFlag.ItemIsFocusable, False)
		self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)
		self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, False)
		LevityDashboard.CENTRAL_PANEL = self
		LevityDashboard.main_action_pool = self._action_pool

	@Slot()
	def onFileLoaded(self):
		print('FileLoaded')

	def _init_args_(self, *args, **kwargs):
		self._scene.addItem(self)
		super(CentralPanel, self)._init_args_(*args, **kwargs)
		self._parent = self.scene()

	@property
	def parent(self):
		return self.scene()

	@cached_property
	def window(self):
		return self.scene().views()[0]

	@cached_property
	def app(self):
		from PySide6.QtWidgets import QApplication
		return QApplication.instance()

	# def contextMenuEvent(self, event):
	# 	menu = self.contextMenu
	# 	menu.exec_(event.screenPos())

	def mousePresEvent(self, event):
		self.scene().clearSelection()
		super(CentralPanel, self).mousePresEvent(event)

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemPositionChange:
			return QGraphicsItem.itemChange(self, change, value)
		return super(CentralPanel, self).itemChange(change, value)

	@property
	def childPanels(self):
		return [i for i in self.childItems() if isinstance(i, Panel)]

	@StateProperty(singleVal=True, inheritFrom=Panel.items)
	def items(self) -> list[Panel]:
		...

	_theme: Any = None

	@StateProperty(default=None, allowNone=True, sortOrder=-1)
	def theme(self) -> str | dict | None:
		"""The colour theme: a name, or ``{extends: name, colors: {...}}``. Tokens such as ``$accent`` read from it."""
		return self._theme

	@theme.setter
	def theme(self, value: str | dict | None):
		self._theme = value
		theme.activate(value)

	@theme.decode
	def theme(self, value):
		if value is not None and not isinstance(value, (str, dict)):
			raise ValueError(f'theme is a theme name or a mapping, not {value!r}')
		return value

	_background: Any = None

	@StateProperty(key='background', default=None, allowNone=True, sortOrder=-1)
	def background(self) -> str | dict | list | None:
		"""The ground of the board: a colour, a theme token (`$background`, or a scale such as `$sky` for a gradient), or a gradient written in place. `{gradient: $sky, angle: 160}` sets the direction. `lib/ui/colors/backdrop.py`"""
		return self._background

	@background.setter
	def background(self, value):
		self._background = value
		self.scene().backdropSpec = value

	_vars: Any = None
	_written: Any = None
	_resolved: Any = None

	@StateProperty(key='vars', default=None, allowNone=True, sortOrder=-2)
	def variables(self) -> dict | None:
		"""Named values for the file: `vars: {hot: 90°F}`, used as `$hot`. Applied when the file loads (`lib/variables.py`); a save writes the `$name` uses back where the value is unchanged."""
		return self._vars

	@variables.setter
	def variables(self, value: dict | None):
		self._vars = value

	@cached_property
	def contextMenu(self):
		return CentralPanelContextMenu(self)

	def load(self, *_):
		try:
			path = Path(self._selectFile()[0])
		except IndexError:
			return
		self.filePath = EasyPathFile(path)
		self._load(self.filePath)

	def loadDefault(self):
		if self.filePath is None:
			path = Path(self._selectFile()[0])
			self.filePath = EasyPathFile(path)
		self._load(self.filePath)

	def reload(self):
		if self.filePath.exists():
			self._load(self.filePath)
		else:
			QMessageBox.warning(self, "No Dashboard", "There is currently no loaded dashboard to refresh").exec_()

	def loadPanel(self):
		from LevityDash.lib.ui.frontends.PySide.Modules import PanelFromFile
		paths = self._selectFile(fileType="Dashboard Files (*.levityPanel *.json)", startingDir='panels', multipleFiles=True)
		for p in paths:
			PanelFromFile(self, p)

	def _save(self, path: Path = None, fileName: str = None):
		if path is None:
			path = userConfig.userPath.joinpath('saves', 'dashboards')
		if fileName is None:
			fileName = 'default.levity'

		if not path.exists():
			path.mkdir(parents=True)

		from .ErrorTile import ErrorTile
		if any(isinstance(i, ErrorTile) for i in self.scene().items()):
			log.error('Not saved: an item failed to load and a save would delete it from the file. Fix the file and reload.')
			return

		with NamedTemporaryFile(delete=True, mode="w+", encoding='utf-8') as f:
			try:
				state = self.state
				yaml.dump(state, f, Dumper=StatefulDumper, default_flow_style=False, allow_unicode=True)
				if self._vars:
					self._restoreVariables(f)

				YAMLPreprocessor(f)
				copyfile(f.name, str(path.joinpath(fileName)))
				log.info('Saved!')
			except Exception if not debug else DebugException as e:
				log.info('Failed')
				log.exception(e)

	def _restoreVariables(self, f) -> None:
		"""Rewrite the dumped file so `$name` stays where the value is as the file resolved it.

		The dump is read back with the loader that read the file, so the live tree and the
		resolved one have the same shape. Never raises: on any failure the values stay.
		"""
		try:
			f.seek(0)
			live = type(self).__loader__(YAMLPreprocessor(f.read())).get_data()
			merged = retemplate(live, self._resolved, self._written)
			text = yaml.dump(merged, Dumper=StatefulDumper, default_flow_style=False, allow_unicode=True)
			f.seek(0)
			f.truncate()
			f.write(text)
		except Exception:
			log.exception('a save could not restore the variable names; it wrote the values')

	def save(self):
		self._save()

	def saveAs(self):
		dateString = datetime.now().strftime('dashboard.%Y.%m.%d.levity')
		path = userConfig.userPath.joinpath('saves', 'dashboards')

		path = path.joinpath(dateString)
		dialog = QFileDialog(self.parentWidget(), 'Save Dashboard As...', str(path))
		dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
		dialog.setNameFilter("Dashboard Files (*.levity)")
		dialog.setViewMode(QFileDialog.ViewMode.Detail)
		if dialog.exec_():
			fileName = Path(dialog.selectedFiles()[0])
			path = fileName.parent
			fileName = dialog.selectedFiles()[0].split('/')[-1]
			self._save(path, fileName)

	def _determine_default_dashboard(self):
		plugins = LevityDashboard.plugins
		base = LevityDashboard.resources / 'example-config' / 'templates' / 'dashboards'
		if (wf := plugins.get('WeatherFlow', None)) is not None and wf.enabled:
			if (govee := plugins.get('Govee', None)) is not None and govee.enabled:
				return base / 'WeatherFlow-Govee.levity'
			return base / 'WeatherFlow.levity'
		if (om := plugins.get('OpenMeteo', None)) is not None and om.enabled:
			return base / 'OpenMeteo.levity'
		return base / 'Empty.levity'

	def _load(self, path: Path = None):
		name = path.name
		self.scene().view.parentWidget().setWindowTitle(f"Levity Dashboard - {name}")
		log.debug(f"Loading dashboard from {str(path)}")
		if isinstance(path, EasyPathFile):
			path = path.path
		if path is None:
			self._determine_default_dashboard()
			path = userConfig.userPath.joinpath('saves', 'dashboards', 'default.levity')
		if not path.exists():
			QMessageBox.critical(self.scene().view, "Error", f"Dashboard file not found: {path}").exec_()
			return

		try:
			with open(path, 'r', encoding='utf-8') as f:
				loader = type(self).__loader__(YAMLPreprocessor(f.read()))
				state = loader.get_data()
				if state is None:
					raise yaml.YAMLError("Failed to load dashboard")
				# Kept so a save can write the `$name` text back (see `_save`).
				self._vars = None
				self._written = deepcopy(state)
				state = resolveVariables(state)
				# Loading consumes the dicts it is given, so the save keeps its own copies.
				self._resolved = deepcopy(state)
		except yaml.YAMLError as error:
			log.exception(f"Error loading dashboard: {path}\n{error}")
			QMessageBox.critical(self.scene().window, "Error", f"Error loading dashboard: {path}\n{error}")
			raise error

		if self.filePath is None or self.loadedFile != path:
			self.filePath = EasyPathFile(path)
			self.clear()
			self.loadedFile = EasyPathFile(path)
		start = perf_counter()
		self.scene().view.status = 'Loading'
		# The theme has to be live before the first item decodes a `$token`.
		self._theme = None
		self._background = None
		self.scene().backdropSpec = None
		try:
			theme.activate(state.get('theme') if isinstance(state, dict) else None)
		except theme.ThemeError as error:
			log.error(f'{error}. Using the default theme.')
			theme.activate(None)
		try:
			self.state = state
		except Exception as error:
			# A single item raising anywhere below here unwinds the whole load,
			# so the board stops at whatever was built first. Left unreported
			# that looks like a layout bug rather than a crash - the reason the
			# 'just a big moon' symptom went undiagnosed for two months. The
			# notice has to match the size of the consequence.
			built = len(self.childPanels)
			# The root is a list in many dashboards and a mapping in others.
			expected = len(state.get('items', ()) if isinstance(state, dict) else state or ())
			log.critical(
				f"DASHBOARD LOAD FAILED: {path.name} is only partly built - "
				f"{built} of {expected} top-level item(s) made it onto the scene, and "
				f"the rest of the file was never read. The dashboard on screen is incomplete. "
				f"Cause below.",
				exc_info=error,
			)
			self.scene().view.status = 'Load Failed'
			self.scene().view.loadingFinished.emit()
			if debug:
				raise
			return
		self.scene().clearSelection()
		self.scene().view.status = 'Ready'
		self.scene().view.loadingFinished.emit()
		log.debug(f'Loading Time: {Time.Second(perf_counter() - start):.2f}')

	def setDefault(self):
		userConfig.dashboardPath = self.loadedFile

	def loadFile(self, path: Path = None):
		path = path or self._selectFile()
		if path:
			if isinstance(path, (list, tuple)):
				path = path[0]
			self._load(path)

	def loadTemplate(self, templatePath: Path, filePath: Path = None):
		if filePath is None:
			dialog = QFileDialog(None, 'Save Template Dashboard As...', str(userConfig.userPath.joinpath('saves', 'dashboards', templatePath.name)))
			dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
			dialog.setNameFilter("Dashboard Files (*.levity)")
			dialog.setViewMode(QFileDialog.ViewMode.Detail)
			if dialog.exec_():
				try:
					filePath = Path(dialog.selectedFiles()[0])
				except IndexError:
					return

		# copy the file from the template's folder to the saves folder
		copyfile(str(templatePath.absolute()), str(filePath.absolute()))
		self._load(filePath)

	def _selectFile(self, fileType: str = "Dashboard Files (*.levity *.yaml)", startingDir: str = 'dashboards', multipleFiles: bool = False):
		path = userConfig.userPath.joinpath('saves', startingDir)
		dialog = QFileDialog(self.parentWidget(), 'Save Dashboard As...', str(path))
		dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
		dialog.setNameFilter(fileType)
		dialog.setViewMode(QFileDialog.ViewMode.Detail)
		dialog.setFileMode(QFileDialog.FileMode.ExistingFiles if multipleFiles else QFileDialog.FileMode.ExistingFile)
		if dialog.exec_():
			filePaths = [Path(p) for p in dialog.selectedFiles()]
			return filePaths
		return []

	@classmethod
	def representer(cls, dumper, data):
		return dumper.represent_list(data.state)

	@property
	def hierarchy(self) -> List['Panel']:
		return [self]

	def boundingRect(self):
		return self.__boundingRect

colorPreprocessIn = r"(?<=color\:)\s*?#*?(?P<color>[A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})", " \\g<color>"

colorPreprocessOut = r"(?<=color\:)\s*?#?(?P<color>[A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})", " #\\g<color>"


def YAMLPreprocessor(data):
	if not isinstance(data, str):
		file = data
		data.seek(0)
		data = file.read()
		file.flush()
		data = re.sub(*colorPreprocessOut, data, 0, re.MULTILINE)
		file.seek(0)
		file.write(data)
		file.truncate()
	else:
		data = re.sub(*colorPreprocessIn, data, 0, re.MULTILINE)
		return data


class DebugException(RuntimeError):
	pass
