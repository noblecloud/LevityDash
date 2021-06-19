import sys
from datetime import datetime, timedelta, timezone
from typing import Tuple

import numpy as np
import pylunar
from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Property, QPropertyAnimation, Qt, Signal
from PySide2.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide2.QtWidgets import QApplication, QDesktopWidget, QSlider, QVBoxLayout, QWidget
from pysolar import solar

from src import config
from ui.colors import Default

golden = (1 + np.sqrt(5)) / 2
dark = QColor(28, 29, 31, 255)


class Moon(QtWidgets.QWidget):
	_date: datetime
	_phase: float = 0
	_animation: QPropertyAnimation
	_radius: float = 200.0
	_rotation: float = 0.0

	valueChanged = Signal(float)

	def __init__(self, *args, **kwargs):
		super(Moon, self).__init__(*args, **kwargs)
		self._date = datetime.now(timezone.utc)
		self.lat, self.lon = config.loc
		self.auto()

	def auto(self):
		mi = pylunar.MoonInfo(self.deg2dms(self.lat), self.deg2dms(self.lon))
		mi.update(self._date)
		self._phase = mi.fractional_age()
		self._rotation = self.getAngle(mi)

	def getAngle(self, mi) -> float:
		"""https://stackoverflow.com/a/45029216/2975046"""

		local = datetime.now(timezone.utc)
		sunalt = solar.get_altitude_fast(self.lat, self.lon, self._date)
		sunaz = solar.get_azimuth_fast(self.lat, self.lon, self._date)
		moonaz = mi.azimuth()
		moonalt = mi.altitude()

		dLon = (sunaz - moonaz)
		y = np.sin(np.deg2rad(dLon)) * np.cos(np.deg2rad(sunalt))
		x = np.cos(np.deg2rad(moonalt)) * np.sin(np.deg2rad(sunalt)) - np.sin(np.deg2rad(moonalt)) * np.cos(
				np.deg2rad(sunalt)) * np.cos(np.deg2rad(dLon))
		brng = np.arctan2(y, x)
		brng = np.rad2deg(brng)
		return brng - 90

	@staticmethod
	def deg2dms(dd: float) -> Tuple[float, float, float]:
		mnt, sec = divmod(dd * 3600, 60)
		deg, mnt = divmod(mnt, 60)
		return deg, mnt, sec

	def sphericalToCartesian(self, ascension: float, declination: float) -> Tuple[float, float, float]:

		r = self._radius

		ascension += 90
		ascension = np.deg2rad(ascension)
		declination = np.deg2rad(declination)

		cx, cy = self.width() / 2, self.height() / 2

		return (float(np.sin(ascension) * np.sin(declination) * r) + cx,
		        float(np.cos(declination) * r) + cy,
		        float(np.cos(ascension) * np.sin(declination) * r))

	def paintEvent(self, event: QtGui.QPaintEvent) -> None:

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
		painter.setRenderHint(QPainter.Antialiasing)

		blackPen = QPen(QtCore.Qt.black, 5)
		whitePen = QPen(Default.main, 0, j=QtCore.Qt.PenJoinStyle.MiterJoin)
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
		# for x in range(0, 16):
		# 	self.drawMoon(painter, self._phase + x/1000, one4)
		#
		painter.end()

	def drawMoon(self, painter, phase: float, color):
		brush = QtGui.QBrush(color)
		pen = QPen(color, 0)
		moon = QPainterPath()
		phase *= 360

		if phase < 10:
			h = self.height() / 500
			border = QPen(color, h)
			self.drawCircle(painter, dark, border)
		elif phase < 180:
			self.drawCircle(painter, dark)
			x, y, z = self.sphericalToCartesian(phase, 0)
			moon.moveTo(x, y)
			for i in range(0, 180):
				x, y, z = self.sphericalToCartesian(phase, i)
				moon.lineTo(x, y)
			for i in range(180, 360):
				x, y, z = self.sphericalToCartesian(180, i)
				moon.lineTo(x, y)
		elif phase < 350:
			self.drawCircle(painter, dark)
			x, y, z = self.sphericalToCartesian(phase, 0)
			moon.moveTo(x, y)
			for i in range(0, 180):
				x, y, z = self.sphericalToCartesian(180, i)
				moon.lineTo(x, y)
			for i in range(180, 360):
				x, y, z = self.sphericalToCartesian(phase, i)
				moon.lineTo(x, y)
		else:
			h = self.height() / 500
			border = QPen(color, h)
			self.drawCircle(painter, dark, border)

		moon.closeSubpath()

		painter.setPen(pen)
		painter.setBrush(brush)
		painter.drawPath(moon)

	def drawCircle(self, painter, color: QColor, border: QPen = None):
		path = QPainterPath()
		fill = QtGui.QBrush(color)
		_, y, _ = self.sphericalToCartesian(0, 180)
		_, r, _ = self.sphericalToCartesian(0, 0)
		x, _, _ = self.sphericalToCartesian(0, 270)
		path.addEllipse(x, y, r - y, r - y)
		painter.setBrush(fill)
		painter.setPen(border)
		painter.drawPath(path)

	def getDegree(self) -> float:
		return self._phase * 12

	@Property(float)
	def phase(self) -> float:
		return self._phase

	@phase.setter
	def phase(self, value: float):
		self._phase = value
		self.update()


class Example(QWidget):

	def __init__(self):
		super().__init__()

		self.initUI()

	def initUI(self):
		hbox = QVBoxLayout()
		self.moon = Moon()

		sld = QSlider(Qt.Horizontal, self)
		sld.setRange(0, 1000)
		sld.setFocusPolicy(Qt.NoFocus)
		sld.setPageStep(5)

		sld.valueChanged.connect(self.updateLabel)

		hbox.addWidget(self.moon)
		hbox.addSpacing(15)
		hbox.addWidget(sld)

		self.setLayout(hbox)

		self.setGeometry(300, 300, 1200, 1200)
		self.setWindowTitle('QSlider')
		self.show()

	def updateLabel(self, value):
		self.moon.phase = value / 1000


if __name__ == '__main__':
	app = QApplication()

	window = Example()

	# window.phase = 2
	display_monitor = 1
	monitor = QDesktopWidget().screenGeometry(display_monitor)
	window.move(monitor.left(), monitor.top())
	# SECOND_DISPLAY = True
	# if SECOND_DISPLAY:
	# 	display = app.screens()[1]
	# 	window.setScreen(display)
	# 	window.move(display.geometry().x() + 200, display.geometry().y() + 200)
	window.show()

	sys.exit(app.exec_())
