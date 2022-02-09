from datetime import datetime
from functools import cached_property
from json import dump, JSONDecodeError, load
from os import remove, rename
from pathlib import Path

from PySide2.QtCore import QEvent, QPoint, QRect, Qt
from PySide2.QtGui import QPainter, QPainterPath, QPen
from PySide2.QtWidgets import QFileDialog, QGraphicsItem, QGraphicsScene, QMessageBox

from src.GridView import GridScene
from src.Grid import Geometry
from src.Modules import hook
from src.Modules.Menus import CentralPanelContextMenu
from src.Modules.Panel import Panel
from src import config, gridPen
from src.utils import FileLocation, hasState, JsonEncoder

from src import logging

log = logging.getLogger(__name__)


class CentralPanel(Panel):
	acceptsWheelEvents = True

	# preventCollisions = False
	# signals = GraphicsItemSignals()

	def __init__(self, parent: GridScene):
		self.gridOpacity = 1
		# self.grid = grid
		# self.grid.surface = self
		geometry = {'fillParent': True}
		super(CentralPanel, self).__init__(parent, geometry=geometry, movable=False, resizable=False)
		self.resizeHandles.setEnabled(False)
		self.resizeHandles.setVisible(False)
		self.setAcceptDrops(True)
		self._keepInFrame = True
		self.setLocked(True)
		self._locked = False
		self.setFlag(QGraphicsItem.ItemStopsClickFocusPropagation, False)
		self.setAcceptedMouseButtons(Qt.AllButtons)
		self.staticGrid = False
		self.grid.static = False

		path = Path(config.dashboardPath)
		name = str(path).split('/')[-1]
		self.filePath = FileLocation(path.parent, name)
		self.preventCollisions = True
		self.setFlag(QGraphicsItem.ItemStopsClickFocusPropagation, False)
		self.setFlag(QGraphicsItem.ItemStopsFocusHandling, False)
		self._load(self.filePath)

		from src.Modules.Drawer import RadialMenuItem
		from src.merger import endpoints
		self.insertMenu = RadialMenuItem(self, subItems=endpoints.categories, root=True)
		if self.isEmpty:
			self.insertMenu.setVisible(True)
		else:
			self.insertMenu.setVisible(False)

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

	# def wheelEvent(self, event):
	# 		event.accept()
	# 		v = event.delta() / 120 * 40
	# 		self.scene().apiDrawer.handle.moveBy(0, v)
	# 		self.scene().update()

	def paint(self, painter, option, widget):
		if self.scene().editingMode:
			# if self.gridOpacity == 1:
			# 	pen = QPen(gridPen)
			# else:
			# pen = QPen(gridPen)
			# color = pen.color()
			# color.setAlphaF(self.gridOpacity)
			# pen.setColor(color)
			painter.setPen(gridPen)
			painter.setBrush(Qt.NoBrush)
			path = QPainterPath()
			for i in range(1, self.grid.columns):
				path.moveTo(i * self.grid.columnWidth, 0)
				path.lineTo(i * self.grid.columnWidth, self.grid.rowHeight * self.grid.rows)
			for i in range(1, self.grid.rows):
				path.moveTo(0, i * self.grid.rowHeight)
				path.lineTo(self.grid.columnWidth * self.grid.columns, i * self.grid.rowHeight)
			# for panel in self.childPanels:
			# 	path -= panel.mappedShape()
			painter.drawPath(path)

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
	def state(self):
		return {
			'childItems': {child.name if child.name is not None else f'{child.__class__.__name__}_0x{child.uuidShort}': child.state for child in self.childPanels if hasState(child)},
			'fullscreen': self.window.isFullScreen()
		}

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
		from Modules.Panel import PanelFromFile
		paths = self._selectFile(fileType="Dashboard Files (*.dashiePanel *.json)", startingDir='panels', multipleFiles=True)
		for p in paths:
			PanelFromFile(self, p)

	def _save(self, path: Path = None, fileName: str = None):
		if path is None:
			path = config.userPath.joinpath('saves', 'dashboards')
		if fileName is None:
			fileName = 'default.dashie'

		if not path.exists():
			path.mkdir(parents=True)

		fileNameTemp = fileName + '.tmp'
		with open(path.joinpath(fileNameTemp), 'w') as f:
			dump(self.state, f, indent=2, cls=JsonEncoder)
		try:
			with open(path.joinpath(fileNameTemp), 'r') as f:
				from Modules import hook
				load(f, object_hook=hook)
			rename(path.joinpath(fileNameTemp), path.joinpath(fileName))
		except Exception as e:
			QMessageBox.critical(self.parent.parentWidget(), "Error", f"Error saving dashboard: {e}")
			remove(path.joinpath(fileNameTemp))

	def save(self):
		self._save()

	def saveAs(self):
		dateString = datetime.now().strftime('dashboard.%Y.%m.%d.dashie')
		path = config.userPath.joinpath('saves', 'dashboards')

		path = path.joinpath(dateString)
		dialog = QFileDialog(self.parentWidget(), 'Save Dashboard As...', str(path))
		dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
		dialog.setNameFilter("Dashboard Files (*.dashie)")
		dialog.setViewMode(QFileDialog.ViewMode.Detail)
		if dialog.exec_():
			fileName = Path(dialog.selectedFiles()[0])
			path = fileName.parent
			fileName = dialog.selectedFiles()[0].split('/')[-1]
			self._save(path, fileName)

	def _load(self, path: Path = None):
		log.debug(f"Loading dashboard from {str(path)}")
		if isinstance(path, FileLocation):
			path = path.fullPath
		if path is None:
			path = config.userPath.joinpath('saves', 'dashboards', 'default.dashie')
		if not path.exists():
			if isinstance(self.parent, QGraphicsScene):
				QMessageBox.critical(self.parentWidget(), "Error", f"Dashboard file not found: {path}")
			else:
				QMessageBox.critical(self.parent.parentWidget(), "Error", f"Error loading dashboard: {path}")
			return
		with open(path, 'r') as f:
			try:
				state = load(f, object_hook=hook)

				# window = self.scene().views()[0].parentWidget()
				# g = window.geometry()
				# g.setSize(QSizeF(*state['size']).toSize())
				# window.setGeometry(g)
				self.clear()
				if 'geometry' in state:
					self.geometry = Geometry(self, **state['geometry'])
				self._loadChildren(state.get('childItems', {}))
				config.dashboardPath = path
			except JSONDecodeError:
				QMessageBox.critical(None, "Error", f"Error loading dashboard: {path}")

	def clear(self):
		items = [child for child in self.childPanels if child is not self.insertMenu]
		for item in items:
			self.scene().removeItem(item)

	def loadFile(self):
		path = self._selectFile()
		if path:
			self._load(path[0])

	def _selectFile(self, fileType: str = "Dashboard Files (*.dashie *.json)", startingDir: str = 'dashboard', multipleFiles: bool = False):
		path = config.userPath.joinpath('saves', startingDir)
		dialog = QFileDialog(self.parentWidget(), 'Save Dashboard As...', str(path))
		dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
		dialog.setNameFilter(fileType)
		dialog.setViewMode(QFileDialog.ViewMode.Detail)
		dialog.setFileMode(QFileDialog.FileMode.ExistingFiles if multipleFiles else QFileDialog.FileMode.ExistingFile)
		if dialog.exec_():
			filePaths = [Path(p) for p in dialog.selectedFiles()]
			return filePaths
		return []
