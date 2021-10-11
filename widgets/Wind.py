from collections import deque

from numpy import sqrt
from PySide2 import QtCore, QtWidgets

from PySide2.QtCore import Property, QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRect, Qt, Signal, Slot
from PySide2.QtGui import QBrush, QDropEvent, QFont, QPainter, QPainterPath, QPaintEvent, QPen, QPolygonF, QResizeEvent
from PySide2.QtWidgets import QApplication, QWidget
from WeatherUnits import Direction
from WeatherUnits.base import Measurement
from WeatherUnits.derived import Wind
from WeatherUnits.length import Meter, Mile
from WeatherUnits.others import Direction
from WeatherUnits.time.time import Second, Hour

from fonts import rounded
from utils import estimateTextFontSize, estimateTextSize
from widgets.Complication import Complication, LocalComplication


class WindSubmodule(QWidget):
	_directionArray: deque = deque([], 10)
	_direction: int = 0
	_speedSignal: Signal
	_sampleRateSignal: Signal
	_directionSignal: Signal
	subscriptionKey = ('speed', 'direction', 'lull', 'gust')
	topLeft: Complication
	topLeftRect: QRect

	topRight: Complication
	topRightRect: QRect

	bottomLeft: Complication
	bottomLeftRect: QRect

	bottomRight: Complication
	bottomRightRect: QRect

	speedState: dict = {'api': None, 'key': None}
	directionState: dict = {'api': None, 'key': None}

	@property
	def speedSignal(self):
		return self._speedSignal

	@speedSignal.setter
	def speedSignal(self, value):
		self._speedSignal = value
		value.connect(self.setSpeed)

	@property
	def directionSignal(self):
		return self._directionSignal

	@directionSignal.setter
	def directionSignal(self, value):
		self._directionSignal = value
		value.connect(self.setDirection)

	@property
	def sampleRateSignal(self):
		return self._sampleRateSignal

	@sampleRateSignal.setter
	def sampleRateSignal(self, value):
		self._sampleRateSignal = value
		value.connect(self.setSampleRate)

	def __init__(self, *args, subscriptions: dict = None, **kwargs):
		super().__init__(*args, **kwargs)
		self.__init_ui__()
		if subscriptions is not None:
			self.speedState = subscriptions['speed']
			if self.speedState is not None:
				api = self.parent().parent().parent().toolbox.toolboxes[self.speedState['api']].api.realtime
				self.speedSignal = api.updateHandler.signalFor(key=self.speedState['key'])
				self.speed = api.get(self.speedState['key'])

			self.directionState = subscriptions['direction']
			if self.directionState is not None:
				api = self.parent().parent().parent().toolbox.toolboxes[self.directionState['api']].api.realtime
				self.directionSignal = api.updateHandler.signalFor(key=self.directionState['key'])
				self.sampleRateSignal = api.updateHandler.signalFor(key='windSampleInterval')
				self.direction = api.get(self.directionState['key'])

		self.topLeftRect = QRect(0, 0, 0, 0)
		self.topRightRect = QRect(0, 0, 0, 0)
		self.bottomLeftRect = QRect(0, 0, 0, 0)
		self.bottomRightRect = QRect(0, 0, 0, 0)

	# self.bottomLeft.show()
	# self.bottomRight.show()
	# self.bottomLeft.subTitleUnit = False
	# self.bottomRight.subTitleUnit = False
	# self.updateSignal.connect(self.updateValueSlot)

	# self.directionLabel.move(-10, 0)
	# self.setAttribute(Qt.WA_NoSystemBackground, True)
	# self.setAttribute(Qt.WA_TranslucentBackground, True)
	# self.setStyleSheet("color: white; background: black")
	# self.maxTitle.setAttribute(Qt.WA_TranslucentBackground, True)
	# self.maxValueLabel.setAttribute(Qt.WA_TranslucentBackground, True)
	# self.gustTitle.setAttribute(Qt.WA_TranslucentBackground, True)
	# self.gustTitle.setAttribute(Qt.WA_TranslucentBackground, True)
	# self.subDataFrame.setAttribute(Qt.WA_TranslucentBackground, True)
	# setAttribute(Qt::WA_NoSystemBackground);
	# setAttribute(Qt::WA_TranslucentBackground);

	# self.animation = QPropertyAnimation(self, b'speed')

	# self.unit.hide()

	# def setLive(self, value):
	# 	self.speedLabel.live = value
	# 	self.directionLabel.live = value
	# 	self.maxValueLabel.live = value
	# 	self.gustValueLabel.live = value
	#

	def __init_ui__(self):
		font = QFont()
		font.setFamily(u"SF Pro Rounded")
		self.setFont(font)
		self.rose = windRose(self)

		self.topLeft = Complication(self)

		self.bottomLeft = Complication(self)

		self.topRight = Complication(self)

		self.bottomRight = Complication(self)

	@property
	def state(self):
		return {'speed':     self.speedState,
		        'direction': self.directionState}

	def setVector(self, speed, direction):
		self.speed = speed
		if speed > 0:
			self.direction = direction

	def resizeEvent(self, event: QResizeEvent) -> None:
		self.rose.setGeometry(self.rect())
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

	@property
	def speed(self):
		return self.rose.speed

	@speed.setter
	def speed(self, value):
		self.rose.speed = value

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
			self.speedSignal = dropped.signal
			return True
		elif 'direction' in dropped.subscriptionKey.lower():
			state = dropped.state
			self.directionState = {k: v for k, v in state.items() if k in self.speedState}
			self.directionSignal = dropped.signal
			dropped.api.tryToSubscribe('windSampleInterval', self._sampleRateSignal)
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
		self.rose.duration = int(value.ms) - 100

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
			self.rose.animateDirection(smoothedValue)

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
		subscriptions = kwargs.get('subscriptions', None)
		self.setWidget(WindSubmodule(self, subscriptions=subscriptions))
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
		s['subscriptions'] = self.valueWidget.state
		return s


if __name__ == '__main__':
	import sys

	rotation: Direction = Direction(45)
	rotation._shorten = True
	speed: Wind = Wind(Mile(13.0), Hour(1))
	app = QApplication()

	window = WindSubmodule()
	window.resize(800, 800)
	window.show()
	window.setVector(speed, rotation)
	sys.exit(app.exec_())


class windRose(QtWidgets.QWidget):
	_direction: Direction = Direction(0.0)
	_speed: Wind = Wind(Meter(0.0), Second(1))
	_animation: QPropertyAnimation
	speed: Wind = None
	direction: float = None
	valueChanged = Signal(float)
	subscriptionKey = ('speed', 'direction')

	def __init__(self, *args, **kwargs):
		super(windRose, self).__init__(*args, **kwargs)
		self._direction: Direction = Direction(0.0)
		self._speed: Wind = Wind(Meter(0.0), Second(1))
		self._animation = QPropertyAnimation(self, b'direction')
		self._animation.setStartValue(0)
		self._animation.setEasingCurve(QEasingCurve.OutCubic)
		self._animation.setDuration(2000)

	def animateDirection(self, direction: Direction = None):
		if self._animation.state() == QtCore.QAbstractAnimation.Running:
			self._animation.stop()
		start = int(self.direction)
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
		super().resizeEvent(event)

	@property
	def radius(self):
		return min(self.height(), self.width()) * .4

	def paintEvent(self, event):
		paint = QPainter(self)
		paint.setRenderHint(QPainter.HighQualityAntialiasing)
		paint.setRenderHint(QPainter.Antialiasing)
		cx, cy = self.width() * 0.5, self.height() * 0.5
		cw, ch = self.width(), self.height()
		pointerHeight = self.radius * 0.178
		base = pointerHeight

		# Draw Circle
		radius = self.radius
		paint.translate(cx, cy)
		paint.rotate(self._direction)
		paint.translate(-cx, -cy)
		penWidth = sqrt(self.height() ** 2 + self.width() ** 2) * 0.08
		d = QBrush(self.palette().text().color())
		pen = QPen(d, 1)
		paint.setPen(pen)
		paint.setBrush(d)
		path = QPainterPath()
		path.addEllipse(QPoint(cx, cy), radius, radius)
		path.addEllipse(QPoint(cx, cy), radius * 0.7, radius * 0.7)
		paint.drawPath(path)
		paint.setBrush(d)
		paint.setPen(QPen(d, 0))

		# Draw Arrow
		middle = QPointF(cx, cy - pointerHeight - radius)
		left = QPointF(cx - base, cy - radius + 10)
		right = QPointF(cx + base, cy - radius + 10)
		arrow = QPolygonF()
		arrow.append(middle)
		arrow.append(left)
		arrow.append(right)
		paint.drawPolygon(arrow)

		paint.translate(cx, cy)
		paint.rotate(-self._direction)
		self._direction._shorten = True
		paint.translate(-cx, -cy)
		text = QPainterPath()
		text.setFillRule(Qt.WindingFill)
		speed = self.speed
		speed.showUnit = False
		font = QFont(self.fontLarge)
		speed = self._speed
		circleCenter = path.boundingRect().center()
		# cx = circleCenter.x()
		# cy = circleCenter.y()
		halfRadius = radius * 0.5 * 2
		x, y, cardFont = estimateTextFontSize(self.fontLarge, self._direction.cardinal, halfRadius * 0.8, halfRadius)
		x1, y1, speedFont = estimateTextFontSize(self.fontLarge, self.speed.str, halfRadius, halfRadius)
		x2, y2, unitFont = estimateTextFontSize(self.fontLarge, self.speed.unit, halfRadius * 0.3, halfRadius * 0.3)
		# cy *= 0.95
		# cardinalText = QPainterPath()
		text.addText(cx - (x / 2), cy, cardFont, self._direction.cardinal)
		# center = cardinalText.boundingRect().center()

		text.addText(cx - (x1 / 2), cy + y1 + radius * 0.05, speedFont, self.speed.str)
		text.addText(cx - (x2 / 2), cy + y1 + y2 + radius * 0.05, unitFont, self.speed.unit)

		textCenter = text.boundingRect().center()
		centerOffset = QPointF(cx - textCenter.x(), radius * -0.07)
		text.translate(centerOffset)

		paint.drawPath(text)
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

	@Property(float)
	def direction(self) -> float:
		return float(self._direction)

	@direction.setter
	def direction(self, value: float):
		if value != self._direction:
			self._direction = Direction(value)
			self.update()
			self.valueChanged.emit(value)

	@Property(float)
	def speed(self):
		return self._speed

	@speed.setter
	def speed(self, value):
		self._speed = value
		self.update()
