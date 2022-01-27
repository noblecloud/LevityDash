import logging
from functools import cached_property
from typing import Callable, Optional, Type
from sys import gettrace

from PySide2.QtCore import QPointF, QRectF, QSize, Qt
from PySide2.QtGui import QPainterPath, QPen
from PySide2.QtWidgets import QGraphicsItem, QGraphicsItemGroup, QGraphicsPathItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView

from src.utils import LocationFlag
from src import colorPalette

log = logging.getLogger(__name__)
log.setLevel('DEBUG' if gettrace() else 'INFO')

debug = log.level <= 10


class Handle(QGraphicsPathItem):
	location: LocationFlag
	cursor: Qt.CursorShape
	surface: QGraphicsItem

	def __init__(self, parent: 'HandleGroup', location: LocationFlag):
		super(Handle, self).__init__()
		self._boundingRect = None
		self.setParentItem(parent)
		self.location = location
		pen = QPen(colorPalette.windowText().color(), self.width)
		pen.setCapStyle(Qt.RoundCap)
		pen.setJoinStyle(Qt.RoundJoin)
		self.setPen(pen)
		self.setAcceptHoverEvents(True)
		self.setFlag(QGraphicsItem.ItemIsMovable, True)
		self.setFlag(QGraphicsItem.ItemIsFocusable, False)
		# self.setFlag(QGraphicsItem.ItemStopsClickFocusPropagation, True)
		self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
		# self.setAcceptedMouseButtons(Qt.NoButton)
		self.setPath(self._path)

	def hoverEnterEvent(self, event):
		self.setCursor(self.cursor)
		self.setScale(1.5)
		self.setZValue(self.zValue() + 100)
		# self.updatePosition()
		# effect = QGraphicsDropShadowEffect(None)
		# effect.setOffset(0, 0)
		# effect.setBlurRadius(5)
		# effect.setColor(Qt.black)
		# self.setGraphicsEffect(effect)
		super(Handle, self).hoverEnterEvent(event)

	def hoverLeaveEvent(self, event):
		self.setCursor(Qt.ArrowCursor)
		self.setScale(1.0)
		self.setZValue(self.zValue() - 100)
		super(Handle, self).hoverLeaveEvent(event)

	def mousePressEvent(self, event):
		self.parentItem().parentItem().mousePressEvent(event)

	@property
	def surfaceRect(self):
		return self.parentItem().surface.rect()

	@property
	def position(self) -> QPointF:
		offset = self.parentItem().offset
		rect = self.surfaceRect
		xS, yS, oX, oY = self.positionScalars
		w = rect.width()
		h = rect.height()
		x = w * xS + (offset * oX)
		y = h * yS + (offset * oY)
		return QPointF(x, y) + rect.topLeft()

	def resetAttribute(self, *attr):
		if not attr:
			attr = ('cursor', 'length', 'width', '_path', '_shape', 'positionFunction', 'location')
		attr = [atr for atr in attr if hasattr(self, atr)]
		list(map(lambda x: self.__resetAttribute(x), attr))

	def __resetAttribute(self, attr: str):
		if hasattr(self, attr) and not isinstance(getattr(self, attr), Callable):
			delattr(self, attr)

	@cached_property
	def positionScalars(self):

		loc = self.location
		xScalar = 0
		yScalar = 0
		xOffset = 1
		yOffset = 1

		if loc.isTop:
			yOffset *= -1
		else:
			yScalar = 1

		if loc.isLeft:
			xOffset = -1
		else:
			xScalar = 1

		if loc.isCentered and not loc.isCorner:
			if loc.isHorizontal:
				xScalar = 0.5
				xOffset = 0
			else:
				yScalar = 0.5
				yOffset = 0

		return xScalar, yScalar, xOffset, yOffset

	@cached_property
	def cursor(self):
		loc = self.location
		if loc.isEdge:
			if loc.isHorizontal:
				return Qt.SizeVerCursor
			else:
				return Qt.SizeHorCursor
		else:
			left, right = Qt.SizeFDiagCursor, Qt.SizeBDiagCursor
			if loc.isBottom:
				left, right = right, left
			if loc.isLeft:
				return left
			else:
				return right

	@cached_property
	def length(self):
		return self.parentItem().length

	@cached_property
	def width(self):
		return self.parentItem().width

	def shape(self):
		return self._shape

	@property
	def surface(self):
		return self.parentItem().parentItem()

	def updatePosition(self):
		if not self.isUnderMouse():
			self.setPos(self.position)

	def paint(self, painter, option, widget):
		super(Handle, self).paint(painter, option, widget)
		if debug and False:
			pen = self.pen()
			pen.setCosmetic(True)
			painter.setPen(pen)
			painter.setBrush(Qt.NoBrush)
			painter.drawRect(self.boundingRect())

	@cached_property
	def _shape(self) -> QPainterPath:
		path = QPainterPath()
		x = 0
		y = 0
		l = self.length
		w = self.width
		if self.location.isEdge:
			l *= 3
			w *= 2
			x = -w / 2
			y = -l / 2
			if self.location.isHorizontal:
				x, y = y, x
				l, w = w, l
		else:
			x = -w
			y = -w
			w = l * 2
			l = l * 2
		if self.location.isBottom:
			l = -l
			y = -y
		if self.location.isRight:
			w = -w
			x = -x
		rect = QRectF(x, y, w, l)
		self._boudingRect = rect
		path.addRect(rect)
		return path

	@cached_property
	def _path(self) -> QPainterPath:
		path = QPainterPath()
		l = self.length
		z = 0
		if self.location.isEdge:
			if self.location.isHorizontal:
				path.moveTo(-l, z)
				path.lineTo(l, z)
			else:
				path.moveTo(z, l)
				path.lineTo(z, -l)
		else:
			hor = l
			ver = l
			if self.location & LocationFlag.Bottom:
				hor = -l
			if self.location & LocationFlag.Right:
				ver = -l
			path.moveTo(0, hor)
			path.lineTo(0, 0)
			path.lineTo(ver, 0)
		return path

	@property
	def parent(self) -> 'HandleGroup':
		return self.parentItem()


class HandleGroup(QGraphicsItemGroup):
	__length: float
	__offset: float
	__width: float
	currentHandle = None
	forceDisplay = False
	locations: LocationFlag = LocationFlag.all()
	handleClass: Type[Handle] = Handle

	def __init__(self, parent: 'Panel', length: float = 10.0, offset: float = -2.0, width: float = 5.0, locations: LocationFlag = None, *args, **kwargs):
		super(HandleGroup, self).__init__(*args, **kwargs)
		self.setParentItem(parent)
		if locations is not None:
			self.locations = locations
		# parent.signals.resized.connect(self.updatePosition)
		self.setHandlesChildEvents(False)
		self.setFiltersChildEvents(False)
		self.forceDisplay = False
		self.setAcceptHoverEvents(False)

		self.length = length
		self.offset = offset
		self.width = width

		self._genHandles()
		self.hide()

	def show(self) -> None:
		super(HandleGroup, self).show()

	def hide(self):
		if not self.forceDisplay:
			super(HandleGroup, self).hide()
		else:
			self.show()

	def _genHandles(self):
		if isinstance(self.locations, LocationFlag):
			locations = {loc & self.locations for loc in LocationFlag.all() if loc & self.locations}
		elif isinstance(self.locations, (list, tuple)):
			locations = self.locations
		else:
			raise TypeError('locations must be a LocationFlag or a list of LocationFlags')
		for value in locations:
			self.handleClass(self, value)

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemVisibleHasChanged:
			self.updatePosition()
		return super(HandleGroup, self).itemChange(change, value)

	@property
	def length(self):
		return self.__length

	@length.setter
	def length(self, value):
		self.__length = value
		self.__resetAttribute('length')

	@property
	def width(self):
		return self.__width

	@width.setter
	def width(self, value):
		self.__width = value
		self.__resetAttribute('width')

	@property
	def offset(self):
		return self.__offset

	@offset.setter
	def offset(self, value):
		self.__offset = value
		self.__resetAttribute('offset')

	def __resetAttribute(self, *attr):
		attr = (a for a in attr if a is not None)
		list(map(lambda item: item.resetAttribute(*attr), self.childItems()))

	def updatePosition(self, *args):
		for item in self.childItems():
			item.updatePosition()

	@cached_property
	def surface(self):
		return self.parentItem()

	def mousePressEvent(self, event) -> None:
		event.ignore()
		super(HandleGroup, self).mousePressEvent(event)


from . import Various
from . import Resize
from . import Incrementer
from . import Grid
from . import Timeframe
from . import Figure

__all__ = ['Handle', 'HandleGroup', 'Various', 'Resize', 'Incrementer', 'Grid', 'Timeframe', 'Figure']

if __name__ == '__main__':
	from PySide2.QtWidgets import QApplication
	import sys

	QApplication.setAttribute(Qt.AA_UseDesktopOpenGL)
	app = QApplication(sys.argv)

	window = QGraphicsView()
	window.setWindowTitle('TestHandles')
	window.setScene(QGraphicsScene())

	rect = QGraphicsRectItem(0, 0, 100, 100)
	rect.setFlag(QGraphicsItem.ItemIsMovable)
	rect.setHandlesChildEvents(False)
	x = IndoorIcon(rect)
	# window.scene().addItem(rect)
	# rect.setPos(100, 100)
	# handles = Handles(rect)
	# d = DrawerHandle(rect)
	window.scene().addItem(x)

	g = window.geometry()
	g.setSize(QSize(800, 600))
	g.moveCenter(app.screens()[1].geometry().center())
	window.setGeometry(g)
	window.show()
	# handles.update()
	sys.exit(app.exec_())
