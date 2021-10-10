import logging
import sys
from cmath import sin
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from math import radians
from random import randint
from typing import Dict, Iterable, List, NamedTuple, Optional, Tuple, Union

import numpy as np
from numpy import ndarray

from PySide2.QtCore import QLineF, QPoint, QPointF, QRectF, Qt, QTimer

from PIL.ImageQt import ImageQt
from PySide2.QtGui import QBrush, QColor, QFont, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPalette, QPen, QPixmap, QResizeEvent
from PySide2.QtWidgets import QApplication, QDesktopWidget, QGraphicsDropShadowEffect, QGraphicsItem, QGraphicsItemGroup, QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsScene, QGraphicsTextItem, QGraphicsView
from PIL import Image
from scipy import interpolate
from scipy.interpolate import interp1d
from WeatherUnits import Measurement, Temperature

import api.tomorrowIO
from src.api import API
from src.api.tomorrowIO import Fields, TomorrowIO, Field
from src.observations import ObservationForecast
from src.api.weatherFlow import WFStation
from src import colors, config
from src.api.forecast import Forecast
from src.utils import (ArrayMetaData, autoDType, closest_point_on_path, defaultMargins, filterBest, findPeaks, findPeaksAndTroughs, group, interpData, invertScale, Margins, normalize, Period, precipitationMargins, smoothData,
                       temperatureMargins, TimeFrame,
                       TimeLine, TimeLineCollection)
from src.colors import Default, kelvinToQColor, rgbHex
from src.fonts import rounded
from src.utils import Axis
from widgets.Complication import Complication
import sys
import os

golden = (1 + np.sqrt(5)) / 2

log = logging.getLogger(__name__)


@dataclass
class ComfortZones:
	freezing: Temperature = Temperature.Celsius(-10)
	cold: Temperature = Temperature.Celsius(5)
	chilly: Temperature = Temperature.Celsius(15)
	comfortable: Temperature = Temperature.Celsius(20)
	hot: Temperature = Temperature.Celsius(25)
	veryHot: Temperature = Temperature.Celsius(30)
	extreme: Temperature = Temperature.Celsius(40)

	@property
	def list(self) -> list[Temperature]:
		return list(asdict(self).values())

	@property
	def max(self):
		return Temperature.Celsius(50)

	@property
	def min(self):
		return self.freezing

	@property
	def ptp(self):
		return self.max - self.min


class TemperatureKelvinGradient(QLinearGradient):
	_figure: 'Figure'
	temperatures = ComfortZones()
	kelvinValues = [25000, 8000, 7000, 6500, 4000, 2500, 1500]

	maxTemp: Temperature = Temperature.Celsius(50)

	def __init__(self, figure: 'Figure'):
		super(TemperatureKelvinGradient, self).__init__()
		self.figure = figure
		start, stop = self.gradientPoints
		self.__genGradient()
		self.setStart(start)
		self.setFinalStop(stop)

	def __genGradient(self):
		v = 100 / self.maxTemp.localize

		unit = self.unit(1).unit
		x = np.array([self.temperatures.min[unit], self.temperatures.max[unit]])
		x = normalize(x, self.figure.dataRange)
		self.setColorAt(x[0], Qt.white)
		a = np.array([t[unit] for t in self.temperatures.list])
		locations = (a - self.temperatures.min[unit]) / (self.temperatures.max[unit] - self.temperatures.min[unit])
		for temperature, kelvin in zip(locations, self.kelvinValues):
			self.setColorAt(temperature, kelvinToQColor(kelvin))

	@property
	def figure(self):
		return self._figure

	@figure.setter
	def figure(self, value):
		self._figure = value

	@property
	def unit(self):
		return list(self.figure.data.values())[0].dataType

	@property
	def gradientPoints(self) -> Tuple[QPoint, QPoint]:
		unit = list(self.figure.data.values())[0].dataType(0)
		x = np.array([self.temperatures.min[unit.unit], self.temperatures.max[unit.unit]])
		x = normalize(x, self.figure.dataRange)
		m = self.figure.scene.height
		top = QPoint(0, x[1] * m)
		bottom = QPoint(0, x[0] * m)
		return top, bottom

	def update(self):
		start, stop = self.gradientPoints
		self.setStart(start)
		self.setFinalStop(stop)


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


class Graph(QGraphicsView):
	resizeTimer = QTimer()
	_timeframe = TimeFrame(timedelta(days=3))
	_pointerPosition = QPoint(0, 0)

	def __init__(self, *args, **kwargs):
		super(Graph, self).__init__(*args, **kwargs)
		self.setStyleSheet('background: black')
		self.setRenderHint(QPainter.HighQualityAntialiasing)
		self.setRenderHint(QPainter.Antialiasing)
		# self.setRenderHint(QPainter.SmoothPixmapTransform)
		scene = GraphScene(self)
		self.setScene(scene)
		self.resizeTimer.timeout.connect(self.updateGraphics)
		x = self.palette()
		x.setColor(QPalette.Text, QColor(colors.kelvinToQColor()))
		self.setPalette(x)
		self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
		self.setAcceptDrops(True)
		self.editor = GraphEditor(self)

	def scene(self) -> 'GraphScene':
		return super(Graph, self).scene()

	def dragMoveEvent(self, event):
		# super(Graph, self).dragMoveEvent(event)
		print(f'{event.pos()}\r', end='')

	def dragEnterEvent(self, event):
		if event.source().api.hasForecastFor(event.source().subscriptionKey):
			event.accept()
			self.tempItem = self.scene().addMeasurement(event.source())
		else:
			log.warning(f'{event.source().api} has not forecast data for {event.source().subscriptionKey}')

	# super(Graph, self).dragEnterEvent(event)

	# super(Graph, self).dragEnterEvent(event)

	def dragLeaveEvent(self, event):
		self.scene().removeMeasurement(self.tempItem)

	def dropEvent(self, event):
		self.tempItem.displayLabels = True
		self.tempItem = None
		self.update()

	def mousePressEvent(self, event: QMouseEvent):
		if self.items(event.pos()):
			event.ignore()
			super(Graph, self).mousePressEvent(event)
		else:
			event.accept()
			super(Graph, self).mousePressEvent(event)

	def resizeEvent(self, event: QResizeEvent) -> None:
		# self.scene().updateValues()
		self.resizeTimer.start(300)

	@property
	def data(self):
		return self.scene().figures

	@data.setter
	def data(self, value):
		self.scene().data = value

	def updateGraphics(self):
		try:
			# self.scene().s.setEnabled(False)
			# for item in self.scene().items():
			# 	item.updateItem()
			# self.fitInView(self.scene(), Qt.AspectRatioMode.KeepAspectRatio)
			rcontent = self.contentsRect()
			self.scene().updateValues()
			sceneRect = self.scene().sceneRect()
			self.setSceneRect(10, sceneRect.top(), sceneRect.width(), rcontent.height())
		# self.setSceneRect(rcontent)
		# self.setSceneRect(self.scene().sceneRect())
		except Exception as e:
			print(e)
		self.resizeTimer.stop()

	@property
	def timeframe(self):
		if self._timeframe is None:
			self._timeframe = TimeFrame(timedelta(days=3))
		return self._timeframe

	@property
	def state(self):
		return {'figures': {k: v.state for k, v in self.scene().figures.items()}}


class SoftShadow(QGraphicsDropShadowEffect):
	def __init__(self, *args, **kwargs):
		super(SoftShadow, self).__init__(*args, **kwargs)
		self.setOffset(0.0)
		self.setBlurRadius(60)
		self.setColor(Qt.black)


class HoverHighlight(QGraphicsDropShadowEffect):
	def __init__(self, *args, **kwargs):
		super(HoverHighlight, self).__init__(*args, **kwargs)
		self.setOffset(0.0)
		self.setBlurRadius(60)
		self.setColor(Qt.white)


class GraphScene(QGraphicsScene):
	parent: Graph
	lineWeight: float
	font: QFont = QFont("SF Pro Rounded", 80)
	figures: Dict[str, 'Figure']

	def __init__(self, parent, *args, **kwargs):
		self.parent = parent
		self.fontSize = min(max(self.height * 0.1, 30, min(self.width * 0.06, self.height * .2)), 100)
		self.lineWeight = self.plotLineWeight()
		super(GraphScene, self).__init__(*args, **kwargs)
		self.setColors()
		self.figures: Dict[str, 'Figure'] = {}

	def resizeEvent(self, event):
		self.fontSize = min(max(self.height * 0.1, 30, min(self.width * 0.06, self.height * .2)), 100)
		self.lineWeight = self.plotLineWeight()
		super(GraphScene, self).resizeEvent(event)

	def addMeasurement(self,
	                   item: Union[str, Measurement, Complication] = None,
	                   field: str = None,
	                   api: Union[str, API] = None,
	                   figure: Union[str, 'Figure'] = None, **params):

		if item is not None:
			if isinstance(item, Complication):
				if isinstance(item.value, Measurement):
					if api is None:
						api = item.api
					item = item.value
					field = item.subscriptionKey
			elif isinstance(item, str):
				field = item

		if figure is None:
			if hasattr(item, 'name'):
				figureName = item.name
			else:
				figureName = api[field][0].name
			figure = self.figures.get(figureName, Figure(self))
			self.figures[figureName] = figure

		item = figure.addItem(field, api, **params)
		figure.update()

		self.update(self.parent.rect())
		return item

	def removeMeasurement(self, item: QGraphicsItem):
		figure = item.figure
		item.figure.removeItem(item)
		figure.update()
		self.update(self.parent.rect())

	def plot(self):

		for items in self.figures.values():
			for x in items.plots():
				self.addItem(x)

	# temperatureFigure = Figure(self, self.data['datetime'], margins=temperatureMargins)
	# precipitationFigure = Figure(self, self.data['datetime'], margins=precipitationMargins)
	# self.clear()
	# temperatureFigure.addItem('Dewpoint', self.data['dewpoint'], pathType=PathType.Linear)
	# temperatureFigure.addItem('Temperature', self.data['temperature'], pathType=PathType.Linear)
	# temperatureFigure.addItem('Feels Like', self.data['feelsLike'], pathType=PathType.Linear)
	# precipitationFigure.addItem('Accumulation', self.data['epaIndex'], pathType=PathType.Linear)
	# t = TemperatureKelvinGradient(temperatureFigure)
	# for x in temperatureFigure.plots():
	# 	self.addItem(x)
	# for x in precipitationFigure.plots():
	# 	self.addItem(x)
	# # self.color = self.parent.palette().text().color()
	# # t = np.linspace(100,0,272)
	# # t = normalize(t) * self.height
	# # plot = Plot(self, 't', array=t)
	# # self.addItem(plot)
	# # self.addItem(BackgroundImage(self, self._data['surface_shortwave_radiation']))
	# # self.addItem(Plot(self, 'feelsLike', style=[1, 3], scalar=.5))
	# # self.addItem(Plot(self, 'dewpoint', style=[1, 3], scalar=.5))
	# # # self.addItem(Plot(self, 'dewpoint', self.babyBlue, [2, 3], scalar=.3))
	# # # for m in ['wind_speed', 'precipitation_probability', 'precipitation', 'precipitation_accumulation']:
	# # # for m in ['precipitation_accumulation']:
	# # # self.addItem(Plot(self, 'precipitation', color=self.babyBlue, style=[1, 3], scalar=.5))
	# # self.addItem(self.barGraph())
	# # self.addItem(Plot(self, 'precipitation_accumulation', color=colors.Rain.maya, scalar=.5, morph='precipitation'))
	# # self.addItem(Plot(self, 'wind_speed', color=self.color, scalar=.5))
	# # x = LineMarkers(self, 'hours', style=[9, 9], alpha=0.4, scalar=0.2)
	# # self.existingPlots.append(x)
	# # self.addItem(x)
	# # x = LineMarkers(self, 'days', scalar=0.5, alpha=0.8)
	# # self.existingPlots.append(x)
	# # self.addItem(x)
	# # self.addItem(TwinPlot(self, 'cloud_cover', 1.0, color=self.color))
	# # self.addAnnotations()
	# # self.addDayNames()

	def barGraph(self):
		bar = QGraphicsPathItem()
		bar.setBrush(QBrush(colors.Rain.freshAir))
		bar.setPen(QColor(None))
		barPath = QPainterPath()
		numberOfBars = len(self.data['precipitation_probability'])
		width = self.width / numberOfBars
		for i, prob in enumerate(self.data['precipitation_probability']):
			if prob > 0:
				xPos = i * width
				rect = QRectF(xPos, 10, width * 0.9, 250 * prob / 100)
				rect.moveBottom(self.height + 10)
				barPath.addRoundedRect(rect, 5, 5)
		bar.setPath(barPath)
		return bar

	def setColors(self):
		self.faded = QColor(255, 255, 255, 128)
		self.babyBlue = QColor(100, 232, 252)

	def addAnnotations(self):
		for item in self._peaks:
			t = PlotAnnotation(self, item, 'temperature')
			self.addItem(t)
		for item in self._troughs:
			t = PlotAnnotation(self, item, 'temperature', Qt.AlignBottom, color=self.color)
			self.addItem(t)

	def addDayNames(self):
		for i, item in enumerate(self.hours.dates):
			item: datetime
			if item.hour == 12:
				p = self.mappedData['hours'][i]
				v = item.day
				t = MarkerAnnotation(self, i, 'hours', color=self.color, scalar=1.2)
				self.addItem(t)

	def updateValues(self) -> None:
		self.fontSize = min(max(self.height * 0.1, 30, min(self.width * 0.06, self.height * .2)), 100)
		self.lineWeight = self.plotLineWeight()
		for figure in self.figures.values():
			figure.update()
		self.update(self.parent.rect())

	# self.gradientPoints = self.genGradientLocations()
	# self.mapData()

	@property
	def height(self):
		return self.parent.height()

	@property
	def width(self):
		return self.parent.width()

	@property
	def data(self):
		return self._data

	@data.setter
	def data(self, data: Forecast):

		# d = data['temperature']
		# d = (d - d.min(axis=0)) / (d.max(axis=0) - d.min(axis=0)) * 120
		# data['temperature'] = d
		self._data = data

		start, finish = data['datetime'][0], data['datetime'][-1]
		self.hours = TimeMarkers(start, finish, timedelta(hours=6), mask=[0])
		self.days = TimeMarkers(start, finish, timedelta(days=1))
		self.updateValues()
		self.plot()

	def plotLineWeight(self) -> float:
		weight = self.parent.height() * golden * 0.005
		weight = weight if weight > 8 else 8.0
		return weight


class CachedList(list):

	def __clearCache(self):
		pass

	def append(self, item):
		self.__clearCache()
		super(CachedList, self).append(item)

	def insert(self, index, item):
		self.__clearCache()
		super(CachedList, self).insert(index, item)

	def extend(self, *args, **kwargs):
		self.__clearCache()
		super(CachedList, self).extend(*args, **kwargs)

	def pop(self, *args, **kwargs):
		self.__clearCache()
		super(CachedList, self).pop(*args, **kwargs)

	def remove(self, *args, **kwargs):
		self.__clearCache()
		super(CachedList, self).remove(*args, **kwargs)

	def reverse(self):
		self.__clearCache()
		super(CachedList, self).reverse()

	def sort(self, *args, **kwargs):
		self.__clearCache()
		super(CachedList, self).sort(*args, **kwargs)

	def __add__(self, *args, **kwargs):
		self.__clearCache()
		super(CachedList, self).__add__(*args, **kwargs)

	def __iadd__(self, *args, **kwargs):
		self.__clearCache()
		super(CachedList, self).__iadd__(*args, **kwargs)


class GraphItemData:
	_rasterValues: Optional[ndarray] = None
	_troughs: Optional[List[int]] = None
	_peaks: Optional[List[int]] = None
	_multiplier: Optional[timedelta] = timedelta(minutes=15)
	_window: Optional[int] = None
	_order: Optional[int] = None
	_array: Optional[ndarray] = None
	_interpolated: Optional[ndarray] = None
	_smoothed: Optional[ndarray] = None
	_smooth: bool
	_length: Optional[int] = None
	_figure: 'Figure'
	_numerical: Optional[bool] = None
	_interpolate: bool
	_pathType: 'PathType'
	_allGraphics: QGraphicsItemGroup = None
	_graphic: Optional[QGraphicsItem] = None
	_labels: Optional[list[QGraphicsItem]] = None
	_timeframe: Optional[TimeLine] = None
	_raw: list
	_api: API
	_field: str
	_labels: bool

	def __init__(self,
	             field: str,
	             api: API,
	             parent: 'Figure' = None,
	             interpolate: bool = True,
	             smooth: bool = True,
	             spread: int = 31,
	             order: int = 3,
	             visualInfo: dict = {}):

		self._api = api
		self._field = field
		self._raw = []
		self._path = None
		self._figure = parent
		self._interpolate = interpolate
		self._smooth = smooth
		self.spread = spread
		self.order = order
		self._timeframe = TimeLine(self)
		self._visualInfo = visualInfo

	# api.hourly.signalDispatcher.signal.connect(self.receiveUpdate)

	@property
	def labeled(self) -> bool:
		return self.labels.isVisible()

	@labeled.setter
	def labeled(self, value: bool):
		self.labels.setVisible(value)

	@property
	def rawData(self) -> list:
		return self._api.hourly[self._field]

	def splitDays(self):
		earliest = self.rawData[0].timestamp
		start = datetime(year=earliest.year, month=earliest.month, day=earliest.day, tzinfo=earliest.tzinfo)
		days = []
		day = []
		currentDay = start + timedelta(days=1)
		for value in self.rawData:
			if value.timestamp < currentDay:
				day.append(value)
			else:
				currentDay += timedelta(days=1)
				days.append(day)
				day = [value]
		return days

	@property
	def highsLows(self):
		now = datetime.now().astimezone(config.tz)
		return {(i[0].timestamp - now).days: {'high': max(i), 'low': min(i)} for i in self.splitDays()}

	@property
	def type(self):
		return '.'.join(str(type(self.rawData[0])).split('.')[1:3])

	@property
	def field(self):
		return self._field

	def __clearCache(self):
		self._array = None
		self._peaks = None
		self._troughs = None
		self._numerical = None
		self._interpolated = None
		self._smoothed = None
		self._rasterValues = None
		self._graphic = None
		self._raw = None

	def clear(self):
		self.__clearCache()

	def __peaksAndTroughs(self):
		# Still needs work but doesn't require scipy
		# a = self.highsLows
		# self._peaks = [i['high'] for i in a.values()]
		# self._troughs = [i['low'] for i in a.values()]
		peaks, troughs = findPeaksAndTroughs(list(self.smoothed), spread=6)
		self._peaks = filterBest(peaks, self.rawData, indexes=False, high=True)
		self._troughs = filterBest(troughs, self.rawData, indexes=False, high=False)

	# peaks, troughs = findPeaksAndTroughs(list(self.smoothed), spread=4)
	# self._peaks = filterBest(peaks, self.smoothed, True)
	# self._troughs = filterBest(troughs, self.smoothed, False)

	def interp(self):
		x = np.array([t.timestamp.timestamp() for t in self.rawData])
		y = np.array(self.rawData)
		f = interp1d(x, y, kind='cubic')
		f = self._figure.interpField
		return f(x, y)

	####### This may not be working!  About to work through how to make gradient points
	def normalizeToFrame(self, x, y) -> Union[QPointF, list[QPointF]]:
		"""
		:param axis: Vertical or Horizontal
		:param margins: Margins of figure
		:return: Normalized
		"""
		margins = self._figure.margins

		if self.scene.parent.geometry().bottom():
			offsetValueH = margins.top
		else:
			offsetValueH = margins.bottom
		offsetValueW = margins.left

		# Multiply array by axis size
		mulH = self.scene.height
		mulW = self.scene.width
		dataRange = self._figure.dataRange
		y = -((y - dataRange.min) / dataRange.range) + 1
		x = (x - self.scene.parent.timeframe.min.timestamp()) / self.scene.parent.timeframe.rangeSeconds

		y = (y * margins.span(Axis.y) + offsetValueH) * mulH
		x = (x * margins.span(Axis.x) + offsetValueW) * mulW
		if isinstance(x, Iterable) and isinstance(y, Iterable):
			return [QPointF(ix, iy) for ix, iy in zip(x, y)]
		return QPointF(x, y)

	@property
	def plotValues(self) -> tuple[ndarray, ndarray]:
		# x = np.array([y.timestamp.timestamp() for y in self.rawData])
		# x -= x.min()
		# y = np.array(self.rawData)
		# y = smoothData(y, 17, 5)
		# x_new = np.linspace(0, x.max(), int(x.max() / 60) + 1)

		# return self.normalizeToFrame(self.timeArray, self.smoothed)
		self.__peaksAndTroughs()
		return self.normalizeToFrame(self.timeArrayInterpolated, self.interpolated)

	# x_new = np.array([y.timestamp.timestamp() for y in self.rawData])
	# y_new = y
	# y_normal = -((y_new - y_new.min()) / y_new.ptp()) + 1
	# x_normal = (x_new - x_new.min()) / timedelta(days=3).total_seconds()

	@property
	def scene(self) -> GraphScene:
		return self._figure.scene

	@property
	def figure(self) -> 'Figure':
		return self._figure

	@property
	def peaks(self) -> List[Measurement]:
		if self._peaks is None:
			self.__peaksAndTroughs()
		return self._peaks

	@property
	def troughs(self) -> List[Measurement]:
		if self._troughs is None:
			self.__peaksAndTroughs()
		return self._troughs

	def genLabels(self):
		values = self.highsLows
		# peak = self.normalizeToFrame(np.array([i.timestamp.timestamp() for i in self.peaks]), np.array(self.peaks))
		# trough = self.normalizeToFrame(np.array([i.timestamp.timestamp() for i in self.troughs]), np.array(self.troughs))
		peaks = [PlotAnnotation(self, value) for value in self.peaks]
		troughs = [PlotAnnotation(self, value, alignment=Qt.AlignBottom) for value in self.troughs]
		self._labels = self.scene.createItemGroup([*peaks, *troughs])

	# self._labels = [a for b in [[PlotAnnotation(self, v['high']), PlotAnnotation(self, v['low'], alignment=Qt.AlignBottom)] for v in values.values()] for a in b]

	@property
	def labels(self) -> QGraphicsItemGroup:
		# self.scene.updateValues()
		# peak = self.normalizeToFrame(np.array([i.timestamp.timestamp() for i in self.peaks]), np.array(self.peaks))
		# trough = self.normalizeToFrame(np.array([i.timestamp.timestamp() for i in self.troughs]), np.array(self.troughs))
		# self.peakLabels = []
		# self.troughLabels = []
		# for x, t in zip(peak, peak):
		# 	self.peakLabels.append(Text(self.scene, x.x(), x.y() - 20, str(t), alignment=Qt.AlignTop, color=Qt.white))
		# for x, t in zip(trough, trough):
		# 	self.troughLabels.append(Text(self.scene, x.x(), x.y() + 40, str(t), alignment=Qt.AlignBottom, color=Qt.white))
		#
		# return [*self.peakLabels, *self.troughLabels]

		if self._labels is None:
			self.genLabels()
			self._labels.setZValue(100)
		return self._labels

	@property
	def normalized(self):
		meta = self._figure.dataRange if self._figure is not None else None
		return -normalize(self.rawData, meta) + 1  # QPainterPath draws from the top left instead of bottom left so flip the values

	@property
	def array(self) -> ndarray:
		return np.array(self.rawData, dtype=self.dtype)
		if self._array is None:
			self._array = np.array(self.rawData, dtype=self.dtype)
		return self._array

	@property
	def timeArray(self) -> ndarray:
		x = np.array([y.timestamp.timestamp() for y in self.rawData])
		return x

	@property
	def timeArrayInterpolated(self):
		# if not self._interpolated:
		# 	return self.timeArray
		x_min = self.rawData[0].timestamp.timestamp()
		x_max = self.rawData[-1].timestamp.timestamp()
		return np.linspace(x_min, x_max, int(len(self.rawData) * self.multiplier))

	@property
	def interpolated(self) -> ndarray:
		f = interpolate.interp1d(self.timeArray, self.smoothed, kind='cubic')
		return f(self.timeArrayInterpolated)
		# if not self._interpolate or not self.isInterpolatable:
		# 	return self.array
		print('building interp')
		if self._interpolated is None:
			f = interpolate.interp1d(self.timeArray, self.smoothed, kind='cubic')
			# self._interpolated = interpData(self.smoothed, self.multiplier, self.length)
			self._interpolated = f(self.timeArrayInterpolated)
		return self._interpolated

	@property
	def smoothed(self) -> ndarray:
		return smoothData(self.array, 17, 5)
		# if not self._smooth or not self.isInterpolatable:
		# 	return self.array
		if self._smoothed is None:
			# return self.interpolated
			# kernel_size = 20l
			# kernel = np.ones(kernel_size) / kernel_size
			# self._smoothed = np.convolve(self.interpolated, kernel, mode='same')
			# y = smoothData(, 17, 5)
			self._smoothed = smoothData(self.array, 17, 5)
		return self._smoothed

	@property
	def data(self) -> ndarray:
		return self.interpolated

	@property
	def dataType(self) -> type:
		return self.rawData[0].__class__

	@property
	def isInterpolatable(self) -> bool:
		return (self.isNumbers or isinstance(self.rawData[0], datetime)) and self._interpolate

	@property
	def isNumbers(self) -> bool:
		if self._numerical is None:
			try:
				sum(self.rawData)
				self._numerical = True
			except TypeError:
				self._numerical = False
		return self._numerical

	@property
	def multiplier(self) -> timedelta:
		if self._multiplier is None:
			return max(int(self.length / len(self)), 1)
		return int(self._api.hourly.period.total_seconds() / self._multiplier.total_seconds())

	@property
	def multiplierRaw(self) -> int:
		return int(self._multiplier.total_seconds() / 60)

	@multiplier.setter
	def multiplier(self, value: Union[int, timedelta]):
		if isinstance(value, int):
			value = timedelta(minutes=value)
		self._multiplier = value
		self._length = None

	@property
	def dtype(self):
		if self.isNumbers:
			return autoDType(self.rawData)
		return

	@property
	def length(self) -> int:
		if self._length is None:
			return len(self.rawData) * max(self.multiplier, 1)
		return self._length

	@length.setter
	def length(self, value: int):
		self._multiplier = None
		self.__clearCache()
		self._length = int(value)

	@property
	def spread(self) -> int:
		return self._window

	@spread.setter
	def spread(self, value: int):
		self.__clearCache()
		self._window = value

	@property
	def order(self) -> int:
		return self._order

	@order.setter
	def order(self, value: int):
		self.__clearCache()
		self._order = value

	@property
	def graphic(self) -> QGraphicsItem:

		if self._graphic is None:
			params = self._visualInfo
			if 'type' in params:
				graphicType = params.pop('type')
			self._graphic = Plot(self, **params)
		return self._graphic

	@property
	def allGraphics(self):
		if self._allGraphics is None:
			self._allGraphics = self.scene.createItemGroup([self.graphic, self.labels])
		return self._allGraphics

	@property
	def timeframe(self):
		return self._timeframe

	def update(self):
		self.graphic.prepareGeometryChange()
		self.graphic.update()
		# self.scene.addItem(self.graphic)
		for label in self.labels.childItems():
			label.show()
		for label in self.labels.childItems():
			label.update()

	def receiveUpdate(self, value):
		self.update()

	@property
	def state(self):
		return {
				'api':        self._api.name,
				'visualInfo': self.graphic.state,
				'field':      self._field,
				'labeled':    self.labeled,
				'zOrder':     self.allGraphics.zValue()
		}


# class TimeAxis(GraphItemData):
# 	_timeSpacingMinutes: int = 15
# 	_axis: Axis = Axis.x
# 	_figure: 'Figure'
#
# 	def __init__(self, data: Iterable, parent: 'Figure' = None):
# 		self._figure = parent
# 		super(TimeAxis, self).__init__(data, parent, interpolate=True, multiplier=None, length=None, spread=None, order=None)
#
# 	@property
# 	def array(self) -> ndarray:
# 		if self._array is None:
# 			self._array = np.array(self)
# 		return self._array
#
# 	@property
# 	def data(self):
# 		return self.interpolated
#
# 	@property
# 	def normalized(self):
# 		return normalize(self.array, self._figure.timeFrame)
#
# 	@property
# 	def interpolated(self) -> ndarray:
# 		if self._interpolated is None:
# 			self._interpolated = interpData(self.normalized, self.multiplier)
# 		return self._interpolated
#
# 	@property
# 	def smoothed(self) -> ndarray:
# 		return self.interpolated
#
# 	@property
# 	def multiplier(self):
# 		a = (self.array[1:, ] - self.array[:-1]).mean().total_seconds() / (self._timeSpacingMinutes * 60)
# 		return a if a < 1 else int(a)
#
# 	@property
# 	def length(self):
# 		return len(self.data)
#
# 	@property
# 	def lengthTime(self) -> timedelta:
# 		return self._figure.timeFrame.range


class Figure:
	_default: str = None
	_margins: Margins
	# _subPlots: list['GraphItem'] = None
	_scene: GraphScene
	_dataRange: Optional[ArrayMetaData] = None
	data: dict[str, GraphItemData]

	def __init__(self, scene: GraphScene, margins: Margins = None, data: dict[str] = None):
		self.data = {}
		self._scene = scene
		self._margins = margins if margins is not None else Margins()
		self.editor = FigureEditor(self)

	@property
	def dataRange(self):
		if self._dataRange is None:
			self._dataRange = ArrayMetaData(self)
		return self._dataRange

	@property
	def name(self):
		a = set([item.type for item in self.data.values()])
		if len(a) > 1:
			return '/'.join(a)
		else:
			return list(a)[0]

	@property
	def scene(self) -> GraphScene:
		return self._scene

	@scene.setter
	def scene(self, value):
		self._scene = value

	@property
	def timeline(self):
		tMax = max([i.timeframe.max for i in self.data.values()])
		tMin = min([i.timeframe.min for i in self.data.values()])
		return TimeLineCollection(tMax, tMin, tMax - tMin)

	def addItem(self, field: str, api: API, labeled: bool = False, zOrder: Optional[int] = None, visualInfo: dict = {}):
		item = GraphItemData(field, api, self, visualInfo=visualInfo)

		self.data[field] = item
		self.scene.addItem(item.graphic)
		self.scene.addItem(item.graphic.hoverArea)
		item.labeled = labeled
		if zOrder is not None:
			item.allGraphics.setZValue(zOrder)
			item.graphic.hoverArea.setZValue(200)
		return item

	def removeItem(self, item: GraphItemData):
		self.data.pop(item.field)
		self.scene.removeItem(item.allGraphics)
		del item

	# for label in item.labels:
	# 	self.scene.addItem(label)

	# def removeItem(self, item: 'Plot'):
	# 	plot = item
	# 	item = item.data
	# 	key = [k for k, v in self.data.items() if v == item][0]
	# 	item = self.data.pop(key)
	# 	self.scene.removeItem(plot)

	@property
	def interpField(self):
		from scipy import interpolate
		t = self.timeline
		d = self.dataRange
		stepT = self.scene.width / t.range.total_seconds()
		x = np.arange(t.min.timestamp(), t.max.timestamp(), 60)
		y = np.arange(d.min, d.max, d.range / self.scene.height)
		xx, yy = np.meshgrid(x, y)
		z = np.sin(xx ** 2 + yy ** 2)
		return interpolate.interp2d(x, y, z, kind='cubic')

	@property
	def margins(self) -> Margins:
		return self._margins

	def update(self):
		for x in self.data.values():
			x.update()
		self.scene.update(self.scene.sceneRect())

	@property
	def state(self):
		return {
				'margins': self.margins.state,
				'data':    {k: v.state for k, v in self.data.items()}
		}


class PathType(Enum):
	Linear = 0
	Cubic = 2
	Quadratic = 3
	Spline = 4


class HoverArea(QGraphicsPathItem):
	parentItem: QGraphicsItem

	def __init__(self, parent: QGraphicsItem):
		super(HoverArea, self).__init__()
		self.parentItem = parent
		# self.setPen(None)
		# self.setBrush(None)
		q_pen = QPen(Qt.black, 0)
		q_pen.setColor(QColor(0, 0, 0, 0))
		self.setPen(q_pen)
		self.setAcceptHoverEvents(True)

	def hoverEnterEvent(self, event):
		event.accept()
		self.parentItem.setGraphicsEffect(HoverHighlight())
		# print(f'Hovering {self.parentItem.data._field}\r', end='')
		super(HoverArea, self).hoverMoveEvent(event)

	def hoverMoveEvent(self, event):
		super(HoverArea, self).hoverMoveEvent(event)

	def hoverLeaveEvent(self, event):
		self.parentItem.setGraphicsEffect(None)
		# print(f'Leaving {self.parentItem.data._field}\r', end='')
		super(HoverArea, self).hoverLeaveEvent(event)

	def mousePressEvent(self, event):
		self.parentItem.figure.editor.currentItem = self.parentItem.data
		if self.parentItem.figure.editor.proxy in self.parentItem.figure.scene.items():
			e = self.parentItem.figure.editor.proxy
		else:
			if self.parentItem.figure.editor.proxy is None:
				self.parentItem.figure.editor.proxy = self.parentItem.figure.scene.addWidget(self.parentItem.figure.editor)
			else:
				self.parentItem.figure.scene.addItem(self.parentItem.figure.editor.proxy)
			e = self.parentItem.figure.editor.proxy
		g: QRectF = e.geometry()
		g.moveCenter(QPoint(event.pos().x(), event.pos().y()))
		containter = self.parentItem.figure.scene.parent.rect()

		if g.left() < containter.left():
			g.moveLeft(containter.left())
		if g.right() > containter.right():
			g.moveRight(containter.right())
		if g.top() < containter.top():
			g.moveTop(containter.top())
		if g.bottom() > containter.bottom():
			g.moveBottom(containter.bottom())

		e.setGeometry(g)
		e.widget().show()
		e.setZValue(150)
		i = self.parentItem.figure.editor.selectedValueComboBox.findData(self.parentItem.data)
		self.parentItem.figure.editor.selectedValueComboBox.setCurrentIndex(i)

	# self.parentItem.data.clear()
	# super(HoverArea, self).mousePressEvent(event)

	def update(self):
		values: QPainterPath = self.parentItem.path()
		rough = [values.elementAt(i) for i in range(0, values.elementCount(), 3)]
		path = self.path()
		path.clear()
		path.moveTo(rough[0])

		for v in rough:
			path.lineTo(v.x, v.y + 15)
		rough.reverse()
		for v in rough:
			path.lineTo(v.x, v.y - 15)

		path.closeSubpath()

		self.setPath(path)
		super(HoverArea, self).update()


class Plot(QGraphicsPathItem):
	_dashPattern: list[int]
	_type: PathType
	figure: Figure
	data: GraphItemData
	_style: Qt.PenStyle
	_scalar: float
	pathType: PathType
	_gradient: bool = False
	_temperatureGradient: Optional[TemperatureKelvinGradient] = None

	def __init__(self, parent: GraphItemData,
	             color: QColor = Qt.white,
	             dashPattern: Union[Qt.PenStyle, Iterable, str] = Qt.SolidLine,
	             scalar: float = 1.0):

		self.data: GraphItemData = parent
		self.figure: Figure = parent.figure
		self.color = color
		self.dashPattern = dashPattern
		self.scalar = scalar
		self._path = QPainterPath()
		# self.gradient = self.setGradient(True)

		# if morph:
		# 	data = self.figure.
		# 	if type(morph) == str:
		# 		morph = self.figure.data[morph]
		# 	if len(data) != len(morph):
		# 		morph = interpData(morph, newLength=len(data))
		# 	morph = normalize(morph) * 10
		# self.morph = morph
		super(Plot, self).__init__()
		self.hoverArea = HoverArea(self)
		self.update()
		self.setAcceptHoverEvents(True)

	def setGradient(self, value: bool):
		if value and self._temperatureGradient is None:
			self._temperatureGradient = TemperatureKelvinGradient(self.figure)
		self._gradient = value

	@property
	def scalar(self) -> float:
		return self._scalar

	@scalar.setter
	def scalar(self, value: Union[str, float, int]):
		if not isinstance(value, float):
			value = float(value)
		self._scalar = value

	@property
	def color(self):
		return self._color

	@color.setter
	def color(self, value):
		if isinstance(value, str):
			if '#' in value:
				value = QColor(value)
		self._color = value

	@property
	def api(self) -> API:
		return self._api

	@property
	def figure(self) -> Figure:
		return self._figure

	@figure.setter
	def figure(self, value: Figure):
		self._figure = value

	@property
	def state(self):
		return {
				'type':        'Plot',
				'scalar':      str(self.scalar),
				'dashPattern': self.dashPattern,
				'color':       rgbHex(*QColor(self.color).toTuple()[:3])
		}

	@property
	def dashPattern(self):
		if isinstance(self._dashPattern, Qt.PenStyle):
			return QPen(self._dashPattern).dashPattern()
		return self._dashPattern

	@dashPattern.setter
	def dashPattern(self, value):

		def convertPattern(value: str) -> list[int]:
			if not isinstance(value, str):
				return value
			pattern = []
			if ',' in value:
				pattern = [int(v) for v in value.strip('[]').split(',') if v.strip().isdigit()]
			elif '-' in value:
				value = [ch for ch in value]
				lastChar = value[0]
				val = 0
				for ch in value:
					if ch == lastChar:
						val += 1
					else:
						pattern.append(val)
						lastChar = ch
						val = 1
				pattern.append(val)
			if len(pattern) % 2:
				pattern.append(0)
			return pattern

		self._dashPattern = convertPattern(value)

	def __repr__(self):
		return f"Plot {hex(id(self))} of '{self.data._field}' in figure '{self.figure.name}'"

	def _generatePen(self):
		weight = self.figure.scene.plotLineWeight() * self.scalar
		brush = QBrush(self.color)
		# self._temperatureGradient.update()
		# brush = QBrush(self._temperatureGradient)
		pen = QPen(brush, weight)
		if isinstance(self.dashPattern, Iterable):
			pen.setDashPattern(self.dashPattern)
		else:
			pen.setStyle(self.dashPattern)
		return pen

	def _updatePath(self):
		values = self.__getValues()
		for value in values:
			self._path.lineTo(value)
		self.setPath(self._path)

	def __getValues(self) -> list[QPointF]:
		self._path = QPainterPath()
		values = self.data.plotValues
		if len(values) > 1200:
			log.warning(f'Plot path contains {len(values)} points and will result in performance issues')
		self._path.moveTo(values[0])
		return values

	# # Hover Area
	# rough = [values[i] for i in range(0, len(values), 3)]
	# if values[-1] != rough[-1]:
	# 	rough.append(values[-1])
	#
	# self._path.moveTo(rough[0])
	# for value in rough:
	# 	value.setY(value.y() - 10)
	# 	self._path.lineTo(value)
	# values.reverse()
	# for value in rough:
	# 	value.setY(value.y() + 20)
	# 	self._path.lineTo(value)
	#
	# self._path.closeSubpath()

	def __spline(self):

		'''Currently broken.  Needs to be updated to the format found in __linear()'''

		path, xa, ya = self.__getValues()
		points = [QPointF(x, y) for x, y in zip(xa, ya)]
		path.moveTo(points[0])
		factor = .15
		for p in range(len(points) - 2):
			p2 = points[p + 1]
			target = QLineF(p2, points[p + 2])
			reverseTarget = QLineF.fromPolar(
					target.length() * factor, target.angle() + 180).translated(p2)
			if not p:
				path.quadTo(reverseTarget.p2(), p2)
			else:
				p0 = points[p - 1]
				p1 = points[p]
				source = QLineF(p0, p1)
				current = QLineF(p1, p2)
				targetAngle = target.angleTo(current)
				if 90 < targetAngle < 270:
					ratio = abs(sin(radians(targetAngle)))
					reverseTarget.setLength(reverseTarget.length() * ratio)
				reverseSource = QLineF.fromPolar(
						source.length() * factor, source.angle()).translated(p1)
				sourceAngle = current.angleTo(source)
				if 90 < sourceAngle < 270:
					ratio = abs(sin(radians(sourceAngle)))
					reverseSource.setLength(reverseSource.length() * ratio)
				path.cubicTo(reverseSource.p2(), reverseTarget.p2(), p2)

		final = QLineF(points[-3], points[-2])
		reverseFinal = QLineF.fromPolar(
				final.length() * factor, final.angle()).translated(final.p2())
		path.quadTo(reverseFinal.p2(), points[-1])
		path.setFillRule(Qt.OddEvenFill)
		return path

	def __cubic(self) -> QPainterPath:

		'''Currently broken.  Needs to be updated to the format found in __linear()'''

		path, x, y = self.__getValues()
		i = 0
		while i < len(x) - 3:
			c1 = QPointF(x[i], y[i])
			c2 = QPointF(x[i], y[i])
			# c2 = QPointF(x[i + 1], y[i + 1])
			endPt = QPointF(x[i + 1], y[i + 1])
			i += 2
			path.cubicTo(c1, c2, endPt)
		return path

	def __quadratic(self) -> QPainterPath:

		'''Currently broken.  Needs to be updated to the format found in __linear()'''

		path, x, y = self.__getValues()
		i = 0
		while i < len(x) - 2:
			c = QPointF(x[i], y[i])
			endPt = QPointF(x[i + 1], y[i + 1])
			i += 2
			path.quadTo(c, endPt)
		return path

	def update(self):
		self.setPen(self._generatePen())
		self._updatePath()
		self.hoverArea.update()
		super(Plot, self).update()


class TwinPlot(QGraphicsPathItem):
	def __init__(self, parent,
	             dataSelector: str,
	             position: float,
	             mapped: bool = False,
	             morph: str = None,
	             color: QColor = Default.main,
	             margins: Margins = defaultMargins):
		self.parent: GraphScene = parent
		self.color = color
		self.position = position
		self.morph = morph
		self.mapped = mapped
		self.margins = margins
		self.selector = dataSelector
		super(TwinPlot, self).__init__()
		self.setGraphicsEffect(SoftShadow())
		# self.setPen(self.genPen())
		self.setBrush(QBrush(color))
		self.setPen(QPen(QColor(color)))
		self.setPath(self.genPath())

	def genPath(self) -> QPainterPath:
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


class LineMarkers(QGraphicsPathItem):

	def __init__(self, parent: GraphScene, markerArray: str, color: QColor = Default.main, style: Union[Qt.PenStyle, list[int]] = Qt.SolidLine, scalar: float = 1.0, **kwargs):
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
				log.warning(f'Unable to set with {value} of type {value.__class__.__name__}')

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


class GraphicText(QGraphicsTextItem):

	def __init__(self, parent, x: float, y: float, text: str, alignment: Qt.AlignmentFlag = Qt.AlignCenter,
	             scalar: float = 1.0, font: Union[QFont, str] = None, color: QColor = None):
		super(GraphicText, self).__init__('')
		self.parent = parent
		self._x = x
		self._y = y
		self._text = text
		self._font = font
		self._alignment = alignment
		self._scalar = scalar
		self._color = color

	def estimateTextSize(self, font: QFont) -> tuple[float, float]:
		"""
		Estimates the height and width of a string provided a font
		:rtype: float, float
		:param font:
		:return: height and width of text
		"""
		p = QPainterPath()
		p.addText(QPoint(0, 0), font, self.text)
		rect = p.boundingRect()
		return rect.width(), rect.height()

	def position(self):
		strWidth, strHeight = self.estimateTextSize(self.font)
		x = self.x + strWidth * -0.6

		if x < 10:
			x = 10
		elif x + strWidth > self.parent.sceneRect().width() - 10:
			x = self.parent.sceneRect().width() - strWidth - 10

		# Set alignment
		y = self.y
		if self.alignment == Qt.AlignBottom:
			y += strHeight

		# Keep text in bounds
		if y - strHeight < 10:
			y = 10 + strHeight
		if y > self.parent.sceneRect().height() - 15:
			y = self.parent.sceneRect().height() - 15

		return QPointF(x, y)

	def updateItem(self):
		self.font.setPixelSize(self.parent.scene.fontSize * self._scalar)
		self.setPlainText(self.text)
		self.setPos(self.position())
		self.setFont(self.font)
		self.setDefaultTextColor(Default.main)

	@property
	def font(self):
		if self._font is None:
			self._font = QFont(rounded)
		return self._font

	@font.setter
	def font(self, font: Union[QFont, str]):
		if font == None:
			self.font = QFont(rounded)
		elif isinstance(font, str):
			self._font = QFont(font, self.height() * .1)
		elif isinstance(font, QFont):
			self._font = font
		else:
			self._font = QFont(font)


class Text(QGraphicsPathItem):

	def __init__(self, parent, x: float, y: float, text: str, alignment: Qt.AlignmentFlag = Qt.AlignCenter,
	             scalar: float = 1.0, font: Union[QFont, str] = None, color: QColor = None):
		super(Text, self).__init__()
		self.x, self.y = x, y
		self._parent = parent
		self._text = text
		self.alignment = alignment
		self.scalar = scalar
		self.color = color
		self.font = font
		self.updateItem()

	@property
	def font(self):
		return self._font

	@font.setter
	def font(self, font: Union[QFont, str]):
		if font == None:
			self.font = QFont(rounded)
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
		p.addText(QPoint(0, 0), font, self.text)
		rect = p.boundingRect()
		return rect.width(), rect.height()

	def updateItem(self) -> None:

		self.font.setPixelSize(self.parent.scene.fontSize * self.scalar)

		lineThickness = max(self.parent.scene.fontSize * self.scalar * golden * 0.07, 3)
		pen = QPen(self.color, lineThickness)

		brush = QBrush(Default.main)
		self.setPen(QColor(Default.main))
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
		elif x + strWidth > self.parent.sceneRect().width() - 10:
			x = self.parent.sceneRect().width() - strWidth - 10

		# Set alignment
		y = self.y
		if self.alignment == Qt.AlignBottom:
			y += strHeight

		# Keep text in bounds
		if y - strHeight < 10:
			y = 10 + strHeight
		if y > self.parent.sceneRect().height() - 15:
			y = self.parent.sceneRect().height() - 15

		return QPointF(x, y)


class MarkerAnnotation(Text):
	scalar: float

	def __init__(self, parent: GraphScene, index: int, array: str, alignment: Qt.AlignmentFlag = Qt.AlignCenter,
	             scalar: float = 1.0, font: Union[QFont, str] = None, color: QColor = Default.main):
		super(MarkerAnnotation, self).__init__(parent, x=0, y=0, text="", alignment=alignment, scalar=scalar, font=font, color=color)
		self.index = index
		self.array = array
		self.updateItem()
		self.setGraphicsEffect(SoftShadow())

	@property
	def text(self):
		date: datetime = self.parent.hours.dates[self.index]
		return date.strftime('%a')

	def position(self) -> QPointF:

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

		return QPointF(x, y)


class PlotAnnotation(Text):
	scalar: float

	def __init__(self, parent: GraphItemData, value: Measurement, alignment: Qt.AlignmentFlag = Qt.AlignCenter,
	             scalar: float = 1.0, font: Union[QFont, str] = None, color: QColor = Default.main):
		self._value = value
		super(PlotAnnotation, self).__init__(parent, x=0, y=0, text="", alignment=alignment, scalar=scalar, font=font, color=color)
		self._parent = parent
		self.setGraphicsEffect(SoftShadow())

	@property
	def text(self):
		return str(self._value)

	def estimateTextSizeD(self, font: QFont) -> tuple[float, float, float]:
		"""
		Estimates the height and width of a string provided a font
		:rtype: float, float
		:param font:
		:return: height and width of text
		"""
		p = QPainterPath()
		decorator = self._value._decorator
		p.addText(QPoint(0, 0), font, self.text.strip(decorator))
		rect = p.boundingRect()
		p.clear()
		p.addText(QPoint(0, 0), font, decorator)
		decoratorWidth = p.boundingRect().width()
		return rect.width(), rect.height(), decoratorWidth

	def estimateTextSize(self, font: QFont) -> tuple[float, float, QPointF, QRectF]:
		"""
		Estimates the height and width of a string provided a font
		:rtype: float, float
		:param font:
		:return: height and width of text
		"""
		p = QPainterPath()
		p.addText(QPoint(0, 0), font, self.text)
		rect = p.boundingRect()
		v = [p.elementAt(i) for i in range(p.elementCount())]
		yC = sum([e.y for e in v]) / len(v)
		xC = sum([e.x for e in v]) / len(v)
		return rect.width(), rect.height(), QPointF(xC, yC), rect

	def position(self) -> QPointF:
		graphicRect = self.parent.graphic.sceneBoundingRect()
		lineWeight = self.parent.scene.lineWeight

		strWidth, strHeight, centerOffset, textRect = self.estimateTextSize(self.font)

		pos = self.parent.normalizeToFrame(self._value.timestamp.timestamp(), self._value)
		textRect.moveCenter(pos)
		pos = closest_point_on_path(textRect, self.parent.graphic.path())
		x = pos.x()
		y = pos.y()

		# x -= centerOffset.x()
		x += strWidth * -0.5
		if x < graphicRect.left() + 10:
			x = graphicRect.left() + 10
		elif x + strWidth > graphicRect.right() - 20:
			x = graphicRect.right() - strWidth - 20

		# Set alignment
		if self.alignment == Qt.AlignBottom:
			y += strHeight + lineWeight * 1.2
		else:
			y -= lineWeight * 1.2

		# Keep text in bounds
		if y - strHeight < 10:
			y = 10 + strHeight
		if y > self.parent.scene.height - 15:
			y = self.parent.scene.height - 15
		pass
		return QPointF(x, y)

	def update(self):
		collections = self.collections
		if len(collections) > 1:
			col = collections[min(range(0, len(collections) - 1), key=lambda i: collections[i]._value)]
			for x in collections:
				if x is not col:
					x.hide()
				else:
					x.show()
		self.updateItem()
		super(PlotAnnotation, self).update()

	@property
	def collections(self) -> list:
		type = self.parent._peaks if self._value in self.parent._peaks else self.parent._troughs
		collections = [col for col in self.collidingItems() if isinstance(col, self.__class__) and col._value in type]
		return collections


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

	# return QPixmap.fromImage(qim)

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


from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *


class FigureEditor(QFrame):
	currentItem: GraphItemData
	colorPicker: Optional[QColorDialog] = None

	def __init__(self, figure: Figure, *args, **kwargs):
		super(FigureEditor, self).__init__(*args, **kwargs)
		self.figure = figure
		self.proxy = None

		self.resize(375, 309)
		self.verticalLayout = QVBoxLayout(self)
		self.formLayout = QFormLayout(self)

		index = 0

		self.primaryValueLabel = QLabel(self, text='Primary Item')
		self.primaryValueComboBox = QComboBox(self)
		self.formLayout.setWidget(index, QFormLayout.LabelRole, self.primaryValueLabel)
		self.formLayout.setWidget(index, QFormLayout.FieldRole, self.primaryValueComboBox)

		index += 1

		self.selectedValueLabel = QLabel(self, text='Selected Item')
		self.selectedValueComboBox = QComboBox(self)
		self.formLayout.setWidget(index, QFormLayout.LabelRole, self.selectedValueLabel)
		self.formLayout.setWidget(index, QFormLayout.FieldRole, self.selectedValueComboBox)

		index += 1

		self.annotationsLabel = QLabel(self, text='Annotations')
		self.annotationsCheckBox = QCheckBox(self)
		self.formLayout.setWidget(index, QFormLayout.LabelRole, self.annotationsLabel)
		self.formLayout.setWidget(index, QFormLayout.FieldRole, self.annotationsCheckBox)

		index += 1

		self.graphicTypeLabel = QLabel(self, text='Graphic Type')
		self.graphicTypeComboBox = QComboBox(self)
		self.formLayout.setWidget(index, QFormLayout.LabelRole, self.graphicTypeLabel)
		self.formLayout.setWidget(index, QFormLayout.FieldRole, self.graphicTypeComboBox)

		index += 1

		self.marginsLabel = QLabel(self, text='Margins')
		self.marginCluster = QGridLayout()

		self.topSpinBoxLabel = QLabel(self, text='Top')
		self.marginCluster.addWidget(self.topSpinBoxLabel, 0, 0, 1, 1)
		self.topSpinBox = QDoubleSpinBox(self)
		self.topSpinBox.setSingleStep(0.05)
		self.marginCluster.addWidget(self.topSpinBox, 1, 0, 1, 1)

		self.bottomSpinBoxLabel = QLabel(self, text='Bottom')
		self.marginCluster.addWidget(self.bottomSpinBoxLabel, 0, 1, 1, 1)
		self.bottomSpinBox = QDoubleSpinBox(self)
		self.bottomSpinBox.setSingleStep(0.05)
		self.marginCluster.addWidget(self.bottomSpinBox, 1, 1, 1, 1)

		self.leftSpinBoxLabel = QLabel(self, text='Left')
		self.marginCluster.addWidget(self.leftSpinBoxLabel, 0, 2, 1, 1)
		self.leftSpinBox = QDoubleSpinBox(self)
		self.leftSpinBox.setSingleStep(0.05)
		self.marginCluster.addWidget(self.leftSpinBox, 1, 2, 1, 1)

		self.rightSpinBoxLabel = QLabel(self, text='Right')
		self.marginCluster.addWidget(self.rightSpinBoxLabel, 0, 3, 1, 1)
		self.rightSpinBox = QDoubleSpinBox(self)
		self.rightSpinBox.setSingleStep(0.05)
		self.marginCluster.addWidget(self.rightSpinBox, 1, 3, 1, 1)

		self.formLayout.setWidget(index, QFormLayout.LabelRole, self.marginsLabel)
		self.formLayout.setLayout(index, QFormLayout.FieldRole, self.marginCluster)

		index += 1

		self.lineWeightLabel = QLabel(self, text='Line Weight')
		self.lineWeight = QDoubleSpinBox(self)
		self.lineWeight.setSingleStep(0.1)
		self.formLayout.setWidget(index, QFormLayout.LabelRole, self.lineWeightLabel)
		self.formLayout.setWidget(index, QFormLayout.FieldRole, self.lineWeight)

		index += 1

		self.lineStyleLabel = QLabel(self, text='Line Style')
		self.lineStyleLineEdit = QLineEdit(self)
		self.formLayout.setWidget(index, QFormLayout.LabelRole, self.lineStyleLabel)
		self.formLayout.setWidget(index, QFormLayout.FieldRole, self.lineStyleLineEdit)

		index += 1

		self.lineColorLabel = QLabel(self, text='Line Color')
		self.lineColorButton = QToolButton(self)
		self.formLayout.setWidget(index, QFormLayout.LabelRole, self.lineColorLabel)
		self.formLayout.setWidget(index, QFormLayout.FieldRole, self.lineColorButton)

		index += 1

		self.lineResolutionLabel = QLabel(self, text='Line Resolution')
		self.lineResolution = QSpinBox(self)
		self.lineResolution.setSingleStep(5)
		self.formLayout.setWidget(index, QFormLayout.LabelRole, self.lineResolutionLabel)
		self.formLayout.setWidget(index, QFormLayout.FieldRole, self.lineResolution)

		self.verticalLayout.addLayout(self.formLayout)

		self.buttonBox = QDialogButtonBox(self)
		self.buttonBox.setOrientation(Qt.Horizontal)
		self.buttonBox.setStandardButtons(QDialogButtonBox.Close)

		self.verticalLayout.addWidget(self.buttonBox)

		self.buttonBox.button(QDialogButtonBox.Close).pressed.connect(self.close)

	def connect(self):
		self.rightSpinBox.valueChanged.connect(self.adjustRightMargin)
		self.leftSpinBox.valueChanged.connect(self.adjustLeftMargin)
		self.bottomSpinBox.valueChanged.connect(self.adjustBottomMargin)
		self.topSpinBox.valueChanged.connect(self.adjustTopMargin)

		self.selectedValueComboBox.currentIndexChanged.connect(self.selectedItemChanged)
		self.primaryValueComboBox.currentIndexChanged.connect(self.setPrimary)

		self.annotationsCheckBox.stateChanged.connect(self.labelsToggle)
		self.lineWeight.valueChanged.connect(self.adjustLineWeight)
		self.lineResolution.valueChanged.connect(self.setResolution)

		self.lineColorButton.pressed.connect(self.showColorPicker)
		self.lineStyleLineEdit.textChanged.connect(self.setLineDashPattern)

	def disconnect(self):
		self.rightSpinBox.valueChanged.disconnect(self.adjustRightMargin)
		self.leftSpinBox.valueChanged.disconnect(self.adjustLeftMargin)
		self.bottomSpinBox.valueChanged.disconnect(self.adjustBottomMargin)
		self.topSpinBox.valueChanged.disconnect(self.adjustTopMargin)

		self.selectedValueComboBox.currentIndexChanged.disconnect(self.selectedItemChanged)
		self.primaryValueComboBox.currentIndexChanged.disconnect(self.setPrimary)

		self.annotationsCheckBox.stateChanged.disconnect(self.labelsToggle)
		self.lineWeight.valueChanged.disconnect(self.adjustLineWeight)
		self.lineResolution.valueChanged.disconnect(self.setResolution)

		self.lineColorButton.pressed.disconnect(self.showColorPicker)
		self.lineStyleLineEdit.textChanged.disconnect(self.setLineDashPattern)

	def show(self):
		for name, data in self.figure.data.items():
			if self.selectedValueComboBox.findText(name) == -1:
				self.selectedValueComboBox.addItem(f'{name}', userData=data)
			if self.primaryValueComboBox.findText(name) == -1:
				self.primaryValueComboBox.addItem(f'{name}', userData=data)

		self.topSpinBox.setValue(self.figure._margins.top)
		self.bottomSpinBox.setValue(self.figure._margins.bottom)
		self.leftSpinBox.setValue(self.figure._margins.left)
		self.rightSpinBox.setValue(self.figure._margins.right)
		self.lineWeight.setValue(self.currentItem.graphic.scalar)
		self.lineStyleLineEdit.setText(str(self.currentItem.graphic.dashPattern))
		self.lineResolution.setValue(self.currentItem.multiplierRaw)
		self.connect()
		super(FigureEditor, self).show()

	def close(self):
		self.figure.scene.removeItem(self.proxy)
		super(FigureEditor, self).close()

	def updateValues(self):
		self.disconnect()
		self.topSpinBox.setValue(self.figure._margins.top)
		self.bottomSpinBox.setValue(self.figure._margins.bottom)
		self.leftSpinBox.setValue(self.figure._margins.left)
		self.rightSpinBox.setValue(self.figure._margins.right)
		self.lineWeight.setValue(self.currentItem.graphic.scalar)
		self.lineStyleLineEdit.setText(str(self.currentItem.graphic.dashPattern))
		self.lineResolution.setValue(self.currentItem.multiplierRaw)
		self.setButtonColor(self.currentItem.graphic.color)
		self.connect()

	def setPrimary(self, index: int):
		i = self.primaryValueComboBox.itemData(index)
		for x in i.figure.data.values():
			if x is i:
				x.allGraphics.setZValue(101)
			else:
				x.allGraphics.setZValue(50)

	def labelsToggle(self, value: bool):
		self.currentItem.labeled = value
		self.figure.update()

	# if self.isVisible():
	# 	self.figure.update()

	def adjustTopMargin(self, value: float):
		self.figure._margins.top = round(value, 3)
		if self.isVisible():
			self.figure.update()

	def adjustBottomMargin(self, value: float):
		self.figure._margins.bottom = round(value, 3)
		if self.isVisible():
			self.figure.update()

	def adjustLeftMargin(self, value: float):
		self.figure._margins.left = value
		if self.isVisible():
			self.figure.update()

	def adjustRightMargin(self, value: float):
		self.figure._margins.right = round(value, 3)
		if self.isVisible():
			self.figure.update()

	def adjustLineWeight(self, value: float):
		self.currentItem.graphic.scalar = round(value, 3)
		if self.isVisible():
			self.currentItem.graphic.update()

	def selectedItemChanged(self, index: int):
		self.currentItem: GraphItemData = self.selectedValueComboBox.itemData(index)
		self.updateValues()

	def showColorPicker(self):
		if self.colorPicker is None:
			self.colorPicker = QColorDialog(self, self.currentItem.graphic.color)
			self.colorPicker.currentColorChanged.connect(self.setLineColor)
		self.colorPicker.show()

	def setLineColor(self, value):
		self.currentItem.graphic.color = value
		self.setButtonColor(value)
		# if self.isVisible():
		self.currentItem.graphic.update()
		self.currentItem.scene.update()

	def setResolution(self, value):
		self.currentItem.multiplier = int(value)
		if self.isVisible():
			self.currentItem.graphic.update()

	def setButtonColor(self, value):
		try:
			color = rgbHex(*value.toTuple()[:3])
			px = QPixmap(20, 20)
			px.fill(color)
			self.lineColorButton.setIcon(px)
		except AttributeError:
			pass

	def setLineDashPattern(self, value):
		self.currentItem.graphic.dashPattern = value
		self.currentItem.graphic.update()


class GraphEditor(QFrame):

	def __init__(self, graph: Graph, *args, **kwargs):
		super(GraphEditor, self).__init__(*args, **kwargs)
		self.graph = graph
		self.proxy = None

		self.resize(375, 309)
		self.verticalLayout = QVBoxLayout(self)
		self.formLayout = QFormLayout(self)

		index = 0

		# self.annotationsLabel = QLabel(self, text='Annotations')
		# self.annotationsCheckBox = QCheckBox(self)
		# self.formLayout.setWidget(index, QFormLayout.LabelRole, self.annotationsLabel)
		# self.formLayout.setWidget(index, QFormLayout.FieldRole, self.annotationsCheckBox)
		#
		# index += 1
		#
		# self.graphicTypeLabel = QLabel(self, text='Graphic Type')
		# self.graphicTypeComboBox = QComboBox(self)
		# self.formLayout.setWidget(index, QFormLayout.LabelRole, self.graphicTypeLabel)
		# self.formLayout.setWidget(index, QFormLayout.FieldRole, self.graphicTypeComboBox)

		# index += 1

		self.timeframeLabel = QLabel(self, text='Timeframe')
		self.timeframe = QSpinBox(self)
		self.timeframe.setSingleStep(1)
		self.formLayout.setWidget(index, QFormLayout.LabelRole, self.timeframeLabel)
		self.formLayout.setWidget(index, QFormLayout.FieldRole, self.timeframe)

		# index += 1
		#
		# self.lineStyleLabel = QLabel(self, text='Line Style')
		# self.lineStyleLineEdit = QLineEdit(self)
		# self.formLayout.setWidget(index, QFormLayout.LabelRole, self.lineStyleLabel)
		# self.formLayout.setWidget(index, QFormLayout.FieldRole, self.lineStyleLineEdit)
		#
		# index += 1
		#
		# self.lineColorLabel = QLabel(self, text='Line Color')
		# self.lineColorButton = QToolButton(self)
		# self.formLayout.setWidget(index, QFormLayout.LabelRole, self.lineColorLabel)
		# self.formLayout.setWidget(index, QFormLayout.FieldRole, self.lineColorButton)
		#
		# index += 1
		#
		# self.lineResolutionLabel = QLabel(self, text='Line Resolution')
		# self.lineResolution = QSpinBox(self)
		# self.lineResolution.setSingleStep(5)
		# self.formLayout.setWidget(index, QFormLayout.LabelRole, self.lineResolutionLabel)
		# self.formLayout.setWidget(index, QFormLayout.FieldRole, self.lineResolution)

		self.verticalLayout.addLayout(self.formLayout)

		self.buttonBox = QDialogButtonBox(self)
		self.buttonBox.setOrientation(Qt.Horizontal)
		self.buttonBox.setStandardButtons(QDialogButtonBox.Close)

		self.verticalLayout.addWidget(self.buttonBox)

		self.buttonBox.button(QDialogButtonBox.Close).pressed.connect(self.close)

	def connect(self):
		self.timeframe.valueChanged.connect(self.adjustTimeframe)

	def disconnect(self):
		self.timeframe.valueChanged.disconnect(self.adjustTimeframe)

	def show(self):
		self.timeframe.setValue(int(self.graph._timeframe.rangeSeconds / 60 / 60))
		self.connect()
		super(GraphEditor, self).show()

	def adjustTimeframe(self, value):
		self.graph._timeframe.max = timedelta(hours=int(value))
		self.graph.updateGraphics()

	def close(self):
		self.figure.scene.removeItem(self.proxy)
		super(GraphEditor, self).close()

	def updateValues(self):
		self.disconnect()
		self.timeframe.setValue(self.currentItem.graphic.scalar)
		self.connect()


class LineExample(QWidget):
	color: QColor = QColor.black
	lineWeight: float

	def __init__(self, *args, **kwargs):
		super(LineExample, self).__init__(*args, **kwargs)

	def paintEvent(self, event):
		p = QPainter(self)
		p.drawLine(self.rect().left(), self.rect().right())


if __name__ == '__main__':
	app = QApplication()
	wf = WFStation()
	# wf = TomorrowIO()
	wf.getData()
	# wf.getCurrent()
	# data = reload('../rain.pickle')
	window = Graph()
	window.resize(1600, 1000)
	window.scene().addMeasurement(wf.realtime['dewpoint'], wf)
	window.scene().addMeasurement(wf.realtime['temperature'], wf)
	print(window.state)
	window.show()
	display_monitor = 1
	monitor = QDesktopWidget().screenGeometry(display_monitor)
	window.move(monitor.left(), monitor.top())

	sys.exit(app.exec_())
