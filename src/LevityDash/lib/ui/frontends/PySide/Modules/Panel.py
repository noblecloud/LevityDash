import sys

from functools import cached_property, lru_cache
from json import dump, dumps, load, loads
from pprint import pprint

from math import prod
from os import remove, replace
from pathlib import Path
from typing import Any, Callable, List, Optional, overload, Union
from uuid import UUID, uuid4

from PySide2.QtCore import QByteArray, QMimeData, QPointF, QRect, QRectF, QSize, QSizeF, Qt, QTimer, Slot
from PySide2.QtGui import QColor, QDrag, QFocusEvent, QPainter, QPainterPath, QPixmap, QTransform
from PySide2.QtWidgets import (QApplication, QFileDialog, QGraphicsBlurEffect, QGraphicsDropShadowEffect, QGraphicsItem, QGraphicsItemGroup, QGraphicsPathItem, QGraphicsScene, QGraphicsSceneDragDropEvent,
                               QGraphicsSceneHoverEvent,
                               QGraphicsSceneMouseEvent,
                               QMessageBox,
                               QStyleOptionGraphicsItem, QGraphicsRectItem)

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.Geometry.Grid import GridItem, Grid
from LevityDash.lib.Geometry import Geometry

from LevityDash.lib.config import userConfig
from LevityDash.lib.EasyPath import FileLocation
from LevityDash.lib.utils.shared import boolFilter, clearCacheAttr, disconnectSignal, getItemsWithType, Numeric, SimilarValue, _Panel
from LevityDash.lib.utils.geometry import Edge, LocationFlag, Margins, polygon_area, Position

from LevityDash.lib.log import LevityGUILog as log
from LevityDash.lib.ui.frontends.PySide.utils import debugPen, DisplayType, gridPen, selectionPen, colorPalette, findScene, findSizePosition, GraphicsItemSignals, hasState, itemLoader
from LevityDash.lib.ui.frontends.PySide.Modules.Menus import BaseContextMenu
from LevityDash.lib.ui.frontends.PySide.Modules.Handles import Handle, HandleGroup
from LevityDash.lib.ui.frontends.PySide.Modules.Handles.Resize import ResizeHandles
from LevityDash.lib.ui.frontends.PySide.Modules.Handles.Grid import GridAdjusters
from LevityDash.lib.ui import colors

blurEffect = QGraphicsBlurEffect()
blurEffect.setBlurRadius(10)
blurEffect.setBlurHints(QGraphicsBlurEffect.PerformanceHint)


class Panel(_Panel):
	collisionThreshold = 0.5
	onlyAddChildrenOnRelease = False
	signals: GraphicsItemSignals
	filePath: FileLocation
	_includeChildrenInState: bool = True
	_grid: Grid = None
	_gridItem: GridItem = None
	_geometry: Geometry = None
	_keepInFrame = True
	_staticGrid = True
	_scene = None
	_showGrid: bool = True
	_parent: QGraphicsItem = None
	_acceptsChildren: bool = True
	savable: bool = True
	acceptsWheelEvents: bool = False
	_childIsMoving: bool = False

	defaults = {
		'resizable': True,
		'movable':   True,
		'frozen':    False,
		'locked':    False,
	}

	# section Panel init
	def __init__(self, parent: 'Panel', *args, **kwargs):
		super(Panel, self).__init__()

		self.__hold = False
		self._contextMenuOpen = False
		self.uuid = kwargs.get('uuid', uuid4())
		if isinstance(self.uuid, str):
			self.uuid = UUID(self.uuid, version=4)
		self.__init_defaults__()
		self.setParentItem(parent if isinstance(parent, QGraphicsItem) else None)
		self.__init_args(parent, *args, **kwargs)
		self.geometry.updateSurface(set=False)
		self.previousParent = self.parent
		self.setFlag(self.ItemIsSelectable, True)

	def __parse_args__(self, *args, **kwargs):
		kwargs = findScene(*args, **kwargs)
		kwargs = findSizePosition(*args, **kwargs)

		geometry = kwargs.get('geometry', {})
		if isinstance(geometry, dict):
			if 'position' not in geometry:
				geometry['position'] = kwargs.get('position', None)
			if 'size' not in geometry:
				geometry['size'] = kwargs.get('size', None)
		kwargs['geometry'] = geometry
		return kwargs

	def __init_args(self, parent, *args, **kwargs):
		kwargs['parent'] = parent
		kwargs = self.__parse_args__(*args, **kwargs)

		if 'scene' in kwargs and (not parent or kwargs['scene'] == parent):
			scene = kwargs['scene']
			if isinstance(scene, Callable):
				scene = scene()
			if isinstance(scene, QGraphicsScene):
				scene.addItem(self)
		elif isinstance(parent, QGraphicsScene):
			parent.addItem(self)
			self._scene = parent
		elif isinstance(parent, QGraphicsItem):
			self.setParentItem(parent)
		# parent.scene().addItem(self)

		self.margins = kwargs.get('margins', None)

		self.geometry = kwargs.get('geometry', None)
		self.geometry.updateSurface(set=False)

		if 'grid' in kwargs:
			self.grid = kwargs.get('grid', None)
			if isinstance(self.grid, dict):
				self.grid = Grid(self, **self.grid)

		self._name = kwargs.get('name', None)

		# self.clipping = kwargs.get('clipChildren', False)
		self.movable = kwargs.get('movable', True)
		self.resizable = kwargs.get('resizable', True)
		items = kwargs.get('items', [])
		self._loadChildren(items)
		self.frozen = kwargs.get('frozen', False)
		self.locked = kwargs.get('locked', False)
		if 'savable' in kwargs:
			self.savable = kwargs.get('savable')

		self.setAcceptedMouseButtons(Qt.AllButtons if kwargs.get('clickable', None) or kwargs.get('intractable', True) else Qt.NoButton)

	# self.geometry.relative = True

	def __init_defaults__(self):
		self.uuidShort = self.uuid.hex[-4:]
		self.signals = GraphicsItemSignals()
		self._geometry = None
		self._fillParent = False
		self.filePath = None
		self._locked = False
		self.mousePressPos = None
		self.hoverPosition = None
		self.hoverOffset = None
		self.startingParent = None
		self.nextParent = None
		self.hoverStart = None
		self.previousParent = None
		self.maxRect = None
		self._frozen = False
		self._name = None
		self.__grid = None
		# self.hoverTimer = QTimer(interval=500, singleShot=True, timeout=self.hoverFunc)
		self.hideTimer = QTimer(interval=1000*3, singleShot=True, timeout=self.hideHandles)
		# self.parentSelectionTimer = QTimer(interval=750, singleShot=True, timeout=self.transferToParent)
		self.setAcceptHoverEvents(False)
		self.setAcceptDrops(True)
		self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
		self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, False)
		self.setFlag(QGraphicsItem.ItemIsFocusable, True)
		# self.setFlag(QGraphicsItem.ItemIsSelectable, True)
		self.setFlag(QGraphicsItem.ItemClipsToShape, not True)
		self.setFlag(QGraphicsItem.ItemClipsChildrenToShape, not True)
		self.setFlag(QGraphicsItem.ItemStopsClickFocusPropagation, True)
		self.setFlag(QGraphicsItem.ItemStopsFocusHandling, True)
		# self.indicator = Indicator(self)
		# self.indicator.setVisible(self.debug)
		# self.setHandlesChildEvents(True)

		selectionEffect: QGraphicsDropShadowEffect = QGraphicsDropShadowEffect()
		selectionEffect.setBlurRadius(30)
		selectionEffect.setOffset(0, 0)
		selectionEffect.setColor(QColor(0, 0, 0, 100))
		selectionEffect.setEnabled(False)

		self.selectionEffect = selectionEffect
		self.setGraphicsEffect(selectionEffect)
		self._highlighted = False

	def __eq__(self, other):
		if isinstance(other, Panel):
			return self.uuid == other.uuid
		return False

	def __hash__(self):
		return hash(self.uuid)

	@classmethod
	def validate(cls, item: dict):
		geometry = Geometry.validate(item.get('geometry', {}))
		return geometry

	def childNames(self, *exclude):
		return [child.name for child in self.childPanels if child not in exclude]

	@property
	def childIsMoving(self):
		return self._childIsMoving

	@childIsMoving.setter
	def childIsMoving(self, value):
		if self._childIsMoving != value:
			self._childIsMoving = value
			self.update()

	def debugBreak(self):
		state = self.state
		print(pprint(self.state))

	def isValid(self) -> bool:
		return self.rect().isValid()

	def size(self) -> QSizeF:
		return self.rect().size()

	@property
	def name(self):
		if self._name is None:
			if hasattr(self, 'title'):
				title = self.title
				if hasattr(title, 'text'):
					title = title.text
				if isinstance(title, Callable):
					title = title()
				self._name = str(title)
				return self._name
			if hasattr(self, 'text'):
				name = self.text
				if isinstance(name, Callable):
					name = name()
				self._name = str(name)
				return self._name

			if self.childPanels:
				# find the largest child with a 'text' attribute
				textAttrs = [child for child in self.childItems() if hasattr(child, 'text')]
				if textAttrs:
					textAttrs.sort(key=lambda child: child.geometry.size, reverse=True)
					self._name = textAttrs[0].text
					return self._name
				# find the largest panel with a linkedValue
				linkedValues = [child for child in self.childItems() if hasattr(child, 'linkedValue')]
			else:
				self._name = f'{self.__class__.__name__}-0x{self.uuidShort}'
				return self._name

	@name.setter
	def name(self, name):
		self._name = name

	@cached_property
	def centralPanel(self) -> 'CentralPanel':
		if self.scene() is None:
			from PySide2.QtWidgets import QGraphicsView
			widgets = QApplication.instance().allWidgets()
			for widget in widgets:
				if isinstance(widget, QGraphicsView):
					return widget.gridScene.base
			return None
		return self.scene().base

	def hideHandles(self):
		self.clearFocus()

	@property
	def uuidDict(self):
		return {item.uuid: item for item in self.childPanels if hasattr(item, 'uuid')}

	def __findChildUUID(self, uuid) -> Optional['Panel']:
		for child in self.childPanels:
			if child.uuid == uuid:
				return child
		return None

	def _loadChildren(self, childItems: list[dict[str, Any]]):
		self.geometry.updateSurface(set=False)
		loadedChildren = []
		# for child in childItems:
		if isinstance(childItems, list):
			for child in childItems:
				item = itemLoader(self, child)
		elif isinstance(childItems, dict):
			for name, child in childItems.items():
				child['name'] = name
				if any(child == c for c in loadedChildren):
					continue
				else:
					loadedChildren.append(child)
				self.loadChildFromState(child)

	def loadState(self, state: dict):
		state.pop('class', None)
		self.__init_args(parent=self.parent, **state)

	def loadChildFromState(self, child):
		if 'uuid' in child:
			childInstance = self.__findChildUUID(child['uuid'])
			if childInstance is not None:
				childInstance.loadState(child)
				return childInstance
		cls = child.pop('class')
		try:
			child = cls(parent=self, **child)
			return child
		except TypeError:
			log.exception(f'Error loading child item: {cls} with type: {type(cls)}')

	def setSize(self, *args):
		if len(args) == 1 and isinstance(args[0], QSizeF):
			size = args[0]
		elif len(args) == 2:
			size = QSizeF(*args)
		else:
			raise ValueError('Invalid arguments')
		self.setRect(self.rect().adjusted(0, 0, size.width(), size.height()))

	@property
	def debug(self):
		if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
			return False
		return log.level <= 10

	@property
	def acceptsChildren(self) -> bool:
		return self._acceptsChildren

	def __repr__(self):
		return f'<{self.uuidShort} | {self.__class__.__name__}(position=({self.geometry.position}), size=({self.geometry.size}) {f", {self.geometry.gridItem}," if False else ""} zPosition={self.zValue()}>'

	@property
	def snapping(self) -> bool:
		return self.geometry.snapping

	@snapping.setter
	def snapping(self, value):
		pass

	def updateSizePosition(self, recursive: bool = False):
		# if self.geometry.size.snapping:
		# 	self.setRect(self.geometry.rect())
		# if self.geometry.size:
		# 	w = self.sizeRatio.width * self.parent.containingRect.width()
		# 	h = self.sizeRatio.height * self.parent.containingRect.height()
		# 	self.setRect(QRectF(0, 0, w, h))
		#
		# if self.geometry.position.snapping:
		# 	self.setPos(self.geometry.pos())
		# elif self.positionRatio:
		# 	y = self.positionRatio.x * self.parent.containingRect.height()
		# 	x = self.positionRatio.y * self.parent.containingRect.width()
		# 	self.setPos(QPointF(x, y))
		# QGraphicsRectItem.setRect(self, self.geometry.rect())
		# QGraphicsRectItem.setPos(self, self.geometry.pos())
		self.signals.resized.emit(self.geometry.absoluteRect())
		if recursive:
			items = [item for item in self.childItems() if isinstance(item, Panel)]
			for item in items:
				item.updateSizePosition()

	def updateRatios(self):
		rect = self.parent.containingRect
		width = max(1, rect.width())
		height = max(1, rect.height())

		if self.geometry.relative:
			self.geometry.size.width = self.rect().width()/width
			self.geometry.size.height = self.rect().height()/height
			self.geometry.position.x = self.pos().x()/width
			self.geometry.position.y = self.pos().y()/height
		else:
			pass

	@property
	def gridItem(self):
		if self.parentGrid is None:
			return None
		return self._geometry.gridItem

	@gridItem.setter
	def gridItem(self, value):
		if self.parentGrid is None:
			raise ValueError('Cannot set gridItem on a panel that is not in a grid')
		self._gridItem = value

	@property
	def parentGrid(self) -> Grid:
		return self._parent.grid

	@cached_property
	def onGrid(self) -> bool:
		return self.parentGrid is not None

	@property
	def grid(self) -> Optional[Grid]:
		if len(self.childPanels) == 0:
			return None
		if self.__grid is None:
			clearCacheAttr(self, 'allHandles')
			self.__grid = Grid(self, static=self._staticGrid)
		return self.__grid

	@grid.setter
	def grid(self, value):
		if isinstance(value, dict):
			value = Grid(self, **value)
		self.__grid = value
		self._staticGrid = value.static

	@cached_property
	def gridAdjusters(self):
		if self.grid is None:
			return None
		clearCacheAttr(self, 'allHandles')
		handles = GridAdjusters(self, offset=-15)
		return handles

	@cached_property
	def resizeHandles(self):
		clearCacheAttr(self, 'allHandles')
		# for value in LocationFlag.all():
		# 	handle = Handle(self, value)
		# 	self.signals.resized.connect(handle.mapValues)
		# 	self.signals.childAdded.connect(handle.mapValues)
		# 	self.signals.childRemoved.connect(handle.mapValues)
		handles = ResizeHandles(self)
		return handles

	@cached_property
	def allHandles(self):
		return [handleGroup for handleGroup in self.childItems() if isinstance(handleGroup, (Handle, HandleGroup))]

	@property
	def geometry(self):
		if self._geometry is None:
			self._geometry = Geometry(surface=self, absolute=True)
		elif isinstance(self._geometry, dict):
			self._geometry = Geometry(surface=self, **self._geometry)
		return self._geometry

	@geometry.setter
	def geometry(self, geometry):
		if isinstance(geometry, dict):
			geometry = Geometry(self, **geometry)
		elif geometry is None:
			geometry = Geometry(self)
		if not isinstance(geometry, Geometry):
			raise ValueError('Invalid geometry')
		if geometry.surface is not self:
			geometry.surface = self
		self._geometry = geometry

	@property
	def margins(self) -> Margins:
		return self._margins

	@margins.setter
	def margins(self, value):
		if value is None:
			value = Margins(self, 0.1, 0.1, 0.1, 0.1)
		elif not isinstance(value, Margins):
			if isinstance(value, str):
				value = Margins(self, *value.split(','))
			elif isinstance(value, list):
				value = Margins(self, *value)
			else:
				value = Margins(self, **value)
		self._margins = value

	@property
	def staticGrid(self):
		return self._staticGrid

	@staticGrid.setter
	def staticGrid(self, value):
		if self.grid:
			self.grid.static = value
			self.gridAdjusters.setEnabled(value)
			self.gridAdjusters.setVisible(value)
			self.gridAdjusters.update()
		self._staticGrid = value

	def show(self):
		self.updateFromGeometry()
		# if not all(self.rect().size().toTuple()):
		# 	self.setRect(self.geometry.rect())
		# 	self.setPos(self.gridItem.pos())
		super(Panel, self).show()

	def scene(self) -> 'LevityScene':
		return super(Panel, self).scene()

	@property
	def state(self) -> dict:
		sizePosType = 'relative' if self.geometry.relative else 'absolute'
		state = {
			# 'uuid':      str(self.uuid),
			'type':      self.__class__.__name__.lower(),
			'geometry':  self.geometry,
			'frozen':    self.frozen,
			'locked':    self.locked,
			'resizable': self.resizeHandles.isEnabled(),
			'movable':   bool(self.flags() & QGraphicsItem.ItemIsMovable),
			'margins':   self.margins,
		}
		if state['type'] == 'panel':
			state['type'] = 'group'
		if self.hasChildren:
			items = self.childPanels
			items.sort(key=lambda x: (x.pos().y(), -x.pos().x()))
			state['items'] = [child for child in items if hasState(child)]
		# state['clipChildren'] = bool(self.flags() & QGraphicsItem.ItemClipsToShape)
		# state['keepInFrame'] = self._keepInFrame
		# state['preventCollisions'] = self.preventCollisions

		return type(self).removeDefaults(state)

	@classmethod
	def representer(cls, dumper, data):
		return dumper.represent_dict(data.state.items())

	@classmethod
	def removeDefaults(cls, state):
		for key, value in list(state.items()):
			if hasattr(value, 'default') and value == (value.default() if isinstance(value.default, Callable) else value.default):
				del state[key]
			elif hasattr(cls, f'_{key}') and value == getattr(cls, f'_{key}'):
				del state[key]
			elif hasattr(cls, 'defaults') and key in cls.defaults and value == cls.defaults[key]:
				del state[key]
			elif value is None:
				del state[key]

		if state.get('locked', False):
			state.pop('movable', None)
			state.pop('resizable', None)
			state.pop('frozen', None)
		if state.get('frozen', False):
			state.pop('movable', None)

		return state

	# section mouseEvents

	@cached_property
	def contextMenu(self):
		menu = BaseContextMenu(self)
		return menu

	def contextMenuEvent(self, event):
		if self.canFocus and self.hasFocus():
			event.accept()
		else:
			event.ignore()
			return
		# if self.scene().focusItem() is self.parent or bool(QApplication.mouseButtons() & Qt.LeftButton):
		# 	event.ignore()
		# 	return
		self.resizeHandles.forceDisplay = True
		self.contextMenu.position = event.pos()
		self._contextMenuOpen = True
		self.contextMenu.exec_(event.screenPos())
		self.setFocus(Qt.MouseFocusReason)
		self.resizeHandles.forceDisplay = False
		self._contextMenuOpen = False
		self.update()

	def underMouse(self):
		return self.scene().underMouse()

	def dragEnterEvent(self, event: QGraphicsSceneDragDropEvent):
		if self.acceptsChildren:
			if event.mimeData().hasFormat('application/panel-valueLink'):
				event.acceptProposedAction()
				return
		event.ignore()
		super().dragEnterEvent(event)

	def dragMoveEvent(self, event: QGraphicsSceneDragDropEvent):
		super(Panel, self).dragMoveEvent(event)

	def dragLeaveEvent(self, event: QGraphicsSceneDragDropEvent):
		self.clearFocus()
		super(Panel, self).dragLeaveEvent(event)

	def dropEvent(self, event: QGraphicsSceneDragDropEvent):
		from LevityDash.lib.ui.frontends.PySide.Modules import Realtime
		def hook(object: dict):
			from LevityDash.lib.plugins.dispatcher import ValueDirectory

			if 'valueLink' in object:
				state = object['valueLink']
				link = ValueDirectory[CategoryItem(state['key'])]
				if 'preferredSource' in state:
					link.preferredSource = state['preferredSource']
				object['valueLink'] = link

			if 'timeframe' in object:
				from utils.data import TimeFrameWindow
				object['timeframe'] = TimeFrameWindow(**object['timeframe'])

			if 'displayType' in object:
				object['displayType'] = DisplayType(object['displayType'])

			if 'key' in object:
				object['key'] = CategoryItem(object['key'])

			if 'displayType' in object:
				try:
					object['displayType'] = DisplayType[object['displayType']]
				except KeyError:
					object['displayType'] = DisplayType.Text
			return object

		data = loads(event.mimeData().data('application/panel-valueLink').data(), object_hook=hook)

		cls = Realtime
		if 'geometry' not in data:
			data['geometry'] = {'position': event.pos(), 'absolute': True}
		else:
			data['geometry']['absolute'] = True
			data['geometry']['position'] = event.pos()
		item = cls(parent=self, **data)
		item.setLocked(False)
		item.updateSizePosition()
		item.geometry.relative = True

		# For whatever reason this prevents the item from jumping to the top left corner
		# when the item is first moved
		rect = item.rect()
		rect.moveTo(event.pos())
		item.geometry.setGeometry(rect)

		super(Panel, self).dropEvent(event)
		return item

	def clone(self):
		item = self
		state = item.state
		state['geometry'] = self.geometry.copy()
		stateString = str(dumps(state, cls=JsonEncoder))
		info = QMimeData()
		if hasattr(item, 'text'):
			info.setText(str(item.text))
		else:
			info.setText(str(item))
		info.setData('application/panel-valueLink', QByteArray(stateString.encode('utf-8')))
		drag = QDrag(self.scene().views()[0].parent())
		drag.setPixmap(item.pix)
		drag.setHotSpot(item.rect().center().toPoint())
		# drag.setParent(child)
		drag.setMimeData(info)

	def focusInEvent(self, event: QFocusEvent) -> None:
		self.refreshHandles()
		super(Panel, self).focusInEvent(event)

	def refreshHandles(self):
		for handleGroup in self.allHandles:
			if handleGroup.isEnabled():
				handleGroup.show()
				handleGroup.updatePosition(self.rect())
				handleGroup.setZValue(self.zValue() + 1000)

	def focusOutEvent(self, event: QFocusEvent) -> None:
		for handleGroup in self.allHandles:
			handleGroup.hide()
			handleGroup.setZValue(self.zValue())
		self.setSelected(False)
		super(Panel, self).focusOutEvent(event)

	def stackOnTop(self):
		if self.parentItem():
			if (items := [item for item in self.parentItem().childItems() if isinstance(item, Panel)]):
				items.sort(key=lambda item: item.zValue())
				items.reverse()
				items.insert(0, self)
				parentZValue = self.parent.zValue() + 1
				# zValues = [int(self.zValue()), *[int(item.zValue()) for item in items]]
				# highestZValue = max(zValues)
				# lowest = min(zValues)
				# set zValues of items
				# degrease all the z _values by 1
				zValues = [parentZValue + (value/100) for value in range(len(items) + 1)]
				zValues.reverse()
				list(map(lambda item: item[1].setZValue(item[0]), zip(zValues, items)))
			# set the z value of the item to the highest z value
			# 	self.setZValue(highestZValue)
			else:
				self.setZValue(self.parentItem().zValue() + 1)

	def setZValue(self, value: int):
		# max(self.parent.zValue() + 1, value)
		super(Panel, self).setZValue(value)
		items = [item for item in self.childItems() if isinstance(item, Panel)]
		if items:
			list(map(lambda item: item.setZValue(value + 1), items))

	def moveToTop(self):
		items = self.scene().items()
		if items:
			highestZValue = max([item.zValue() for item in items])
			self.setZValue(highestZValue + 1)

	@property
	def neighbors(self):
		n = 10
		rect = self.boundingRect()
		rect.adjust(-n, -n, n, n)
		rect = self.mapToScene(rect).boundingRect()
		path = QPainterPath()
		path.addRect(rect)
		neighbors = [item for item in self.parent.childPanels if item is not self and item.sceneShape().intersects(path)]

		return neighbors

	def childHasFocus(self):
		return any(item.hasFocus() or item.childHasFocus() for item in self.childPanels)

	def siblingHasFocus(self):
		return self.parent.childHasFocus()

	def mousePressEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		if mouseEvent.buttons() == Qt.LeftButton | Qt.RightButton:
			mouseEvent.setButtons(Qt.LeftButton)
			mouseEvent.setButton(Qt.LeftButton)
			return self.mousePressEvent(mouseEvent)
		elif mouseEvent.modifiers() & Qt.KeyboardModifier.ControlModifier:
			self.clone()
			mouseEvent.accept()
			self.clearFocus()
			return
		elif mouseEvent.button() == Qt.RightButton and mouseEvent.buttons() ^ Qt.RightButton:
			mouseEvent.accept()
			return super(Panel, self).mousePressEvent(mouseEvent)
		elif mouseEvent.button() == Qt.MouseButton.LeftButton:
			# if self.resizeHandles.isEnabled() and self.resizeHandles.currentHandle is not None:
			# 	mouseEvent.ignore()
			# 	self.resizeHandles.mousePressEvent(mouseEvent)
			# if self.scene().focusStack.focusAllowed(self):

			if (self.scene().focusItem() is self.parent
			    or self.parent is self.scene().base
			    or self.hasFocus()
			    or self.siblingHasFocus()) and self.canFocus:
				self.scene().clearSelection()
				self.setSelected(True)
				mouseEvent.accept()
				self.setFocus(Qt.FocusReason.MouseFocusReason)
				self.stackOnTop()
				self.startingParent = self.parent
				if self.maxRect is None:
					self.maxRect = self.rect().size()
			else:
				mouseEvent.ignore()

	# self.parent.mousePressEvent(mouseEvent)

	# self.parentSelectionTimer.start()

	# self.setFocus(Qt.FocusReason.MouseFocusReason)
	# if self.resizeHandles.isVisible() and self.resizeHandles.currentHandle is not None:
	# 	# mouseEvent.accept()
	# 	self.handleSelected = self.resizeHandles.currentHandle
	# elif self.resizeHandles.isEnabled():
	# 	self.resizeHandles.update()
	# mouseEvent.accept()
	# self.resizeHandles.setVisible(True)
	# if hasattr(self, 'gridAdjusters') and self.gridAdjusters.isVisible() and self.gridAdjusters.currentHandle is not None:
	# 	loc = self.gridAdjusters.currentHandle.location
	# 	value = -1 if loc & loc.TopLeft else 1
	# 	if loc.isVertical:
	# 		self.grid.columns += value
	# 	else:
	# 		self.grid.rows += value
	# 	self.signals.resized.emit(self.rect().size())
	# else:
	# 	if self.maxRect is None:
	# 		self.maxRect = self.rect().size()
	# 	self.startingParent = self.parent
	# 	self.parent.setHighlighted(True)
	# 	self.hoverStart = mouseEvent.pos()
	# if self.parent is not self.scene():
	# 	effect = QGraphicsDropShadowEffect()
	# 	effect.setBlurRadius(5)
	# 	effect.setOffset(0, 0)
	# 	effect.setColor(Qt.white)
	# if self.parent is not self.scene():
	# 	self.parent.setGraphicsEffect(effect)
	# self.setGraphicsEffect(effect)
	# return super(Panel, self).mousePressEvent(mouseEvent)

	@property
	def canFocus(self) -> bool:
		parentIsFrozen = isinstance(self.parent, Panel) and self.parent.frozen
		return bool(int(self.flags() & QGraphicsItem.ItemIsFocusable)) and not parentIsFrozen

	def hold(self):
		self.setFlag(QGraphicsItem.ItemIsMovable, False)
		self.__hold = True

	def release(self):
		self.setFlag(QGraphicsItem.ItemIsMovable, True)
		self.__hold = False

	def mouseMoveEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		if self.__hold:
			return
		# if self.parentItem() is not self.scene().base:
		# 	self.startingParent = self.parent
		# 	self.setParentItem(self.scene().base)
		filledParent = self.rect().size().toSize() == self.parent.rect().size().toSize()
		if (filledParent or self.parent.hasFocus()) and isinstance(self.parent, (QGraphicsItemGroup, Panel)):
			mouseEvent.ignore()
			self.parent.mouseMoveEvent(mouseEvent)
		if not self.movable and isinstance(self.parent, Panel) and self.parent.movable and self.parent.childHasFocus() and self.parent is not self.scene():
			mouseEvent.ignore()
			self.parent.mouseMoveEvent(mouseEvent)
			self.parent.setFocus(Qt.FocusReason.MouseFocusReason)
		else:
			if hasattr(self.parent, 'childIsMoving'):
				self.parent.childIsMoving = True
			# self.hoverPosition = mouseEvent.scenePos()
			# if mouseEvent.lastPos() != mouseEvent.pos() and mouseEvent.buttons() & Qt.MouseButton.LeftButton:
			# 	self.hoverTimer.start()
			return super(Panel, self).mouseMoveEvent(mouseEvent)

	def mouseReleaseEvent(self, mouseEvent: QGraphicsSceneMouseEvent) -> None:
		if hasattr(self.parent, 'childIsMoving'):
			wasMoving = self.parent.childIsMoving
			self.parent.childIsMoving = False

			if wasMoving:
				releaseParents = [item for item in self.scene().items(mouseEvent.scenePos())
					if item is not self
					   and not item.isAncestorOf(self)
					   and self.parent is not item
					   and isinstance(item, Panel)
					   and item.onlyAddChildrenOnRelease]

				sorted(releaseParents, key=lambda item: item.zValue(), reverse=True)
				if releaseParents:
					releaseParent = releaseParents[0]
					self.setParentItem(releaseParent)
					self.updateFromGeometry()
		# self.geometry.setAbsolutePosition(self.pos())
		if self.scene().focusItem() is not self:
			self.setFocus(Qt.FocusReason.MouseFocusReason)
		# if self.hoverPosition:
		# 	self.stackOnTop()
		# if self.nextParent:
		# 	# newParent = self.findNewParent(mouseEvent.scenePos())
		# 	# if newParent is not None:
		# 	# 	if newParent is not self.parentItem():
		# 	self.setParentItem(self.nextParent)
		# 	self.parent.setFocus(Qt.FocusReason.OtherFocusReason)

		# self.hoverFunc()
		super().mouseReleaseEvent(mouseEvent)
		# self.resizeHandles.currentHandle = None
		self.mousePressPos = None
		self.hoverPosition = None
		self.hoverOffset = None
		self.previousParent = None
		self.maxRect = None
		self.startingParent = self.parent
		self.parent.setHighlighted(False)

	def mouseDoubleClickEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		if not self.parent in [self.scene(), self.scene().base]:
			self._fillParent = not self._fillParent
			if self._fillParent:
				self.fillParent()
			else:
				self.geometry.updateSurface()

	def fillParent(self, setGeometry: bool = False):
		if self.parent is None:
			log.warn('No parent to fill')
			return QRect(0, 0, 0, 0)
		area = self.parent.fillArea(self)
		if area:
			rect = area[0]
			pos = rect.topLeft()
			rect.moveTo(0, 0)
			self.setRect(rect)
			self.setPos(pos)
			if setGeometry:
				self.geometry.setAbsolutePosition(pos)
				self.geometry.setAbsoluteRect(rect)

	def fillArea(self, *exclude) -> List[QRectF]:
		spots = []
		mappedVisibleArea = self.mapFromScene(self.visibleArea(*exclude))
		polygons = mappedVisibleArea.toFillPolygons()
		for spot in polygons:
			rect = spot.boundingRect()
			if rect.width() > 20 and rect.height() > 20:
				spots.append(rect)
		spots.sort(key=lambda x: x.width()*x.height(), reverse=True)
		return spots

	def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent):
		# log.debug(f'hoverEnterEvent: {self}')
		# self.hideTimer.stop()
		# self.setFocus(Qt.FocusReason.MouseFocusReason)

		super(Panel, self).hoverEnterEvent(event)

	def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent):
		# log.debug(f'hoverLeaveEvent: {self}')
		super(Panel, self).hoverLeaveEvent(event)

	def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
		super(Panel, self).hoverMoveEvent(event)

	def findNewParent(self, position: QPointF):
		items = self.scene().items(position)
		items = getItemsWithType(items, Panel)
		items = [item for item in items if item is not self and item.acceptDrops()]
		items.sort(key=lambda item: item.zValue(), reverse=True)
		# log.debug(f'Items at {self.hoverPosition}: {items}')
		if items:
			return items[0]
		else:
			return None

	# return rect, p

	def similarEdges(self, other: 'Panel', rect: QRectF = None, singleEdge: LocationFlag = None):
		if singleEdge is None:
			edges = LocationFlag.edges()
		else:
			edges = [singleEdge]

		if rect is None:
			rect = self.rect()

		otherRect = self.parent.mapRectFromScene(other.sceneRect())

		matchedEdges = []
		for edge in edges:
			e = edge.fromRect(rect)
			for oEdge in [i for i in LocationFlag.edges() if i.sharesDirection(edge)]:
				o = oEdge.fromRect(otherRect)
				distance = abs(o - e)
				if distance <= 10:
					eX = Edge(self, edge, e)
					oX = Edge(other, oEdge, o)
					s = SimilarValue(eX, oX, distance)
					matchedEdges.append(s)
		matchedEdges.sort(key=lambda x: x.differance)
		return matchedEdges

	def contentsRect(self) -> QRectF:
		return self.geometry.absoluteRect()

	@cached_property
	def marginRect(self) -> QRectF:
		margins = self.contentsRect().marginsRemoved(self.margins.asQMarginF())
		return margins

	def setHighlighted(self, value: bool):
		self._highlighted = value
		self.update()

	def grandChildren(self) -> list['Panel']:
		if self._frozen:
			return [self]
		children = [i.grandChildren() for i in self.childPanels]
		# flatten children list
		children = [i for j in children for i in j]
		children.insert(0, self)
		return children

	def visibleArea(self, *exclude: 'Panel') -> QRectF:
		children = self.childPanels
		path = self.sceneShape()
		for child in children:
			if child.hasFocus() or child in exclude or not child.isVisible() or not child.isEnabled():
				continue
			path -= child.sceneShape()
		return path

	# section itemChange

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemSceneHasChanged:
			clearCacheAttr(value, 'panels')

		# if change == QGraphicsItem.ItemSelectedHasChanged:
		# 	if hasattr(self, 'resizeHandles') and self.resizeHandles.isEnabled():
		# 		self.resizeHandles.setVisible(value)
		# 	if self.shouldShowGrid():
		# 		if hasattr(self, 'gridAdjusters') and self.gridAdjusters.isEnabled():
		# 			self.gridAdjusters.setVisible(value)
		#
		# 	if value:
		# 		self.indicator.color = Qt.green
		# 		# self.setFlag(self.ItemStopsClickFocusPropagation, False)
		# 		# self.setFlag(self.ItemStopsFocusHandling, False)
		# 		# self.setFiltersChildEvents(False)
		# 		self.setHandlesChildEvents(True)
		# 	else:
		# 		# self.setFlag(self.ItemStopsClickFocusPropagation, True)
		# 		# self.setFlag(self.ItemStopsFocusHandling, True)
		# 		# self.setFiltersChildEvents(True)
		# 		self.setHandlesChildEvents(False)
		# 		self.indicator.color = Qt.white

		elif change == QGraphicsItem.ItemPositionChange:
			if QApplication.mouseButtons() & Qt.LeftButton and self.isSelected() and not self.focusProxy():
				area = polygon_area(self.shape())
				diff = value - self.pos()

				# if self.debug:
				# 	if self.parent is not self.scene().base:
				# 		self.visualAid.setVisible(True)
				# 		path = QPainterPath()
				# 		parentPos = self.mapFromParent(diff)
				# 		path.lineTo(parentPos)
				# 		self.visualAid.setPath(path)
				# 	else:
				# 		self.visualAid.hide()

				# if geoPosition.x.snapping:
				# 	value.setX(self.geometry.absoluteX)
				# if geoPosition.y.snapping:
				# 	value.setY(self.geometry.absoluteY)
				# if geoPosition.x.snapping and geoPosition.y.snapping:
				# 	return super(Panel, self).itemChange(change, value)

				rect = self.rect()
				rect.moveTo(value)

				similarEdges = [item for sublist in [self.similarEdges(n, rect=rect) for n in self.neighbors] for item in sublist]
				for s in similarEdges:
					loc = s.value.location
					oLoc = s.otherValue.location
					snapValue = s.otherValue.pix
					if loc.isRight:
						rect.moveRight(snapValue)
					elif loc.isLeft:
						rect.moveLeft(snapValue)
					elif loc.isTop:
						rect.moveTop(snapValue)
					elif loc.isBottom:
						rect.moveBottom(snapValue)
				if similarEdges:
					value = rect.topLeft()

				translated = self.sceneShape().translated(*diff.toTuple())

				if self.startingParent is not self.parent:
					translated = self.parent.mapFromItem(self.startingParent, translated)

				siblings = []
				areas = []
				collidingItems = [i for i in self.scene().items(translated) if
					i is not self and
					isinstance(i, Panel) and
					not self.isAncestorOf(i) and
					i.acceptsChildren and
					not i.onlyAddChildrenOnRelease and
					not i.frozen]

				for item in collidingItems:
					itemShape = translated.intersected(item.visibleArea())
					overlap = round(polygon_area(itemShape)/area, 5)
					if item.isUnderMouse():
						overlap *= 1.5
					if overlap:
						siblings.append(item)
						areas.append(overlap)

				collisions = [(item, area) for item, area in zip(siblings, areas) if item.acceptsChildren and area > item.collisionThreshold]
				collisions.sort(key=lambda x: (x[0].zValue(), x[1]), reverse=True)

				if collisions and any([i[1] for i in collisions]):
					p = self.parent
					newParent = collisions[0][0]
					if newParent is not p:
						p.setHighlighted(False)
						newParent.setHighlighted(True)
						self.setParentItem(newParent)

				# else:
				# 	collisions = [i for i in collisions if i[0] is not self.scene().base]
				# 	if collisions:
				#
				#
				# 		# 	# collisionItem = self.mapFromParent(collisions[0].shape()).boundingRect()
				# 		collisionItem = collisions[0][0].shape().boundingRect()
				# 		# if self.startingParent is not self.parent:
				#
				# 			# collisionItem = collisions[0][0].mapRectToScene(collisionItem)
				# 		# collisionItem = collisions[0][0].mapToScene(collisionItem).boundingRect()
				#
				#
				# 		# innerRect = QRectF(collisionItem)
				# 		panel = collisions.pop(0)
				# 		# n = 20
				# 		# innerRect.adjust(n, n, -n, -n)
				# 		# if innerRect.contains(value):
				# 		# 	# panel.resizeHandles.show()
				# 		# 	collisions = False
				# 		# 	self.setParentItem(panel)
				# 		# 	break
				#
				# 		x, y = value.x(), value.y()
				#
				# 		shape = shape.boundingRect()
				#
				# 		f = [abs(collisionItem.top() - shape.center().y()), abs(collisionItem.bottom() - shape.center().y()), abs(collisionItem.left() - shape.center().x()), abs(collisionItem.right() - shape.center().x())]
				# 		closestEdge = min(f)
				# 		if closestEdge == abs(collisionItem.top() - shape.center().y()):
				# 			y = collisionItem.top() - shape.height()
				# 			if y < 0:
				# 				y = collisionItem.bottom()
				# 		elif closestEdge == abs(collisionItem.bottom() - shape.center().y()):
				# 			y = collisionItem.bottom()
				# 			if y + shape.height() > self.parent.containingRect.height():
				# 				y = collisionItem.top() - shape.height()
				# 		elif closestEdge == abs(collisionItem.left() - shape.center().x()):
				# 			x = collisionItem.left() - shape.width()
				# 			if x < 0:
				# 				x = collisionItem.right()
				# 		elif closestEdge == abs(collisionItem.right() - shape.center().x()):
				# 			x = collisionItem.right()
				# 		value = QPointF(x, y)
				# else:
				#
				# 	self.indicator.color = Qt.green
				# 	if self.parentItem() is not self.scene().base:
				# 		self.setParentItem(self.scene().base)

				if self.startingParent is not None and self.startingParent is not self.parent:
					destination = self.parent
					start = self.startingParent
					value = destination.mapFromItem(start, value)

				if self._keepInFrame and self.parentGrid is not None and not self.parentGrid.overflow:
					intersection = self.parent.shape().intersected(self.shape().translated(*value.toTuple()))
					overlap = prod(intersection.boundingRect().size().toTuple())/area

					if overlap >= 0.75:
						frame = self.parent.rect()
						maxX = frame.width() - min(self.rect().width(), frame.width())
						maxY = frame.height() - min(self.rect().height(), frame.height())

						x = min(max(value.x(), 0), maxX)
						y = min(max(value.y(), 0), maxY)
						value.setX(x)
						value.setY(y)

				self.geometry.setPos(value)

		# section Child Added
		elif change == QGraphicsItem.ItemChildAddedChange:
			# Whenever a Panel is added
			if isinstance(value, Panel):
				if value.geometry.snapping:
					self.grid.gridItems.add(value.geometry)

				self.signals.resized.connect(value.parentResized)
				clearCacheAttr(self, 'childPanels')
				self.signals.childAdded.emit()

			# Whenever Handles are added
			elif isinstance(value, HandleGroup):
				clearCacheAttr(self, 'allHandles')
			elif isinstance(value, Handle):
				self.signals.resized.connect(value.updatePosition)

		# section Child Removed
		elif change == QGraphicsItem.ItemChildRemovedChange:
			# Removing Panel
			if isinstance(value, Panel):
				try:
					self.grid.gridItems.remove(value.geometry)
				except ValueError:
					pass
				except AttributeError:
					pass
				disconnectSignal(self.signals.resized, value.parentResized)
				clearCacheAttr(self, 'childPanels')
				self.signals.childRemoved.emit()

			# Removing Handle
			elif isinstance(value, HandleGroup):
				clearCacheAttr(self, 'allHandles')
				disconnectSignal(self.signals.resized, value.updatePosition)
				disconnectSignal(value.signals.action, self.updateFromGeometry)
			elif isinstance(value, Handle):
				disconnectSignal(self.signals.resized, value.updatePosition)

		elif change == QGraphicsItem.ItemParentChange:
			if value != self.parent and None not in (value, self.previousParent):
				if self.geometry.size.relative and value is not None:
					g = self.geometry.absoluteSize()/value.geometry.absoluteSize()
					self.geometry.setRelativeSize(g)
				self.previousParent = self.parent
			self.parent = value

		elif change == QGraphicsItem.ItemParentHasChanged:
			if hasattr(self.previousParent, 'childIsMoving'):
				self.previousParent.childIsMoving = False
			self.parent = value

			if hasattr(value, 'childIsMoving') and QApplication.mouseButtons() & Qt.LeftButton:
				value.childIsMoving = True

			# log.debug(f'Parent now {self.parent}')

			if value is not None:
				self.signals.parentChanged.emit()

		elif change == QGraphicsItem.ItemVisibleChange:
			if value:
				self.updateFromGeometry()

		# elif change == QGraphicsItem.ItemVisibleChange:
		# 	if value:
		# 		self.geometry.updateSurface()

		return super(Panel, self).itemChange(change, value)

	@property
	def parent(self) -> Union['Panel', 'LevityScene']:
		if self._parent is not None:
			return self._parent
		parents = [self.parentItem(), self.parentObject(), self.parentWidget()]
		for parent in parents:
			if parent is not None:
				return parent
		return self.scene()

	@parent.setter
	def parent(self, value: Union['Panel', 'LevityScene']):
		if self._parent is not value:
			self._parent = value

	# QGraphicsRectItem.setParentItem(self, value)

	def updateFromGeometry(self):
		self.setRect(self.geometry.absoluteRect())
		self.setPos(self.geometry.absolutePosition().asQPointF())
		self.update()

	def setGeometry(self, rect: Optional[QRectF], position: Optional[QPointF]):
		if rect is not None:
			self.geometry.setAbsoluteRect(rect)
			if self.geometry.size.snapping or self.geometry.size.relative:
				rect = self.geometry.absoluteRect()
			self.setRect(rect)
		if position is not None:
			self.geometry.setAbsolutePosition(position)
			if self.geometry.position.snapping or self.geometry.position.relative:
				position = self.geometry.absolutePosition()
			self.setPos(position)

	# elif self.snapping.size:
	# 	pass
	# elif self.geometry.size:
	# 	x = self.parent.width() * self.geometry.size.x
	# 	y = self.parent.height() * self.geometry.size.y
	# 	self.setRect(QRectF(0, 0, x, y))
	# if position is not None:
	# 	self.setPos(position)
	# elif self.snapping.location:
	# 	pass
	# elif self.geometry.position:
	# 	x = self.parent.width() * self.geometry.position.x
	# 	y = self.parent.height() * self.geometry.position.y
	# 	self.setPos(QPointF(x, y))

	# def setPos(self, pos: Union[QPointF, QPoint, Position, Tuple[float, float]]):
	# 	if isinstance(pos, Position):
	# 		pos = pos.toTuple()
	# 	if isinstance(pos, tuple):
	# 		pos = QPointF(*pos)
	# 	super(Panel, self).setPos(pos)

	@overload
	def setRect(self, pos: 'Position', size: 'Size'): ...

	@overload
	def setRect(self, args: tuple[Numeric, Numeric, Numeric, Numeric]): ...

	def setRect(self, rect):
		emit = self.rect().size() != rect.size()
		super(Panel, self).setRect(rect)
		if emit:
			clearCacheAttr(self, 'marginRect')
			clearCacheAttr(self, 'sharedFontSize')
			self.signals.resized.emit(rect)

	def updateRect(self, parentRect: QRectF = None):
		self.setRect(self.geometry.absoluteRect())

	def setMovable(self, value: bool = None):
		if value is None:
			value = not self.movable
		self.movable = value

	#
	@property
	def movable(self) -> bool:
		return bool(self.flags() & QGraphicsItem.ItemIsMovable)

	@movable.setter
	def movable(self, value: bool):
		self.setFlag(QGraphicsItem.ItemIsMovable, boolFilter(value))

	def setResizable(self, value: bool = None):
		if value is None:
			value = not self.resizable
		self.resizable = value

	@property
	def resizable(self):
		return self.resizeHandles.isEnabled()

	@resizable.setter
	def resizable(self, value):
		self.resizeHandles.setEnabled(boolFilter(value))

	def setClipping(self, value: bool = None):
		if value is None:
			value = not self.clipping
		self.clipping = value

	@property
	def clipping(self) -> bool:
		return bool(self.flags() & QGraphicsItem.ItemClipsChildrenToShape)

	@clipping.setter
	def clipping(self, value: bool):
		self.setFlag(QGraphicsItem.ItemClipsChildrenToShape, boolFilter(value))

	def setKeepInFrame(self, value: bool = None):
		if value is None:
			value = not self._keepInFrame
		self._keepInFrame = value

	@property
	def keepInFrame(self) -> bool:
		return self._keepInFrame

	@keepInFrame.setter
	def keepInFrame(self, value: bool):
		self._keepInFrame = value
		self.updateFromGeometry()

	def clipPath(self) -> QPainterPath:
		path = self.shape()
		if self.resizeHandles.isEnabled():
			for handle in self.resizeHandles.childItems():
				shape = handle.shape()

				shape = handle.mapToItem(self, shape)
				path += shape
		# shape = self.resizeHandles.shape()
		# path += shape
		path.closeSubpath()

		return path.simplified()

	def setShowGrid(self, value: bool = None):
		if value is None:
			value = not self.showGrid
		self.showGrid = value

	def sceneShape(self):
		# for panel in self.childPanels:
		# 	shape = shape.subtracted(panel.mappedShape())
		return self.mapToScene(self.shape())

	def sceneRect(self):
		return self.mapRectToScene(self.rect())

	def sceneShapePunched(self):
		return self.sceneShape() - self.childrenShape()

	def childrenShape(self):
		path = QPainterPath()
		for panel in self.childPanels:
			path += panel.sceneShape()
		return path

	def mappedShape(self) -> QPainterPath:
		return self.mapToParent(self.shape())

	def shouldShowGrid(self) -> bool:
		return any([self.isSelected(), *[panel.hasFocus() for panel in self.childPanels]]) and self.childPanels

	@property
	def isEmpty(self):
		return len([childPanel for childPanel in self.childPanels if not childPanel.isEmpty]) == 0

	# section paint

	def paint(self, painter, option, widget):
		if self.parent is None or self.scene() is None:
			return
		# return super(Panel, self).paint(painter, option, widget)
		color = colorPalette.window().color()
		# color.setAlpha(100)
		# painter.setBrush(color)
		# painter.setPen(Qt.NoPen)

		if self._contextMenuOpen or self.isSelected():
			painter.setPen(selectionPen)
			painter.setBrush(Qt.NoBrush)
			painter.drawRect(self.boundingRect())
			return

		if self.debug:
			# if self.parent and not self.parent.frozen:
			# 	painter.setBrush(self.color)
			# 	painter.drawPath(self.shape())
			painter.setPen(debugPen)
			# painter.setBrush(color)
			painter.drawPath(self.shape())

		if self.isEmpty or self.childIsMoving or self.isSelected() and not self.resizeHandles.isEnabled():
			painter.setPen(selectionPen)
			painter.setBrush(Qt.NoBrush)
			painter.drawRect(self.rect().adjusted(2, 2, -2, -2))

		if not self._frozen and (self.shouldShowGrid()):
			painter.setPen(gridPen)
			painter.setBrush(Qt.NoBrush)

	# if self.grid:
	# 	path = QPainterPath()
	# 	for i in range(1, self.grid.columns):
	# 		path.moveTo(i * self.grid.columnWidth, 0)
	# 		path.lineTo(i * self.grid.columnWidth, self.grid.rowHeight * self.grid.rows)
	# 	for i in range(1, self.grid.rows):
	# 		path.moveTo(0, i * self.grid.rowHeight)
	# 		path.lineTo(self.grid.columnWidth * self.grid.columns, i * self.grid.rowHeight)
	# 	for panel in self.childPanels:
	# 		path -= panel.mappedShape()
	# 	painter.drawPath(path)

	@cached_property
	def sharedFontSize(self):
		labels = [x for x in self.childPanels if hasattr(x, 'text')]
		if False:
			return sum([x.fontSize for x in labels])/len(labels)
		return min([x.fontSize for x in labels])

	@Slot(QPointF, QSizeF, QRectF, 'parentResized')
	def parentResized(self, arg: Union[QPointF, QSizeF, QRectF]):
		# if self.snapping.size and self.sizeRatio:
		# 	self.gridItem.width = self.sizeRatio[0] * self.parentGrid.columns
		# 	self.gridItem.height = self.sizeRatio[1] * self.parentGrid.rows
		# if self.snapping.location and self.positionRatio:
		# 	self.gridItem.column = self.positionRatio[0] * self.parentGrid.columns
		# 	self.gridItem.row = self.positionRatio[1] * self.parentGrid.rows

		# if self.geometry.size.relative or self.geometry.size.snapping:
		# 	self.updateRect()
		# if self.geometry.position.relative or self.geometry.position.snapping:

		if isinstance(arg, (QRect, QRectF, QSize, QSizeF)):
			self.geometry.updateSurface(arg)

	@property
	def containingRect(self):
		return self.rect()

	@property
	def globalTransform(self):
		return self.scene().views()[0].viewportTransform()

	@property
	def pix(self) -> QPixmap:
		pix = QPixmap(self.containingRect.size().toSize())
		pix.fill(Qt.transparent)
		painter = QPainter(pix)
		pix.initPainter(painter)
		painter.setRenderHint(QPainter.Antialiasing)
		opt = QStyleOptionGraphicsItem()
		self.paint(painter, opt, None)
		for child in self.childItems():
			child.paint(painter, opt, None)
		return pix

	def recursivePaint(self, painter: QPainter):
		t = QTransform.fromTranslate(*self.scenePos().toPoint().toTuple())
		# if hasattr(self.parentItem(), 'globalTransform'):
		# 	painter.setTransform(self.parentItem().globalTransform)
		# 	painter.setTransform(t, True)
		# else:
		painter.setTransform(t)
		self.paint(painter, QStyleOptionGraphicsItem(), None)
		for child in self.childItems():
			if hasattr(child, 'collapse'):
				continue
			if hasattr(child, 'recursivePaint'):
				child.recursivePaint(painter)
			else:
				child.paint(painter, QStyleOptionGraphicsItem(), None)

	def height(self):
		return self.rect().height()

	def width(self):
		return self.rect().width()

	@property
	def showGrid(self):
		return self._showGrid

	@showGrid.setter
	def showGrid(self, value):
		self._showGrid = value
		if self.gridAdjusters:
			self.gridAdjusters.setEnabled(value)
			self.gridAdjusters.setVisible(value)
		if value:
			self.update()

	@property
	def locked(self):
		return self._locked

	@locked.setter
	def locked(self, value):
		if value != self._locked:
			self.setFlag(QGraphicsItem.ItemIsMovable, not value)
			self.setFlag(QGraphicsItem.ItemStopsClickFocusPropagation, not value)
			# self.setFiltersChildEvents(value)
			for handle in self.allHandles:
				if not value:
					handle.setVisible(not value)
				handle.setEnabled(not value)
				handle.update()
		# self.setAcceptedMouseButtons(Qt.AllButtons if not value else Qt.RightButton)
		self._locked = value
		self.update()

	# if not value:
	# 	self.clearFocus()

	def setLocked(self, value: bool = None):
		if value is None:
			value = not self._locked
		self.locked = value

	@property
	def frozen(self) -> bool:
		return self._frozen

	@frozen.setter
	def frozen(self, value: bool):
		self.freeze(value)
		if value:
			self.showGrid = False

	def freeze(self, value: bool = None):
		if self._frozen == value:
			return
		if value is None:
			value = not self._frozen
		self._frozen = value
		for child in self.childPanels:
			child.setLocked(value)
		# self.setHandlesChildEvents(value)
		# self.setFiltersChildEvents(value)
		self.setFlag(QGraphicsItem.ItemStopsClickFocusPropagation, value)
		self.setFlag(QGraphicsItem.ItemStopsFocusHandling, value)
		# self.setHandlesChildEvents(value)
		self.setAcceptDrops(not value)

	@cached_property
	def childPanels(self) -> List['Panel']:
		items = [child for child in self.childItems() if isinstance(child, Panel)]
		items.sort(key=lambda x: (x.pos().y(), x.pos().x()))
		return items

	@property
	def hasChildren(self) -> bool:
		return len(self.childPanels) > 0 and self._includeChildrenInState

	def _save(self, path: Path = None, fileName: str = None):
		if path is None:
			path = userConfig.userPath.joinpath('saves', 'panels')
		if fileName is None:
			QMessageBox.critical(self.parent.parentWidget(), "Invalid Filename", "A filename must be provided")
			return

		if not path.exists():
			path.mkdir(parents=True)

		fileNameTemp = fileName + '.tmp'
		with open(path.joinpath(fileNameTemp), 'w') as f:
			dump(JsonEncoder.removeNullValues(self.state), f, indent=2, sort_keys=False, cls=JsonEncoder)
		try:
			with open(path.joinpath(fileNameTemp), 'r') as f:
				from Modules import hook
				load(f, object_hook=hook)
			replace(path.joinpath(fileNameTemp), path.joinpath(fileName))
			self.filePath = FileLocation(path, fileName)
		except Exception as e:
			QMessageBox.critical(self.parent.parentWidget(), "Error", f"Error saving dashboard: {e}")
			remove(path.joinpath(fileNameTemp))

	def _saveAs(self):
		path = userConfig.userPath.joinpath('saves', 'panels')

		path = path.joinpath(self.__class__.__name__)
		dialog = QFileDialog(self.parentWidget(), 'Save Dashboard As...', str(path))
		dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
		dialog.setNameFilter("Dashboard Files (*.levity)")
		dialog.setViewMode(QFileDialog.ViewMode.Detail)
		if dialog.exec_():
			fileName = Path(dialog.selectedFiles()[0])
			path = fileName.parent
			fileName = dialog.selectedFiles()[0].split('/')[-1]
			self._save(path, fileName)

	def save(self):
		if self.filePath is not None:
			self._save(*self.filePath.asTuple)
		else:
			self._saveAs()

	def delete(self):
		for item in self.childItems():
			if hasattr(item, 'delete'):
				item.delete()
			else:
				item.setParentItem(None)
				self.scene().removeItem(item)
		if self.scene() is not None:
			self.scene().removeItem(self)

	def wheelEvent(self, event) -> None:
		if self.acceptsWheelEvents:
			event.accept()
		else:
			event.ignore()
		super(Panel, self).wheelEvent(event)


class PanelFromFile:

	def __new__(cls, parent: Panel, filePath: Path, position: QPointF = None):
		if not isinstance(filePath, Path):
			filePath = Path(filePath)
		with open(filePath, 'r') as f:
			state = load(f, object_hook=hook)
			cls = state.pop('class')
			item = cls(parent, **state)
			path = filePath.parent
			fileName = str(filePath).split('/')[-1]
			extension = fileName.split('.')[-1]
			item.filePath = FileLocation(path, fileName, extension)
			item.updateSizePosition(True)
			if position is not None:
				item.setPos(position)
			item.frozen = True
			return item
