from functools import cached_property
from typing import Callable, List, Optional, Type, Union

from PySide2.QtCore import QObject, QPointF, QRectF, QSize, Qt, Signal
from PySide2.QtGui import QPainterPath, QPen
from PySide2.QtWidgets import QGraphicsItem, QGraphicsItemGroup, QGraphicsPathItem, QGraphicsRectItem, QGraphicsScene, QGraphicsSceneMouseEvent, QGraphicsView

from LevityDash.lib.utils.shared import _Panel
from LevityDash.lib.utils.geometry import LocationFlag, Position, Axis
from LevityDash.lib.ui.frontends.PySide.utils import colorPalette
from ... import qtLogger

log = qtLogger.getChild('Handles')

debug = log.level <= 10


class HandleItemSignals(QObject):
	action = Signal(LocationFlag, Axis)
	resized = Signal(Axis, QRectF, QRectF)


class Handle(QGraphicsPathItem):
	location: Union[LocationFlag, Position]
	cursor: Qt.CursorShape
	surface: _Panel
	signals: HandleItemSignals
	_resizeSignalConnected: bool

	def __init__(self, parent: 'HandleGroup', location: Union[LocationFlag, Position], alignment: LocationFlag = LocationFlag.Center):
		super(Handle, self).__init__(parent=parent)
		self.location = location
		self.alignment = alignment
		self.__init_defaults__()
		self.setFlag(QGraphicsItem.ItemIgnoresTransformations)

	def __repr__(self):
		return f'{self.__class__.__name__}({self.location.name})'

	def __init_defaults__(self):
		self.__surface = None
		self.__surfaceProxy = None
		pen = QPen(colorPalette.windowText().color(), self.width)
		pen.setCapStyle(Qt.RoundCap)
		pen.setJoinStyle(Qt.RoundJoin)

		if isinstance(self.parentItem(), _Panel):
			self._resizeSignalConnected = False
		self._init_signals_()
		self.setPen(pen)
		self.setAcceptHoverEvents(True)
		self.setFlag(QGraphicsItem.ItemIsMovable)
		self.setFlag(QGraphicsItem.ItemIsFocusable, False)
		self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
		self.setPath(self._path)

	def _init_signals_(self):
		if hasattr(self.parentItem(), 'signals') and isinstance(self.parentItem(), HandleGroup):
			self.signals = self.parentItem().signals
		else:
			cls = type(self)
			annotations = cls.__annotations__
			while 'signals' not in annotations:
				cls = cls.mro()[1]
				annotations = cls.__annotations__
			self.signals = annotations['signals']()

	def __hash__(self):
		return hash((self.surface, self.location, type(self)))

	def hoverEnterEvent(self, event):
		self.setCursor(self.cursor)
		self.setScale(1.5)
		self.update()
		self.surface.update()
		self.setZValue(self.zValue() + 100)
		super(Handle, self).hoverEnterEvent(event)

	def hoverLeaveEvent(self, event):
		self.setCursor(Qt.ArrowCursor)
		self.setScale(1.0)
		self.update()
		self.surface.update()
		self.setZValue(self.zValue() - 100)
		super(Handle, self).hoverLeaveEvent(event)

	def mousePressEvent(self, event):
		event.accept()
		super(Handle, self).mousePressEvent(event)

	def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		event.accept()
		super(Handle, self).mouseReleaseEvent(event)

	@property
	def surfaceRect(self):
		return self.surface.boundingRect()

	@property
	def position(self) -> QPointF:
		if isinstance(self.location, Position):
			pos = self.location.toAbsolute(*self.surfaceRect.size().toTuple()).asQPointF()
		else:
			pos = self.location.action(self.surface.geometry.absoluteRect())
		return pos

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
		if self.__surface is None:
			parent = self.parentItem()
			if isinstance(parent, HandleGroup):
				return parent.surface
			while parent is not None and not isinstance(parent, _Panel):
				parent = parent.parentItem()
			self.__surface = parent
		return self.__surface

	@property
	def surfaceProxy(self):
		if self.__surfaceProxy is None:
			return self.surface
		return self.__surfaceProxy

	@surfaceProxy.setter
	def surfaceProxy(self, value):
		self.__surfaceProxy = value

	def updatePosition(self, rect: QRectF = None):
		if rect is None:
			rect = self.surfaceRect
		if not self.isUnderMouse() and self.isVisible():
			self.setPos(self.location.action(rect))

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
			x = -w/2
			y = -l/2
			if self.location.isHorizontal:
				x, y = y, x
				l, w = w, l
		else:
			x = -w
			y = -w
			w = l*2
			l = l*2
		if self.location.isBottom:
			l = -l
			y = -y
		if self.location.isRight:
			w = -w
			x = -x
		rect = QRectF(x*1.2, y*1.2, w*1.2, l*1.2)
		path.addRect(rect)
		path.translate(self.offset)
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
		path.translate(self.offset)
		return path

	@property
	def offset(self):
		_, _, oX, oY = self.positionScalars
		offset = getattr(self.parentItem(), 'offset', 0)
		return QPointF(oX*offset, oY*offset)

	@property
	def parent(self) -> 'HandleGroup':
		return self.parentItem()


class HandleGroup(QGraphicsItemGroup):
	__length: float
	__offset: float
	__width: float
	currentHandle = None
	forceDisplay = False
	locations: Union[LocationFlag, List[Union[LocationFlag, Position]]] = [*LocationFlag.edges(), *LocationFlag.corners()]
	handleClass: Type[Handle] = Handle
	_resizeSignalConnected: bool = True
	signals: HandleItemSignals

	def __init__(self, parent: 'Panel',
		length: float = 10.0,
		offset: float = 0.0,
		width: float = 5.0,
		locations: Optional[LocationFlag] = None,
		*args, **kwargs):
		super(HandleGroup, self).__init__(*args, **kwargs)
		self.__surfaceProxy = None
		self._init_signals_()
		self.setParentItem(parent)
		if locations is not None:
			self.locations = locations
		self.setHandlesChildEvents(False)
		self.setFiltersChildEvents(False)
		self.forceDisplay = False
		self.setAcceptHoverEvents(False)

		self.length = length
		self.offset = offset
		self.width = width

		self._genHandles()
		self.hide()

	def _init_signals_(self):
		cls = type(self)
		annotations = cls.__annotations__
		while 'signals' not in annotations:
			cls = cls.__mro__[1]
			annotations = cls.__annotations__
		self.signals = annotations['signals']()

	def hide(self):
		if not self.forceDisplay:
			super(HandleGroup, self).hide()
		else:
			self.show()

	def _genHandles(self):
		self.handles = []
		if isinstance(self.locations, LocationFlag):
			locations = {loc & self.locations for loc in LocationFlag.all() if loc & self.locations}
		elif isinstance(self.locations, (list, tuple)):
			locations = self.locations
		else:
			raise TypeError('locations must be a LocationFlag or a list of LocationFlags')
		for value in locations:
			h = self.handleClass(self, value)
			self.handles.append(h)
			setattr(self, f'{h.location.name[0].lower()}{h.location.name[1:]}Handle', h)

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

	def updatePosition(self, rect=None, exclude=None):
		list(map(lambda item: item.updatePosition(rect), (h for h in self.childItems() if h is not exclude)))

	@property
	def surface(self):
		return self.parentItem()

	@property
	def surfaceProxy(self):
		if self.__surfaceProxy is None:
			return self.surface
		return self.__surfaceProxy

	@surfaceProxy.setter
	def surfaceProxy(self, value):
		self.__surfaceProxy = value
		for handle in self.handles:
			handle.surfaceProxy = value


from . import Various
from . import Resize
from . import Incrementer
from . import Timeframe
from . import MarginHandles

__all__ = ['Handle', 'HandleGroup', 'Various', 'Resize', 'Incrementer', 'Grid', 'Timeframe', 'MarginHandles', 'debug']

if __name__ == '__main__':
	from PySide2.QtWidgets import QApplication
	import sys

	app = QApplication(sys.argv)

	window = QGraphicsView()
	window.setWindowTitle('TestHandles')
	window.setScene(QGraphicsScene())

	rect = QGraphicsRectItem(0, 0, 100, 100)
	rect.setFlag(QGraphicsItem.ItemIsMovable)
	rect.setHandlesChildEvents(False)
	x = IndoorIcon(rect)
	window.scene().addItem(x)

	g = window.geometry()
	g.setSize(QSize(800, 600))
	g.moveCenter(app.screens()[1].geometry().center())
	window.setGeometry(g)
	window.show()
	sys.exit(app.exec_())
