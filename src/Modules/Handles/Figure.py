from PySide2.QtWidgets import QGraphicsItem

from src.utils import LocationFlag

from .Resize import ResizeHandle, ResizeHandles

__all__ = ['FigureHandle', 'FigureHandles']


class FigureHandle(ResizeHandle):

	@property
	def figureRect(self):
		rect = self.parentItem().surface.rect()
		parentRect = self.parentItem().surface.parentItem().rect()
		rect.setWidth(parentRect.width())
		return rect

	@property
	def position(self):
		loc = self.location
		rect = self.surfaceRect
		pos = rect.center()
		if loc.isTop:
			y = rect.top()
		elif loc.isBottom:
			y = rect.bottom()
		else:
			y = rect.center().y()
		pos.setY(y)
		return pos

	@property
	def surfaceRect(self):
		return self.surface.mapRectFromParent(self.surface.marginRect)

	def interactiveResize(self, event):
		loc = self.location
		rect = self.figureRect
		margins = self.surface.margins
		if loc.isBottom:
			value = 1 - self.mapToParent(event.pos()).y() / rect.height()
			margins.bottom = value
		elif loc.isTop:
			value = self.mapToParent(event.pos()).y() / rect.height()
			margins.top = value
		elif loc.isLeft:
			value = self.mapToParent(event.pos()).x() / rect.width()
			margins.left = value
		elif loc.isRight:
			value = 1 - self.mapToParent(event.pos()).x() / rect.width()
			margins.right = value
		self.surface.signals.resized.emit(rect.size())

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemPositionChange:
			center = self.surface.mapFromParent(self.surface.parent.rect().center())
			x = center.x()
			value.setX(x)
			y = value.y()
			yMax = self.figureRect.top() - self.parentItem().offset
			yMin = self.surfaceRect.bottom() + self.parentItem().offset
			if y < yMax:
				y = yMax
			elif y > yMin:
				y = yMin
			value.setY(y)
		return super(FigureHandle, self).itemChange(change, value)


class FigureHandles(ResizeHandles):
	locations = LocationFlag.Top | LocationFlag.Bottom
	handleClass = FigureHandle

	def __init__(self, parent: 'Figure', *args, offset: float = -5.0, **kwargs):
		super(FigureHandles, self).__init__(parent=parent, offset=offset, *args, **kwargs)

	def _genHandles(self):
		return super()._genHandles()

# def addLocation(self, location: LocationFlag):
# 	if location not in self.handleLocations:
# 		self.handleLocations.append(location)
# 		self.addToGroup(Handle(self, location))
#
# def removeLocation(self, location: LocationFlag):
# 	if location in self.handleLocations:
# 		i = self.handleLocations.index(location)
# 		self.handleLocations.pop(i)
# 		self.removeFromGroup(self.childItems()[i])
