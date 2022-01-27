from PySide2.QtCore import QPointF, QRectF
from PySide2.QtWidgets import QGraphicsItem, QGraphicsSceneMouseEvent

from utils import LocationFlag
from . import Handle, HandleGroup

__all__ = ['ResizeHandle', 'ResizeHandles', 'Splitter']


class ResizeHandle(Handle):

	def mousePressEvent(self, event) -> None:
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
		self.surface.geometry.updateSurface()
		super(Handle, self).mouseReleaseEvent(event)

	def interactiveResize(self, mouseEvent: QGraphicsSceneMouseEvent) -> tuple[QRectF, QPointF]:

		rect = self.surface.rect()
		startWidth = rect.width()
		startHeight = rect.height()
		pos = self.surface.pos()
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
		# self.surface.geometry.setAbsolutePosition(p)
		self.surface.geometry.updateSurface()

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemPositionChange:
			x = value
			value = self.position
		return super(ResizeHandle, self).itemChange(change, value)


class ResizeHandles(HandleGroup):
	handleClass = ResizeHandle


class Splitter(Handle):
	surfaceAPosition: LocationFlag
	surfaceBPosition: LocationFlag

	def __init__(self, surfaceA, surfaceB):
		assert surfaceA.parent == surfaceB.parent

		self.surfaceA = surfaceA
		self.surfaceB = surfaceB
		self.splitType = self.determineSplitType()
		self.surfaceA.parent.signals.resized.connect(self.updatePosition)
		# self.surfaceB.signals.resized.connect(self.updatePosition)
		self.determinePositions()

		self.width = 5
		self.length = 20

		super(Splitter, self).__init__(surfaceA.parent, location=self.splitType)

	def determineSplitType(self):
		centerA, centerB = self.centers()
		horizontal = abs(centerA.x() - centerB.x())
		vertical = abs(centerA.y() - centerB.y())
		if horizontal < vertical:
			return LocationFlag.TopCenter
		else:
			return LocationFlag.CenterLeft

	def determinePositions(self):
		centerA, centerB = self.centers()
		if self.splitType.isHorizontal:
			if centerA.x() < centerB.x():
				self.surfaceAPosition = LocationFlag.Left
				self.surfaceBPosition = LocationFlag.Right
			else:
				self.surfaceAPosition = LocationFlag.Right
				self.surfaceBPosition = LocationFlag.Left
		else:
			if centerA.y() < centerB.y():
				self.surfaceAPosition = LocationFlag.Top
				self.surfaceBPosition = LocationFlag.Bottom
			else:
				self.surfaceAPosition = LocationFlag.Bottom
				self.surfaceBPosition = LocationFlag.Top

	def rects(self) -> tuple[QRectF, QRectF]:
		a = self.surfaceA.mapRectFromParent(self.surfaceA.rect())
		b = self.surfaceB.mapRectFromParent(self.surfaceB.rect())
		return a, b

	def centers(self) -> tuple[QPointF, QPointF]:
		a, b = self.rects()
		return a.center(), b.center()

	@property
	def position(self) -> QPointF:
		a, _ = self.rects()
		aCenter = a.center()
		if self.splitType.isHorizontal:
			if self.surfaceAPosition.isLeft:
				aCenter.setX(a.right())
			else:
				aCenter.setX(a.left())
		else:
			if self.surfaceAPosition.isTop:
				aCenter.setY(a.bottom())
			else:
				aCenter.setY(a.top())
		return aCenter

	def mousePressEvent(self, event) -> None:
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
		# self.setFlag(QGraphicsItem.ItemIgnoresTransformations, False)
		self.surface.geometry.updateSurface()
		super(Handle, self).mouseReleaseEvent(event)

	def interactiveResize(self, mouseEvent):
		a, b = self.rects()
		aCenter, bCenter = self.centers()
		if self.splitType.isHorizontal:
			if self.surfaceAPosition.isLeft:
				a.setRight(mouseEvent.pos().x())
			else:
				a.setLeft(mouseEvent.pos().x())
		else:
			if self.surfaceAPosition.isTop:
				a.setBottom(mouseEvent.pos().y())
			else:
				a.setTop(mouseEvent.pos().y())
		if self.splitType.isHorizontal:
			if self.surfaceBPosition.isLeft:
				b.setLeft(mouseEvent.pos().x())
			else:
				b.setRight(mouseEvent.pos().x())
		else:
			if self.surfaceBPosition.isTop:
				b.setTop(mouseEvent.pos().y())
			else:
				b.setBottom(mouseEvent.pos().y())
		self.surfaceA.geometry.setGeometry(a)
		self.surfaceB.geometry.setGeometry(b)
		self.surfaceA.geometry.updateSurface()
