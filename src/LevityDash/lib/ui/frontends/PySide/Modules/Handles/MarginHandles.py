from PySide2.QtCore import QObject, QRectF, Signal
from PySide2.QtGui import QTransform
from PySide2.QtWidgets import QGraphicsItem

from LevityDash.lib.utils.shared import clamp, clearCacheAttr
from LevityDash.lib.utils.geometry import Axis, LocationFlag

from LevityDash.lib.ui.frontends.PySide.Modules.Handles.Resize import ResizeHandle, ResizeHandles

__all__ = ['MarginHandle', 'MarginHandles', 'FigureHandle', 'FigureHandles']


class MarginHandleSignals(QObject):
	action = Signal(Axis)


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
			margins.relativeTop = clamp(pos.y()/rect.height(), 0, 1)
			value = margins.relativeTop
			other = 1 - margins.relativeBottom
			if value > other:
				margins.relativeTop = float(other)
		elif loc.isBottom:
			margins.relativeBottom = clamp(1 - pos.y()/rect.height(), 0, 1)
			value = 1 - margins.relativeBottom
			other = margins.relativeTop
			if value < other:
				margins.relativeBottom = 1 - float(other)
		elif loc.isLeft:
			margins.relativeLeft = clamp(pos.x()/rect.width(), 0, 1)
			value = margins.relativeLeft
			other = 1 - margins.relativeRight
			if value > other:
				margins.relativeLeft = float(other)
		elif loc.isRight:
			margins.relativeRight = clamp(1 - pos.x()/rect.width(), 0, 1)
			value = 1 - margins.relativeRight
			other = margins.relativeLeft
			if value < other:
				margins.relativeRight = 1 - float(other)
		self.emitUpdate(loc.asAxis)

	def emitUpdate(self, axis):
		self.surface.t = None
		clearCacheAttr(self.surface, 'marginRect')
		self.signals.action.emit(axis)

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
				if boundingRect.width() < surfaceRect.width():
					proxy = self.surface.parentItem()
					center = proxy.visibleRect().center()
					value.setX(center.x())
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
	signals: MarginHandleSignals

	def __init__(self, parent: 'Panel', *args, offset: float = 0, **kwargs):
		super(MarginHandles, self).__init__(parent=parent, offset=offset, *args, **kwargs)

	def updatePosition(self, rect=None, *args, **kwargs):
		# t = QTransform()
		# wScale = self.surface.parentItem().parentItem().rect().width() / self.surface.parentItem().rect().width()
		# hScale = self.surface.parentItem().parentItem().rect().height() / self.surface.parentItem().rect().height()
		# t.scale(wScale, hScale)
		# self.setTransformOriginPoint(self.surface.geometry.absoluteRect().center())
		# # t.scale(1, -1)
		# for handle in self.handles:
		# 	handle.updatePosition(self.surface.marginRect)
		# self.setTransform(t)
		super(MarginHandles, self).updatePosition(self.surface.marginRect, *args, **kwargs)


# list(map(lambda item: item.updatePosition(self.surface.marginRect), self.handles))


class FigureHandle(MarginHandle):

	def surfaceBoundingRect(self) -> QRectF:
		return self.surface.mapRectFromParent(super(FigureHandle, self).surfaceBoundingRect())

	def emitUpdate(self, axis):
		# self.surface.onAxisResized(axis)
		# action = list(map(lambda plot: plot.onAxisTransform(axis), self.surface.plotData.values()))
		self.signals.action.emit(axis)


class FigureHandles(MarginHandles):
	handleClass = FigureHandle
	locations = [LocationFlag.Top, LocationFlag.Bottom]

	def __init__(self, parent: 'Panel', *args, offset: float = -5.0, **kwargs):
		super(FigureHandles, self).__init__(parent=parent, offset=offset, length=15, width=7, *args, **kwargs)
