import utils.data
from LevityDash.lib import logging
from dataclasses import dataclass
from functools import cached_property
from operator import attrgetter
from typing import Optional, Type, Union

from numpy import ceil, cos, pi, radians, sin, sqrt
from PySide2 import QtCore
from PySide2.QtCore import Property, QAbstractAnimation, QEasingCurve, QLineF, QObject, QPoint, QPointF, QPropertyAnimation, QRect, QRectF, QSizeF, Qt, QTimer, Signal, Slot
from PySide2.QtGui import QBrush, QColor, QFont, QFontMetrics, QFontMetricsF, QPainter, QPainterPath, QPen, QPolygonF
from PySide2.QtWidgets import (QCheckBox, QFormLayout, QGraphicsItem, QGraphicsItemGroup, QGraphicsObject, QGraphicsPathItem, QGraphicsScene, QGraphicsSceneDragDropEvent, QGraphicsSceneMouseEvent, QGraphicsTextItem, QGraphicsView, QLabel,
                               QStyleOptionGraphicsItem,
                               QVBoxLayout, QWidget)
from WeatherUnits import Direction, DistanceOverTime, Measurement, Angle

from LevityDash.lib.fonts import defaultFont
from LevityDash.lib.utils import Subscription
from Modules import estimateTextSize
from LevityDash.lib.utils.data import MinMax
from LevityDash.lib.utils.shared import half, Numeric, radialPoint
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel

log = logging.getLogger(__name__)


@dataclass
class Divisions:
	"""
	Divisions for a gauge.
	"""

	#: The number of divisions.
	count: Optional[int]
	#: The length of each tick.
	length: float
	#: The line width of each tick.
	lineWidth: float
	#: The color of the tick.
	color: QColor = None
	#: The Alpha level.
	alpha: float = 1.0

	subdivison: 'Divisions' = None


class savedCashedProperty(cached_property):

	def __set_name__(self, owner, name):
		owner._cashedValues.add(name)
		super(savedCashedProperty, self).__set_name__(owner, name)


class GaugeItem:
	_gauge: 'Gauge'
	_cache: list

	def __init__(self, gauge: 'Gauge'):
		self._cache = []
		self._gauge = gauge
		super(GaugeItem, self).__init__()

	def _clearCache(self):
		while self._cache:
			delattr(self, self._cache.pop())

	def update(self):
		self._clearCache()
		super(GaugeItem, self).update()

	@property
	def gauge(self) -> 'Gauge':
		return self._gauge


class GaugePathItem(GaugeItem, QGraphicsPathItem):

	def __init__(self, *args, **kwargs):
		super(GaugePathItem, self).__init__(*args, **kwargs)
		self.setPen(self.gauge.pen)

	def update(self):
		super(GaugePathItem, self).update()
		p = self.pen()
		p.setWidthF(self.gauge.pen.widthF())
		self.setPen(p)


class GaugeArc(GaugePathItem):

	def __init__(self, *args, **kwargs):
		super(GaugeArc, self).__init__(*args, **kwargs)
		pen = self.pen()
		pen.setCapStyle(Qt.RoundCap)
		self.setPen(pen)
		self.update()

	def mousePressEvent(self, event):
		print('click')
		event.ignore()
		super(GaugeArc, self).mousePressEvent(event)

	@property
	def center(self):
		return QPointF(self.gauge.rect().center())

	# return self.boundingRect().center()

	@cached_property
	def offset(self):
		self._cache.append('offset')
		return self.pen().widthF()/4*360/(2*pi*self._gauge.radius)*0.85

	@property
	def startAngle(self) -> float:
		return self.gauge.startAngle + self.offset

	@property
	def endAngle(self):
		return self.gauge.endAngle - self.offset

	@property
	def fullAngle(self) -> float:
		return self.endAngle - self.startAngle

	def update(self):
		super(GaugeArc, self).update()
		self.draw()

	def makeShape(self):
		iShape = QRectF(self.gauge.gaugeRect)
		oShape = QRectF(self.gauge.gaugeRect)
		x, y = self.gauge.gaugeRect.size().toTuple()
		small = self.gauge.radius*1.95
		large = self.gauge.radius*2.05
		iShape.setSize(QSizeF(small, small))
		oShape.setSize(QSizeF(large, large))
		path = QPainterPath()
		path.arcMoveTo(iShape, -self.startAngle + 90)
		path.arcTo(iShape, -self.startAngle + 90, -self.fullAngle)
		path.arcMoveTo(oShape, -self.startAngle + 90)
		path.arcTo(oShape, -self.startAngle + 90, -self.fullAngle)
		path.closeSubpath()
		return path

	def draw(self):
		self._shape = self.makeShape()
		path = self.path()
		path.clear()
		path.arcMoveTo(self.gauge.gaugeRect, -self.startAngle + 90)
		path.arcTo(self.gauge.gaugeRect, -self.startAngle + 90, -self.fullAngle)
		self.setPath(path)

	def shape(self):
		return self._shape


class Tick(QGraphicsPathItem):
	_index: float
	_center: QPointF
	_radius: float
	_properties: Divisions
	_offsetAngle: float
	startPoint: QPointF
	endPoint: QPointF

	def __init__(self, group: 'TickGroup', index: float):
		self._index = index
		self._group = group
		super(Tick, self).__init__()
		pen = QPen(self.gauge.pen.color())
		pen.setCapStyle(Qt.RoundCap)
		self.setPen(pen)
		self.draw()
		self.setAcceptedMouseButtons(Qt.LeftButton)

	def mousePressEvent(self, event):
		event.accept()
		print(event)

	def mouseMoveEvent(self, event):
		print(event.pos())

	@property
	def gauge(self):
		return self._group.gauge

	@property
	def group(self) -> Union['TickGroup', 'SubTickGroup']:
		return self._group

	def update(self):
		pen = self.pen()
		pen.setWidthF(self.properties.lineWidth*self.gauge.baseWidth)
		self.setPen(pen)
		super(Tick, self).update()
		self.draw()

	@cached_property
	def angle(self):
		return self.group.startAngle + self._index*self.group.spacing

	@property
	def index(self):
		return self._index

	@index.setter
	def index(self, value):
		if hasattr(self, 'angle'):
			delattr(self, 'angle')
		self._index = value

	@property
	def radius(self):
		return self.gauge.radius

	@property
	def properties(self):
		return self._group._properties

	def draw(self):
		path = QPainterPath()
		angle = radians(self.angle)
		cosI, sinI = cos(angle), sin(angle)
		center = self.gauge.arc.center
		cx = center.x()
		cy = center.y()
		radius = self.radius
		length = self.properties.length*radius

		x1 = cx + radius*cosI
		y1 = cy + radius*sinI
		x2 = cx + (radius - length)*cosI
		y2 = cy + (radius - length)*sinI
		p1 = QPointF(x1, y1)
		self.startPoint = p1
		p2 = QPointF(x2, y2)
		self.endPoint = p2
		path.moveTo(p1)
		path.lineTo(p2)
		# path.closeSubpath()
		self.setPath(path)


class SubTick(Tick):
	_superTick: Tick

	def __init__(self, superTick: Tick, *args, **kwargs):
		self._superTick = superTick
		super(SubTick, self).__init__(*args, **kwargs)

	@cached_property
	def angle(self):
		return self._superTick.angle + self._index*self.group.spacing


class TickGroup(QGraphicsItemGroup):
	_properties: Divisions
	_cache: list
	_ticks: list[Tick]

	def __init__(self, gauge: 'Gauge', properties: Divisions):
		self._cache = []
		self._ticks = []
		self._gauge = gauge
		self._properties = properties
		self.scale = 1
		super(TickGroup, self).__init__()
		self.draw()

	def draw(self):
		for i in range(0, self.count + 1):
			tick = Tick(self, i)
			self.addToGroup(tick)
			self._ticks.insert(i, tick)
		if self._properties.subdivison is not None:
			self.addToGroup(SubTickGroup(self, self._gauge, self._properties.subdivison))

	@property
	def ticks(self):
		return self._ticks

	@property
	def gauge(self):
		return self._gauge

	@cached_property
	def spacing(self) -> float:
		self._cache.append('spacing')
		return self._gauge.fullAngle/self.count

	@cached_property
	def count(self):
		self._cache.append('count')
		count = self._properties.count
		if count is None:
			count = self.gauge.range.range
			if count == 360:
				return 8
			while count > 15:
				count /= 10
				self.scale *= 10
			count = int(ceil(count))
		return count

	def clear(self):
		for item in self.childItems():
			self.removeFromGroup(item)

	def rebuild(self):
		self.clear()
		self.draw()

	def update(self):
		while self._cache:
			delattr(self, self._cache.pop())
		for item in self.childItems():
			item.update()
		super(TickGroup, self).update()

	@property
	def startAngle(self):
		return self._gauge.startAngle - 90


class SubTickGroup(TickGroup):
	superTickGroup: TickGroup

	def __init__(self, superTickGroup, *args, **kwargs):
		self.superTickGroup = superTickGroup
		super(SubTickGroup, self).__init__(*args, **kwargs)

	@cached_property
	def count(self):
		return self._properties.count

	@cached_property
	def spacing(self) -> float:
		return self.superTickGroup.spacing/self.count

	@property
	def items(self):
		items = self.superTickGroup.childItems()
		group = self.superTickGroup
		while isinstance(group, SubTickGroup):
			group = group.superTickGroup
			items.extend(group.childItems())
		return items

	def draw(self):
		items = self.items
		items.sort(key=attrgetter('angle'))
		for tick in items[:-1]:
			for i in range(1, self.count):
				item = SubTick(tick, self, i)
				self.addToGroup(item)
		if self._properties.subdivison is not None:
			self.addToGroup(SubTickGroup(self, self._gauge, self._properties.subdivison))


# item.setPos(parent.arc.center)
# item = QGraphicsTextItem(str(i))


class NeedleAnimation(QPropertyAnimation):

	def __init__(self, parent, varName=b"rotation"):
		super(NeedleAnimation, self).__init__(parent, varName)
		self.setStartValue(0)
		self.setDuration(3000)
		self.setEasingCurve(QEasingCurve.OutCubic)


class Needle(GaugePathItem):
	_animation: QPropertyAnimation
	_animationSignal = Signal(float)
	_value: float = 0.0

	def __init__(self, *args, **kwargs):
		super(Needle, self).__init__(*args, **kwargs)
		# self._animation = NeedleAnimation(self)
		pen = QPen()
		pen.setJoinStyle(Qt.RoundJoin)
		self.setPen(Qt.NoPen)
		# self.setPen(QPen(Qt.red))
		self.setBrush(QBrush(self.gauge.defaultColor))

	# self.setTransformOriginPoint(*self.gauge.arc.center.toTuple())

	def mousePressEvent(self, event):
		print(event.pos())
		super(Needle, self).mousePressEvent(event)

	def update(self):
		super(Needle, self).update()
		# self.setTransformOriginPoint(*self.gauge.arc.center.toTuple())
		self.draw()

	@cached_property
	def needleWidth(self) -> float:
		self._cache.append('needleWidth')
		return self.gauge.needleWidth*self.gauge.radius

	@cached_property
	def needleLength(self) -> float:
		self._cache.append('needleLength')
		return self.gauge.needleLength*self.gauge.radius

	@cached_property
	def needleSize(self) -> QSizeF:
		self._cache.append('needleSize')
		return QSizeF(self.needleWidth, self.needleLength)

	def draw(self):
		center = self._gauge.arc.center
		cx = 0
		cy = 0
		middle = QPointF(cx, cy - self.needleLength)
		needleWidth = self.needleWidth
		left = QPointF(cx - needleWidth/2, cy)
		right = QPointF(cx + needleWidth/2, cy)
		arcStart = QPointF(left)
		arcStart.setY(left.y() + needleWidth*0.6)
		arcEnd = QPointF(right)
		arcEnd.setY(right.y() + needleWidth*0.6)
		arcRect = QRectF(arcStart, QSizeF(needleWidth, -needleWidth))

		needlePath = QPainterPath()
		needlePath.arcMoveTo(arcRect, 0)
		needlePath.lineTo(middle)
		# needlePath.lineTo(arcRect.center())
		# needlePath.lineTo(center)
		# needlePath.lineTo(cx, cy + 10)
		needlePath.arcTo(arcRect, 180, -180)
		# needlePath.arcMoveTo(arcRect, 180)
		# needlePath.lineTo(right)
		# needlePath.lineTo(1000,1000)
		# needlePath.closeSubpath()
		self.setPath(needlePath.simplified())


class Arrow(Needle):

	def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget):
		# draw lines through the center
		painter.setPen(QPen(Qt.red))
		painter.drawRect(self.boundingRect())
		# c = self.boundingRect().center()
		# cTop = QPointF(c.x(), 0)
		# cBottom = QPointF(c.x(), self.boundingRect().height())
		# painter.drawLine(cTop, cBottom)
		# c = self.gauge.arc.center
		# cLeft = QPointF(0, c.y())
		# cRight = QPointF(self.boundingRect().width(), c.y())
		# horizontal = QLineF(cLeft, cRight)
		# painter.drawLine(horizontal)
		# horizontal.translate(0, self.gauge.radius/2/4)
		# painter.drawLine(horizontal)
		# horizontal.translate(0, -self.gauge.radius/2/4*2)
		# painter.drawLine(horizontal)
		# painter.drawLine(self.gauge.arc.center, self.gauge.arc.center + QPointF(0, self.needleLength))
		super(Arrow, self).paint(painter, option, widget)

	@property
	def safeZone(self):
		path = QPainterPath()
		radius = self.gauge.radius
		path.addEllipse(QPoint(0, 0), radius*0.6, radius*0.6)
		return path

	# super(Arrow, self).paint(painter, option, widget)

	def draw(self):
		# center = self._gauge.arc.center
		cx = 0
		cy = 0

		# Draw Circle
		radius = self.gauge.radius
		pointerHeight = radius*0.178
		radius = radius - pointerHeight
		base = pointerHeight
		path = QPainterPath()

		# Draw Outer Circle
		path.setFillRule(Qt.FillRule.WindingFill)
		path.addEllipse(QPoint(cx, cy), radius, radius)

		# Draw Arrow
		middle = QPointF(cx, cy - pointerHeight - radius)
		left = QPointF(cx - base, cy - radius + 10)
		right = QPointF(cx + base, cy - radius + 10)
		arrow = QPolygonF()
		path.moveTo(left)
		path.lineTo(middle)
		path.lineTo(right)
		# arrow.append(middle)
		# arrow.append(left)
		# arrow.append(right)
		# path.addPolygon(arrow)

		path = path.simplified()

		# path.setFillRule(Qt.FillRule.WindingFill)

		# Draw Center Circle
		path.addEllipse(QPoint(0, 0), radius*0.8, radius*0.8)
		path.setFillRule(Qt.FillRule.OddEvenFill)

		self.setPath(path)


# center = self._gauge.arc.center
# cx = center.x()
# cy = center.y()
# middle = QPointF(cx, cy - self.needleLength)
# needleWidth = self.needleWidth
# left = QPointF(cx - needleWidth / 2, cy)
# right = QPointF(cx + needleWidth / 2, cy)
# arcStart = QPointF(left)
# arcStart.setY(left.y() + needleWidth * 0.6)
# arcEnd = QPointF(right)
# arcEnd.setY(right.y() + needleWidth * 0.6)
# arcRect = QRectF(arcStart, QSizeF(needleWidth, -needleWidth))
#
# needlePath = QPainterPath()
# needlePath.arcMoveTo(arcRect, 0)
# needlePath.lineTo(middle)
# # needlePath.lineTo(arcRect.center())
# # needlePath.lineTo(center)
# # needlePath.lineTo(cx, cy + 10)
# needlePath.arcTo(arcRect, 180, -180)
# # needlePath.arcMoveTo(arcRect, 180)
# # needlePath.lineTo(right)
# # needlePath.lineTo(1000,1000)
# # needlePath.closeSubpath()
# self.setPath(needlePath.simplified())


class GaugeText(GaugeItem, QGraphicsTextItem):
	def __init__(self, *args, **kwargs):
		super(GaugeText, self).__init__(*args, **kwargs)
		self.setFont(self.gauge.tickFont)
		self.setDefaultTextColor(self.gauge.defaultColor)

	def update(self):
		super(GaugeText, self).update()


class GaugeValueText(GaugeText):
	_value: Numeric = Measurement(0)
	_valueClass: Type[Measurement] = Measurement

	def setClass(self, value):
		assert value is Measurement
		self._valueClass = value

	def mousePressEvent(self, event):
		print(self.string)

	@property
	def string(self):
		valueClass = self.gauge.valueClass
		value = self.gauge.value
		if isinstance(valueClass, tuple):
			valueClass, n, d = valueClass
			value = valueClass(n(value), d(1)).withoutUnit
		elif issubclass(valueClass, Measurement):
			value = valueClass(value).withoutUnit
		else:
			value = str(round(value, 2))
		return value

	@property
	def value(self):
		return self._value

	@value.setter
	def value(self, value):
		self._value = value

	def draw(self):
		font = self.gauge.tickFont
		font.setPixelSize(self.gauge.radius*0.2)
		self.setFont(font)
		self.setHtml(self.string)
		textRect = self.boundingRect()
		textRect.moveCenter(radialPoint(self.gauge.arc.center, self.gauge.radius*0.35, self.gauge.startAngle + 90 + (self.gauge.fullAngle/2)))
		# textRect.translate(-textRect.width() / 2, 0)
		self.setPos(textRect.topLeft())

	def update(self):
		self.draw()
		super(GaugeValueText, self).update()


class AnimationBridge(QObject):

	def __init__(self, object, *args, **kwargs):
		super(AnimationBridge, self).__init__(*args, **kwargs)
		self.object = object
		self._testAnim = 0

		self._scaleAnimation = QPropertyAnimation(self, b'testAnim')
		self._scaleAnimation.setDuration(1000)
		self._scaleAnimation.setStartValue(0.01)
		self._scaleAnimation.setEasingCurve(QEasingCurve.OutQuad)
		self._scaleAnimation.setEndValue(0.75)

	def start(self):
		self._scaleAnimation.start()

	@Property(float)
	def testAnim(self):
		return self._testAnim

	@testAnim.setter
	def testAnim(self, value):
		self._testAnim = value
		self.object.fontScale = value
		self.object.update()


class CustomText(QGraphicsPathItem):
	gauge: 'Gauge'
	_fontScale = 0.2
	_text: str = '0.0'
	_font: QFont

	def __init__(self, gauge: 'Gauge', *args, **kwargs):
		super(CustomText, self).__init__(*args, **kwargs)
		self.mouseDown = False
		self.setFlag(QGraphicsItem.ItemIsMovable, True)
		self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
		self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
		self.gauge = gauge
		self.setPen(QPen(self.gauge.defaultColor))
		self.setBrush(QBrush(self.gauge.defaultColor))
		self.color = self.gauge.defaultColor
		self._cachedValues = []
		self._font = self.gauge.tickFont
		# self.animationBridge = AnimationBridge(self)

		self.animationTimer = QTimer()
		self.animationTimer.timeout.connect(self.grav)
		self.animationTimer.setInterval(20)

		self.animationTimer.start()

	# fm = QFontMetrics(self.font())
	# fm.tightBoundingRect(self.text)

	def updateFontSize(self):
		self.textWidthRatio = self.fontMetrics.width(self.text)/100
		self._maxFontSize = min(font.pointSizeF()*self._ratio, self.height()*.7)

	def widthForHeight(self, height: float):
		return self.text

	@cached_property
	def fontMetrics(self):
		font = self.font
		font.setPixelSize(100)
		return QFontMetrics(font)

	@property
	def safeZone(self) -> QPainterPath:
		return self.mapFromParent(self.gauge.safeZone)

	@property
	def fontMetrics(self):
		return QFontMetrics(self.dynamicFont)

	@property
	def string(self):
		value = self.text
		return str(value)

	@property
	def text(self):
		return self._text

	@text.setter
	def text(self, value):
		self._text = value

	# self.autoResize()

	@property
	def font(self):
		self._font.setPointSizeF(self.fontSize)
		return self._font

	@font.setter
	def font(self, value):
		self._font = value

	@property
	def color(self):
		return self._color

	@color.setter
	def color(self, value):
		self._color = value

	@property
	def dynamicFont(self):
		return self.font

	def autoResize(self):
		if not self.insideSafeZone:
			self.animationBridge._scaleAnimation.setStartValue(self.fontScale)
			self.animationBridge._scaleAnimation.setEndValue(0.5)
			self.animationBridge._scaleAnimation.start()
		else:
			self.animationBridge._scaleAnimation.setStartValue(self.fontScale)
			self.animationBridge._scaleAnimation.setEndValue(.75)
			self.animationBridge._scaleAnimation.start()

	def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget):
		# # if self.path().intersects(self.safeZone.path()):
		# sPath = self.mapToScene(self.path())
		# zPath = self.mapToScene(self.safeZone)
		# # x = self.path().intersected(zPath)
		# painter.setBrush(QBrush(Qt.blue))
		# painter.setPen(QPen(Qt.red, 1))
		# painter.drawPath(self.overlap)
		super(CustomText, self).paint(painter, option, widget)

	@property
	def overlap(self) -> QPainterPath:
		return self.path().subtracted(self.safeZone)

	@property
	def fontScale(self) -> float:
		if self._fontScale is None:
			self._fontScale = 0.0
		return self._fontScale

	@fontScale.setter
	def fontScale(self, value):
		old = self._fontScale
		self._fontScale = value
		self.update()
		# if self.animationBridge._scaleAnimation.state() == QAbstractAnimation.Running:
		# 	if self.animationBridge._scaleAnimation.startValue() < self.animationBridge._scaleAnimation.endValue():
		# 		if not self.insideSafeZone:
		# 			self._fontScale = old
		# 			self.animationBridge._scaleAnimation.stop()
		# 	else:
		# 		if self.insideSafeZone:
		# 			self._fontScale = old
		# 			self.animationBridge._scaleAnimation.stop()
		# else:
		if value > old:
			if not self.insideSafeZone:
				self._fontScale = old
				self.gravitateTo()
				self.update()

	def grav(self):
		self.gravitateTo()

	def gravitateTo(self, point: QPointF = None):
		'''
			Gravitates the text to the given point by a slight amout
		:param self:
		:type self:
		:param point:
		:type point:
		:return:
		:rtype:
		'''
		if point is None:
			point = QPoint(0, 0)

		nudge = (self.mapToScene(self.boundingRect().center()) - self.boundingRect().center())*.03
		self.moveBy(-nudge.x(), -nudge.y())

	@property
	def insideSafeZone(self):
		return self.collidesWihPath(self.safeZone, Qt.ContainsItemShape)

	@property
	def hasCollisions(self):
		return [x for x in self.collidingItems() if x.__class__ == self.__class__]

	def resize(self):
		oldScale = self.fontScale
		self.prepareGeometryChange()

	# self.setPos(QPoint(0,0))
	# while self.insideSafeZone:
	# 	self.fontScale *= 1.05
	# 	self.update()
	# while not self.collidesWithPath(self.safeZone, Qt.ContainsItemShape):
	# 	self.fontScale *= 0.99
	# 	self.update()
	# self.setPos(QPoint(0,0))
	# print(self.overlap.boundingRect())

	# def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
	# 	if not self.insideSafeZone:
	# 		self.setFlag(QGraphicsItem.ItemIsMovable, False)
	# 		self.gravitateTo()
	# 		self.hasLeft = True
	# 	if not self.flags() & QGraphicsItem.ItemIsMovable:
	# 		if self.boundingRect().contains(event.pos()) and not self.hasLeft:
	# 			self.setFlag(QGraphicsItem.ItemIsMovable, True)
	# 			self.setTransformOriginPoint(event.pos())
	# 			self.hasLeft = False
	# 	super(CustomText, self).mouseMoveEvent(event)

	def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget):
		super(CustomText, self).paint(painter, option, widget)
		fm = QFontMetrics(self.font)
		rect = fm.tightBoundingRect(self.text)
		rect.moveCenter(QPoint(0, 0))
		painter.setPen(QPen(Qt.white, 1))
		painter.drawRect(rect)

	def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
		self.animationTimer.stop()
		self.mouseDown = True

		# points: list[QPointF] = []
		# polygon: QPolygonF = self.shape().toFillPolygon()

		'''QPolygonF
		polygon = outerArc.toFillPolygon();
		foreach(auto
		point, polygon)
		{
			points.push_back(point);
		}
		QList < QPointF > pointsResult;
		makeOffsetFace(points, -0.25 * mMaxelSize, pointsResult);
		QPolygonF
		polygonOffset;
		foreach(auto
		point, pointsResult)
		{
			polygonOffset << point;
		}
		if (!polygonOffset.isEmpty())
		{
			mOuterFillPath.addPolygon(polygonOffset);
		}'''
		super(CustomText, self).mousePressEvent(event)

	def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
		if self.boundingRect().contains(event.pos()):
			if self.x == False:
				self.y = True
			else:
				self.y = False
			self.x = True
		else:
			self.x = False
		super(CustomText, self).mouseMoveEvent(event)

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemPositionChange:
			collisions = self.hasCollisions
			if not self.mouseDown and collisions:
				offset = sum((self.mapToScene(self.boundingRect().center()) - collisions[0].mapToScene(collisions[0].boundingRect().center())).toTuple())
				# if offset < 10:
				# 	return self.pos() + QPoint(*self.boundingRect().size().toTuple())
				# else:
				return self.pos()
			# cols = self.hasCollisions
			# if cols:
			# 	i = cols[0]
			# 	p = self.pos()
			# 	p.setY(p.y() - i.pos().y() + i.boundingRect().height() + 5)
			# 	return p
			if not self.insideSafeZone:
				if value.manhattanLength() < self.pos().manhattanLength():
					return super(CustomText, self).itemChange(change, value)
				return self.pos()

		return super(CustomText, self).itemChange(change, value)

	def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
		self.mouseDown = False
		self.setFlag(QGraphicsItem.ItemIsMovable, True)
		self.animationTimer.start()
		super(CustomText, self).mouseReleaseEvent(event)

	@property
	def dynamicFontSize(self):
		font = self.font

	# self.setFont(font)
	# self.textWidth = self.fontMetrics().width(self.textSizeHint)
	# self._ratio = self.width() / self.textWidth
	# self._maxFontSize = min(font.pointSizeF() * self._ratio, self.height() * .7)

	@property
	def fontSize(self) -> float:
		self._cachedValues.append('fontSize')
		return self.gauge.radius*self.fontScale

	def update(self):
		tightRect = self.fontMetrics.tightBoundingRect(self.string)
		wid = self.fontMetrics.width(self.string)
		tightRect.moveCenter(self.gauge.arc.center.toPoint())

		path = QPainterPath()
		p = self.gauge.arc.center.toPoint()
		# p = QPointF(0,0)
		# p.setX(p.x() - tightRect.width() / 2)
		# p.setY(p.y() + tightRect.height() / 2)
		path.addText(0 - tightRect.width()*1.05/2, tightRect.height()/2, self.dynamicFont, self.string)
		# path.moveTo(p)

		self.setPath(path)
		t = QPointF(*half(tightRect.size()).toTuple())
		self.setTransformOriginPoint(tightRect.center())
		# t.setY(t.y() * -1)
		self.setTransformOriginPoint(t)
		# self.setPos(p)

		# self.setRotation(45)
		super(CustomText, self).update()


# def setPos(self, point: QPointF):
# 	point.setX(point.x() - self.boundingRect().width() / 2)
# 	point.setY(point.y() + self.boundingRect().height() / 2)
# 	super(CustomText, self).setPos(point)


class GaugeSpeedText(GaugeText):
	_value: DistanceOverTime = DistanceOverTime(0)
	_valueClass: Type[DistanceOverTime] = DistanceOverTime

	def __init__(self, gauge: 'Gauge', value: DistanceOverTime = None, subscription: Subscription = None, *args, **kwargs):
		super(GaugeSpeedText, self).__init__(gauge, *args, **kwargs)

	def setClass(self, value):
		assert value is Measurement
		self._valueClass = value

	@property
	def string(self):
		valueClass = self._valueClass
		value = self._value
		if isinstance(valueClass, tuple):
			valueClass, n, d = valueClass
			value = valueClass(n(value), d(1)).withoutUnit
		elif issubclass(valueClass, Measurement):
			value = valueClass(value).withoutUnit
		else:
			value = str(round(value, 2))
		return value

	@property
	def value(self):
		return self._value

	@value.setter
	def value(self, value):
		self._value = value

	def draw(self):
		font = self.gauge.tickFont
		font.setPixelSize(self.gauge.radius*0.4)
		self.setFont(font)

	# self.setHtml(self.string)
	# textRect = self.boundingRect()
	# point = radialPoint(self.gauge.arc.center, 0, 90)
	# point.setY(point.y() + textRect.height() / 2)
	# textRect.moveCenter(point)
	# self.setPos(textRect.topLeft())
	# textRect.translate(-textRect.width() / 2, 0)

	def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget):
		painter.drawRect(self.boundingRect())
		painter.setFont(self.font())
		fm = painter.fontMetrics()
		tightRect = fm.tightBoundingRect(self.string)
		tightRect.moveCenter(self.gauge.arc.center.toPoint())
		painter.drawRect(tightRect)
		super(GaugeSpeedText, self).paint(painter, option, widget)

	def update(self):
		self.draw()
		super(GaugeSpeedText, self).update()


class GaugeDirectionText(GaugeText):
	_value: Direction = Direction(0)
	_valueClass: Type[DistanceOverTime] = Direction

	def __init__(self, gauge: 'Gauge', value: DistanceOverTime = None, subscription: Subscription = None, *args, **kwargs):
		super(GaugeDirectionText, self).__init__(gauge, *args, **kwargs)

	@property
	def string(self):
		valueClass = self._valueClass
		value = self._value
		if isinstance(valueClass, tuple):
			valueClass, n, d = valueClass
			value = valueClass(n(value), d(1)).withoutUnit
		elif issubclass(valueClass, Measurement):
			value = valueClass(value).withoutUnit
		else:
			value = str(round(value, 2))
		return value

	@property
	def value(self):
		return self._value

	@value.setter
	def value(self, value):
		self._value = value

	def draw(self):
		font = self.gauge.tickFont
		font.setPixelSize(self.gauge.radius*0.2)
		self.setFont(font)
		self.setHtml(self.string)

	# textRect.translate(-textRect.width() / 2, 0)

	def update(self):
		self.draw()
		super(GaugeDirectionText, self).update()


class GaugeUnit(GaugeText):

	def __init__(self, *args, **kwargs):
		super(GaugeText, self).__init__(*args, **kwargs)
		self.draw()

	@property
	def string(self):
		return str(self.gauge.unit)

	def draw(self):
		font = self.gauge.tickFont
		font.setPixelSize(self.gauge.radius*0.3)
		self.setFont(font)
		self.setHtml(self.string)
		textRect = self.boundingRect()
		textRect.moveCenter(radialPoint(self.gauge.arc.center, self.gauge.radius*0.35, self.gauge.startAngle - 90 + (self.gauge.fullAngle/2)))
		# textRect.translate(-textRect.width() / 2, 0)
		self.setPos(textRect.topLeft())

	# self.setPos(radialPoint(self.gauge.arc.center, self.gauge.radius * 0.35, self.gauge.startAngle - 90 + (self.gauge.fullAngle / 2)))

	def update(self):
		self.draw()
		self.setVisible(self.gauge.unit is not None)
		super(GaugeUnit, self).update()


class GaugeTickText(GaugeText):
	_rotated: bool = True
	_flipUpsideDown = (False, True)
	_scale: Optional[float] = None

	def __init__(self, tick, group, *args, **kwargs):
		self.group = group
		self.offset = 0.75
		self.tick = tick
		super(GaugeTickText, self).__init__(utils.data.group.gauge, *args, **kwargs)
		font = QFont(defaultFont)
		font.setPointSizeF(70)
		self.setFont(font)
		self.rect = QGraphicsPathItem()

	@property
	def ax(self):
		return self.tick.radius*0.35

	def fontSizeCalc(self):
		# if self._scale is not None:
		# 	font.setPointSizeF(self.tick.radius * self._scale)
		# else:
		count = 0
		scale = 1.0

		# def hasCollisions(rect):
		# return rect.intersects(self.tick.boundingRect()) or collidingNeighbors(self, rect)
		# return collidingNeighbors(self, rect)

		# font = self.font()
		# font.setPointSizeF(self.ax)
		# fm = QFontMetricsF(font)
		# rect = fm.boundingRect(self.string)
		# rect.moveCenter(self.position())
		# collides = hasCollisions(rect)
		# while collides and scale > 0.3:
		# 	scale *= 0.9
		# 	font.setPointSizeF(self.ax * scale)
		# 	fm = QFontMetricsF(font)
		# 	rect = fm.tightBoundingRect(self.string)
		# 	rect.moveCenter(self.position())
		# 	collides = hasCollisions(rect)
		# 	count += 1
		# return scale
		self.setPlainText(self.string)
		textRect = self.boundingRect()
		textRect.moveCenter(self.position())
		self.setTransformOriginPoint(0 + textRect.width()/2, textRect.height()/2)
		self.setPos(textRect.topLeft())

	# collides = collidingNeighbors(self)

	def collidingNeighbors(self):
		v = [x for x in self.collidingItems(Qt.ItemSelectionMode.IntersectsItemShape) if isinstance(x, self.__class__)]
		return v

	def position(self):
		return radialPoint(self.gauge.arc.center, self.tick.radius*self.offset, self.tick.angle)

	# def shape(self):
	# 	return self.mapToScene(super(GaugeTickText, self).shape())

	@property
	def angleValue(self):
		return self.tick.angle - self.gauge.startAngle + 90

	@property
	def string(self):
		value = self.gauge.range.range/self.gauge.fullAngle*self.angleValue + self.gauge.range.min
		valueClass = self.gauge.valueClass
		if valueClass is float:
			if value.is_integer():
				value = int(value)
		else:
			if isinstance(valueClass, tuple):
				value = valueClass[0](valueClass[1](value), valueClass[2](1))
			else:
				value = valueClass(value)
				if valueClass is Direction:
					return value.cardinal.twoLetter
			if isinstance(value, Measurement):
				value = value.decoratedInt
		return str(value)

	def draw(self):
		# font = self.font()
		# font.setPointSizeF(self.tick.radius * 0.15)
		# self.setFont(font)
		self.setPlainText(self.string)
		textRect = self.boundingRect()

		textRect.moveCenter(self.position())
		self.setTransformOriginPoint(0 + textRect.width()/2, textRect.height()/2)
		self.setPos(textRect.topLeft())

	# self.setScale(1)
	# while self.collidesWithItem(self.tick, Qt.IntersectsItemShape) and count < 10:
	# # while self.collidesWithPath(self.tick.path(), Qt.IntersectsItemShape) and count < 50:
	# 	self.shrinkFont()
	# 	count += 1
	# print()

	def shape(self):
		# return super(GaugeTickText, self).shape()
		path = QPainterPath()
		fm = QFontMetricsF(self.font())
		rect = fm.tightBoundingRect(self.string)
		rect.moveCenter(self.boundingRect().center().toPoint())
		path.addRect(rect)
		return path

	def shrinkFont(self):
		scale = self.scale()
		self.setScale(scale - 0.05)

	# def setScale(self, value: float):
	# 	font = self.font()
	# 	self._scale = value
	# 	font.setPointSizeF(self.ax * value)
	# 	self.setFont(font)
	# 	self.update()

	def update(self):
		# scale = self.fontSizeCalc()
		# font = self.font()
		# font.setPointSizeF(self.ax * scale)
		# self.setFont(font)
		# self.draw()
		if self.group.tickScale is not None:
			# self.setScale(self.group.tickScale)
			font = self.font()
			font.setPointSizeF(self.ax*self.group.tickScale)
			self.setFont(font)
		self.draw()
		if self.rotated:
			angle = self.tick.angle + 90
			if (-90 > angle and self._flipUpsideDown[0]) or (angle > 90 and self._flipUpsideDown[1]):
				angle -= 180
			self.setRotation(angle)

	@property
	def rotated(self):
		return self.gauge.rotatedLabels


class GaugeTickTextGroup(QGraphicsItemGroup):
	tickScale = 1.0

	def __init__(self, ticks: TickGroup):
		self._ticks = ticks
		super(GaugeTickTextGroup, self).__init__()
		for tick in self.ticks:
			text = GaugeTickText(tick, self)
			self.addToGroup(text)
			self.addToGroup(text.rect)
		self.setTickScale()

	def setTickScale(self):
		self.tickScale = 1.0
		for item in self.childItems():
			cols = [x for x in item.collidingItems(Qt.ItemSelectionMode.IntersectsItemShape) if isinstance(x, (item.__class__, Tick))]
			while cols and self.tickScale > 0.3:
				cols.append(item)
				self.tickScale *= 0.9
				for x in cols:
					x.update()
				cols = [x for x in item.collidingItems(Qt.ItemSelectionMode.IntersectsItemShape) if isinstance(x, (item.__class__, Tick))]
			item.update()

	def update(self):
		if self.hasCollisions():
			self.setTickScale()
		for item in self.childItems():
			item.update()
		super(GaugeTickTextGroup, self).update()

	def getFontSizeRatio(self):
		scale = min([item.fontSizeCalc() for item in self.childItems() if isinstance(item, GaugeTickText)])
		for item in self.childItems():
			item.setScale(scale)
		return scale

	def collidesWithTicks(self) -> bool:
		return any([item.collidesWithItem(item.tick) for item in self.childItems() if isinstance(item, GaugeTickText)])

	def hasCollisions(self):
		collidesWitTicks = self.collidesWithTicks()
		if collidesWitTicks:
			return True
		for item in self.childItems():
			if isinstance(item, GaugeTickText) and item.collidingNeighbors():
				return True
		return False

	@property
	def ticks(self):
		if self._ticks.gauge.fullAngle >= 360:
			return [i for i in self._ticks.ticks if i.angle + 90 != 360]
		return self._ticks.ticks


class Gauge(Panel):
	__value: float = 0.0
	_needleAnimation: QPropertyAnimation
	valueChanged = Signal(float)

	ranges = {
		'inhg':       MinMax(27, 31),
		'mmhg':       MinMax(730, 790),
		'mbar':       MinMax(970, 1060),
		'f':          MinMax(0, 120),
		'c':          MinMax(-20, 50),
		'mph':        MinMax(0, 15),
		'in/hr':      MinMax(0, 3),
		'mm/hr':      MinMax(0, 75),
		'v':          MinMax(2.5, 3.3),
		'default':    MinMax(0, 100),
		'lux':        MinMax(0, 100000),
		'angle':      MinMax(0, 360),
		'percentage': MinMax(0, 1)
	}

	startAngle = -120
	endAngle = 120
	microDivisions = Divisions(count=5, length=0.04, lineWidth=0.2)
	minorDivisions = Divisions(count=2, length=0.075, lineWidth=0.4, subdivison=microDivisions)
	majorDivisions = Divisions(count=None, length=0.1, lineWidth=0.6, subdivison=minorDivisions)
	needleLength = 1.0
	needleWidth = 0.1
	_range = MinMax(0, 100)
	_valueClass: type = float
	_unit: Optional[str] = None
	_scene: QGraphicsScene
	_pen: QPen
	_cache: list
	rotatedLabels = True

	def __init__(self, *args, **kwargs):
		self._cache = []
		super(Gauge, self).__init__(*args, **kwargs)
		# config = ConfigWindow(self)
		self.__value: Union[Numeric, Measurement]
		self._pen = QPen(self.defaultColor)
		# self.setStyleSheet('background-color: black; color: white')

		# self.scene().setStyleSheet('background - color: black; color: white')

		self.image.setParentItem(self)

	# self.arc.moveBy(*offset.toTuple())
	# self.r = self.scene().addRect(rect, QPen(Qt.red))

	# def mousePressEvent(self, event):
	# 	print(self.itemAt(event.pos()))
	# 	if self.items(event.pos()):
	# 		event.ignore()
	# 		super(Gauge, self).mousePressEvent(event)
	# 	else:
	# 		event.accept()
	# 		super(Gauge, self).mousePressEvent(event)

	# 	s = self.scene()
	# 	x = self.items(event.pos())
	# 	items = []
	# 	for item in x:
	# 		if isinstance(item, QGraphicsItemGroup):
	# 			for i in item.childItems():
	# 				i: QGraphicsItem
	# 				if i.contains(event.pos()):
	# 					items.append(i)
	# 		else:
	# 			items.append(item)
	# 	# print([x for x in s.items() if x.contains(event.pos())])

	def update(self):
		try:
			self.image.update()
		except AttributeError:
			pass

	# self.scene().update(self.rect())

	@property
	def state(self):
		return {}

	@property
	def value(self):
		return self._value

	@value.setter
	def value(self, value):
		if isinstance(value, (int, float)):
			self._value = value
			self.valueClass = value
			if isinstance(value, Measurement):
				self.setUnit(value)

	@cached_property
	def image(self):
		group = QGraphicsItemGroup()
		self.arc = GaugeArc(self)
		self.ticks = TickGroup(self, self.majorDivisions)
		self.labels = GaugeTickTextGroup(self.ticks)
		self.needle = Needle(self)
		self.unitLabel = GaugeUnit(self)
		self.valueLabel = GaugeValueText(self)
		group.addToGroup(self.arc)
		group.addToGroup(self.ticks)
		group.addToGroup(self.labels)
		group.addToGroup(self.unitLabel)
		group.addToGroup(self.valueLabel)
		group.addToGroup(self.needle)
		return group

	@Property(float)
	def _value(self):
		return self.__value

	@_value.setter
	def _value(self, value: float):
		value = max(self._range.min, min(self._range.max, value))
		angle = (value - self._range.min)/self._range.range*self.fullAngle + self.startAngle
		self.needle.setRotation(angle)
		self.valueLabel.update()
		self.__value = value

	@property
	def valueClass(self):
		return self._valueClass

	@valueClass.setter
	def valueClass(self, value):
		if isinstance(value, type):
			self._valueClass = value
		else:
			if hasattr(value, 'denominator'):
				self._valueClass = (value.__class__, value.numerator.__class__, value.denominator.__class__)
			else:
				self._valueClass = value.__class__
				if issubclass(self._valueClass, Angle):
					self.startAngle = 0
					self.endAngle = 360
					self.range = self.ranges['angle']

	def setValue(self, value: Union[Measurement, Numeric]):
		if isinstance(value, Measurement):
			self.valueClass = value
			self.setUnit(value)
		self.animateValue(self.__value, value)

	@Slot(float)
	def updateSlot(self, value: Union[Measurement, Numeric]):
		if isinstance(value, (int, float)):
			self.valueClass = value
			if isinstance(value, Measurement):
				self.setUnit(value)
			self.animateValue(self.__value, value)

	def animateValue(self, start: Numeric, end: Numeric):
		if self._needleAnimation.state() == QtCore.QAbstractAnimation.Running:
			self._needleAnimation.stop()
		self._needleAnimation.setStartValue(float(start))
		self._needleAnimation.setEndValue(float(end))
		self._needleAnimation.start()

	@property
	def pen(self):
		return self._pen

	@Slot(str)
	def setUnit(self, value: Union[str, Measurement]):
		if isinstance(value, (Measurement, str)):
			self.unit = value
		else:
			log.warning(f'{value} is not a valid string')

	@property
	def unit(self):
		return self._unit

	@unit.setter
	def unit(self, value):
		self._setUnit(value)
		self.unitLabel.update()

	def _setUnit(self, value):
		if isinstance(value, Measurement):
			self.range = self.getRange(value)
		if isinstance(value, Measurement):
			self._unit = value.unit
		elif isinstance(value, str):
			self._unit = value.strip()

	@property
	def range(self):
		return self._range

	@range.setter
	def range(self, value):
		if self._range != value:
			self._range = value
			self.rebuild()
			self.update()

	def getRange(self, value):
		toTry = []
		if isinstance(value, str):
			toTry.append(value)
		elif isinstance(value, Measurement):
			if not isinstance(value.type, tuple):
				typeString = str(value.type).strip("<class' >").split('.')[-1].lower()
				toTry.append(typeString)
			toTry.extend([value.unit.lower(), value.localize.unit.lower()])
		for attempt in toTry:
			try:
				return self.ranges[attempt]
			except KeyError:
				pass
		else:
			return self.ranges['default']

	def rebuild(self):
		while self._cache:
			delattr(self, self._cache.pop())
		self.image.removeFromGroup(self.ticks)
		self.scene().removeItem(self.ticks)
		self.image.removeFromGroup(self.labels)
		self.scene().removeItem(self.labels)
		self.image.removeFromGroup(self.unitLabel)
		self.scene().removeItem(self.unitLabel)
		self.image.removeFromGroup(self.valueLabel)
		self.scene().removeItem(self.valueLabel)

		self.ticks = TickGroup(self, self.majorDivisions)
		self.labels = GaugeTickTextGroup(self.ticks)
		self.unitLabel = GaugeUnit(self)
		self.valueLabel = GaugeValueText(self)
		self.image.addToGroup(self.ticks)
		self.image.addToGroup(self.labels)
		self.image.addToGroup(self.unitLabel)
		self.image.addToGroup(self.valueLabel)

	@Slot(int)
	def setMajorTicks(self, value: int):
		self.majorDivisions.count = value
		self.update()

	@Slot(int)
	def setMinorTicks(self, value: int):
		self.minorDivisions.count = value
		self.update()

	@Slot(int)
	def setMicroTicks(self, value):
		self.microDivisions.count = value
		self.update()

	@Slot(bool)
	def showLabels(self, value):
		self.labels.setVisible(value)

	@Slot(bool)
	def showArc(self, value):
		self.arc.setVisible(value)

	@cached_property
	def baseWidth(self):
		self._cache.append('baseWidth')
		return sqrt(self.height() ** 2 + self.width() ** 2)*0.008

	@cached_property
	def radius(self):
		self._cache.append('radius')
		return min(self.height(), self.width())/2 - 10

	@cached_property
	def gaugeRect(self) -> QRectF:
		self._cache.append('gaugeRect')
		f = QRectF(0.0, 0.0, self.radius*2, self.radius*2)
		f.moveCenter(self.rect().center())
		return f

	@cached_property
	def fullAngle(self):
		self._cache.append('fullAngle')
		return self.endAngle + -self.startAngle

	@property
	def defaultColor(self):
		# return Qt.white
		return self.scene().palette().text().color()

	@cached_property
	def tickFont(self):
		self._cache.append('tickFont')
		font = QFont(defaultFont)
		font.setPixelSize(max(self.radius*.1, 18))
		return font

	def draw(self):
		paint = QPainter(self)
		paint.setRenderHint(QPainter.HighQualityAntialiasing)
		paint.setRenderHint(QPainter.Antialiasing)
		cx, cy = QPointF(self.rect().center()).toTuple()
		radius = self.radius
		needleLength = self.needleLength*radius
		needleWidth = self.needleWidth*radius

		penWidth = sqrt(self.height() ** 2 + self.width() ** 2)*0.008
		brush = QBrush(self.defaultColor)
		paint.pen().setColor(self.defaultColor)

		fullAngle = self.endAngle + -self.startAngle

		# Gauge divisions setup
		major = self.majorDivisions
		minor = self.minorDivisions
		micro = self.microDivisions

		# Set spacing for divisions
		count = major.count
		scale = 1
		if count is None:
			count = self._range.range
			while count > 10:
				count /= 10
				scale *= 10
			count = int(ceil(count))

		majorSpacing = fullAngle/count
		minorSpacing = majorSpacing/minor.count
		microSpacing = minorSpacing/micro.count

		start = self.startAngle - 90

		majorLength = major.length*radius
		minorLength = minor.length*radius
		microLength = micro.length*radius

		arcPen = QPen(self.defaultColor)
		arcPen.setWidthF(penWidth)
		arcPen.setCapStyle(Qt.FlatCap)

		majorPen = QPen(self.defaultColor, major.lineWidth*penWidth)
		majorPen.setCapStyle(Qt.RoundCap)

		minorPen = QPen(self.defaultColor, minor.lineWidth*penWidth)
		minorPen.setCapStyle(Qt.RoundCap)

		microPen = QPen(self.defaultColor, micro.lineWidth*penWidth)
		microPen.setCapStyle(Qt.RoundCap)

		needlePen = QPen(self.defaultColor, 1)
		needlePen.setCapStyle(Qt.RoundCap)
		needlePen.setJoinStyle(Qt.RoundJoin)

		# Draw gauge arc
		paint.setPen(arcPen)
		arcPath = QPainterPath()
		arcPath.arcMoveTo(self.gaugeRect, (self.startAngle + 90))
		arcPath.arcTo(self.gaugeRect, (self.startAngle + 90), fullAngle)

		# Center drawing first
		translate = list((arcPath.boundingRect().center() - self.rect().center()).toTuple())
		translate[1] *= -1
		paint.translate(*translate)

		# Draw
		paint.drawPath(arcPath)

		gaugePath = QPainterPath()
		majorTicksPath = QPainterPath()
		minorTicksPath = QPainterPath()
		microTicksPath = QPainterPath()

		majorOffset = penWidth/2 - (major.lineWidth/2*penWidth)
		minorOffset = penWidth/2 - (minor.lineWidth/2*penWidth)
		microOffset = penWidth/2 - (micro.lineWidth/2*penWidth)
		paint.setFont(self.tickFont)

		def drawTick(i, path, length, offset, withValue: bool = False):
			radI = radians(i)
			cosI, sinI = cos(radI), sin(radI)

			x1 = cx + (radius + offset)*cosI
			y1 = cy + (radius + offset)*sinI
			x2 = cx + (radius - length)*cosI
			y2 = cy + (radius - length)*sinI
			p1 = QPointF(x1, y1)
			p2 = QPointF(x2, y2)
			path.moveTo(p1)
			path.lineTo(p2)

			# add value text
			if withValue:
				x3 = cx + (radius - length*2)*cosI
				y3 = cy + (radius - length*2)*sinI
				p3 = QPointF(x3, y3)
				textValue = (i - start)/fullAngle*count*scale
				text = str(int(textValue))

				textRect = estimateTextSize(self.tickFont, text)
				textRect.moveCenter(p3)
				paint.drawText(textRect, Qt.AlignCenter, text)

		# Draw first and last marker
		drawTick(start, majorTicksPath, majorLength, majorOffset, True)
		drawTick(start + count*majorSpacing, majorTicksPath, majorLength, majorOffset, True)

		i = start + count*majorSpacing
		paint.setPen(majorPen)
		paint.drawPath(majorTicksPath)
		paint.setPen(minorPen)
		paint.drawPath(minorTicksPath)
		paint.setPen(microPen)
		paint.drawPath(microTicksPath)

		# Draw Needle

		# Rotate drawing angle
		paint.translate(cx, cy)
		value = self.value - self._range.min
		print(f' {value}')
		if value >= 0:
			rotation = value/count/scale*fullAngle + self.startAngle
		else:
			rotation = self.startAngle
		paint.rotate(rotation)
		paint.translate(-cx, -cy)

		middle = QPointF(cx, cy - radius)
		left = QPointF(cx - needleWidth/2, cy)
		right = QPointF(cx + needleWidth/2, cy)
		arcRect = QRectF(left, QSizeF(needleWidth, needleWidth))

		needlePath = QPainterPath()
		needlePath.moveTo(right)
		needlePath.lineTo(middle)
		needlePath.lineTo(left)
		needlePath.arcTo(arcRect, -180, 180)
		needlePath.closeSubpath()

		paint.setPen(needlePen)
		paint.setBrush(brush)
		paint.drawPath(needlePath)
		paint.translate(cx, cy)
		paint.rotate(-rotation)

		paint.end()

	@property
	def duration(self):
		return self._needleAnimation.duration()

	@duration.setter
	def duration(self, value):
		self._needleAnimation.setDuration(value)

	@property
	def easing(self):
		return self._needleAnimation.getEasingCurve()

	@easing.setter
	def easing(self, value: QEasingCurve):
		if isinstance(QEasingCurve, value):
			self._needleAnimation.setEasingCurve(value)
		else:
			print('Not a valid easing curve')


class AirPressureGauge(Gauge):

	def __init__(self, parent, pressureType: Union[str, Measurement, None] = None):
		if pressureType is not None:
			self.range = self.getRange(pressureType)
		super(AirPressureGauge, self).__init__(parent)

	def getRange(self, value):
		toTry = []
		if isinstance(value, str):
			toTry.append(value)
		elif isinstance(value, Measurement):
			toTry.extend([value.unit.lower(), value.localize.unit.lower()])
		for attempt in toTry:
			try:
				return self.ranges[attempt]
			except KeyError:
				pass
		else:
			return self.ranges['mbar']

	def _setUnit(self, value):
		if isinstance(value, Measurement):
			self.range = self.getRange(value)
		super(AirPressureGauge, self)._setUnit(value)
		self.update()


class ConfigWindow(QWidget):
	types = {'checkbox': QCheckBox}

	def __init__(self, parent):
		super(ConfigWindow, self).__init__(parent)
		self.resize(300, 300)
		self.verticalLayout = QVBoxLayout(self)
		self.formLayout = QFormLayout(self)
		self.verticalLayout.addLayout(self.formLayout)
		self.build()
		self.show()

	def build(self):
		parent = self.parent()
		cnf = [
			{
				'label': 'Show Labels',
				'type':  'checkbox',
				'slot':  'showLabels'
			},
			{
				'label': 'Show Arc',
				'type':  'checkbox',
				'slot':  'showArc'
			}
		]

		for item in cnf:
			self.addItem(item)

	def addItem(self, item: dict):
		label = QLabel(self, text=item['label'])
		value: QCheckBox = self.types[item['type']]()
		index = self.formLayout.count()
		self.formLayout.setWidget(index, QFormLayout.LabelRole, label)
		self.formLayout.setWidget(index, QFormLayout.FieldRole, value)
		value.stateChanged.connect(getattr(self.parent(), item['slot']))


class WindVein(Gauge):
	__value: float = 0.0
	_needleAnimation: QPropertyAnimation
	valueChanged = Signal(float)

	startAngle = 0
	endAngle = 360
	microDivisions = Divisions(count=5, length=0.04, lineWidth=0.2)
	minorDivisions = Divisions(count=2, length=0.075, lineWidth=0.4, subdivison=microDivisions)
	majorDivisions = Divisions(count=8, length=0.1, lineWidth=0.6, subdivison=minorDivisions)
	needleLength = 1.0
	needleWidth = 0.1
	_range = MinMax(0, 360)
	_valueClass: type = Direction
	_unit = None
	rotatedLabels = False

	def __init__(self, *args, **kwargs):
		self._cache = []
		super(Gauge, self).__init__(*args, **kwargs)
		# config = ConfigWindow(self)
		self.setAcceptDrops(False)
		self._direction = 0.0
		self.setRenderHint(QPainter.HighQualityAntialiasing)
		self._scene = QGraphicsScene()
		self._pen = QPen(self.defaultColor)
		self.setAttribute(Qt.WA_TranslucentBackground)
		# self.setStyleSheet('background-color: black; color: white')

		self.setScene(self._scene)
		# self.scene().setStyleSheet('background - color: black; color: white')

		self.scene().addItem(self.image)
		self.image.setFlag(QGraphicsItem.ItemIsMovable, False)
		self.image.removeFromGroup(self.speedLabel)
		self.directionLabel = CustomText(self)
		self.directionLabel.moveBy(0, -10)
		self.scene().addItem(self.directionLabel)

		self.directionAnimation = QPropertyAnimation(self, b'direction')
		self.directionAnimation.setDuration(1000)
		self.directionAnimation.setEasingCurve(QEasingCurve.InOutQuad)
		self.directionAnimation.setStartValue(0)
		self.directionAnimation.setEndValue(360)

	# self._needleAnimation = NeedleAnimation(self, b'_value')

	@Property(float)
	def direction(self):
		return self._direction

	@direction.setter
	def direction(self, value):
		self._direction = value
		self.needle.setRotation(value)

	@Slot(float)
	def setDirection(self, value):
		self.needle.setRotation(value)

	# print('setDirection', value, self._direction)
	# self.directionAnimation.setStartValue(self._direction)
	# self.directionAnimation.setEndValue(value)
	# self.directionAnimation.start()

	def wheelEvent(self, event):
		if event.angleDelta().y() > 0:
			self.speedLabel.fontScale *= 1.05
			self.speedLabel.update()
		else:
			self.speedLabel.fontScale *= 0.95
			self.speedLabel.update()

	def resizeEvent(self, event):
		while self._cache:
			delattr(self, self._cache.pop())

		rect: QRectF = self.needle.boundingRect()
		offset = (self.rect().center().y() - rect.center().y())
		# rect.moveCenter(QPointF(self.rect().center().x(), self.rect().center().y() - offset))
		# self.speedLabel.resize()
		# rect.translate(0, -offset)
		n = self.needle
		s = self.speedLabel
		# s.setPos(0, 0)
		# self.scene().setSceneRect(rect)
		# if self.isVisible() and sum(n.boundingRect().size().toTuple()):
		# 	while not s.collidesWithItem(self.safeSpace) and s.y() < self.radius:
		# 		ps = s.pos()
		# 		p = QPointF(s.pos().x(), s.pos().y() + s.boundingRect().height() / 4)
		# 		s.setPos(p)
		self.scene().setSceneRect(rect)
		self.pen.setWidthF(self.baseWidth)
		self.update()
		super(Gauge, self).resizeEvent(event)

	@cached_property
	def image(self) -> QGraphicsItemGroup:
		self.items()
		group = QGraphicsItemGroup()
		self.arc = GaugeArc(self)
		# self.ticks = TickGroup(self, self.majorDivisions)
		# self.labels = GaugeTickTextGroup(self.ticks)
		self.needle = Arrow(self)
		self.needle.setFlag(QGraphicsItem.ItemIsMovable, True)
		path = QPainterPath()
		path.addEllipse(QPoint(0, 0), self.radius - 10, self.radius - 10)
		# self.unitLabel = GaugeUnit(self)
		# self.valueLabel = CustomText(self)
		self.speedLabel = CustomText(self)
		# group.addToGroup(self.arc)
		# group.addToGroup(self.ticks)
		# group.addToGroup(self.labels)
		# group.addToGroup(self.unitLabel)
		# group.addToGroup(self.valueLabel)
		group.addToGroup(self.needle)
		# group.addToGroup(self.valueLabel)
		group.addToGroup(self.speedLabel)
		return group

	@property
	def safeZone(self):
		return self.needle.safeZone

	@Slot(float)
	def updateSlot(self, value: float):
		self.speedLabel.text = str(value.withoutUnit)
