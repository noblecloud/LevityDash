import sys
from typing import Any, Iterable, Union
from enum import Enum

import numpy as np
from numpy import ndarray

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt
from scipy.signal import find_peaks

sys.modules['PyQt5.QtGui'] = QtGui
from PIL.ImageQt import ImageQt
from PySide2.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide2.QtWidgets import QApplication, QHBoxLayout, QLabel
from PIL import Image

from api.forecast import Forecast, hourlyForecast

golden = (1 + np.sqrt(5)) / 2


class Axis(Enum):
	Vertical = 0
	Horizontal = 1
	x = 0
	y = 1


class TimeMarkers:
	_stamps: ndarray
	_dates: ndarray

	def __init__(self, start: datetime, finish: datetime, increment: timedelta):
		dates = []
		stamps = []

		if increment.days:
			start = datetime(year=start.year, month=start.month, day=start.day, hour=0, minute=0, second=0, tzinfo=start.tzinfo)
		elif not increment.seconds % 3600:
			hour = increment.seconds / 3600
			startHour = int(hour * (start.hour // hour))
			start = datetime(year=start.year, month=start.month, day=start.day, hour=startHour, minute=0, second=0, tzinfo=start.tzinfo)

		i = start + increment
		while i < finish:
			stamps.append(i.timestamp())
			dates.append(i)
			i += increment
		self._dates = np.array(dates)
		self._stamps = np.array(stamps)

	@property
	def stamps(self):
		return self._stamps

	@property
	def dates(self):
		return self._dates


class Graph(QtWidgets.QFrame):
	_image: QPixmap
	_font: QFont
	_painter: QPainter
	_time: np.ndarray
	_data: dict
	_max: float
	_min: float
	_p2p: float

	def __init__(self, *args, **kwargs):
		super(Graph, self).__init__(*args, **kwargs)
		self.parseKwargs(kwargs)
		self.setStyleSheet('background-color: black;')
		self.setContentsMargins(10, 20, 10, 20)

	def parseKwargs(self, kwargs):
		if 'font' in kwargs:
			font = kwargs['font']
			if isinstance(font, str):
				self._font = QFont(font, self.height() * .1)
			elif isinstance(font, QFont):
				self._font = kwargs['font']
			else:
				self._font = QFont(font)
		else:
			self._font = QFont("SF Pro Rounded", self.height() * .1)

	def backgroundImage(self) -> QPixmap:
		LightImage = self.image()
		img = Image.fromarray(np.uint8(LightImage)).convert('RGBA')
		img.resize((self.width(), self.height()), Image.ANTIALIAS)
		qim = ImageQt(img)
		return QtGui.QPixmap.fromImage(qim)

	def paintEvent(self, event: QtGui.QPaintEvent) -> None:

		self._time: np.ndarray = self.normalizeToFrame(self.data['timestampInt'], Axis.y, frame='timestampInt')

		self._painter = QPainter()
		self._painter.begin(self)

		# Set render hints
		self._painter.setRenderHint(QPainter.HighQualityAntialiasing)
		self._painter.setRenderHint(QPainter.Antialiasing)
		self._painter.setRenderHint(QPainter.SmoothPixmapTransform)

		self._painter.drawPixmap(self.rect(), self._image)

		babyBlue = QtGui.QColor(3, 232, 252)
		# self.painter.drawText(self.rect(), QtCore.Qt.AlignCenter, "Hello")
		self.plotLine(self.data['dewpoint'], babyBlue, [1, 3])
		self.plotLine(self.data['temp'])
		temperature: np.ndarray = self.data['temp']
		peaks, _ = find_peaks(temperature, distance=80)
		troughs, _ = find_peaks(-temperature, distance=80)
		peaks = np.concatenate((peaks, troughs))
		peaks.sort()
		x = np.empty(len(peaks))
		y = np.zeros(len(peaks))
		for i in range(0, len(peaks)):
			y[i] = (self._time[peaks[i]])
			x[i] = (self.data['temp'][peaks[i]])
		x = self.normalizeToFrame(x, Axis.x, 0.1)
		# y = self.normalizeToFrame(y, self.width(), 0, 'timestampInt')

		average = sum(peaks) / len(peaks)
		for x, y, value in zip(y, x, peaks):
			self.plotText(x, y, f"{str(round(temperature[value]))}º", offset="+" if value > average else '-')
			self.drawVerticalLine(x)
		#
		# for x in range(0, len(self.time)):
		# 	y = (self.height() * 0.1) + ((self._data['feels_like'][x] - tmin) * yStep) * 0.8
		# 	path.lineTo(x * xStep, y)

		self._painter.end()

	def drawVerticalLine(self, position: Union[int, float], color: QtGui.QColor = QtCore.Qt.white, style: Union[QtCore.Qt.PenStyle, list[int]] = Qt.SolidLine):
		lineThickness = self.height() * golden * 0.01
		lineThickness = lineThickness if lineThickness > 8 else 8
		pen = QPen(color, lineThickness)
		if isinstance(style, Iterable):
			pen.setDashPattern(style)
		else:
			pen.setStyle(style)

		self._painter.setPen(pen)
		path = QPainterPath()
		path.moveTo(position, 0)
		path.lineTo(position, self.height())
		self._painter.drawPath(path)

	def plotLine(self, data: np.ndarray, color: QtGui.QColor = QtCore.Qt.white, style: Union[QtCore.Qt.PenStyle, list[int]] = Qt.SolidLine):

		plotData = self.normalizeToFrame(data, Axis.Vertical, 0.1)

		lineThickness = self.height() * golden * 0.01
		lineThickness = lineThickness if lineThickness > 8 else 8
		pen = QPen(color, lineThickness)
		if isinstance(style, Iterable):
			pen.setDashPattern(style)
		else:
			pen.setStyle(style)

		self._painter.setPen(pen)

		path = QPainterPath()
		path.moveTo(self._time[0], plotData[0])

		for xPlot, yPlot in zip(plotData, self._time):
			path.lineTo(yPlot, xPlot)

		self._painter.drawPath(path)

	def plotText(self, x: Union[float, int], y: Union[float, float], string: str, color=QtCore.Qt.white, offset: str = None):
		def outOfBounds(value):
			return 0 < value < self.height()

		fontSize = min(max(self.height() * 0.1, 30, min(self.width() * 0.06, self.height() * .2)), 100)
		self._font.setPixelSize(fontSize)

		# TODO: add logic to put values above line for high and below for lows while keeping text in frame
		"""
		if font is outside of screen:
			if font is for high:
				lower font
			else:
				raise font
		else:
			if font is for high:
				raise font
			else:
				lower font

		"""

		if 0 < y < self.height():
			if offset == '+':
				y = y - fontSize
			else:
				y = y + fontSize
		position = QtCore.QPoint(x - fontSize * .8, y + fontSize)

		lineThickness = max(fontSize * golden * 0.07, 3)
		pen = QPen(color, lineThickness)

		brush = QBrush(QtCore.Qt.black)
		self._painter.setPen(pen)
		self._painter.setBrush(QColor(None))
		path = QPainterPath()
		path.addText(position, self._font, string)
		self._painter.drawPath(path)

		self._painter.setPen(None)
		self._painter.setBrush(brush)
		path = QPainterPath()
		path.addText(position, self._font, string)
		self._painter.drawPath(path)

	def normalizeToFrame(self, array: ndarray, axis: Axis, offset: float = 0.0, frame: str = 'temp'):
		"""
		:param array: array which to normalize
		:param axis: Vertical or Horizontal
		:param offset:
		:param frame:
		:return: Normalized
		"""
		# start at leading margin
		# subtract the lowest value
		# height / peak to trough represents one unit value
		# shrink by top margin

		temp = self._data[frame]

		if axis == Axis.Vertical:
			leading = self.height() * offset
			return self.height() - (leading + (((array - self._min) * self.height() / self._p2p) * (1 - offset * 2)))
		else:
			return ((array - temp.min()) * self.width() / np.ptp(temp)) * (1 - offset * 2)

	@property
	def data(self):
		return self._data

	@data.setter
	def data(self, data: Forecast):

		def minMaxP2P(data) -> tuple[float, float, float]:
			arr = np.concatenate(((data['feels_like']), (data['temp']), (data['dewpoint'])), axis=0)
			return float(arr.min()), float(arr.max()), float(arr.ptp())

		self._data = data
		self._min, self._max, self._p2p = minMaxP2P(data)
		self._image = self.backgroundImage()

	@staticmethod
	def normalize(a):
		return (a - np.min(a)) / np.ptp(a)

	def gen(self, size):
		l = 200

		u = int(l * .07)
		# up = np.linspace((-np.pi / 2)+2, np.pi * .5, 20)
		# y2 = np.linspace(np.pi * .5, np.pi * .5, int(u / 2))
		# down = np.linspace(np.pi * .5, np.pi * 1.5, int(u * 2.5))

		up = np.logspace(.95, 1, 5)
		down = np.logspace(1, 0, int(u * 4))

		# x = normalize(x)
		y = self.normalize(np.concatenate((up, down)))
		x = np.linspace(0, 1, 272)
		y2 = np.zeros(size)
		y = np.concatenate((y, y2))
		return y

	def image(self):
		raw = self.normalize(self._data['surface_shortwave_radiation'])
		raw = np.outer(np.ones(len(raw)), raw)
		# raw = np.flip(raw)

		fade = .3

		# raw = self.solarColorMap(raw)
		scale = 1 / len(raw)
		rr = self.gen(len(raw))
		for x in range(0, len(raw)):
			raw[x] = raw[x] * rr[x]
		# if x < len(raw) * .1:
		# 	raw[x] *= scale * x *10
		# if x < len(raw) * fade:
		# 	raw[x] *= 1 - (scale * x) * (1/fade)
		# else:
		# 	raw[x] = 0

		opacity = .9
		raw *= 255 * opacity
		raw = raw.astype(np.uint8)

		return raw


if __name__ == '__main__':
	from tests.pickler import pans as reload

	app = QApplication()

	data = reload('../tests/snapshots/202101031000')
	# data = hourlyForecast()
	window = Graph()
	window.data = data
	window.show()

	sys.exit(app.exec_())
