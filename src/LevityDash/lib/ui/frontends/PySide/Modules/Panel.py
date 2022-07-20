from functools import cached_property
from pprint import pprint
from pathlib import Path
from typing import Any, Callable, List, Optional, overload, Union, Sized, Set, ClassVar, Tuple
from uuid import uuid4

from math import prod
from PySide2.QtCore import QByteArray, QMimeData, QPointF, QRect, QRectF, QSize, QSizeF, Qt, QTimer, Slot, QPoint
from PySide2.QtGui import QColor, QDrag, QFocusEvent, QPainter, QPainterPath, QPixmap, QTransform, QBrush, QPen
from PySide2.QtWidgets import (QApplication, QFileDialog, QGraphicsItem, QGraphicsItemGroup,
                               QGraphicsSceneDragDropEvent,
                               QGraphicsSceneHoverEvent,
                               QGraphicsSceneMouseEvent,
                               QStyleOptionGraphicsItem)
from rich.repr import auto

from LevityDash.lib.ui.Geometry import Geometry
from LevityDash.lib.config import userConfig
from LevityDash.lib.EasyPath import EasyPathFile
from LevityDash.lib.utils.shared import (boolFilter, clearCacheAttr, disconnectSignal, getItemsWithType, Numeric,
                                         SimilarValue, _Panel, hasState)
from LevityDash.lib.stateful import StateProperty, Stateful, DefaultGroup
from LevityDash.lib.utils.geometry import Edge, LocationFlag, Margins, polygon_area, Position, Size
from LevityDash.lib.ui import UILogger as log
from LevityDash.lib.ui.colors import randomColor
from .Menus import BaseContextMenu
from .Handles import Handle, HandleGroup
from .Handles.Resize import ResizeHandles
from ..utils import GraphicsItemSignals, colorPalette, selectionPen, itemLoader
from LevityDash.lib.log import debug


@auto
class Panel(_Panel, Stateful, tag='group'):
	collisionThreshold: ClassVar[float] = 0.5
	onlyAddChildrenOnRelease: ClassVar[bool] = False
	_acceptsChildren: ClassVar[bool] = True
	savable: ClassVar[bool] = True
	_keepInFrame: ClassVar[bool] = True
	acceptsWheelEvents: ClassVar[bool] = False
	__exclude__: ClassVar[Set[str]] = set()
	__match_args__ = ('geometry',)
	deletable: ClassVar[bool] = True

	signals: GraphicsItemSignals
	filePath: Optional[EasyPathFile]
	_childIsMoving: bool

	__defaults__ = {
		'resizable': True,
		'movable':   True,
		'frozen':    False,
		'locked':    False,
	}

	# section Panel init
	def __init__(self, parent: _Panel, *args, **kwargs):
		# !setting the parent through the QGraphicsItem __init__ causes early
		# !isinstance checks to fail, so we do it manually later
		super(Panel, self).__init__()
		if debug:
			self.debugColor = QColor(randomColor(min=50, max=200))
			self.debugColor.setAlpha(200)
			self.debugPen = QPen(self.debugColor)
			brush = QBrush(self.debugColor)
			self.debugPen.setBrush(brush)
		self._parent = parent
		kwargs = Stateful.prep_init(self, kwargs)
		self._init_defaults_()
		self.setParentItem(parent)
		self._init_args_(*args, **kwargs)
		self.previousParent = self.parent
		self.setFlag(self.ItemClipsChildrenToShape, False)
		self.setFlag(self.ItemClipsToShape, False)

	def _init_args_(self, *args, **kwargs) -> None:
		self._name = kwargs.pop('name', None)
		self.setAcceptedMouseButtons(Qt.AllButtons if kwargs.get('clickable', None) or kwargs.get('intractable', True) else Qt.NoButton)
		self.state = kwargs

	def _init_defaults_(self):
		self._childIsMoving = False
		self._contextMenuOpen = False
		self.uuid = uuid4()
		self.uuidShort = self.uuid.hex[-4:]
		self.__hold = False
		self.signals = GraphicsItemSignals()
		self._geometry = None
		self._fillParent = False
		self.filePath = None
		self._locked = False
		self.startingParent = None
		self.previousParent = None
		self.maxRect = None
		self._frozen = False
		self._name = None

		self.resizeHandles.setEnabled(True)

		self.hideTimer = QTimer(interval=1000*3, singleShot=True, timeout=self.hideHandles)

		self.setAcceptHoverEvents(False)
		self.setAcceptDrops(True)
		self.setFlag(QGraphicsItem.ItemIsSelectable, True)
		self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
		self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, False)
		self.setFlag(QGraphicsItem.ItemIsFocusable, True)

		# self.setFlag(QGraphicsItem.ItemClipsToShape, True)
		# self.setFlag(QGraphicsItem.ItemClipsChildrenToShape, False)
		self.setBrush(Qt.NoBrush)
		self.setPen(QColor(Qt.transparent))
		self.setFlag(QGraphicsItem.ItemStopsClickFocusPropagation, True)
		self.setFlag(QGraphicsItem.ItemStopsFocusHandling, True)

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

	@property
	def childIsMoving(self):
		return self._childIsMoving

	@childIsMoving.setter
	def childIsMoving(self, value):
		if self._childIsMoving != value:
			self._childIsMoving = value

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

	def hideHandles(self):
		self.clearFocus()

	def setSize(self, *args):
		if len(args) == 1 and isinstance(args[0], QSizeF):
			size = args[0]
		elif len(args) == 2:
			size = QSizeF(*args)
		else:
			raise ValueError('Invalid arguments')
		self.setRect(self.rect().adjusted(0, 0, size.width(), size.height()))

	@property
	def acceptsChildren(self) -> bool:
		return self._acceptsChildren

	@acceptsChildren.setter
	def acceptsChildren(self, value: bool):
		self._acceptsChildren = value

	def __rich_repr__(self, **kwargs):
		if self.rect().width() <= 10 or self.rect().height() <= 10:
			yield 'rect', Size(*self.rect().size().toTuple())
		if getattr(self, '_geometry', None):
			yield 'position', self.geometry.position
			yield 'size', self.geometry.size
		yield from Stateful.__rich_repr__(self, exclude={'geometry'})

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

	@cached_property
	def resizeHandles(self):
		clearCacheAttr(self, 'allHandles')
		handles = ResizeHandles(self)
		return handles

	@cached_property
	def allHandles(self):
		return [handleGroup for handleGroup in self.childItems() if isinstance(handleGroup, (Handle, HandleGroup))]

	@StateProperty(default={'width': 1, 'height': 1, 'x': 0, 'y': 0}, match=True, allowNone=False)
	def geometry(self) -> Geometry:
		return self._geometry

	@geometry.setter
	def geometry(self, geometry):
		self._geometry = geometry

	@geometry.decode
	def geometry(self, value: dict | None) -> Geometry:
		match value:
			case None:
				return None
			case dict():
				return Geometry(surface=self, **value)
			case tuple():
				x, y, w, h = value
				return Geometry(surface=self, x=x, y=y, width=w, height=h)
			case _:
				raise ValueError('Invalid geometry', value)

	@geometry.after
	def geometry(self):
		self.geometry.updateSurface()

	@StateProperty(default=Margins.default(), allowNone=False, dependencies={'geometry'})
	def margins(self) -> Margins:
		return self._margins

	@margins.setter
	def margins(self, value: Margins):
		value.surface = self
		self._margins = value
		clearCacheAttr(self, 'marginRect')

	@margins.decode
	def margins(self, value: dict | list | tuple | str) -> Margins:
		match value:
			case str(value):
				return Margins(self, *value.split(','))
			case list(value) | tuple(value):
				return Margins(self, *value)
			case dict(value):
				return Margins(self, **value)
			case _:
				raise ValueError('Invalid margins', value)

	def show(self):
		self.updateFromGeometry()
		# if not all(self.rect().size().toTuple()):
		# 	self.setRect(self.geometry.rect())
		# 	self.setPos(self.gridItem.pos())
		super(Panel, self).show()

	def scene(self) -> 'LevityScene':
		return super(Panel, self).scene()

	@StateProperty(sort=True, sortKey=lambda x: x.geometry.sortValue, default=DefaultGroup(None, []), dependencies={'geometry', 'margins'})
	def items(self) -> List['Panel']:
		return [child for child in self.childItems() if isinstance(child, _Panel) and hasState(child)]

	@items.setter
	def items(self, value):
		self.geometry.updateSurface()
		existing = self.items if 'items' in self._set_state_items_ else []
		itemLoader(self, value, existing=existing)

	@items.condition(method='get')
	def items(owner: 'Panel') -> bool:
		return owner.hasChildren

	@items.condition(method={'get', 'set'})
	def items(value: List['Panel']) -> bool:
		if isinstance(value, Sized):
			return len(value) > 0
		return False

	def addItem(self, item: dict | _Panel, position: Position | QPoint | Tuple[float | int, float | int] = None):
		if isinstance(item, dict):
			item = itemLoader(self, [item])[0]
		else:
			item.setParentItem(self)
		item.updateSizePosition()
		item.geometry.relative = True

		# For whatever reason this prevents the item from jumping to the top left corner
		# when the item is first moved
		if position is not None:
			position = Position(position)
		else:
			position = item.geometry.position
		rect = item.rect()
		rect.moveTo(position.asQPointF())
		item.geometry.setGeometry(rect)

	@property
	def initArgs(self):
		return self.__initAgs__

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
		# self.resizeHandles.forceDisplay = True
		self.contextMenu.position = event.pos()
		self.setSelected(True)
		self.setFocus(Qt.MouseFocusReason)
		self.contextMenu.exec_(event.screenPos())
		self.setSelected(True)

	def underMouse(self):
		return self.scene().underMouse()

	def dragEnterEvent(self, event: QGraphicsSceneDragDropEvent):
		if self.acceptsChildren:
			if {*event.mimeData().formats()} & {'text/plain', 'text/yaml', 'text/x-yaml', 'application/x-yaml', 'application/yaml'}:
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
		fmt = {*event.mimeData().formats()} & {'text/plain', 'text/yaml', 'text/x-yaml', 'application/x-yaml', 'application/yaml'}
		invalidFormats = []
		loader = type(self).__loader__
		for fmt in fmt:
			data = event.mimeData().data(fmt)
			try:
				data = data.data().decode('utf-8')
				data = loader(data).get_data()
				break
			except Exception as e:
				invalidFormats.append((fmt, data, e))
		else:
			raise ValueError('Invalid data', invalidFormats)

		self.addItem(data, position=Position(event.pos()))

	def clone(self):
		item = self
		state = item.state
		stateString = self.__dumper__(state)
		info = QMimeData()
		if hasattr(item, 'text'):
			info.setText(str(item.text))
		else:
			info.setText(repr(item))
		info.setData('text/yaml', QByteArray(stateString.encode('utf-8')))
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
			if handleGroup.isEnabled() and handleGroup.surface is self:
				handleGroup.show()
				handleGroup.updatePosition(self.rect())
				handleGroup.setZValue(self.zValue() + 1000)
			else:
				handleGroup.hide()

	def focusOutEvent(self, event: QFocusEvent) -> None:
		for handleGroup in self.allHandles:
			handleGroup.hide()
			handleGroup.setZValue(self.zValue() + 100)
		self.setSelected(False)
		super(Panel, self).focusOutEvent(event)

	def stackOnTop(self, *above, recursive: bool = False):
		maxZ = max([item.z for item in above], default=0)
		if recursive:
			if parentFunc := getattr(self.parentItem(), 'stackOnTop', None):
				parentFunc(recursive=True)
		siblings = getattr(self.parentItem(), 'childPanels', [])
		for z, sibling in enumerate(sorted(filter(lambda x: x is not self and x.z >= maxZ, siblings), key=lambda x: x.z)):
			sibling.z = z
		self.z = len(siblings)

	def stackBelow(self, recursive: bool = False):
		if recursive:
			if parentFunc := getattr(self.parentItem(), 'stackBelow', None):
				parentFunc(recursive=True)
		siblings = getattr(self.parentItem(), 'childPanels', [])
		for z, sibling in enumerate(sorted(filter(lambda x: x is not self and x.z < self.z, siblings), key=lambda x: x.z)):
			sibling.z = z
		self.z = 0

	@property
	def z(self):
		return self.zValue()

	@z.setter
	def z(self, value):
		self.setZValue(value)

	@property
	def level(self):
		return getattr(self.parentItem(), 'level', -1) + 1

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
				self.stackOnTop(recursive=True)
				self.startingParent = self.parent
				if self.maxRect is None:
					self.maxRect = self.rect().size()
			else:
				mouseEvent.ignore()

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
		if wasMoving := getattr(self.parent, 'childIsMoving', False):
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
		self.previousParent = None
		self.maxRect = None
		self.startingParent = self.parent

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

	def setHighlighted(self, highlighted: bool):
		self._childIsMoving = highlighted

	# section itemChange

	def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
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
					not i._frozen]

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
						p.update()
						newParent.setHighlighted(True)
						self.setParentItem(newParent)
						newParent.update()

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

				if self._keepInFrame:
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

				self._geometry.setPos(value)

		# section Child Added
		elif change == QGraphicsItem.ItemChildAddedChange:
			# Whenever a Panel is added
			if isinstance(value, Panel):
				# if value.geometry.snapping:
				# 	self.grid.gridItems.add(value.geometry)

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

		# section Parent Changed
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
			self.stackOnTop()

			if hasattr(value, 'childIsMoving') and QApplication.mouseButtons() & Qt.LeftButton:
				value.childIsMoving = True

			# log.debug(f'Parent now {self.parent}')

			if value is not None:
				self.signals.parentChanged.emit()

		# elif change == QGraphicsItem.ItemVisibleChange:
		# if value:
		# 	self.updateFromGeometry()

		# elif change == QGraphicsItem.ItemVisibleChange:
		# 	if value:
		# 		self.geometry.updateSurface()

		return super(Panel, self).itemChange(change, value)

	@property
	def parent(self) -> Union['Panel', 'LevityScene']:
		if (parent := getattr(self, '_parent', None)) is None:
			parent = self.parentItem() or self.scene()
			self._parent = parent
		return parent

	@parent.setter
	def parent(self, value: Union['Panel', 'LevityScene']):
		if getattr(self, '_parent', None) is not value:
			self._parent = value

	def updateFromGeometry(self):
		self.setRect(self.geometry.absoluteRect())
		self.setPos(self.geometry.absolutePosition().asQPointF())

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

	@StateProperty(default=True, allowNone=False)
	def movable(self) -> bool:
		return bool(self.flags() & QGraphicsItem.ItemIsMovable)

	@movable.setter
	def movable(self, value: bool):
		self.setFlag(QGraphicsItem.ItemIsMovable, boolFilter(value))

	@movable.condition
	def movable(self) -> bool:
		return not getattr(self.parent, 'frozen', False)

	@movable.condition
	def movable(self) -> bool:
		return not self.frozen or not self.locked

	def setResizable(self, value: bool = None):
		if value is None:
			value = not self.resizable
		self.resizable = value

	@StateProperty(default=True)
	def resizable(self) -> bool:
		return self.resizeHandles.isEnabled()

	@resizable.setter
	def resizable(self, value):
		self.resizeHandles.setEnabled(boolFilter(value))

	@resizable.condition
	def resizable(self) -> bool:
		return not getattr(self.parent, 'frozen', False)

	@resizable.condition
	def resizable(self) -> bool:
		return not self.frozen or not self.locked

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
		color = colorPalette.window().color()
		# if debug:
		# 	pen = painter.pen()
		# 	brush = painter.brush()
		# 	painter.setPen(self.debugPen)
		# 	painter.setBrush(self.debugColor)
		# 	painter.drawRect(self.rect())
		# 	painter.setPen(pen)
		# 	painter.setBrush(brush)

		if self._contextMenuOpen or self.isSelected():
			painter.setPen(selectionPen)
			painter.setBrush(Qt.NoBrush)
			painter.drawRect(self.boundingRect())
			return

		# if debug:
		# 	if self.parent and not self.parent.frozen:
		# 		painter.setBrush(self.color)
		# 		painter.drawPath(self.shape())
		# 	painter.setPen(debugPen)
		# 	# painter.setBrush(color)
		# 	painter.drawPath(self.shape())

		if self.isEmpty or self.childIsMoving or self.isSelected() and not self.resizeHandles.isEnabled():
			painter.setPen(selectionPen)
			painter.setBrush(Qt.NoBrush)
			painter.drawRect(self.rect().adjusted(2, 2, -2, -2))

		super().paint(painter, option, widget)

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

	@StateProperty(default=False)
	def locked(self) -> bool:
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

	@locked.condition
	def locked(self) -> bool:
		return not getattr(self.parent, 'frozen', False)

	def setLocked(self, value: bool = None):
		if value is None:
			value = not self._locked
		self.locked = value

	@StateProperty(default=False)
	def frozen(self) -> bool:
		return self._frozen

	@frozen.setter
	def frozen(self, value: bool):
		self.freeze(value)

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
		return len(self.items) > 0 and getattr(self, 'includeChildrenInState', True)

	def _save(self, path: Path = None, fileName: str = None):
		raise NotImplementedError

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


class NonInteractivePanel(Panel):

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.setFlag(QGraphicsItem.ItemIsMovable, False)
		self.setFlag(QGraphicsItem.ItemIsSelectable, False)
		self.setFlag(QGraphicsItem.ItemIsFocusable, False)
		self.setFlag(QGraphicsItem.ItemStopsClickFocusPropagation, True)
		self.setFlag(QGraphicsItem.ItemStopsFocusHandling, True)
		self.setAcceptDrops(False)
		self.setHandlesChildEvents(False)
		self.setFiltersChildEvents(False)
		self.setAcceptTouchEvents(False)
		self.setAcceptedMouseButtons(Qt.NoButton)

		def mousePressEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
			mouseEvent.ignore()
			return

		def mouseMoveEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
			mouseEvent.ignore()
			return

		def mouseReleaseEvent(self, mouseEvent):
			mouseEvent.ignore()
			return


class PanelFromFile:

	def __new__(cls, parent: Panel, filePath: Path, position: QPointF = None):
		raise NotImplementedError


__all__ = ['Panel', 'NonInteractivePanel', 'PanelFromFile']
