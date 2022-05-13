from functools import cached_property
from typing import Any, Callable, Optional

from PySide2.QtCore import QPointF, QRectF, Qt, QTimer
from PySide2.QtGui import QPainter, QPainterPath, QPen
from PySide2.QtWidgets import QApplication, QGraphicsItem, QGraphicsPathItem, QGraphicsSceneHoverEvent, QGraphicsSceneMouseEvent

from LevityDash.lib.ui.frontends.PySide.Modules.Handles import debug, Handle
from LevityDash.lib.ui.frontends.PySide.utils import colorPalette
from LevityDash.lib.utils.geometry import relativePosition, LocationFlag
from LevityDash.lib.utils.shared import clamp

__all__ = ["DrawerHandle", "HoverArea", "IndoorIcon"]


class DrawerHandle(Handle):
	size = 8
	width = 5
	height = 3
	debug = True

	# length = 15
	elapseSize = 6

	location = LocationFlag.BottomCenter
	parent: 'Panel'

	def __init__(self, parent):
		super(DrawerHandle, self).__init__(None, LocationFlag.BottomCenter)
		self.hideTimer = QTimer(interval=1000*5, timeout=self.close, singleShot=True)
		self.moveDoneTimer = QTimer(interval=1500, timeout=self.openClose, singleShot=True)
		parent.signals.resized.connect(self.rePos)
		self._parent = parent
		self.setParentItem(None)
		self.parent.scene().addItem(self)
		pen = QPen(QApplication.palette().foreground(), 1)
		self.setBrush(QApplication.palette().foreground().color())
		self.setPen(pen)
		self.setAcceptHoverEvents(True)
		self.setFlag(self.ItemIsMovable, True)
		self.setFlag(self.ItemSendsGeometryChanges, True)
		self.setAcceptedMouseButtons(Qt.LeftButton)

		self.setPath(self._path)
		self.setZValue(parent.zValue() + 10)
		self.setPos(self.position)
		self.setVisible(True)
		self.setEnabled(True)

	@cached_property
	def parent(self):
		return self._parent

	@property
	def position(self):
		# center = self.parent.rect().center()
		# center.setY(self.parent.rect().bottom() + self.boundingRect().height())
		pos = self.parent.pos() + self.parent.rect().bottomLeft()
		pos.setX(self.parent.rect().center().x())
		return pos

	def rePos(self, *args):
		self.setPos(self.position)

	def hoverEnterEvent(self, event):
		self.setCursor(Qt.OpenHandCursor)

	def hoverLeaveEvent(self, event):
		self.setCursor(Qt.ArrowCursor)

	def mousePressEvent(self, event):
		self.setCursor(Qt.ClosedHandCursor)

	def mouseReleaseEvent(self, event):
		self.moveDoneTimer.stop()
		self.openClose()
		if self.isUnderMouse():
			self.setCursor(Qt.OpenHandCursor)
		else:
			self.setCursor(Qt.ArrowCursor)

	def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
		if not self.isUnderMouse():
			self.setCursor(Qt.ArrowCursor)
		diff = event.scenePos() - event.lastScenePos()
		self.moveBy(diff.x(), diff.y())

	def itemChange(self, change: int, value: Any) -> Any:
		if change == self.ItemPositionChange or change == self.ItemPositionHasChanged:
			parentRect = self.parent.rect()
		if change == self.ItemPositionChange:
			value.setX(self.position.x())
			maxY = parentRect.height()
			minY = 0
			value.setY(clamp(value.y(), minY, maxY))
			self.moveDoneTimer.start()
		if change == QGraphicsItem.ItemPositionHasChanged:
			# self.scene().update()
			parentPos = QPointF(value)
			parentPos.setX(0)
			parentPos.setY(value.y() - parentRect.height())
			value.setX(0)
			self.parent.setPos(parentPos)
		return super(DrawerHandle, self).itemChange(change, value)

	def close(self):
		print('close')
		self.setPos(self.pos().x(), 0)

	def open(self):
		print('open')
		self.setPos(self.pos().x(), self.parent.rect().height())
		self.hideTimer.start()

	def openClose(self):
		if self.pos().y() > self.parent.rect().height()/2:
			self.open()
		else:
			self.close()

	@cached_property
	def _path(self):
		path = QPainterPath()
		e = self.size/6
		w = self.size/2
		o = self.size*0.8
		h = self.size/2
		xPositions = [x*o for x in range(0, self.width)]
		yPositions = [y*o for y in range(0, self.height)]
		# place circles in a 3 by 2 grid that is l long and w tall
		points = [QPointF(x, y) for x in xPositions for y in yPositions]
		for point in points:
			path.addEllipse(point, e, e)
		path.translate(-path.boundingRect().center().x(), -(e*self.height))
		return path

	@cached_property
	def _shape(self):
		# e = self.size / 6
		# x = (self.width - self.size / 2 + 0.5) * self.size * 0.8 - e
		# y = (self.height - self.size / 2 + 0.5) * self.size * 0.8 - e
		# path = QPainterPath(QPointF(x, y))
		# path.addRect(QRectF(x*2, y*6, -x*4, -y*8))
		path = QPainterPath()
		rect = self._path.boundingRect()
		rect.setWidth(rect.width()*2)
		rect.setHeight(rect.height()*2)
		rect.translate(-rect.center().x(), 0)
		path.addRect(rect)
		return path


class HoverArea(QGraphicsPathItem):

	def __init__(self, parent: 'Panel',
		size: int = 80,
		visible: bool = False,
		enterAction: Callable = None,
		exitAction: Callable = None,
		alignment: Optional[LocationFlag] = None,
		position: Optional[LocationFlag] = None):
		super(HoverArea, self).__init__(None)
		self.alignment = alignment
		self.position = position
		self.parent = parent
		self.parent.scene().addItem(self)
		self.setZValue(parent.zValue() + 10)
		self.size = size
		self.visible = visible
		self._enterAction = enterAction
		self._exitAction = exitAction
		self.setPath(self._path)
		self.setAcceptHoverEvents(True)
		self.setFlag(self.ItemIsMovable, False)
		self.setFlag(self.ItemSendsGeometryChanges, False)
		self.setAcceptedMouseButtons(Qt.NoButton)
		self.update()

		if self.visible:
			color = colorPalette.button().color()
			color.setAlpha(200)
			self.setBrush(color)
			self.setPen(Qt.NoPen)
		else:
			self.setBrush(Qt.NoBrush)
			self.setPen(Qt.NoPen)

	def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
		if self._enterAction:
			self._enterAction()

	def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
		if self._exitAction:
			self._exitAction()

	def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		if self._enterAction:
			self._enterAction()

	@property
	def _path(self):
		path = QPainterPath()

		align = self.alignment
		size = self.size

		if align.isCentered:
			x = -size/2
			y = -size/2

		if align.isTop:
			y = 0
		elif align.isBottom:
			y = -size
		if align.isLeft:
			x = 0
		elif align.isRight:
			x = -size

		path.addRect(QRectF(x, y, self.size, self.size))
		return path

	@property
	def position(self):
		if self._position is None:
			return relativePosition(self.parent)
		return self._position

	@position.setter
	def position(self, value):
		self._position = value

	@property
	def alignment(self):
		if self._alignment is None:
			return relativePosition(self.parent)
		return self._alignment

	@alignment.setter
	def alignment(self, value):
		self._alignment = value

	# def paint(self, painter: QPainter, option, widget=None):
	# 	if debug:
	# 		painter.setPen(QPen(Qt.red, 1))
	# 		painter.drawPath(self._path)
	# 		painter.setPen(QPen(Qt.black, 1))
	# 		painter.drawRect(self.boundingRect())
	# 	super(HoverArea, self).paint(painter, option, widget)

	def update(self):
		parentRect = self.parent.sceneRect()
		positionFlag = self.position

		if positionFlag.isCentered:
			x = parentRect.center().x()
			y = parentRect.center().y()

		if positionFlag.isTop:
			y = parentRect.top()
		elif positionFlag.isBottom:
			y = parentRect.bottom()

		if positionFlag.isLeft:
			x = parentRect.left()
		elif positionFlag.isRight:
			x = parentRect.right()

		self.setPos(x, y)
		self.setPath(self._path)
		super(HoverArea, self).update()


class IndoorIcon(QGraphicsPathItem):
	size = 5

	'''
	  This class is used to draw the indoor icon for measurements that are indoors
	  It ie denoted by a small house
	'''

	def __init__(self, parent):
		super(IndoorIcon, self).__init__(parent)
		self.setParentItem(parent)
		self.setZValue(parent.zValue() + 1)
		self.setPath(self._path)
		self.setPen(QPen(QApplication.palette().text().color(), self.size/4))

	@cached_property
	def _path(self):
		path = QPainterPath()
		mainHouseRect = QRectF(-self.size/2, 0, self.size, self.size*0.8)
		roofTopPoint = QPointF(0, -self.size*0.7)
		roofBottomLeft = QPointF(-self.size*0.8, 0)
		roofBottomRight = QPointF(self.size*0.8, 0)
		path.addRect(mainHouseRect)
		path.moveTo(roofTopPoint)
		path.lineTo(roofBottomLeft)
		path.lineTo(roofBottomRight)
		path.lineTo(roofTopPoint)
		path = path.simplified()
		r = path.boundingRect()
		r.moveCenter(QPointF(0, 0))
		path.translate(-r.topLeft())
		return path

	def update(self):
		super(IndoorIcon, self).update()
		# move to the bottom right corner of parent offset by 10
		p = self.parentItem().rect().bottomRight()
		size = self.boundingRect()
		size.moveBottomRight(p)
		size.moveBottomRight(size.topLeft())
		self.setPos(size.topLeft())
