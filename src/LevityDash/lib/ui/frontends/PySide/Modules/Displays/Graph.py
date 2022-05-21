import re
import sys
from json import loads

import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import cached_property

from itertools import chain, zip_longest
from PySide2.QtCore import QLineF, QObject, QPoint, QPointF, QRectF, Qt, QTimer, Signal, Slot
from PySide2.QtGui import QBrush, QColor, QFocusEvent, QLinearGradient, QPainter, QPainterPath, QPainterPathStroker, QPen, QPixmap, QPolygonF, QTransform
from PySide2.QtWidgets import (QGraphicsDropShadowEffect, QGraphicsItem, QGraphicsItemGroup, QGraphicsLineItem, QGraphicsPathItem,
                               QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsSceneDragDropEvent, QGraphicsSceneHoverEvent, QGraphicsSceneMouseEvent, QGraphicsSceneWheelEvent, QToolTip)
from scipy.constants import golden
from scipy.interpolate import CubicSpline
from typing import Callable, ClassVar, Iterable, List, Optional, overload, Set, Tuple, Union, Any, Type, TypeVar, Dict
from uuid import uuid4
from WeatherUnits import Measurement, Temperature, Probability
from WeatherUnits.derived.precipitation import Hourly
from WeatherUnits.time.time import Millisecond, Second
from WeatherUnits.length import Centimeter, Inch, Millimeter
from yaml import SafeDumper

from LevityDash.lib.plugins.plugin import Container
from LevityDash.lib.plugins.observation import MeasurementTimeSeries, TimeAwareValue, TimeSeriesItem
from LevityDash.lib.ui.frontends.PySide import app, colorPalette

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.ui.colors import rgbHex
from LevityDash.lib.plugins.dispatcher import ValueDirectory, ForecastPlaceholderSignal, MultiSourceContainer, MonitoredKey
from LevityDash.lib.log import LevityGUILog
from LevityDash.lib.ui.frontends.PySide.Modules.DateTime import baseClock, baseClock as ClockSignals
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import Text
from LevityDash.lib.ui.frontends.PySide.Modules.Handles.MarginHandles import FigureHandles
from LevityDash.lib.ui.frontends.PySide.Modules.Handles.Incrementer import Incrementer, IncrementerGroup
from LevityDash.lib.ui.frontends.PySide.Modules.Handles.Timeframe import GraphZoom
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
from LevityDash.lib.utils.shared import _Panel, LOCAL_TIMEZONE, Unset, getOr, getOrSet
from LevityDash.lib.utils.various import DateTimeRange
from LevityDash.lib.ui.frontends.PySide.utils import DisplayType, GraphicsItemSignals, modifyTransformValues, addCrosshair
from LevityDash.lib.utils.data import AxisMetaData, DataTimeRange, findPeaksAndTroughs, normalize, smoothData, TimeFrameWindow, gaussianKernel
from LevityDash.lib.utils.shared import autoDType, clamp, clearCacheAttr, closestCeil, disconnectSignal, roundToPeriod, timestampToTimezone
from LevityDash.lib.utils.geometry import AlignmentFlag, Axis, Margins
from time import time

log = LevityGUILog.getChild('Graph')

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
		if qApp.mouseButtons() or not painter.testRenderHint(QPainter.Antialiasing):
			self.drawSource(painter)
			return
		super(SoftShadow, self).draw(painter)


class Color:
	__slots__ = ('__red', '__green', '__blue', '__alpha')
	__red: int
	__green: int
	__blue: int
	__alpha: int

	def __init__(self, color: str | Tuple[int | float]):
		self.__validate(color)

	def __validate(self, color: str | Tuple[int | float]):
		match color:
			case str(color):
				colors = [int(i, 16) for i in re.findall(r'([A-Fa-f0-9]{2})', color)]
				if len(colors) == 3:
					red, green, blue = colors
					alpha = 255
				elif len(colors) == 4:
					red, green, blue, alpha = colors
				else:
					raise ValueError(f'Invalid color string: {color}')
			case Iterable(int(red), int(green), int(blue)):
				alpha = 255
			case Iterable(int(red), int(green), int(blue), int(alpha)):
				pass
			case _:
				raise TypeError(f'Color must be a string, tuple of ints, or hexadecimal value, not {type(color)}')
		self.__red, self.__green, self.__blue, self.__alpha = red, green, blue, alpha

	@property
	def red(self) -> int:
		return self.__red

	@red.setter
	def red(self, value):
		self.__red = sorted((0, value, 255))[1]

	@property
	def green(self) -> int:
		return self.__green

	@green.setter
	def green(self, value):
		self.__green = sorted((0, value, 255))[1]

	@property
	def blue(self) -> int:
		return self.__blue

	@blue.setter
	def blue(self, value):
		self.__blue = sorted((0, value, 255))[1]

	@property
	def alpha(self) -> int:
		return self.__alpha

	@alpha.setter
	def alpha(self, value):
		self.__alpha = sorted((0, value, 255))[1]

	@property
	def QColor(self) -> QColor:
		return QColor(self.red, self.green, self.blue, self.alpha)

	def __str__(self):
		if self.alpha == 255:
			return f'#{self.__red:02x}{self.__green:02x}{self.__blue:02x}'
		return f'#{self.__red:02x}{self.__green:02x}{self.__blue:02x}{self.__alpha:02x}'

	def __get__(self, instance, owner):
		return getattr(instance, f'__{self.__class__.__name__}')

	def __set__(self, instance, value):
		setattr(instance, f'__{self.__class__.__name__}', value)

	@classmethod
	def representer(cls, dumper, data):
		return dumper.represent_str(str(data))


def typeFromAnnotation(annotatedClass: type, key: str, default: Type = Unset) -> type:
	value = annotatedClass.__annotations__.get(key, None)
	if default is not Unset and value is None:
		return default
	raise TypeError(f'{key} is not annotated for {annotatedClass}')


ValueCls = TypeVar('ValueCls')


class MappedGradientValue:
	__slots__ = ('__color', '__value')
	__types__: ClassVar[Dict[Type, Type]] = {}
	__item__: ClassVar[Type]
	value: ValueCls
	color: Color

	def __class_getitem__(cls, item):
		if isinstance(item, TypeVar):
			return cls
		if not isinstance(item, type):
			item = type(item)
		if item not in cls.__types__:
			t = type(f'MappedGradientValue[{item.__name__}]', (cls,), {'__annotations__': {'value': item}, '__item__': item})
			cls.__types__[item] = t
		return cls.__types__[item]

	def __init__(self, value: Any, color: Color | str | Tuple[int | float]):
		self.value = value
		self.color = color if isinstance(color, Color) else Color(color)

	@property
	def color(self):
		return self.__color

	@color.setter
	def color(self, value):
		self.__color = value

	@property
	def value(self):
		return self.__value

	@value.setter
	def value(self, value):
		if not isinstance(value, self.expectedType):
			value = self.expectedType(value)
		self.__value = value

	@property
	def expectedType(self) -> Type | Callable:
		t = self.__class__.__item__
		if not issubclass(t, TypeVar):
			return t
		return lambda x: x

	@expectedType.setter
	def expectedType(self, value):
		self.__class__.__item__ = value

	@classmethod
	def representer(cls, dumper: SafeDumper, data):
		value = float(data.value)
		if value.is_integer():
			value = int(value)
		return dumper.represent_mapping(cls.__name__, {'value': value, 'color': data.color})


class GradientValues(dict[str, MappedGradientValue[ValueCls]]):
	__types__: ClassVar[Dict[Type, Type]] = {}
	__presets__: ClassVar[Dict[str, 'GradientValues']] = {}
	__item__: ClassVar[Type]

	class QtGradient(QLinearGradient):
		def __init__(self, plot: 'Plot', values):
			self.plot = plot
			self.values = values
			super().__init__(0, 0, 0, 1)
			self.__genGradient()

		def __genGradient(self):
			T = self.localized
			locations = (T - T.min())/T.ptp()
			for position, value in zip(locations, self.values):
				self.setColorAt(position, value.color.QColor)

		@cached_property
		def localized(self):
			if getattr(self.plot.data.rawData[0], '@convertible', False):
				unit = self.plot.data.rawData[0]['@unit']
				return np.array([t.value[unit] for t in self.values.list])
			return np.array([t.value for t in self.values.list])

		@property
		def gradientPoints(self) -> Tuple[QPoint, QPoint]:
			T = (self.localized - self.plot.data.data[1].min())/self.plot.data.data[1].ptp()
			t = QTransform(self.plot.data.t)
			bottom = QPointF(0, T.max())
			top = QPointF(0, T.min())
			top = t.map(top)
			bottom = t.map(bottom)
			return top, bottom

		def update(self):
			start, stop = self.gradientPoints
			self.setStart(start)
			self.setFinalStop(stop)

		def __str__(self):
			return self.__class__.__name__

	def __class_getitem__(cls, item) -> 'GradientValues' | Type['GradientValues']:
		if isinstance(item, type):
			if not item in cls.__types__:
				t = type(f'GradientValues[{item.__name__}]', (GradientValues,), {'__item__': MappedGradientValue[item]})
				cls.__types__[item] = t
			return cls.__types__[item]
		if isinstance(item, str) and item in cls.__presets__:
			return cls.__presets__[item]

	def __new__(cls, name: str = None, *args, **kwargs):
		if name is not None:
			if name not in cls.__presets__:
				cls.__presets__[name] = super().__new__(cls, *args, **kwargs)
				cls.__presets__[name].presetName = name
			return cls.__presets__[name]
		return super().__new__(cls, *args, **kwargs)

	def __init__(self, name: str = None, **colors: Tuple[int | float, Color | str | Tuple[int | float]]):
		super().__init__()
		itemType = self.itemCls()
		for key, item in colors.items():
			self[key] = itemType(*item)

	@classmethod
	def itemCls(cls) -> ValueCls:
		if hasattr(cls, '__item__'):
			return cls.__item__
		return Any

	@classmethod
	def presets(cls) -> List[str]:
		return list(cls.__presets__.keys())

	@property
	def list(self) -> List[MappedGradientValue[ValueCls]]:
		return sorted(list(self.values()), key=lambda x: x.value, reverse=False)

	@property
	def min(self) -> int | float:
		return min(self, key=lambda x: x.value)

	@property
	def max(self) -> int | float:
		return max(self, key=lambda x: x.value)

	def __iter__(self):
		return iter(self.list)

	def __get__(self, instance, owner):
		if isinstance(instance, Plot):
			return self.QtGradient(plot=instance)
		return self

	@property
	def ptp(self):
		return self.max - self.min

	def toQGradient(self, plot: 'Plot') -> QtGradient:
		gradients = getOrSet(self.__dict__, '__QtGradients__', {})
		if plot not in gradients:
			gradients[plot] = self.QtGradient(plot, self)
		return gradients[plot]

	@classmethod
	def representer(cls, dumper: SafeDumper, data):
		if name := getattr(data, 'presetName', None):
			return dumper.represent_scalar(u'tag:yaml.org,2002:str', name)
		return dumper.represent_mapping(cls.__name__, {k: v.value for k, v in data.items()})


TemperatureGradient = GradientValues[Temperature.Celsius](
	name='TemperatureGradient',
	freezing=(-10, '#94B7FF'),
	cold=(7, '#B2CBFF'),
	chilly=(12, '#F2F2FF'),
	comfortableStart=(17, '#F2F2FF'),
	comfortable=(22, '#FFFEFA'),
	hot=(28, '#ffb75d'),
	veryHot=(33, '#FF9F46'),
	veryVeryHot=(37.5, '#FF571D'),
	extreme=(40, '#f6f0f6')
)

PrecipitationProbabilityGradient = GradientValues[Probability](
	name='PrecipitationProbabilityGradient',
	none=(5, '#00c6fb88'),
	Low=(10, '#00c6fb'),
	high=(100, '#005bea'),
)

# Source https://webgradients.com/ 061 Sweet PeriodGet
PrecipitationRateGradient = GradientValues[Hourly[Millimeter]](
	name='PrecipitationRateGradient',
	# none=(0, '#00000000'),
	# noneA=(0.025, '#3f51b144'),
	# noneB=(0.05, '#3f51b188'),
	# noneC=(0.075, '#3f51b1CC'),
	# noneD=(0.1, '#3f51b1ff'),
	none=(0, '#3f51b100'),
	veryLight=(0.2, '#3f51b1'),
	light=(1, '#5a55ae'),
	moderate=(3, '#7b5fac'),
	heavy=(10, '#8f6aae'),
	veryHeavy=(15, '#a86aa4'),
	extreme=(20, '#cc6b8e'),
	storm=(25, '#f18271'),
	hurricane=(30, '#f3a469'),
	tornado=(35, '#f7c978'),
)


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
		self.log.info(f'GraphItemData {self.key} value changed')

		self.axisChanged.announce(Axis.Both, instant=True)

	def refresh(self):
		if self._value is not None:
			self.value.refresh()
		self.__clearAxis(Axis.Both)
		self.__updateTransform(Axis.Both)
		self.graphic.onAxisChange(Axis.Both)
		self.timeframe.invalidate()
		if self.labeled:
			clearCacheAttr(self, 'peaksAndTroughs')
			self.labels.onValueChange(Axis.Both)
		self.log.info(f'GraphItemData[{self.key.name}] refreshed')

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
			if value.value.forecast is not None:
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
				T = np.array([(t.timestamp.timestamp(), t.value.value) for t in T])
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
			y = y*margins.height() + margins.top()
		if x is not None:
			x = x*margins.width() + margins.left()
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
	def plotValues(self) -> [QPointF]:
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
		tz = LOCAL_TIMEZONE
		dataType = self.dataType
		if {'denominator', 'numerator'}.intersection(dataType.__init__.__annotations__.keys()):
			value = self.value.first.value
			n = type(value.n)
			d = type(value.d)(1)
			return [TimeSeriesItem(self.dataType(n(y), d), timestampToTimezone(x, tz=tz)) for x, y in zip(*self.data)]
		return [TimeSeriesItem(self.dataType(y), timestampToTimezone(x, tz=tz)) for x, y in zip(*self.data)]

	@cached_property
	def list(self):
		if self.value is not None:
			return self.value[self.graph.timeframe.historicalStart:] or []
		else:
			return self.value or []

	@staticmethod
	def smooth_data_np_convolve(arr, span):
		return np.convolve(arr, np.ones(span*2 + 1)/(span*2 + 1), mode="valid")

	@cached_property
	def data(self) -> np.array:
		arr = self.list

		# create new period that covers five pixels
		newPeriod = int(round(self.graph.secondsPerPixel*5))

		xS = np.arange(arr[0].timestamp.timestamp(), arr[-1].timestamp.timestamp(), newPeriod)
		arrL = np.array([(i.timestamp.timestamp(), float(i.value)) for i in arr])

		# remove duplicates x values
		x, y = np.unique(arrL, axis=0).T

		if len(x) == 1:
			return x, y
		# if 'environment.precipitation.precipitation' == str(self.key):
		# 	y *= 10
		# 	print(y.ptp())
		# Interpolate
		interpField = CubicSpline(x, y)
		y = interpField(xS)

		# Smooth
		sf = 8
		kernel = gaussianKernel(sf, sf*2)
		y = np.convolve(y, kernel, mode='valid')

		# Clip values
		if (limits := getattr(self.dataType, 'limits', None)) is not None:
			y = np.clip(y, *limits)

		return xS, y

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
			# TODO: this is currently recursive, fix it
			return max(int(self.length/len(self)), 1)
		totalSeconds = self.value.period.total_seconds()
		return int(totalSeconds/self._multiplier.total_seconds())

	@property
	def multiplierRaw(self) -> int:
		return int(self._multiplier.total_seconds()/60)

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
			'labeled': self.labeled,
			'plot':    self.graphic.state,
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
	_temperatureGradient: Optional[GradientValues] = None
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
			if self._gradient in GradientValues.presets():
				self.__gradient = GradientValues[self._gradient]
		return self.__gradient.toQGradient(plot=self) if self.__gradient is not None else None

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
			'gradient':    self.__gradient,
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
		weight = self.figure.parent.plotLineWeight()*self.scalar
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
		self.gradient.update()
		pen = self.pen()
		brush = QBrush(self.gradient)
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

	def __dir__(self):
		return set(super().__dir__()) - set(dir(QGraphicsItem))


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
				target.length()*factor, target.angle() + 180).translated(p2)
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
					reverseTarget.setLength(reverseTarget.length()*ratio)
				reverseSource = QLineF.fromPolar(
					source.length()*factor, source.angle()).translated(p1)
				sourceAngle = current.angleTo(source)
				if 90 < sourceAngle < 270:
					ratio = abs(np.sin(np.radians(sourceAngle)))
					reverseSource.setLength(reverseSource.length()*ratio)
				path.cubicTo(reverseSource.p2(), reverseTarget.p2(), p2)

		final = QLineF(points[-3], points[-2])
		reverseFinal = QLineF.fromPolar(
			final.length()*factor, final.angle()).translated(final.p2())
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


# class BackgroundImage(QGraphicsPixmapItem):
#
# 	def __init__(self, parent: 'GraphPanel', data: np.array, *args, **kwargs):
# 		self._data = data
# 		self._parent = parent
# 		super(BackgroundImage, self).__init__(*args, **kwargs)
# 		self.setPixmap(self.backgroundImage())
#
# 	def updateItem(self):
# 		print('update background image')
# 		self.setPixmap(self.backgroundImage())
#
# 	@property
# 	def parent(self):
# 		return self._parent
#
# 	def backgroundImage(self) -> QPixmap:
# 		LightImage = self.image()
# 		img = Image.fromarray(np.uint8(LightImage)).convert('RGBA')
# 		img = img.resize((self.parent.width, self.parent.height))
# 		qim = ImageQt(img)
#
# 	def gen(self, size):
# 		print('gen image')
# 		l = self.parent.height
#
# 		u = int(l*.2)
# 		# up = np.linspace((-np.pi / 2)+2, np.pi * .5, 20)
# 		# y2 = np.linspace(np.pi * .5, np.pi * .5, int(u / 2))
# 		# down = np.linspace(np.pi * .5, np.pi * 1.5, int(u * 2.5))
#
# 		up = np.logspace(.95, 1, 5)
# 		down = np.logspace(1, 0, u, base=10)
#
# 		y = normalize(np.concatenate((up, down)))
# 		x = np.linspace(0, 1, 272)
# 		y2 = np.zeros(size)
# 		y = np.concatenate((y, y2))
# 		return y
#
# 	def image(self):
# 		raw = normalize(self._data)
# 		raw = np.outer(np.ones(len(raw)), raw)
# 		# raw = np.flip(raw)
#
# 		fade = .3
#
# 		# raw = self.solarColorMap(raw)
# 		scale = 1/len(raw)
# 		rr = self.gen(len(raw))
# 		for x in range(0, len(raw)):
# 			raw[x] = raw[x]*rr[x]
# 		# if x < len(raw) * .1:
# 		# 	raw[x] *= scale * x *10
# 		# if x < len(raw) * fade:
# 		# 	raw[x] *= 1 - (scale * x) * (1/fade)
# 		# else:
# 		# 	raw[x] = 0
#
# 		opacity = .9
# 		raw *= 255*opacity
# 		raw = raw.astype(np.uint8)
#
# 		return raw


# Section Plot Text


class PlotText(Text):
	baseLabelRelativeHeight = 0.3
	idealTextSize: Centimeter = Centimeter(.75)
	shadow = SoftShadow

	def __init__(self, *args, **kwargs):
		super(PlotText, self).__init__(*args, **kwargs)
		if isinstance(self.parent, GraphItemData):
			self.setParentItem(self.parent.figure)
			self.graph = self.parent.figure.graph
		elif graph := kwargs.get('graph', None):
			self.graph = graph
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

	# @property
	# def limitRect(self) -> QRectF:
	# 	rect = QRectF(0, 0, 200, self.parent.graph.height()*self.baseLabelRelativeHeight)
	# 	rect.moveCenter(self.boundingRect().center())
	# 	return rect

	@property
	def allowedWidth(self):
		return 400

	@property
	def limitRect(self) -> QRectF:
		global qApp
		heightInchs = self.idealTextSize.inch
		dpi = qApp.primaryScreen().physicalDotsPerInch()
		physicalHeight = heightInchs*dpi  # * t.inverted()[0].m11()

		wt = self.worldTransform()
		# wt = QTransform()
		rect = QRectF(0, 0, self.allowedWidth/wt.m11(), physicalHeight/wt.m22())
		rect.moveCenter(self.boundingRect().center())
		return rect

	def paint(self, painter: QPainter, option, widget=None):
		# keep the text visible as long as the center is
		sRect = self.sceneBoundingRect()
		grRect = self.graph.sceneBoundingRect()
		if not grRect.contains(sRect):
			if grRect.contains(sRect.center()):
				subRect = grRect.intersected(sRect)
				relativePos = subRect.center() - sRect.center()
				if relativePos.x() > 0:
					diff = subRect.topLeft() - sRect.topLeft()
				else:
					diff = subRect.topRight() - sRect.topRight()
				painter.translate(diff*0.3)
				fract = abs(diff.x())/(sRect.width()/2)
				painter.setOpacity(1 - fract)
				painter.scale(1 - fract*0.2, 1 - fract*0.2)

			else:
				return

		super(PlotText, self).paint(painter, option, widget)


class PeakTroughLabel(PlotText):
	_scaleSelection = min
	offset = 15
	# baseLabelRelativeHeight = 0.075
	idealTextSize: Centimeter = Centimeter(.9)
	index: int

	def __init__(self, parent: 'PlotLabels', value: 'PeakTroughData'):
		self.peakList = parent
		super(PeakTroughLabel, self).__init__(parent=parent.labels, graph=parent.data.graph)
		self.value = value
		# self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
		parent.labels.addToGroup(self)
		self.setParentItem(parent.labels)

	# def updateTransform(self):
	# 	if self._value is not None and self._value.isPeak:
	# 		self.moveBy(0, -self.offset)
	# 	else:
	# 		self.moveBy(0, self.offset)

	@property
	def limitRect(self) -> QRectF:
		return super(PeakTroughLabel, self).limitRect

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

	@property
	def index(self):
		return self.__index

	@index.setter
	def index(self, value):
		self.__index = value

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

	def setPos(self, pos: QPointF):
		if self._value is not None and self._value.isPeak:
			pos.setY(pos.y() - self.offset)
		else:
			pos.setY(pos.y() + self.offset)
		super(PlotText, self).setPos(pos)

		self.updateTransform()


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
		while hasattr(self.value, 'value'):
			self.value = self.value.value
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
					item.graphic.index = i
					item.graphic.setPos(values.at(i))
					item.graphic.refresh()
					alignment = AlignmentFlag.Bottom if item.isPeak else AlignmentFlag.Top
					item.graphic.setAlignment(alignment)
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

		else:
			self.labels.hide()

	def quickSet(self):
		values = self.values
		firstItem = self[0].graphic
		# font = QFont(firstItem.font().family(), self.figure.parent.fontSize * firstItem.scalar)
		for i, item in enumerate(self):
			item.graphic.index = i
			item.graphic.setPos(values.at(i))
			item.graphic.refresh()

	# cols = item.graphic.collidingItems(Qt.ItemSelectionMode.IntersectsItemBoundingRect)
	# for i in cols:
	# 	if isinstance(i, PeakTroughLabel):
	# 		i.hide()

	# def quickSetDisplayed(self):
	# 	boundingRect = self.figure.graph.proxy.boundingRect()
	# 	for item in (i.graphic for i in self if boundingRect.contains(self.values.at(i.graphic.index))):
	# 		itemRect = self.figure.graph.proxy.mapRectFromItem(item, item.boundingRect())
	# 		leftDiff = itemRect.left() - boundingRect.left()
	# 		rightDiff = boundingRect.right() - itemRect.right()
	# 		xPos = self.values.at(item.index).x()
	# 		if leftDiff <= 0:
	# 			item.setPos(xPos - leftDiff, item.pos().y())
	# 		elif rightDiff <= 0:
	# 			item.setPos(xPos + rightDiff, item.pos().y())
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
	return args[1]

from platform import system as syscheck
class TimeStampText(PlotText):
	formatID: int
	defaultFormatID = 3
	formatStrings = ['%H:%M:%S.%f', '%H:%M:%S', '%H:%M', f'%{"-" if syscheck() != "Windows" else "#"}I%p', '%A', '%a']
	scalar = 1
	displayScale = 1
	baseLabelRelativeHeight = 0.1
	_scaleSelection = useHeight
	idealTextSize: Centimeter = Centimeter(0.5)

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
		self._value = timestamp
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

	# def updateTransform(self, *args):
	# 	rect = self.boundingRect()
	# 	# rect.setHeight(self._fm.ascent())
	# 	# if rect.height() < self._fm.height():
	# 	# 	fmHeight = self._fm.height()
	# 	# 	diff = fmHeight - rect.height()
	# 	# 	rect.setBottom(rect.bottom() + diff)
	# 	super(TimeStampText, self).updateTransform(rect)

	@property
	def allowedWidth(self) -> float:
		return self.spread.total_seconds()*self.graph.pixelsPerHour/3600

	def setZValue(self, z: float) -> None:
		super(Text, self).setZValue(z)

	# def setFont(self, font: Union[QFont, str]):
	# 	# self.prepareGeometryChange()
	# 	# clearCacheAttr(self, 'textRect')
	# 	if font is None:
	# 		font = QFont(defaultFont)
	# 	# elif isinstance(font, str):
	# 	# 	font = QFont(font)
	# 	# elif isinstance(font, QFont):
	# 	# 	font = font
	# 	# else:
	# 	# 	font = QFont(font)
	# 	# font.setPointSizeF(self.preferredFontSize())
	# 	self._fm = QFontMetricsF(font)
	# 	font.setPointSizeF(16)
	# 	self._font = font

	def preferredFontSize(self) -> float:
		dpi = (qApp.activeWindow().screen().logicalDotsPerInch()
		       if qApp.activeWindow() is not None
		       else qApp.desktop().logicalDpiY())
		return float(self.idealTextSize.inch)*dpi/72

	def boundingRect(self) -> QRectF:
		if self._textRect:
			return self._textRect
		rect = super().boundingRect()
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
		start = datetime.now(tz=LOCAL_TIMEZONE)
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


class HourLabels(dict[datetime, TimeStampText]):
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
		self.refresh()
		self.update()
		if axis & Axis.X:
			pass

	def onAxisTransform(self, axis: Axis):
		if axis & Axis.X:
			self.refresh()
			self.update()

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
				marker.refresh()
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
			for i in range(len(markers), totalHours):
				self[start + timedelta(hours=i)]
		for i, marker in enumerate(markers):
			marker.value = start + timedelta(hours=i)
			marker.refresh()


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
		self.scene().views()[0].resizeFinished.connect(self.onFrameChange)

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
		return self.graph.proxy.rect()
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


class GraphPanel(Panel):
	isEmpty = False
	figures: List['Figure']
	timeframe: TimeFrameWindow
	_acceptsChildren: bool = False
	graphZoom: GraphZoom
	log = LevityGUILog.getChild('Graph')
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

		self.setFlag(self.ItemClipsChildrenToShape, True)
		self.setFlag(self.ItemClipsToShape, True)

		# self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)

		self.movable = False

	@Slot(Axis)
	def onAxisChange(self, axis: Axis):
		if axis & Axis.X:
			clearCacheAttr(self, 'timescalar', 'contentsTimespan', 'contentsMaxTime', 'contentsMinTime, plots, annotatedPlots')
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
		updateFrequency = Millisecond(self.msPerPixel).minute
		self.log.debug(f"Will now update every {updateFrequency} {type(updateFrequency).__name__.lower()}s")
		self.syncTimer.start()

	def syncDisplay(self):
		self.proxy.snapToTime(self.timeframe.displayPosition)

	def timeToX(self, time: datetime):
		pass

	def refresh(self):
		for figure in self.figures:
			figure.refresh()

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
		hour = self.timeframe.rangeSeconds/60/60
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
		return min(max(self.rect().height()*0.1, 30, min(self.rect().width()*0.06, self.rect().height()*.2)), 100)

	def plotLineWeight(self) -> float:
		weight = self.rect().height()*golden*0.005
		weight = weight if weight > 8 else 8.0
		return weight

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemTransformHasChanged:
			self.signals.transformChanged.emit(value)
		if change == QGraphicsItem.ItemChildAddedChange:
			if isinstance(value, (Incrementer, IncrementerGroup)):
				value.setZValue(10000)
			elif isinstance(value, Figure):
				clearCacheAttr(self, 'plots')
				clearCacheAttr(self, 'annotatedPlots')

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

	@cached_property
	def plots(self) -> List[GraphItemData]:
		# return a flat list of all the plots from all the figures
		return [plotList for figure in self.figures for plotList in figure.plotData.values()]

	@cached_property
	def annotatedPlots(self) -> List[GraphItemData]:
		return [plot for plot in self.plots if plot.labeled]


class CurrentTimeIndicator(QGraphicsLineItem):

	def __init__(self, display: 'GraphProxy', *args, **kwargs):
		self.display = display
		baseClock.sync.connect(self.updateItem)
		super(CurrentTimeIndicator, self).__init__(*args, **kwargs)

	def updateItem(self):
		now = datetime.now(tz=LOCAL_TIMEZONE)
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
			differance = x - datetime.now(tz=LOCAL_TIMEZONE)
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

	@property
	def polygon(self) -> QPolygonF:
		rect = self.boundingRect()
		return QPolygonF([rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()])

	# def pos(self):
	# 	return self.pos()

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemPositionChange:
			value = self.clampPoint(value)
		# for plot in self.graph.annotatedPlots:
		# 	if not plot.hasData:
		# 		continue
		# 	plot.labels.quickSetDisplayed()
		return super(GraphProxy, self).itemChange(change, value)

	@property
	def currentTimeFrame(self) -> DateTimeRange:
		visibleRect = self.boundingRect()
		beginningOffsetSeconds = visibleRect.left()/self.pixelsPerSecond
		endOffsetSeconds = visibleRect.right()/self.pixelsPerSecond
		return DateTimeRange(timedelta(seconds=beginningOffsetSeconds), timedelta(seconds=endOffsetSeconds))

	def contentsWidth(self):
		return self.graph.dataWidth

	def contentsX(self):
		return 0

	def clampPoint(self, value):
		maxX = -self.graph.timeframe.lookback.total_seconds()*self.graph.pixelsPerSecond
		maxY = self.graph.rect().bottom() - self.rect().height()
		minX = self.graph.rect().right() - self.contentsWidth()
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
		x = self.xForTime(datetime.now(tz=LOCAL_TIMEZONE))
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
		self.upperLimit = kwargs.pop('max', None)
		self.lowerLimit = kwargs.pop('min', None)

		if margins is None:
			margins = {'left': 0, 'top': 0.1, 'right': 0, 'bottom': 0.1}

		if 'geometry' not in kwargs:
			kwargs['geometry'] = {'size': {'width': 1.0, 'height': 1.0}, 'position': {'x': 0, 'y': 0}, 'absolute': False}
		self.syncTimer = QTimer(singleShot=False, interval=5000)
		self.axisTransformed = AxisSignal(self)
		super(Figure, self).__init__(parent=parent, margins=margins, **kwargs)
		self._parent = parent

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

	@Panel.parent.getter
	def parent(self) -> Union['Panel', 'LevityScene']:
		parent = self.parentItem() or super().parent
		if isinstance(parent, QGraphicsItemGroup):
			return parent.parentItem()
		return parent

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
			plot.refresh()

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
		clearCacheAttr(self.graph, 'plots', 'annotatedPlots')

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
			return self.figureTimeRangeMax.total_seconds()/r*self.frameRect.width()
		return self.frameRect.width()

	@property
	def contentsX(self) -> float:
		return self.graph.timeframe.lookback.total_seconds()/3600*self.graph.pixelsPerHour
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
		return self.sharedKey.name
		a = list(set([item.key for item in self.plotData.values()]))
		if len(a) > 1:
			name = a[0]
			for i in a[1:]:
				name = name & i
			return name.name
		else:
			return a[0].name

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

	# def itemChange(self, change, value):
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
	# return super(Figure, self).itemChange(change, value)

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
			return xLimit - (xLimit*np.ma.log(xLimit/x))

		# return xLimit * np.ma.log(xLimit / x)
		if v > M:
			m = int(M)
			M = elastic(v, M)
		elif v < m:
			m = elastic(v, m)
		return min(max(m, v), M)

		return x

	@property
	def state(self):
		state = {
			'figure':  self.name,
			**{str(k): v for k, v in self.plotData.items()},
			'margins': self.margins,
		}
		if self.upperLimit is not None:
			state['max'] = self.upperLimit
		if self.lowerLimit is not None:
			state['min'] = self.lowerLimit
		return state

	def shape(self):
		return self.graph.proxy.shape()
