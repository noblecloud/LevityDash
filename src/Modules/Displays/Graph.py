from json import loads

import numpy as np
import scipy as sp
from copy import copy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import cached_property
from itertools import chain, zip_longest
from PIL import Image
from PIL.ImageQt import ImageQt
from PySide2.QtCore import QLineF, QObject, QPoint, QPointF, QRectF, QSize, Qt, QTimer, Signal, Slot
from PySide2.QtGui import QBrush, QColor, QFocusEvent, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPainterPathStroker, QPen, QPixmap, QPolygonF, QTransform
from PySide2.QtWidgets import (QGraphicsDropShadowEffect, QGraphicsEffect, QGraphicsItem, QGraphicsItemGroup, QGraphicsLineItem, QGraphicsPathItem,
                               QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsSceneDragDropEvent, QGraphicsSceneHoverEvent, QGraphicsSceneMouseEvent, QGraphicsSceneWheelEvent, QToolTip)
from scipy.constants import golden
from scipy.interpolate import CubicSpline, interp1d
import scipy.signal
from typing import Callable, ClassVar, Iterable, List, Optional, overload, Set, Tuple, Union
from uuid import uuid4
from WeatherUnits import Measurement, Temperature
from WeatherUnits.time.time import Millisecond, Second
from WeatherUnits.length import Centimeter

from src.plugins.plugin import Container
from src.plugins.observation import MeasurementTimeSeries, Realtime, TimeAwareValue, TimeSeriesItem
from src import app, colorPalette, config, logging
from src.catagories import CategoryItem
from src.colors import kelvinToQColor, rgbHex
from src.plugins.dispatcher import ValueDirectory, ForecastPlaceholderSignal, MultiSourceContainer, MonitoredKey
from src.logger import guiLog
from src.Modules import hook
from src.Modules.DateTime import baseClock, baseClock as ClockSignals
from src.Modules.Displays.Text import Text
from src.Modules.Handles.Figure import FigureHandles
from src.Modules.Handles.Incrementer import Incrementer, IncrementerGroup
from src.Modules.Handles.Timeframe import GraphZoom
from src.Modules.Panel import Panel
from src.utils import (_Panel, AlignmentFlag, autoDType, Axis, AxisMetaData, clamp, clearCacheAttr, closestCeil, DataTimeRange, disconnectSignal, DisplayType, findPeaksAndTroughs, GraphicsItemSignals, Margins, modifyTransformValues,
                       normalize, roundToPeriod, smoothData, TimeFrameWindow, timestampToTimezone)
from time import time

log = guiLog.getChild(__name__)

__all__ = ['GraphItemData', 'Figure', 'GraphPanel']


class SoftShadow(QGraphicsDropShadowEffect):
	# __instances__: ClassVar[Set['SoftShadow']] = set()
	parentSingleton = QObject()

	def __init__(self, *args, **kwargs):
		super(SoftShadow, self).__init__(parent=self.parentSingleton, *args, **kwargs)
		# self.__hash = hash(uuid4())
		# self.__instances__.add(self)
		self.setOffset(0.0)
		self.setBlurRadius(60)
		self.setColor(Qt.black)

	# self.destroyed.connect(removeInstance)

	def __hash__(self):
		return self.__hash

	@classmethod
	def disable(cls):
		if any(i.isEnabled() for i in cls.parentSingleton.children()):
			list(i.setEnabled(False) for i in cls.parentSingleton.children())

	@classmethod
	def enable(cls):
		list(i.setEnabled(True) for i in cls.parentSingleton.children())

	def draw(self, painter: QPainter) -> None:
		if not painter.testRenderHint(QPainter.Antialiasing):
			self.drawSource(painter)
			# offset = QPoint(0, 0)
			# pixmap = self.sourcePixmap(Qt.LogicalCoordinates, offset, QGraphicsEffect.PadToTransparentBorder)
			# # painter.setWorldTransform(QTransform())
			# painter.drawPixmap(offset, self.sourcePixmap())
			return
		super(SoftShadow, self).draw(painter)


@dataclass
class ComfortZones:
	extreme: Temperature = Temperature.Celsius(40)
	veryHot: Temperature = Temperature.Celsius(35)
	hot: Temperature = Temperature.Celsius(30)
	comfortable: Temperature = Temperature.Celsius(22)
	chilly: Temperature = Temperature.Celsius(18)
	cold: Temperature = Temperature.Celsius(10)
	freezing: Temperature = Temperature.Celsius(-10)

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


class TemperatureGradient(QLinearGradient):
	temperatures = ComfortZones()
	kelvinValues = [45000, 16000, 7000, 6500, 5500, 2500, 1500]

	def __init__(self, plot: 'Plot'):
		self.plot = plot
		super(TemperatureGradient, self).__init__(0, 0, 0, 1)
		self.__genGradient()

	def __genGradient(self):
		T = self.localized
		locations = (T - T.min())/T.ptp()
		for temperature, kelvin in zip(locations, self.kelvinValues):
			self.setColorAt(temperature, kelvinToQColor(kelvin))

	@cached_property
	def localized(self):
		unit = self.plot.data.rawData[0]['@unit']
		return np.array([t[unit] for t in self.temperatures.list])

	@property
	def gradientPoints(self) -> Tuple[QPoint, QPoint]:
		T = (self.localized - self.plot.data.data[1].min())/self.plot.data.data[1].ptp()
		t = QTransform(self.plot.data.t)
		bottom = QPointF(0, T.min())
		top = QPointF(0, T.max())
		top = t.map(top)
		bottom = t.map(bottom)
		return top, bottom

	def update(self):
		start, stop = self.gradientPoints
		self.setStart(start)
		self.setFinalStop(stop)

	def __str__(self):
		return self.__class__.__name__


class HoverHighlight(QGraphicsDropShadowEffect):
	def __init__(self, color=Qt.white, *args, **kwargs):
		super(HoverHighlight, self).__init__(*args, **kwargs)
		self.setOffset(0.0)
		self.setBlurRadius(60)
		self.setColor(color)


# Section GraphItemData


class GraphItemData(QObject):
	axisChanged: 'AxisSignal'

	lastUpdate: datetime
	_placeholder: Optional[ForecastPlaceholderSignal]
	_multiplier: Optional[timedelta]
	_spread: Optional[int]
	_order: Optional[int]
	_array: Optional[np.array]
	_numerical: bool
	_interpolated: Optional[np.array]
	_smoothed: Optional[np.array]
	_smooth: bool
	_figure: 'Figure'
	_interpolate: bool
	_pathType: 'PathType'
	_graphic: Optional[QGraphicsItem]
	_timeframe: Optional[DataTimeRange]
	__normalX: np.array
	__normalY: np.array
	_value: MeasurementTimeSeries
	__labels: 'PlotLabels'

	log = log.getChild('GraphItemData')

	def __init__(self,
	             key: CategoryItem,
	             parent: 'Figure' = None,
	             interpolate: bool = True,
	             labeled: bool = False,
	             smooth: bool = True,
	             spread: int = 31,
	             order: int = 3,
	             plot=None, **kwargs):
		super(GraphItemData, self).__init__()
		if plot is None:
			plot = {}
		self.__init_defaults__()
		self.graphic = plot
		self._interpolate = interpolate
		self._smooth = smooth
		self._spread = spread
		self._order = order
		self.labeled = labeled
		self.figure = parent
		self.key = key

	def __init_defaults__(self):
		self.__lastUpdate = datetime.now()
		self.axisChanged = AxisSignal(self)
		self.uuid = uuid4()
		self._key = None
		self._length = None
		self.offset = 0
		self._placeholder = None
		self._multiplier = timedelta(minutes=15)
		self._spread = None
		self._order = None
		self._array = None
		self._numerical = None
		self._interpolated = None
		self._smoothed = None
		self._raw = []

		self._figure = None
		self._interpolate = None
		self._pathType = None
		self._graphic = None
		self._timeframe = None
		self.__normalX = None
		self.__normalY = None
		self._value = None
		self.__labels = None

	# Section GraphItemEvents

	@Slot(Axis)
	def __onAxisTransform(self, axis: Axis):
		"""
		Called when given the signal that the parent figure's axis spread has changed
		either due to a graph zoom or figure margin change.

		Parameters
		----------
		axis: Axis
			The axis that has been transformed
		"""
		if self._value is None:
			return
		self.__updateTransform(axis)
		self.graphic.onAxisTransform(axis)
		if self.labeled:
			self.labels.onAxisTransform(axis)

	@Slot()
	def __onValueChange(self):
		"""
		Called when the value of the timeseries has changed.  Alerts parent figure
		that its values have changed.  The figure briefly waits for other GraphItemData to
		announce their own changes before announcing that the transform needs to be updated.

		Note: This slot should not update the transform, it should wait for the parent figure
		to finish collecting announcements from sibling GraphItemData.
		"""
		self.graph.onAxisChange(Axis.Both)
		self.__clearAxis(Axis.Both)
		self.__updateTransform(Axis.Both)
		self.graphic.onAxisChange(Axis.Both)
		self.timeframe.invalidate()
		if self.labeled:
			clearCacheAttr(self, 'peaksAndTroughs')
			self.labels.onValueChange(Axis.Both)
		self.log.info(f"GraphItemData {self.key.name} updated")

		self.axisChanged.announce(Axis.Both, instant=True)

	@cached_property
	def timeframe(self) -> DataTimeRange:
		return DataTimeRange(self)

	def __clearAxis(self, axis: Axis, rebuild: bool = True):
		if len(self.list) == 1:
			return
		# TODO: Add a check to see if the axis value actually changed and only announce if it did
		"""Called by only when the value of the timeseries has changed."""
		self.__clearCache()
		if axis & Axis.X:
			self.__normalX = None
		if axis & Axis.Y:
			self.__normalY = None
		if rebuild:
			self.normalizeData()

	def __updateTransform(self, axis: Axis):
		# TODO: this currently assumes all values are provided at intervals of one hour
		xTranslate, yTranslate = 0, 0
		xScale, yScale = 1, 1
		# if axis & Axis.X:
		# 	xTranslate = (self.timeframe.min - self.figure.graph.timeframe.start).total_seconds() / self.figure.graph.timeframe.seconds
		if axis & Axis.Y:
			T = (self.data[1] - self.figure.dataValueRange.min)/self.figure.dataValueRange.range
			yTranslate = T.min()
			yScale = T.ptp()
		modifyTransformValues(self._t, xTranslate, yTranslate, xScale, yScale)

	def __clearCache(self):
		self.timeframe.invalidate()
		clearCacheAttr(self, 'data', '_t', 'list', 'smoothed')

	@property
	def lastUpdate(self):
		return self.__lastUpdate.timestamp()

	def refreshUpdateTime(self):
		self.__lastUpdate = datetime.now()

	@cached_property
	def _t(self) -> QTransform:
		timeOffset = (self.timeframe.min - self.figure.graph.timeframe.start).total_seconds()/self.figure.graph.timeframe.seconds
		t = QTransform()
		clearCacheAttr(self, 't2')
		# return self.t2
		if self.plotValues:
			T = (self.data[1] - self.figure.dataValueRange.min)/self.figure.dataValueRange.range
			t.translate(-timeOffset, T.min())
			t.scale(1, T.ptp())
		return t

	@property
	def t(self):
		return self._t*self.figure.t

	@cached_property
	def t2(self):
		timeOffset = (self.timeframe.min - self.figure.graph.timeframe.start).total_seconds()/self.figure.graph.timeframe.seconds
		t = QTransform()
		if self.plotValues:
			start = (self.figure.graph.timeframe.start - self.figure.graph.timeframe.offset).timestamp()
			end = start + self.figure.graph.timeframe.timeframe.total_seconds()
			a = [i for i, j in enumerate(self.data[0]) if j >= start and j <= end]
			i = min(a)
			j = max(a)
			minMax = self.figure.dataValueRange[i:j]
			T = (self.data[1][i:j] - minMax.min)/minMax.range*(self.figure.dataValueRange.range/minMax.range)
			t.translate(-timeOffset, T.min())
			t.scale(1, T.ptp())
			print(self.figure.dataValueRange.min, self.figure.dataValueRange.max, minMax.min, minMax.max)
		return t

	@property
	def figure(self) -> 'Figure':
		return self._figure

	@figure.setter
	def figure(self, figure: 'Figure'):
		# if item is already assigned to a figure, disconnect the signals and
		# remove the item from the figure's list of items
		if self._figure is not None:
			self._figure.plotData.pop(self.value.key)
			self._figure.axisChanged.disconnectSlot(self.__onAxisTransform)
			self.axisChanged.disconnectSlot(self._figure.onGraphItemUpdate)
		assert isinstance(figure, Figure)

		self._figure = figure
		self.graphic.setParentItem(self.figure)

		# Connect slot that informs the figure to update the transform
		self.axisChanged.connectSlot(self._figure.onGraphItemUpdate)

		# Connect figures signals to update the local transform
		self._figure.axisTransformed.connectSlot(self.__onAxisTransform)

	@property
	def graph(self) -> 'GraphPanel':
		return self._figure.graph

	@property
	def graphic(self) -> 'Plot':
		return self._graphic

	@graphic.setter
	def graphic(self, value):
		if isinstance(value, dict):
			value = self.buildGraphic(**value)
		self._graphic = value

	@property
	def key(self):
		return self._key

	@key.setter
	def key(self, value):
		if isinstance(value, str):
			value = CategoryItem(value)
		if value != self._key and self._key in self._figure.plotData:
			self._figure.plotData[self.key].figure = None

		self._key = value

		self._figure.plotData[self.key] = self

		value = ValueDirectory.getHourly(value, self, source=None)
		if isinstance(value, ForecastPlaceholderSignal):
			self.value = None
			self.placeholder = value
		elif isinstance(value, MultiSourceContainer):
			self.placeholder = None
			self.value = value

	@property
	def value(self) -> MeasurementTimeSeries:
		if self._value is None:
			return None
		return self._value.forecast

	@value.setter
	def value(self, value: MonitoredKey):
		if self._value:
			self._value.hourly.signals.disconnectSlot(self.__onValueChange)
		if value:
			if isinstance(value, MultiSourceContainer):
				value.forecast.signals.connectSlot(self.__onValueChange)
				self._value = value
			else:
				value.value.forecast.signals.connectSlot(self.__onValueChange)
				self._value = value.value
			if len(value.value.forecast) > 2:
				self.__onValueChange()
			if self.labeled:
				if self.__labels is None:
					self.__labels = PlotLabels(self.key, self, peaksTroughs=True)
			else:
				if self.__labels is None:
					pass
				elif self._labels.isVisible():
					self._labels.setVisible(False)
			if isinstance(value, MonitoredKey):
				value.requesters.remove(self)

	@property
	def hasData(self) -> bool:
		return self.value is not None

	@property
	def placeholder(self):
		return self._placeholder

	@placeholder.setter
	def placeholder(self, value):
		if self._placeholder is not None and value is None:
			self._placeholder.signal.disconnect(self.listenForKey)
		self._placeholder = value
		if self._placeholder is not None:
			self._placeholder.signal.connect(self.listenForKey)

	@Slot(MonitoredKey)
	def listenForKey(self, value: MonitoredKey):
		if str(value.key) == str(self.placeholder.key):
			print(f"{self.key.name} got new value {value.key}")
			if value.value.forecast is not None:
				value.value.forecast.update()
				self.value = value
				value.requesters.discard(self)

	def buildGraphic(self, **kwargs: object) -> 'Plot':
		type = kwargs.pop('type', DisplayType.LinePlot)
		if type == DisplayType.LinePlot:
			return LinePlot(self, **kwargs)

	def __repr__(self):
		if self._value is not None:
			# mY = min(self._value.forecast._values())
			# MY = max(self._value.hourly._values())
			# mX = list(self._value.hourly.keys())[0]
			# MX = list(self._value.hourly.keys())[-1]
			return f'{self.__class__.__name__}(key: {self.key})'
		return f'{self.__class__.__name__} awaiting data for key: {self.key}'

	@property
	def labeled(self) -> bool:
		# return False
		return self._labeled

	@labeled.setter
	def labeled(self, value: bool):
		self._labeled = value

	@property
	def labels(self):
		if self.labeled:
			if self.__labels is None:
				self.__labels = PlotLabels(self.key, self, peaksTroughs=True)
			return self.__labels
		else:
			return None

	@property
	def interpolate(self) -> bool:
		return self._interpolate

	@interpolate.setter
	def interpolate(self, value):
		self._interpolate = value

	@property
	def rawData(self) -> MeasurementTimeSeries:
		# TODO: Refactor this to use the value property
		if self.value is not None:
			return self.value
		return None

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
	def type(self):
		return '.'.join(str(type(self.rawData[0])).split('.')[1:3])

	@property
	def source(self):
		return self._value.source

	@cached_property
	def peaksAndTroughs(self):
		# def mergeSequentialDuplicates(lst: list):
		# 	if len(lst) < 2:
		# 		return lst
		# 	merged = []
		# 	remaining = (copy(i) for i in lst)
		# 	first = next(remaining)
		# 	while remaining:
		# 		try:
		# 			second = next(remaining)
		# 			if abs(first.value - second.value) < 0.5 and second.timestamp.date() - first.timestamp.date() < timedelta(hours=6):
		# 				first += second
		# 				merged.append(first)
		# 				first = next(remaining)
		# 			else:
		# 				merged.append(first)
		# 				first = second
		# 		except StopIteration:
		# 			break
		# 	if first not in merged:
		# 		merged.append(first)
		# 	return merged

		# Still needs work but doesn't require scipy
		# a = self.highsLows
		# self._peaks = [i['high'] for i in a._values()]
		# self._troughs = [i['low'] for i in a._values()]
		# periodHours = self._value.hourly.period.seconds // 3600

		# arr = np.array([(i.timestamp.timestamp(), float(i.value)) for i in source])
		peaks, troughs = findPeaksAndTroughs(self.smoothed, spread=timedelta(hours=9))
		# peaks = [i for j in peaks for i in j]
		# troughs = [i for j in troughs for i in j]

		# if multiplier > 1:
		# 	peaks = [self.rawData[int(i / 1)] for i in peaks]
		# 	troughs = [self.rawData[int(i / 1)] for i in troughs]
		# else:
		# 	peaks = [self.rawData[i] for i in peaks]
		# 	troughs = [self.rawData[i] for i in troughs]

		# peaks = mergeSequentialDuplicates(peaks)
		# troughs = mergeSequentialDuplicates(troughs)
		# peaks = filterBest(peaks, self.rawData, indexes=False, high=True)
		# troughs = filterBest(troughs, self.rawData, indexes=False, high=False)
		return peaks, troughs

	@overload
	def __parseData(self, values: Iterable[Union[TimeAwareValue, 'PeakTroughData']]):
		...  # _values is an iterable of TimeAwareValue or PeakTroughData that contain both x and y axes

	@overload
	def __parseData(self, value: Union[TimeAwareValue, 'PeakTroughData']):
		...  # value is a single TimeAwareValue or PeakTroughData that contains both x and y axes

	@overload
	def __parseData(self, x: Iterable[Union[float, int]], y: Iterable[Union[float, int]]):
		...  # x and y are iterables of floats or ints

	@overload
	def __parseData(self, x: Union[float, int], y: Union[float, int]):
		...  # x and y are single _values of floats or ints

	@overload
	def __parseData(self, T: Iterable[Iterable[Union[float, int]]], axis: Axis):
		...  # T is a 1d array of floats or ints that requires axis to be specified

	@overload
	def __parseData(self, v: Union[float, int], axis: Axis):
		...  # v is a single float or int that requires axis to be specified

	def __parseData(self, *T, **K) -> tuple[Optional[Union[float, int, Iterable]], Optional[Union[float, int, Iterable]]]:
		axis, T, K = self.__findAxis(*T, **K)
		x = K.get('x', None)
		y = K.get('y', None)
		if '_values' in K:
			T = K['_values']
			if isinstance(T[0], PeakTroughData):
				T = np.array([[t.timestamp.timestamp(), t.value.value] for t in T])
				x, y = np.swapaxes(T, 0, 1)
			elif isinstance(T[0], TimeAwareValue):
				T = np.array([[t.timestamp.timestamp(), t.value] for t in T])
				x, y = np.swapaxes(T, 0, 1)
			if axis is not None:
				if axis == Axis.Both:
					pass
				elif axis & Axis.X:
					y = None
				elif axis & Axis.Y:
					x = None
			return x, y

		if len(T) == 0:
			return x, y
		if len(T) == 1:  # unwrap T
			T = T[0]
		if len(T) == 1 and isinstance(T, Iterable):
			T = T[0]
			if len(T) == 2:
				x, y = T
				if isinstance(x, Iterable) and isinstance(y, Iterable):
					return x, y
				if isinstance(x, TimeAwareValue) and isinstance(y, TimeAwareValue):
					return x.value, y.value
			if isinstance(T[0], Iterable):
				if len(T[0]) == 2:
					x, y = T[0]
				if axis == Axis.Horizontal:
					x, y = T[0], None
				else:
					x, y = None, T[0]
		if len(T) == 2:
			x, y = T

			if isinstance(x, Iterable) and isinstance(y, Iterable):
				return x, y
			if isinstance(x, TimeAwareValue) and isinstance(y, TimeAwareValue):
				return x.value, y.value
			return x, y
		if len(T) > 2:
			if isinstance(T[0], TimeAwareValue):
				T = np.array([[t.timestamp.timestamp(), t.value] for t in T])
				x, y = np.swapaxes(T, 0, 1)
			elif isinstance(T[0], PeakTroughData):
				T = np.array([[t.timestamp.timestamp(), t.value.value] for t in T])
				x, y = np.swapaxes(T, 0, 1)
				if axis is not None:
					if not axis ^ Axis.Both:
						pass
					elif axis ^ Axis.Horizontal:
						y = None
					elif axis ^ Axis.Vertical:
						x = None
				return x, y
			if axis is None:
				raise ValueError('Axis must be specified')
			if axis == Axis.X:
				x, y = T, None
			else:
				x, y = None, T
			return x, y
		raise ValueError('Invalid data')

	@staticmethod
	def __findAxis(*T, **K) -> tuple[Axis, tuple, dict]:
		if any(isinstance(i, Axis) for i in T):
			axis = T.pop(T.index([i for i in T if isinstance(i, Axis)][0]))
		elif 'axis' in K:
			axis = K.pop('axis')
		else:
			axis = None
		return axis, T, K

	def normalize(self, *T, **K) -> Union[QPointF, list[QPointF]]:
		"""
		:param axis: Vertical or Horizontal
		:return: tuple of normalized points (_values between 0 and 1)
		"""
		x, y = self.__parseData(*T, **K)

		if y is not None:
			try:
				y = (y - y.min())/y.ptp()
			except RuntimeWarning:
				print(y.min(), y.ptp(), y)
				print('##################### RuntimeWarning ###################')
		if x is not None:
			# start = self.figure.figureMinStart()
			start = datetime.now()
			x = (x - start.timestamp())/self.figure.figureTimeRangeMax.total_seconds()
		return x, y

	def normalizeToFrame(self, *T, **K):
		x, y = self.__parseData(*T, **K)

		margins = self.figure.marginRect
		margins.setWidth(self.figure.geometry.absoluteWidth)

		if y is not None:
			y = y * margins.height() + margins.top()
		if x is not None:
			x = x * margins.width() + margins.left()
		return x, y

	def normalizeData(self):
		x, y = None, None
		values = {'axis': Axis.Neither}
		if self.__normalX is None:
			values['axis'] |= Axis.X
			values['x'] = self.data[0]
		if self.__normalY is None:
			values['axis'] |= Axis.Y
			values['y'] = self.data[1]
		if values['axis']:
			x, y = self.normalize(**values)
		if x is not None:
			self.__normalX = x
		if y is not None:
			self.__normalY = y

	@property
	def plotValues(self) -> tuple[np.array, np.array]:
		x = self.normalizedX
		y = self.normalizedY
		start = self.figure.graph.timeframe
		return [QPointF(ix, iy) for ix, iy in zip(self.normalizedX, self.normalizedY)]

	@property
	def normalizedX(self):
		if self.__normalX is None:
			self.normalizeData()
		return self.__normalX

	@property
	def normalizedY(self):
		if self.__normalY is None:
			self.normalizeData()
		return self.__normalY

	@property
	def peaks(self) -> List[Measurement]:
		return self.__labels[0]

	@property
	def troughs(self) -> List[Measurement]:
		return self.__labels[1]

	@property
	def array(self) -> np.array:
		if self.rawData:
			return np.array(self.rawData.array, dtype=self.dtype)
		if self._array is None:
			self._array = np.array(self.rawData, dtype=self.dtype)
		return self._array

	@property
	def timeArray(self) -> np.array:
		# x = self.rawData.timeseriesInts
		return self.data[0]

	# @property
	# def timeArrayInterpolated(self):
	# 	# if not self._interpolated:
	# 	# 	return self.timeArray
	# 	values = self.rawData.timeseriesInts
	# 	x_min = values[0]
	# 	x_max = values[-1]
	# 	return np.linspace(x_min, x_max, self.length)
	# # 
	# @property
	# def interpolated(self) -> np.array:
	# 	f = interp1d(self.timeArray, self.smoothed, kind='cubic')
	# 	return f(self.timeArrayInterpolated)
	# 	# if not self._interpolate or not self.isInterpolatable:
	# 	# 	return self.array
	# 	print('building interp')
	# 	if self._interpolated is None:
	# 		f = interp1d(self.timeArray, self.smoothed, kind='cubic')
	# 		# self._interpolated = interpData(self.smoothed, self.multiplier, self.length)
	# 		self._interpolated = f(self.timeArrayInterpolated)
	# 	return self._interpolated

	@cached_property
	def smoothed(self) -> np.array:
		tz = config.tz
		dataType = self.dataType
		if {'denominator', 'numerator'}.intersection(dataType.__init__.__annotations__.keys()):
			value = self.value.first.value
			n = type(value.n)
			d = type(value.d)(1)
			return [TimeSeriesItem(self.dataType(n(y), d), timestampToTimezone(x, tz=tz)) for x, y in zip(*self.data)]
		return [TimeSeriesItem(self.dataType(y), timestampToTimezone(x, tz=tz)) for x, y in zip(*self.data)]

	@cached_property
	def list(self):
		return self.value[self.graph.timeframe.historicalStart:]

	@staticmethod
	def smooth_data_np_convolve(arr, span):
		return np.convolve(arr, np.ones(span*2 + 1)/(span*2 + 1), mode="valid")

	@cached_property
	def data(self) -> np.array:
		arr = self.list
		# a = isinstance(arr[0], Realtime)
		# timestamps = np.array([i.timestamp.timestamp() for i in arr if not isinstance(i, Realtime)])
		#
		# meanPeriod = np.unique(timestamps[1:-2] - np.roll(timestamps, 1)[1:-2])
		newPeriod = int(round(self.graph.secondsPerPixel*5))
		# newPeriod = 1800
		start = arr[0].timestamp.timestamp()
		end = arr[-1].timestamp.timestamp()

		xS = np.arange(start, end, newPeriod)
		arrL = np.array([(i.timestamp.timestamp(), float(i.value)) for i in arr])
		# remove duplicates x values

		x, y = np.unique(arrL, axis=0).T

		# f = sp.interpolate.BarycentricInterpolator(x, y)
		# f = sp.interpolate.PchipInterpolator(x, y)
		# y = f(xS)
		# return xS, y
		# y = smoothData(y, 17, 5)
		if len(x) == 1:
			return x, y
		# i = interp1d(x, y, kind='quadratic')
		i = CubicSpline(x, y)
		y = i(xS)

		# smoothi
		# ngFactor = int(round(500/newPeriod*17))

		def smooth_data_np_cumsum_my_average(arr, span):
			cumsum_vec = np.cumsum(arr)
			moving_average = (cumsum_vec[2*span:] - cumsum_vec[:-2*span])/(2*span)

			# The "my_average" part again. Slightly different to before, because the
			# moving average from cumsum is shorter than the input and needs to be padded
			front, back = [np.average(arr[:span])], []
			for i in range(1, span):
				front.append(np.average(arr[:i + span]))
				back.insert(0, np.average(arr[-i - span:]))
			back.insert(0, np.average(arr[-2*span:]))
			return np.concatenate((front, moving_average, back))

		def gaussianKernel(size, sigma):
			filter_range = np.linspace(-int(size/2), int(size/2), size)
			kernel = np.array([1/(sigma*np.sqrt(2*np.pi))*np.exp(-x ** 2/(2*sigma ** 2)) for x in filter_range])
			return kernel/np.sum(kernel)

		sf = 8
		kernel = gaussianKernel(sf, sf*2)
		# kernel = (kernel - kernel.min()) / kernel.ptp()
		# kernel = kernel*(1/sum(kernel))
		# z = np.ones(sf*2 + 1)/(sf*2 + 1)
		# box = [0.1, 0.5, 1.0, 0.5, 0.1]
		# y = self.smooth_data_np_convolve(y, 2)
		y = np.convolve(y, kernel, mode='valid')
		# y = smooth_data_np_cumsum_my_average(y, sf)
		# y = gaussian_filter1d()
		# y = smoothData(y, min(len(y), smoothingFactor), 1)
		# x /= 4
		x = xS

		return x, y

	@property
	def dataType(self) -> type:
		return self.rawData[0].value.__class__

	@property
	def isInterpolatable(self) -> bool:
		return (self.isNumbers or isinstance(self.rawData[0], datetime)) and self._interpolate

	@property
	def isNumbers(self) -> bool:
		if self._numerical is None:
			try:
				sum(float(i.value) for i in self.rawData)
				self._numerical = True
			except TypeError:
				self._numerical = False
		return self._numerical

	@property
	def multiplier(self) -> int:
		if self._multiplier is None:
			#TODO: this is currently recursive, fix it
			return max(int(self.length / len(self)), 1)
		totalSeconds = self.value.period.total_seconds()
		return int(totalSeconds / self._multiplier.total_seconds())

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
			return len(self.data[0])
		return self._length

	@length.setter
	def length(self, value: int):
		self._multiplier = None
		self.__clearCache()
		self._length = int(value)

	@property
	def spread(self) -> int:
		return self._spread

	@spread.setter
	def spread(self, value: int):
		self.__clearCache()
		self._spread = value

	@property
	def order(self) -> int:
		return self._order

	@order.setter
	def order(self, value: int):
		self.__clearCache()
		self._order = value
		self.update()

	@property
	def allGraphics(self):
		if self._allGraphics is None:
			self._allGraphics = self.scene.createItemGroup([self.graphic, self.labels])
		return self._allGraphics

	@property
	def state(self):
		return {
			'labeled':     self.labeled,
			'plot':        self.graphic.state,
		}


class PathType(Enum):
	Linear = 0
	Cubic = 2
	Quadratic = 3
	Spline = 4


# Section Plot


class Plot(QGraphicsPathItem):
	""" The graphical plot of GraphItemData.
	All updates are handled by the GraphItemData.
	"""

	_dashPattern: list[int]
	_type: PathType
	figure: 'Figure'
	data: GraphItemData
	_style: Qt.PenStyle
	_scalar: float
	pathType: PathType
	_temperatureGradient: Optional[TemperatureGradient] = None
	__useCache: bool = False
	shadow = SoftShadow

	def __init__(self, parent: GraphItemData,
	             color: QColor = None,
	             gradient: str = '',
	             opacity: float = 1.0,
	             dashPattern: Union[Qt.PenStyle, Iterable, str] = Qt.SolidLine,
	             scalar: float = 1.0):
		self.__gradient = None
		self.data: GraphItemData = parent
		self.figure: 'Figure' = parent.figure

		self.scalar = scalar
		self.gradient = gradient
		self._normalPath = QPainterPath()
		self._shape = QPainterPath()

		# if morph:
		# 	data = self.figure.
		# 	if type(morph) == str:
		# 		morph = self.figure.data[morph]
		# 	if len(data) != len(morph):
		# 		morph = interpData(morph, newLength=len(data))
		# 	morph = normalize(morph) * 10
		# self.morph = morph
		super(Plot, self).__init__()
		self.color = color
		self.dashPattern = dashPattern
		self.setOpacity(opacity)
		self.setAcceptHoverEvents(True)
		self.setParentItem(self.figure)
		self.setFlag(QGraphicsItem.ItemIsMovable, False)
		self.setFlag(QGraphicsItem.ItemClipsToShape, True)
		self.setGraphicsEffect(Plot.shadow())

	def setZValue(self, value: int):
		super(Plot, self).setZValue(self.figure.zValue() + 1)

	def mousePressEvent(self, event) -> None:
		if self.shape().contains(event.pos()):
			event.accept()
			self.figure.setFocus(Qt.MouseFocusReason)
			self.figure.marginHandles.show()
		# print(f'Clicked: {self.data._value.value["@title"]} path at value {self.data.smoothed[round(event.pos().x() / self.figure.graph.pixelsPerHour)]} at {event.pos().y()}')
		# self.setSelected(True)
		# if debug:
		# 	self.data.updateEverything(None)

		else:
			event.ignore()
		super(Plot, self).mousePressEvent(event)

	def wheelEvent(self, event: QGraphicsSceneWheelEvent) -> None:
		if self.figure.hasFocus() and self._shape.contains(event.pos()):
			event.accept()
			self.scalar += event.delta()/1000
			self.update()
		else:
			event.ignore()

	@property
	def gradient(self):
		if self.__gradient is None and self._gradient and self.data.rawData:
			if self._gradient == 'TemperatureGradient':
				self.__gradient = TemperatureGradient(self)
		return self.__gradient

	@gradient.setter
	def gradient(self, value):
		self._gradient = value
		self.__gradient = None

	@property
	def scalar(self) -> float:
		return self._scalar

	@scalar.setter
	def scalar(self, value: Union[str, float, int]):
		if not isinstance(value, float):
			value = float(value)
		self._scalar = clamp(value, 0.0, 10)

	@property
	def color(self):
		if self._color is None:
			return colorPalette.windowText().color()
		return self._color

	@color.setter
	def color(self, value):
		if isinstance(value, str):
			if '#' in value:
				value = QColor(value)
			else:
				value = QColor(f'#{value}')
		self._color = value
		pen = self.pen()
		pen.setColor(self.color)
		self.setPen(pen)

	@property
	def api(self) -> 'API':
		return self._api

	@property
	def figure(self) -> 'Figure':
		return self._figure

	@figure.setter
	def figure(self, value: 'Figure'):
		self._figure = value

	@property
	def state(self):
		state = {
			'type':        DisplayType.LinePlot.value,
			'scalar':      round(self.scalar, 5),
			'dashPattern': str(tuple(self.dashPattern)).strip('()') if isinstance(self.dashPattern, list) else self.dashPattern,
			'gradient':    self._gradient or self.__gradient,
			'color':       rgbHex(*QColor(self.color).toTuple()[:3]).strip('#') if self._color is not None else None,
			'opacity':     self.opacity()
		}
		if state['opacity'] == 1.0:
			del state['opacity']
		return {k: v for k, v in state.items() if v}

	@property
	def dashPattern(self):
		if isinstance(self._dashPattern, Qt.PenStyle):
			return QPen(self._dashPattern).dashPattern()
		return self._dashPattern

	@dashPattern.setter
	def dashPattern(self, value):

		def convertPattern(value: str) -> list[int]:
			if not isinstance(value, str):
				pattern = value
			elif ',' in value:
				pattern = [int(v) for v in value.strip('[]').split(',') if v.strip().isdigit()]
			elif '-' in value:
				pattern = []
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
			if len(pattern)%2:
				pattern.pop(-1)
			return pattern

		self._dashPattern = convertPattern(value) if not isinstance(value, Qt.PenStyle) else value
		pen = self.pen()
		pen.setDashPattern(self.dashPattern)
		# pen.setCapStyle(Qt.PenCapStyle.FlatCap)
		# pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
		self.setPen(pen)

	def __repr__(self):
		return f"{self.__class__.__name__} {hex(id(self))} of '{self.data.value.key}' in figure '0x{self.figure.uuidShort}'"

	def _generatePen(self):
		weight = self.figure.parent.plotLineWeight() * self.scalar
		if self.gradient == 'temperature':
			self._temperatureGradient.update()
			brush = QBrush(self._temperatureGradient)
		else:
			brush = QBrush(self.color)
		pen = QPen(brush, weight)
		if isinstance(self.dashPattern, Iterable):
			pen.setDashPattern(self.dashPattern)
		# pen.setCapStyle(Qt.PenCapStyle.FlatCap)
		# pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
		else:
			pen.setStyle(self.dashPattern)

		return pen

	def shape(self) -> QPainterPath:
		return self._shape

	def onAxisTransform(self, axis: Axis):
		if axis & Axis.Y:
			self._updatePath()
		self.updateTransform()
		if self.gradient:
			self.updateGradient()
		self.update()
		if self.__useCache:
			self.setCacheMode(QGraphicsItem.CacheMode.ItemCoordinateCache)

	def onAxisChange(self, axis: Axis):
		self._updatePath()
		self.updateTransform()
		if self.gradient:
			self.updateGradient()
		self.update()

	def updateGradient(self):
		self.__gradient.update()
		pen = self.pen()
		brush = QBrush(self.__gradient)
		pen.setBrush(brush)
		self.setPen(pen)

	@property
	def _path(self):
		if self._normalPath.elementCount() == 0 and self.data.value:
			self._updatePath()
		return self._normalPath

	def _updatePath(self):
		self.prepareGeometryChange()
		self._normalPath.clear()

	def setPath(self, path: QPainterPath):
		super(Plot, self).setPath(path)
		self._updateShape()

	def _updateShape(self):
		qp = QPainterPathStroker()
		qp.setWidth(self.figure.graph.plotLineWeight())
		shape = qp.createStroke(self.path())
		self.prepareGeometryChange()
		self._shape = shape

	def updateTransform(self):
		# pen = self.pen()
		# # pen.setWidthF(self.figure.graph.plotLineWeight() / min(painter.worldTransform().m11(), painter.worldTransform().m22()) * self.scalar)
		# self.setPen(pen)
		p = self._path
		if p.elementCount():
			p = self.t.map(p)
			self.setPath(p)
		if self.__useCache:
			self.setCacheMode(QGraphicsItem.CacheMode.ItemCoordinateCache)

	@property
	def t(self) -> QTransform:
		t = QTransform(self.data.t)
		return t

	def setParentItem(self, parent: 'Figure'):
		self._figure = parent
		super(Plot, self).setParentItem(parent)

	def boundingRect(self):
		return self.figure.graph.proxy.boundingRect()


class LinePlot(Plot):
	_gradient: bool = False

	def __init__(self, *args, **kwargs):
		self._temperatureGradient = None
		self.penOffsetScaler = None
		self.penOffset = None
		self._shape = None
		self._dashPattern = None
		super(LinePlot, self).__init__(*args, **kwargs)

	def __getValues(self) -> list[QPointF]:
		values = self.data.plotValues
		if len(values) > 1200:
			log.warning(f'Plot path contains {len(values)} points and will result in performance issues')
		if len(values) > 2000:
			log.warning(f'Plot path contains {len(values)} points and will result in performance issues')
			return values[:1000]
		return values

	def _updatePath(self):
		# data = self.data
		# minY = data.normalizedY.min()
		# maxY = data.normalizedY.max()
		# minX = data.normalizedX.min()
		# maxX = data.normalizedX.max()
		# super(LinePlot, self)._updatePath()
		# self._normalPath.moveTo(minX, minY)
		# self._normalPath.lineTo(maxX, maxY)
		# self._normalPath.lineTo(0, 0)
		# self._normalPath.lineTo(.1, 0)
		# self._normalPath.lineTo(.10, .10)
		# self._normalPath.lineTo(.20, .10)
		# self._normalPath.lineTo(.20, .20)
		# self.updateTransform()

		values = self.__getValues()
		x = sum((value.x() for value in values[:3]))/3 - values[0].x()
		y = sum((value.y() for value in values[:3]))/3 - values[0].y()
		start = values[0] - QPointF(x, y)
		self._normalPath.clear()
		self._normalPath.moveTo(start)
		for value in values:
			self._normalPath.lineTo(value)

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
					ratio = abs(np.sin(np.radians(targetAngle)))
					reverseTarget.setLength(reverseTarget.length() * ratio)
				reverseSource = QLineF.fromPolar(
					source.length() * factor, source.angle()).translated(p1)
				sourceAngle = current.angleTo(source)
				if 90 < sourceAngle < 270:
					ratio = abs(np.sin(np.radians(sourceAngle)))
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

	def paint(self, painter: QPainter, option, widget=None):
		pen = self.pen()
		weight = self.figure.parent.plotLineWeight()*self.scalar
		t = painter.worldTransform()
		m_ = weight*max(t.m11(), t.m22())
		pen.setWidthF(m_)
		painter.setPen(pen)
		painter.drawPath(self.path())
	# super(LinePlot, self).paint(painter, option, widget)


class BackgroundImage(QGraphicsPixmapItem):

	def __init__(self, parent: 'GraphPanel', data: np.array, *args, **kwargs):
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
		raw *= 255*opacity
		raw = raw.astype(np.uint8)

		return raw


@Slot()
def removeInstance(*args):
	print(args)


# Section Plot Text


class PlotText(Text):
	baseLabelRelativeHeight = 0.3
	idealTextSize: Centimeter
	shadow = SoftShadow

	def __init__(self, *args, **kwargs):
		super(PlotText, self).__init__(*args, **kwargs)
		if isinstance(self.parent, GraphItemData):
			self.setParentItem(self.parent.figure)
		else:
			pass
		self.setGraphicsEffect(PlotText.shadow())

	@property
	def figure(self):
		return self._parent.figure

	def setZValue(self, z: float) -> None:
		z = max(i.graphic.zValue() for i in self.figure.plots) + 10
		super(Text, self).setZValue(z)

	def refresh(self):
		super(PlotText, self).refresh()

	@property
	def limitRect(self) -> QRectF:
		rect = QRectF(0, 0, 200, self.parent.graph.height()*self.baseLabelRelativeHeight)
		rect.moveCenter(self.boundingRect().center())
		return rect


class PeakTroughLabel(PlotText):
	_scaleSelection = min
	offset = 15
	baseLabelRelativeHeight = 0.1
	idealTextSize: Centimeter = Centimeter(.75)

	def __init__(self, parent: 'PlotLabels', value: 'PeakTroughData'):
		self.peakList = parent
		super(PeakTroughLabel, self).__init__(parent=parent.data)
		self.value = value
		# self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
		self.setParentItem(parent.labels)

	def updateTransform(self):
		if self._value is not None and self._value.isPeak:
			self.moveBy(0, -self.offset)
		else:
			self.moveBy(0, self.offset)

	def delete(self):
		self.figure.scene().removeItem(self)

	@property
	def text(self) -> str:
		return str(self.value)

	@property
	def value(self):
		if self._value is None:
			return None
		return self._value.value

	@value.setter
	def value(self, value):
		self._value = value
		self.updateTransform()

	def update(self):
		super(PeakTroughLabel, self).update()

	# self.setTransform(self.parentItem().parentItem().t.inverted()[0] * self.transform())

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemPositionChange:
			containingRect = self.figure.contentsRect()
			selfRect = self.boundingRect()
			tr = self.transform()
			selfRect.translate(tr.dx(), tr.dy())
			maxX = containingRect.right() - selfRect.width() - 10
			minX = containingRect.left() + 10
			maxY = containingRect.bottom() - selfRect.height() - 10
			minY = containingRect.top() + 10
			x, y = value.toTuple()

			plotShape = self.parent.graphic.mapToScene(self.parent.graphic.shape())
			diff = QPointF(x, y) - self.pos()
			shape = self.mapToScene(self.shape())
			shape.translate(diff)
			intersectedRect = plotShape.intersected(shape).boundingRect()

			x = clamp(x, minX, maxX)
			y = clamp(y, minY, maxY)

			if intersectedRect.height():
				if self.alignment().vertical.isTop:
					y += intersectedRect.height()
				else:
					y -= intersectedRect.height()

			value = QPointF(x, y)
		# elif change == QGraphicsItem.ItemPositionHasChanged:
		# 	sceneShape = self.mapToScene(self.shape())
		# 	for i in self.parentItem().childItems():
		# 		if i is self:
		# 			continue
		# 		if not isinstance(i, PeakTroughLabel):
		# 			continue
		# 		otherSceneShape = i.mapToScene(i.shape())
		# 		if sceneShape.intersects(otherSceneShape):
		# 			i.hide()
		return super(PeakTroughLabel, self).itemChange(change, value)

	@property
	def scalar(self):
		return self.peakList.scalar

	@scalar.setter
	def scalar(self, value):
		self.peakList.scalar = value

	def wheelEvent(self, event: QGraphicsSceneWheelEvent) -> None:
		self.scalar += event.delta()/1000

	def paint(self, painter, option, widget=None):
		# keep the text visible as long as the center is
		sRect = self.sceneBoundingRect()
		grRect = self.figure.graph.sceneBoundingRect()
		if not grRect.contains(sRect):
			if grRect.contains(sRect.center()):
				subRect = grRect.intersected(sRect)
				painter.translate(subRect.topLeft() - sRect.topLeft())
			else:
				return

		super(PlotText, self).paint(painter, option, widget)


# def paint(self, painter, option, widget):
# 	addCrosshair(painter)
# 	# tW = painter.worldTransform()
# 	# t = self.transform().inverted()[0]
# 	# scale = self._scaleSelection(tW.m11(), tW.m22())
# 	# t.scale(1 / tW.m11(), 1 / tW.m22())
# 	# t.scale(scale, scale)
# 	# painter.setTransform(t, True)
# 	# painter.setTransform(self.transform(), True)
# 	# option.exposedRect = self.fixExposedRect(option.rect, t, painter)
# 	super(Text, self).paint(painter, option, widget)


@dataclass
class PeakTroughData:
	value: Container
	timestamp: datetime
	parent: 'PlotLabels' = field(repr=False, compare=False)
	isPeak: bool
	graphic: PeakTroughLabel = field(init=False)

	def __post_init__(self):
		self.graphic = PeakTroughLabel(self.parent, self)

	def delete(self):
		self.graphic.delete()

	def update(self, **kwargs):
		# if not any(getattr(self, k) != v for k, v in kwargs.items()) and self.parent.normalized:
		# 	self.parent.clearNormalized()
		for key, value in kwargs.items():
			setattr(self, key, value)
		self.graphic.update()


class PeakTroughGroup(QGraphicsItemGroup):

	def __init__(self, figure: 'Figure'):
		super(PeakTroughGroup, self).__init__(figure.parentItem())
		self.figure = figure


class PlotLabels(list):
	data: GraphItemData
	key: CategoryItem
	_scalar: float = 1.0
	__xValues: list[float] = None  # Normalized x _values
	__yValues: list[float] = None  # Normalized y _values
	_xValues: list[float] = None  # Mapped x _values
	_yValues: list[float] = None  # Mapped y _values
	log = log.getChild('Plotlabels')

	def __init__(self, key: CategoryItem, data: GraphItemData, peaksTroughs: bool = True):
		self.peaksTroughs = peaksTroughs
		self.key = key
		self.data = data
		super(PlotLabels, self).__init__()
		self.labels = PeakTroughGroup(self.figure)

		self.refreshList()

		self.setLabels()

	def onValueChange(self, axis: Axis):
		self.resetAxis(axis)
		self.refreshList()
		self.setLabels()

	def onAxisTransform(self, axis: Axis):
		self.quickSet()

	def __hash__(self):
		return hash(self.key)

	@property
	def scalar(self):
		return self._scalar

	@scalar.setter
	def scalar(self, value):
		self._scalar = value
		if len(self) > 0:
			self.setLabels()

	@property
	def figure(self) -> 'Figure':
		return self.data.figure

	@property
	def plot(self) -> LinePlot:
		return self.data.graphic

	def clear(self, after: int = 0):
		while after < len(self):
			i = self.pop()
			i.delete()

	def update(self, values: list[dict]):
		self.clear(len(values))
		if len(values) > len(self):
			self.extend([PeakTroughData(parent=self, **value) for value in values[len(self):]])
		for newValue, oldValue in zip(values, self):
			oldValue.update(**newValue)

	# if (self[1].timestamp - self[0].timestamp).total_seconds() / 3600 <= 6:
	# 	v = self.pop(0)
	# 	v.delete()
	# if (self[-1].timestamp - self[-2].timestamp).total_seconds() / 3600 <= 6:
	# 	v = self.pop()
	# 	v.delete()
	# self.pop(0).delete()

	def refreshList(self):
		if self.peaksTroughs and self.data.value:
			peaks, troughs = self.data.peaksAndTroughs
			peaks = [{'timestamp': item.timestamp, 'value': item, 'isPeak': True} for item in peaks]
			troughs = [{'timestamp': item.timestamp, 'value': item, 'isPeak': False} for item in troughs]
			values = [x for x in chain.from_iterable(zip_longest(peaks, troughs)) if x is not None]
			values = sorted(values, key=lambda x: x['timestamp'])
		else:
			values = [{'timestamp': item.timestamp, 'value': item, 'isPeak': True} for item in self.data.rawData if item.timestamp.hour%3 == 0]
		self.update(values)

	@property
	def shouldDisplay(self):
		if self.peaksTroughs:
			return self.data.figure.graph.timeframe.hours > 18
		else:
			return self.data.figure.graph.timeframe.hours <= 18

	def setLabels(self):
		if self.shouldDisplay:
			self.labels.show()
			values = self.values
			withLambda = False
			if withLambda:
				list(map(lambda item, value: item.graphic.setPos(*value), self, values))
			else:
				# plot_shape = self.plot.mapToScene(self.plot.shape())
				for i, item in enumerate(self):
					item.graphic.setPos(values.at(i))
					item.graphic.refresh()
					# item.graphic.updateFontSize()
					alightment = AlignmentFlag.Bottom if item.isPeak else AlignmentFlag.Top
					item.graphic.setAlignment(alightment)
					# shape = item.graphic.mapToScene(item.graphic.shape())
					# intersection = shape.intersected(plot_shape)
					# if not intersection.isEmpty():
					# 	x = value[0]
					# 	rect = intersection.boundingRect()
					# 	y = rect.top() if item.isPeak else rect.bottom()
					# 	item.graphic.setPos(x, y)
					#
					# others = [o for o in self[max(0, i - 3):i] if shape.intersects(o.graphic.mapToScene(o.graphic.shape()))]
					# if others:
					# 	item.graphic.hide()
					# # _all = [*others, item]
					# # x = sum(i.graphic.pos().x() for i in _all) / len(_all)
					# # y = sum(i.graphic.pos().y() for i in _all) / len(_all)
					# # if item.isPeak:
					# # 	m = max(others, key=lambda x: x.value)
					# # else:
					# # 	m = min(others, key=lambda x: x.value)
					# # m.graphic.setPos(x, y)
					# # for it in _all:
					# # 	if it is m:
					# # 		continue
					# # 	it.graphic.hide()
					# else:
					# 	item.graphic.show()

					i += 1
		else:
			self.labels.hide()

	def quickSet(self):
		values = self.values
		firstItem = self[0].graphic
		# font = QFont(firstItem.font().family(), self.figure.parent.fontSize * firstItem.scalar)
		for i, item in enumerate(self):
			item.graphic.setPos(values.at(i))
			item.graphic.refresh()

	# cols = item.graphic.collidingItems(Qt.ItemSelectionMode.IntersectsItemBoundingRect)
	# for i in cols:
	# 	if isinstance(i, PeakTroughLabel):
	# 		i.hide()

	def normalizeValues(self):
		# start with assuming neither axis needs to be normalized
		kwargs = {'axis': Axis.Neither}
		if self.__xValues is None:  # if x _values are already normalized, add Axis.X to axis
			kwargs['axis'] |= Axis.X
		if self.__yValues is None:  # if y _values are already normalized, add Axis.Y to axis
			kwargs['axis'] |= Axis.Y
		if kwargs['axis']:
			kwargs['_values'] = self
		x, y = self.data.normalize(**kwargs)
		if x is not None:
			self.__xValues = x
		if y is not None:
			self.__yValues = y
		else:
			pass  # Both axes are already normalized

	def resetAxis(self, axis: Axis.Both):
		if axis & Axis.X:
			self.__xValues = None
		if axis & Axis.Y:
			self.__yValues = None
		if axis:
			self.normalizeValues()
			self.setLabels()

	def onAxisChange(self, axis):
		self.resetAxis(axis)

	@property
	def normalizedX(self):
		if self.__xValues is None:
			self.normalizeValues()
		return self.__xValues

	@property
	def normalizedY(self):
		if self.__yValues is None:
			self.normalizeValues()
		return self.__yValues

	@property
	def values(self):
		return self.data.t.map(QPolygonF([QPointF(*i) for i in zip(self.normalizedX, self.normalizedY)]))

	def isVisible(self):
		return any(i.graphic.isVisible() for i in self)

	def setVisible(self, visible: bool):
		list(map(lambda label: label.setVisible(visible), self.labels.childItems()))


# Section TimeMarkers


class TimeMarkers(QGraphicsRectItem):

	def __init__(self, parent):
		self.time = time()
		self.graph = parent.graph
		lineWidth = 1
		pen = QPen(colorPalette.windowText().color(), lineWidth)
		pen.setDashPattern([3, 3])
		self.hour = pen

		lineWidth *= 1.2
		pen = QPen(colorPalette.windowText().color(), lineWidth)
		pen.setDashPattern([3, 3])
		self.hour3 = pen

		lineWidth *= 1.2
		pen = QPen(colorPalette.windowText().color(), lineWidth)
		pen.setDashPattern([3, 3])
		self.hour6 = pen

		lineWidth *= 1.5
		pen = QPen(colorPalette.windowText().color(), lineWidth)
		pen.setDashPattern([3, 3])
		self.hour12 = pen

		lineWidth *= golden
		pen = QPen(colorPalette.windowText().color(), lineWidth)
		# pen.setDashPattern([2, 2])
		self.hour24 = pen
		super(TimeMarkers, self).__init__(parent)
		self.parentItem().parentItem().parentItem().signals.resized.connect(self.updateRect)
		self.parentItem().parentItem().graph.timeframe.connectItem(self.onAxisChange)
		self.parentItem().parentItem().graph.axisTransformed.connectSlot(self.onAxisChange)
		self.setOpacity(0.4)
		self.setZValue(-100)
		# self.setCacheMode(QGraphicsItem.ItemCoordinateCache)
		self.reset()

	def onAxisChange(self, axis: Axis):
		# if axis & Axis.X:
		clearCacheAttr(self, 'hours', 'lines', 'paintedLines')
		self.updateRect()
		rect = self.deviceTransform(self.scene().views()[0].transform()).mapRect(self.rect())
		rect = self.rect()
		# self.setCacheMode(QGraphicsItem.NoCache)
		self.reset()
		# self.setCacheMode(QGraphicsItem.ItemCoordinateCache)
		# self.setCacheMode(QGraphicsItem.ItemCoordinateCache, rect.size().toSize())
		t = QTransform()
		t.translate(self.xOffset(), 0)
		self.setTransform(t)

	# self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
	# self.setCacheMode(self.ItemCoordinateCache, self.deviceTransform(self.scene().views()[0].transform()).mapRect(self.rect()).size().toSize())

	def updateRect(self, *args):
		self.setRect(self.parentItem().rect())

	# def boundingRect(self) -> QRectF:
	# 	# t = self.sceneTransform()
	# 	# tl = QTransform.fromScale(t.m11(), t.m22()).inverted()[0] * t
	# 	# return tl.mapRect(self.rect())
	# 	return self.parentItem().boundingRect()  # .translated(self.xOffset(), 0)
	#
	# def sceneBoundingRect(self) -> QRectF:
	# 	return self.parentItem().sceneBoundingRect()

	def reset(self):
		while self.childItems():
			self.childItems()[0].setParentItem(None)

		for k, group in self.paintedLines.items():
			pen = QPen(group['pen'])
			pen.setWidthF(pen.widthF()*0.5)
			for line in group['values']:
				lineItem = QGraphicsLineItem(line, self)
				lineItem.setPen(pen)
		# painter.setPen(pen)
		# painter.drawLines(group['values'])

	# def paint(self, painter: QPainter, option, widget):
	# 	# t = painter.worldTransform()
	# 	# xOffset = self.xOffset()
	# 	# painter.translate(xOffset, 0)
	# 	print('painting lines')
	# 	for k, group in self.paintedLines.items():
	# 		pen = QPen(group['pen'])
	# 		pen.setWidthF(pen.widthF())
	# 		painter.setPen(pen)
	# 		painter.drawLines(group['values'])
	#
	# 	super(TimeMarkers, self).paint(painter, option, widget)

	@cached_property
	def paintedLines(self):
		pixelHour = self.parentItem().graph.pixelsPerHour
		t = self.scene().views()[0].transform()

		# line every 2cm
		dpi = (app.screenAt(self.scene().views()[0].pos()) or app.primaryScreen()).logicalDotsPerInchX()
		pixelsPerCentimeter = dpi/2.54
		skipFactor = pixelsPerCentimeter*2/pixelHour/t.m11()

		markEveryNthHour = closestCeil([1, 3, 6, 7, 12, 24, 48], skipFactor)
		if markEveryNthHour == 7:
			markEveryNthHour = 6
		return {k: v for k, v in self.lines.items() if k >= markEveryNthHour}

	@cached_property
	def lines(self):
		hours = self.hours

		minY = -2
		maxY = (self.parentItem().graph.height()) + 2
		pixelHour = self.parentItem().graph.pixelsPerHour

		lines = [(hour, QLineF(hour*pixelHour, minY, hour*pixelHour, maxY)) for hour in range(hours)]
		daily = []
		bidaily = []
		quaterly = []
		three = []
		hourly = []
		lines.pop(0)
		for value in lines:
			hour, line = value
			if hour%24 == 0:
				daily.append(line)
			elif hour%12 == 0:
				bidaily.append(line)
			elif hour%6 == 0:
				quaterly.append(line)
			elif hour%3 == 0:
				three.append(line)
			else:
				hourly.append(line)
		return {
			24: {
				'pen':    self.hour24,
				'values': daily
			},
			12: {
				'pen':    self.hour12,
				'values': bidaily
			},
			6:  {
				'pen':    self.hour6,
				'values': quaterly
			},
			3:  {
				'pen':    self.hour3,
				'values': three
			},
			1:  {
				'pen':    self.hour,
				'values': hourly
			}
		}

	def xOffset(self):
		dayStart = self.parentItem().graph.timeframe.historicalStart.replace(hour=0, minute=0, second=0, microsecond=0)
		xOffset = (dayStart - self.parentItem().graph.timeframe.start).total_seconds()*self.parentItem().graph.pixelsPerSecond
		return xOffset

	@cached_property
	def hours(self):
		start = self.parentItem().timeStart()
		start = start.replace(hour=0, minute=0, second=0, microsecond=0)
		end = self.parentItem().timeEnd()
		end = end.replace(day=end.day, hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
		hours = int((end - start).total_seconds()/3600)
		return hours


def useHeight(_, *args):
	return args[-1]


class TimeStampText(PlotText):
	formatID: int
	defaultFormatID = 3
	formatStrings = ['%H:%M:%S.%f', '%H:%M:%S', '%H:%M', '%-I%p', '%A', '%a']
	scalar = 0.40
	displayScale = 1
	baseLabelRelativeHeight = 0.05
	_scaleSelection = useHeight
	idealTextSize: Centimeter = Centimeter(0.3)

	worstStrings = {}

	def hasCollisions(self, *items):
		t = self.scene().views()[0].transform()
		rects = [t.mapRect(item.sceneBoundingRect()) for item in items]
		# i = self.collidingItems(Qt.IntersectsItemBoundingRect)
		return any(t.mapRect(self.sceneBoundingRect()).intersects(rect) for rect in rects)

	def __init__(self, parent: 'DayAnnotations', timestamp: datetime, spread: timedelta, formatID: int = 3):
		self.spread: timedelta = spread
		self.graph = parent.graph
		self.formatID = formatID
		super(TimeStampText, self).__init__(parent=parent, value=timestamp, scalar=self.scalar)
		self.update()
		self.setGraphicsEffect(PlotText.shadow())
		self.setFlag(QGraphicsItem.ItemIgnoresTransformations, False)
		self.alignment = AlignmentFlag.Bottom
		self.setParentItem(parent)
		self.refresh()

	def updateItem(self) -> None:
		self.setZValue(self.parent.zValue() + 1)
		self.setPos(self.position())

	@property
	def allowedWidth(self) -> float:
		return self.spread.total_seconds()*self.graph.pixelsPerHour/3600

	def setZValue(self, z: float) -> None:
		super(Text, self).setZValue(z)

	@property
	def limitRect(self) -> QRectF:
		if self.scene():
			# window = self.scene().views()[0]
			# t = self.worldTransform()
			# rect = t.map(self.path()).boundingRect()
			# physicalHeight = rect.height() / window.physicalDpiY() * 2.54

			window = self.scene().views()[0]
			t = self.worldTransform()
			rect = t.map(self.path()).boundingRect()
			physicalHeight = window.physicalDpiY()*float(self.idealTextSize.inch)  # * t.inverted()[0].m11()
		else:
			physicalHeight = float(self.idealTextSize/72*2.54)

		rect = QRectF(0, 0, self.allowedWidth, physicalHeight)
		rect.moveCenter(self.boundingRect().center())
		# rect.moveCenter(self.position())
		return rect

	#
	# def updateFontSize(self):
	# 	font = self.font()
	# 	font.setPixelSize(round(self.graph.fontSize * self.scalar * self.displayScale))
	# 	self.setFont(font)
	# 	self.update

	@property
	def spread(self):
		return self._spread

	@spread.setter
	def spread(self, value):
		self._spread = value
		if self._spread >= timedelta(days=1):
			self.formatID = 5

	def position(self):
		start = datetime.now(tz=config.tz)
		x = (self._value - start).total_seconds()/3600*self.graph.pixelsPerHour
		y = self.graph.height() - 10
		# y *= self.sceneTransform().inverted()[0].m22()
		# x *= self.sceneTransform().inverted()[0].m11()
		return QPointF(x, y)

	@Text.value.setter
	def value(self, value: datetime):
		Text.value.fset(self, value)
		self.updateItem()

	@property
	def text(self) -> str:
		if self._value:
			value = self.value.strftime(self.formatStrings[self.formatID]).lower()
			return value
		return ''

	def resetFormatID(self):
		self.formatID = self.defaultFormatID
		self.displayScale = 1
		self.refresh()

	@property
	def isHourMarker(self):
		return 'h' in self.formatStrings[self.formatID].lower() or 'i' in self.formatStrings[self.formatID].lower()

	@property
	def isDayMarker(self):
		return 'a' in self.formatStrings[self.formatID].lower()

	def paint(self, painter: QPainter, option, widget=None):
		w = painter.worldTransform()
		scale = min(w.m11(), w.m22())
		# if self.font().pointSizeF() > self.minimumFontSize * scale:
		# 	scale = self.minimumFontSize / self.font().pointSizeF()
		self.screenWidth = option.rect.width()*scale

		self.screenHeight = option.rect.height()*scale
		super(TimeStampText, self).paint(painter, option, widget)


class DayMarkerText(TimeStampText):
	scalar = 1
	defaultFormatID = 4
	dayLabelRelativeHeight = 0.3

	def __init__(self, parent: 'DayAnnotations', timestamp: datetime, formatID: int = 4, *args, **kwargs):
		super(DayMarkerText, self).__init__(parent=parent, timestamp=timestamp, formatID=formatID, *args, **kwargs)
		self.update()
		self.setPlainText(self.text())
		self.setOpacity(0.6)
		# self.alignment().vertical = AlignmentFlag.Center
		# self.alignment.vertical = AlignmentFlag.Top
		self.updateTransform()

	def position(self):
		start = self.parent.displayStart()
		x = (self._value - start).total_seconds()/3600*self.graph.pixelsPerHour
		y = self.graph.height()/2
		# y *= self.sceneTransform().inverted()[0].m22()
		# x *= self.sceneTransform().inverted()[0].m11()
		return QPointF(x, y)

	def text(self) -> str:
		return self.value.strftime(self.formatStrings[self.formatID])

	def setTransform(self, transform: QTransform, combine: bool = False):
		super(DayMarkerText, self).setTransform(transform, combine)


# Section Annotations


class HourLabels(dict):
	markerSpans = [1, 3, 6, 12]
	__spanIndex = 0

	def __init__(self, parent: 'DayAnnotations'):
		self.parent = parent
		self.graph = parent.graph
		self.graph.timeframe.connectItem(self.onAxisChange)
		self.graph.axisTransformed.connectSlot(self.onAxisTransform)
		self.update()

	def __hash__(self):
		return id(self)

	def onAxisChange(self, axis: Axis):
		self.update()
		self.refresh()
		if axis & Axis.X:
			pass

	def onAxisTransform(self, axis: Axis):
		self.update()
		self.refresh()

	def refresh(self):
		l = list(self.values())

		l = [x for x in l if x.isVisible()]
		if len(l) < 1:
			return
		keystone = l[0]
		others = l[1:24//self.span]
		hourPixelWidth = self.graph.pixelsPerHour*self.graph.worldTransform().m11()
		spans = np.array(self.markerSpans)*hourPixelWidth
		labelScreenWidth = keystone.screenWidth*1.2

		lst = np.asarray(spans)
		idx = (np.abs(lst - labelScreenWidth)).argmin()
		newVal = lst[idx]
		if newVal > labelScreenWidth:
			i = idx
		else:
			i = idx + 1
		# if keystone.font().pointSizeF() * self.graph.worldTransform().m22() > keystone.minimumDisplayHeight:
		# 	i += 1

		# i = closest(spans, labelScreenWidth, returnIndex=True)
		self.spanIndex = i
		# if hourPixelWidth < keystone.screenWidth:
		# 	self.spanIndex += 1
		# elif hourPixelWidth < keystone.screenWidth * 2:
		# 	self.spanIndex -= 1
		# elif abs(keystone.sceneTransform().mapRect(keystone.textRect).x() - others[0].sceneTransform().mapRect(others[0].textRect).x()) > keystone.sceneTransform().mapRect(keystone.textRect).width() * 1.3:
		# 	self.spanIndex -= 1
		self.__showHideItems()

	@property
	def span(self):
		return self.markerSpans[self.__spanIndex]

	@property
	def spanNext(self):
		i = clamp(self.__spanIndex + 1, 0, len(self.markerSpans) - 1)
		return self.markerSpans[i]

	@property
	def spanPrevious(self):
		i = clamp(self.__spanIndex - 1, 0, len(self.markerSpans) - 1)
		return self.markerSpans[i]

	@property
	def spanIndex(self):
		return self.__spanIndex

	@spanIndex.setter
	def spanIndex(self, value):
		value = int(value)
		value = clamp(value, 0, len(self.markerSpans) - 1)
		if self.__spanIndex != value:
			self.__spanIndex = value
			self.__showHideItems()

	# self.refresh()

	def __showHideItems(self):
		span = self.markerSpans[self.__spanIndex]
		spanTimedelta = timedelta(hours=span)
		for marker in self.values():
			if marker.value.hour%span == 0:
				marker.show()
				marker.spread = spanTimedelta
			else:
				marker.hide()

	def __getitem__(self, item: datetime):
		item = item.replace(minute=0, second=0, microsecond=0)
		return super(HourLabels, self).__getitem__(item)

	def __missing__(self, key: datetime):
		key = key.replace(minute=0, second=0, microsecond=0)
		self[key] = TimeStampText(parent=self.parent, timestamp=key, formatID=3, spread=timedelta(hours=1))
		return self[key]

	def update(self):
		start = self.graph.timeframe.historicalStart - timedelta(hours=1)
		start = start.replace(minute=0, second=0, microsecond=0)
		end = self.graph.contentsMaxTime + timedelta(hours=1)
		end = end.replace(minute=0, second=0, microsecond=0)
		timespan = end - start
		totalHours = int(timespan.total_seconds()/3600)
		markers = [i for i in self.values()]
		markerKeys = [x for x in self.keys()]
		if len(markerKeys) > totalHours:
			for i in markerKeys[totalHours:]:
				item = self.pop(i)
				if item.scene():
					item.scene().removeItem(item)
		elif len(markers) < totalHours:
			for marker in self.values():
				marker.refresh()
			for i in range(len(markers), totalHours):
				self[start + timedelta(hours=i)]
		for i, marker in enumerate(markers):
			marker.value = start + timedelta(hours=i)


class DayAnnotations(QGraphicsItemGroup):

	def __init__(self, graph: 'GraphPanel', **kwargs):
		self.markEveryNthHour = 0
		self.S = 1
		self.s = 1
		self.graph = graph.parentItem()
		super(DayAnnotations, self).__init__(parent=graph)
		self._dayLabels = kwargs.get('dayLabels', False)
		self._dayLines = kwargs.get('dayLines', False)

		self.hourLabels = HourLabels(self)

		self.graph.signals.resized.connect(self.onFrameChange)
		self.graph.graphZoom.signals.action.connect(self.onTimeScaleChange)
		ClockSignals.sync.connect(self.updateItem)
		self.setFlag(QGraphicsItem.ItemClipsChildrenToShape, True)
		self.setFlag(QGraphicsItem.ItemClipsToShape, True)
		self.hourLabelWidth = 0
		self.singleHourLabelWidth = 0
		# if self._dayLines:
		self.hourLines = TimeMarkers(self)
		self.scene().views()[0].resizeFinshed.connect(self.onFrameChange)

	# self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)

	def onTimeScaleChange(self):
		self.hourLabels.onAxisChange(Axis.X)
		self.hourLines.onAxisChange(Axis.X)

	# self.buildLabels()

	def onFrameChange(self, axis: Axis = Axis.Both):
		self.setTransform(self.graph.proxy.t)
		self.hourLabels.onAxisTransform(axis)
		self.hourLines.onAxisChange(axis)

	# self.a.setRect(self.parentItem().rect())
	# closest = closestCeil([1, 3, 6, 7, 12], 24 / self.singleHourLabelWidth * self.transform().m11())
	# if closest == 7:
	# 	closest = 6
	# if m11 > self.S or m11 < self.s:
	# 	print(self.S, m11, self.s)
	# self.buildLabels()
	# print(self.singleHourLabelWidth)
	# print(self.hourLabelWidth)
	# print(self.graph.pixelsPerHour * 24)

	def shape(self):
		return self.graph.proxy.shape()

	def buildLabels(self):
		return

		start = self.timeStart()
		start = datetime(year=start.year, month=start.month, day=start.day, hour=start.hour, minute=0, second=0, microsecond=0, tzinfo=start.tzinfo)

		# Find all the existing labels
		dayLabels = [marker for marker in self.childItems() if isinstance(marker, DayMarkerText)]
		hourLabels = [marker for marker in self.childItems() if isinstance(marker, TimeStampText) and marker not in dayLabels]

		# If there are no hour labels, create a day's worth for calculations
		if not hourLabels:
			hourLabels = [TimeStampText(self, start + timedelta(hours=i), spread=timedelta(hours=2)) for i in range(0, 12)]

		# hourLabels = [marker for marker in self.childItems() if isinstance(marker, TimeStampText) and marker not in dayLabels]

		t = self.deviceTransform(self.scene().views()[0].viewportTransform())
		width = max(t.mapRect(m.textRect).width() for m in hourLabels)
		print(width)
		self.maxHourLabelWidth = width
		hourLabelsWidthPerDay = (24*self.graph.pixelsPerHour/t.m11())/width
		self.hourLabelsWidthPerDay = hourLabelsWidthPerDay

		self.markEveryNthHour = closestCeil([1, 3, 7, 12], hourLabelsWidthPerDay)
		if self.markEveryNthHour == 7:
			self.markEveryNthHour = 6
		self.S = width*(24 + self.markEveryNthHour*1.2)/hourLabelsWidthPerDay*t.m11()
		self.s = width*(24 - self.markEveryNthHour*1.2)/hourLabelsWidthPerDay*t.m11()
		self.singleHourLabelWidth = hourLabelsWidthPerDay

		hourMarkerSpread = timedelta(hours=int(self.markEveryNthHour))
		dayMarkerSpread = timedelta(hours=24)
		# only mark hours if it is more than every 12
		# self.singleHourLabelWidth = labelsHourWidth * self.graph.pixelsPerHour * self.transform().inverted()[0].m11()
		self.hourLabelWidth = self.singleHourLabelWidth*24/self.markEveryNthHour
		if self.markEveryNthHour == 12:
			start = start.replace(hour=12, minute=0, second=0, microsecond=0)
			while start < self.timeEnd() + timedelta(days=5):
				if hourLabels:
					label = hourLabels.pop(0)
					label.value = start
					label.formatID = 4
					label.setPlainText(label.text())
				else:
					label = TimeStampText(self, start, formatID=4, spread=hourMarkerSpread)
				start += timedelta(days=1)


		else:
			while start < self.timeEnd() + timedelta(hours=1):
				if start.hour%self.markEveryNthHour == 0:
					if hourLabels:
						value = hourLabels.pop(0)
						value.formatID = 3
						value.value = start
						value.setPlainText(value.text())
					else:
						TimeStampText(self, start, formatID=3, spread=hourMarkerSpread)
				if (start.hour + 12)%24 == 0:
					if dayLabels:
						label = dayLabels.pop(0)
						label.value = start
					else:
						label = DayMarkerText(self, start, spread=dayMarkerSpread)
					label.setPlainText(label.text())
				start += timedelta(hours=1)

		for label in hourLabels:
			if label.scene() is None:
				label.deleteLater()
			label.scene().removeItem(label)
		for label in dayLabels:
			if label.scene() is None:
				label.deleteLater()
			label.scene().removeItem(label)

		markers = [marker for marker in self.childItems() if isinstance(marker, TimeStampText) if marker.isDayMarker]

	# if markers:
	# 	if (masW := max(m.boundingRect().width() for m in markers)) > self.graph.pixelsPerHour * 24:
	# 		s = self.graph.pixelsPerHour * 24 / masW
	# 		if s > 0.7 > 1:
	# 			for marker in markers:
	# 				marker.displayScale = s
	# 				marker.updateFontSize()
	# 				marker.setPlainText(marker.text())
	# 		else:
	# 			for marker in markers:
	# 				marker.formatID += 1
	# 				marker.setPlainText(marker.text())
	# 	else:
	# 		print('here')

	# for day in range(6, ceil(self.timeRange().total_seconds() / 3600) + 1, 6):
	# 	if (day + hourOffset + 12) % 24 == 0:
	# 		if dayLabels:
	# 			dmarker = dayLabels.pop(0)
	# 			dmarker.value = start + timedelta(days=day // 24, hours=day % 24)
	# 		else:
	# 			DayMarkerText(self, start + timedelta(days=day // 24, hours=day % 24))
	# 	value = start + timedelta(hours=day)
	# 	if hourLabels:
	# 		marker = hourLabels.pop(0)
	# 		marker.value = value
	# 	else:
	# 		TimeStampText(self, value)
	# dayLabels = [marker for marker in self.childItems() if isinstance(marker, DayMarkerText)]
	#
	#
	# textWidth = max(marker.boundingRect().width() for marker in dayLabels) * 1.1
	# dayWidth = self.graph.pixelsPerHour * 24
	# scalar = dayWidth / textWidth
	# if textWidth < 200:
	# 	formatID = 1
	# else:
	# 	formatID = 0
	# for marker in dayLabels:
	# 	marker.scalar *= scalar
	# 	marker.formatID = formatID
	# 	marker.refresh()

	def timeStart(self):
		figures = [figure.figureMinStart() for figure in self.graph.figures if figure.plots]
		if figures:
			figures.append(self.graph.timeframe.historicalStart)
			return min(figures)
		return self.graph.timeframe.historicalStart

	def displayStart(self):
		return self.graph.timeframe.historicalStart

	def timeEnd(self):
		figures = [figure.figureMaxEnd() for figure in self.graph.figures if figure.plots]
		if figures:
			return max(figures)
		return self.graph.timeframe.max

	def timeRange(self):
		return self.timeEnd() - self.timeStart()

	def rect(self):
		figureRects = [f.mapRectToParent(f.contentsRect()) for f in self.graph.figures]
		if figureRects:
			x = min(f.x() for f in figureRects)
			y = min(f.y() for f in figureRects)
			w = max(f.width() for f in figureRects)
			h = max(f.height() for f in figureRects)
			return QRectF(x, y, w, h)
		return self.graph.rect()

	def boundingRect(self):
		return self.parentItem().boundingRect()

	def updateChildren(self):
		for child in self.childItems():
			child.update()

	def updatePosition(self):
		rect = self._rect
		pos = rect.topLeft()
		self.setPos(pos)

	def updateItem(self):
		self.setTransform(self.graph.proxy.t)
		# self.buildLabels()
		self.hourLabels.refresh()
		rect = self.rect()
		pos = rect.topLeft()
		self.setPos(pos)
		rect.moveTo(0, 0)
		self.updateChildren()

	@property
	def state(self):
		return {
			'dayLabels': self._dayLabels,
			'dayLines':  self._dayLines
		}


# Section AxisSignal


class AxisSignal(QObject):
	__signal = Signal(Axis)
	log = log.getChild('AxisSignal')

	def __init__(self, parent: _Panel):
		super(AxisSignal, self).__init__()
		self.__axis = Axis.Neither
		self.parent = parent
		self.timer = QTimer(singleShot=True, interval=200)
		self.timer.timeout.connect(self.__announce)

	def announce(self, axis: Axis, instant: bool = False):
		self.__axis |= axis
		if instant:
			self.__announce()
		else:
			self.timer.start()

	def __announce(self):
		self.__signal.emit(self.__axis)
		self.__axis = Axis.Neither

	def connectSlot(self, slot: Callable):
		# self.log.debug(f'Connecting slot {slot.__func__.__name__} to AxisSignal for {self.parent}')
		self.__signal.connect(slot)

	def disconnectSlot(self, slot: Callable):
		disconnectSignal(self.__signal, slot)


AxisSignal.log.setLevel(logging.DEBUG)


class GraphPanel(Panel):
	isEmpty = False
	figures: List['Figure']
	timeframe: TimeFrameWindow
	_acceptsChildren: bool = False
	graphZoom: GraphZoom
	log = guiLog.getChild('Graph')
	savable = True

	# Section GraphPanel
	def __init__(self, *args, **kwargs):
		self.__timescalar = 1
		t = kwargs.get('timeframe', TimeFrameWindow(timedelta(days=3)))
		if isinstance(t, dict):
			t = TimeFrameWindow(**t)
		self.timeframe = t
		if 'geometry' not in kwargs:
			kwargs['geometry'] = {'size': {'width': 800, 'height': 400, 'absolute': True}, 'absolute': True}
		super(GraphPanel, self).__init__(*args, **kwargs)
		self.worldTransform = self.scene().views()[0].transform
		self.isEmpty = False
		self.axisTransformed = AxisSignal(self)
		self.figures = []

		self.setAcceptDrops(True)
		self.clipping = True
		self.graphZoom = GraphZoom(self, self.timeframe)
		self.setAcceptHoverEvents(True)

		self.proxy = GraphProxy(graph=self)
		self.proxy.annotations = DayAnnotations(self.proxy, **kwargs.get('annotations', {}))
		figures = kwargs.get('figures', None)
		if isinstance(figures, dict):
			figures = list(figures.values())
		for figure in reversed(figures or []):
			figure.pop('class', None)
			Figure(self, **figure)
		self.syncTimer = QTimer(timeout=self.syncDisplay, interval=self.msPerPixel)
		self.updateSyncTimer()
		self.syncDisplay()
		self.timeframe.connectItem(self.updateSyncTimer)
		self.signals.resized.connect(self.updateSyncTimer)
		self.axisTransformed.connectSlot(self.onAxisChange)

		self.setFlag(self.ItemClipsChildrenToShape, False)

		# self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)

		self.movable = False

	@Slot(Axis)
	def onAxisChange(self, axis: Axis):
		if axis & Axis.X:
			clearCacheAttr(self, 'timescalar', 'contentsTimespan', 'contentsMaxTime', 'contentsMinTime')
		self.proxy.annotations.onFrameChange(axis)
		self.updateSyncTimer()

	def parentResized(self, *args):
		super(GraphPanel, self).parentResized(*args)
		self.axisTransformed.announce(Axis.X)

	def setRect(self, rect: QRectF):
		super(GraphPanel, self).setRect(rect)
		clearCacheAttr(self, 'timescalar', 'contentsTimespan', 'contentsMaxTime', 'contentsMinTime')

	def updateSyncTimer(self):
		self.syncTimer.stop()
		self.syncTimer.setInterval(self.msPerPixel)
		self.log.setLevel(logging.DEBUG)
		updateFrequency = Millisecond(self.msPerPixel).minute
		self.log.debug(f"Will now update every {updateFrequency} {type(updateFrequency).__name__.lower()}s")
		self.log.setLevel(logging.INFO)
		self.syncTimer.start()

	def syncDisplay(self):
		self.proxy.snapToTime(self.timeframe.displayPosition)

	def timeToX(self, time: datetime):
		pass

	def refresh(self):
		for figure in self.figures:
			figure.update()
		self.graphZoom.update()

	@property
	def msPerPixel(self) -> int:
		'''
		Returns the number of milliseconds per pixel.  Useful for deciding how often to update
		the display.
		:return: How many milliseconds span each pixel
		:rtype: int
		'''
		return round(self.timeframe.seconds/self.width()*1000)

	@property
	def pixelsPerSecond(self) -> float:
		'''
		Returns the number of pixels per second.  Useful for determining the width of a bar.
		:return: How many pixels span each second
		:rtype: float
		'''
		return self.width()/self.timeframe.seconds

	@property
	def pixelsPerHour(self):
		return self.width()/self.timeframe.hours

	@property
	def pixelsPerDay(self):
		return self.width()/self.timeframe.days

	@property
	def secondsPerPixel(self):
		return self.timeframe.seconds/self.width()

	@property
	def minutesPerPixel(self):
		return self.timeframe.minutes/self.width()

	@property
	def hoursPerPixel(self):
		return self.timeframe.hours/self.width()

	@property
	def daysPerPixel(self):
		return self.timeframe.days/self.width()

	def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent):
		self.graphZoom.setVisible(True)
		event.ignore()
		super(GraphPanel, self).hoverEnterEvent(event)

	def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent):
		self.graphZoom.setVisible(False)
		event.ignore()
		super(GraphPanel, self).hoverLeaveEvent(event)

	def wheelEvent(self, event: QGraphicsSceneWheelEvent):
		if self.hasFocus():
			event.accept()
			if event.delta() > 1:
				self.timeframe.decrease(self.timeframeIncrement)
			else:
				self.timeframe.increase(self.timeframeIncrement)
			self.signals.resized.emit(self.rect())
		else:
			event.ignore()

	# def mousePressEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
	# 	self.setFocus()
	# 	self.scene().clearSelection()
	# 	self.setSelected(True)
	# 	super(GraphPanel, self).mousePressEvent(mouseEvent)

	# def mouseMoveEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
	# 	mouseEvent.accept()
	# 	if mouseEvent.buttons() == Qt.LeftButton | Qt.RightButton:
	# 		super(GraphPanel, self).mouseMoveEvent(mouseEvent)
	# 	else:
	# 		self.proxy.mouseMoveEvent(mouseEvent)

	@property
	def name(self) -> str:
		return f'{self.__class__.__name__}-0x{self.uuidShort}'

	@property
	def timeframeIncrement(self):
		days = self.timeframe.rangeSeconds/60/60/24
		if days < 1:
			return timedelta(hours=3)
		elif days < 2:
			return timedelta(hours=6)
		elif days < 5:
			return timedelta(hours=12)
		elif days < 10:
			return timedelta(days=1)
		hour = self.timeframe.rangeSeconds / 60 / 60
		if hour < 24:
			return timedelta(days=1)
		elif hour < 18:
			return timedelta(hours=1)
		elif hour < 12:
			return timedelta(minutes=30)
		elif hour < 6:
			return timedelta(minutes=15)
		else:
			return timedelta(minutes=5)

	def dragEnterEvent(self, event: QGraphicsSceneDragDropEvent):
		if event.mimeData().hasFormat('application/panel-valueLink'):
			event.acceptProposedAction()
			return
		event.ignore()
		super().dragEnterEvent(event)

	def dropEvent(self, event: QGraphicsSceneDragDropEvent):
		data = loads(event.mimeData().data('application/panel-valueLink').data(), object_hook=hook)
		if 'valueLink' not in data:
			event.ignore()
			return
		value = data['valueLink']
		figures = [figure for figure in self.figures if figure.sharedKey > value.key.category]
		if len(figures) == 1:
			figure = figures[0]
			figure.addItem(value)
		elif len(figures) > 1:
			raise Exception('Too many figures')
		else:
			if value.hourly:
				a = Figure(self)
				a.addItem(value)
				a.show()
			else:
				event.ignore()

	@property
	def fontSize(self):
		return min(max(self.rect().height() * 0.1, 30, min(self.rect().width() * 0.06, self.rect().height() * .2)), 100)

	def plotLineWeight(self) -> float:
		weight = self.rect().height() * golden * 0.005
		weight = weight if weight > 8 else 8.0
		return weight

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemTransformHasChanged:
			self.signals.transformChanged.emit(value)
		if change == QGraphicsItem.ItemChildAddedChange:
			if isinstance(value, (Incrementer, IncrementerGroup)):
				value.setZValue(10000)
		# elif isinstance(value, FigureRect):
		# 	self.signals.resized.connect(value.redraw)
		# elif change == QGraphicsItem.ItemChildRemovedChange:
		# 	if isinstance(value, FigureRect):
		# 		disconnectSignal(self.signals.resized, value.redraw)
		return super(GraphPanel, self).itemChange(change, value)

	@classmethod
	def validate(cls, item: dict) -> bool:
		panelValidation = super(GraphPanel, cls).validate(item)
		timeframe = TimeFrameWindow.validate(item.get('timeframe', {}))
		return panelValidation and timeframe

	@property
	def state(self):
		state = super(GraphPanel, self).state
		state.pop('childItems', None)
		state.pop('movable', None)
		state.update({
			'timeframe': self.timeframe.state,
			'figures':   self.figures,
		})
		# annotationState = self.proxy.annotations.state
		# if annotationState:
		# 	state['annotations'] = annotationState
		state['type'] = 'graph'
		return state

	@cached_property
	def contentsTimespan(self) -> timedelta:
		if self.figures and any(figure.plots for figure in self.figures):
			return max(figure.figureTimeRangeMax for figure in self.figures)
		return self.timeframe.range

	@cached_property
	def contentsMaxTime(self) -> datetime:
		if self.figures and any(figure.plots for figure in self.figures):
			return max(figure.figureMaxEnd() for figure in self.figures)
		return self.timeframe.end

	@cached_property
	def contentsMinTime(self) -> datetime:
		if self.figures and any(figure.plots for figure in self.figures):
			return min(figure.figureTimeRangeMin for figure in self.figures)
		return self.timeframe.start

	@cached_property
	def timescalar(self) -> float:
		if self.figures and any(figure.plots for figure in self.figures):
			value = self.contentsTimespan/self.timeframe.range
		else:
			value = 1
		return value

	@property
	def dataWidth(self) -> float:
		return self.width()*self.timescalar


class CurrentTimeIndicator(QGraphicsLineItem):

	def __init__(self, display: 'GraphProxy', *args, **kwargs):
		self.display = display
		baseClock.sync.connect(self.updateItem)
		super(CurrentTimeIndicator, self).__init__(*args, **kwargs)

	def updateItem(self):
		now = datetime.now(tz=config.tz)
		x = self.display.timeToX(now)
		self.setLine(0, 0, 0, self.parentItem().rect().height())


class GraphProxy(QGraphicsItemGroup):
	signals: GraphicsItemSignals = GraphicsItemSignals()

	log = log.getChild('graphProxy')

	# Section GraphProxy
	def __init__(self, graph):
		super(GraphProxy, self).__init__(graph)
		self.graph = graph
		self._previous = graph.rect()

		properties = {k: v for k, v in self.graph.__class__.__dict__.items() if isinstance(v, property)}
		for p in properties.values():
			if p.fset:
				p.fset(self, p.fget(self.graph))
			else:
				setattr(self, p.fget.__name__, p.fget(self.graph))
		self.geometry = self.graph.geometry
		self.setFlag(QGraphicsItem.ItemIsMovable, True)
		self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
		self.setFlag(QGraphicsItem.ItemIsFocusable, False)
		self.setAcceptHoverEvents(True)

		self.graph.timeframe.connectItem(self.onTimeFrameChange)
		self.graph.signals.resized.connect(self.onFrameChange)
		self.setHandlesChildEvents(False)
		self.setFlag(QGraphicsItem.ItemClipsChildrenToShape, True)
		self.setFlag(QGraphicsItem.ItemClipsToShape, True)
		t = QTransform()
		t.scale(1, -1)

	@Slot(Axis)
	def onTimeFrameChange(self, axis):
		self.updateTransform()

	@Slot(Axis)
	def onDataRangeChange(self, axis: Axis):
		if axis & Axis.X:
			clearCacheAttr(self.graph, 'timescalar')

	@Slot(Axis)
	def onFrameChange(self, axis):
		self.updateTransform()

	def updateTransform(self):
		scale = [1, 1]
		if self._previous:
			previous = self._previous.size()
			current = self.graph.rect().size()
			if previous != current:
				scale[0] = current.width()/previous.width()
				scale[1] = current.height()/previous.height()
				self._previous = self.graph.rect()
		self.t.scale(*scale)

	def mousePressEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		self.parentItem().setSelected(True)

		if mouseEvent.buttons() == Qt.LeftButton | Qt.RightButton or mouseEvent.modifiers() == Qt.KeyboardModifier.ControlModifier:
			mouseEvent.ignore()
		else:
			self.scene().clearSelection()
			self.setSelected(True)
			mouseEvent.accept()
		super(GraphProxy, self).mousePressEvent(mouseEvent)

	def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		if event.buttons() == Qt.LeftButton | Qt.RightButton or event.modifiers() == Qt.KeyboardModifier.ControlModifier:
			event.ignore()
		else:
			event.accept()
			SoftShadow.disable()
		# self.scene().clearFocus()
		super(GraphProxy, self).mouseMoveEvent(event)

	def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		event.accept()
		self.graph.timeframe.displayPosition = timedelta(seconds=self.graph.pixelsPerSecond*-self.pos().x())
		if self.graph.graphZoom.isAncestorOf(inc := self.scene().itemAt(event.scenePos(), self.transform())):
			inc.mouseReleaseEvent(event)
		else:
			super(GraphProxy, self).mouseReleaseEvent(event)
		SoftShadow.enable()

	def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
		event.accept()
		super(GraphProxy, self).hoverEnterEvent(event)

	def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
		event.accept()
		QToolTip.hideText()
		super(GraphProxy, self).hoverLeaveEvent(event)

	def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
		if any(figure.marginRect.contains(event.pos()) for figure in self.graph.figures):
			event.accept()

			x = event.pos().x()
			x = self.graph.timeframe.min + timedelta(milliseconds=(x*self.graph.msPerPixel))
			differance = x - datetime.now(tz=config.tz)
			time = Second(differance.total_seconds()).hour
			values = []
			for figure in (i for i in self.graph.figures if i.plots):
				if not figure.marginRect.contains(event.pos()):
					continue
				y = event.pos().y() - figure.marginRect.top()
				minVal = figure.dataValueRange.min
				maxVal = figure.dataValueRange.max
				y = maxVal - (maxVal - minVal)*(y/figure.marginRect.height())
				values.append((figure, figure.plots[0].dataType(y)))
			if len(values):
				values.sort(key=lambda x: len(x[0].plots), reverse=True)
				value = f'{time} | {" | ".join(f"{i[0].sharedKey.key}: {i[1]}" for i in values)}'
				QToolTip.showText(event.screenPos(), value)
		else:
			QToolTip.hideText()

	def snapToTime(self, time: datetime):
		# earliest = min(figure.figureMinStart() for figure in self.graph.figures)
		timeOffset = self.graph.timeframe.start - time
		xOffset = timeOffset.total_seconds()*self.graph.pixelsPerSecond
		self.setPos(xOffset, 0)

	@cached_property
	def t(self) -> QTransform:
		return QTransform()

	@cached_property
	def _previous(self) -> QRectF:
		return self.graph.rect()

	def rect(self):
		rect = self.graph.rect()
		rect.setWidth(self.graph.dataWidth)
		# rect.setX(-self.graph.timeframe.offset.total_seconds() * self.graph.pixelsPerSecond)
		return rect

	def boundingRect(self):
		rect = self.graph.rect()
		rect = self.mapRectFromParent(rect)
		# rect.setX(self.graph.timeframe.combinedOffset.total_seconds() * self.graph.pixelsPerSecond)
		return rect

	def shape(self):
		shape = self.graph.shape()
		shape = self.mapFromParent(shape)
		return shape

	def height(self):
		return self.graph.height()

	def width(self):
		return self.graph.width()

	def visibleRect(self):
		rect = self.graph.rect()
		rect = self.mapRectFromParent(rect)
		return rect

	# def pos(self):
	# 	return self.pos()

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemPositionChange:
			value = self.clampPoint(value)
		return super(GraphProxy, self).itemChange(change, value)

	@property
	def currentTimeFrame(self):
		visibleRect = self.mapRectFromParent(self.rect().intersected(self.parentItem().rect()))
		visibleTimeStart = self.graph.timeframe.start + timedelta(hours=visibleRect.x()/self.graph.pixelsPerHour)
		visibleTimeEnd = self.graph.timeframe.start + timedelta(hours=visibleRect.x()/self.graph.pixelsPerHour + visibleRect.width()/self.graph.pixelsPerHour)
		hoursFromStart = int((visibleTimeStart - self.graph.timeframe.start).total_seconds()/3600)
		hoursFromEnd = int((visibleTimeEnd - self.graph.timeframe.start).total_seconds()/3600) + 1

		return

	def contentsWidth(self):
		return self.graph.dataWidth

	def contentsX(self):
		return 0

	def clampPoint(self, value):
		maxX = -self.graph.timeframe.negativeOffset.total_seconds()*self.graph.pixelsPerSecond
		maxY = self.graph.rect().bottom() - self.rect().height()
		minX = self.graph.rect().right() - self.contentsWidth() - maxX
		x = clamp(value.x(), minX, maxX)
		y = clamp(value.y(), 0, maxY)
		# if x != value.x():
		# 	elasticValue = self.elasticCap(value.x(), minX, maxX)
		# rubberband scroll while dragging
		# if self.scene().clicked and value.x() != x:
		# 	self.elasticTransform(x, value.x())
		value.setX(x)
		value.setY(y)
		return value

	def xForTime(self, time: datetime) -> float:
		x = (time - self.graph.timeframe.start).total_seconds()/3600
		return x*self.graph.pixelsPerHour

	def paint(self, painter, option, widget):
		top = self.graph.rect().top()
		bottom = self.graph.rect().bottom()
		painter.setPen(QPen(QColor('#ff9aa3'), 1))
		x = self.xForTime(datetime.now(tz=config.tz))
		painter.drawLine(x, top, x, bottom)
		# painter.setPen(QPen(Qt.cyan, 1))
		# painter.drawRect(self.rect().adjusted(3, 3, -3, -3))
		super(GraphProxy, self).paint(painter, option, widget)


# Section Figure


class Figure(Panel):
	_default: str = None
	_margins: Margins
	dataValueRange: Optional[AxisMetaData] = None
	plotData: dict[str, GraphItemData]
	isEmpty: bool = False
	_acceptsChildren: bool = False
	axisTransformed: AxisSignal

	def __init__(self, parent: GraphPanel, margins: Margins = None, data: list[dict] = None, *args, **kwargs):
		self.plotData = {}
		self._transform = None

		if margins is None:
			margins = {'left': 0, 'top': 0.1, 'right': 0, 'bottom': 0.1}

		if 'geometry' not in kwargs:
			kwargs['geometry'] = {'size': {'width': 1.0, 'height': 1.0}, 'position': {'x': 0, 'y': 0}, 'absolute': False}
		self.syncTimer = QTimer(singleShot=False, interval=5000)
		self.axisTransformed = AxisSignal(self)
		super(Figure, self).__init__(parent, margins=margins, **kwargs)

		self.setFlag(QGraphicsItem.ItemIsMovable, False)
		# self.setFlag(QGraphicsItem.ItemHasNoContents, True)
		# self.setFlag(QGraphicsItem.ItemIsFocusable, False)
		# self.setFlag(QGraphicsItem.ItemClipsChildrenToShape, False)
		self.setFlag(QGraphicsItem.ItemClipsChildrenToShape, True)
		# self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
		self.resizeHandles.setParentItem(None)
		self.marginHandles = FigureHandles(self)
		self.setAcceptedMouseButtons(Qt.NoButton)
		# ClockSignals.sync.connect(self.redraw)

		# self.timer = QTimer(singleShot=False, interval=5000, timeout=self.redraw)
		# self.timer.start()

		self.marginHandles.hide()
		self.marginHandles.setZValue(1000)
		self.geometry.setRelativeSize(1.0)
		# self.setFlag(self.ItemIsSelectable, False)
		self.graph.proxy.addToGroup(self)
		self.graph.signals.resized.connect(self.parentResized)
		self.graph.timeframe.changed.connect(self.onAxisResized)
		self.marginHandles.signals.action.connect(self.onAxisResized)
		self.axisTransformed.connectSlot(self.onAxisTransform)
		self.axisTransformed.connectSlot(self.graph.onAxisChange)
		data = [*(data or []), *[{'key': k, **v} for k, v in kwargs.items() if 'plot' in v]]
		if data:
			self.loadLinePlotData(data)
		self.setAcceptHoverEvents(False)

	# self.log = log.getChild(self.key.name)

	# Section Figure Events

	@Slot(Axis)
	def onGraphItemUpdate(self, axis: Axis):
		"""Called by a child GraphItem when its value has changed so that it can notify the other children to update"""
		self.axisTransformed.announce(axis)
		self.setRect(self.rect())
		clearCacheAttr(self, 'marginRect')

	@Slot(Axis)
	def onAxisTransform(self, axis: Axis):
		# Inform the graph that the axis has changed so that it can invalidate the timescalars
		# eventually, further action should wait for the graph to announce the change
		self.graph.axisTransformed.announce(axis)

	# self.axisTransformed.announce(axis, instant=True

	@Slot(Axis)
	def onAxisResized(self, axis: Axis):
		self._transform = None
		self.axisTransformed.announce(axis, instant=True)

	@property
	def parent(self) -> Union['Panel', 'GridScene']:
		if isinstance(self.parentItem(), QGraphicsItemGroup):
			return self.parentItem().parentItem()
		return self.parentItem()

	@property
	def t(self) -> QTransform:
		if self._transform is None:
			transform = QTransform()
			transform.translate(0, self.graph.height())
			transform.scale(1, -1)
			graphTimeRange = self.graph.timeframe.rangeSeconds
			xScale = (self.figureTimeRangeMax.total_seconds()/graphTimeRange)*self.graph.width()
			# xScale = self.graph.width()
			yScale = self.graph.height()
			transform.scale(xScale, yScale)
			marginTransform = self.margins.asTransform()
			self._transform = transform*marginTransform*self.graph.transform()
		return self._transform

	def refresh(self):
		for plot in self.plotData.values():
			plot.update()

	def mousePressEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		mouseEvent.ignore()
		super(QGraphicsRectItem, self).mousePressEvent(mouseEvent)

	def mouseMoveEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		mouseEvent.ignore()
		super(QGraphicsRectItem, self).mouseMoveEvent(mouseEvent)

	def mouseReleaseEvent(self, mouseEvent):
		mouseEvent.ignore()
		super(QGraphicsRectItem, self).mouseReleaseEvent(mouseEvent)

	@property
	def graph(self) -> GraphPanel:
		return self.parent

	def loadLinePlotData(self, plotData: dict[str, GraphItemData]):
		if isinstance(plotData, dict):
			plotData = list(plotData.values())
		for data in plotData:
			self.addItem(**data)

	@property
	def plots(self):
		return list(i for i in self.plotData.values() if i.hasData)

	@property
	def sharedKey(self) -> CategoryItem:
		keys = list(self.plotData.keys())
		i = keys.pop()
		for key in keys:
			i = i & key
		return i

	def focusInEvent(self, event: QFocusEvent) -> None:
		self.marginHandles.show()
		super().focusInEvent(event)
		self.parent.graphZoom.setVisible(True)
		self.marginHandles.updatePosition(self.graph.rect())

	def focusOutEvent(self, event: QFocusEvent) -> None:
		super().focusOutEvent(event)
		if not self.parent.childHasFocus():
			self.parent.graphZoom.setVisible(False)
		self.marginHandles.hide()

	def debugBreak(self):
		a = list(self.plotData.values())[0]

	def setParentItem(self, parent: GraphPanel):
		if self.parentItem() is parent:
			return

		if isinstance(parent, GraphPanel):
			parent.figures.append(self)
		elif self.parentItem() is not None:
			i = self.parentItem().figures.index(self)
			self.parentItem().figures.pop(i)
		super(Figure, self).setParentItem(parent)

	def dragEnterEvent(self, event: QGraphicsSceneDragDropEvent):
		if event.mimeData().hasFormat('application/graph-feature'):
			event.accept()
		else:
			event.ignore()
		super(Figure, self).dragEnterEvent(event)

	def figureMaxStart(self) -> datetime:
		plotsWithData = [item for item in self.plotData.values() if item.rawData is not None]
		if not plotsWithData:
			return max([item.timeframe.min for item in plotsWithData])
		return self.graph.timeframe.start

	def figureMinStart(self) -> datetime:
		plotsWithData = [item for item in self.plotData.values() if item.rawData is not None]
		if plotsWithData:
			return min([item.timeframe.min for item in plotsWithData])
		return self.graph.timeframe.start

	def figureEnd(self) -> datetime:
		plotsWithData = [item for item in self.plotData.values() if item.rawData is not None]
		if plotsWithData:
			return sum([item.timeframe.max for item in plotsWithData])/len(self.plotData)
		return self.graph.timeframe.end

	def figureMaxEnd(self) -> datetime:
		plotsWithData = [item for item in self.plotData.values() if item.rawData is not None]
		if plotsWithData:
			return max([item.timeframe.max for item in plotsWithData])
		return self.graph.timeframe.end

	def figureMinEnd(self) -> datetime:
		plotsWithData = [item for item in self.plotData.values() if item.rawData is not None]
		if plotsWithData:
			return min([item.timeframe.max for item in plotsWithData])
		return self.graph.timeframe.end

	@property
	def figureTimeRangeMin(self) -> timedelta:
		return self.figureMaxStart() - self.figureMinStart()

	@property
	def figureTimeRangeMax(self) -> timedelta:
		return self.figureMaxEnd() - self.figureMinStart()

	@property
	def contentsWidth(self) -> float:
		if self.plotData:
			r = max(self.parent.timeframe.rangeSeconds, 60)
			return self.figureTimeRangeMax.total_seconds() / r * self.frameRect.width()
		return self.frameRect.width()

	@property
	def contentsX(self) -> float:
		return self.graph.timeframe.negativeOffset.total_seconds()/3600*self.graph.pixelsPerHour
		# if self.plotData and any(i.value for i in self.plotData.values()):
		# 	return min(i.plotValues[0].x() for i in self.plots if i.value) * self.graph.timescalar * 10
		return 0

	def setRect(self, rect: QRectF):
		rect.setWidth(self.contentsWidth)
		rect.setX(self.contentsX)
		QGraphicsRectItem.setRect(self, rect)
		self._transform = None
		self.axisTransformed.announce(Axis.Both)

	def contentsRect(self) -> QRectF:
		rect = super(Figure, self).contentsRect()
		rect.setWidth(self.contentsWidth)
		rect.setX(self.contentsX)
		return rect

	def boundingRect(self) -> QRectF:
		return self.graph.proxy.boundingRect()

	def visibleRect(self) -> QRectF:
		return self.parentItem().visibleRect()

	@property
	def marginPosition(self) -> QPointF:
		frame = self.frameRect
		return self.frameRect.topLeft()

	@property
	def frameRect(self):
		rect = self.parent.rect()
		return rect

	def width(self):
		return self.parent.width()

	def height(self):
		return self.parent.height()

	@cached_property
	def dataValueRange(self) -> AxisMetaData:
		return AxisMetaData(self)

	@property
	def name(self):
		a = set([item.type for item in self.plotData.values()])
		if len(a) > 1:
			return '/'.join(a)
		else:
			return list(a)[0]

	# def genLabels(self):
	# 	list(self.plotData._values())[0].genLabels()

	def addItem(self, key: CategoryItem, labeled: bool = None, zOrder: Optional[int] = None, graphic: dict = {}, *args, **kwargs):

		cls = kwargs.pop('class', GraphItemData)
		if len(self.plotData) == 0 and labeled is None:
			labeled = True
		elif labeled is None:
			labeled = False

		item = cls(parent=self, key=key, labeled=labeled, graphic=graphic, *args, **kwargs)

		if zOrder is not None:
			item.allGraphics.setZValue(zOrder)
		# for plot in self.plots:
		# 	if plot is item:
		# 		continue
		# 	plot.updateEverything(None)
		return item

	def removeItem(self, item: GraphItemData):
		self.plotData.pop(item.key)
		self.scene.removeItem(item.allGraphics)
		del item

	def update(self):
		super(Figure, self).update()

	def ensureFramed(self):
		self.setPos(self.clampPoint(self.pos()))

	def itemChange(self, change, value):
		# if change == QGraphicsItem.ItemPositionChange:
		# 	self.clampPoint(value)
		# 	return super(QGraphicsRectItem, self).itemChange(change, value)

		# if change == QGraphicsItem.ItemParentChange:
		# if isinstance(value, QGraphicsItemGroup):
		# 	self._parent = value.parentItem()
		# 	return super(QGraphicsRectItem, self).itemChange(change, value)

		# elif change == QGraphicsItem.ItemChildRemovedChange:
		# 	if isinstance(value, LinePlot):
		# 		disconnectSignal(self.signals.resized, value.update)
		# 		disconnectSignal(value.data.updateSlot, self.parent.incrementers.action.action)
		# 		disconnectSignal(self.marginHandles.action.action, value.update)
		# 	elif isinstance(value, Text):
		# 		disconnectSignal(value.updateItem, self.parent.incrementers.action.action)
		# 		disconnectSignal(self.signals.resized, value.updateItem)

		return super(Figure, self).itemChange(change, value)

	def clampPoint(self, value):
		maxX = -self.contentsX
		maxY = self.graph.rect().bottom() - self.rect().height()
		minX = self.graph.rect().right() - self.contentsWidth - self.contentsX
		x = clamp(value.x(), minX, maxX)
		y = clamp(value.y(), 0, maxY)
		# if x != value.x():
		# 	elasticValue = self.elasticCap(value.x(), minX, maxX)
		# rubberband scroll while dragging
		# if self.scene().clicked and value.x() != x:
		# 	self.elasticTransform(x, value.x())
		value.setX(x)
		value.setY(y)
		return value

	def elasticCap(self, m, M, v):
		def elastic(x, xLimit):
			return xLimit - (xLimit * np.ma.log(xLimit / x))

		# return xLimit * np.ma.log(xLimit / x)
		if v > M:
			m = int(M)
			M = elastic(v, M)
			print(m, round(M, 4), round(v, 4))
		elif v < m:
			m = elastic(v, m)
		return min(max(m, v), M)

		return x

	@property
	def state(self):
		return {
			**{str(k): v for k, v in self.plotData.items()},
			'margins': self.margins,
		}

	def shape(self):
		return self.graph.proxy.shape()
