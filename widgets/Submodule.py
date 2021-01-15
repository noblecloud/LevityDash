import logging
from typing import Union

from PySide2 import QtCore, QtWidgets
from PySide2.QtCore import Property, QEasingCurve, QPoint, QPointF, QPropertyAnimation, Signal
from PySide2.QtGui import QFont, QImage, QPainter, QPen, QPolygonF

from constants import Fonts
from measurments import Measurement
from measurments.groups import Wind
from ui.conditions_UI import Ui_conditions
from ui.wind_UI import Ui_Frame as windUI
from widgets.loudWidget import LoudWidget
from widgets.Status import StatusObject

fonts = Fonts()


class RotateSVG(QtWidgets.QFrame):
	_rotation: float = 0
	_image: QImage = QImage()
	_animation: QPropertyAnimation

	valueChanged = Signal(float)
	clicked = Signal()

	def __init__(self, imagePath: str, *args, **kwargs):
		super(RotateSVG, self).__init__(*args, **kwargs)
		self._image.load(imagePath)
		# self.resize(self._image.size())
		self._animation = QPropertyAnimation(self, b'rotation')
		self._animation.setEasingCurve(QEasingCurve.InOutCubic)

	# def resizeEvent(self, event):
	# 	super().resizeEvent(event)

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

	def paintEvent(self, event):
		paint = QPainter()
		paint.begin(self)
		cx, cy = self.width() * 0.5, self.height() * 0.5
		cw, ch = self.width() * 0.9, self.height() * 0.9
		base = self.height() * 0.17
		pointerHeight = base * .9

		paint.translate(cx, cy)
		paint.rotate(self._rotation)
		paint.translate(-cx, -cy)

		pen = QPen(QtCore.Qt.white, self.width() * .08)
		paint.setPen(pen)
		paint.drawEllipse(QPoint(cx, cy), self.height() / 3, self.height() / 3)

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

	def resizeSVG(self, svg, size):
		pass

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


class Submodule(LoudWidget, StatusObject):

	def __init__(self, *args, **kwargs):
		super().__init__()
		self.setProperty('live', False)

	# @property
	# def live(self):
	# 	return self.property('live')
	#
	# @live.setter
	# def live(self, value: bool):
	# 	self.setProperty('live', value)

class windSubmodule(windUI, Submodule):
	_value: Wind

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.setupUi(self)
		self.directionLabel.move(-10, 0)
		self.image = RotateSVG('ui/elements/WindDial.svg', self.mainFrame)
		self.image.setObjectName(u"windVane")
		# self.unit.hide()

	# self.move(0,10)
	# self.image.pos = self.pos()
	# self.mainFrame.layout().addWidget(self.image)

	def refresh(self, data: Wind):
		self.live = True
		self._value = data
		self.speed.setText(data.wind.speed)

	def setLive(self, value):
		self.speedLabel.live = value
		self.directionLabel.live = value
		self.maxValueLabel.live = value
		self.gustValueLabel.live = value


	def paintEvent(self, event):
		cardinalDirections = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
		direction = int(((self.image.rotation + 22.5) % 360) // 45 % 8)
		self.directionLabel.setText(cardinalDirections[direction])
		super().paintEvent(event)
		self.image.setGeometry(self.mainFrame.geometry())

	@property
	def speed(self):
		return self.speedLabel.text()

	@speed.setter
	def speed(self, value):
		self.speedLabel.setText(value)

	@property
	def direction(self):
		return self.directionLabel.text()

	@direction.setter
	def direction(self, value):
		if isinstance(value, float) or isinstance(value, int):
			logging.debug('setting wind with int or float')
			self.image.animate(value, True, 3000)
		elif isinstance(value, Measurement):
			logging.debug('setting wind with int or float')
			self.image.animate(value.int, True, 3000)
		else:
			logging.warn('Unable to set wind direction')

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


class currentConditions(Ui_conditions, Submodule):

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.glyphs = QFont()
		self.glyphs.setPointSize(30)
		self.glyphs.setFamily(u"Weather Icons")
		self.setupUi(self)
		self.glyphLabel.fontFamily = u"Weather Icons"
		self.forecastString = False

	# self.forecastString.setFont('test')

	@property
	def glyph(self):
		return None

	@glyph.setter
	def glyph(self, value):
		self.live = True
		self.glyphLabel.glyph = value

	@property
	def forecastString(self):
		return self.forecastStringLabel.text()

	@forecastString.setter
	def forecastString(self, value):
		self.live = True
		if value:
			self.forecastStringLabel.setText(value)
			self.forecastStringLabel.show()
		else:
			self.forecastStringLabel.hide()

	@property
	def currentCondition(self):
		return self.currentConditionLabel.text()

	@currentCondition.setter
	def currentCondition(self, value):
		if value:
			self.currentConditionLabel.setText(value)
			self.currentConditionLabel.show()
		else:
			self.currentConditionLabel.hide()
