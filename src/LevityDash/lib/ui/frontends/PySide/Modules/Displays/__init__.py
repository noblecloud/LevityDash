from typing import TYPE_CHECKING

from PySide6.QtGui import QPainterPath, QPainter
from PySide6.QtWidgets import QGraphicsItemGroup, QGraphicsItem, QStyleOptionGraphicsItem, QWidget


class Surface(QGraphicsItemGroup):
	if TYPE_CHECKING:
		from ... import LevityScene
		from ..Panel import Panel
		def scene(self) -> LevityScene: ...

		def parentItem(self) -> Panel: ...

	def __init__(self, parent: 'Panel'):
		super().__init__()
		self.setParentItem(parent)

	def boundingRect(self):
		return self.parentItem().rect()

	def boundingRegion(self, itemToDeviceTransform):
		return self.parentItem().boundingRegion(itemToDeviceTransform)

	def shape(self) -> QPainterPath:
		return self.parentItem().shape()

	def _debug_paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget):
		self._normal_paint(painter, option, widget)
		addRect(painter, self.boundingRect(), color=self._debug_paint_color, offset=1)


class SurfaceCentered(Surface):

	def shape(self) -> QPainterPath:
		return self.parentItem().shape().translated(self.parentItem().rect().center())

	def boundingRect(self):
		return self.parentItem().rect().translated(-self.parentItem().rect().center())

	def boundingRegion(self, itemToDeviceTransform):
		return self.parentItem().boundingRegion(itemToDeviceTransform).translated(self.parentItem().rect().center())


from .Text import *
from .Label import *
from .DateTime import *
from .Gauge import *
from .Realtime import Realtime
from .Moon import Moon
from .Graph import *
from ... import LevityScene
from ...utils import addRect
