from PySide2.QtCore import QObject, QPointF, QRectF, Signal, QTimer
from PySide2.QtWidgets import QGraphicsItem, QGraphicsSceneMouseEvent

from LevityDash.lib.ui.Geometry import Axis
from LevityDash.lib.ui.frontends.PySide.Modules.Handles import Handle, HandleGroup

__all__ = ['ResizeHandle', 'ResizeHandles']


class ResizeHandleSignals(QObject):
	action = Signal(QRectF, Axis)


class ResizeHandle(Handle):
	signals: ResizeHandleSignals
	_ratio = None
	parentWasMovable = True

	def mousePressEvent(self, event) -> None:
		self.parentItem().hideTimer.stop()
		if hasattr(self.surfaceProxy.parent, 'childIsMoving'):
			self.surfaceProxy.parent.childIsMoving = True
			self.parentWasMovable = self.surfaceProxy.parent.movable
			if self.parentWasMovable:
				self.surfaceProxy.parent.setMovable(False)
		event.accept()
		self.surfaceProxy.hold()
		self.surfaceProxy.setFocusProxy(self)
		self.setSelected(True)
		super(Handle, self).mousePressEvent(event)

	def mouseMoveEvent(self, event):
		event.accept()
		self.interactiveResize(event)
		self.parent.updatePosition(exclude=self)
		super(Handle, self).mouseMoveEvent(event)

	def hoverEnterEvent(self, event):
		self.parentItem().hideTimer.stop()
		super(ResizeHandle, self).hoverEnterEvent(event)

	def hoverMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		self.parentItem().hideTimer.stop()
		super(Handle, self).hoverMoveEvent(event)

	def hoverLeaveEvent(self, event):
		self.parentItem().hideTimer.start()
		super(ResizeHandle, self).hoverLeaveEvent(event)

	def mouseReleaseEvent(self, event):
		if hasattr(self.surfaceProxy.parent, 'childIsMoving'):
			self.surfaceProxy.parent.childIsMoving = False
			if self.parentWasMovable:
				self.surfaceProxy.parent.setMovable(True)
		self.setSelected(False)
		self.surfaceProxy.release()
		self.surfaceProxy.setFocusProxy(None)
		self.parentItem().hideTimer.start()
		super(Handle, self).mouseReleaseEvent(event)

	def interactiveResize(self, mouseEvent: QGraphicsSceneMouseEvent) -> tuple[QRectF, QPointF]:
		rect = self.surface.rect()
		original = self.surface.rect()
		# if self.parent.keepInFrame:
		# 	mousePos = self.mapToFromScene(mouseEvent.scenePos())
		# 	parentRect = self.parent.rect()
		# 	mousePos.setX(min(max(mousePos.x(), 0), parentRect.width()))
		# 	mousePos.setY(min(max(mousePos.y(), 0), parentRect.height()))
		# 	mouseEvent.setPos(self.mapFromParent(mousePos))

		loc = self.location
		mousePos = mouseEvent.scenePos()
		mousePos = self.surface.mapFromScene(mousePos)

		# if self.surface.parentGrid is not None:
		# 	colW = self.surface.parentGrid.columnWidth
		# 	rowH = self.surface.parentGrid.rowHeight
		# 	parentPosition = self.surface.mapToParent(mousePos)
		# 	x = parentPosition.x()
		# 	y = parentPosition.y()
		# 	v = round(x/colW)
		# 	V = round(v*colW)
		# 	if abs(V - x) < 10:
		# 		parentPosition.setX(round(v*colW, 4))
		# 	h = round(y/rowH)
		# 	H = round(h*rowH)
		# 	if abs(H - y) < 10:
		# 		parentPosition.setY(round(h*rowH, 4))
		# 	mousePos = self.surface.mapFromParent(parentPosition)

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
		original = self.surface.mapRectToParent(original)
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
			rect.setX(original.x())
			rect.setWidth(20)
		if rect.height() < 20:
			rect.setY(original.y())
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
		elif value and change == QGraphicsItem.ItemVisibleHasChanged and self.surface and self.surface.geometry:
			self.updatePosition(self.surface.geometry.absoluteRect())
		return super(ResizeHandle, self).itemChange(change, value)


class ResizeHandles(HandleGroup):
	handleClass = ResizeHandle
	signals: ResizeHandleSignals

	def __init__(self, *args, **kwargs):
		super(ResizeHandles, self).__init__(*args, **kwargs)
		self.hideTimer = getattr(self.surface, 'hideTimer', None) or QTimer(interval=5000, timeout=self.hide, singleShot=True)

	def disable(self):
		self.setEnabled(False)
