import logging
import sys
from datetime import datetime, timedelta
from typing import Any, Iterable, Union
from enum import Enum

import numpy as np
from numpy import ndarray

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import QPoint, QRectF, Qt, QTimer
from scipy.signal import find_peaks

sys.modules['PyQt5.QtGui'] = QtGui
from PIL.ImageQt import ImageQt
from PySide2.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide2.QtWidgets import QApplication, QGraphicsDropShadowEffect, QGraphicsItem, QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsScene, QGraphicsTextItem, QGraphicsView
from PIL import Image

from api.forecast import Forecast, hourlyForecast

golden = (1 + np.sqrt(5)) / 2


class Axis(Enum):
	Vertical = 0
	Horizontal = 1
	y = 0
	x = 1


class TimeMarkers:
	_stamps: ndarray
	_dates: ndarray

	def __init__(self, start: datetime, finish: datetime, increment: timedelta, mask: list[int] = None):
		dates = []
		stamps = []

		mask = [] if not mask else mask

		if increment.days:
			start = datetime(year=start.year, month=start.month, day=start.day, hour=0, minute=0, second=0, tzinfo=start.tzinfo)
		elif not increment.seconds % 3600:
			hour = increment.seconds / 3600
			startHour = int(hour * (start.hour // hour))
			start = datetime(year=start.year, month=start.month, day=start.day, hour=startHour, minute=0, second=0, tzinfo=start.tzinfo)

		i = start + increment
		while i < finish:
			if i.hour not in mask:
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


class Holder(QGraphicsView):
	resizeTimer = QTimer()

	def __init__(self, *args, **kwargs):
		super(Holder, self).__init__(*args, **kwargs)
		self.setStyleSheet('background: black')
		self.setRenderHint(QPainter.HighQualityAntialiasing)
		self.setRenderHint(QPainter.Antialiasing)
		self.setRenderHint(QPainter.SmoothPixmapTransform)
		scene = GraphScene(self)
		self.setScene(scene)
		self.resizeTimer.timeout.connect(self.updateGraphics)

	def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
		self.resizeTimer.start(300)

	@property
	def data(self):
		return self.scene().data

	@data.setter
	def data(self, value):
		self.scene().data = value

	def updateGraphics(self):
		print('update')
		try:
			# self.scene().s.setEnabled(False)
			self.scene().updateValues()
			for item in self.scene().items():
				item.updateItem()
			# self.fitInView(self.scene(), Qt.AspectRatioMode.KeepAspectRatio)
			rcontent = self.contentsRect()
			self.setSceneRect(0, 0, rcontent.width(), rcontent.height())
		except Exception:
			pass
		self.resizeTimer.stop()
# self.scene().s.setEnabled(True)


class SoftShadow(QGraphicsDropShadowEffect):
	def __init__(self, *args, **kwargs):
		super(SoftShadow, self).__init__(*args, **kwargs)
		self.setOffset(0.0)
		self.setBlurRadius(60)
		self.setColor(Qt.black)


class GraphScene(QGraphicsScene):
	parent: Holder
	lineWeight: float
	data: Forecast
	dataKeys = ['temp', 'feels_like']
	mappedData: dict[str, ndarray] = {}
	mappedTime: ndarray
	textField: str = 'temp'
	font: QFont = QFont("SF Pro Rounded", 80)
	existingPlots = []

	def __init__(self, parent, *args, **kwargs):
		self.parent = parent
		super(GraphScene, self).__init__(*args, **kwargs)
		self.setColors()

	def plot(self):
		self.line = Plot(self, 'temp')
		self.addItem(BackgroundImage(self, self._data['surface_shortwave_radiation']))
		self.addItem(Plot(self, 'feels_like', self.babyBlue, [1, 3]))
		self.addItem(self.line)
		x = LineMarkers(self, 'hours', style=[9, 9], alpha=0.4, scalar=0.2)
		self.existingPlots.append(x)
		self.addItem(x)
		x = LineMarkers(self, 'days', scalar=0.5, alpha=0.8)
		self.existingPlots.append(x)
		self.addItem(x)
		self.addItem(TwinPlot(self))
		self.addAnnotations()
		self.addDayNames()

	def setColors(self):
		self.faded = QColor(255, 255, 255, 128)
		self.babyBlue = QtGui.QColor(3, 232, 252)

	def addAnnotations(self):
		for item in self._peaks:
			t = PlotAnnotation(self, item, 'temp')
			self.addItem(t)
		for item in self._troughs:
			t = PlotAnnotation(self, item, 'temp', Qt.AlignBottom)
			self.addItem(t)

	def addDayNames(self):
		for i, item in enumerate(self.hours.dates):
			item: datetime
			if item.hour == 12:
				p = self.mappedData['hours'][i]
				v = item.day
				t = MarkerAnnotation(self, i, 'hours', scalar=1.2)
				self.addItem(t)

	def mapData(self):
		for arrayName in self.dataKeys:
			self.mappedData.update({arrayName: self.normalizeToFrame(self.data[arrayName], Axis.y, offset=(0.3, 0.2))})
		self.mappedData.update({'cloud_cover': self.normalizeToFrame(self.data['cloud_cover'], Axis.y)})
		self.mappedData.update({'time': self.normalizeToFrame(self.data['timestampInt'], Axis.x, offset=(0.3, 0.2))})
		self.mappedData.update({'days': self.normalizeToFrame(self.days.stamps, Axis.x)})
		self.mappedData.update({'hours': self.normalizeToFrame(self.hours.stamps, Axis.x)})

	def normalizeToFrame(self, array: ndarray, axis: Axis, offset: tuple[float, float] = (0.0, 0.0)) -> ndarray:
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
		topMargin = offset[0]
		bottomMargin = offset[1]
		remainder = 1.0 - topMargin - bottomMargin
		if axis == Axis.Vertical:
			height = self.height
			leading = height * topMargin
			min, max, p2p = self.minMaxP2P
			return height - ((array - min) * height * remainder / p2p) - (height * bottomMargin)
		else:
			time = self.time
			return (array - time.min()) * self.width / np.ptp(time)

	def updateValues(self) -> None:
		self.fontSize = min(max(self.height * 0.1, 30, min(self.width * 0.06, self.height * .2)), 100)
		self.lineWeight = self.plotLineWeight()
		self.mapData()

	@property
	def height(self):
		return self.parent.height()

	@property
	def width(self):
		return self.parent.width()

	@property
	def peaks(self):
		return self._peaks

	@property
	def troughs(self):
		return self._troughs

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
		self._time: np.ndarray = data['timestampInt']
		self._peaks, _ = find_peaks(self.data[self.textField], distance=80)
		self._troughs, _ = find_peaks(-self.data[self.textField], distance=80)
		# self._image = self.backgroundImage()
		start, finish = data['timestamp'][0], data['timestamp'][-1]
		self.hours = TimeMarkers(start, finish, timedelta(hours=6), mask=[0])
		self.days = TimeMarkers(start, finish, timedelta(days=1))
		self.updateValues()
		self.plot()

	@property
	def minMaxP2P(self):
		return self._min, self._max, self._p2p

	def plotLineWeight(self) -> float:
		weight = self.parent.height() * golden * 0.005
		weight = weight if weight > 8 else 8.0
		return weight

	@property
	def time(self):
		return self._data['timestampInt']


class LineMarkers(QGraphicsPathItem):

	def __init__(self, parent: GraphScene, markerArray: str, color: QtGui.QColor = QtCore.Qt.white, style: Union[QtCore.Qt.PenStyle, list[int]] = Qt.SolidLine, scalar: float = 1.0, **kwargs):
		super(LineMarkers, self).__init__()
		self.markerArray = markerArray
		self.parent = parent
		color = QColor(color)

		if 'alpha' in kwargs.keys():
			value = kwargs['alpha']
			if isinstance(value, float):
				color.setAlphaF(value)
			elif isinstance(value, int) and 0 < value < 255:
				color.setAlpha(value)
			else:
				logging.warning(f'Unable to set with {value} of type {value.__class__.__name__}')

		pen = QPen(color, self.parent.lineWeight * scalar)
		if isinstance(style, Iterable):
			pen.setDashPattern(style)
		else:
			pen.setStyle(style)

		self.setPen(pen)
		self.updateItem()

	def updateItem(self) -> None:
		path = QPainterPath()
		for i in self.parent.mappedData[self.markerArray]:
			path.moveTo(i, 0)
			path.lineTo(i, self.parent.height)
		self.setPath(path)


class Text(QGraphicsPathItem):

	def __init__(self, parent, x: float, y: float, text: str, alignment: QtCore.Qt.AlignmentFlag = Qt.AlignCenter,
	             scalar: float = 1.0, font: Union[QFont, str] = None, color: QColor = Qt.white):
		super(Text, self).__init__()
		self.x, self.y = x, y
		self._parent = parent
		self._text = text
		self.alignment = alignment
		self.scalar = scalar
		self.color = color
		self.font = font

	@property
	def font(self):
		return self._font

	@font.setter
	def font(self, font: Union[QFont, str]):
		if font == None:
			self.font = QFont(self.parent.font)
		elif isinstance(font, str):
			self._font = QFont(font, self.height() * .1)
		elif isinstance(font, QFont):
			self._font = font
		else:
			self._font = QFont(font)

	def estimateTextSize(self, font: QFont) -> tuple[float, float]:
		"""
		Estimates the height and width of a string provided a font
		:rtype: float, float
		:param font:
		:return: height and width of text
		"""
		p = QPainterPath()
		p.addText(QtCore.QPoint(0, 0), font, self.text)
		rect = p.boundingRect()
		return rect.width(), rect.height()

	def updateItem(self) -> None:

		self.font.setPixelSize(self.parent.fontSize * self.scalar)

		lineThickness = max(self.parent.fontSize * self.scalar * golden * 0.07, 3)
		pen = QPen(self.color, lineThickness)

		brush = QBrush(QtCore.Qt.white)
		self.setPen(QColor(Qt.white))
		self.setBrush(brush)
		path = QPainterPath()
		path.setFillRule(Qt.WindingFill)
		path.addText(self.position(), self.font, self.text)
		self.setPath(path)

	# self.setPen(None)
	# self.setBrush(brush)
	# path = QPainterPath()
	# path.addText(self.position(), self.font, self.text)
	# self.setPath(path)

	@property
	def text(self) -> str:
		return self._text

	@text.setter
	def text(self, value: str):
		self._text = value

	@property
	def parent(self):
		return self._parent

	def position(self):
		strWidth, strHeight = self.estimateTextSize(self.font)
		x = self.x + strWidth * -0.6

		if x < 10:
			x = 10
		elif x + strWidth > self.parent.width - 10:
			x = self.parent.width - strWidth - 10

		# Set alignment
		y = self.y
		if self.alignment == Qt.AlignBottom:
			y += strHeight

		# Keep text in bounds
		if y - strHeight < 10:
			y = 10 + strHeight
		if y > self.parent.height - 15:
			y = self.parent.height - 15

		return QtCore.QPointF(x, y)


class MarkerAnnotation(Text):
	scalar: float

	def __init__(self, parent: GraphScene, index: int, array: str, alignment: Qt.AlignmentFlag = Qt.AlignCenter,
	             scalar: float = 1.0, font: Union[QFont, str] = None, color: QColor = Qt.white):
		super(MarkerAnnotation, self).__init__(parent, x=0, y=0, text="", alignment=alignment, scalar=scalar, font=font, color=color)
		self.index = index
		self.array = array
		self.updateItem()
		self.setGraphicsEffect(SoftShadow())

	@property
	def text(self):
		date: datetime = self.parent.hours.dates[self.index]
		return date.strftime('%a')

	def position(self) -> QtCore.QPointF:

		strWidth, strHeight = self.estimateTextSize(self.font)

		y = self.parent.height * 0.9
		x = self.parent.mappedData[self.array][self.index]
		x += strWidth * -0.5

		if x < 10:
			x = 10
		elif x + strWidth > self.parent.width - 10:
			x = self.parent.width - strWidth - 10

		# Set alignment
		if self.alignment == Qt.AlignBottom:
			y += strHeight
		elif self.alignment == Qt.AlignTop:
			pass
		else:
			y -= strHeight * -0.5

		# Keep text in bounds
		if y - strHeight < 10:
			y = 10 + strHeight
		if y > self.parent.height - 15:
			y = self.parent.height - 15

		return QtCore.QPointF(x, y)


class PlotAnnotation(Text):
	scalar: float

	def __init__(self, parent: GraphScene, index: int, array: str, alignment: Qt.AlignmentFlag = Qt.AlignCenter,
	             scalar: float = 1.0, font: Union[QFont, str] = None, color: QColor = Qt.white):
		super(PlotAnnotation, self).__init__(parent, x=0, y=0, text="", alignment=alignment, scalar=scalar, font=font, color=color)
		self.index = index
		self.array = array
		self.setGraphicsEffect(SoftShadow())
		self.updateItem()

	@property
	def text(self):
		return f"{str(round(self.parent.data[self.array][self.index]))}º"

	def position(self) -> QtCore.QPointF:

		lineWeight = self.parent.lineWeight

		strWidth, strHeight = self.estimateTextSize(self.font)

		y = self.parent.mappedData[self.array][self.index]
		x = self.parent.mappedData['time'][self.index]
		x += strWidth * -0.5

		if x < 10:
			x = 10
		elif x + strWidth > self.parent.width - 10:
			x = self.parent.width - strWidth - 10

		# Set alignment
		if self.alignment == Qt.AlignBottom:
			y += strHeight + lineWeight * 1.2
		else:
			y -= lineWeight * 1.2

		# Keep text in bounds
		if y - strHeight < 10:
			y = 10 + strHeight
		if y > self.parent.height - 15:
			y = self.parent.height - 15

		return QtCore.QPointF(x, y)


class BackgroundImage(QGraphicsPixmapItem):

	def __init__(self, parent: GraphScene, data: ndarray, *args, **kwargs):
		self._data = data
		self._parent = parent
		super(BackgroundImage, self).__init__(*args, **kwargs)
		self.setPixmap(self.backgroundImage())

	def updateItem(self):
		print('update background image')
		self.setPixmap(self.backgroundImage())

	@property
	def parent(self):
		return self._parent

	def backgroundImage(self) -> QPixmap:
		LightImage = self.image()
		img = Image.fromarray(np.uint8(LightImage)).convert('RGBA')
		img = img.resize((self.parent.width, self.parent.height))
		qim = ImageQt(img)
		return QtGui.QPixmap.fromImage(qim)

	def gen(self, size):
		print('gen image')
		l = self.parent.height

		u = int(l * .2)
		# up = np.linspace((-np.pi / 2)+2, np.pi * .5, 20)
		# y2 = np.linspace(np.pi * .5, np.pi * .5, int(u / 2))
		# down = np.linspace(np.pi * .5, np.pi * 1.5, int(u * 2.5))

		up = np.logspace(.95, 1, 5)
		down = np.logspace(1, 0, u, base=10)

		y = normalize(np.concatenate((up, down)))
		x = np.linspace(0, 1, 272)
		y2 = np.zeros(size)
		y = np.concatenate((y, y2))
		return y

	def image(self):
		raw = normalize(self._data)
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


class Plot(QGraphicsPathItem):
	def __init__(self, parent, x: str, color: QtGui.QColor = QtCore.Qt.white, style: Union[QtCore.Qt.PenStyle, list[int]] = Qt.SolidLine, scalar: float = 1.0):
		self.parent: GraphScene = parent
		self.color = color
		self.style = style
		self.scalar = scalar
		self._x = x
		super(Plot, self).__init__()
		self.grad()
		self.setPen(self.genPen())
		self.setPath(self.genPath())

	def grad(self) -> QLinearGradient:
		gradient = QLinearGradient(QtCore.QPointF(0, self.parent.height), QtCore.QPointF(0, 0))
		gradient.setColorAt(0, QColor(0, 0, 0))
		gradient.setColorAt(.4, QColor(75, 0, 130))
		gradient.setColorAt(.6, Qt.red)
		gradient.setColorAt(.8, Qt.yellow)
		gradient.setColorAt(1.0, Qt.white)
		return gradient

	def genPen(self):
		weight = self.parent.plotLineWeight() * self.scalar
		# brush = QBrush(self.grad())
		pen = QPen(self.color, weight)
		if isinstance(self.style, Iterable):
			pen.setDashPattern(self.style)
		else:
			pen.setStyle(self.style)
		return pen

	def genPath(self):
		path = QPainterPath()
		x = self.parent.mappedData[self._x]
		y = self.parent.mappedData['time']
		path.moveTo(y[0], x[0])

		for xPlot, yPlot in zip(x, y):
			path.lineTo(yPlot, xPlot)

		return path

	def updateItem(self):
		self.setPen(self.genPen())
		self.setPath(self.genPath())


class Margins:
	def __init__(self, top: Union[int, float], right: Union[int, float], bottom: Union[int, float], left: Union[int, float]):
		self.top = top
		self.right = right
		self.bottom = bottom
		self.left = left


NoMargin = Margins(0, 0, 0, 0)


class TwinPlot(QGraphicsPathItem):
	def __init__(self, parent, color: QtGui.QColor = QtCore.Qt.white, margins: Margins = NoMargin):
		self.parent: GraphScene = parent
		self.color = color
		self.margins = margins
		super(TwinPlot, self).__init__()
		self.setGraphicsEffect(SoftShadow())
		# self.setPen(self.genPen())
		self.setBrush(QBrush(color))
		self.setPen(QPen(QColor(color)))
		self.setPath(self.genPath())

	def genPath(self) -> QtGui.QPainterPath:
		width = self.parent.height * 0.02
		path = QPainterPath()
		top = normalize(self.parent.data['cloud_cover'])
		bottom = -top[::-1].copy()
		top *= width * 2
		top += width * 2 + 10
		bottom *= width
		bottom += width + 10
		y = self.parent.mappedData['time']
		yd = y[::-1]
		path.moveTo(y[0], top[0])

		for xPlot, yPlot in zip(top, y):
			path.lineTo(yPlot, xPlot)
		for xPlot, yPlot in zip(bottom, yd):
			path.lineTo(yPlot, xPlot)

		return path

	def updateItem(self):
		self.setPath(self.genPath())


def normalize(a, scalar: float = 1.0):
	return (a - np.min(a)) / np.ptp(a) * scalar


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

	def paintEvent(self, event: QtGui.QPaintEvent) -> None:
		self._fontSize = min(max(self.height() * 0.1, 30, min(self.width() * 0.06, self.height() * .2)), 100)
		self._lineWeight = self.plotLineWeight()

		self._painter = QPainter()
		self._painter.begin(self)

		# Set render hints
		self._painter.setRenderHint(QPainter.HighQualityAntialiasing)
		self._painter.setRenderHint(QPainter.Antialiasing)
		self._painter.setRenderHint(QPainter.SmoothPixmapTransform)

		# Draw Background
		self._painter.drawPixmap(self.rect(), self._image)

		# Draw markers
		pen = self._painter.pen()
		faded = QColor(255, 255, 255, 128)
		for i in self.normalizeToFrame(self.days.stamps, Axis.y):
			self.drawVerticalLine(i, scalar=.5, color=faded)

		hourMarkers = self.normalizeToFrame(self.hours.stamps, Axis.y)
		for i, date in zip(hourMarkers, self.hours.dates):
			if date.hour != 0:
				self.drawVerticalLine(i, scalar=0.2, style=[3, 9], color=faded)
			self.plotText(i, self.height(), date.strftime('%-I%p').lower(), scalar=.5)

		# Draw foreground
		babyBlue = QtGui.QColor(3, 232, 252)
		self.plotLine(self.data['dewpoint'], babyBlue, [1, 3])
		self.plotLine(self.data['temp'])

		# Add Temperatures
		temperature: np.ndarray = self.data['temp']
		peaks, _ = find_peaks(temperature, distance=80)
		x, y = np.empty(len(peaks)), np.empty(len(peaks))
		for i in range(0, len(peaks)):
			j = peaks[i]
			y[i] = self._time[j]
			x[i] = temperature[j]
		x = self.normalizeToFrame(x, Axis.x, 0.1)
		for x, y, i in zip(x, y, peaks):
			self.plotText(y, x, f"{str(round(temperature[i]))}º", offset="+")

		troughs, _ = find_peaks(-temperature, distance=80)
		x, y = np.empty(len(troughs)), np.empty(len(troughs))
		for i in range(0, len(troughs)):
			j = troughs[i]
			y[i] = self._time[j]
			x[i] = self.data['temp'][j]
		x = self.normalizeToFrame(x, Axis.x, 0.1)
		for x, y, value in zip(y, x, troughs):
			self.plotText(x, y, f"{str(round(temperature[value]))}º", offset="-")

		self._painter.end()

	def drawVerticalLine(self, position: Union[int, float], color: QtGui.QColor = QtCore.Qt.white, style: Union[QtCore.Qt.PenStyle, list[int]] = Qt.SolidLine, scalar: float = 1.0) -> None:
		"""
		Draws a vertical line on graph
		:param Union[int, float] position: y position of line
		:param QColor color: Color of pen
		:param Union[PenStyle, list[int]] style:
		:param float scalar: weight relative to baseline line thickness
		"""
		pen = QPen(color, self._lineWeight * scalar)
		if isinstance(style, Iterable):
			pen.setDashPattern(style)
		else:
			pen.setStyle(style)

		self._painter.setPen(pen)
		path = QPainterPath()
		path.moveTo(position, 0)
		path.lineTo(position, self.height())
		self._painter.drawPath(path)

	def plotLine(self, data: np.ndarray, color: QtGui.QColor = QtCore.Qt.white, style: Union[QtCore.Qt.PenStyle, list[int]] = Qt.SolidLine, scalar: float = 1.0):

		plotData = self.normalizeToFrame(data, Axis.Vertical, 0.1)

		lineThickness = self._lineWeight * scalar
		pen = QPen(color, lineThickness)
		if isinstance(style, Iterable):
			pen.setDashPattern(style)
		else:
			pen.setStyle(style)

		self._painter.setPen(pen)
		self._painter.setBrush(Qt.NoBrush)

		path = QPainterPath()
		path.moveTo(self._time[0], plotData[0])

		for xPlot, yPlot in zip(plotData, self._time):
			path.lineTo(yPlot, xPlot)

		self._painter.drawPath(path)

	def plotLineWeight(self) -> float:
		weight = self.height() * golden * 0.005
		weight = weight if weight > 8 else 8.0
		return weight

	def plotText(self, x: Union[float, int], y: Union[float, float], string: str, color=QtCore.Qt.white, offset: str = None, scalar: float = 1.0):

		def estimateTextSize(font: QFont) -> tuple[float, float]:
			p = QPainterPath()
			p.addText(QtCore.QPoint(0, 0), font, string)
			rect = p.boundingRect()
			return rect.width(), rect.height()

		font = QFont(self._font)
		font.setPixelSize(self._fontSize * scalar)

		strWidth, strHeight = estimateTextSize(font)

		lineWeight = self._lineWeight
		x -= strWidth / 2

		lineThickness = max(self._fontSize * scalar * golden * 0.07, 3)
		print(offset)

		if offset == '-':
			y += strHeight + lineWeight * 1.2
		else:
			y -= lineWeight * 1.2
		if y - strHeight < 10:
			y = 10 + strHeight
		if y > self.height() - 15:
			y = self.height() - 15
		position = QtCore.QPoint(x, y)

		pen = QPen(color, lineThickness)

		brush = QBrush(QtCore.Qt.black)
		self._painter.setPen(pen)
		self._painter.setBrush(QColor(None))
		path = QPainterPath()
		path.addText(position, font, string)
		self._painter.drawPath(path)

		self._painter.setPen(None)
		self._painter.setBrush(brush)
		path = QPainterPath()
		path.addText(position, font, string)
		self._painter.drawPath(path)

	def normalizeToFrame(self, array: ndarray, axis: Axis, offset: float = 0.0):
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

		if axis == Axis.Vertical:
			leading = self.height() * offset
			return self.height() - (leading + (((array - self._min) * self.height() / self._p2p) * (1 - offset * 2)))
		else:
			time = self._data['timestampInt']
			return ((array - time.min()) * self.width() / np.ptp(time)) * (1 - offset * 2)

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
		start, finish = data['timestamp'][0], data['timestamp'][-1]
		self.hours = TimeMarkers(start, finish, timedelta(hours=6))
		self.days = TimeMarkers(start, finish, timedelta(days=1))

	@staticmethod
	def normalize(a):
		return (a - np.min(a)) / np.ptp(a)


if __name__ == '__main__':
	from tests.pickler import pans as reload

	app = QApplication()

	data = reload('../tests/snapshots/202101031000')
	# data = hourlyForecast()
	window = Holder()
	window.resize(1800, 1000)
	window.scene().data = data
	window.show()
	window.scene().plot()
	# scene = QGraphicsScene()
	# scene.addText('test')
	# scene.addEllipse(100, 100, 100, 100)
	# view = QGraphicsView(scene)
	# view.show()

	sys.exit(app.exec_())
