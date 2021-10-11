from collections import deque
from dataclasses import dataclass
from functools import cached_property
from typing import Literal, Union

from numpy import cos, radians, sin, sqrt
from PySide2 import QtCore, QtWidgets

from PySide2.QtCore import Property, QEasingCurve, QLineF, QPoint, QPointF, QPropertyAnimation, QRect, QRectF, QSizeF, Qt, Signal, Slot
from PySide2.QtGui import QBrush, QColor, QDropEvent, QFont, QPainter, QPainterPath, QPaintEvent, QPen, QPolygonF, QResizeEvent
from PySide2.QtWidgets import QApplication, QWidget
from sympy.codegen.ast import float32
from WeatherUnits import Direction
from WeatherUnits.base import Measurement
from WeatherUnits.derived import Wind
from WeatherUnits.length import Meter, Mile
from WeatherUnits.others import Direction
from WeatherUnits.time.time import Second, Hour

from api import API
from fonts import rounded
from utils import estimateTextFontSize, estimateTextSize, MinMax, Numeric
from widgets.Complication import Complication, LocalComplication


@dataclass
class Divisions:
	"""
	Divisions for a gauge.
	"""

	#: The number of divisions.
	count: int
	#: The length of each tick.
	length: float
	#: The line width of each tick.
	lineWidth: float
	#: The color of the tick.
	color: QColor = None
	#: The Alpha level.
	alpha: float = 1.0


class Gauge(QtWidgets.QWidget):
	_value: Numeric = 10.0
	_animation: QPropertyAnimation
	direction: float = None
	valueChanged = Signal(float)
	startAngle = -120
	endAngle = 120
	majorDivisions = Divisions(count=10, length=0.1, lineWidth=0.6)
	minorDivisions = Divisions(count=2, length=0.05, lineWidth=0.4)
	microDivisions = Divisions(count=5, length=0.025, lineWidth=0.25)
	needleLength = 1.0
	needleWidth = 0.1
	range = MinMax(0, 100)
	_valueClass: type = float

	def __init__(self, *args, **kwargs):
		super(Gauge, self).__init__(*args, **kwargs)
		self._value: Union[Numeric, Measurement]
		self._animation = QPropertyAnimation(self, b'value')
		self._animation.setStartValue(0)
		self._animation.setEasingCurve(QEasingCurve.OutCubic)
		self._animation.setDuration(2000)

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

	def animateDirection(self, direction: Direction = None):
		if self._animation.state() == QtCore.QAbstractAnimation.Running:
			self._animation.stop()
		start = int(self.value)
		end = int(direction)
		if abs(end - start) > 180:
			start += 360
		self._animation.setStartValue(start)
		self._animation.setEndValue(end)
		self._animation.start()

	def resizeEvent(self, event):
		self.fontLarge = QFont(rounded)
		# self.fontLarge.setKerning(QFont.AbsoluteSpacing)
		self.fontLarge.setWeight(70)
		self.fontLarge.setPixelSize(self.radius * .6)
		if hasattr(self, 'gaugeRect'):
			delattr(self, 'gaugeRect')
		if hasattr(self, 'centerOffset'):
			delattr(self, 'centerOffset')
		super().resizeEvent(event)

	@property
	def radius(self):
		return min(self.height(), self.width()) * .4

	@cached_property
	def gaugeRect(self) -> QRectF:
		f = QRectF(0.0, 0.0, self.radius * 2, self.radius * 2)
		f.moveCenter(self.rect().center())
		return f

	@property
	def defaultColor(self):
		return self.palette().text().color()

	def paintEvent(self, event):
		paint = QPainter(self)
		paint.setRenderHint(QPainter.HighQualityAntialiasing)
		paint.setRenderHint(QPainter.Antialiasing)
		cx, cy = QPointF(self.rect().center()).toTuple()
		radius = self.radius
		needleLength = self.needleLength * radius
		needleWidth = self.needleWidth * radius

		penWidth = sqrt(self.height() ** 2 + self.width() ** 2) * 0.008
		brush = QBrush(self.defaultColor)
		paint.pen().setColor(self.defaultColor)

		fullAngle = self.endAngle + -self.startAngle

		# Gauge divisions setup
		major = self.majorDivisions
		minor = self.minorDivisions
		micro = self.microDivisions

		# Set spacing for divisions
		majorSpacing = fullAngle / major.count
		minorSpacing = majorSpacing / minor.count
		microSpacing = minorSpacing / micro.count

		start = self.startAngle - 90

		majorLength = major.length * radius
		minorLength = minor.length * radius
		microLength = micro.length * radius

		arcPen = QPen(self.defaultColor)
		arcPen.setWidthF(penWidth)
		arcPen.setCapStyle(Qt.FlatCap)
		print(penWidth)

		majorPen = QPen(self.defaultColor, major.lineWidth * penWidth)
		majorPen.setCapStyle(Qt.RoundCap)

		minorPen = QPen(self.defaultColor, minor.lineWidth * penWidth)
		minorPen.setCapStyle(Qt.RoundCap)

		microPen = QPen(self.defaultColor, micro.lineWidth * penWidth)
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

		# Draw starting marker
		i = start
		radI = radians(i)
		cosI, sinI = cos(radI), sin(radI)

		offset = penWidth / 2
		offset = offset - (major.lineWidth / 2 * penWidth)

		x1 = cx + radius * cosI + offset * cosI
		y1 = cy + radius * sinI + offset * sinI
		x2 = cx + radius * cosI - majorLength * cosI
		y2 = cy + radius * sinI - majorLength * sinI
		line = QLineF(x1, y1, x2, y2)
		paint.setPen(majorPen)
		paint.drawLine(line)

		# Draw gauge divisions
		for i in range(0, major.count):
			i = start + i * majorSpacing
			if i != start:
				radI = radians(i)
				cosI, sinI = cos(radI), sin(radI)
				x1 = cx + radius * cosI - major.lineWidth * penWidth * cosI
				y1 = cy + radius * sinI - major.lineWidth * penWidth * sinI
				x2 = cx + radius * cosI - majorLength * cosI
				y2 = cy + radius * sinI - majorLength * sinI
				line = QLineF(x1, y1, x2, y2)
				paint.setPen(majorPen)
				paint.drawLine(line)
			for j in range(0, minor.count):
				j = j * minorSpacing + i
				if j != i:
					radJ = radians(j)
					cosJ, sinJ = cos(radJ), sin(radJ)
					x1 = cx + radius * cosJ - minor.lineWidth * penWidth * cosJ
					y1 = cy + radius * sinJ - minor.lineWidth * penWidth * sinJ
					x2 = cx + radius * cosJ - minorLength * cosJ
					y2 = cy + radius * sinJ - minorLength * sinJ
					line = QLineF(x1, y1, x2, y2)
					paint.setPen(minorPen)
					paint.drawLine(line)

				for k in range(1, micro.count):
					k = k * microSpacing + j
					radK = radians(k)
					cosK, sinK = cos(radK), sin(radK)
					x1 = cx + radius * cosK - micro.lineWidth * penWidth * cosK
					y1 = cy + radius * sinK - micro.lineWidth * penWidth * sinK
					x2 = cx + radius * cosK - microLength * cosK
					y2 = cy + radius * sinK - microLength * sinK
					line = QLineF(x1, y1, x2, y2)
					paint.setPen(microPen)
					paint.drawLine(line)

		# Draw final gauge tick
		i = start + major.count * majorSpacing
		x1 = cx + radius * cos(radians(i)) + offset * cos(radians(i))
		y1 = cy + radius * sin(radians(i)) + offset * sin(radians(i))
		x2 = cx + radius * cos(radians(i)) - majorLength * cos(radians(i))
		y2 = cy + radius * sin(radians(i)) - majorLength * sin(radians(i))
		line = QLineF(x1, y1, x2, y2)
		paint.setPen(majorPen)
		paint.drawLine(line)

		# Draw Needle

		# Rotate drawing angle
		paint.translate(cx, cy)
		rotation = self._value / self.range.range * fullAngle + self.startAngle
		paint.rotate(rotation)
		paint.translate(-cx, -cy)

		middle = QPointF(cx, cy - radius)
		left = QPointF(cx - needleWidth / 2, cy)
		right = QPointF(cx + needleWidth / 2, cy)
		arcRect = QRectF(left, QSizeF(needleWidth, needleWidth))

		arcPath = QPainterPath()
		arcPath.moveTo(right)
		arcPath.lineTo(middle)
		arcPath.lineTo(left)
		arcPath.arcTo(arcRect, -180, 180)
		arcPath.closeSubpath()

		paint.setPen(needlePen)
		paint.setBrush(brush)
		paint.drawPath(arcPath)
		paint.translate(cx, cy)
		paint.rotate(-rotation)

		paint.end()

	def shrinkFont(self, text: str):
		font = QFont(self.fontLarge)
		x, y = estimateTextSize(font, text)
		radius = self.radius
		while x > radius * 0.5 * 2:
			size = font.pixelSize()
			if font.pixelSize() < 10:
				break
			font.setPixelSize(size - 3)
			x, y = estimateTextSize(font, text)
		return font

	@property
	def duration(self):
		return self._animation.duration()

	@duration.setter
	def duration(self, value):
		self._animation.setDuration(value)

	@property
	def easing(self):
		return self._animation.getEasingCurve()

	@easing.setter
	def easing(self, value: QEasingCurve):
		if isinstance(QEasingCurve, value):
			self._animation.setEasingCurve(value)
		else:
			print('Not a valid easing curve')

	def setValue(self, value: Union[Measurement, Numeric]):
		self._valueClass = value.__class__
		self.value = value

	@Property(float)
	def value(self) -> float:
		return float(self._value)

	@value.setter
	def value(self, value: float):
		if value != self._value:
			self._value = self._valueClass(value)
			self.update()
			self.valueChanged.emit(value)


@dataclass
class Subscription:
	key: str
	api: 'API'
	signal: Signal

	def __init__(self, key: str, api: 'API'):
		self.key = key
		self.api = api
		super(Subscription, self).__init__()


class GaugeSubmodule(QWidget):
	slots = ['centerGauge']

	_value: int = 0
	valueUpdateSignal = Signal(Measurement)

	speedState: dict = {'api': None, 'key': None}
	directionState: dict = {'api': None, 'key': None}

	def __init__(self, *args, state: dict = None, **kwargs):
		super().__init__(*args, **kwargs)
		if state is not None:
			self.valueState = state['value']
			if self.valueState is not None:
				self.parent().parent().parent().toolbox.toolboxes[self.speedState['api']].api.realtime.tryToSubscribe(self.valueState['key'], self.valueUpdateSignal)

		self.valueUpdateSignal.connect(self.setDirection)

		# add slider to layout
		# self.layout = QtWidgets.QVBoxLayout()
		# self.layout.addWidget(self.slider)
		# self.setLayout(self.layout)

		self.__init_ui__()

		self.topLeftRect = QRect(0, 0, 0, 0)
		self.topRightRect = QRect(0, 0, 0, 0)
		self.bottomLeftRect = QRect(0, 0, 0, 0)
		self.bottomRightRect = QRect(0, 0, 0, 0)

	def __init_ui__(self):
		font = QFont()
		font.setFamily(u"SF Pro Rounded")
		self.setFont(font)
		self.image = Gauge(self)

		self.topLeft = Complication(self)

		self.bottomLeft = Complication(self)

		self.topRight = Complication(self)

		self.bottomRight = Complication(self)

	def makeConfigWindow(self):
		# add slider to change number of majorTicks
		self.slider = QtWidgets.QSlider(Qt.Horizontal)
		self.slider.setMinimum(1)
		self.slider.setMaximum(20)
		self.slider.setValue(10)
		self.slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
		self.slider.setTickInterval(1)
		self.slider.setSingleStep(1)
		self.slider.setMinimumWidth(600)
		self.slider.setMaximumWidth(100)
		self.slider.setMinimumHeight(20)
		self.slider.setMaximumHeight(20)
		r = self.slider.rect()
		r.moveBottom(self.rect().bottom())
		self.slider.setGeometry(r)
		self.slider.show()

		# add slider to change number of minorTicks
		self.slider2 = QtWidgets.QSlider(Qt.Horizontal)
		self.slider2.setMinimum(0)
		self.slider2.setMaximum(4)
		self.slider2.setValue(1)
		self.slider2.setTickPosition(QtWidgets.QSlider.TicksBelow)
		self.slider2.setTickInterval(1)
		self.slider2.setSingleStep(1)
		self.slider2.setMinimumWidth(600)
		self.slider2.setMaximumWidth(100)
		self.slider2.setMinimumHeight(20)
		self.slider2.setMaximumHeight(20)
		r = self.slider2.rect()
		r.moveBottom(self.rect().bottom())
		self.slider2.setGeometry(r)
		self.slider2.show()

		# add slider to change number of microTicks
		self.slider3 = QtWidgets.QSlider(Qt.Horizontal)
		self.slider3.setMinimum(1)
		self.slider3.setMaximum(12)
		self.slider3.setValue(10)
		self.slider3.setTickPosition(QtWidgets.QSlider.TicksBelow)
		self.slider3.setTickInterval(1)
		self.slider3.setSingleStep(1)
		self.slider3.setMinimumWidth(600)
		self.slider3.setMaximumWidth(100)
		self.slider3.setMinimumHeight(20)
		self.slider3.setMaximumHeight(20)
		r = self.slider3.rect()
		r.moveBottom(self.rect().bottom())
		self.slider3.setGeometry(r)
		self.slider3.show()
		self.slider.valueChanged.connect(self.image.setMajorTicks)
		self.slider2.valueChanged.connect(self.image.setMinorTicks)
		self.slider3.valueChanged.connect(self.image.setMicroTicks)

	@property
	def state(self):
		return {'value':     self.speedState,
		        'direction': self.directionState}

	def resizeEvent(self, event: QResizeEvent) -> None:
		self.image.setGeometry(self.rect())
		width = int(self.width() / 4)
		height = int(self.height() / 4)
		rect = QRect(0, 0, width, height)

		rect.moveTopRight(self.rect().topRight())
		self.topRight.setGeometry(rect)

		rect.moveTopLeft(self.rect().topLeft())
		self.topLeft.setGeometry(rect)

		rect.moveBottomLeft(self.rect().bottomLeft())
		self.bottomLeft.setGeometry(rect)

		rect.moveBottomRight(self.rect().bottomRight())
		self.bottomRight.setGeometry(rect)

	# @Property(float)
	@property
	def speed(self):
		return self.image.speed

	@speed.setter
	def speed(self, value):
		self.image.speed = value

	def drop(self, event: QDropEvent):
		position = event.pos()
		dropped = event.source()
		for location in [self.topLeft, self.topRight, self.bottomLeft, self.bottomRight]:
			if location.geometry().contains(position):
				dropped.setParent(self)
				dropped.setGeometry(location.geometry())
				varName: str = [x for x, y in self.__dict__.items() if y is location][0]
				setattr(self, varName, dropped)
				location.deleteLater()
				dropped.show()
				return True
		if self.topLeft.geometry().contains(position):
			dropped.setGeometry(self.topLeft.geometry())

		elif 'speed' in dropped.subscriptionKey.lower():
			state = dropped.state
			self.speedState = {k: v for k, v in state.items() if k in self.speedState}
			self.speedUpdateSignal = dropped.updateSignal
			self.speedUpdateSignal.connect(self.setSpeed)
			return True
		elif 'direction' in dropped.subscriptionKey.lower():
			state = dropped.state
			self.directionState = {k: v for k, v in state.items() if k in self.speedState}
			self.valueUpdateSignal = dropped.updateSignal
			self.valueUpdateSignal.connect(self.setDirection)
			dropped.api.tryToSubscribe('windSampleInterval', self.sampleRateSignal)
			return True
		return False

	@Slot(Measurement)
	def setSpeed(self, value):
		self.speed = value

	@Slot(Measurement)
	def setDirection(self, value):
		self.direction = value

	@Slot(Measurement)
	def setSampleRate(self, value):
		print(int(value.ms) - 100)
		self.image.duration = int(value.ms) - 100

	@Slot(Measurement)
	def setGust(self, value):
		self.gust = value

	@property
	def value(self):
		return 'Wind'

	@value.setter
	def value(self, value: Measurement):
		if value:
			key = value.subscriptionKey
			if key == 'direction':
				self.direction = value
			elif key == 'speed':
				self.speed = value
			elif key == 'gust':
				self.gust = value
			elif key == 'lull':
				self.lull = value
			if hasattr(self.parent(), 'valueChangedSignal'):
				self.parent().valueChangedSignal.emitUpdate(self)

	@property
	def direction(self):
		return 'N'

	@direction.setter
	def direction(self, value):
		if self.speed > 0:
			self._directionArray.append(value)
			smoothedValue = Direction(sum(self._directionArray) / len(self._directionArray))
			self.image.animateDirection(smoothedValue)

	@property
	def max(self):
		return self.maxValueLabel.text()

	@max.setter
	def max(self, value):
		pass

	@property
	def lull(self):
		return self.lull

	@lull.setter
	def lull(self, value):
		self.bottomRight.value = value

	@property
	def gust(self):
		pass

	@gust.setter
	def gust(self, value):
		self.bottomLeft.value = value

	@property
	def hitBox(self):
		return self.rect()


class WindComplication(LocalComplication):

	def __init__(self, *args, **kwargs):
		super(WindComplication, self).__init__(*args, **kwargs)
		state = kwargs.get('state', None)
		self.setWidget(GaugeSubmodule(self, state=state))
		self.setAcceptDrops(True)

	@Slot(Measurement)
	def updateValueSlot(self, value: Measurement):
		self.value = value
		# print(f'{self} updated with {value}')
		if hasattr(self.parent(), 'valueChangedSignal'):
			self.parent().valueChangedSignal.emit(self)

	def dragEnterEvent(self, event):
		if isinstance(event.source(), Complication):
			event.accept()

	def dropEvent(self, event):
		if self.valueWidget.drop(event):
			event.accept()
		else:
			event.reject()

	@property
	def state(self):
		s = super(WindComplication, self).state
		s.update(self.valueWidget.state)
		return s


if __name__ == '__main__':
	import sys

	rotation: Direction = Direction(0)
	rotation._shorten = True
	speed: Wind = Wind(Mile(13.0), Hour(1))
	app = QApplication()

	window = GaugeSubmodule()
	window.image.setValue(25.4)
	window.resize(800, 800)
	window.show()
	sys.exit(app.exec_())
