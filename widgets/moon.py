import sys
from datetime import datetime

import numpy as np
import pylunar
from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Property, QPropertyAnimation, Signal
from PySide2.QtGui import QPainter, QPainterPath, QPen
from PySide2.QtWidgets import QApplication
from pysolar import solar

from src import config
from utils import utcCorrect


class MoonPhases(QtWidgets.QFrame):
	_phase: float = 0
	_animation: QPropertyAnimation
	_radius: float = 200.0
	_rotation: float = 0.0

	valueChanged = Signal(float)

	def __init__(self, *args, **kwargs):
		super(MoonPhases, self).__init__(*args, **kwargs)
		# self.setFrameRect(rect)
		self.setStyleSheet('background-color: black')
		# self.installEventFilter(self)
		# self._animation = QPropertyAnimation(self, b'phase')
		# self._animation.setEasingCurve(QEasingCurve.InCurve)

		self.lat, self.lon = config.loc

		date = datetime.now()
		date = utcCorrect(date)
		mi = pylunar.MoonInfo(self.decdeg2dms(self.lat), self.decdeg2dms(self.lon))
		mi.update(date)
		self._phase = mi.fractional_phase()
		print(self._phase)

		self._rotation = self.getAngle(mi)

	def getAngle(self, mi) -> float:

		local = datetime.now(tz=config.tz)
		sunalt = solar.get_altitude_fast(self.lat, self.lon, local)
		sunaz = solar.get_azimuth_fast(self.lat, self.lon, local)
		moonaz = mi.azimuth()
		moonalt = mi.altitude()

		dLon = (sunaz - moonaz)
		y = np.sin(np.deg2rad(dLon)) * np.cos(np.deg2rad(sunalt))
		x = np.cos(np.deg2rad(moonalt)) * np.sin(np.deg2rad(sunalt)) - np.sin(np.deg2rad(moonalt)) * np.cos(
				np.deg2rad(sunalt)) * np.cos(np.deg2rad(dLon))
		brng = np.arctan2(y, x)
		brng = np.rad2deg(brng)
		return brng

	@staticmethod
	def decdeg2dms(dd):
		# a = []
		# for dd in args:
		mnt, sec = divmod(dd * 3600, 60)
		deg, mnt = divmod(mnt, 60)
		return deg, mnt, sec

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
			painter.rotate(self._rotation + 180)
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

		self.drawMoon(painter, self._phase, full)

		# This sorta works for drawing a gradient phase
		# TODO: Find a more efficient method for this
		# for x in range(0,16):
		# 	self.drawMoon(painter, phase + x - 8, one4)

		painter.end()

	def drawMoon(self, painter, phase: float, color):
		brush = QtGui.QBrush(color)
		pen = QPen(color, 0)
		moon = QPainterPath()
		painter.setPen(pen)

		phase *= 360
		phase = (phase + 180) % 360

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


if __name__ == '__main__':
	app = QApplication()

	window = MoonPhases()

	# window.phase = 2
	window.show()

	sys.exit(app.exec_())
