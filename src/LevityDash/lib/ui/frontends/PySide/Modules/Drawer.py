import numpy as np
from functools import cached_property
from json import dumps
from typing import Any, Callable, Iterable, Optional, Union

import math
from PySide2.QtCore import QByteArray, QMimeData, QPoint, QPointF, QRect, QRectF, Qt, QTimer, Slot
from PySide2.QtGui import QColor, QDrag, QFocusEvent, QPainter, QPainterPath, QPen, QPixmap
from PySide2.QtWidgets import QGraphicsBlurEffect, QGraphicsItem, QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsSceneHoverEvent, QGraphicsSceneMouseEvent, QGraphicsSceneWheelEvent

from LevityDash.lib.plugins.observation import TimeAwareValue
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime import LockedRealtime
from LevityDash.lib.ui.frontends.PySide.Modules.glyphs import BackArrow, Plus
from LevityDash.lib.plugins.categories import CategoryDict, CategoryItem
from LevityDash.lib.Geometry.Grid import Grid
from LevityDash.lib.Geometry import Geometry, GridItem
from LevityDash.lib.ui.frontends.PySide.utils import GraphicsItemSignals, mouseHoldTimer, mouseTimer
from LevityDash.lib.utils.shared import clearCacheAttr, levenshtein
from LevityDash.lib.utils.geometry import Alignment, angleBetweenPoints, GridItemSize, Margins, Position, Size
from LevityDash.lib.plugins.dispatcher import ValueDirectory, MultiSourceContainer

from LevityDash.lib.ui.frontends.PySide.Modules.Handles.Various import DrawerHandle, HoverArea, IndoorIcon
from LevityDash.lib.ui.frontends.PySide.Modules.Label import Label, TitleLabel
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel


class ScrollRect(Panel):
	savable = False

	def __init__(self, *args, **kwargs):
		kwargs['geometry'] = {'fillParent': True}
		super().__init__(*args, **kwargs)
		# self.setEnabled(False)
		# self.setLocked(True)
		self.parent.signals.resized.connect(self.parentResized)
		self.setMovable(True)
		self.setAcceptDrops(False)
		self.resizeHandles.setEnabled(False)
		self.setAcceptedMouseButtons(Qt.AllButtons)
		self.staticGrid = False

	def hoverFunc(self):
		pass

	# print('hoverBlock')
	# pass

	def setPos(self, pos: QPointF):
		super(ScrollRect, self).setPos(pos)

	def updateSizePosition(self):
		self.setRect(self.rect())

	def parentResized(self, *arg):
		rect = arg[0]
		if not isinstance(rect, (QRectF, QRect)):
			rect = self.parent.rect()
		r = self.rect()
		r.setHeight(rect.height())
		self.setRect(r)
		super(ScrollRect, self).parentResized(arg)

	def setRect(self, rect):
		rect = self.grid.gridRect()
		rect.setHeight(self.parent.rect().height())
		super(ScrollRect, self).setRect(rect)

	def setGeometry(self, rect: Optional[QRectF], position: Optional[QPointF]):
		self.setRect(rect)

	def width(self):
		return self.parent.width()

	def height(self):
		return self.parent.height()

	@property
	def grid(self):
		return self.parent.grid

	@property
	def containingRect(self):
		return self.parent.rect()

	def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
		self.setFocus(Qt.MouseFocusReason)
		event.accept()
		super(ScrollRect, self).mousePressEvent(event)

	# 	self.parent.mousePressEvent(event)
	#
	# 	super(ScrollRect, self).mousePressEvent(event)

	def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
		event.accept()
		diff = event.scenePos() - event.lastScenePos()
		self.moveBy(*diff.toTuple())
		# 	self.parent.mouseMoveEvent(event)
		super(QGraphicsRectItem, self).mouseMoveEvent(event)

	def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
		# self.parent.mouseReleaseEvent(event)
		event.accept()
		super(ScrollRect, self).mouseReleaseEvent(event)

	def itemChange(self, change: int, value: Any) -> Any:
		if change == self.ItemPositionChange:
			frame = self.rect()
			maxX = self.parent.width() - frame.width()
			maxY = self.parent.height() - frame.height()
			x = min(max(value.x(), maxX), 0)
			y = min(max(value.y(), maxY), 0)
			value.setX(x)
			value.setY(y)
			return super(QGraphicsRectItem, self).itemChange(change, value)
		if change == self.ItemPositionHasChanged:
			return super(QGraphicsRectItem, self).itemChange(change, value)
		return super().itemChange(change, value)

	def parentResized(self, arg):
		self.setRect(self.grid.gridRect())


class RadialMenuItem(Panel):
	savable = False
	root: 'RadialMenu' = None

	angle: float = 90
	start: float = 270
	iconSize: float = 200

	def __init__(self, *args, key: CategoryItem = None, subItems: CategoryDict = None, value: TimeAwareValue = None, **kwargs):
		if self.__class__.root is None:
			self.__class__.root = self
		self.showing = False
		self.__boundingRect = QRectF(0, 0, self.iconSize, self.iconSize)
		super(RadialMenuItem, self).__init__(*args, **kwargs)
		self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
		self.backArrow = BackArrow(self)
		self.subItems = subItems

		self.key = key
		self.lookupTable = {}
		self.value = value

		self.clipping = False
		self.backArrow.update()
		self.backArrow.hide()

		self.resizeHandles.setEnabled(False)
		self.resizeHandles.setVisible(False)
		self.resizable = False
		self.movable = False

		self.setZValue(1000)

		self.backArrow.setZValue(self.zValue() + 10)
		self.setAcceptHoverEvents(True)

		self.label = Label(self, text=str(key), geometry={'fillParent': True}, margin={'left': 0, 'right': 0, 'top': 0, 'bottom': 0})
		self.label.setLocked(True)
		self.label.geometry.relative = True

		if subItems:
			# if key in aliases:
			# 	key = aliases[key]
			# 	font = weatherGlyph
			# else:
			# 	font = None

			# self.title = TitleLabel(self, text=str(self.key))
			# self.title.setLocked(True)
			self.subItems = subItems

		# Move to bottom of scene rect

		radialPath = QGraphicsPathItem(self)
		self.backgroundImage = QGraphicsPixmapItem(radialPath)

		path = QPainterPath()
		path.arcMoveTo(0, 0, self.iconSize, self.iconSize, self.start)
		path.arcTo(0, 0, self.iconSize, self.iconSize, self.start, self.angle)
		path.translate(-self.iconSize/2, -self.iconSize/2)
		# path = QPainterPath()
		# path.arcMoveTo(0, 0, self.iconSize, self.iconSize, self.start)
		# path.arcTo(0, 0, self.iconSize, self.iconSize, self.start, self.angle)
		# path.translate(-self.iconSize / 2, -self.iconSize / 2)
		#
		radialPath.setPath(path)
		#
		# # set pen to red with width of 5
		radialPath.setPen(Qt.NoPen)
		color = QColor(Qt.black)
		# color.setAlpha(200)
		radialPath.setBrush(color)
		radialPath.setZValue(self.zValue() - 100)
		radialPath.setParentItem(self)

		self.path = radialPath
		self.displayGeometry = Geometry(self, size=Size(100, 100), absolute=True)
		self.menuGeometry = Geometry(self, size=Size(100, 100), position=Position(0, 0), absolute=True)
		self.__hold = True
		if self.isRoot:
			self.hideTimer = QTimer()
			self.hideTimer.setSingleShot(True)
			self.hideTimer.timeout.connect(lambda x=self: x.collapse(hide=True))
			self.hideTimer.setInterval(1000)
			self.plus = Plus(self)
			self.plus.setZValue(self.zValue() + 10)
			self.plus.update()
			self.plus.show()
			self.path.hide()
			self.label.hide()
			self.hoverArea = HoverArea(self, enterAction=self.show, exitAction=None)
			self.geometry = self.displayGeometry
			self.updateFromGeometry()
			ValueDirectory.newKeys.connectSlot(self.refreshRoot)
			self.refreshRoot()
			self.collapse()
			self.hide()
		else:
			self.geometry = self.displayGeometry
			self.hide()

	# self.title.hide()

	@property
	def isRoot(self) -> bool:
		return self.root is self

	def shape(self) -> QPainterPath:
		return self.path.shape()

	def buildSubItems(self):
		for key, item in self.subItems.items():
			subkwargs = {'parent': self, 'key': key}
			if isinstance(item, CategoryDict):
				subkwargs['subItems'] = item
				self.lookupTable[key] = RadialMenuItem(**subkwargs)
			elif key == 'sources':
				self.lookupTable['sources'] = RadialMenuItem(parent=self, key="sources", subItems=item)
			else:
				subkwargs['value'] = item
				self.lookupTable[key] = LockedRealtime(**subkwargs)
				self.lookupTable[key].hide()

	def refreshRoot(self):
		if self.isRoot:
			ValueDirectory.categories.refresh()
			self.subItems = ValueDirectory.categories

	# self.buildSubItems()
	# showAfter = self.showingself.showing
	# self.collapse()

	def hideChildren(self, exclude=None):
		for item in self.childItems():
			if item is not exclude:
				item.hide()

	def showChildren(self, exclude=None):
		for item in self.childItems():
			if item is not exclude and item.isEnabled():
				item.show()

	def hideLabels(self):
		self.label.hide()
		# self.title.hide()
		self.backArrow.show()

	def showLabels(self):
		self.label.show()
		# self.title.show()
		self.backArrow.hide()

	def hide(self):
		if self.isUnderMouse():
			return
		super(RadialMenuItem, self).hide()

	def show(self):
		if self.isRoot:
			# self.ppix = QPixmap(self.scene().sceneRect().size().toSize())
			# self.ppix.fill(Qt.red)
			self.ppix = self.scene().views()[0].grab(self.scene().sceneRect().toRect())
		self.setZValue(1000)
		super(RadialMenuItem, self).show()

	def setItems(self):
		self.setFocus(Qt.MouseFocusReason)
		self.backgroundImage.setPixmap(self.scene().views()[0].grab(self.scene().sceneRect().toRect()))
		if self.isRoot:
			self.plus.hide()
			self.plus.setEnabled(False)
			self.label.hide()
			self.label.setEnabled(False)
		if isinstance(self.parent, RadialMenuItem):
			self.parent.hideChildren(self)
		self.showChildren()
		self.hideLabels()
		self.show()
		self.backArrow.show()
		self.label.hide()

		spacing = 0.7
		layer = 1
		self.showing = True
		# arcLength = 2 * math.pi * self.iconSize * layer / 4 / items
		I = 0
		if isinstance(self.subItems, CategoryDict):
			self.subItems.refresh()
		elif isinstance(self.subItems, dict):
			for item in self.subItems.values():
				item.refresh()
		quantity = len(self.subItems.keys())

		startAngle = 90/max(quantity - 1, 1)/2

		items = [i for i in self.childItems() if isinstance(i, RadialMenuItem)]
		previousItem = None
		for i in dict(self.lookupTable).keys():
			if i not in self.subItems.keys():
				abandon = self.lookupTable.pop(i)
				self.scene().removeItem(abandon)
				abandon.setParentItem(None)

		# if 3 > quantity or quantity > 5:
		# 	# first check to see if there are any _values that contain more _values
		# 	_values = [(key, value) for key, value in self.subItems.items() if isinstance(value, CategoryDict)]
		#
		# 	if len(_values) > 0:
		# 		# find the smallest subcategory
		#
		# 		smallest = min(_values, key=lambda x: len(x[1].keys()))
		# 		if len(smallest[1].keys()) < 4:
		# 			items = dict(self.subItems)
		# 			toFlatten = dict(items.pop(smallest[0]))
		#
		# 			for key, value in toFlatten.items():
		# 				if isinstance(value, CategoryDict):
		# 					for k, v in value.items():
		# 						items[k] = v
		# 				else:
		# 					items[key] = value
		#
		# 			items = items.items()
		#
		# 			quantity = len(items)
		# 		else:
		# 			items = self.subItems.items()
		# 	else:
		# 		items = self.subItems.items()
		# else:
		items = list(i for i in self.subItems.items() if str(i[0]) != 'time')

		# sort items alphabetically but put the key that is the same at the top
		# items.sort(key=lambda x: (x[0] != self.key, x[0]))

		# sort items based on key similarity
		# items.sort(key=lambda x: levenshtein(str(x[0]), str(self.key)))

		# sort items based on frequency of use and key similarity
		items.sort(key=lambda x: (len(x) if isinstance(x, Iterable) else x[1], levenshtein(str(x[0]), str(self.key))), reverse=True)

		size = self.iconSize*spacing

		for i, (key, value) in enumerate(items):
			self.scene().update()
			if key not in self.lookupTable:
				if isinstance(value, CategoryDict):
					kwargs = {'parent': self, 'key': key, 'subItems': value}
					self.lookupTable[key] = RadialMenuItem(**kwargs)
				elif key == 'sources':
					self.lookupTable['sources'] = RadialMenuItem(parent=self, key="sources", subItems=value)
				else:
					self.lookupTable[key] = LockedRealtime(parent=self, value=value)

			item = self.lookupTable[key]

			if isinstance(item, RadialMenuItem):
				item.path.hide()

			arcLength = 2*math.pi*size*layer/4
			itemSize = 100
			# if I > itemsForThisLayer:
			# 	I = 0
			# 	layer += 1
			# 	itemsForThisLayer = arcLength // itemSize
			# 	arcLength = 2 * math.pi * size * layer / 4 / quantity

			if previousItem:
				pointA = previousItem.rect().bottomLeft() + previousItem.pos()
				a = pointA.y()
				c = size*layer
				pointA.setX(math.sqrt(abs(c ** 2 - a ** 2)) - 20)
				if pointA.y() > size*layer:
					layer += 1
					I = 0
					angle = 0
				else:
					bottom = previousItem.mapRectFromParent(previousItem.rect()).bottom()
					angle = angleBetweenPoints(pointA, degrees=True)
					apparentAngle = angle + 180
					if apparentAngle > 90:
						layer += 1
						I = 0
						angle = 0
			else:
				angle = 0
			# if angle > self.start + 90:
			# 	I = 0
			# 	angle = 0
			# 	layer += 1
			# angle += startAngle
			# angle += self.start
			x = math.cos(math.radians(angle + 180 if angle else 0))*size*layer
			y = math.sin(math.radians(angle + 180 if angle else 0))*size*layer

			# add another layer if there are too many items

			# x += self.iconSize / 2
			# y += self.iconSize / 2
			if hasattr(item, 'displayGeometry'):
				item.geometry = item.displayGeometry
			item.geometry.position.x.setAbsolute(x)
			item.geometry.position.y.setAbsolute(y)
			item.updateFromGeometry()
			item.show()

			# item.title.show()
			# item.title.updateFromGeometry()
			if isinstance(item, RadialMenuItem):
				item.unsetItems()
			if hasattr(item, 'label'):
				item.label.updateFromGeometry()
				item.label.show()
			previousItem = item
			I += 1

		# size *= layer * 2
		# size += itemSize * math.pi
		path = QPainterPath()
		scenePath = QPainterPath()
		self.__boundingRect = QRectF(0, 0, size*layer + 170, size*layer + 170)
		scenePath.addRect(self.__boundingRect)
		path.addEllipse(QPoint(0, 0), size*layer + 170, size*layer + 170)
		path = scenePath.intersected(path)
		# path.arcMoveTo(0, 0, size, size, self.start)
		# path.arcTo(0, 0, size, size, self.start, self.angle)
		# path.lineTo(0, 0)
		# path.closeSubpath()
		# path.translate(-size / 2, -size / 2)
		self.path.setPath(path)
		self.prepareGeometryChange()
		self.path.show()
		self.path.setFlag(self.ItemClipsChildrenToShape, True)
		# self.setFlag(self.ItemHasNoContents, True)

		# self.setFlag(self.ItemHasNoContents, False)
		effect = QGraphicsBlurEffect()
		effect.setBlurRadius(30)
		self.backgroundImage.setGraphicsEffect(effect)
		self.backgroundImage.setPos(0, 0)
		self.backgroundImage.show()
		self.backgroundImage.setOpacity(0.6)
		self.scene().update()

	def setZValue(self, value: int):
		if self.root is self:
			value = 1000
		else:
			value = self.parent.zValue() + 1
		super(RadialMenuItem, self).setZValue(value)

	def containingRect(self):
		return self.rect()

	def unsetItems(self, exclude=None):
		path = QPainterPath()
		path.addEllipse(QPoint(0, 0), 200, 200)
		self.__bounidngRect = QRect(0, 0, 200, 200)
		scenePath = QPainterPath()
		scenePath.addRect(self.__boundingRect)
		path = scenePath.intersected(path)
		self.path.setPath(path)

		self.showing = False
		self.showLabels()
		# items = [i for i in self.childItems() if isinstance(i, (RadialMenuItem, LockedRealtime)) and i != exclude]
		for item in self.childPanels:
			if item is exclude:
				continue
			if isinstance(item, RadialMenuItem):
				item.unsetItems(exclude)
			item.hide()
		if hasattr(self, 'plus'):
			self.plus.setEnabled(True)
			self.plus.show()
			self.label.setEnabled(True)
			self.label.hide()
		# self.backgroundImage.hide()
		self.path.hide()
		self.scene().update()

	def collapse(self, hide: bool = False):
		self.scene().clearSelection()
		self.__boundingRect = self.containingRect()
		if hasattr(self, 'plus'):
			self.unsetItems()
			if hide:
				self.hide()
		else:
			self.parent.collapse()

	def collapseAndHide(self):
		self.collapse(hide=True)

	def startHideTimer(self, interval: Union[int, float] = None):
		if interval is not None:
			self.root.hideTimer.setInterval(int(interval*1000))
		self.root.hideTimer.start()

	def stopHideTimer(self):
		self.root.hideTimer.stop()

	def setRect(self, rect: QRectF):
		super(RadialMenuItem, self).setRect(rect)

	def boundingRect(self):
		if self.showing:
			return self.__boundingRect
		return super(RadialMenuItem, self).boundingRect()

	# def mouseMoveEvent(self, mouseEvent):
	# 	print(f'{angleBetweenPoints(mouseEvent.scenePos(), degrees=True)}\r', end='')

	# super(RadialMenuItem, self).mousePressEvent(mouseEvent)
	# if self.subItems is None:
	# 	pass
	def mousePressEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		# if self.showing:
		mouseEvent.accept()

	# super(RadialMenuItem, self).mousePressEvent(mouseEvent)

	# self.root.setFocus(Qt.MouseFocusReason)

	def mouseMoveEvent(self, event):
		event.ignore()

	def mouseReleaseEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		if self.subItems:
			if not self.showing:
				if isinstance(self.parent, RadialMenuItem):
					self.parent.unsetItems(exclude=self)
					self.geometry = self.menuGeometry
					self.updateFromGeometry()
				self.setItems()
			elif self.displayGeometry.rect().contains(mouseEvent.pos()):
				self.parent.show()
				self.unsetItems()
				if isinstance(self.parent, RadialMenuItem):
					self.parent.setItems()
		self.scene().clearSelection()

	def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent):
		if self.showing:
			event.accept()
		self.stopHideTimer()
		super(RadialMenuItem, self).hoverEnterEvent(event)

	def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
		self.startHideTimer(15)

	def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent):
		if self.boundingRect().contains(event.pos()):
			event.ignore()
			return
		if self.showing:
			print('hiding in 200ms')
			if self.root.childHasFocus():
				self.startHideTimer(5)
			else:
				self.startHideTimer(0.2)
		super(RadialMenuItem, self).hoverLeaveEvent(event)

	def focusInEvent(self, event: QFocusEvent) -> None:
		super(RadialMenuItem, self).focusInEvent(event)

	def focusOutEvent(self, event: QFocusEvent) -> None:
		if not self.root.childHasFocus():
			self.root.collapse()

	def hasFocus(self):
		return self.scene().focusItem() is self or self.focusItem() is self

	def rootHasFocus(self):
		return self.root.childHasFocus() or self.root.hasFocus()


class APIRect(ScrollRect):
	savable = False

	def __init__(self, *args, **kwargs):
		super(APIRect, self).__init__(*args, **kwargs)
		self.clickHoldTimer = mouseHoldTimer(self.startPickup)
		# self.insertBlanks()
		# from src.merger import observations
		self.grid.overflow = [False, True]

		# 	EndpointRect(self.scene().base, endpoint=endpoint)
		# # x = endpoint.realtime
		# # x['time.temperature'] = x['environment.temperature.temperature']
		# # clearCacheAttr(x.categories, '_dict')
		# # x = endpoint.realtime['*.temperature']
		# # x = endpoint.realtime['temperature']
		# # endpoint.get('temperature')
		# endpoint.category = None
		# endpoint.level = None
		# a = CategoryDict(None, endpoint.items(), None)
		# a._dict
		# # a = endpoint.containerValue('temperature')
		# endpoint.hourly.categories.subKeys()
		# endpoint.realtime.updateHandler.newKey.connect(self.insertSubscription)
		# for item in endpoint.realtime._values():
		# 	self.insertSubscription(item)
		# if not observations._values():
		# 	self.insertBlanks()
		self.show()

	def insertBlanks(self):
		words = ["within", "future", "marriage", "occasion", "paper", "past", "present", "previous", "prospective", "recent", "religion", "residence", "school", "social", "state", "travel", "work"]
		for word in words[:10]:
			LockRealtimeDisplay(parent=self, subscription=None, text=word)

	def insertSubscription(self, item):
		LockRealtimeDisplay(parent=self, valueLink=item)

	def startPickup(self):
		item = [item for item in (self.scene().items(self.clickHoldTimer.position)) if item in self.childPanels]
		if item:
			item = item[0]
			stateString = str(dumps(item.state, cls=JsonEncoder))
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
			self.parent.close()
			status = drag.exec_()

	def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
		self.clickHoldTimer.start(event.scenePos())
		super(APIRect, self).mousePressEvent(event)

	def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
		self.clickHoldTimer.updatePosition(event.scenePos())
		super(APIRect, self).mouseMoveEvent(event)

	def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
		self.clickHoldTimer.stop()
		super(APIRect, self).mouseReleaseEvent(event)


class PanelDrawer(Panel):
	_keepInFrame = False
	savable = False
	centralPanel: 'CentralPanel'

	def __init__(self, parent: 'LevityScene', centralPanel: 'CentralPanel', *args, **kwargs):
		self.centralPanel = centralPanel
		kwargs['geometry'] = {'size': {'width': 1, 'height': 0.1}, 'position': {'x': 0, 'y': -0.1}, 'absolute': False}
		super(PanelDrawer, self).__init__(parent, *args, **kwargs)
		self.centralPanel.signals.resized.connect(self.parentResized)
		# self.movementTimer = QTimer(interval=600, timeout=self.close)

		# self.gridItem.width = 10
		# self.gridItem.height = 1

		self._showGrid = False
		self.grid.autoPlace = True
		self.scrollRect.show()

		self.setAcceptedMouseButtons(Qt.AllButtons)
		self.resizeHandles.setEnabled(False)
		self.resizeHandles.setVisible(False)
		self.setFiltersChildEvents(True)
		self.setFlag(self.ItemClipsChildrenToShape, False)
		self.setAcceptHoverEvents(True)
		self.handle = DrawerHandle(self)
		self.handle.update()
		self.setAcceptDrops(False)

	def close(self):
		self.handle.close()

	def open(self):
		self.handle.open()

	@cached_property
	def scrollRect(self):
		return APIRect(self)

	@cached_property
	def parentGrid(self) -> Grid:
		return None

	@cached_property
	def grid(self) -> 'Grid':
		clearCacheAttr(self, 'allHandles')
		grid = Grid(self, static=False, overflow=[False, True])
		return grid

	def itemChange(self, change: int, value: Any) -> Any:
		if change == self.ItemPositionChange:
			value.setX(0)
			maxY = -self.height()
			if value.y() < maxY:
				value.setY(maxY)
			if value.y() > 0:
				value.setY(0)
			return super(Panel, self).itemChange(change, value)
		if change == self.ItemPositionHasChanged:
			panelPos = QPointF(value)
			panelPos.setY(value.y() + self.height())
			self.centralPanel.setPos(panelPos)
			return super(Panel, self).itemChange(change, value)

		return super(PanelDrawer, self).itemChange(change, value)

	@property
	def state(self):
		return None

	# def paint(self, painter, option, widget):
	# 	painter.setPen(QPen(self.scene().palette().background(), 1))
	# 	painter.drawRect(self.rect())
	# 	super(PanelDrawer, self).paint(painter, option, widget)

	def sceneEventFilter(self, watched: QGraphicsItem, event: QGraphicsSceneMouseEvent):
		# 	self.hoverTimer.stop()
		# if isinstance(watched, Handle):
		# 	if event.type() == QtCore.QEvent.GraphicsSceneHoverEnter:
		# 		self.scrollRect.setMovable(False)
		# 	elif event.type() == QtCore.QEvent.GraphicsSceneHoverLeave:
		# 		self.scrollRect.setMovable(True)

		# if any([x.mapToParent(x.shape()).contains(event.pos()) for x in self.resizeHandles.childItems()]):
		# 	if isinstance(watched, ScrollRect):
		# 		event.ignore()
		# 	else:
		# 		event.accept()
		# return super().sceneEventFilter(self, event)

		return super().sceneEventFilter(watched, event)

	def width(self):
		return self.rect().width()

	def height(self):
		return self.rect().height()

	def setRect(self, rect):
		rect.setHeight(max(rect.height(), 100))
		super(PanelDrawer, self).setRect(rect)

	def parentResized(self, arg):
		super(PanelDrawer, self).parentResized(arg)

	def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
		event.ignore()

	def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
		event.ignore()

	def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
		event.ignore()

	def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent):
		self.handle.hideTimer.stop()

	def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent):
		self.handle.hideTimer.start()

	def wheelEvent(self, event: QGraphicsSceneWheelEvent) -> None:
		self.handle.hideTimer.stop()
		self.scroll(event.delta(), 0, self.scrollRect.grid.gridRect())
		if self.scrollRect.grid.columns > self.scrollRect.grid.rows:
			self.scrollRect.moveBy(event.delta()*0.5, 0)
		else:
			self.scrollRect.moveBy(0, event.delta()*0.5)
