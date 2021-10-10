import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple, Union

import numpy as np
import pylunar
from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Property, QPropertyAnimation, QRect, Qt, QTimer, Signal
from PySide2.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QRegion
from PySide2.QtWidgets import QApplication, QDesktopWidget, QMessageBox, QSlider, QVBoxLayout, QWidget
from pysolar import solar

from src import config
from widgets.Complication import LocalComplication

golden = (1 + np.sqrt(5)) / 2
dark = QColor(28, 29, 31, 255)


class Moon(QtWidgets.QWidget):
	moonFull: QPainterPath
	moonPath: QPainterPath
	_date: datetime
	_phase: float = 0
	_animation: QPropertyAnimation
	_radius: float = 200.0
	_rotation: float = 0.0
	_hitBox: QPainterPath
	_interval = 60

	valueChanged = Signal(float)

	def __init__(self, *args, **kwargs):
		super(Moon, self).__init__(*args, **kwargs)
		self._date = datetime.now(timezone.utc)
		self.lat, self.lon = config.loc
		self.mi = pylunar.MoonInfo(self.deg2dms(self.lat), self.deg2dms(self.lon))
		self.moonFull = QPainterPath()
		self.mainColor = self.palette().midlight()
		self.updateMoon()

		# Build timer
		self.timer = QTimer(self)
		self.timer.setInterval(1000 * self._interval)
		self.timer.setTimerType(Qt.VeryCoarseTimer)
		self.timer.timeout.connect(self.updateMoon)
		self.timer.start()

	def updateMoon(self):
		self.mi.update(self._date)
		self._phase = self.mi.fractional_age()
		self._rotation = self.getAngle(self.mi)
		self.moonFull.addEllipse(self.rect().center(), self._radius - 1, self._radius - 1)

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

	def resizeEvent(self, event):
		w = self.width()
		h = self.height()
		lineThickness = h * golden * 0.01
		self._radius = (h if h < w else w) * 0.48
		self.moonPath = self.drawMoon()
		self.moonFull.clear()
		self.moonFull.addEllipse(self.rect().center(), self._radius, self._radius)

		super(Moon, self).resizeEvent(event)

	def update(self):
		self.moonPath = self.drawMoon()
		super(Moon, self).update()

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

		c = self.rect().center()
		return (float(np.sin(ascension) * np.sin(declination) * r) + c.x(),
		        float(np.cos(declination) * r) + c.y(),
		        float(np.cos(ascension) * np.sin(declination) * r))

	def paintEvent(self, event: QtGui.QPaintEvent) -> None:

		self.painter = QPainter(self)
		self.painter.setRenderHint(QPainter.HighQualityAntialiasing)
		self.painter.setRenderHint(QPainter.Antialiasing)

		c = self.rect().center()
		if self._rotation:
			self.painter.translate(c.x(), c.y())
			self.painter.rotate(self._rotation)
			self.painter.translate(-c.x(), -c.y())

		# Draw entire sphere
		self.painter.setBrush(QBrush(dark))
		self.painter.drawPath(self.moonFull)

		# Draw the illuminated bit
		self.painter.setBrush(self.mainColor)
		# self.painter.setPen(QPen(self.mainColor, 0, j=QtCore.Qt.PenJoinStyle.MiterJoin))
		self.painter.drawPath(self.moonPath)

		self.painter.end()

	def drawMoon(self) -> QPainterPath:
		color = self.mainColor
		phase = self._phase
		brush = QtGui.QBrush(color)
		pen = QPen(color, 0)
		moon = QPainterPath()
		phase *= 360

		## Todo: try to rewrite this to use an ellipse rather than 240 lines

		'''
		pen = QPen(Qt.red, 10)
		self.painter.setPen(QColor(Qt.red))
		path = QPainterPath()
		rect = QRect()
		_, t, _ = self.sphericalToCartesian(self._phase * 360, 180)
		r, b, _ = self.sphericalToCartesian(self._phase * 360, 360)
		l, _, _ = self.sphericalToCartesian(self._phase * 360, 270)
		rect.setTop(t)
		rect.setRight(r)
		rect.setLeft(l)
		rect.setBottom(b)
		path.arcTo(rect, 0, 360.0)
		# path.addRect(rect)
		self.painter.drawPath(path)
		'''

		if phase < 180:
			x, y, z = self.sphericalToCartesian(phase, 0)
			moon.moveTo(x, y)
			for i in range(0, 180, 3):
				x, y, z = self.sphericalToCartesian(phase, i)
				moon.lineTo(x, y)
			for i in range(180, 360, 3):
				x, y, z = self.sphericalToCartesian(180, i)
				moon.lineTo(x, y)
		else:
			x, y, z = self.sphericalToCartesian(phase, 0)
			moon.moveTo(x, y)
			for i in range(0, 180, 3):
				x, y, z = self.sphericalToCartesian(180, i)
				moon.lineTo(x, y)
			for i in range(180, 360, 3):
				x, y, z = self.sphericalToCartesian(phase, i)
				moon.lineTo(x, y)

		moon.closeSubpath()
		return moon

	@Property(float)
	def phase(self) -> float:
		return self._phase

	@phase.setter
	def phase(self, value: float):
		self._phase = value
		self.update()

	@property
	def hitBox(self):
		return self.moonFull


class MoonComplication(LocalComplication):

	def __init__(self, *args, **kwargs):
		super(MoonComplication, self).__init__(*args, **kwargs)
		self.setWidget(Moon(self))


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
