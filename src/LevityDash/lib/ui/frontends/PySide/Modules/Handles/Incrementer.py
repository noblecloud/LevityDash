from functools import cached_property

from PySide2.QtWidgets import QGraphicsSceneMouseEvent
from PySide2.QtCore import QObject, QPointF, Qt, Signal
from PySide2.QtGui import QPainterPath

from LevityDash.lib.utils.geometry import Axis, LocationFlag

from LevityDash.lib.ui.frontends.PySide.Modules.Handles import Handle, HandleGroup

__all__ = ["Incrementer", "IncrementerGroup"]


class IncrementerSignals(QObject):
	action = Signal(Axis)


class Incrementer(Handle):
	clickStart: QPointF
	signals: IncrementerSignals

	def __init__(self, parent, location, **kwargs):
		super().__init__(parent, location, **kwargs)
		self.setTransformOriginPoint(self.offset)
		self.setFlag(self.ItemIsMovable, False)

	@cached_property
	def cursor(self):
		return Qt.ArrowCursor

	@cached_property
	def _path(self):
		path = QPainterPath()
		l = self.length
		path.moveTo(l, 0)
		path.lineTo(-l, 0)
		if self.location & LocationFlag.TopRight:
			path.moveTo(0, l)
			path.lineTo(0, -l)
		path.translate(self.offset)
		return path

	@cached_property
	def _shape(self):
		path = QPainterPath()
		l = self.length
		path.addRect(-l, -l, l*2, l*2)
		path.translate(self.offset)
		return path

	def mousePressEvent(self, event):
		event.accept()
		loc = self.location
		if loc.isTop or loc.isRight:
			self.increase()
		else:
			self.decrease()
		self.signals.action.emit(self.location.asAxis)
		return super().mousePressEvent(event)

	def increase(self):
		self.surface.update()

	def decrease(self):
		self.surface.update()

	def itemChange(self, change, value):
		if change == self.ItemPositionChange:
			value = self.position
		return super().itemChange(change, value)


class IncrementerGroup(HandleGroup):
	signals: IncrementerSignals
	handleClass = Incrementer
	locations = LocationFlag.edges()

	@property
	def offset(self):
		return self.__offset - self.length

	@offset.setter
	def offset(self, value):
		self.__offset = value

	@property
	def incrementValue(self) -> int:
		return 1
