import sys

import numpy as np

from PySide2 import QtCore, QtGui, QtWidgets
from scipy.signal import find_peaks

sys.modules['PyQt5.QtGui'] = QtGui
from PIL.ImageQt import ImageQt
from PySide2.QtGui import QBrush, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide2.QtWidgets import QApplication, QHBoxLayout, QLabel
from PIL import Image

from api.forecast import Forecast, hourlyForecast

golden = (1 + np.sqrt(5)) / 2


class Graph(QtWidgets.QFrame):
	painter: QPainter
	pix: QPixmap
	_time: np.ndarray
	_data: dict
	_max: float
	_min: float
	_p2p: float

	def __init__(self, *args, **kwargs):
		# self._data = data
		super(Graph, self).__init__(*args, **kwargs)
		self.buildColorMaps()
		self.setStyleSheet('background-color: black;')
		self.font = QFont("SF Pro Rounded", 50)
		self.setContentsMargins(10, 20, 10, 20)

	def backgroundImage(self):
		LightImage = self.image()
		img = Image.fromarray(np.uint8(LightImage)).convert('RGBA')
		img.resize((self.width(), self.height()), Image.ANTIALIAS)
		qim = ImageQt(img)
		pix = QtGui.QPixmap.fromImage(qim)
		self.pix = pix

	def buildColorMaps(self):
		from matplotlib.colors import LinearSegmentedColormap
		solarColorDict = {'red':   [(0.0, 0.0, 0.0),
		                            # (0.12, 1, 1),
		                            (0.2, 0.9, 0.9),
		                            # (0.3, 0.3, 0.3),
		                            # (0.4, 0.4, 0.4),
		                            # (0.5, 0.5, 0.5),
		                            # (0.6, 0.6, 0.6),
		                            # (0.7, 0.7, 0.7),
		                            # (0.8, 0.8, 0.8),
		                            (0.7, 1, 1),
		                            (1, 1, 1)],
		                  'green': [(0.0, 0.0, 0.0),
		                            (0.2, 0.75, 0.75),
		                            # (0.2, 0.2, 0.2),
		                            # (0.3, 0.3, 0.3),
		                            # (0.4, 0.4, 0.4),
		                            # (0.5, 0.5, 0.5),
		                            # (0.6, 0.6, 0.6),
		                            # (0.7, 0.7, 0.7),
		                            # (0.8, 0.8, 0.8),
		                            (0.7, 1, 1),
		                            (1, 1, 1)],
		                  'blue':  [(0.0, 0.0, 0.0),
		                            (0.1, 0.2, 0.2),
		                            # (0.2, 0.2, 0.2),
		                            # (0.3, 0.3, 0.3),
		                            (0.4, 0.4, 0.4),
		                            # (0.5, 0.5, 0.5),
		                            # (0.6, 0.6, 0.6),
		                            (0.75, 1, 1),
		                            # (0.8, 0.8, 0.8),
		                            # (0.9, 0.9, 0.9),
		                            (1, 1, 1)
		                            ]  # ,
		                  # 'alpha': [(0.0, 0.0, 0.0),
		                  #           (0.1, 0.1, 0.1),
		                  #           (0.2, 0.2, 0.2),
		                  #           (0.3, 0.3, 0.3),
		                  #           (0.4, 0.4, 0.4),
		                  #           (0.5, 0.5, 0.5),
		                  #           (0.6, 0.6, 0.6),
		                  #           (0.7, 0.7, 0.7),
		                  #           (0.8, 0.8, 0.8),
		                  #           (0.9, 0.9, 0.9),
		                  #           (1, 1, 1.0)]
		                  }

		gray = {'red':   ((0.0, 0, 0), (1.0, 1, 1)),
		        'green': ((0.0, 0, 0), (1.0, 1, 1)),
		        'blue':  ((0.0, 0, 0), (1.0, 1, 1))}

		rain = {'red':   [(0.0, 0.1, 0.1),
		                  (1.0, .4, .4)],

		        'green': [(0.0, 0.1, 0.1),
		                  (1.0, .6, .6)],

		        'blue':  [(0.0, .2, .2),
		                  (0.0, .6, .6),
		                  (1.0, 0.8, 0.8)],

		        'alpha': [(0.0, 0.0, 0.0),
		                  (0.1, 0.2, 0.2),
		                  (1.0, 1, 1)]}
		# 'alpha': [(0.0, 0.0, 0.0),
		#           (0.25, 0.0, 0.0),
		#           (.5, 0.5, 0.5)]}

		self.rainColorMap = LinearSegmentedColormap('colormap', rain)

		self.solarColorMap = LinearSegmentedColormap('colorMap', solarColorDict)

	def paintEvent(self, event):
		self.margin = 0.2

		self._time: np.ndarray = self.normalizeToFrame(self.data['timestampInt'], self.width(), frame='timestampInt')

		# yStep = ((tempRange / y) - (y * self.margin))
		self.painter = QPainter()
		self.painter.begin(self)
		# self.painter.translate(0, self.height());
		# self.painter.scale(1.0, -1.0);

		self.painter.setRenderHint(QPainter.HighQualityAntialiasing)
		self.painter.setRenderHint(QPainter.Antialiasing)
		self.painter.setRenderHint(QPainter.SmoothPixmapTransform)

		self.painter.drawPixmap(self.rect(), self.pix)

		babyBlue = QtGui.QColor(3, 232, 252)
		# self.painter.drawText(self.rect(), QtCore.Qt.AlignCenter, "Hello")
		self.plotLine(self.data['temp'])
		self.plotLine(self.data['dewpoint'], babyBlue)
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
		x = self.normalizeToFrame(x, self.height(), 0.1)
		# y = self.normalizeToFrame(y, self.width(), 0, 'timestampInt')
		for x, y, value in zip(x, y, peaks):
			self.plotText(QtCore.QPoint(y - 30, x + 20), str(round(temperature[value])))
		#
		# for x in range(0, len(self.time)):
		# 	y = (self.height() * 0.1) + ((self._data['feels_like'][x] - tmin) * yStep) * 0.8
		# 	path.lineTo(x * xStep, y)

		self.painter.end()

	def plotLine(self, data: np.ndarray, color=QtCore.Qt.white):
		plotData = self.normalizeToFrame(data, self.height(), 0.1)

		lineThickness = self.height() * golden * 0.01
		lineThickness = lineThickness if lineThickness > 8 else 8
		pen = QPen(color, lineThickness)
		self.painter.setPen(pen)

		path = QPainterPath()
		path.moveTo(self._time[0], plotData[0])
		for xPlot, yPlot in zip(plotData, self._time):
			path.lineTo(yPlot, xPlot)

		self.painter.drawPath(path)

	def plotText(self, position: QtCore.QPoint, string: str, color=QtCore.Qt.white):
		# lineThickness = self.height() * golden * 0.005
		# lineThickness = lineThickness if lineThickness > .01 else 0.01
		pen = QPen(color, 3)
		brush = QBrush(QtCore.Qt.black)
		self.painter.setPen(pen)
		self.painter.setBrush(brush)
		path = QPainterPath()
		path.moveTo(position)
		path.addText(position, self.font, string)
		self.painter.drawPath(path)

		pen = QPen(color, 0)
		brush = QBrush(QtCore.Qt.black)
		self.painter.setPen(pen)
		self.painter.setBrush(brush)
		path = QPainterPath()
		path.moveTo(position)
		path.addText(position, self.font, string)
		self.painter.drawPath(path)

	def normalizeToFrame(self, array, axis: int, offset: float = 0.0, frame: str = 'temp'):

		# start at leading margin
		# subtract the lowest value
		# height / peak to trough represents one unit value
		# shrink by top margin

		temp = self._data[frame]

		leading = axis * offset
		if self.height() == axis:
			return axis - (leading + (((array - self._min) * axis / self._p2p) * (1 - offset * 2)))
		return leading + (((array - temp.min()) * axis / np.ptp(temp)) * (1 - offset * 2))

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
		self.backgroundImage()

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


class GraphScene(QtWidgets.QGraphicsScene):
	time: dict
	temp: dict

	def __init__(self, *args, **kwargs):
		super(GraphScene, self).__init__(*args, **kwargs)

	def parseData(self):
		self.time = self._data['timestamp']
		self.temp = self._data['temp']

	def plotGraph(self):
		tmin = self.temp.min()
		tmax = self.temp.max()
		w = self.width()
		h = self.height()
		trange = tmax - tmin
		xlen = len(self.time)
		xm, ym = w, h
		xStep = xm / xlen
		yStep = ((trange / ym) - (ym * 0.2))
		yStep = ym / trange
		paint = QPainter()
		paint.begin(self)

		lineThickness = (w * h * 0.00001) if (w * h * 0.00001) > 2 else 2

		pen = QPen(QtCore.Qt.white, lineThickness)
		paint.setPen(pen)
		path = QPainterPath()

		firsty = (self.temp[0] - tmin) * yStep
		path.moveTo(0, firsty)

		for x in range(0, len(self.time)):
			y = (self.height() * 0.1) + ((self.temp[x] - tmin) * yStep) * 0.8
			path.lineTo(x * xStep, y)

		paint.drawPath(path)
		paint.end()


class GraphImage(QtWidgets.QFrame):

	def __init__(self, *args, **kwargs):
		super(GraphImage, self).__init__(*args, **kwargs)

		from tests.pickler import pans as reload
		data = reload('./tests/snapshots/202101031000')['surface_shortwave_radiation']

		hbox = QHBoxLayout(self)
		# img = Image.fromarray(self.image().astype('uint8'), 'RGB')
		img = Image.fromarray(self.image())
		# img.resize((self.width(), self.height()), Image.ANTIALIAS)
		qim = ImageQt(img)
		pix = QtGui.QPixmap.fromImage(qim)
		lbl = QLabel(self)
		w = self.width()
		h = self.height()
		lbl.setPixmap(pix)

	#   hbox.addWidget(lbl)
	# 		self.setLayout(hbox)
	#
	# 		self.show()

	def paintEvent(self, event):
		super(GraphImage, self).paintEvent(event)
		paint = QPainter()
		paint.begin(self)

		# img = img.scaled(50, 50, Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
		# p.drawPixmap(100, 0, img);
		# paint.drawPixmap(self.rect(), self.pix)
		paint.end()

	@staticmethod
	def normalize(a):
		return (a - np.min(a)) / np.ptp(a)

# def image(self, data: [dict]):
# 	norm = self.normalize(data)
# 	raw = []
# 	rS = 1.0
# 	gS = 0.85
# 	bS = 0.6
# 	aS = 1.0
# 	for i in range(0, 272):
# 		r, g, b, a = [norm[i]] * 4
# 		r *= rS
# 		g *= gS
# 		b *= bS
# 		a *= aS
# 		raw.append((r, g, b))
# 	raw = np.outer(np.ones(len(raw)), raw)
# 	raw = raw.reshape(272, 272, 3)
#
# 	raw *= 255
# 	raw = raw.astype(np.uint8)
# 	return QtGui.QImage(raw, 272, 272, QtGui.QImage.Format_RGB32)


if __name__ == '__main__':
	from tests.pickler import pans as reload

	app = QApplication()

	data = reload('../tests/snapshots/202101031000')
	# data = hourlyForecast()
	window = Graph()
	window.data = data
	window.show()

	sys.exit(app.exec_())
