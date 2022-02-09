import ctypes

from math import ceil

from logger import debug
from src import logging
from itertools import chain, zip_longest

from cmath import sin
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import cached_property
from typing import Any, Iterable, List, Optional, overload, Tuple, Union

import numpy as np
from json import loads
from PIL import Image
from PIL.ImageQt import ImageQt
from PySide2.QtCore import QLineF, QObject, QPoint, QPointF, QRectF, QSizeF, Qt, QTimer, Signal, Slot
from PySide2.QtGui import QBrush, QColor, QFocusEvent, QFont, QLinearGradient, QPainter, QPainterPath, QPainterPathStroker, QPen, QPixmap, QPolygonF, QTextBlockFormat, QTransform
from PySide2.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QFrame, QGraphicsDropShadowEffect, QGraphicsItem, QGraphicsItemGroup, QGraphicsLineItem, QGraphicsPathItem,
                               QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsSceneDragDropEvent, QGraphicsSceneHoverEvent, QGraphicsSceneMouseEvent, QGraphicsSceneWheelEvent, QGraphicsTextItem, QGridLayout, QLabel, QLineEdit, QSpinBox,
                               QToolButton,
                               QVBoxLayout, QWidget)
from scipy.constants import golden
from scipy.interpolate import interp1d, interp2d
from shiboken2 import getCppPointer
from WeatherUnits import Measurement, Temperature

from src.Modules.Handles.Incrementer import Incrementer, IncrementerGroup
from src.Modules.Handles.Timeframe import GraphZoom
from src.catagories import CategoryItem, ValueWrapper
from src.Modules import hook
from src.merger import MergedValue
from src.Modules.Handles.Figure import FigureHandles
from src.Modules.Panel import Panel
from src import colorPalette, config, selectionPen
from src.api import API
from src.colors import Default, kelvinToQColor, rgbHex
from src.fonts import rounded
from src.utils import Alignment, AlignmentFlag, autoDType, Axis, capValue, clearCacheAttr, dataTimeRange, disconnectSignal, DisplayType, findPeaksAndTroughs, normalize, replaceSignal, smoothData
from src.utils import ArrayMetaData, Margins, TimeFrame, TimeLineCollection

log = logging.getLogger(__name__)

__all__ = ['GraphItemData', 'FigureRect', 'GraphPanel']


class GradientPoints(list):

	def __init__(self, *args):
		super(GradientPoints, self).__init__(*args)


class ComfortZones(GradientPoints):
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

	def __init__(self, figure: 'Figure', values: GradientPoints):
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
		return list(self.figure.plotData.values())[0].dataType

	@property
	def gradientPoints(self) -> Tuple[QPoint, QPoint]:
		unit = list(self.figure.plotData.values())[0].dataType(0)
		x = np.array([self.temperatures.min[unit.unit], self.temperatures.max[unit.unit]])
		x = normalize(x, self.figure.dataRange)
		m = self.figure.margins.verticalSpan * self.figure.height()
		top = QPoint(0, x[1] * m)
		bottom = QPoint(0, x[0] * m)
		return top, bottom

	def update(self):
		start, stop = self.gradientPoints
		self.setStart(start)
		self.setFinalStop(stop)

	@property
	def state(self):
		return {}


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


hover = HoverHighlight()


class GraphItemData(QObject):
	_rasterValues: Optional[np.array] = None
	_troughs: Optional[List[int]] = None
	_peaks: Optional[List[int]] = None
	_multiplier: Optional[timedelta] = timedelta(minutes=15)
	_window: Optional[int] = None
	_order: Optional[int] = None
	_array: Optional[np.array] = None
	_interpolated: Optional[np.array] = None
	_smoothed: Optional[np.array] = None
	_smooth: bool
	_length: Optional[int] = None
	_figure: 'Figure' = None
	_numerical: Optional[bool] = None
	_interpolate: bool
	_pathType: 'PathType'
	_allGraphics: QGraphicsItemGroup = None
	_graphic: Optional[QGraphicsItem] = None
	_timeframe: Optional[dataTimeRange] = None
	__normalX = None
	__normalY = None
	__mappedX = None
	__mappedY = None
	_raw: list
	_value: MergedValue
	_labelData: 'PeakTroughList'
	_labels: list['PeakTroughLabel']
	valuesChanged = Signal()
	normalsChanged = Signal(Axis)
	mappedChanged = Signal(Axis)

	def __init__(self,
	             value: MergedValue,
	             parent: 'Figure' = None,
	             interpolate: bool = True,
	             labeled: bool = False,
	             smooth: bool = True,
	             spread: int = 31,
	             order: int = 3,
	             plot: dict = {}, **kwargs):
		super(GraphItemData, self).__init__()
		self.offset = 0
		self.value = value
		self._raw = []
		self._labelData = None
		self._path = None
		self.figure = parent
		self._interpolate = interpolate
		self._smooth = smooth
		self._spread = spread
		self._order = order
		self._timeframe = dataTimeRange(self)
		self.graphic = self.buildGraphic(**plot)
		self.labeled = labeled
		self.figure.parent.graphZoom.signals.action.connect(self.renormalizeValues)
		self.figure.marginHandles.signals.action.connect(self.remapValues)
		self.figure.signals.resized.connect(self.remapValues)
		self._value.hourly.signals.updated.connect(self.updateEverything)
		self.rollTimer = QTimer()
		self.rollTimer.setInterval(3000)

	# self.rollTimer.timeout.connect(self.roll)
	# self.rollTimer.start()

	def buildGraphic(self, **kwargs):
		type = kwargs.pop('type', DisplayType.Plot)
		if type == DisplayType.Plot:
			return Plot(self, **kwargs)

	def __repr__(self):
		mY = min(self._value.hourly.values())
		MY = max(self._value.hourly.values())
		mX = list(self._value.hourly.keys())[0]
		MX = list(self._value.hourly.keys())[-1]

		return f'{self.__class__.__name__}(key: {self.key}, x: {mX} - {MX}, y: {mY} - {MY})'

	def roll(self):
		self.value.hourly.roll()

	def updateEverything(self, source):
		print('update everything')
		self.__clearCache()
		self.renormalizeValues(Axis.Both)

	@Slot(Axis)
	def remapValues(self, axis: Axis = Axis.Both):
		if axis & Axis.X:
			self.__mappedX = None
		if axis & Axis.Y:
			self.__mappedY = None
		self.mappedChanged.emit(axis)

	@Slot(QRectF, Axis)
	def remapValues(self, rect: QRectF, axis: Axis = Axis.Both):
		if axis & Axis.X:
			self.__mappedX = None
		if axis & Axis.Y:
			self.__mappedY = None
		self.mappedChanged.emit(axis)

	@Slot(Axis)
	def renormalizeValues(self, axis: Axis = Axis.Both):
		if axis & Axis.X:
			self.__normalX = None
			self.__mappedX = None
		if axis & Axis.Y:
			self.__normalY = None
			self.__mappedY = None
		self.normalsChanged.emit(axis)

	@Slot(Axis)
	def renormalizeValues(self, axis: Axis = Axis.Both):
		if axis & Axis.X:
			self.__normalX = None
			self.__mappedX = None
		if axis & Axis.Y:
			self.__normalY = None
			self.__mappedY = None
		self.normalsChanged.emit(axis)

	@Slot(dict)
	def updateSlot(self, data: dict = None):
		self.__clearCache()
		self.update()

	@Slot()
	def updateSlot(self):
		self.__clearCache()
		self.update()

	@property
	def labeled(self) -> bool:
		if self._labelData is None:
			return False
		return self._labelData.isVisible()

	@labeled.setter
	def labeled(self, value: bool):
		if value and self._labelData is None:
			self._labelData = PeakTroughList(self.key, self)
			self._labelData.setVisible(value)
		elif value and self._labelData is not None:
			self._labelData.setVisible(value)
		elif not value and self._labelData is not None:
			self._labelData.setVisible(value)
		else:
			pass

	@property
	def interpolate(self) -> bool:
		return self._interpolate

	@interpolate.setter
	def interpolate(self, value):
		self._interpolate = value

	@cached_property
	def rawData(self) -> list:
		return self._value.hourly

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
	def value(self):
		return self._value

	@value.setter
	def value(self, value):
		# if self._value is not None and value != self._value:
		# 	self._value.valueChanged.disconnect(self.updateSlot)
		self._value = value

	# self._value.valueChanged.connect(self.updateSlot)

	@property
	def key(self):
		return self._value.key

	@property
	def api(self):
		return self._value.api

	def __clearCache(self):
		clearCacheAttr(self, 'rawData')
		clearCacheAttr(self, '__peaksAndTroughs')
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

	@cached_property
	def __peaksAndTroughs(self):
		# Still needs work but doesn't require scipy
		# a = self.highsLows
		# self._peaks = [i['high'] for i in a.values()]
		# self._troughs = [i['low'] for i in a.values()]
		periodHours = self._value.hourly.period.seconds // 3600
		source = self.smoothed

		spreadHours = 6
		multiplier = len(source) / len(self.array) if len(source) > len(self.array) else 1

		spread = round(spreadHours * multiplier / periodHours)

		peaks, troughs = findPeaksAndTroughs(list(source), spread=spread)
		peaks = [i for j in peaks for i in j]
		troughs = [i for j in troughs for i in j]
		if multiplier > 1:
			peaks = [self.rawData[int(i / self.multiplier)] for i in peaks]
			troughs = [self.rawData[int(i / self.multiplier)] for i in troughs]
		else:
			peaks = [self.rawData[i] for i in peaks]
			troughs = [self.rawData[i] for i in troughs]
		# peaks = filterBest(peaks, self.rawData, indexes=False, high=True)
		# troughs = filterBest(troughs, self.rawData, indexes=False, high=False)
		return peaks, troughs

	# peaks, troughs = findPeaksAndTroughs(list(self.smoothed), spread=4)
	# self._peaks = filterBest(peaks, self.smoothed, True)
	# self._troughs = filterBest(troughs, self.smoothed, False)

	def interp(self):
		x = np.array([t.timestamp.timestamp() for t in self.rawData])
		y = np.array(self.rawData)
		f = interp1d(x, y, kind='cubic')
		f = self._figure.interpField
		return f(x, y)

	@overload
	def __parseData(self, values: Iterable[Union[ValueWrapper, 'PeakTroughData']]):
		...  # values is an iterable of ValueWrapper or PeakTroughData that contain both x and y axes

	@overload
	def __parseData(self, value: Union[ValueWrapper, 'PeakTroughData']):
		...  # value is a single ValueWrapper or PeakTroughData that contains both x and y axes

	@overload
	def __parseData(self, x: Iterable[Union[float, int]], y: Iterable[Union[float, int]]):
		...  # x and y are iterables of floats or ints

	@overload
	def __parseData(self, x: Union[float, int], y: Union[float, int]):
		...  # x and y are single values of floats or ints

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
		if 'values' in K:
			T = K['values']
			if isinstance(T[0], PeakTroughData):
				T = np.array([[t.timestamp.timestamp(), t.value.value] for t in T])
				x, y = np.swapaxes(T, 0, 1)
			elif isinstance(T[0], ValueWrapper):
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
				if isinstance(x, ValueWrapper) and isinstance(y, ValueWrapper):
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
			if isinstance(x, ValueWrapper) and isinstance(y, ValueWrapper):
				return x.value, y.value
			return x, y
		if len(T) > 2:
			if isinstance(T[0], ValueWrapper):
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

	def __findAxis(self, *T, **K) -> tuple[Axis, tuple, dict]:
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
		:return: tuple of normalized points (values between 0 and 1)
		"""
		x, y = self.__parseData(*T, **K)

		dataRange = self._figure.dataRange

		if y is not None:
			y = -((y - dataRange.min) / dataRange.range) + 1
		if x is not None:
			x = (x - self._figure.parentItem().timeframe.min.timestamp()) / self._figure.parentItem().timeframe.rangeSeconds
		if isinstance(x, Iterable) and isinstance(y, Iterable):
			return np.stack((x, y))
		return np.array([[x], [y]])

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
		values = {'axis': Axis.Neither}
		if self.__normalX is None:
			values['axis'] |= Axis.X
			values['x'] = self.timeArrayInterpolated
		if self.__normalY is None:
			values['axis'] |= Axis.Y
			values['y'] = self.interpolated
		if values['axis']:
			x, y = self.normalize(**values)
		if x is not None:
			self.__normalX = x
		if y is not None:
			self.__normalY = y

	# self.normalsChanged.emit(values['axis'])

	@property
	def plotValues(self) -> tuple[np.array, np.array]:
		return [QPointF(ix, iy) for ix, iy in zip(self.mappedX, self.mappedY)]

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
	def mapped(self):
		return self.mappedX, self.mappedY

	@property
	def mappedX(self):
		if self.__mappedX is None:
			self.mapData()
		return self.__mappedX

	@property
	def mappedY(self):
		if self.__mappedY is None:
			self.mapData()
		return self.__mappedY

	def mapData(self):
		# self.blockSignals(True)
		values = {'axis': Axis.Neither}
		if self.__mappedX is None:
			values['axis'] |= Axis.X
			values['x'] = self.normalizedX
		if self.__mappedY is None:
			values['axis'] |= Axis.Y
			values['y'] = self.normalizedY
		if values['axis']:
			x, y = self.normalizeToFrame(**values)
		if x is not None:
			self.__mappedX = x
		if y is not None:
			self.__mappedY = y

	# self.blockSignals(False)
	# self.mappedChanged.emit(values['axis'])

	# x_new = np.array([y.timestamp.timestamp() for y in self.rawData])
	# y_new = y
	# y_normal = -((y_new - y_new.min()) / y_new.ptp()) + 1
	# x_normal = (x_new - x_new.min()) / timedelta(days=3).total_seconds()

	@property
	def figure(self) -> 'Figure':
		return self._figure

	@figure.setter
	def figure(self, figure: 'Figure'):
		if self._figure is not None:
			self._figure.plotData.pop(self.value.key)
		self._figure = figure
		self._figure.plotData[self.value.key] = self
		self.__clearCache()

	@property
	def peaks(self) -> List[Measurement]:
		return self.__peaksAndTroughs[0]

	@property
	def troughs(self) -> List[Measurement]:
		return self.__peaksAndTroughs[1]

	@property
	def peaksAndTroughs(self) -> tuple[List[Measurement], List[Measurement]]:
		return self.__peaksAndTroughs

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
		if self._labelData is None:
			self.genLabels()
		return self._labelData.labels

	# @property
	# def normalized(self):
	# 	meta = self._figure.dataRange if self._figure is not None else None
	# 	return -normalize(self.rawData, meta) + 1  # QPainterPath draws from the top left instead of bottom left so flip the values

	@property
	def array(self) -> np.array:
		return np.array(self.rawData.array, dtype=self.dtype)
		if self._array is None:
			self._array = np.array(self.rawData, dtype=self.dtype)
		self._array
		return np.roll(self._array, -self.offset)

	@property
	def timeArray(self) -> np.array:
		x = self.rawData.timeseries
		return x

	@property
	def timeArrayInterpolated(self):
		# if not self._interpolated:
		# 	return self.timeArray
		x_min = self.rawData[0].timestamp.timestamp()
		x_max = self.rawData[-1].timestamp.timestamp()
		return np.linspace(x_min, x_max, int(len(self.rawData) * self.multiplier))

	@property
	def interpolated(self) -> np.array:
		f = interp1d(self.timeArray, self.smoothed, kind='cubic')
		return f(self.timeArrayInterpolated)
		# if not self._interpolate or not self.isInterpolatable:
		# 	return self.array
		print('building interp')
		if self._interpolated is None:
			f = interp1d(self.timeArray, self.smoothed, kind='cubic')
			# self._interpolated = interpData(self.smoothed, self.multiplier, self.length)
			self._interpolated = f(self.timeArrayInterpolated)
		return self._interpolated

	@property
	def smoothed(self) -> np.array:
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
	def data(self) -> np.array:
		return self.interpolated

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
	def multiplier(self) -> timedelta:
		if self._multiplier is None:
			return max(int(self.length / len(self)), 1)
		totalSeconds = self.value.hourly.period.total_seconds()
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
		self.update()

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
	# for label in self.labels.childItems():
	# 	label.show()
	# for label in self.labels.childItems():
	# 	label.update()

	def receiveUpdate(self, value):
		self.update()

	@property
	def state(self):
		return {
			'class':       self.__class__.__name__,
			'valueLink':   self.value.toDict(),
			'key':         self.key,
			'labeled':     self.labeled,
			'interpolate': self.interpolate,
			'order':       self.order,
			'multiplier':  self.multiplier,
			'smooth':      self._smooth,
			'plot':        self.graphic.state,
		}


class PathType(Enum):
	Linear = 0
	Cubic = 2
	Quadratic = 3
	Spline = 4


class Plot(QGraphicsPathItem):
	_dashPattern: list[int]
	_type: PathType
	figure: 'Figure'
	data: GraphItemData
	_style: Qt.PenStyle
	_scalar: float
	pathType: PathType
	_gradient: bool = False
	_temperatureGradient: Optional[TemperatureKelvinGradient] = None

	def __init__(self, parent: GraphItemData,
	             color: QColor = None,
	             gradient: str = '',
	             dashPattern: Union[Qt.PenStyle, Iterable, str] = Qt.SolidLine,
	             scalar: float = 1.0):

		self.data: GraphItemData = parent
		self.figure: 'Figure' = parent.figure
		self.color = color
		self.dashPattern = dashPattern
		self.scalar = scalar
		self._path = QPainterPath()
		self.gradient = gradient

		# if morph:
		# 	data = self.figure.
		# 	if type(morph) == str:
		# 		morph = self.figure.data[morph]
		# 	if len(data) != len(morph):
		# 		morph = interpData(morph, newLength=len(data))
		# 	morph = normalize(morph) * 10
		# self.morph = morph
		super(Plot, self).__init__()
		self.update()
		self.setAcceptHoverEvents(True)
		self.setParentItem(self.figure)
		self.data.normalsChanged.connect(self.replot)
		self.data.mappedChanged.connect(self.replot)
		self.setAcceptHoverEvents(True)

	def replot(self, axis: Axis = Axis.Both):
		self.update()

	def setZValue(self, value: int):
		super(Plot, self).setZValue(self.figure.zValue + 1)

	def mousePressEvent(self, event) -> None:
		if self.shape().contains(event.pos()):
			event.accept()
			self.figure.setFocus(Qt.MouseFocusReason)
			print(f'Clicked: {self.data.value.title} path at value {self.data.rawData[round(event.pos().x() / self.figure.graph.pixelHour)]}')
			self.setSelected(True)
			if debug:
				self.data.updateEverything(None)

		else:
			event.ignore()

	def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		event.ignore()
		self.figure.parent.mouseMoveEvent(event)
		self.figure.parent.setFocus(Qt.MouseFocusReason)

	def hoverEntryEvent(self, event: QGraphicsSceneHoverEvent) -> None:
		self.setGraphicsEffect(hover)
		super(Plot, self).hoverEntryEvent(event)

	def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
		self.setGraphicsEffect(None)
		super(Plot, self).hoverLeaveEvent(event)

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
		if self._color is None:
			return colorPalette.windowText().color()
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
	def figure(self) -> 'Figure':
		return self._figure

	@figure.setter
	def figure(self, value: 'Figure'):
		self._figure = value

	@property
	def state(self):
		return {
			'type':        DisplayType.Plot,
			'scalar':      round(self.scalar, 5),
			'dashPattern': self.dashPattern,
			'gradient':    None,
			'color':       rgbHex(*QColor(self.color).toTuple()[:3]) if self._color is not None else None
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
		return f"Plot {hex(id(self))} of '{self.data.value.key}' in figure '{self.figure.name}'"

	def _generatePen(self):
		weight = self.figure.parentItem().plotLineWeight() * self.scalar
		self.penOffset = weight * 0.6
		self.penOffsetScaler = 1 - (weight / self.figure.frameRect.height())
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
		start = values[0]
		start.setY(start.y() * self.penOffsetScaler + self.penOffset)
		start.setX(-10)
		self._path.moveTo(start)
		for value in values:
			value.setY(value.y() * self.penOffsetScaler + self.penOffset)
			self._path.lineTo(value)
		self.setPath(self._path)
		clearCacheAttr(self, '_hoverArea')

	def __getValues(self) -> list[QPointF]:
		self._path = QPainterPath()
		values = self.data.plotValues
		if len(values) > 1200:
			log.warning(f'Plot path contains {len(values)} points and will result in performance issues')
		return values

	# def paint(self, painter: QPainter, option, widget: QWidget):
	# 	painter.setPen(QPen(Qt.red, 1))
	# 	painter.setBrush(Qt.red)
	# 	painter.drawPath(self.shape())
	# 	super(Plot, self).paint(painter, option, widget)

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
					ratio = abs(sin(np.radians(targetAngle)))
					reverseTarget.setLength(reverseTarget.length() * ratio)
				reverseSource = QLineF.fromPolar(
					source.length() * factor, source.angle()).translated(p1)
				sourceAngle = current.angleTo(source)
				if 90 < sourceAngle < 270:
					ratio = abs(sin(np.radians(sourceAngle)))
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

	def shape(self) -> QPainterPath:
		return self._shape

	def _genShape(self):
		qp = QPainterPathStroker()
		qp.setWidth(self.figure.parentItem().plotLineWeight() * self.scalar * 4)
		shape = qp.createStroke(self._path)
		self._shape = shape

	def update(self):
		self.setPen(self._generatePen())
		self._updatePath()
		self._genShape()
		super(Plot, self).update()

	def setZValue(self, z: float) -> None:
		super(Plot, self).setZValue(z)


class GraphicText(QGraphicsTextItem):
	_value: ValueWrapper
	_parent: GraphItemData
	figure: 'FigureRect'
	__alignment: Alignment = Alignment.Center

	def __init__(self, parent: GraphItemData,
	             value: Optional[Any] = None,
	             alignment: Alignment = Alignment.Center,
	             scalar: float = 1.0,
	             font: Union[QFont, str] = None,
	             color: QColor = None):
		super(GraphicText, self).__init__(parent=None)
		self._parent = parent
		self._value = value
		self.scalar = scalar
		self.setColor(color)
		self.setFont(font)
		self.updateItem()
		self.setGraphicsEffect(SoftShadow())
		if isinstance(parent, GraphItemData):
			self.setParentItem(parent.figure)
		else:
			self.setParentItem(parent)
		self.setPlainText('')
		self.setAlignment(alignment)

	def setZValue(self, z: float) -> None:
		z = max(i.graphic.zValue() for i in self.figure.plots) + 10
		super(GraphicText, self).setZValue(z)

	def setFontSize(self, size: float) -> None:
		font = self.font()
		font.setPixelSize(size)
		self.setFont(font)

	@property
	def parent(self):
		return self._parent

	@property
	def figure(self):
		return self._parent.figure

	def setAlignment(self, alignment: Alignment):
		if not isinstance(alignment, Alignment):
			alignment = Alignment(alignment)
		self.__alignment = alignment
		self.updateTransform()

	def alignment(self):
		return self.__alignment

	def setFont(self, font: Union[QFont, str]):
		if font == None:
			font = QFont(rounded)
		elif isinstance(font, str):
			font = QFont(font, self.height() * .1)
		elif isinstance(font, QFont):
			font = font
		else:
			font = QFont(font)
		super(GraphicText, self).setFont(font)
		self.updateTransform()

	def updateTransform(self):
		transform = QTransform()
		transform.translate(self.boundingRect().width() * self.alignment().multipliers[0], self.boundingRect().height() * self.alignment().multipliers[1])
		self.setTransform(transform)

	def setColor(self, value):
		if value is None:
			color = colorPalette.windowText().color()
		elif isinstance(value, str) and value.startswith('#'):
			value = QColor(value)
		elif isinstance(value, QColor):
			color = value
		else:
			color = colorPalette.windowText().color()
		self.setDefaultTextColor(color)

	def updateFontSize(self):
		self.setFont(QFont(self.font().family(), self.figure.parent.fontSize * self.scalar))

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

	def setPlainText(self, text: str) -> None:
		super(GraphicText, self).setPlainText(text)
		self.updateTransform()

	def setPos(self, *args, **kwargs):
		super(GraphicText, self).setPos(*args, **kwargs)

	def updateItem(self) -> None:
		self.setZValue(self.parent.graphic.zValue() + 1)
		self.updateFontSize()

	def text(self) -> str:
		return str(self._value)

	@property
	def value(self):
		return self._value

	@value.setter
	def value(self, value):
		if str(value) != self.text():
			self._value = value
			self.setPlainText(self.text())
			self.updateItem()


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
		raw *= 255 * opacity
		raw = raw.astype(np.uint8)

		return raw


class PeakTroughLabel(GraphicText):

	def __init__(self, parent: 'PeakTroughList', value: 'PeakTroughData'):
		super(PeakTroughLabel, self).__init__(parent=parent.data)
		self._value = value
		self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

	def delete(self):
		self.figure.scene().removeItem(self)

	def text(self) -> str:
		return str(self.value)

	@property
	def value(self):
		if self._value is None:
			return None
		return self._value.value

	def update(self):
		self.setPlainText(self.text())
		super(PeakTroughLabel, self).update()

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemPositionChange:
			containingRect = self.figure.contentsRect()
			selfRect = self.boundingRect()
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

			x = capValue(x, minX, maxX)
			y = capValue(y, minY, maxY)

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

# def paint(self, painter, option, widget):
# 	painter.setPen(selectionPen)
# 	painter.drawRect(self.boundingRect())
# 	super(PeakTroughLabel, self).paint(painter, option, widget)


@dataclass
class PeakTroughData:
	value: ValueWrapper
	timestamp: datetime
	parent: 'PeakTroughList' = field(repr=False, compare=False)
	isPeak: bool
	graphic: PeakTroughLabel = field(init=False)

	def __post_init__(self):
		self.graphic = PeakTroughLabel(self.parent, self)
		self.graphic.update()

	def delete(self):
		self.graphic.delete()

	def update(self, **kwargs):
		if not any(getattr(self, k) != v for k, v in kwargs.items()) and self.parent.normalized:
			self.parent.clearNormalized()
		for key, value in kwargs.items():
			setattr(self, key, value)
		self.graphic.update()


class PeakTroughList(list):
	labels: list[PeakTroughLabel] = []
	data: GraphItemData
	key: CategoryItem
	__xValues: list[float] = None  # Normalized x values
	__yValues: list[float] = None  # Normalized y values
	_xValues: list[float] = None  # Mapped x values
	_yValues: list[float] = None  # Mapped y values

	def __init__(self, key: CategoryItem, data: GraphItemData):
		self.key = key
		self.data = data
		super(PeakTroughList, self).__init__()

		self.refreshList()
		self.mapValues()
		self.setLabels()

		self.data.normalsChanged.connect(self.resetNormalized)
		self.data.mappedChanged.connect(self.clearMapped)

	def __hash__(self):
		return hash(self.key)

	@property
	def figure(self) -> 'FigureRect':
		return self.data.figure

	@property
	def plot(self) -> Plot:
		return self.data.graphic

	def clear(self, after: int = 0):
		while after < len(self):
			i = self.pop()
			i.delete()

	def update(self, values: list[dict]):
		self.clearNormalized = True
		self.clear(len(values))
		if len(values) > len(self):
			self.extend([PeakTroughData(parent=self, **value) for value in values[len(self):]])
		for newValue, oldValue in zip(values, self):
			oldValue.update(**newValue)
		if (self[1].timestamp - self[0].timestamp).total_seconds() / 3600 <= 6:
			v = self.pop(0)
			v.delete()
		if (self[-1].timestamp - self[-2].timestamp).total_seconds() / 3600 <= 6:
			v = self.pop()
			v.delete()

	@property
	def normalized(self) -> bool:
		return self._xValues is not None or self._yValues is not None

	@property
	def mapped(self) -> bool:
		return self.__xValues is not None or self.__yValues is not None

	def resetNormalized(self, axis: Axis = Axis.Neither):
		if axis & Axis.X:
			self.__xValues = None
			self._xValues = None
		if axis & Axis.Y:
			self.__yValues = None
			self._yValues = None
		self.setLabels()

	def clearMapped(self, axis: Axis = Axis.Neither):
		if axis & Axis.X:
			self._xValues = None
		if axis & Axis.Y:
			self._yValues = None
		self.setLabels()

	def reset(self, axis: Axis = Axis.Both):
		if axis & Axis.X:
			self.__xValues = None
		if axis & Axis.Y:
			self.__yValues = None

	def refreshList(self):
		peaks, troughs = self.data.peaksAndTroughs
		peaks = [{'timestamp': item.timestamp, 'value': item, 'isPeak': True} for item in peaks]
		troughs = [{'timestamp': item.timestamp, 'value': item, 'isPeak': False} for item in troughs]
		values = [x for x in chain.from_iterable(zip_longest(peaks, troughs)) if x is not None]
		values = sorted(values, key=lambda x: x['timestamp'])
		self.update(values)

	def setLabels(self):
		values = self.values
		withLambda = False
		fontSize = self.plot.figure.parent.fontSize
		if withLambda:
			list(map(lambda item, value: item.graphic.setPos(*value), self, values))
		else:
			i = 0
			plot_shape = self.plot.mapToScene(self.plot.shape())
			for item, value in zip(self, values):
				item.graphic.setFontSize(fontSize)
				item.graphic.setPos(*value)
				alightment = AlignmentFlag.Bottom if item.isPeak else AlignmentFlag.Top
				item.graphic.setAlignment(alightment)
				shape = item.graphic.mapToScene(item.graphic.shape())
				intersection = shape.intersected(plot_shape)
				if not intersection.isEmpty():
					x = value[0]
					rect = intersection.boundingRect()
					y = rect.top() if item.isPeak else rect.bottom()
					item.graphic.setPos(x, y)

				others = [o for o in self[max(0, i - 3):i] if shape.intersects(o.graphic.mapToScene(o.graphic.shape()))]
				if others:
					item.graphic.hide()
				# _all = [*others, item]
				# x = sum(i.graphic.pos().x() for i in _all) / len(_all)
				# y = sum(i.graphic.pos().y() for i in _all) / len(_all)
				# if item.isPeak:
				# 	m = max(others, key=lambda x: x.value)
				# else:
				# 	m = min(others, key=lambda x: x.value)
				# m.graphic.setPos(x, y)
				# for it in _all:
				# 	if it is m:
				# 		continue
				# 	it.graphic.hide()
				else:
					item.graphic.show()

				i += 1
		# cols = item.graphic.collidingItems(Qt.ItemSelectionMode.IntersectsItemBoundingRect)
		# for i in cols:
		# 	if isinstance(i, PeakTroughLabel):
		# 		i.hide()

	def mapValues(self):
		axis = Axis.Neither
		kwargs = {'axis': axis}
		if self._xValues is None:
			kwargs['axis'] |= Axis.X
			kwargs['x'] = self.normalizedX
		if self._yValues is None:
			kwargs['axis'] |= Axis.Y
			kwargs['y'] = self.normalizedY
		if kwargs['axis']:
			x, y = self.data.normalizeToFrame(**kwargs)
			if x is not None:
				self._xValues = x
			if y is not None:
				self._yValues = y
		else:
			pass  # Both axes are already mapped

	def normalizeValues(self):
		# start with assuming neither axis needs to be normalized
		kwargs = {'axis': Axis.Neither}
		if self.__xValues is None:  # if x values are already normalized, add Axis.X to axis
			kwargs['axis'] |= Axis.X
		if self.__yValues is None:  # if y values are already normalized, add Axis.Y to axis
			kwargs['axis'] |= Axis.Y
		if kwargs['axis']:
			kwargs['values'] = self
		x, y = self.data.normalize(**kwargs)
		if x is not None:
			self.__xValues = x
		if y is not None:
			self.__yValues = y
		else:
			pass  # Both axes are already normalized

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
	def xValues(self):
		if self._xValues is None:
			self.mapValues()
		return self._xValues

	@property
	def yValues(self):
		if self._yValues is None:
			self.mapValues()
		return self._yValues

	@property
	def values(self):
		return [i for i in zip(self.xValues, self.yValues)]

	def isVisible(self):
		return any(i.graphic.isVisible() for i in self)

	def setVisible(self, visible: bool):
		list(map(lambda label: label.setVisible(visible), self.labels))


class TimeMarker(QGraphicsLineItem):

	def __init__(self, graph: 'GraphPanel', timestamp: datetime, color: QColor = None):
		self.parent = graph
		self.timestamp = timestamp
		super(TimeMarker, self).__init__(parent=graph)
		if color is None:
			color = colorPalette.windowText().color()
		self.setPen(QPen(color, 3, Qt.DashLine))
		self.update()

	@property
	def _line(self):
		graphHeight = self.parent.rect().height()
		a = QPointF(0, -20)
		b = QPointF(0, graphHeight + 20)
		return QLineF(a, b)

	@property
	def position(self):
		start = self.parent.timeStart()
		x = (self.timestamp - start).total_seconds() / 3600 * self.parent.graph.pixelHour
		# y = self.parent.graph.height() - self.boundingRect().height() - 20
		return QPointF(x, 0)

	def update(self):
		self.setLine(self._line)
		self.setPos(self.position)
		super(TimeMarker, self).update()


class DayLine(TimeMarker):

	def __init__(self, graph: 'GraphPanel', timestamp: datetime):
		super(DayLine, self).__init__(graph, timestamp)
		self.update()


class DayText(GraphicText):
	formatStrings = ['%A', '%a']

	def __init__(self, parent: 'DayAnnotations', timestamp: datetime):
		self.graph = parent.graph
		super(DayText, self).__init__(parent=parent, value=timestamp, scalar=0.75)
		self.update()
		self.setPlainText(self.text())

	def updateItem(self) -> None:
		self.setZValue(self.parent.zValue() + 1)
		self.updateFontSize()
		self.setPos(self.position())

	def setZValue(self, z: float) -> None:
		super(GraphicText, self).setZValue(z)

	def updateFontSize(self):
		self.setFont(QFont(self.font().family(), self.graph.fontSize * self.scalar))

	def position(self):
		start = self.parent.timeStart()
		x = (self._value - start).total_seconds() / 3600 * self.graph.pixelHour
		y = self.graph.height() - self.boundingRect().height() - 10
		return QPointF(x, y)

	def update(self):
		QGraphicsTextItem.setPos(self, self.position())
		# self.setPlainText(self.text())
		super(DayText, self).update()

	def text(self) -> str:
		return self.value.strftime(self.formatStrings[0])

# def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
# 	painter.setPen(selectionPen)
# 	painter.drawRect(self.boundingRect())
# 	painter.drawRect(QRectF(-2, -2, 4, 4))
# 	super(DayText, self).paint(painter, option, widget)


class DayAnnotations(QGraphicsRectItem):

	def __init__(self, graph: 'GraphPanel'):
		self.graph = graph
		super(DayAnnotations, self).__init__(parent=graph)
		self.buildLabels()
		self.addDayLines()
		self.graph.signals.resized.connect(self.parentResized)
		self.update()

	def parentResized(self):
		self.update()

	def addDayLines(self):
		self.lines = []
		start = self.timeStart().replace(hour=0, minute=0, second=0, microsecond=0)
		for day in range(ceil(self.timeRange().total_seconds() / 3600 / 24) + 1):
			line = TimeMarker(self, start + timedelta(days=day))
			self.scene().addItem(line)
			self.lines.append(line)

	def buildLabels(self):
		self.dayLabels = []
		start = self.timeStart().replace(hour=0, minute=0, second=0, microsecond=0)
		for day in range(ceil(self.timeRange().total_seconds() / 3600 / 24) + 1):
			timestamp = start + timedelta(days=day) + timedelta(hours=12)
			label = DayText(self, timestamp)
			self.dayLabels.append(label)
			self.graph.scene().addItem(label)

	def timeStart(self):
		return min(figure.figureMinStart() for figure in self.graph.figures)

	def timeEnd(self):
		return max(figure.figureMaxEnd() for figure in self.graph.figures)

	def timeRange(self):
		return self.timeEnd() - self.timeStart()

	@property
	def _rect(self):
		figureRects = [f.mapRectToParent(f.contentsRect()) for f in self.graph.figures]
		x = min(f.x() for f in figureRects)
		y = min(f.y() for f in figureRects)
		w = max(f.width() for f in figureRects)
		h = max(f.height() for f in figureRects)
		return QRectF(x, y, w, h)

	def update(self):
		rect = self._rect
		pos = rect.topLeft()
		self.setPos(pos)
		rect.moveTo(0, 0)
		self.setRect(rect)
		for label in self.dayLabels:
			label.updateItem()
		for line in self.lines:
			line.update()
		super(DayAnnotations, self).update()

	def updatePosition(self):
		rect = self._rect
		pos = rect.topLeft()
		self.setPos(pos)

# def paint(self, painter, option, widget):
# 	pen = QPen(Qt.red, 1)
# 	brush = QBrush(Qt.NoBrush)
# 	painter.setPen(pen)
# 	painter.setBrush(brush)
# 	# draw lines for each hour
# 	painter.setPen(QPen(Qt.red, 1, Qt.DashLine))
# 	for hour in range(24):
# 		x = hour * self.graph.pixelHour
# 		painter.drawLine(x, 0, x, self.graph.height())
# 	super(DayAnnotations, self).paint(painter, option, widget)


class GraphPanel(Panel):
	isEmpty = False
	figures: List['FigureRect'] = []
	timeframe: TimeFrame
	_acceptsChildren: bool = False
	graphZoom: GraphZoom
	a = None

	def __init__(self, *args, **kwargs):
		if 'geometry' not in kwargs:
			kwargs['geometry'] = {'size': {'width': 800, 'height': 400, 'absolute': True}, 'absolute': True}
		super(GraphPanel, self).__init__(*args, **kwargs)
		self.isEmpty = False
		self.timeframe = kwargs.get('timeframe', TimeFrame(timedelta(days=3)))
		self.selectedItem = None
		self.setHighlighted(True)
		self.setAcceptDrops(True)
		self.clipping = True
		self.graphZoom = GraphZoom(self, self.timeframe)
		for figure in kwargs.get('figures', {}).values():
			cls = figure.pop('class', FigureRect)
			cls(self, **figure)
		self.lines = []
		self.a = DayAnnotations(self)
		self.scene().addItem(self.a)

	@property
	def pixelHour(self):
		return self.width() / self.timeframe.hours

	def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent):
		self.graphZoom.setVisible(True)
		super(GraphPanel, self).hoverEnterEvent(event)

	def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent):
		self.graphZoom.setVisible(False)
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

	@property
	def name(self) -> str:
		return f'{self.__class__.__name__}_0x{self.uuidShort}'

	def redraw(self, axis: Axis = Axis.Both):
		pass

	def focusInEvent(self, event) -> None:
		super(GraphPanel, self).focusInEvent(event)

	def focusOutEvent(self, event) -> None:
		super(GraphPanel, self).focusOutEvent(event)

	def mouseMoveEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		diff = mouseEvent.scenePos() - mouseEvent.lastScenePos()
		for figure in [*self.figures]:
			figure.moveBy(diff.x(), diff.y())
			self.a.updatePosition()
		# figure.marginHandles.topHandle.moveBy(diff.x(), diff.y())

	@property
	def timeframeIncrement(self):
		days = self.timeframe.rangeSeconds / 60 / 60 / 24
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
				a = FigureRect(self)
				a.addItem(value)
				a.show()
			else:
				event.ignore()

	@property
	def fontSize(self):
		return min(max(self.rect().height() * 0.1, 30, min(self.rect().width() * 0.06, self.rect().height() * .2)), 100)

	def parentResized(self, arg):
		super(GraphPanel, self).parentResized(arg)
		if self.a is not None:
			self.a.update()

	def plotLineWeight(self) -> float:
		weight = self.rect().height() * golden * 0.005
		weight = weight if weight > 8 else 8.0
		return weight

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemChildAddedChange:
			if isinstance(value, (Incrementer, IncrementerGroup)):
				value.setZValue(10000)
			elif isinstance(value, FigureRect):
				self.signals.resized.connect(value.redraw)
		elif change == QGraphicsItem.ItemChildRemovedChange:
			if isinstance(value, FigureRect):
				disconnectSignal(self.signals.resized, value.redraw)
		return super(GraphPanel, self).itemChange(change, value)

	@property
	def state(self):
		state = super(GraphPanel, self).state
		state.pop('childItems', None)
		state.update({
			'figures':   {str(figure.sharedKey): figure.state for figure in self.figures},
			'timeframe': self.timeframe.state,
		})
		return state


class FigureRect(Panel):
	_default: str = None
	_margins: Margins
	dataValueRange: Optional[ArrayMetaData] = None
	plotData: dict[str, GraphItemData]
	isEmpty: bool = False
	_acceptsChildren: bool = False

	def __init__(self, parent: GraphPanel, margins: Margins = None, data: dict[str: GraphItemData] = None, *args, **kwargs):
		self.plotData = {}

		if margins is None:
			margins = {'left': 0, 'top': 0.1, 'right': 0, 'bottom': 0.1}

		if 'geometry' not in kwargs:
			kwargs['geometry'] = {'size': {'width': 1.0, 'height': 1.0}, 'position': {'x': 0, 'y': 0}, 'absolute': False}

		super(FigureRect, self).__init__(parent, margins=margins, **kwargs)

		self.setParentItem(parent)
		self.setFlag(QGraphicsItem.ItemIsMovable, False)
		self.setFlag(QGraphicsItem.ItemIsFocusable, True)
		self.setFlag(QGraphicsItem.ItemClipsChildrenToShape, False)
		self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
		self.resizeHandles.setParentItem(None)
		self.marginHandles = FigureHandles(self)

		self.marginHandles.hide()
		self.marginHandles.setZValue(1000)
		self.geometry.setRelativeSize(1.0)
		self.setFlag(self.ItemIsSelectable, False)
		if data:
			self.loadPlotData(data)

	@property
	def graph(self) -> GraphPanel:
		return self.parentItem()

	def redraw(self):
		for item in self.plotData.values():
			item.graphic.update()

	def loadPlotData(self, plotData: dict[str, GraphItemData]):
		for key, data in plotData.items():
			value = data.pop('valueLink', None)
			self.addItem(value, **data)

	@property
	def plots(self):
		return list(self.plotData.values())

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
		self.marginHandles.updatePosition(self.parentItem().rect())

	def focusOutEvent(self, event: QFocusEvent) -> None:
		super().focusOutEvent(event)
		if not self.parent.childHasFocus():
			self.parent.graphZoom.setVisible(False)
		self.marginHandles.hide()

	def debugBreak(self):
		a = list(self.plotData.values())[0]

	def parentResized(self, arg: Union[QPointF, QSizeF, QRectF]):
		super().parentResized(arg)

	def setParentItem(self, parent: GraphPanel):
		if self.parentItem() is parent:
			return

		if isinstance(parent, GraphPanel):
			parent.figures.append(self)
		elif self.parentItem() is not None:
			i = self.parentItem().figures.index(self)
			self.parentItem().figures.pop(i)
		super(FigureRect, self).setParentItem(parent)

	def dragEnterEvent(self, event: QGraphicsSceneDragDropEvent):
		if event.mimeData().hasFormat('application/graph-feature'):
			event.accept()
		else:
			event.ignore()
		super(FigureRect, self).dragEnterEvent(event)

	def figureStart(self) -> datetime:
		return sum([item.timeframe.min for item in self.plotData.values()]) / len(self.plotData)

	def figureMaxStart(self) -> datetime:
		return max([item.timeframe.min for item in self.plotData.values()])

	def figureMinStart(self) -> datetime:
		return min([item.timeframe.min for item in self.plotData.values()])

	def figureEnd(self) -> datetime:
		return sum([item.timeframe.max for item in self.plotData.values()]) / len(self.plotData)

	def figureMaxEnd(self) -> datetime:
		return max([item.timeframe.max for item in self.plotData.values()])

	def figureMinEnd(self) -> datetime:
		return min([item.timeframe.max for item in self.plotData.values()])

	@property
	def figureTimeRangeMin(self) -> timedelta:
		return self.figureMaxStart() - self.figureMinStart()

	@property
	def figureTimeRangeMax(self) -> timedelta:
		return self.figureMaxEnd() - self.figureMinStart()

	@property
	def contentsWidth(self) -> float:
		if self.plotData:
			r = max(self.parentItem().timeframe.rangeSeconds, 60)
			return self.figureTimeRangeMax.total_seconds() / r * self.frameRect.width()
		return self.frameRect.width()

	def setRect(self, rect: QRectF):
		rect.setWidth(self.contentsWidth)
		super(FigureRect, self).setRect(rect)

	def contentsRect(self) -> QRectF:
		rect = super(FigureRect, self).contentsRect()
		rect.setWidth(self.contentsWidth)
		return rect

	@property
	def marginPosition(self) -> QPointF:
		frame = self.frameRect
		return self.frameRect.topLeft()

	@property
	def frameRect(self):
		rect = self.parentItem().rect()
		return rect

	def width(self):
		return self.parent.width()

	def height(self):
		return self.parent.height()

	@property
	def dataRange(self):
		if self.dataValueRange is None:
			self.dataValueRange = ArrayMetaData(self)
		return self.dataValueRange

	@property
	def name(self):
		a = set([item.type for item in self.plotData.values()])
		if len(a) > 1:
			return '/'.join(a)
		else:
			return list(a)[0]

	def genLabels(self):
		list(self.plotData.values())[0].genLabels()

	@property
	def timeline(self):
		tMax = max([i.timeframe.max for i in self.plotData.values()])
		tMin = min([i.timeframe.min for i in self.plotData.values()])
		return TimeLineCollection(tMax, tMin, tMax - tMin)

	def addItem(self, value: MergedValue, labeled: bool = None, zOrder: Optional[int] = None, graphic: dict = {}, *args, **kwargs):

		cls = kwargs.pop('class', GraphItemData)
		if len(self.plotData) == 0 and labeled is None:
			labeled = True
		elif labeled is None:
			labeled = False

		item = cls(value, parent=self, labeled=labeled, graphic=graphic, *args, **kwargs)

		item.graphic.setParentItem(self)
		self.parent: GraphPanel
		# self.addToGroup(item.graphic)
		# self.addToGroup(item.graphic.hoverArea)
		item.labeled = labeled
		if zOrder is not None:
			item.allGraphics.setZValue(zOrder)
		for plot in self.plots:
			if plot is item:
				continue
			plot.updateEverything(None)
		return item

	def removeItem(self, item: GraphItemData):
		self.plotData.pop(item.key)
		self.scene.removeItem(item.allGraphics)
		del item

	@property
	def interpField(self):
		t = self.timeline
		d = self.dataRange
		stepT = self.scene.width / t.range.total_seconds()
		x = np.arange(t.min.timestamp(), t.max.timestamp(), 60)
		y = np.arange(d.min, d.max, d.range / self.scene.height)
		xx, yy = np.meshgrid(x, y)
		z = np.sin(xx ** 2 + yy ** 2)
		return interp2d(x, y, z, kind='cubic')

	def update(self):
		super(FigureRect, self).update()

	def ensureFramed(self):
		maxX = 0
		maxY = self.parentItem().rect().bottom() - self.rect().height()
		minX = self.parentItem().rect().right() - self.contentsWidth
		value = self.pos()
		x = min(max(value.x(), minX), maxX)
		y = min(max(value.y(), 0), maxY)
		value.setX(x)
		value.setY(y)
		self.setPos(value)

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemPositionChange:
			maxX = 0
			maxY = self.parentItem().rect().bottom() - self.rect().height()
			minX = self.parentItem().rect().right() - self.contentsWidth
			x = min(max(value.x(), minX), maxX)
			y = min(max(value.y(), 0), maxY)
			value.setX(x)
			value.setY(y)
			return super(Panel, self).itemChange(change, value)

		elif change == QGraphicsItem.ItemChildAddedChange:
			if isinstance(value, Plot):
				self.signals.resized.connect(value.update)
				value.setZValue(self.zValue() + 1)

		# elif change == QGraphicsItem.ItemChildRemovedChange:
		# 	if isinstance(value, Plot):
		# 		disconnectSignal(self.signals.resized, value.update)
		# 		disconnectSignal(value.data.updateSlot, self.parent.incrementers.action.action)
		# 		disconnectSignal(self.marginHandles.action.action, value.update)
		# 	elif isinstance(value, Text):
		# 		disconnectSignal(value.updateItem, self.parent.incrementers.action.action)
		# 		disconnectSignal(self.signals.resized, value.updateItem)

		return super(FigureRect, self).itemChange(change, value)

	@property
	def state(self):
		return {
			'class':   self.__class__.__name__,
			'margins': self.margins,
			'key':     self.sharedKey,
			'data':    {str(k): v.state for k, v in self.plotData.items()}
		}
