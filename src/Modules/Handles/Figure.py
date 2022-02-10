from PySide2.QtCore import QRectF
from PySide2.QtWidgets import QGraphicsItem

from src.utils import capValue, clearCacheAttr, LocationFlag

from src.Modules.Handles.Resize import ResizeHandle, ResizeHandles

__all__ = ['MarginHandle', 'MarginHandles', 'FigureHandle', 'FigureHandles']


class MarginHandle(ResizeHandle):

	@property
	def position(self):
		loc = self.location
		marginRect = self.marginRect()
		if loc.isHorizontal:
			boundingRect = self.surfaceBoundingRect()
			pos = boundingRect.center() if marginRect.width() > boundingRect.width() else marginRect.center()
			if loc.isTop:
				pos.setY(marginRect.top())
			else:
				pos.setY(marginRect.bottom())
		else:
			pos = marginRect.center()
			if loc.isLeft:
				pos.setX(marginRect.left())
			else:
				pos.setX(marginRect.right())
		return pos

	def marginRect(self) -> QRectF:
		return self.surface.marginRect

	@property
	def surfaceRect(self) -> QRectF:
		return self.surface.contentsRect()

	def surfaceBoundingRect(self) -> QRectF:
		return self.surface.geometry.absoluteRect()

	@property
	def margins(self):
		return self.surface.margins

	def interactiveResize(self, event):
		loc = self.location
		rect = self.surfaceRect
		margins = self.margins
		pos = self.mapToParent(event.pos())

		if loc.isTop:
			margins.relativeTop = capValue(pos.y() / rect.height(), 0, 1)
			value = margins.relativeTop
			other = 1 - margins.relativeBottom
			if value > other:
				margins.relativeTop = float(other)
		elif loc.isBottom:
			margins.relativeBottom = capValue(1 - pos.y() / rect.height(), 0, 1)
			value = 1 - margins.relativeBottom
			other = margins.relativeTop
			if value < other:
				margins.relativeBottom = 1 - float(other)
		elif loc.isLeft:
			margins.relativeLeft = capValue(pos.x() / rect.width(), 0, 1)
			value = margins.relativeLeft
			other = 1 - margins.relativeRight
			if value > other:
				margins.relativeLeft = float(other)
		elif loc.isRight:
			margins.relativeRight = capValue(1 - pos.x() / rect.width(), 0, 1)
			value = 1 - margins.relativeRight
			other = margins.relativeLeft
			if value < other:
				margins.relativeRight = 1 - float(other)
		clearCacheAttr(self.surface, 'marginRect')
		self.signals.action.emit(rect, loc.asAxis)

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemPositionChange:

			marginRect = self.marginRect()
			surfaceRect = self.surface.contentsRect()
			y = value.y()
			offset = self.parentItem().offset
			if self.location.isHorizontal:
				boundingRect = self.surfaceBoundingRect()
				center = marginRect.center()
				value.setX(center.x() + boundingRect.x())
				surfaceRect = self.surfaceRect
				offset = -offset
				if self.location.isTop:
					yMax = surfaceRect.top() - offset
					yMin = marginRect.bottom() + offset
				else:
					yMax = marginRect.top() - offset
					yMin = surfaceRect.bottom() + offset
				if y < yMax:
					value.setY(yMax)
				elif y > yMin:
					value.setY(yMin)
			else:

				center = marginRect.center()
				value.setY(center.y())
				offset = -offset
				if self.location.isLeft:
					xMax = surfaceRect.left() - offset
					xMin = marginRect.right() + offset
				else:
					xMax = marginRect.left() - offset
					xMin = surfaceRect.right() + offset
				if value.x() < xMax:
					value.setX(xMax)
				elif value.x() > xMin:
					value.setX(xMin)

		return super(ResizeHandle, self).itemChange(change, value)

# def updatePosition(self, rect: QRectF = None):
# 	if rect is None:
# 		rect = self.surfaceRect
# 	marginRect = self.marginRect()
# 	super(MarginHandle, self).updatePosition(marginRect)


class MarginHandles(ResizeHandles):
	locations = LocationFlag.edges()
	handleClass = MarginHandle

	def __init__(self, parent: 'Panel', *args, offset: float = -5.0, **kwargs):
		super(MarginHandles, self).__init__(parent=parent, offset=offset, *args, **kwargs)

	def updatePosition(self, rect=None):
		for handle in self.handles:
			handle.updatePosition(self.surface.marginRect)
	# list(map(lambda item: item.updatePosition(self.surface.marginRect), self.handles))


class FigureHandle(MarginHandle):

	def surfaceBoundingRect(self) -> QRectF:
		return self.surface.mapRectFromParent(super(FigureHandle, self).surfaceBoundingRect())


class FigureHandles(MarginHandles):
	handleClass = FigureHandle
	locations = [LocationFlag.Top, LocationFlag.Bottom]

	def __init__(self, parent: 'Panel', *args, offset: float = -5.0, **kwargs):
		super(FigureHandles, self).__init__(parent=parent, offset=offset, length=15, width=7, *args, **kwargs)
