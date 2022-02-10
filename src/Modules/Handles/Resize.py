from PySide2.QtCore import QObject, QPointF, QRectF, Signal
from PySide2.QtWidgets import QGraphicsItem, QGraphicsSceneMouseEvent

from src.utils import _Panel, Axis, clearCacheAttr, disconnectSignal, HandleItemSignals, LocationFlag
from src.Modules.Handles import Handle, HandleGroup

__all__ = ['ResizeHandle', 'ResizeHandles', 'Splitter']


class ResizeHandleSignals(QObject):
	action = Signal(QRectF, Axis)


class ResizeHandle(Handle):
	signals: ResizeHandleSignals
	_ratio = None
	parentWasMovable = True

	def mousePressEvent(self, event) -> None:
		if hasattr(self.surface.parent, 'childIsMoving'):
			self.surface.parent.childIsMoving = True
			self.parentWasMovable = self.surface.parent.movable
			if self.parentWasMovable:
				self.surface.parent.setMovable(False)
		self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
		event.accept()
		self.setSelected(True)
		self.surface.setSelected(False)
		super(Handle, self).mousePressEvent(event)

	def mouseMoveEvent(self, event):
		event.accept()
		self.interactiveResize(event)
		super(Handle, self).mouseMoveEvent(event)

	def mouseReleaseEvent(self, event):
		if hasattr(self.surface.parent, 'childIsMoving'):
			self.surface.parent.childIsMoving = False
			if self.parentWasMovable:
				self.surface.parent.setMovable(True)
		self.surface.setFocus()
		super(Handle, self).mouseReleaseEvent(event)

	def interactiveResize(self, mouseEvent: QGraphicsSceneMouseEvent) -> tuple[QRectF, QPointF]:

		rect = self.surface.rect()
		# if self.parent.keepInFrame:
		# 	mousePos = self.mapToFromScene(mouseEvent.scenePos())
		# 	parentRect = self.parent.rect()
		# 	mousePos.setX(min(max(mousePos.x(), 0), parentRect.width()))
		# 	mousePos.setY(min(max(mousePos.y(), 0), parentRect.height()))
		# 	mouseEvent.setPos(self.mapFromParent(mousePos))

		loc = self.location
		mousePos = mouseEvent.scenePos()
		mousePos = self.surface.mapFromScene(mousePos)

		if self.surface.parentGrid is not None:
			colW = self.surface.parentGrid.columnWidth
			rowH = self.surface.parentGrid.rowHeight
			parentPosition = self.surface.mapToParent(mousePos)
			x = parentPosition.x()
			y = parentPosition.y()
			v = round(x / colW)
			V = round(v * colW)
			if abs(V - x) < 10:
				parentPosition.setX(round(v * colW, 4))
			h = round(y / rowH)
			H = round(h * rowH)
			if abs(H - y) < 10:
				parentPosition.setY(round(h * rowH, 4))
			mousePos = self.surface.mapFromParent(parentPosition)

		# if abs((mousePos.x() % self.surface.parentGrid.columnWidth) - self.surface.parentGrid.columnWidth) < 20:
		# 	x = ((mousePos.x() // self.surface.parentGrid.columnWidth) + 1) * self.surface.parentGrid.columnWidth
		# 	mousePos.setX(x)
		# mousePos = self.mapToItem(self.surface, mouseEvent.pos())
		# mousePos = self.mapToParent(mousePos)
		if loc.isRight:
			rect.setRight(mousePos.x())
		elif loc.isLeft:
			rect.setLeft(mousePos.x())
		if loc.isBottom:
			rect.setBottom(mousePos.y())
		elif loc.isTop:
			rect.setTop(mousePos.y())

		rect = self.surface.mapRectToParent(rect)
		# flatten array
		similarEdges = [item for sublist in [self.surface.similarEdges(n, rect=rect, singleEdge=loc) for n in self.surface.neighbors] for item in sublist]

		if similarEdges:
			s = similarEdges[0]
			snapValue = s.otherValue.pix
			if loc.isRight:
				rect.setRight(snapValue)
			elif loc.isLeft:
				rect.setLeft(snapValue)
			elif loc.isTop:
				rect.setTop(snapValue)
			elif loc.isBottom:
				rect.setBottom(snapValue)

		# snap handle to surface parent grid

		# rect = self.surface.mapRectFromParent(rect)

		# if any(rect.topLeft().toTuple()):
		# 	p = self.mapToParent(rect.topLeft())
		# 	rect.moveTo(QPointF(0, 0))
		# else:
		# 	p = self.pos()

		# rect = self.surface.mapRectToParent(rect)

		if rect.width() < 20:
			rect.setWidth(20)
		if rect.height() < 20:
			rect.setHeight(20)

		# if rect.width() == startWidth:
		# 	p.setX(pos.x())
		# if rect.height() == startHeight:
		# 	p.setY(pos.y())
		# self.setPos(self.position)
		# self.surface.setPos(QPointF(0, 0))
		# self.surface.setRect(rect)
		self.surface.geometry.setGeometry(rect)
		self.signals.action.emit(rect, self.location.asAxis)

	# self.mapValues(rect)

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemPositionChange:
			value = self.position
		elif value and change == QGraphicsItem.ItemVisibleHasChanged and self.surface:
			self.updatePosition(self.surface.geometry.absoluteRect())
		return super(ResizeHandle, self).itemChange(change, value)


class ResizeHandles(HandleGroup):
	handleClass = ResizeHandle
	signals: ResizeHandleSignals

	def __init__(self, *args, **kwargs):
		super(ResizeHandles, self).__init__(*args, **kwargs)


class Splitter(Handle):
	_ratio: float = None

	def __init__(self, surface, ratio=0.5, splitType: LocationFlag = LocationFlag.Horizontal, *args, **kwargs):
		assert isinstance(ratio, float)

		if isinstance(splitType, str):
			splitType = LocationFlag[splitType.title()]
		assert isinstance(splitType, LocationFlag)

		self.width = 2.5
		self.length = 10
		self.location = splitType

		primary = kwargs.pop('primary', None)
		if primary is not None and primary.parent is not surface:
			primary.setParentItem(surface)
		secondary = kwargs.pop('secondary', None)
		if secondary is not None and secondary.parent is not surface:
			secondary.setParentItem(surface)

		super(Splitter, self).__init__(surface, location=splitType, *args, **kwargs)

		self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

		surfaceChildren = [child for child in self.surface.childPanels if child is not primary or child is not secondary]
		if len(surfaceChildren) > 2:
			raise Exception("Splitter can only be used with 2 child panels")
		elif len(surfaceChildren) == 2:
			self.primary = surfaceChildren[0]
			self.secondary = surfaceChildren[1]
		elif len(surfaceChildren) == 1:
			self.primary = surfaceChildren[0]
			self.secondary = None
		else:
			self.primary = None
			self.secondary = None

		self.ratio = ratio
		self.setPos(self.position)

	@property
	def position(self) -> QPointF:
		center = self.surface.rect().center()
		if self.location.isVertical:
			center.setX(self.ratio * float(self.surface.geometry.absoluteWidth))
		else:
			center.setY(self.ratio * float(self.surface.geometry.absoluteHeight))
		return center

	def mousePressEvent(self, event) -> None:
		event.accept()
		self.setSelected(True)
		super(Handle, self).mousePressEvent(event)

	def mouseMoveEvent(self, event):
		event.accept()
		self.interactiveResize(event)

	def mouseDoubleClickEvent(self, event):
		event.accept()
		self.swapSurfaces()

	def mouseReleaseEvent(self, event) -> None:
		self.update()
		super(Handle, self).mouseReleaseEvent(event)

	def interactiveResize(self, mouseEvent):
		eventPosition = self.parent.mapFromScene(mouseEvent.scenePos())
		value = eventPosition.x() if self.location.isVertical else eventPosition.y()
		surfaceSize = float(self.surface.geometry.absoluteWidth if self.location.isVertical else self.surface.geometry.absoluteHeight)
		value /= surfaceSize
		# Snap value to 0.1 increments if within 0.03
		valueRounded = round(value, 1)
		if abs(valueRounded - value) < surfaceSize * 0.0003:
			value = valueRounded
		self.ratio = value

	def swapSurfaces(self):
		self.primary, self.secondary = self.secondary, self.primary
		if hasattr(self.surface, 'primary'):
			self.surface.primary, self.surface.secondary = self.surface.secondary, self.surface.primary
		self.setGeometries()

	def updatePosition(self, rect: QRectF):
		center = rect.center()
		if self.location.isVertical:
			center.setX(self.ratio * float(self.surface.geometry.absoluteWidth))
		else:
			center.setY(self.ratio * float(self.surface.geometry.absoluteHeight))
		self.setPos(center)

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemPositionChange:
			value = self.position
			if self.location.isVertical:
				value.setY(self.position.y())
			else:
				value.setX(self.position.x())
		elif change == QGraphicsItem.ItemVisibleChange:
			if value and not self._resizeSignalConnected:
				self.surface.signals.resized.connect(self.updatePosition)
				self._resizeSignalConnected = True
			elif not value and self._resizeSignalConnected:
				disconnectSignal(self.surface.signals.resized, self.updatePosition)
				self._resizeSignalConnected = False
		return super(Handle, self).itemChange(change, value)

	@property
	def ratio(self):
		if self.primary is not None and self.secondary is not None and self.primary.isVisible() != self.secondary.isVisible():
			self._ratio = 0
		if self._ratio is None:
			if self.location.isVertical:
				self._ratio = self.pos().x() / float(self.surface.rect().width())
			else:
				self._ratio = self.pos().y() / float(self.surface.rect().height())
		return self._ratio

	@ratio.setter
	def ratio(self, value):
		if self._ratio != value:
			self._ratio = value
			self.updatePosition(self.surface.rect())
			self.setGeometries()

	def setGeometries(self):
		value = self._ratio

		if value == 0:
			selected = self.primary if self.primary.isVisible() else self.secondary
			selected.geometry.setRelativeGeometry(QRectF(0, 0, 1, 1))
			selected.updateFromGeometry()
			self.surface.update()
			return

		primary, secondary = self.primary, self.secondary

		if self.location.isVertical:
			if primary is not None:
				primary.geometry.relativeWidth = value
				primary.geometry.relativeHeight = 1
				primary.geometry.relativeX = 0
				primary.geometry.relativeY = 0
			if secondary is not None:
				secondary.geometry.relativeWidth = 1 - value
				secondary.geometry.relativeHeight = 1
				secondary.geometry.relativeX = value
				secondary.geometry.relativeY = 0
		else:
			if primary is not None:
				primary.geometry.relativeWidth = 1
				primary.geometry.relativeHeight = value
				primary.geometry.relativeY = 0
				primary.geometry.relativeX = 0
			if secondary is not None:
				secondary.geometry.relativeWidth = 1
				secondary.geometry.relativeHeight = 1 - value
				secondary.geometry.relativeY = value
				secondary.geometry.relativeX = 0
		for child in [primary, secondary]:
			if child is not None:
				child.updateFromGeometry()
		self.surface.update()

	@property
	def state(self):
		return {
			'ratio:':    self.ratio,
			'primary':   self.primary,
			'secondary': self.secondary,
			'splitType': self.location.name
		}
