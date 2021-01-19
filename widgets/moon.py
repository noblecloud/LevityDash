import numpy as np
from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Property, QEasingCurve, QPropertyAnimation, QRect, Signal
from PySide2.QtGui import QPainter, QPainterPath, QPen
from scipy.constants import golden


class MoonPhases(QtWidgets.QFrame):
	_phase: float = 0
	_animation: QPropertyAnimation
	_radius: float = 200.0
	_rotation: float = 0.0

	valueChanged = Signal(float)

	def __init__(self, rect: QRect, *args, **kwargs):
		super(MoonPhases, self).__init__(*args, **kwargs)
		self.setFrameRect(rect)
		self.setStyleSheet('background-color: black')
		self.installEventFilter(self)
		self._animation = QPropertyAnimation(self, b'phase')
		self._animation.setEasingCurve(QEasingCurve.InCurve)
		self.show()

	def animate(self):
		if self._animation.state() != QtCore.QAbstractAnimation.Running:
			self._animation.setStartValue(0.0)
			self._animation.setEndValue(10.0)
			self._animation.setDuration(5000)
			self._animation.start()

	def mousePressEvent(self, event):
		print(self._phase)

	def eventFilter(self, obj, event):
		if event.type() == QtCore.QEvent.KeyPress:
			if event.key() == QtCore.Qt.Key_R:
				self.animate()

	def sphericalToCartesian(self, ascension, declination):

		r = self._radius

		ascension += 90
		ascension = np.deg2rad(ascension)
		declination = np.deg2rad(declination)

		cx, cy = self.width() / 2, self.height() / 2

		return (float(np.sin(ascension) * np.sin(declination) * r) + cx,
		        float(np.cos(declination) * r) + cy,
		        float(np.cos(ascension) * np.sin(declination) * r))

	def paintEvent(self, event):

		w = self.width()
		h = self.height()

		self._radius = (h if h < w else w) * 0.4

		lineThickness = self.height() * golden * 0.01
		lineThickness = 1
		r = 100

		painter = QPainter()
		painter.begin(self)

		if self._rotation:
			painter.translate(w / 2, h / 2)
			painter.rotate(self._rotation)
			painter.translate(-(w / 2), -(h / 2))

		painter.setRenderHint(QPainter.HighQualityAntialiasing)

		blackPen = QPen(QtCore.Qt.black, 5)
		whitePen = QPen(QtCore.Qt.white, 0, j=QtCore.Qt.PenJoinStyle.MiterJoin)
		redPen = QPen(QtCore.Qt.red, 5)

		# moon.setFillRule(QtCore.Qt.WindingFill)

		phase = self.getDegree()

		one4 = QtGui.QColor(255, 255, 255, 32)
		half = QtGui.QColor(255, 255, 255, 128)
		three4 = QtGui.QColor(255, 255, 255, 192)
		full = QtGui.QColor(255, 255, 255, 255)

		self.drawMoon(painter, phase, full)

		# This sorta works for drawing a gradient phase
		# TODO: Find a more efficient method for this
		# for x in range(0,16):
		# 	self.drawMoon(painter, phase + x - 8, one4)

		painter.end()

	def drawMoon(self, painter, phase, color):
		brush = QtGui.QBrush(color)
		pen = QPen(color, 0)
		moon = QPainterPath()
		painter.setPen(pen)
		if phase < 9:
			pass
		elif phase < 180:
			x, y, z = self.sphericalToCartesian(phase, 0)
			moon.moveTo(x, y)
			for i in range(0, 180):
				x, y, z = self.sphericalToCartesian(phase, i)
				moon.lineTo(x, y)
			for i in range(180, 360):
				x, y, z = self.sphericalToCartesian(180, i)
				moon.lineTo(x, y)
		elif phase < 360:
			x, y, z = self.sphericalToCartesian(phase, 0)
			moon.moveTo(x, y)
			for i in range(0, 180):
				x, y, z = self.sphericalToCartesian(180, i)
				moon.lineTo(x, y)
			for i in range(180, 360):
				x, y, z = self.sphericalToCartesian(phase, i)
				moon.lineTo(x, y)
		elif phase < 350:
			pass
		painter.setBrush(brush)
		painter.drawPath(moon)
		moon.closeSubpath()

	def getDegree(self) -> float:
		return self._phase * 12

	@Property(float)
	def phase(self) -> float:
		return self._phase

	@phase.setter
	def phase(self, value: float):
		self._phase = value
		self.update()
		self.valueChanged.emit(value)
