import re
from datetime import datetime
from functools import cached_property
from pathlib import Path
from shutil import copyfile
from tempfile import NamedTemporaryFile
from typing import Any, List

import yaml
from PySide2.QtCore import QRect, Qt, Slot
from PySide2.QtWidgets import QFileDialog, QGraphicsItem, QMessageBox
from time import perf_counter

from LevityDash import LevityDashboard
from LevityDash.lib.config import userConfig
from LevityDash.lib.EasyPath import EasyPathFile
from LevityDash.lib.log import debug
from LevityDash.lib.stateful import StatefulDumper, StateProperty
from LevityDash.lib.ui.frontends.PySide.Modules.Menus import CentralPanelContextMenu
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
from LevityDash.lib.utils import BusyContext
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

	def __init__(self, parent: 'LevityScene'):
		self._parent = parent
		self.__boundingRect = QRect(-2000, -2000, 6000, 6000)
		self._scene = parent
		super(CentralPanel, self).__init__(None, stateParent=None)

		self.setAcceptedMouseButtons(Qt.AllButtons)

		defaultDashboardPath = userConfig.dashboardPath
		self.filePath = EasyPathFile(defaultDashboardPath) if defaultDashboardPath is not None else None
		self.loadedFile: Any = None

		self.setFlag(QGraphicsItem.ItemStopsClickFocusPropagation, False)
		self.setFlag(QGraphicsItem.ItemStopsFocusHandling, False)
		self.setFlag(QGraphicsItem.ItemHasNoContents)
		self.resizeHandles.setVisible(False)
		self.resizeHandles.setEnabled(False)
		self.setFlag(self.ItemClipsChildrenToShape, False)
		self.setFlag(self.ItemClipsToShape, False)
		self.setFlag(self.ItemIsFocusable, False)
		self.setFlag(self.ItemIsMovable, False)
		self.setFlag(self.ItemIsSelectable, False)
		LevityDashboard.CENTRAL_PANEL = self
		LevityDashboard.main_action_pool = self._actionPool

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
		from PySide2.QtWidgets import QApplication
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

	@StateProperty(singleVal='force', inheritFrom=Panel.items)
	def items(self) -> list[Panel]:
		...

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

		with NamedTemporaryFile(delete=True, mode="w+", encoding='utf-8') as f:
			try:
				state = self.state
				yaml.dump(state, f, Dumper=StatefulDumper, default_flow_style=False, allow_unicode=True)

				YAMLPreprocessor(f)
				copyfile(f.name, str(path.joinpath(fileName)))
				log.info('Saved!')
			except Exception if not debug else DebugException as e:
				log.info('Failed')
				log.exception(e)

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

	def _load(self, path: Path = None):
		name = path.name
		self.scene().view.parentWidget().setWindowTitle(f"Levity Dashboard - {name}")
		log.debug(f"Loading dashboard from {str(path)}")
		if isinstance(path, EasyPathFile):
			path = path.path
		if path is None:
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
		self.state = state
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
