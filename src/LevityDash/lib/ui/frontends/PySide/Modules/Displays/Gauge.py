from dataclasses import dataclass
from functools import cached_property, lru_cache
from typing import Optional, Type, Union, Tuple

from PySide6 import QtCore
from PySide6.QtCore import (
	QEasingCurve, QPoint, QPointF, QPropertyAnimation,
	QRectF, QSizeF, Qt, QTimer, Signal, Slot
)
from PySide6.QtGui import (
	QBrush, QFont, QFontMetrics, QFontMetricsF, QPainter, QPainterPath,
	QPen, QPolygonF
)
from PySide6.QtWidgets import (
	QGraphicsItem, QGraphicsPathItem,
	QGraphicsScene, QGraphicsSceneMouseEvent, QGraphicsTextItem, QStyleOptionGraphicsItem,
	QWidget
)
from math import isinf, floor
from numpy import ceil, cos, pi, radians, sin, sqrt

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.stateful import Stateful, StateProperty
from LevityDash.lib.ui import UILogger, Color
from LevityDash.lib.ui.frontends.PySide.Modules.Displays import SurfaceCentered, Surface
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.DisplayBase import Display
from LevityDash.lib.ui.frontends.PySide.utils import DisplayType, addCrosshair, DebugPaint, modifyTransformValues
from LevityDash.lib.utils.data import MinMax
from LevityDash.lib.utils.shared import half, Numeric, radialPoint, defer, factors, is_prime
from WeatherUnits import Measurement, Direction, Angle, Wind, Humidity, auto as auto_wu

log = UILogger.getChild('Gauge')


@lru_cache(maxsize=2048)
def generate_ticks(
	lower: int,
	upper: int,
	min_ticks: int = 2,
	max_ticks: int = 12,
	min_interval: int = 1,
	max_interval: int = 12,
	require_interval_factors: set[int] = None,
	exclude_interval_factors: set[int] = None,
) -> Tuple[int, int, list[int]]:
	"""

	This function is used to generate a list of tick marks for a gauge.

	:param lower:int: Set the lower bound of the range
	:param upper:int: Specify the upper bound of the range
	:param min_ticks:int=2: Set the minimum number of ticks that will be shown on the axis
	:param max_ticks:int=10: Set the maximum number of ticks that will be generated
	:param min_interval:int=1: Set the minimum interval between ticks
	:param max_interval:int=10: Specify the maximum interval between tick marks
	:param require_interval_factors:set[int]=None: Specify that the tick interval must have a factor in this set
	:param exclude_interval_factors:set[int]=None: Exclude certain factors from being used as tick intervals

	:param : Determine the number of ticks to generate
	:return: A tuple containing the tick interval, number of ticks, and a list of tick values
	:rtype: tuple[int, int, list[int]]
	"""
	lower = int(lower)
	upper = int(upper)

	require_interval_factors = require_interval_factors or set()
	exclude_interval_factors = exclude_interval_factors or set()

	range_size = abs(upper - lower)

	tick_interval = max(min_interval, 1)

	if is_prime(range_size):
		range_size += 1

	num_ticks = int(ceil(range_size / tick_interval))

	range_factors = sorted(factors(range_size) - {1, range_size} - exclude_interval_factors)

	while num_ticks >= max_ticks and range_factors:
		next_factor = range_factors.pop(0)

		if next_factor > max_interval:
			break

		if require_interval_factors and not factors(next_factor) & require_interval_factors:
			continue

		tick_interval = next_factor
		num_ticks = int(ceil(range_size / tick_interval))

	return tick_interval, num_ticks, [i for i in range(lower, upper + tick_interval, tick_interval)]


@dataclass
class Divisions:
	"""
	Divisions for a gauge.
	"""

	#: The number of divisions.
	_count: int = None
	#: The length of each tick.
	length: float = 1.0
	#: The line width of each tick.
	lineWidth: float = 1.0
	#: Sub-divisions for this division (if any).
	sub_division: 'Divisions' = None
	#: The super division for this division (if any).
	super_division: 'Divisions' = None
	#: The gauge the divisions belong to.
	gauge: 'Gauge' = None
	#: The minimum number of divisions.
	min_count: int = 3
	#: The maximum number of divisions.
	max_count: int = 10

	def __post_init__(self):
		if (sub_divisions := self.sub_division) is not None:
			sub_divisions.super_division = self

	@property
	def spacing(self):
		return self.angle_range / self.count

	@property
	def angle_range(self) -> float:
		if self.super_division is None:
			return self.gauge.fullAngle
		else:
			return self.super_division.angle_range / self.super_division.count

	@property
	def count(self):
		if (count := self._count) is None:
			_, count, _ = generate_ticks(
				self.gauge.range.rounded_min,
				self.gauge.range.rounded_max,
				self.min_count,
				self.max_count
			)
		return count

	@count.setter
	def count(self, value: int | None):
		self._count = value

	@property
	def interval(self) -> int:
		return generate_ticks(
			self.gauge.range.rounded_min,
			self.gauge.range.rounded_max,
			self.min_count, self.max_count
		)[1]

	@property
	def tick_values(self) -> list[int | float]:
		return generate_ticks(
			self.gauge.range.rounded_min,
			self.gauge.range.rounded_max,
			self.min_count, self.max_count
		)[2]

	@property
	def startAngle(self):
		return self.gauge.startAngle - 90


class GaugeItem:
	_gauge: 'Gauge'

	def __init__(self, gauge: 'Gauge'):
		self._gauge = gauge
		super(GaugeItem, self).__init__(gauge)

	@property
	def gauge(self) -> 'Gauge':
		return self._gauge

	def remove(self):
		self.gauge.scene().removeItem(self)


class GaugePathItem(GaugeItem, QGraphicsPathItem):
	_weight_scale: float = 1.0

	def __init__(self, *args, **kwargs):
		super(GaugePathItem, self).__init__(*args, **kwargs)
		self.setPen(self.gauge.pen)

	def refresh(self):
		pen = QPen(self.gauge.pen)
		pen.setWidthF(self.gauge.baseWidth * self._weight_scale)
		self.setPen(pen)


class GaugeArc(GaugePathItem):
	_weight_scale = 0.75
	_center_offset: QPointF = QPointF(0, 0)

	def __init__(self, *args, **kwargs):
		super(GaugeArc, self).__init__(*args, **kwargs)
		self.refresh()

	@property
	def center(self):
		return self.gauge.rect().center()

	@property
	def offset(self):
		return self.pen().widthF() / 4 * 360 / (2 * pi * self._gauge.radius) * 0.85

	@property
	def center_offset(self) -> QPointF:
		return self._center_offset

	@property
	def startAngle(self) -> float:
		return self.gauge.startAngle + self.offset

	@property
	def endAngle(self):
		return self.gauge.endAngle - self.offset

	@property
	def fullAngle(self) -> float:
		return self.endAngle - self.startAngle

	@property
	def centered_gauge_rect(self):
		rect = QRectF(self.gauge.gaugeRect)
		rect.moveCenter(QPoint(0, 0))
		return rect

	def makeShape(self):
		rect = self.centered_gauge_rect

		iShape = QRectF(rect)
		oShape = QRectF(rect)

		radius = self.gauge.radius

		small = radius * 1.95
		large = radius * 2.05

		iShape.setSize(QSizeF(small, small))
		oShape.setSize(QSizeF(large, large))

		path = QPainterPath()
		start_angle = self.startAngle
		path.arcMoveTo(iShape, -start_angle + 90)
		path.arcTo(iShape, -start_angle + 90, -self.fullAngle)
		path.arcMoveTo(oShape, -start_angle + 90)
		path.arcTo(oShape, -start_angle + 90, -self.fullAngle)
		path.closeSubpath()
		return path

	def draw(self):
		self._shape = self.makeShape()
		path = self.path()
		path.clear()
		rect = self.centered_gauge_rect
		path.arcMoveTo(rect, -self.startAngle + 90)
		path.arcTo(rect, -self.startAngle + 90, -self.fullAngle)
		self._center_offset = path.boundingRect().center()
		self.setPath(path)

	def refresh(self):
		super().refresh()
		self.draw()
		self.setPos(self.gauge.rect().center())

	def shape(self):
		return self._shape


@DebugPaint
class Tick(GaugePathItem):
	_index: float
	_center: QPointF
	_radius: float
	_properties: Divisions
	_offsetAngle: float
	_label: 'GaugeTickText' = None
	startPoint: QPointF
	endPoint: QPointF

	@cached_property
	def _sub_ticks(self) -> list['SubTick']:
		return []

	def __init__(self, gauge: 'Gauge', surface: 'TickSurface', index: float):
		self._index = index
		super(Tick, self).__init__(gauge)
		self.setParentItem(surface)

		pen = QPen(self.gauge.pen.color())
		pen.setCapStyle(Qt.RoundCap)
		self.setPen(pen)
		self.rebuild()
		self.setAcceptedMouseButtons(Qt.LeftButton)

	def _debug_paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget):
		super().paint(painter, option, widget)
		zero = QPoint(0, 0)
		addCrosshair(painter, pos=zero, color=self._debug_paint_color)

	def remove(self):
		for subtick in self._sub_ticks:
			subtick.remove()
		self._sub_ticks.clear()
		if self.label is not None:
			self.label.remove()
		super(Tick, self).remove()

	def mousePressEvent(self, event):
		event.accept()
		print(event)

	def mouseMoveEvent(self, event):
		print(event.pos())

	def refresh(self, recursive=True):
		pen = self.pen()
		pen.setWidthF(self.properties.lineWidth * self.gauge.baseWidth)
		self.setPen(pen)
		self.draw()
		if recursive:
			for sub_tick in self._sub_ticks:
				sub_tick.refresh()

	def rebuild(self):
		self.refresh(False)
		self.rebuild_sub_ticks()

	def rebuild_sub_ticks(self):

		tick_count = self.sub_tick_count
		existing = self._sub_ticks[:]

		if tick_count == 0:
			return

		self._sub_ticks.clear()

		for i in range(self.sub_tick_count):
			if existing:
				sub_tick = existing.pop(0)
				sub_tick.rebuild()
			else:
				sub_tick = SubTick(self, i)
			self._sub_ticks.append(sub_tick)

		for sub_tick in existing:
			sub_tick.remove()

	@property
	def angle(self):
		return self.properties.startAngle + self._index * self.properties.spacing

	@property
	def index(self):
		return self._index

	@index.setter
	def index(self, value):
		self._index = value
		self.refresh()

	@property
	def sub_tick_spacing(self) -> float:
		return self.properties.sub_division.spacing

	@property
	def sub_tick_count(self):

		# Prevent the last tick from having sub ticks
		if self._index == self.properties.count:
			# But only if there is no super tick
			if self.properties.super_division is None:
				return 0

		try:
			return self.properties.sub_division.count
		except AttributeError:
			return 0

	@property
	def radius(self):
		return self.gauge.radius

	@property
	def properties(self):
		return self.gauge.majorDivisions

	def draw(self):
		path = QPainterPath()
		angle = radians(self.angle)
		cosI, sinI = cos(angle), sin(angle)
		center = QPointF(0, 0)
		cx = center.x()
		cy = center.y()
		radius = self.radius
		length = self.properties.length * radius

		x1 = cx + radius * cosI
		y1 = cy + radius * sinI
		x2 = cx + (radius - length) * cosI
		y2 = cy + (radius - length) * sinI
		p1 = QPointF(x1, y1)
		self.startPoint = p1
		p2 = QPointF(x2, y2)
		self.endPoint = p2
		path.moveTo(p1)
		path.lineTo(p2)
		self.setPath(path)

	def setLabel(self, label: 'GaugeTickText'):
		self._label = label

	@property
	def label(self) -> 'GaugeTickText':
		return self._label

	@label.setter
	def label(self, label: 'GaugeTickText'):
		self._label = label


class SubTick(Tick):
	_superTick: Tick

	def __init__(self, superTick: Tick, index: float):
		self._superTick = superTick
		super(SubTick, self).__init__(superTick.gauge, superTick.parentItem(), index)

	@property
	def properties(self):
		return self._superTick.properties.sub_division

	@property
	def angle(self):
		return self._superTick.angle + self._index * self.properties.spacing


class TickSurface(SurfaceCentered, GaugeItem):
	_properties: Divisions
	_ticks: list[Tick] = cached_property(lambda self: [])

	def __init__(self, gauge: 'Gauge', properties: Divisions):
		self._gauge = gauge
		self._properties = properties
		self.scale = 1
		super(TickSurface, self).__init__(gauge)
		self.rebuild()

	def refresh(self):
		self.setPos(self.gauge.rect().center())
		for tick in self.childItems():
			try:
				tick.refresh()
			except AttributeError:
				pass

	def rebuild(self):
		tick_count = self.count
		existing = self._ticks[:]

		if tick_count == 1:
			return

		self._ticks.clear()

		for i in range(self.count + 1):
			if existing:
				tick = existing.pop(0)
				tick.rebuild()
			else:
				tick = Tick(self.gauge, self, i)
			self._ticks.append(tick)

		try:
			for sub_tick in self._ticks[-1]._sub_ticks:
				sub_tick.remove()
		except AttributeError:
			pass
		except IndexError:
			pass

		for tick in existing:
			tick.remove()

	@property
	def ticks(self) -> list[Tick]:
		return self._ticks

	@property
	def gauge(self) -> 'Gauge':
		return self._gauge

	@property
	def spacing(self) -> float:
		return self._properties.spacing

	@property
	def count(self) -> int:
		return self._properties.count


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
		self.refresh()

	@property
	def needleWidth(self) -> float:
		return self.gauge.needleWidth * self.gauge.radius

	@property
	def needleLength(self) -> float:
		return self.gauge.needleLength * self.gauge.radius

	@property
	def needleSize(self) -> QSizeF:
		return QSizeF(self.needleWidth, self.needleLength)

	def draw(self):
		cx = 0
		cy = 0
		middle = QPointF(cx, cy - self.needleLength)
		needleWidth = self.needleWidth
		left = QPointF(cx - needleWidth / 2, cy)
		right = QPointF(cx + needleWidth / 2, cy)
		arcStart = QPointF(left)
		arcStart.setY(left.y() + needleWidth * 0.6)
		arcEnd = QPointF(right)
		arcEnd.setY(right.y() + needleWidth * 0.6)
		arcRect = QRectF(arcStart, QSizeF(needleWidth, -needleWidth))

		needlePath = QPainterPath()
		needlePath.arcMoveTo(arcRect, 0)
		needlePath.lineTo(middle)
		needlePath.arcTo(arcRect, 180, -180)
		self.setPath(needlePath.simplified())

	def refresh(self):
		self.setBrush(QBrush(self.gauge.defaultColor))
		self.draw()
		self.setPos(self.gauge.arc.center)


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
		path.addEllipse(QPoint(0, 0), radius * 0.6, radius * 0.6)
		return path

	# super(Arrow, self).paint(painter, option, widget)

	def draw(self):
		# center = self._gauge.arc.center
		cx = 0
		cy = 0

		# Draw Circle
		radius = self.gauge.radius
		pointerHeight = radius * 0.178
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
		path.addEllipse(QPoint(0, 0), radius * 0.8, radius * 0.8)
		path.setFillRule(Qt.FillRule.OddEvenFill)

		self.setPath(path)


class GaugeText(GaugeItem, QGraphicsTextItem):
	def __init__(self, *args, **kwargs):
		super(GaugeText, self).__init__(*args, **kwargs)
		self.setFont(self.gauge.tickFont)
		self.setDefaultTextColor(self.gauge.defaultColor)


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
		font.setPixelSize(self.gauge.radius * 0.2)
		self.setFont(font)
		self.setHtml(self.string)
		textRect = self.boundingRect()
		textRect.moveCenter(radialPoint(self.gauge.arc.center, self.gauge.radius * 0.35, self.gauge.startAngle + 90 + (self.gauge.fullAngle / 2)))
		# textRect.translate(-textRect.width() / 2, 0)
		self.setPos(textRect.topLeft())

	def update(self):
		self.draw()
		super(GaugeValueText, self).update()


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
		self._font = self.gauge.tickFont
		# self.animationBridge = AnimationBridge(self)

		self.animationTimer = QTimer()
		self.animationTimer.timeout.connect(self.grav)
		self.animationTimer.setInterval(20)

		self.animationTimer.start()

	# fm = QFontMetrics(self.font())
	# fm.tightBoundingRect(self.text)

	def updateFontSize(self):
		self.textWidthRatio = self.fontMetrics.width(self.text) / 100
		self._maxFontSize = min(font.pointSizeF() * self._ratio, self.height() * .7)

	def widthForHeight(self, height: float):
		return self.text

	@property
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

		nudge = (self.mapToScene(self.boundingRect().center()) - self.boundingRect().center()) * .03
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
		return max(self.gauge.radius * self.fontScale, 10)

	def update(self):
		tightRect = self.fontMetrics.tightBoundingRect(self.string)
		wid = self.fontMetrics.width(self.string)
		tightRect.moveCenter(self.gauge.arc.center.toPoint())

		path = QPainterPath()
		p = self.gauge.arc.center.toPoint()
		# p = QPointF(0,0)
		# p.setX(p.x() - tightRect.width() / 2)
		# p.setY(p.y() + tightRect.height() / 2)
		path.addText(0 - tightRect.width() * 1.05 / 2, tightRect.height() / 2, self.dynamicFont, self.string)
		# path.moveTo(p)

		self.setPath(path)
		t = QPointF(*half(tightRect.size()).toTuple())
		self.setTransformOriginPoint(tightRect.center())
		# t.setY(t.y() * -1)
		self.setTransformOriginPoint(t)
		# self.setPos(p)

		# self.setRotation(45)
		super(CustomText, self).update()


class GaugeUnit(GaugeText):

	def __init__(self, *args, **kwargs):
		super(GaugeText, self).__init__(*args, **kwargs)
		self.draw()

	@property
	def string(self):
		return str(self.gauge.unit)

	def draw(self):
		font = self.gauge.tickFont
		font.setPixelSize(self.gauge.radius * 0.3)
		self.setFont(font)
		self.setHtml(self.string)
		textRect = self.boundingRect()
		textRect.moveCenter(radialPoint(self.gauge.arc.center, self.gauge.radius * 0.35, self.gauge.startAngle - 90 + (self.gauge.fullAngle / 2)))
		self.setPos(textRect.topLeft())

	def update(self):
		self.draw()
		self.setVisible(self.gauge.unit is not None)
		super(GaugeUnit, self).update()


class GaugeTickText(GaugeText):
	_rotated: bool = True
	_flipUpsideDown = (False, True)
	_scale: Optional[float] = None

	def __init__(self, gauge, tick, group, *args, **kwargs):
		self.group = group
		self.offset = 0.75
		self.tick = tick
		super(GaugeTickText, self).__init__(gauge, *args, **kwargs)
		font = QFont()
		font.setPointSizeF(70)
		self.setFont(font)
		self.rect = QGraphicsPathItem()

	@property
	def ax(self):
		return self.tick.radius * 0.35

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
		self.setTransformOriginPoint(0 + textRect.width() / 2, textRect.height() / 2)
		self.setPos(textRect.topLeft())

	# collides = collidingNeighbors(self)

	def collidingNeighbors(self):
		v = [x for x in self.collidingItems(Qt.ItemSelectionMode.IntersectsItemShape) if isinstance(x, self.__class__)]
		return v

	def position(self):
		return radialPoint(self.gauge.arc.center, self.tick.radius * self.offset, self.tick.angle)

	# def shape(self):
	# 	return self.mapToScene(super(GaugeTickText, self).shape())

	@property
	def angleValue(self):
		return self.tick.angle - self.gauge.startAngle + 90

	@property
	def string(self):
		range_range = self.gauge.range.rounded_range
		value = float(range_range) / self.gauge.fullAngle * self.angleValue + float(self.gauge.range.rounded_min)
		valueClass = self.gauge.valueClass
		if valueClass is float:
			if value.is_integer():
				value = int(value)
		else:
			if isinstance(valueClass, tuple):
				value = valueClass[0](valueClass[1](value), valueClass[2](1))
			else:
				value = valueClass(value)
				if issubclass(valueClass, Direction):
					return value.cardinal.twoLetter
			if isinstance(value, Measurement):
				value = value.withoutUnit
		return str(value)

	def draw(self):
		# font = self.font()
		# font.setPointSizeF(self.tick.radius * 0.15)
		# self.setFont(font)
		self.setPlainText(self.string)
		textRect = self.boundingRect()

		textRect.moveCenter(self.position())
		self.setTransformOriginPoint(0 + textRect.width() / 2, textRect.height() / 2)
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
			font.setPointSizeF(max(self.ax * self.group.tickScale, 10))
			self.setFont(font)
		self.draw()
		if self.rotated:
			angle = self.tick.angle + 90
			if (-90 > angle and self._flipUpsideDown[0]) or (angle > 90 and self._flipUpsideDown[1]):
				angle -= 180
			self.setRotation(angle)

	@property
	def rotated(self):
		return self.parentItem().rotation


class GaugeTickTextGroup(Surface, GaugeItem, Stateful):
	tickScale = 1.0

	@property
	def rotation(self):
		return False

	def __init__(self, gauge, ticks: TickSurface):
		self._gauge = gauge
		self._ticks = ticks
		super(GaugeTickTextGroup, self).__init__(gauge)
		self.build()
		self.setTickScale()

	@property
	def gauge(self) -> 'Gauge':
		return self._gauge

	@property
	def unlabeled_ticks(self) -> list[Tick]:
		return [i for i in self._ticks.childItems() if type(i) is Tick and i.label is None]

	def build(self):
		tick_list = self.unlabeled_ticks
		while tick_list:
			tick = tick_list.pop()
			tick.label = GaugeTickText(self.gauge, tick, self)
			self.addToGroup(tick.label)

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

	def rebuild(self):
		self.setPos(0, 0)
		self.build()
		if self.hasCollisions():
			self.setTickScale()
		font = self.gauge.tickFont
		font.setPointSizeF(min([i.font().pointSizeF() for i in self.childItems()], default=16))
		for item in self.childItems():
			item.setFont(font)
			item.draw()

	def collidesWithTicks(self) -> bool:
		return any([item.collidesWithItem(item.tick) for item in self.childItems() if isinstance(item, GaugeTickText)])

	def hasCollisions(self):
		# collidesWitTicks = self.collidesWithTicks()
		# if collidesWitTicks:
		# 	return True
		for item in self.childItems():
			if isinstance(item, GaugeTickText) and item.collidingNeighbors():
				return True
		return False

	@property
	def ticks(self):
		if self._ticks.gauge.fullAngle >= 360:
			return [i for i in self._ticks.ticks if i.angle + 90 != 360]
		return self._ticks.ticks

	def refresh(self):
		self.setPos(self.gauge.arc.center)


def decode_measurement(self, value: str | int | float) -> Measurement:
	_type = getattr(self, 'valueClass', Measurement)
	match value:
		case str(v):
			value = auto_wu(v)
		case int(v) | float(v):
			value = _type(v)
		case _:
			raise TypeError(f'Invalid type for min: {type(value)}')
	return value


class Gauge(Display):
	__value: float = 0.0
	_needleAnimation: QPropertyAnimation
	valueChanged = Signal(float)

	class GaugeRange(Stateful):
		_min: Measurement
		_max: Measurement
		_round_to: int | float = 1
		valueClass: Type[Measurement]

		ranges = {
			'inhg': MinMax(27, 31),
			'mmhg': MinMax(730, 790),
			'mbar': MinMax(970, 1060),
			'f': MinMax(0, 120),
			'c': MinMax(-20, 50),
			'mph': MinMax(0, 15),
			'in/hr': MinMax(0, 3),
			'mm/hr': MinMax(0, 75),
			'v': MinMax(2.5, 3.3),
			'default': MinMax(0, 120),
			'lux': MinMax(0, 100000),
			'angle': MinMax(0, 360),
			'percentage': MinMax(0, 1),

			CategoryItem('*.humidity.*'):
				MinMax(
					Humidity(0),
					Humidity(1)
				),

			CategoryItem('environment.wind.speed'):
				MinMax(
					Wind.MetersPerSecond(0),
					Wind.MetersPerSecond(10)
				),

			CategoryItem('environment.wind.speed.gust'):
				MinMax(
					Wind.MetersPerSecond(0),
					Wind.MetersPerSecond(35)
				),

		}

		def __init__(self, gauge: 'Gauge', **state):
			self._gauge = gauge
			self.state = self.prep_init(state)

		@StateProperty(key='round_to', default=1)
		def round_to(self) -> int | float:
			return self._round_to

		@round_to.setter
		def round_to(self, value: int | float):
			self._round_to = value

		@StateProperty(key='min')
		def min(self) -> Measurement:
			return self._min

		@min.setter
		def min(self, value: Measurement):
			self._min = value

		min.decode(decode_measurement)

		@min.factory
		def min(self) -> Measurement:
			_type = self._gauge.valueClass
			try:
				limits_min = _type(self.default_range.min)
			except AttributeError:
				limits_min = 0
			if isinf(limits_min):
				limits_min = 0
			return _type(limits_min)

		@min.condition(method='get')
		def min(self, value: Measurement):
			return value != type(value).typedLimits.min

		@property
		def rounded_min(self) -> Measurement:
			round_to = self.round_to
			if not round_to:
				return self.min
			return self._gauge.valueClass(floor(float(self.min) / round_to) * round_to)

		@StateProperty(key='max')
		def max(self) -> Measurement:
			return self._max

		@max.setter
		def max(self, value: Measurement):
			self._max = value

		max.decode(decode_measurement)

		@max.factory
		def max(self) -> Measurement:
			_type = self._gauge.valueClass
			try:
				limits_max = _type(self.default_range.max)
			except AttributeError:
				limits_max = 100
			if isinf(limits_max):
				limits_max = 100
			return _type(limits_max)

		@max.condition(method='get')
		def max(self, value: Measurement):
			return value != type(value).typedLimits.max

		@property
		def _rounded_max(self) -> Measurement:
			round_to = self.round_to
			if not round_to:
				return self.max
			return self._gauge.valueClass(ceil(float(self.max) / round_to) * round_to)

		@property
		def rounded_max(self):
			if is_prime(self._rounded_range):
				return self._rounded_max + 1
			return self._rounded_max

		@property
		def range(self) -> Measurement:
			return abs(self.max - self.min)

		@range.setter
		def range(self, value: MinMax):
			self.min, self.max = value

		@property
		def rounded_range(self) -> Measurement:
			return abs(self.rounded_max - self.rounded_min)

		@property
		def _rounded_range(self) -> Measurement:
			return abs(self._rounded_max - self.rounded_min)

		@property
		def default_range(self) -> MinMax:
			_type = self._gauge.valueClass

			try:
				similar_keys = [
					i for i in self.ranges
					if not isinstance(i, str)
						 and self._gauge.parent.key < i
				]
				similar_keys.sort(key=lambda i: len(i), reverse=True)
				for key in similar_keys:
					try:
						return self.ranges[key]
					except KeyError:
						pass
			except AttributeError:
				pass

			try:
				if (preset_range := self.ranges.get(_type.unit.lower(), None)) is not None:
					return preset_range
			except AttributeError:
				pass

			try:
				return MinMax(_type.typedLimits.min, _type.typedLimits.max)
			except AttributeError:
				pass

			return MinMax(0, 100)

	startAngle = -120
	endAngle = 120
	microDivisions: Divisions
	minorDivisions: Divisions
	majorDivisions: Divisions
	needleLength = 1.0
	needleWidth = 0.1
	_valueClass: type = float
	_unit: Optional[str] = None
	_scene: QGraphicsScene
	_pen: QPen
	_cache: list

	def _init_defaults_(self):

		self.majorDivisions = Divisions(
			gauge=self,
			length=0.1,
			lineWidth=0.6,
			sub_division=(minor := Divisions(
				gauge=self,
				_count=2,
				length=0.075,
				lineWidth=0.4,
				sub_division=(micro := Divisions(
					gauge=self,
					_count=5,
					length=0.04,
					lineWidth=0.2
				))
			))
		)
		self.minorDivisions = minor
		self.microDivisions = micro
		self._valueClass = self.parent.container.value_type
		super()._init_defaults_()
		# config = ConfigWindow(self)
		self.__value: Union[Numeric, Measurement]
		self._pen = QPen(self.defaultColor)

		self.arc = GaugeArc(self)
		self.recenter()
		self.ticks = TickSurface(self, self.majorDivisions)
		self.labels = GaugeTickTextGroup(self, self.ticks)
		self.needle = Needle(self)
		self.unitLabel = GaugeUnit(self)
		self.valueLabel = GaugeValueText(self)

	@property
	def type(self):
		return DisplayType.Gauge

	@property
	def displayType(self):
		return DisplayType.Gauge

	def __init__(self, parent, *args, **kwargs):
		self.previousParent = None
		super(Gauge, self).__init__(parent)

	def _afterSetState(self):
		super()._afterSetState()
		self.arc.refresh()

		self.rebuild()

		self.needle.refresh()
		self.unitLabel.draw()

	def recenter(self):
		t = self.transform()
		offset = self.arc.center_offset
		modifyTransformValues(t, offset.x(), -offset.y())
		self.setTransform(t)

	@defer
	def rebuild(self):
		self.ticks.rebuild()
		self.labels.rebuild()
		self.unitLabel.draw()
		self.needle.refresh()
		self.recenter()

	def refresh(self):
		self.ticks.refresh()
		self.labels.refresh()
		self.unitLabel.draw()
		self.needle.refresh()

	def parentResized(self, arg: Union[QPointF, QSizeF, QRectF]):
		super().parentResized(arg)
		self.arc.refresh()
		self.ticks.refresh()
		self.labels.rebuild()
		self.needle.draw()
		self.unitLabel.draw()

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

	@property
	def _value(self):
		return self.__value

	@_value.setter
	def _value(self, value: float):
		value = max(self._range.rounded_min, min(self._range.max, value))
		self.__value = value
		angle = float(value - self._range.rounded_min) / self._range.rounded_range * self.fullAngle + self.startAngle
		self.needle.setRotation(angle)
		self.valueLabel.update()

	@property
	def valueClass(self):
		return self._valueClass

	@valueClass.setter
	def valueClass(self, value):
		if not isinstance(value, type):
			value = type(value)

		self._valueClass = value

		if issubclass(self._valueClass, Measurement):
			self.unit = value.unit

		self.rebuild()

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
		if value != self._unit:
			self._setUnit(value)
			self.unitLabel.update()
			self.rebuild()

	def _setUnit(self, value):
		if isinstance(value, Measurement):
			self._unit = value.unit
		elif isinstance(value, str):
			self._unit = value.strip()

	range: GaugeRange

	@StateProperty(key='range', link=GaugeRange, default=Stateful, allowNone=False)
	def range(self) -> GaugeRange:
		return self._range

	@range.setter
	def range(self, value: GaugeRange):
		self._range = value

	@range.factory
	def range(self):
		return Gauge.GaugeRange(self)

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

	@property
	def center(self) -> QPointF:
		return self.rect().center()

	@property
	def scene_center(self) -> QPointF:
		return self.mapToScene(self.center)

	@property
	def baseWidth(self):
		return sqrt(self.height() ** 2 + self.width() ** 2) * 0.008

	def height(self) -> float:
		return self.marginRect.height()

	def width(self) -> float:
		return self.marginRect.width()

	@property
	def radius(self):
		return min(self.height(), self.width()) / 2 - 10

	@property
	def gaugeRect(self) -> QRectF:
		f = QRectF(0.0, 0.0, self.radius * 2, self.radius * 2)
		f.moveCenter(self.rect().center())
		return f

	@property
	def fullAngle(self):
		return self.endAngle + -self.startAngle

	@property
	def defaultColor(self):
		# return Qt.white
		return Color.presets.white.QColor

	@property
	def tickFont(self):
		font = QFont()
		font.setPixelSize(max(self.radius * .1, 18))
		return font

	def setRect(self, *args, **kwargs):
		super().setRect(*args, **kwargs)
		self.refresh()

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
