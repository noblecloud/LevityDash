from collections import deque

from numpy import sqrt
from PySide2 import QtCore, QtWidgets
from PySide2.QtCore import Property, QEasingCurve, QPoint, QPointF, QPropertyAnimation, Signal
from PySide2.QtGui import QBrush, QFont, QPainter, QPainterPath, QPaintEvent, QPen, QPolygonF
from PySide2.QtWidgets import QApplication

from ui.wind_UI import Ui_Frame as windUI
from widgets.Submodule import Submodule

cardinalDirections = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


class windRose(QtWidgets.QFrame):
	_rotation: float = 0
	_animation: QPropertyAnimation

	valueChanged = Signal(float)
	clicked = Signal()

	def __init__(self, *args, **kwargs):
		super(windRose, self).__init__(*args, **kwargs)
		self._animation = QPropertyAnimation(self, b'rotation')
		self._animation.setEasingCurve(QEasingCurve.InOutCubic)

	def animate(self, rotation: int = None, absolute: bool = False, duration: int = 2000):
		if self._animation.state() != QtCore.QAbstractAnimation.Running:
			if rotation is not None:
				self._animation.setStartValue(self._rotation)
				if absolute:
					if self._animation.startValue() > 180 and rotation % 360 == 0:
						self._animation.setEndValue(360)
					else:
						self._animation.setEndValue(rotation)
				else:
					self._animation.setEndValue(self._rotation + rotation)
				self._animation.setDuration(duration)
			else:
				self._animation.setStartValue(0)
				self._animation.setEndValue(360)
				self._animation.setDuration(duration)
			self._animation.start()

	def resizeEvent(self, event):
		self.fontLarge = QFont(self.font())
		self.fontLarge.setWeight(70)
		self.fontLarge.setPointSize(self.height() * .25)
		super().resizeEvent(event)

	def paintEvent(self, event):
		paint = QPainter()
		paint.begin(self)
		paint.setRenderHint(QPainter.HighQualityAntialiasing)
		paint.setRenderHint(QPainter.Antialiasing)
		cx, cy = self.width() * 0.5, self.height() * 0.5
		cw, ch = self.width() * 0.9, self.height() * 0.9
		base = self.height() * 0.17
		pointerHeight = base * .9

		paint.translate(cx, cy)
		paint.rotate(self._rotation)
		paint.translate(-cx, -cy)
		penWidth = sqrt(self.height() ** 2 + self.width() ** 2) * 0.08
		pen = QPen(QtCore.Qt.white, penWidth)
		# paint.setPen(pen)
		radius = self.height() * .4
		paint.setBrush(QBrush(QtCore.Qt.white))
		path = QPainterPath()
		path.addEllipse(QPoint(cx, cy), radius, radius)
		path.addEllipse(QPoint(cx, cy), radius * 0.7, radius * 0.7)
		paint.drawPath(path)
		paint.setBrush(QtCore.Qt.white)

		paint.setPen(QPen(QtCore.Qt.white, 0))

		middle = QPointF(cx, 5)
		left = QPointF(cx - pointerHeight, base)
		right = QPointF(cx + pointerHeight, base)

		arrow = QPolygonF()
		arrow.append(middle)
		arrow.append(left)
		arrow.append(right)

		paint.drawPolygon(arrow)

		paint.translate(cx, cy)
		paint.rotate(-self._rotation)
		paint.translate(-cx, -cy)
		text = QPainterPath()
		directionStr = cardinalDirections[int(((self._rotation + 22.5) % 360) // 45 % 8)]
		x, y = estimateTextSize(self.fontLarge, directionStr)
		x1, y1 = estimateTextSize(self.fontLarge, '0.0')
		text.addText(cx - (x / 2) - 10, (cy) - 10, self.fontLarge, 'N')
		text.addText(cx - (x1 / 2) - 10, (cy) + y1, self.fontLarge, '0.0')
		paint.drawPath(text)

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
	def rotation(self) -> float:
		return self._rotation

	@rotation.setter
	def rotation(self, value: float):
		if value != self._rotation:
			self._rotation = value
			self.update()
			self.valueChanged.emit(value)

	@property
	def speed(self):
		return self._speed

	@speed.setter
	def speed(self, value):
		self._speed = value


def estimateTextSize(font: QFont, string: str) -> tuple[float, float]:
	p = QPainterPath()
	p.addText(QtCore.QPoint(0, 0), font, string)
	rect = p.boundingRect()
	return rect.width(), rect.height()


class windSubmodule(Submodule, windUI):
	# _speed: float
	# animation: QPropertyAnimation
	_directionArray: deque = deque([], 10)
	_direction: int = 0

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self._speed = 0.0
		self.setupUi(self)
		# self.directionLabel.move(-10, 0)
		self.image = windRose(self.mainFrame)
		self.image.setObjectName(u"windRose")

	# self.animation = QPropertyAnimation(self, b'speed')

	# self.unit.hide()

	# def setLive(self, value):
	# 	self.speedLabel.live = value
	# 	self.directionLabel.live = value
	# 	self.maxValueLabel.live = value
	# 	self.gustValueLabel.live = value
	#
	def setVector(self, speed, direction):
		self.speed = speed
		if speed > 0:
			self.direction = direction

	def paintEvent(self, event: QPaintEvent) -> None:
		super().paintEvent(event)
		self.image.setGeometry(self.mainFrame.geometry())

	# @Property(float)
	@property
	def speed(self):
		return self.image.speed

	@speed.setter
	def speed(self, value):
		self.image.speed = value

	# def animate(self, value):
	# 	print(value, self._speed)
	# 	self.animation.setStartValue(float(self._speed))
	# 	self.animation.setEndValue(value)
	# 	self.animation.setDuration(1000)
	# 	self.animation.start()

	#
	# def animateSpeed(self, value):
	# 	self.animate(value)

	@property
	def direction(self):
		return 'N'

	@direction.setter
	def direction(self, value):
		self._directionArray.append(value)
		smoothedValue = sum(self._directionArray) / len(self._directionArray)
		self.image.animate(smoothedValue, True, 3000)

	@property
	def max(self):
		return self.maxValueLabel.text()

	@max.setter
	def max(self, value):
		self.maxValueLabel.setText(value)

	@property
	def gust(self):
		return self.gustValueLabel.text()

	@gust.setter
	def gust(self, value):
		self.gustValueLabel.setText(value)


if __name__ == '__main__':
	import sys
	from tests.pickler import pans as reload

	app = QApplication()

	window = windSubmodule()
	window.resize(800, 800)
	window.show()
	sys.exit(app.exec_())
