from os import remove
from shutil import copyfile
from tempfile import NamedTemporaryFile

from datetime import datetime
from functools import cached_property
import yaml
from pathlib import Path

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QFileDialog, QGraphicsItem, QGraphicsScene, QMessageBox

from LevityDash.lib.ui.frontends.PySide.Modules.Drawer import RadialMenuItem
from LevityDash.lib.Geometry import Geometry
from LevityDash.lib.ui.frontends.PySide.utils import hasState, itemLoader
from LevityDash.lib.ui.frontends.PySide.Modules.Menus import CentralPanelContextMenu
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
from LevityDash.lib.config import userConfig
from LevityDash.lib.EasyPath import FileLocation

from LevityDash.lib.log import LevityGUILog as guiLog

log = guiLog.getChild(__name__)


class CentralPanel(Panel):
	acceptsWheelEvents = True

	# preventCollisions = False
	# signals = GraphicsItemSignals()

	def __init__(self, parent: 'LevityScene'):
		self.gridOpacity = 1
		# self.grid = grid
		# self.grid.surface = self
		geometry = {'fillParent': True}
		super(CentralPanel, self).__init__(parent, geometry=geometry, movable=False, resizable=False)
		self.setAcceptDrops(True)
		self._keepInFrame = True
		self.setAcceptedMouseButtons(Qt.AllButtons)
		self.staticGrid = False

		path = Path(userConfig.dashboardPath)
		name = str(path).split('/')[-1]
		self.filePath = FileLocation(path.parent, name)
		self.preventCollisions = True
		self.setFlag(QGraphicsItem.ItemStopsClickFocusPropagation, False)
		self.setFlag(QGraphicsItem.ItemStopsFocusHandling, False)
		self.setFlag(self.ItemHasNoContents, True)
		self.insertMenu = RadialMenuItem(self, root=True)
		self.insertMenu.setVisible(False)
		self.resizeHandles.setVisible(False)
		self.resizeHandles.setEnabled(False)

	def load(self):
		if self.isEmpty:
			self.insertMenu.setVisible(True)
		else:
			self.insertMenu.setVisible(False)
		self._load(self.filePath)

	@property
	def parentGrid(self):
		return None

	@cached_property
	def window(self):
		return self.scene().views()[0]

	@cached_property
	def app(self):
		from PySide2.QtWidgets import QApplication
		return QApplication.instance()

	def mousePresEvent(self, event):
		self.scene().clearSelection()
		return

	# def wheelEvent(self, event):
	# 		event.accept()
	# 		v = event.delta() / 120 * 40
	# 		self.scene().apiDrawer.handle.moveBy(0, v)
	# 		self.scene().update()

	def paint(self, painter, option, widget):
		return super(CentralPanel, self).paint(painter, option, widget)

	# if self.scene().editingMode:
	# 	# if self.gridOpacity == 1:
	# 	# 	pen = QPen(gridPen)
	# 	# else:
	# 	# pen = QPen(gridPen)
	# 	# color = pen.color()
	# 	# color.setAlphaF(self.gridOpacity)
	# 	# pen.setColor(color)
	# 	painter.setPen(gridPen)
	# 	painter.setBrush(Qt.NoBrush)
	# 	path = QPainterPath()
	# 	for i in range(1, self.grid.columns):
	# 		path.moveTo(i*self.grid.columnWidth, 0)
	# 		path.lineTo(i*self.grid.columnWidth, self.grid.rowHeight*self.grid.rows)
	# 	for i in range(1, self.grid.rows):
	# 		path.moveTo(0, i*self.grid.rowHeight)
	# 		path.lineTo(self.grid.columnWidth*self.grid.columns, i*self.grid.rowHeight)
	# 	for panel in self.childPanels:
	# 		if isinstance(panel, GraphPanel):
	# 			path -= panel.mappedShape()
	# 	painter.drawPath(path)

	# elif self.gridOpacity > 0:
	# 	self.gridOpacity -= 0.05
	# else:
	# 	self.gridOpacity = 0
	# super(CentralPanel, self).paint(painter, option, widget)

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemPositionChange:
			return QGraphicsItem.itemChange(self, change, value)
		return super(CentralPanel, self).itemChange(change, value)

	@property
	def state(self) -> list[Panel]:
		items = self.childPanels
		items.sort(key=lambda x: (x.geometry.position.y, -x.geometry.position.x))
		return [item for item in items if hasState(item)]

	# def contextMenuEvent(self, event):
	# 	contextMenu = QMenu(event.widget())
	# 	# newAct = contextMenu.addAction("Insert")
	# 	insertMenu = contextMenu.addMenu('Insert')
	# 	insertBlock = insertMenu.addMenu('Block')
	# 	insertSnapping = insertBlock.addAction('Snapping')
	# 	insertFreeform = insertBlock.addAction('Freeform')
	# 	time = insertMenu.addAction('Time')
	# 	saveAct = contextMenu.addAction("Save")
	# 	loadAct = contextMenu.addAction("Load")
	# 	quitAct = contextMenu.addAction("Quit")
	# 	action = contextMenu.exec_(event.screenPos())
	# 	if action == quitAct:
	# 		QApplication().quit()
	# 	elif action == insertSnapping:
	# 		item = Panel(self)
	# 		item.gridItem.location = event.pos()
	# 		item.setPos(event.pos())
	# 		item.snapping.setValue(True)
	# 	elif action == insertFreeform:
	# 		item = Panel(self)
	# 		item.setPos(event.pos())
	# 		item.snapping.setValue(False)
	# 	elif action == saveAct:
	# 		childItems = self.childItems()
	# 		state = [child.state for child in childItems if hasattr(child, 'state') and child.state is not None]
	# 		with open('state.json', 'w') as f:
	# 			dump(state, f, indent=2, sort_keys=True, cls=JsonEncoder)
	#
	# 	elif action == loadAct:
	# 		with open('state.json', 'r') as f:
	# 			state = load(f, object_hook=JsonDecoder(self.apiDrawer.apiDict))
	# 			for item in state:
	# 				cls = item.pop('class')
	# 				item = cls(parent=self, **item)
	#
	# def itemChange(self, change, value):
	# 	if change == QGraphicsItem.ItemChildAddedChange:
	# 		if hasattr(value, 'gridItem'):
	# 			self.grid.gridItems.add(value.gridItem)
	# 			self.signals.resized.connect(value.parentResized)
	# 	if change == QGraphicsItem.ItemChildRemovedChange:
	# 		if hasattr(value, 'gridItem'):
	# 			self.signals.resized.disconnect(value.parentResized)
	# 			self.grid.gridItems.remove(value.gridItem)
	# 	return super(GridLines, self).itemChange(change, value)
	#
	# def setRect(self, rect: QRectF):
	# 	self.signals.resized.emit(rect)
	# 	super(GridLines, self).setRect(rect)
	#
	# @property
	# def containingRect(self):
	# 	return self.rect()
	# self.setFlag(QGraphicsItem.ItemIsFocusable, False)
	@cached_property
	def contextMenu(self):
		return CentralPanelContextMenu(self)

	# def setRect(self, rect):
	# 	super(CentralPanel, self).setRect(rect)

	# def itemChange(self, change, value):
	#
	# 	if change == QGraphicsItem.ItemChildAddedChange:
	# 		value.setZValue(self.zValue() - 10)
	# 	return super(CentralPanel, self).itemChange(change, value)

	def load(self):
		if self.filePath is None:
			path = Path(self._selectFile()[0])
			name = str(path).split('/')[-1]
			self.filePath = FileLocation(path.parent, name)
		self._load(self.filePath)

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

		try:
			tempFile = NamedTemporaryFile(delete=False, mode='w')
			with tempFile as f:
				yaml.safe_dump(self.state, f, default_flow_style=False)
			copyfile(tempFile.name, str(path.joinpath(fileName)))
		except Exception as e:
			log.error(e)
		finally:
			remove(tempFile.name)
			# 	t = locals().get('tempFile', False)
			# 	if t and t.mode == 'w':
			# 		t.close()
		return

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

	def _load(self, path: Path = None, isTemplate: bool = False):
		log.debug(f"Loading dashboard from {str(path)}")
		if isinstance(path, FileLocation):
			path = path.fullPath
		if path is None:
			path = userConfig.userPath.joinpath('saves', 'dashboards', 'default.levity')
		if not path.exists():
			if isinstance(self.parent, QGraphicsScene):
				QMessageBox.critical(self.parentWidget(), "Error", f"Dashboard file not found: {path}")
			else:
				QMessageBox.critical(self.parent.parentWidget(), "Error", f"Error loading dashboard: {path}")
			return
		with open(path, 'r') as f:
			try:
				state = yaml.safe_load(f)
				if 'geometry' in state:
					self.geometry = Geometry(self, **state['geometry'])
				self.clear()
				for item in state:
					itemLoader(self, item)
				if path != userConfig.dashboardPath:
					userConfig.dashboardPath = path
			except yaml.YAMLError as error:
				log.error(f"Error loading dashboard: {path}\n{error}")
				message = QMessageBox.critical(None, "Error", f"Error loading dashboard: {path}\n{error}")
				message.show()
				message.exec_()
				return
		self.scene().views()[0].setWindowFilePath(str(path))
		self.scene().views()[0].setWindowModified(True)

	def clear(self):
		items = [child for child in self.childPanels if child is not self.insertMenu]
		for item in items:
			self.scene().removeItem(item)

	def loadFile(self, path: Path = None):
		path = path or self._selectFile()
		if path:
			if isinstance(path, (list, tuple)):
				path = path[0]
			self._load(path)

	def _selectFile(self, fileType: str = "Dashboard Files (*.levity *.yaml)", startingDir: str = 'dashboard', multipleFiles: bool = False):
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
