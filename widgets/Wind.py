from collections import deque

from PySide2.QtCore import Qt
from PySide2.QtGui import QPaintEvent
from PySide2.QtWidgets import QApplication
from WeatherUnits.derived import Wind
from WeatherUnits.length import Meter
from WeatherUnits.others import Direction
from WeatherUnits.time import Second

from ui.wind_UI import Ui_wind as windUI
from widgets.Submodule import Submodule


class WindSubmodule(Submodule, windUI):
	# _speed: float
	# animation: QPropertyAnimation
	_directionArray: deque = deque([], 10)
	_direction: int = 0

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self._speed = 0.0
		self.setupUi(self)

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
	def setVector(self, speed, direction):
		self.speed = speed
		if speed > 0:
			self.direction = direction

	def paintEvent(self, event: QPaintEvent) -> None:
		super().paintEvent(event)
		self.rose.setGeometry(self.rect())
		width = self.width() / 5 + (self.width() - self.rose.width())
		height = self.height() / 5 + (self.height() - self.rose.height())
		self.bottomLeft.setGeometry(0, self.height() - height, width, height)
		self.topLeft.setGeometry(0, 0, width, height)
		self.topRight.setGeometry(self.width() - width, 0, width, height)
		self.bottomRight.setGeometry(self.width() - width, self.height() - height, width, height)

	# @Property(float)
	@property
	def speed(self):
		return self.image.speed

	@speed.setter
	def speed(self, value):
		self.rose.speed = value

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
		smoothedValue = Direction(sum(self._directionArray) / len(self._directionArray))
		self.rose.animate(smoothedValue, True, 3000)

	@property
	def max(self):
		return self.maxValueLabel.text()

	@max.setter
	def max(self, value):
		pass

	# self.TLValue.setText(value)

	@property
	def gust(self):
		return self.gustValueLabel.text()

	@gust.setter
	def gust(self, value):
		pass
	# self.TRValue.setText(value)


if __name__ == '__main__':
	import sys

	rotation: Direction = Direction(30)
	speed: Wind = Wind(Meter(13.0), Second(1))
	app = QApplication()

	window = WindSubmodule()
	window.topLeft.show()
	window.resize(800, 800)
	window.show()
	window.setVector(speed, rotation)
	sys.exit(app.exec_())
