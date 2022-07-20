import asyncio
import operator
import platform
import re
from abc import abstractmethod

from builtins import isinstance
from json import loads
from types import SimpleNamespace

import numpy as np
from datetime import datetime, timedelta
from enum import Enum
from functools import cached_property, reduce, partial

from itertools import chain, zip_longest
from math import inf, prod, sqrt
from PySide2.QtCore import QLineF, QObject, QPoint, QPointF, QRectF, Qt, QTimer, Signal, Slot, QRect, QDateTime, QSizeF
from PySide2.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPainterPathStroker, QPen, QPolygonF, QTransform, QCursor, QPixmap, QPixmapCache, QKeyEvent, QFontMetricsF
from PySide2.QtWidgets import (QGraphicsDropShadowEffect, QGraphicsItem, QGraphicsItemGroup, QGraphicsLineItem, QGraphicsPathItem,
                               QGraphicsRectItem, QGraphicsSceneDragDropEvent, QGraphicsSceneHoverEvent, QGraphicsSceneMouseEvent, QGraphicsSceneWheelEvent, QToolTip, QMenu, QStyleOptionGraphicsItem, QGraphicsPixmapItem, QWidget,
                               QGraphicsEffect)

from qasync import asyncSlot, QApplication
from rich.repr import auto
from scipy.constants import golden
from scipy.interpolate import CubicSpline, interp1d
from typing import Callable, ClassVar, Iterable, List, Optional, overload, Tuple, Union, Any, Type, TypeVar, Dict, ForwardRef, Protocol, runtime_checkable
from uuid import uuid4

from WeatherUnits import Measurement, Temperature, Probability, Length, Time, DerivedMeasurement
from WeatherUnits.derived.precipitation import Hourly
from WeatherUnits.time_.time import Millisecond, Second
from WeatherUnits.length import Centimeter, Millimeter, Inch
from WeatherUnits.derived.rate import MilesPerHour
from WeatherUnits.others.light import Lux, Irradiance
from yaml import SafeDumper

from LevityDash.lib.plugins.observation import TimeAwareValue, TimeSeriesItem
from LevityDash.lib.plugins import Plugins, Plugin, Container
from LevityDash.lib.plugins.plugin import AnySource, SomePlugin
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.dispatcher import ValueDirectory, MultiSourceContainer
from LevityDash.lib.ui.frontends.PySide import app
from LevityDash.lib.ui.frontends.PySide.Modules.Displays import Text
from LevityDash.lib.ui.frontends.PySide.Modules.Handles.MarginHandles import FigureHandles
from LevityDash.lib.ui.frontends.PySide.Modules.Handles.Incrementer import Incrementer, IncrementerGroup
from LevityDash.lib.ui.frontends.PySide.Modules.Handles.Timeframe import GraphZoom
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel, NonInteractivePanel
from LevityDash.lib.utils.shared import _Panel, LOCAL_TIMEZONE, Unset, getOrSet, closestStringInList, camelCase, joinCase, Numeric, now, numberRegex, BusyContext
from LevityDash.lib.stateful import DefaultGroup, StateProperty, Stateful
from LevityDash.lib.utils.various import DateTimeRange
from LevityDash.lib.ui.frontends.PySide.utils import DisplayType, GraphicsItemSignals, modifyTransformValues, colorPalette, addCrosshair, EffectPainter, SoftShadow, addRect, DebugSwitch, DebugPaint
from LevityDash.lib.utils.data import AxisMetaData, DataTimeRange, findPeaksAndTroughs, TimeFrameWindow, gaussianKernel
from LevityDash.lib.utils.shared import clamp, clearCacheAttr, disconnectSignal, timestampToTimezone
from LevityDash.lib.utils.geometry import AlignmentFlag, Axis, Margins, Dimension, Size, DisplayPosition, Alignment
from LevityDash.lib.plugins.observation import MeasurementTimeSeries
from LevityDash.lib.config import DATETIME_NO_ZERO_CHAR
from time import time, perf_counter, sleep
from ..Menus import BaseContextMenu, SourceMenu
from ... import UILogger

from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from LevityDash.lib.ui.frontends.PySide.app import LevityScene

log = UILogger.getChild('Graph')

__all__ = ['GraphItemData', 'Figure', 'GraphPanel']

loop = asyncio.get_running_loop()


class Color:
	__slots__ = ('__red', '__green', '__blue', '__alpha')
	__red: int
	__green: int
	__blue: int
	__alpha: int

	def __init__(self, color: str | Tuple[int | float, ...]):
		self.__validate(color)

	def __validate(self, color: str | Tuple[int | float, ...]):
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
			try:
				unitType = self.plot.data.dataType
				values = [unitType(t.value) for t in self.values.list]
			except Exception:
				values = [t.value for t in self.values.list]
			return np.array(values)

		@property
		def gradientPoints(self) -> Tuple[QPoint, QPoint]:
			T = (self.localized - self.plot.data.data[1].min())/(self.plot.data.data[1].ptp() or 1)
			t = self.plot.data.combinedTransform*self.plot.scene().view.transform()
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

	def __init__(self, name: str = None, *color, **colors: Tuple[int | float, Color | str | Tuple[int | float]]):
		super().__init__()
		itemType = self.itemCls()
		for key, item in colors.items():
			self[key] = itemType(*item)
		for color in color:
			match color:
				case int(p) | float(p), Color(c) | str(c) | tuple(c):
					self[str(c)] = itemType(p, c)
				case _:
					raise TypeError(f'{color} is not a valid color')

	@StateProperty(unwrap=True)
	def data(self) -> Dict:
		return self

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
	veryHot=(30, '#f3a469'),
	a=(32, '#f18271'),
	b=(38, '#cc6b8e'),
	c=(40, '#a86aa4'),
	d=(50, '#8f6aae'),
)

FabledSunsetGradientLux = GradientValues[Lux](
	'FabledSunsetGradientLux',
	(0, '#23155700'),
	(3600, '#44107A55'),
	(6000, '#8F6AAEAA '),
	(7200, '#CC6B8E'),
	(10800, '#F3A469'),
	(18000, '#F7B731'),
	(36000, '#FFFEFA'),
)

FabledSunsetGradientWattsPerSquareMeter = GradientValues[Irradiance](
	'FabledSunsetGradientWattsPerSquareMeter',
	(0, '#23155700'),
	(30, '#44107A55'),
	(50, '#8F6AAEAA '),
	(60, '#CC6B8E'),
	(90, '#F3A469'),
	(150, '#F7B731'),
	(300, '#FFFEFA'),
)
RipeMalinkaGradient = GradientValues[MilesPerHour](
	'RipeMalinkaGradient',
	(0, '#f093fb'),
	(10, '#f5576c'),
	(20, '#f7b731'),
	(30, '#f9f64f'),
	(40, '#a9f7a9'),
	(50, '#5ff781'),
	(60, '#00e756'),
	(70, '#00b7eb'),
	(80, '#0052f3'),
	(90, '#0f00f9'),
	(100, '#7b00d4'),
)

PrecipitationProbabilityGradient = GradientValues[Probability](
	name='PrecipitationProbabilityGradient',
	none=(0, '#00c6fb00'),
	Low=(.10, '#00c6fb'),
	high=(1, '#005bea'),
	one=(1, '#7b00d4'),
)

# Source https://webgradients.com/ 061 Sweet PeriodGet
PrecipitationRateGradient = GradientValues[Hourly[Millimeter]](
	name='PrecipitationRateGradient',
	none=(0.1, '#3f51b100'),
	veryLight=(0.2, '#3f51b1'),
	light=(1, '#5a55ae'),
	moderate=(1.5, '#7b5fac'),
	heavy=(3, '#8f6aae'),
	veryHeavy=(5, '#a86aa4'),
	extreme=(12, '#cc6b8e'),
	storm=(24, '#f18271'),
	hurricane=(30, '#f3a469'),
	tornado=(35, '#f7c978'),
)


# Section Surface
@DebugPaint
class Surface(QGraphicsItemGroup):
	if TYPE_CHECKING:
		def scene(self) -> LevityScene: ...

	def __init__(self, parent: QGraphicsItem):
		super().__init__(parent)

	def boundingRect(self):
		return self.parentItem().rect()

	def boundingRegion(self, itemToDeviceTransform):
		return self.parentItem().boundingRegion(itemToDeviceTransform)

	def shape(self) -> QPainterPath:
		return self.parentItem().shape()

	def _debug_paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget):
		self._normal_paint(painter, option, widget)
		addRect(painter, self.boundingRect(), color=self._debug_paint_color, offset=1)


X_ = TypeVar('X_', int, float, np.ndarray)
Y_ = TypeVar('Y_', int, float, np.ndarray)
Array_ = TypeVar('Array_')
_PlotLabels = ForwardRef('PlotLabels')


# Section GraphItemData

@auto
class GraphItemData(QObject, Stateful, tag=...):
	_source: Plugin
	axisChanged: 'AxisSignal'

	lastUpdate: datetime

	_smooth: bool
	_figure: 'Figure'
	_interpolate: bool
	_pathType: 'PathType'
	_graphic: Optional[QGraphicsItem]
	__normalX: np.array
	__normalY: np.array
	_key: CategoryItem
	_container: MultiSourceContainer
	__connectedContainer: Optional[Container]
	__connectedTimeseries: Optional[MeasurementTimeSeries]
	timeseries: MeasurementTimeSeries
	_labels: 'PlotLabels'
	_resolution: int
	__connectedTimeseries: MeasurementTimeSeries | None

	__exclude__ = {'z'}

	log = log.getChild('GraphItemData')

	def __init__(self, parent: 'Figure' = None, **kwargs):
		self.pendingUpdate = None
		self._preferredSourceName = 'any'
		self.__pendingActions = []
		self._waitingForPreferredSourceTimeout = None
		self.__connectedTimeseries = None
		self.__connectedContainer = None
		super(GraphItemData, self).__init__()
		self._set_state_items_ = set()
		kwargs = Stateful.prep_init(self, kwargs)
		self.__init_defaults__()
		self.figure = parent
		self.state = kwargs
		parent.scene().view.loadingFinished.connect(self.waitForLoadComplete)
		parent.scene().view.resizeFinished.connect(self.onResizeDone)

	def __init_defaults__(self):
		self.__lastUpdate = None
		self.axisChanged = AxisSignal(self)
		self.uuid = uuid4()

		self.__normalX = None
		self.__normalY = None

	def __hash__(self):
		return hash(self.uuid)

	def __str__(self):
		return f'Plot[{self.key.name}]'

	@asyncSlot()
	async def onResizeDone(self):
		self.graphic.onResizeDone()

	# Section .events
	@asyncSlot()
	async def waitForLoadComplete(self):
		if not len(self.__pendingActions):
			return
		await asyncio.gather(*self.__pendingActions)
		self.__pendingActions.clear()
		try:
			self.figure.scene().view.loadingFinished.disconnect(self.waitForLoadComplete)
		except Exception:
			pass

	@asyncSlot()
	async def __onAxisTransform(self, axis: Axis):
		"""
		Called when given the signal that the parent figure's axis spread has changed
		either due to a graph zoom or figure margin change.

		Parameters
		----------
		axis: Axis
			The axis that has been transformed
		"""
		if not self.hasData:
			return
		# self.__updateTransform(axis)
		self.graphic.onAxisTransform(axis)
		if self.labels.enabled:
			self.labels.onAxisTransform(axis)

	def connectTimeseries(self, container: Container):
		try:
			self.pendingUpdate.cancel()
		except AttributeError:
			pass
		self.pendingUpdate = None
		try:
			disconnected = self.disconnectTimeseries()
		except ValueError:
			disconnected = True
		if not disconnected:
			raise ValueError('Failed to disconnect from existing timeseries')

		with container.timeseries.signals as signal:
			connected = signal.connectSlot(self.__onValueChange)
			if connected:
				self.__connectedContainer = container
				self.__connectedTimeseries = container.timeseries
				self.pendingUpdate = loop.call_soon(self.__onValueChange)
				log.debug(f'GraphItem {self.key.name} connected to {self.__connectedTimeseries}')
			else:
				log.warning(f'GraphItem {self.key.name} failed to connect to {container}')
		return connected

	def disconnectTimeseries(self) -> bool:
		if self.__connectedTimeseries is not None:
			disconnected = self.__connectedTimeseries.signals.disconnectSlot(self.__onValueChange)
			if disconnected:
				log.debug(f'GraphItem {self.key.name} disconnected from {self.__connectedTimeseries}')
				self.__connectedTimeseries = None
				self.__connectedContainer = None
				self.__clearAxis(Axis.Both, rebuild=False)
				self.__clearCache()
			else:
				log.warning(f'GraphItem {self.key.name} failed to disconnect from {self.__connectedTimeseries}')
			return disconnected
		raise ValueError('No timeseries connected')

	@asyncSlot()
	async def __onValueChange(self):
		"""
		Called when the value of the timeseries has changed.  Alerts parent figure
		that its values have changed.  The figure briefly waits for other GraphItemData to
		announce their own changes before announcing that the transform needs to be updated.

		Note: This slot should not update the transform, it should wait for the parent figure
		to finish collecting announcements from sibling GraphItemData.
		"""
		if not self.hasData:
			return
		if self.pendingUpdate is not None:
			try:
				self.pendingUpdate.cancel()
			except Exception:
				pass

		self.log.info(f'Updating GraphItemData[{self.key.name}]')
		self.graph.onAxisChange(Axis.Both)
		self.__clearAxis(Axis.Both)
		self.graphic.onDataChange()
		if self.labels.enabled:
			clearCacheAttr(self, 'peaksAndTroughs')
			loop.call_soon(self.labels.onValueChange, Axis.Both)
		self.__lastUpdate = now()

		self.axisChanged.announce(Axis.Both, instant=True)

	@asyncSlot(MultiSourceContainer)
	async def listenForKey(self, container: MultiSourceContainer):
		self.container = container
		ValueDirectory.getChannel(self.key).disconnectSlot(self.listenForKey)

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

	def __clearCache(self):
		clearCacheAttr(self, 'data', 'list', 'smoothed')

	def refresh(self):
		if self.container is None:
			return
		if not self.hasData:
			if self.container.getTimeseries(self.key) is not None:
				asyncio.create_task(self.setContainer('refresh'))
			return
		print('refreshing', self.key)
		self.timeseries.refresh()
		self.__clearCache()
		self.__clearAxis(Axis.Both)
		self.graphic.onDataChange()
		if self.labels.enabled:
			clearCacheAttr(self, 'peaksAndTroughs')
			self.labels.onValueChange(Axis.Both)
		self.log.info(f'GraphItemData[{self.key.name}] refreshed')

	@property
	def figure(self) -> 'Figure':
		return self._figure

	@figure.setter
	def figure(self, figure: 'Figure'):
		# if item is already assigned to a figure, disconnect the signals and
		# remove the item from the figure's list of items
		if existingFigure := getattr(self, '_figure', None):
			existingFigure.axisChanged.disconnectSlot(self.__onAxisTransform)
			self.axisChanged.disconnectSlot(existingFigure.onGraphItemUpdate)
			existingFigure.removeItem(self)

		self._figure = figure
		if graphic := getattr(self, '_graphic', None) is not None:
			graphic.setParentItem(figure)

		# Connect slot that informs the figure to update the transform
		self.axisChanged.connectSlot(self._figure.onGraphItemUpdate)

		# Connect figures signals to update the local transform
		self._figure.axisTransformed.connectSlot(self.__onAxisTransform)

	@property
	def graph(self) -> 'GraphPanel':
		return self._figure.graph

	# Section .properties

	@StateProperty(dependencies={'plot'})
	def z(self) -> int:
		return self.graphic.zValue()

	@z.setter
	def z(self, z: int):
		self.graphic.setZValue(z)

	@z.encode
	def z(z: float) -> int:
		return round(z)

	@z.condition
	def z(self) -> bool:
		return len(self.figure.plotData) > 1

	@StateProperty(key='plot')
	def graphic(self) -> 'Plot':
		return self._graphic

	@graphic.setter
	def graphic(self, value):
		self._graphic = value
		if figure := getattr(self, '_figure', None):
			self._graphic.setParentItem(figure)

	@graphic.decode
	def graphic(self, value):
		if isinstance(value, dict):
			if existingGraphic := getattr(self, '_graphic', None):
				existingGraphic.state = value
				return {}
			return LinePlot(self, **value)
		return value

	@StateProperty(sortOrder=2, default=Stateful, dependencies={'labeled'}, allowNone=False)
	def labels(self) -> 'PlotLabels':
		return self._labels

	@labels.setter
	def labels(self, value: 'PlotLabels'):
		self._labels = value

	@labels.decode
	def labels(self, state: bool) -> dict:
		if isinstance(state, bool):
			return {'enabled': state}

	@labels.factory
	def labels(self):
		return PlotLabels(source=self, surface=Surface(parent=self.figure))

	@labels.after
	def labels(self):
		labels = self.labels
		if labels.enabled:
			if labels.surface.parentItem() is None:
				labels.surface.setParentItem(self.figure)
		else:
			scene = self.figure.scene()
			labels.surface.setParentItem(None)
			scene.removeItem(labels.surface)

	@StateProperty(default=True, allowNone=False, after=refresh)
	def interpolate(self) -> bool:
		return getattr(self, '_interpolate', True)

	@interpolate.setter
	def interpolate(self, value):
		self._interpolate = value

	@StateProperty(default=True, allowNone=False, after=refresh)
	def smooth(self) -> bool:
		return getattr(self, '_smooth', True)

	@smooth.setter
	def smooth(self, value):
		self._smooth = value

	@StateProperty(default=1.0, allowNone=False, after=refresh)
	def smoothingStrength(self) -> float:
		return getattr(self, '_smoothingStrength', 1.0)

	@smoothingStrength.setter
	def smoothingStrength(self, value: float | int):
		self._smoothingStrength = value

	@smoothingStrength.condition
	def smoothingStrength(self):
		return self.smooth

	@StateProperty(exclude=True, dependencies={'labeled', 'interpolate', 'smooth', 'smoothingStrength', 'source'})
	def key(self) -> CategoryItem:
		return self._key

	@key.setter
	def key(self, value):
		if isinstance(value, str):
			value = CategoryItem(value)
		if getattr(self, '_key', Unset) == value:
			return
		self._key = value

	@key.after
	def key(self):
		self.container = ValueDirectory.getContainer(self._key, None)

	@StateProperty(default=AnySource, dependencies={'labeled', 'interpolate', 'smooth', 'smoothingStrength'}, values=Plugins.plugins)
	def source(self) -> Plugin | SomePlugin:
		return getattr(self, '_source', AnySource)

	@source.setter
	def source(self, value: Plugin):
		self._source = value or AnySource

	@source.after
	def source(self):
		if getattr(self, '_container', None):
			asyncio.create_task(self.setContainer('Source Change Menu'))

	@source.encode
	def source(value: Plugin) -> str:
		return getattr(value, 'name', 'any')

	@source.decode
	def source(self, value: str) -> Plugin:
		source = Plugins.get(value, AnySource)
		self._preferredSourceName = value
		if source is None:
			log.info(f'{value} is not a valid source or the plugin is not Loaded')
		return source

	@property
	def currentSource(self) -> Plugin | None:
		return getattr(self.__connectedContainer, 'source', None)

	def changeSource(self, source: Plugin):
		if self.currentSource is source:
			return
		self.source = source

	@property
	def connectedContainer(self) -> Container | None:
		return self.__connectedContainer

	@property
	def timeseries(self) -> MeasurementTimeSeries | None:
		return self.__connectedTimeseries

	@property
	def container(self) -> MultiSourceContainer | None:
		return getattr(self, '_container', None)

	@container.setter
	def container(self, container: MultiSourceContainer):
		# TODO: Rename this property to 'container' and add a new property 'timeseries'
		# TODO: Figure out why windSpeed is not being set

		if container is None:
			ValueDirectory.notifyWhenKeyAdded(self.key, self.setContainer())
			return
		if self.container is container:
			return
		self._container = container

		if self._waitingForPreferredSourceTimeout is not None:
			self._waitingForPreferredSourceTimeout.cancel()

		loop.create_task(self.setContainer())

	async def setContainer(self, trigger=None) -> None:
		if self.figure.scene().view.status != 'Ready':
			self.__pendingActions.append(self.setContainer('pendingActions'))
			return

		multiSourceContainer = self.container or ValueDirectory.getContainer(self.key, None)
		if multiSourceContainer is None:
			ValueDirectory.notifyWhenKeyAdded(self.key, self.setContainer('notifyWhenAdded'))
			return

		correctSource = False
		timeSeriesContainer = multiSourceContainer.getTimeseries(self.source, strict=True)

		if timeSeriesContainer is None:
			multiSourceContainer.getPreferredSourceContainer(self, self.source, self.setContainer('getPreferredSourceContainer'), timeseriesOnly=True)
		elif timeSeriesContainer.source is self.source or self.source is AnySource:
			correctSource = True

		if correctSource:
			try:
				self._waitingForPreferredSourceTimeout.cancel()
			except AttributeError:
				pass
			self._waitingForPreferredSourceTimeout = None
			self.connectTimeseries(timeSeriesContainer)
			return
		elif timeSeriesContainer is not None:
			multiSourceContainer.getPreferredSourceContainer(self, self.source, self.setContainer('getPreferredSourceContainer'), timeseriesOnly=True)

		if self._waitingForPreferredSourceTimeout is None:
			async def giveupAsync():
				print(f'Giving up waiting for preferred source {self.source.name}[{self.key}]')
				fallbackContainer = multiSourceContainer.getTimeseries(self.source, strict=True)
				if fallbackContainer is None:
					print(f'No fallback container found for {self.source.name}[{self.key}]. '
					      f' Waiting for any timeseries source to become available.')
					multiSourceContainer.getPreferredSourceContainer(self, AnySource, giveupAsync(), timeseriesOnly=True)
					return
				print(f'Using {fallbackContainer!r} instead.')
				self.connectTimeseries(fallbackContainer)

			def giveup():
				loop.create_task(giveupAsync())

			self._waitingForPreferredSourceTimeout = loop.call_later(60, giveup)

	@StateProperty(default=5, allowNone=False, after=refresh)
	def resolution(self) -> int:
		return self._resolution

	@resolution.setter
	def resolution(self, value: int):
		self._resolution = value

	@property
	def hasData(self) -> bool:
		return getattr(self.timeseries, 'hasTimeseries', False)

	def __rich_repr__(self):
		if key := getattr(self, '_key', None):
			yield 'key', key
		lastUpdate = self.lastUpdate
		if lastUpdate is not None:
			updated = (now() - self.lastUpdate).total_seconds()
			if updated < 1:
				yield 'updated', 'just now'
			else:
				relativeTime = Time.Second(updated).auto
				timeValue: int = round(relativeTime)
				timeAgo = f'{timeValue} {type(relativeTime).pluralName.lower() if timeValue != 1 else type(relativeTime).name.lower()} ago'
				yield 'lastUpdate', timeAgo
		else:
			yield 'lastUpdate', 'never'
		if (value := self.timeseries) is not None:
			yield 'plot', self.graphic
			yield 'length', len(value)
			yield 'timeframe', self.timeframe
			yield 'min', min(value)
			yield 'max', max(value)
			yield 'dataType', self.dataType

			if self.currentSource is not None and self.source:
				yield 'source', f'✓ {self.source.name}', self.source
			else:
				yield 'source', value.source.name, self.source

			labels = self.labels
			yield 'labeled', labels.enabled
			if labels.enabled:
				yield 'labels', labels

			interpolate = self.interpolate
			yield 'interpolated', interpolate
			if interpolate:
				yield 'resolution', self.resolution

			smooth = self.smooth
			yield 'smoothed', smooth
			if smooth:
				yield 'smoothingStrength', self.smoothingStrength
		else:
			yield 'uninitialized', True

	# Section .data

	@property
	def lastUpdate(self) -> datetime | None:
		return self.__lastUpdate

	@property
	def dataTransform(self) -> QTransform:
		timeOffset = (self.graph.timeframe.start.timestamp() - self.timeframe.min.timestamp())/self.figure.graph.timeframe.seconds
		t = QTransform()
		graphTimeRange = self.figure.graph.timeframe.rangeSeconds
		if self.plotValues:
			T = (self.data[1] - self.figure.dataValueRange.min)/self.figure.dataValueRange.range
			t.translate(0, T.min())
			t.scale((self.timeframe.range.total_seconds()/graphTimeRange), T.ptp())
		return t

	def __updateTransform(self, axis: Axis):
		xTranslate, yTranslate = None, None
		xScale, yScale = None, None
		if axis & Axis.X:
			xTranslate = (self.timeframe.min.timestamp() - self.figure.figureMinStart.timestamp())/self.figure.graph.timeframe.seconds
		if axis & Axis.Y:
			T = (self.data[1] - self.figure.dataValueRange.min)/self.figure.dataValueRange.range
			yTranslate = T.min()
			yScale = T.ptp()
		modifyTransformValues(self.dataTransform, xTranslate, yTranslate, xScale, yScale)

	@property
	def combinedTransform(self):
		return self.dataTransform*self.figure.figureTransform

	@property
	def visibleOnlyTransform(self):
		timeOffset = (self.timeframe.min - self.figure.graph.timeframe.start).total_seconds()/self.figure.graph.timeframe.seconds
		t = QTransform()
		if self.plotValues:
			start = (self.figure.graph.timeframe.start - self.figure.graph.timeframe.offset).timestamp()
			end = start + self.figure.graph.timeframe.timeframe.total_seconds()
			a = [i for i, j in enumerate(self.data[0]) if start <= j <= end]
			i = min(a)
			j = max(a)
			minMax = self.figure.dataValueRange[i:j]
			T = (self.data[1][i:j] - minMax.min)/minMax.range*(self.figure.dataValueRange.range/minMax.range)
			t.translate(-timeOffset, T.min())
			t.scale(1, T.ptp())
		return t

	@cached_property
	def timeframe(self) -> DataTimeRange:
		return DataTimeRange(self)

	@cached_property
	def peaksAndTroughs(self):
		# TODO: this should not be a cached property
		self.peaks, self.troughs = findPeaksAndTroughs(self.smoothed, spread=timedelta(hours=9))
		return self.peaks, self.troughs

	@staticmethod
	def __parseData(values: Optional[Iterable[TimeAwareValue] | Tuple[X_, Y_]] = None,
		value: Optional[TimeAwareValue | Tuple[X_, Y_]] = None,
		x: Optional[Iterable[X_]] = None,
		y: Optional[Iterable[Y_]] = None,
		axis: Optional[Axis] = None,
	) -> Tuple[X_ | None, Y_ | None]:
		axis = axis or Axis.Both

		if values is not None:
			if any(isinstance(i, TimeAwareValue) for i in values):
				x = {'iter': (int(i.timestamp.timestamp()) for i in values), 'dtype': 'i4'}
				y = {'iter': (float(i.value) for i in values), 'dtype': 'f4'}
			elif any(isinstance(i, tuple) for i in values):
				x = {'iter': (int(i[0]) for i in values), 'dtype': 'i4'}
				y = {'iter': (float(i[1]) for i in values), 'dtype': 'f4'}
			x = np.fromiter(**x) if axis.X & Axis.X else None
			y = np.fromiter(**y) if axis.Y & Axis.Y else None
			return x, y
		elif x is not None and y is not None:
			pass
		elif x is not None:
			x, y = x, None
		elif y is not None:
			x, y = None, y
		elif value is not None:
			if isinstance(value, TimeAwareValue):
				x, y = value.timestamp, value.value
			elif isinstance(value, tuple):
				x, y = value

		if axis == Axis.Both:
			return x, y
		elif axis == Axis.X:
			return x, None
		elif axis == Axis.Y:
			return None, y
		raise ValueError('Invalid axis or data')

	def normalize(self, **data) -> Union[QPointF, list[QPointF]]:
		"""
		:param axis: Vertical or Horizontal
		:return: tuple of normalized points (_values between 0 and 1)
		"""
		x, y = self.__parseData(**data)

		if y is not None:
			y = (y - y.min())/(y.ptp() or 1)
		if x is not None:
			start = self.graph.timeframe.start
			x = (x - start.timestamp())/self.figure.figureTimeRangeMaxMin.total_seconds()
		return x, y

	def normalizeToFrame(self, **data):
		x, y = self.__parseData(**data)

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
	def timeArray(self) -> np.array:
		return self.data[0]

	@cached_property
	def smoothed(self) -> np.array:
		tz = LOCAL_TIMEZONE
		dataType = self.dataType
		if issubclass(dataType, DerivedMeasurement):
			n = dataType.numeratorClass
			d = dataType.denominatorClass(1)
			return [TimeSeriesItem(self.dataType(n(y), d), timestampToTimezone(x, tz=tz)) for x, y in zip(*self.data)]
		return [TimeSeriesItem(self.dataType(y), timestampToTimezone(x, tz=tz)) for x, y in zip(*self.data)]

	@cached_property
	def list(self):
		if self.hasData and len(sliced := self.timeseries[self.graph.timeframe.historicalStart:]):
			return sliced
		return []

	@cached_property
	def data(self) -> np.array:
		# TODO: Add try/except for when the data is not sorted
		arr = self.list

		# create new period that covers five pixels
		newPeriod = int(round(self.graph.secondsPerPixel*self.resolution))

		xS = np.arange(arr[0].timestamp.timestamp(), arr[-1].timestamp.timestamp(), newPeriod)
		arrL = np.array([(i.timestamp.timestamp(), float(i.value)) for i in arr])

		# remove duplicates x values
		x, y = np.unique(arrL, axis=0).T

		if len(x) == 1:
			return x, y
		# Interpolate

		smooth = self.smooth
		interpField = CubicSpline(x, y) if smooth else interp1d(x, y)
		y = interpField(xS)

		# Smooth
		if smooth:
			sf = int(round(40/self.resolution*self.smoothingStrength))
			kernel = gaussianKernel(sf, sf*2)
			y = np.convolve(y, kernel, mode='valid')

		# Clip values
		if (limits := getattr(self.dataType, 'limits', None)) is not None:
			y = np.clip(y, *limits)
		# i, j = 0, 300
		# return xS[i:j], y[i:j]
		return xS, y

	@property
	def dataType(self) -> Type[Measurement] | Type[float] | None:
		return type(self.timeseries.first.value) if self.hasData else None


class PathType(Enum):
	Linear = 0
	Cubic = 2
	Quadratic = 3
	Spline = 4


class PlotTip(QToolTip):
	def __init__(self, parent):
		super().__init__(parent)

	@staticmethod
	def hideText() -> None:
		return


Effect = TypeVar('Effect', bound=QGraphicsEffect)
PlotShadow = SoftShadow


# Section Plot
class Plot(QGraphicsPixmapItem, Stateful):
	""" The graphical plot of GraphItemData.
	All updates are handled by the GraphItemData.
	"""

	_dashPattern: list[int]
	_type: PathType
	figure: 'Figure'
	data: GraphItemData
	_style: Qt.PenStyle
	_weight: float
	pathType: PathType
	_temperatureGradient: Optional[GradientValues] = None
	__useCache: bool = False
	__path: QPainterPath
	effects: Dict[str, Dict[str, Effect | Any]]

	if TYPE_CHECKING:
		def scene(self) -> LevityScene: ...

	def __init__(self, parent: GraphItemData, **kwargs):
		self.renderTask = None
		self.__dataTransformAtRender = QTransform()
		self.__resizeTask = None
		self.__path = QPainterPath()
		self.__pen = QPen()
		self._set_state_items_ = set()
		self._gradientValue = None
		self.data: GraphItemData = parent
		self.figure: 'Figure' = parent.figure
		self.effects = {}
		super().__init__(None)
		self.setParentItem(parent.figure)
		self._normalPath = QPainterPath()
		self._shape = QPainterPath()
		kwargs = self.prep_init(kwargs)
		self.state = kwargs
		self.setAcceptHoverEvents(True)
		self.setParentItem(self.figure)
		self.setFlag(QGraphicsItem.ItemIsMovable, False)
		self.setFlag(QGraphicsItem.ItemClipsToShape, False)
		self.addEffect(PlotShadow, name='shadow')
		self.figure.signals.clicked.connect(self.showToolTip)
		self.setTransformationMode(Qt.SmoothTransformation)
		self.setShapeMode(QGraphicsPixmapItem.BoundingRectShape)
		if self.__useCache:
			self.setCacheMode(QGraphicsItem.ItemCoordinateCache)

	def __rich_repr__(self, **kwargs):
		pathLen = self.path().elementCount()
		# yield the size of the pixmap in megabytes
		yield 'pixmap_size', f'{prod(self.pixmap().size().toTuple())*4/1024/1024:g} MB'
		yield 'minX', f'{self.path().elementAt(0).x:g}'
		yield 'maxX', f'{self.path().elementAt(pathLen - 1).x:g}'
		yield 'minY', f'{self.path().elementAt(0).y:g}'
		yield 'maxY', f'{self.path().elementAt(pathLen - 1).y:g}'
		yield from super(Plot, self).__rich_repr__()

	def setZValue(self, value: int):
		super(Plot, self).setZValue(self.figure.zValue() + 1)

	def addEffect(self, effect: Type[Effect], name: str | None = None, **effectArgs) -> None:
		name = name or effect.__class__.__name__
		self.effects[name] = effect

	# Section .properties

	@StateProperty(default=None, dependencies={'color'}, after=QGraphicsItem.update)
	def gradient(self) -> Optional[GradientValues]:
		if self._gradient:
			return self._gradient

	@gradient.setter
	def gradient(self, value):
		self._gradient = value
		if value:
			self._color = None
			self.updateGradient()

	@gradient.decode
	def gradient(value) -> GradientValues:
		if isinstance(value, GradientValues):
			pass
		elif isinstance(value, str):
			if value in GradientValues.presets():
				value = GradientValues[value]
		return value

	@property
	def gradientQt(self) -> GradientValues.QtGradient:
		if self._gradient:
			return self._gradient.toQGradient(plot=self)

	@StateProperty(default=1.0, after=QGraphicsItem.update)
	def weight(self) -> float:
		return getattr(self, '_weight', 1.0)

	@weight.setter
	def weight(self, value: Union[str, float, int]):
		if not isinstance(value, float):
			value = float(value)
		self._weight = sorted((value, 0.0, 10))[1]

	@weight.encode
	def weight(value: float) -> float:
		return round(value, 3)

	@property
	def weight_px(self) -> float:
		return self.figure.parent.plotLineWeight()*self.weight

	@StateProperty(default=DefaultGroup(colorPalette.windowText().color(), '#ffffff', 'ffffff'), allowNone=False, after=QGraphicsItem.update)
	def color(self) -> QColor:
		if (color := getattr(self, '_color', None)) is None:
			return colorPalette.windowText().color()
		return color

	@color.setter
	def color(self, value):
		self._color = value
		if value:
			self._gradient = None
			pen = self.pen()
			pen.setColor(value)
			self.setPen(pen)

	@color.decode
	def color(self, value):
		match value:
			case str():
				if hexVal := re.findall(r"([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})", value):
					value = QColor(f'#{hexVal[0]}')
				else:
					try:
						value = QColor(value)
					except ValueError:
						UILogger.warning(f'Invalid color: {value} for plot {self.data.name}')
						value = colorPalette.windowText().color()
			case QColor() | None:
				pass
			case Color():
				value = value.toQColor()
			case _:
				raise ValueError(f'Invalid color: {value} for plot {self.data.name}')
		return value

	@color.encode
	def color(value) -> str:
		return value.name().strip('#')

	@color.condition
	def color(self) -> bool:
		return getattr(self, '_gradient', None) is None

	@StateProperty(default=1)
	def opacity(self) -> float:
		return super(Plot, self).opacity()

	@opacity.setter
	def opacity(self, value: float):
		if value > 1.0:
			self.data.log.warning(f'Plot opacity must be between 0 and 1. {value} is not valid.')
			value = 1.0
		super(Plot, self).setOpacity(value)

	@opacity.encode
	def opacity(value) -> float:
		return round(value, 3)

	@property
	def figure(self) -> 'Figure':
		return self._figure

	@figure.setter
	def figure(self, value: 'Figure'):
		self._figure = value

	@StateProperty(key='type', sortOrder=0)
	def plotType(self) -> DisplayType:
		return DisplayType.LinePlot

	@plotType.setter
	def plotType(self, value: DisplayType):
		log.warning('Setting plot type currently not implemented.')

	@plotType.encode
	def plotType(value: DisplayType) -> str:
		if isinstance(value, DisplayType):
			return value.value
		return value

	@StateProperty(default=DefaultGroup(Qt.SolidLine, 'solid', '', None), after=QGraphicsItem.update)
	def dashPattern(self) -> list[int]:
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
		self.setPen(pen)

	@dashPattern.encode
	def dashPattern(value) -> str:
		if value is None:
			return ''
		return ', '.join(str(v) for v in value)

	@StateProperty(key='cap', default=DefaultGroup(Qt.RoundCap, 'round'), allowNone=False, after=QGraphicsItem.update)
	def capStyle(self) -> Qt.PenCapStyle:
		return self.pen().capStyle()

	@capStyle.setter
	def capStyle(self, value: Qt.PenCapStyle):
		pen = self.pen()
		pen.setCapStyle(value)
		self.setPen(pen)

	@capStyle.encode
	def capStyle(value) -> str:
		if value is None:
			return 'round'
		return camelCase(value.name.decode().strip('Cap'), titleCase=False)

	@capStyle.decode
	def capStyle(value) -> Qt.PenCapStyle:
		caps: dict[str, Qt.PenCapStyle] = Qt.PenCapStyle.values
		capNames = list(caps.keys())
		cap = closestStringInList(value, capNames)
		return caps[cap]

	# Section .events
	def onAxisTransform(self, axis: Axis):
		"""Called when an axis is transformed."""
		self.prepareGeometryChange()

		if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
			if self.renderTask is not None:
				self.renderTask.cancel()
			t = self.__dataTransformAtRender.inverted()[0]*self.figure.figureTransform
			timeOffsetTranslate = self.figure.contentsX
			t.translate(timeOffsetTranslate*self.scene().viewScale.x, 0)
			self.setTransform(t)
			self.renderTask = loop.call_later(0.3, partial(self.onAxisTransform, axis))
			return

		pixmap = self.pixmap()
		# self.setPixmap(pixmap.transformed(self.__dataTransformAtRender.inverted()[0] * self.figure.figureTransform))
		self._updatePath()
		self.updateTransform()
		if self.gradient:
			self.updateGradient()
		self.renderTask = loop.create_task(self.render())

	def onDataChange(self):
		"""Called when the data is changed."""
		self.prepareGeometryChange()
		self._updatePath()
		self.updateTransform()
		if self.gradient:
			self.updateGradient()
		loop.create_task(self.render())

	@asyncSlot()
	async def onResizeDone(self):
		"""Called when the plot is resized but not while being actively resized."""
		if not self.data.hasData:
			return
		self.prepareGeometryChange()
		self._updatePath()
		self.updateTransform()
		if self.gradient:
			self.updateGradient()
		loop.create_task(self.render())

	def updateTransform(self):
		p = self._path
		if p.elementCount():
			p = self.data.combinedTransform.map(p)
			timeOffsetTranslate = self.figure.contentsX
			p.translate(-timeOffsetTranslate, 0)

			invertedViewTransform = self.scene().view.transform().inverted()[0]
			invertedViewTransform.translate(timeOffsetTranslate*self.scene().viewScale.x, 0)
			self.setPath(p)
		self.setTransform(invertedViewTransform)

		self.prepareGeometryChange()
		self.update()

	def updateGradient(self):
		if not self.data.hasData:
			return
		self.gradientQt.update()
		pen = self.pen()
		brush = QBrush(self.gradientQt)
		pen.setBrush(brush)
		self.setPen(pen)

	def mousePressEvent(self, event) -> None:
		pos = event.pos()
		if self.shape().contains(pos):
			event.accept()
			self.figure.signals.clicked.emit(event)
		else:
			event.ignore()
		super(Plot, self).mousePressEvent(event)

	def mouseReleaseEvent(self, event) -> None:
		super(Plot, self).mouseReleaseEvent(event)
		self.showToolTip(event)

	@Slot(QGraphicsSceneMouseEvent)
	def showToolTip(self, event):
		if self.data.hasData is None:
			return
		pos = event.pos()
		x = pos.x()
		graph = self.figure.graph
		x = graph.timeframe.min + timedelta(milliseconds=(x*graph.msPerPixel))
		differance = x - now()

		figure = self.figure
		rect = figure.marginRect
		y = pos.y() - rect.top()

		value_range = figure.dataValueRange
		minVal = value_range.min
		maxVal = value_range.max
		y = maxVal - (maxVal - minVal)*(y/rect.height())
		value = self.data.dataType(y)
		_time = Second(differance.total_seconds()).hour
		value = f'{_time} | {figure.sharedKey.key}: {value}'
		PlotTip.showText(QCursor.pos(), value, timeout=1000)

	# Section .shape
	def containingRect(self) -> QRectF:
		return self.figure.rect()

	def shape(self) -> QPainterPath:
		return self._shape

	# Section .drawing
	def pen(self) -> QPen:
		return self.__pen

	def setPen(self, value: QPen):
		self.__pen = value

	@property
	def _path(self):
		if self._normalPath.elementCount() == 0 and self.data.timeseries:
			self._updatePath()
		return self._normalPath

	def _updatePath(self):
		self.prepareGeometryChange()
		self._normalPath.clear()

	def setPath(self, path: QPainterPath):
		self.__path = path
		self._updateShape()

	def path(self) -> QPainterPath:
		return self.__path

	def _updateShape(self):
		qp = QPainterPathStroker()
		weight = self.weight_px*2
		qp.setWidth(max(weight, 30))
		shape = qp.createStroke(self.path())
		self.prepareGeometryChange()
		self._shape = shape

	async def render(self):
		with BusyContext(task=self.render):
			self.__dataTransformAtRender = self.figure.figureTransform

			deviceTransform = self.scene().view.deviceTransform()
			viewTransform = self.scene().view.transform()
			deviceScale = self.scene().view.devicePixelRatio()

			rect = self.figure.rect()
			rect.setWidth((self.data.data[0][-1] - min(self.data.data[0][0], self.figure.graph.timeframe.historicalStart.timestamp()))*self.figure.graph.pixelsPerSecond)
			rect = (deviceTransform*viewTransform).mapRect(rect)
			ratio = rect.width()/rect.height()
			scaleTo = False
			if prod(rect.size().toTuple())*4 >= self.scene().view.maxTextureSize:
				newWidth = sqrt(8e6*ratio)
				newHeight = newWidth/ratio
				scaleTo = QSizeF(newWidth, newHeight)

			pixmap = QPixmap(rect.size().toSize())
			pixmap.setDevicePixelRatio(deviceScale)
			pixmap.fill(Qt.transparent)
			painter = EffectPainter(pixmap)

			pen = self.pen()
			weight = self.weight_px
			pen.setWidthF(weight)
			painter.setPen(pen)

			path = viewTransform.map(self.path())
			painter.drawPath(path)
			painter.end()
			pixmap = self.scene().bakeEffects(pixmap, *self.effects.values())

			self.prepareGeometryChange()
			self._updateShape()
			if scaleTo:
				scale = rect.width()/scaleTo.width()
				pixmap = pixmap.scaled(scaleTo.toSize(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
				self.setScale(scale)
			else:
				self.setScale(1)

			self.setPixmap(pixmap)
			self.renderTask = None
			self.pixmapTransformCache = None


# Section LinePlot
class LinePlot(Plot):
	_gradient: bool = False

	def __init__(self, *args, **kwargs):
		self._fill = False
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
			return values
		return values

	def _updatePath(self):
		values = self.__getValues()
		x = sum((value.x() for value in values[:3]))/3 - values[0].x()
		y = sum((value.y() for value in values[:3]))/3 - values[0].y()
		start = values[0] - QPointF(x, y)
		path = self._normalPath
		path.clear()
		path.moveTo(start)
		for value in values:
			# if value.y() <= 0:
			# 	self._normalPath.moveTo(value)
			path.lineTo(value)

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


# Section Annotation Text

@runtime_checkable
class GraphItem(Protocol):

	@property
	@abstractmethod
	def graphic(self) -> Plot:
		...

	@property
	@abstractmethod
	def figure(self) -> 'Figure':
		...

	@property
	@abstractmethod
	def graph(self) -> 'Graph':
		...


@runtime_checkable
class LinePlotGraphItem(GraphItem, Protocol):

	@property
	@abstractmethod
	def graphic(self) -> LinePlot:
		...


@runtime_checkable
class HasWeight(Protocol):

	@property
	@abstractmethod
	def weight(self) -> float:
		...

	@property
	@abstractmethod
	def weight_px(self) -> float:
		...


class LineWeight(Size.Width, relativeDecorator='lw'):
	pass


class AnnotationText(Text):
	textSize: Length | Size.Height
	shadow = SoftShadow
	data: GraphItemData | Iterable
	labelGroup: 'AnnotationLabels'
	limits: Axis = Axis.Y
	value: Any
	timestamp: datetime

	def __init__(self, labelGroup: 'AnnotationLabels', data: GraphItemData | Iterable, *args, **kwargs):
		self.labelGroup = labelGroup
		self.data = data
		super(AnnotationText, self).__init__(parent=labelGroup.surface, **kwargs)
		self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
		self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges)
		self.setOpacity(getattr(self.labelGroup, 'opacity', 1))

	# self.setCacheMode(QGraphicsItem.ItemCoordinateCache)

	def setZValue(self, z: float) -> None:
		z = max(i.graphic.zValue() for i in self.figure.plots) + 10
		super(Text, self).setZValue(z)

	@property
	def value(self):
		return self._value

	@value.setter
	def value(self, value):
		self._value = value
		self.refresh()

	def refresh(self):
		super(AnnotationText, self).refresh()

	@property
	def surface(self):
		return self.labelGroup.surface

	@property
	def allowedWidth(self):
		return 400

	@property
	def textSize(self) -> float:
		return self.data.textSize

	@property
	def limitRect(self) -> QRectF:
		viewScale = self.scene().viewScale
		rect = QRectF(0, 0, self.allowedWidth/viewScale.x, self.data.textSize_px/viewScale.y)
		rect.moveCenter(self.boundingRect().center())
		return rect

	@property
	def displayPosition(self) -> DisplayPosition:
		return self.data.position

	def boundingRect(self) -> QRectF:
		return getattr(self, '_textRect', None) or super().boundingRect()

	def containingRect(self) -> QRectF:
		return self.surface.rect()

	@property
	def offset(self) -> float:
		return self.data.offset_px

	@property
	def x(self) -> float:
		return (self.timestamp - now()).total_seconds()*self.graphSurface.pixelsPerSecond

	@property
	def y(self) -> float:
		return self.pos().y()

	@property
	def position(self) -> QPointF:
		return QPointF(self.x, self.y)

	@position.setter
	def position(self, value):
		self.setPos(value)

	@property
	def graphSurface(self):
		return self.data.graph

	# !TODO: Reimplement keeping text in containing rect
	def itemChange(self, change, value):
		if change is QGraphicsItem.ItemScenePositionHasChanged:
			# Shrink and fade out as the item moves out of view
			opacity = getattr(self.labelGroup, 'opacity', 1)
			sRect = self.mapRectToScene(self.boundingRect())
			grRect = self.graphSurface.mapRectToScene(self.graphSurface.containingRect)
			if not grRect.contains(sRect):
				if grRect.contains(sRect.center()):
					subRect = grRect.intersected(sRect)
					relativePos = subRect.center() - sRect.center()
					if relativePos.x() > 0:
						diff = subRect.topLeft() - sRect.topLeft()
					else:
						diff = subRect.topRight() - sRect.topRight()
					fract = abs(diff.x())/((sRect.width()/2) or diff.x() or 100)
					self.setScale(1 - fract*0.5)
					self.setOpacity((1 - fract)*opacity)

			else:
				self.setScale(1)
				self.setOpacity(opacity)
		return QGraphicsItem.itemChange(self, change, value)

	def delete(self):
		if scene := self.scene():
			scene.removeItem(self)
			return
		if groupRemove := getattr(self.labelGroup, 'removeItem', None) is not None:
			groupRemove(self)
			return


# Section Annotation Labels
class AnnotationLabels(list[AnnotationText], Stateful, tag=...):
	__typeCache__: ClassVar[dict[Type[AnnotationText], Type[list[AnnotationText]]]] = {}
	__labelClass: ClassVar[Type[AnnotationText]] = AnnotationText

	source: Any
	surface: Surface
	graph: 'GraphPanel'

	enabled: bool
	position: DisplayPosition
	labelHeight: Length | Size.Height
	offset: Length | Size.Height

	_enabled: bool
	xAxisValues: np.ndarray
	yAxisValues: np.ndarray

	def __class_getitem__(cls, item: Type[AnnotationText]):
		if not issubclass(item, AnnotationText):
			raise TypeError('item must be a subclass of PlotLabels')
		if item not in cls.__typeCache__:
			cls.__typeCache__[item] = type(f'{item.__name__}Labels', (cls,), {'__labelClass': item})
		return cls.__typeCache__[item]

	def pre_init(self, source, surface, **kwargs) -> dict:
		self.source = source
		self.surface = surface

		# Find the graph panel
		graph = surface
		while graph is not None and not isinstance(graph, GraphPanel):
			graph = graph.parentItem()
		self.graph = graph

		kwargs = self.prep_init(kwargs)
		return kwargs

	def __init__(self, source: Any, surface: Surface, *args, **kwargs):
		kwargs = self.pre_init(source, surface, **kwargs)
		super(AnnotationLabels, self).__init__()
		self.post_init(state=kwargs)

	def post_init(self, state: dict, *args, **kwargs):
		self.state = state

	# Section .properties
	# ======= state properties ======== #

	# ----------- enabled ------------- #
	@StateProperty(default=True, allowNone=False, singleValue=True)
	def enabled(self) -> bool:
		return getattr(self, '_enabled', True)

	@enabled.setter
	def enabled(self, value):
		self._enabled = value

	@enabled.after
	def enabled(self) -> Callable:
		return self.refresh

	# ----------- opacity ------------- #
	@StateProperty(default=DefaultGroup('100%', 1), allowNone=False)
	def opacity(self) -> float:
		return getattr(self, '_opacity', 1)

	@opacity.setter
	def opacity(self, value: float):
		if getattr(self, '_opacity', 1) != value:
			list(map(lambda x: x.setOpacity(value), self))
		self._opacity = value

	@opacity.decode
	def opacity(value: int | str) -> float:
		if isinstance(value, str):
			number = float((numberRegex.search(value) or {'number': 1})['number'])
			if '%' in value:
				value = (number or 100)/100
				value = sorted((value, 0, 1))[1]
			else:
				value = number
		if value > 100:
			value /= 255
		if value >= 100:
			value /= 100
		value = sorted((0, value, 1))[1]
		return value

	@opacity.encode
	def opacity(value: float) -> str:
		return f'{value*100:.4g}%'

	# ---------- position ------------ #
	@StateProperty(default=DisplayPosition.Auto, allowNone=False, singleValue=True)
	def position(self) -> DisplayPosition:
		return getattr(self, '_position', Unset) or type(self).position.default(self)

	@position.setter
	def position(self, value: DisplayPosition):
		self._position = value

	@position.decode
	def position(self, value: str) -> DisplayPosition:
		return DisplayPosition[value]

	@position.after
	def position(self) -> Callable:
		return self.refresh

	# ----------- height ------------- #
	@StateProperty(key='height', default=Centimeter(0.5), allowNone=False)
	def labelHeight(self) -> Length | Size.Height:
		value = getattr(self, '_labelHeight', Unset) or type(self).labelHeight.default(self)
		return value

	@labelHeight.setter
	def labelHeight(self, value: Length | Size.Height):
		self._labelHeight = value

	@labelHeight.decode
	def labelHeight(self, value: str | float | int) -> Length | Size.Height:
		return self.parseSize(value, type(self).labelHeight.default(self))

	@labelHeight.encode
	def labelHeight(self, value: Length | Size.Height) -> str:
		if isinstance(value, Length) or hasattr(value, 'precision'):
			return f'{value:.3f}'
		return value

	@labelHeight.after
	def labelHeight(self) -> Callable:
		return self.refresh

	# ----------- offset ------------- #
	@StateProperty(default=Size.Height('5px'), allowNone=False)
	def offset(self) -> Length | Size.Height:
		if (offset := getattr(self, '_offset', Unset)) is not Unset:
			return offset
		return type(self).offset.default(self)

	@offset.setter
	def offset(self, value: Length | Size.Height):
		self._offset = value

	@offset.decode
	def offset(self, value: str | float | int) -> Length | Size.Height:
		return self.parseSize(value, type(self).offset.default(self))

	@offset.encode
	def offset(self, value: Length | Size.Height) -> str:
		if isinstance(value, Length) or hasattr(value, 'precision'):
			return f'{value:.3f}'
		return value

	@offset.after
	def offset(self) -> Callable:
		return self.refresh

	# --------- alignment ------------ #
	@StateProperty(default=None, allowNone=True)
	def alignment(self) -> Alignment:
		return getattr(self, '_alignment', Unset) or type(self).alignment.default(self) or self.alignmentAuto

	@alignment.setter
	def alignment(self, value: Alignment):
		self._alignment = value

	@alignment.decode
	def alignment(value: str | int | tuple[AlignmentFlag, AlignmentFlag] | AlignmentFlag) -> Alignment:
		if isinstance(value, (str, int)):
			alignment = AlignmentFlag[value]
		elif value is None:
			alignment = AlignmentFlag.Center
		elif isinstance(value, tuple):
			return Alignment(*value)
		else:
			alignment = AlignmentFlag.Center
		return Alignment(alignment)

	# ======= label properties ======= #
	@property
	def textSize_px(self) -> float:
		textHeight = self.labelHeight
		if isinstance(textHeight, Dimension):
			if textHeight.absolute:
				textHeight = float(textHeight)
			else:
				textHeight = float(textHeight.toAbsolute(self.surface.height()))
		elif isinstance(textHeight, Length):
			dpi = self.surface.scene().view.screen().physicalDotsPerInchY()
			# dpi = 1080 / Centimeter(13.5).inch
			textHeight = float(textHeight.inch)*dpi
		return textHeight

	@property
	def offset_px(self) -> float:
		offset = self.offset
		match offset, self.source:
			case LineWeight(), GraphItem(graphic=HasWeight(weight_px=_) as p):
				offset = offset.toAbsoluteF(p.weight_px)
			case Dimension(absolute=True), _:
				offset = float(offset)
			case Dimension(relative=True), _:
				offset = float(offset.toAbsolute(self.surface.boundingRect().height()))
			case Length(), _:
				dpi = self.surface.scene().view.screen().physicalDotsPerInchY()
				offset = float(offset.inch)*dpi
			case _, _:
				offset = float(offset)
		return offset

	@property
	def alignmentAuto(self) -> Alignment:
		match self.position:
			case DisplayPosition.Top:
				return Alignment(AlignmentFlag.TopCenter)
			case DisplayPosition.Bottom:
				return Alignment(AlignmentFlag.BottomCenter)
			case DisplayPosition.Left:
				return Alignment(AlignmentFlag.CenterRight)
			case DisplayPosition.Right:
				return Alignment(AlignmentFlag.CenterLeft)
			case DisplayPosition.Center | DisplayPosition.Auto:
				return Alignment(AlignmentFlag.Center)

	# ======= abstract methods ======== #
	@abstractmethod
	def refresh(self): ...

	@abstractmethod
	def onDataChange(self, axis: Axis): ...

	""" Called when the data of the axis changes. """

	@abstractmethod
	def onAxisTransform(self, axis: Axis): ...

	""" 
	Called when the axis transform changes.
	For example, when the graph timeframe window changes. 
	"""

	@abstractmethod
	def labelFactory(self, **kwargs): ...

	""" Creates labels for the data."""

	# ======= shared methods ======== #
	def resize(self, newSize: int):
		currentSize = len(self)
		if newSize > currentSize:
			self.extend([self.labelFactory() for _ in range(newSize - currentSize)])
		elif newSize < currentSize:
			for _ in range(currentSize - newSize):
				self.pop().delete()

	def parseSize(self, value: str | float | int, default) -> Length | Size.Height | Size.Width:
		match value:
			case str(value):
				unit = ''.join(re.findall(r'[^\d\.\,]+', value)).strip(' ')
				match unit:
					case 'cm':
						value = Centimeter(float(value.strip(unit)))
						value.precision = 3
						value.max = 10
						return value
					case 'mm':
						value = Millimeter(float(value.strip(unit)))
						value.precision = 3
						value.max = 10
						return value
					case 'in':
						value = Inch(float(value.strip(unit)))
						value.precision = 3
						value.max = 10
						return value
					case 'pt' | 'px':
						return Size.Height(float(value.strip(unit)), absolute=True)
					case '%':
						return Size.Height(float(value.strip(unit)), relative=True)
					case 'lw':
						match self.source:
							case GraphItem(graphic=HasWeight(weight_px=_)):
								value = float(value.strip(unit))
								return LineWeight(value, relative=True)
							case _:
								return value
					case _:
						try:
							return Centimeter(float(value))
						except Exception as e:
							log.error(e)
							return Centimeter(1)
			case float(value) | int(value):
				return Centimeter(float(value))
			case _:
				log.error(f'{value} is not a valid value for labelHeight.  Using default value of 1cm for now.')
				return default


# Section Plot Label
class PlotLabel(AnnotationText):
	_scaleSelection: ClassVar[Callable[[Iterable], Any]] = min

	def __init__(self, **kwargs):
		self.__x, self.__y = 0, 0
		super(PlotLabel, self).__init__(**kwargs)
		self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
		# dropShadow = QGraphicsDropShadowEffect()
		# dropShadow.setBlurRadius(5)
		# dropShadow.setOffset(0, 0)
		# dropShadow.setColor(Qt.black)
		self.setGraphicsEffect(SoftShadow(owner=self))

	# self.setGraphicsEffect(AnnotationText.shadow())

	@property
	def text(self) -> str:
		return str(self.value)

	@property
	def y(self) -> float:
		y = self.__y
		vertical = self.alignment.vertical
		if vertical.isTop:
			y += self.data.offset_px + self.data.source.graphic.pen().widthF()*.25
		elif vertical.isBottom:
			y -= self.data.offset_px + self.data.source.graphic.pen().widthF()
		return y

	@y.setter
	def y(self, value: float):
		self.__y = value

	@property
	def x(self):
		return self.__x

	@x.setter
	def x(self, value: float):
		self.__x = value

	@property
	def position(self) -> QPointF:
		return QPointF(self.x, self.y)

	@position.setter
	def position(self, value):
		match value:
			case QPointF() | QPoint():
				self.__x, self.__y = value.x(), value.y()
			case (x, y):
				self.__x, self.__y = x, y
		self.setPos(self.x, self.y)

	@property
	def timestamp(self):
		return getattr(self._value, 'timestamp', None) or now()

	def itemChange(self, change, value):
		if change is QGraphicsItem.ItemPositionChange:
			x, y = value.toTuple()
			height = self.boundingRect().height()
			containingRect = self.data.graph.containingRect
			if y + height + 10 > containingRect.height():
				y = containingRect.height() - height - 10
			elif y - height - 10 < containingRect.top():
				self.alignment = AlignmentFlag.Top
				y = 10
			value = QPointF(x, y)
		# elif change is QGraphicsItem.ItemPositionHasChanged:
		# 	shape = self.mapToScene(self.shape())
		# 	plotShape = self.data.source.graphic.sceneShape()
		# 	intersectedRect = plotShape.intersected(shape).boundingRect()
		#
		# 	if intersectedRect.height():
		# 		if intersectedRect.top() < shape.boundingRect().top():
		# 			self.moveBy(0, -intersectedRect.height())
		# 		else:
		# 			self.moveBy(0, intersectedRect.height())

		return super(PlotLabel, self).itemChange(change, value)


# Section Plot Labels
class PlotLabels(AnnotationLabels[PlotLabel]):
	# TODO: While saving a without plugins loaded, the labels are not saved.
	"""
	Loaded file had:
	labels:
    enabled: true
    opacity: 100%
    height: 60px
  saved file had:
  completely removed
	"""

	source: GraphItemData
	surface: Surface
	isPeaks: bool = True
	labelInterval: int | timedelta
	data: Iterable[TimeAwareValue]
	peaks: Optional[List[TimeAwareValue]]
	troughs: Optional[List[TimeAwareValue]]

	__xValues: list[float] | None = None  # Normalized x _values (0-1)
	__yValues: list[float] | None = None  # Normalized y _values (0-1)

	__defaults__: dict = {
		'height':  Centimeter(1),
		'enabled': False,
		'offset':  Size.Height(5, absolute=True),
	}

	def __init__(self, peaksTroughs: bool = True, **state):
		self._enabled = True
		self.peaksTroughs = peaksTroughs
		super(PlotLabels, self).__init__(**state)

	def __hash__(self):
		return hash((self.figure, type(self)))

	def post_init(self, **state):
		super(PlotLabels, self).post_init(**state)
		self.surface.setZValue(self.source.figure.zValue() + 100)

	# loop.call_later(5, self.refresh)

	@StateProperty(default=Alignment.default(), allowNone=True, inheritFrom=AnnotationLabels.alignment)
	def alignment(self) -> Alignment:
		pass

	@alignment.condition
	def alignment(self) -> bool:
		return not self.peaksTroughs

	def onDataChange(self, axis: Axis):
		# ! TODO: This could be optimized
		self.resetAxis(axis)
		self.refresh()

	def onAxisTransform(self, axis: Axis):
		if axis is Axis.Vertical:
			self.quickRefresh()
			return
		self.resetAxis(axis)
		self.refresh()

	def quickRefresh(self):
		positions = self.values
		for label, value, pos in zip_longest(self, self.data, positions):
			label.value = value
			label.position = pos

	def refresh(self):
		if self.enabled:
			if self.source.hasData and self.peaksTroughs:
				self.normalizeValues()
				peaks = set(self.source.peaks)
				positions = self.values
				self.resize(len(positions))
				for label, value, pos in zip_longest(self, self.data, positions):
					label.value = value
					label.alignment = AlignmentFlag.Bottom if value in peaks else AlignmentFlag.Top
					label.position = pos
			elif not self.source.hasData:
				return
			else:
				raise NotImplementedError
		else:
			if self:
				self.resize(0)

	@property
	def data(self):
		self.peaks, self.troughs = peaks, troughs = self.source.peaksAndTroughs
		data = [x for x in chain.from_iterable(zip_longest(peaks, troughs)) if x is not None]
		return data

	def onValueChange(self, axis: Axis):
		self.resetAxis(axis)
		self.refresh()

	def labelFactory(self, **kwargs):
		return PlotLabel(labelGroup=self, data=self, **kwargs)

	@property
	def figure(self) -> 'Figure':
		return self.source.figure

	@property
	def plot(self) -> LinePlot:
		return self.source.graphic

	def normalizeValues(self):
		# start with assuming neither axis needs to be normalized
		kwargs = {'axis': Axis.Neither}
		if self.__xValues is None:  # if x _values are already normalized, add Axis.X to axis
			kwargs['axis'] |= Axis.X
		if self.__yValues is None:  # if y _values are already normalized, add Axis.Y to axis
			kwargs['axis'] |= Axis.Y
		if kwargs['axis']:
			kwargs['values'] = self.data
		x, y = self.source.normalize(**kwargs)
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
	def polygon(self):
		return QPolygonF([QPointF(*i) for i in zip(self.normalizedX, self.normalizedY)])

	@property
	def values(self) -> QPolygonF:
		return self.source.combinedTransform.map(self.polygon)

	def isVisible(self):
		return any(i.isVisible() for i in self)


# Section TimeStampGenerator
class TimestampGenerator:
	__timeframe: TimeFrameWindow
	__current: datetime

	def __init__(
		self,
		graph: "GraphPanel",
		filterFunc: Callable[[datetime], bool] = None,
		interval: timedelta = None,
	):
		self.__graph = graph
		self.__timeframe = graph.timeframe
		self.__filter = filterFunc

		if interval is None:
			interval = timedelta(hours=1)
		self.__interval = abs(interval)

		self.__timeframe.changed.connect(self.__onTimeframeChange)
		self.__current = self.start - self.__interval

	def __onTimeframeChange(self):
		try:
			delattr(self, 'start')
		except AttributeError:
			pass

		try:
			delattr(self, 'end')
		except AttributeError:
			pass

		self.__current = self.start - self.__interval

	def setInterval(self, interval: timedelta):
		self.__interval = interval
		try:
			delattr(self, '_replace')
		except AttributeError:
			pass
		self.__onTimeframeChange()

	def setFilter(self, filterFunc: Callable[[datetime], bool]):
		self.__filter = filterFunc

	@cached_property
	def _replace(self) -> dict:
		replace = {'microsecond': 0}
		interval = self.__interval
		if interval >= timedelta(minutes=1):
			replace['second'] = 0
		if interval >= timedelta(hours=1):
			replace['minute'] = 0
		if interval >= timedelta(hours=1):
			replace['hour'] = 0
		return replace

	@cached_property
	def start(self) -> datetime:
		start = self.__timeframe.historicalStart.replace(**self._replace)
		start -= self.__interval
		return start

	@cached_property
	def end(self) -> datetime:
		contentsEnd = self.__graph.contentsMaxTime
		end = contentsEnd.replace(**self._replace)
		while end < contentsEnd:
			end += self.__interval or timedelta(hours=1)
		return end

	@property
	def current(self) -> datetime:
		return self.__current

	def reset(self):
		clearCacheAttr(self, 'start', 'end', '_replace')
		self.__current = self.start - self.__interval

	def __iter__(self):
		return self

	def __len__(self) -> int:
		return int((self.end - self.start)/self.__interval)

	def __next__(self) -> datetime:
		if self.__current > self.end:
			raise StopIteration
		self.__current += self.__interval
		if self.__filter is not None and not self.__filter(self.__current):
			return self.__next__()
		return self.__current

	def __getitem__(self, key):
		if isinstance(key, int):
			return self.start + key*self.__interval
		elif isinstance(key, slice):
			return [self[i] for i in range(key.start, key.stop, key.step)]
		else:
			raise TypeError("TimestampGenerator indices must be integers or slices")

	def __contains__(self, item: datetime) -> bool:
		if isinstance(item, datetime):
			return self.start <= item < self.end
		if isinstance(item, timedelta):
			item = self.start + item
			return self.start <= item < self.end


# Section TimeMarkers
class TimeMarkers(QGraphicsRectItem, Stateful, tag=...):

	def __init__(self, parent):
		self.time = time()
		self.graph = parent.graph
		self.pens = {}
		self.state = self.prep_init({})
		super(TimeMarkers, self).__init__(parent)
		self.parentItem().parentItem().parentItem().signals.resized.connect(self.updateRect)
		self.parentItem().parentItem().graph.timeframe.connectItem(self.onAxisChange)
		self.parentItem().parentItem().graph.axisTransformed.connectSlot(self.onAxisChange)
		self.setOpacity(0.2)
		self.setZValue(-100)

	def __hash__(self):
		return QGraphicsRectItem.__hash__(self)

	@StateProperty(key='weight', default=1, allowNone=False)
	def lineWidth(self) -> float:
		return getattr(self, '_lineWidth', 1)

	@lineWidth.setter
	def lineWidth(self, value):
		self._lineWidth = value

	@lineWidth.after
	def lineWidth(self):
		self.updatePens()

	@lineWidth.encode
	def lineWidth(value: float):
		if value > 10:
			return round(value, 2)
		elif value > 1:
			return round(value, 3)
		return round(value, 4)

	@property
	def lineWidth_px(self):
		return getattr(self, '_lineWidth', 1)*self.graph.plotLineWeight()*0.1

	def updatePens(self):
		lineWidth = self.lineWidth_px
		pen = QPen(colorPalette.windowText().color(), lineWidth)
		pen.setDashPattern([3, 3])
		hour = pen

		lineWidth *= 1.2
		pen = QPen(colorPalette.windowText().color(), lineWidth)
		pen.setDashPattern([3, 3])
		hour3 = pen

		lineWidth *= 1.2
		pen = QPen(colorPalette.windowText().color(), lineWidth)
		pen.setDashPattern([3, 3])
		hour6 = pen

		lineWidth *= 1.5
		pen = QPen(colorPalette.windowText().color(), lineWidth)
		pen.setDashPattern([3, 3])
		hour12 = pen

		lineWidth *= golden
		pen = QPen(colorPalette.windowText().color(), lineWidth)
		# pen.setDashPattern([2, 2])
		hour24 = pen
		self.pens = {
			24: hour24,
			12: hour12,
			6:  hour6,
			3:  hour3,
			1:  hour
		}

	def onAxisChange(self, axis: Axis):
		if isinstance(axis, Axis) and axis & Axis.X:
			clearCacheAttr(self, 'hours')
			self.updateRect()
			self.refresh()
		elif isinstance(axis, (QRect, QRectF)):
			clearCacheAttr(self, 'hours')
			self.updateRect()
			self.refresh()
		t = QTransform()
		t.translate(self.xOffset(), 0)
		self.setTransform(t)

	def updateRect(self, *args):
		self.setRect(self.parentItem().rect())

	def refresh(self):
		self.updatePens()
		scale = self.scene().viewScale.x
		dpi = self.scene().view.window().screen().logicalDotsPerInchX()/scale
		pixelsPerCentimeter = dpi/2.54

		targetWidth = 2*pixelsPerCentimeter
		for group in self.lines.values():
			periodWidth = group.period*self.parentItem().graph.pixelsPerHour*scale
			group.setVisible(periodWidth >= targetWidth)
			group.updateLines()

	@cached_property
	def lines(self):
		return {
			24: HourLines(self, period=24),
			12: HourLines(self, period=12),
			6:  HourLines(self, period=6),
			3:  HourLines(self, period=3),
			1:  HourLines(self, period=1),
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


class HourLines(QGraphicsItemGroup):

	def __init__(self, parent: TimeMarkers, period: timedelta | int):
		super(HourLines, self).__init__(parent)
		if isinstance(period, timedelta):
			period = round(period.total_seconds()/3600)
		self.period = period
		self.setVisible(True)
		self.updateLines()

	@property
	def pen(self):
		return self.parentItem().pens.get(self.period, None) or QPen()

	def updateLines(self):
		self._lines = None
		current = len(self.childItems())
		expected = len(self)
		yMax = self.parentItem().graph.height() + 2
		pen = QPen(self.pen)
		pen.setWidthF(self.pen.widthF()*self.scene().viewScale.x)
		yMin = -2
		if current == expected:
			pass
		if current > expected:
			for item in self.childItems()[expected:]:
				item.setParentItem(None)
				self.removeFromGroup(item)
			return
		if current < expected:
			for h in self.lines[current:]:
				item = QGraphicsLineItem(self, 1, 1, 2, 2)
				self.addToGroup(item)
		for i, line in zip(self.lines, self.childItems()):
			x = i*self.parentItem().graph.pixelsPerHour
			l = QLineF(x, yMin, x, yMax)
			line.setPen(self.pen)
			line.setLine(l)

	@property
	def lines(self):
		if self._lines is None:
			hourInterval = self.period
			f = self.getFilter(hourInterval)
			self._lines = list(filter(f, range(self.parentItem().hours)))
		return self._lines

	def getFilter(self, hourInterval: int):
		exclude = [i for i in (1, 3, 6, 12, 24) if i > hourInterval]
		return lambda i: i%hourInterval == 0 and not any(i%y == 0 for y in exclude)

	def __len__(self):
		return len(self.lines)


def useHeight(_, *args):
	return args[1]


# Section Timestamp Label
class TimestampLabel(AnnotationText):
	formatID: int
	defaultFormatID = 3
	formatStrings = ['%H:%M:%S.%f', '%H:%M:%S', '%H:%M', f'%{DATETIME_NO_ZERO_CHAR}I%p', '%a', '%A', '']
	scaleSelection = useHeight
	labelGroup: 'DayAnnotations'

	def hasCollisions(self, *items):
		t = self.scene().views()[0].transform()
		rects = [t.mapRect(item.sceneBoundingRect()) for item in items]
		# i = self.collidingItems(Qt.IntersectsItemBoundingRect)
		return any(t.mapRect(self.sceneBoundingRect()).intersects(rect) for rect in rects)

	def __init__(self, labelGroup: AnnotationLabels, spread: timedelta, formatID: int = None, format: str = None, **kwargs):
		self.spread: timedelta = spread
		self.graph = labelGroup.graph
		if formatID is None and format is None:
			formatID = self.defaultFormatID
		self.formatID = formatID if formatID is not None else -1
		self.format = format
		super(TimestampLabel, self).__init__(labelGroup=labelGroup, **kwargs)

	@property
	def y(self) -> float:
		containingRect = self.containingRect()
		match self.data.position:
			case DisplayPosition.Top:
				return containingRect.top() + self.offset
			case DisplayPosition.Bottom | DisplayPosition.Auto:
				return containingRect.bottom() - self.offset - QFontMetricsF(self.font()).descent()
			case DisplayPosition.Center:
				return containingRect.center().y() + self.offset
			case _:
				return containingRect.bottom() - self.offset

	def updateTransform(self, rect: QRectF = None, *args):
		super(TimestampLabel, self).updateTransform(rect, *args)
		self.setTransform(modifyTransformValues(self.transform(), yTranslate=0))

	@property
	def allowedWidth(self) -> float:
		return self.spread.total_seconds()*self.graph.pixelsPerSecond

	def setZValue(self, z: float) -> None:
		super(Text, self).setZValue(z)

	@property
	def spread(self):
		return getattr(self, '_spread', None) or timedelta(hours=6)

	@spread.setter
	def spread(self, value):
		self._spread = value

	@property
	def alignment(self) -> Alignment:
		return self.data.alignment

	@alignment.setter
	def alignment(self, value: Alignment):
		pass

	@Text.value.setter
	def value(self, value: datetime):
		if self.spread >= timedelta(days=1):
			value += timedelta(hours=12)
		Text.value.fset(self, value)
		self.refresh()
		self.setPos(self.x, self.y)

	@property
	def timestamp(self):
		return self.value

	@property
	def text(self) -> str:
		if self._value:
			value = self.value.strftime(self.format or self.formatStrings[self.formatID])
			if self.spread < timedelta(days=1):
				value = value.lower()[:-1]
			return value
		return ''

	@property
	def formatID(self):
		val = self.__formatID
		if val is None:
			spread = self.spread
			if spread.days > 0:
				val = 4
			else:
				val = 3
		return val

	@formatID.setter
	def formatID(self, value):
		self.__formatID = value

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


# Section Hour Labels
class HourLabels(AnnotationLabels[TimestampLabel]):
	surface: 'DayAnnotations'
	source: TimestampGenerator
	markerIntervals = [1, 3, 6, 12, 24]
	__spanIndex = 0

	__defaults__ = {
		'position': DisplayPosition.Bottom,
		'offset':   Size.Height(-5, absolute=True),
		'height':   Centimeter(0.5),
		'format':   '%H',
	}

	def __init__(self, surface: 'HourLabels', graph: 'GraphPanel' = None, source: TimestampGenerator = None, **kwargs):
		if graph is not None and source is None:
			source = TimestampGenerator(graph)
		elif graph is None and source is None:
			raise ValueError('Either graph or source must be specified')
		super(HourLabels, self).__init__(surface=surface, source=source, **kwargs)

	def post_init(self, **kwargs):
		super(HourLabels, self).post_init(**kwargs)
		graph = self.surface.graph
		graph.timeframe.connectItem(self.onDataChange)
		graph.axisTransformed.connectSlot(self.onAxisTransform)

	def labelFactory(self, **kwargs):
		if 'spread' not in kwargs:
			kwargs['spread'] = timedelta(hours=6)
		if 'value' not in kwargs:
			kwargs['value'] = now()
		return TimestampLabel(labelGroup=self, data=self, **kwargs)

	def __hash__(self):
		return id(self)

	@Slot(Axis)
	def onDataChange(self, axis: Axis):
		if isinstance(axis, (QRect, QRectF)) or axis & Axis.X:
			self.refresh()

	def onAxisTransform(self, axis: Axis):
		if isinstance(axis, Axis):
			# if axis & Axis.X:
			self.refresh()
		else:
			self.refresh()

	@property
	def labelPadding(self) -> float:
		return 1.5

	def refresh(self):
		if not self.enabled:
			for i in self:
				i.hide()
		if not self:
			spread = timedelta(hours=1)
			s = now().replace(minute=0, second=0, microsecond=0)
			for i in range(24):
				item = self.labelFactory(value=s.replace(hour=i), spread=spread)
				self.append(item)

		labelWidth = max(i.boundingRect().width() for i in self[:min(len(self), 12)])
		viewScale = self.surface.scene().viewScale
		scale = TimestampLabel.scaleSelection(self, *tuple(viewScale))
		hourPixelWidth = self.surface.graph.pixelsPerHour*viewScale.x
		labelIntervals = np.array(self.markerIntervals)*hourPixelWidth
		labelScreenWidth = labelWidth*scale*self.labelPadding

		# find the closest time interval to the label width
		idx = (np.abs(labelIntervals - labelScreenWidth)).argmin()

		span = self.markerIntervals[min(idx, len(self.markerIntervals) - 1)]
		t = timedelta(hours=span)
		self.source.setInterval(t)
		self.source.reset()

		self.resize(len(self.source))
		self.source.reset()

		for label, value in zip(self, self.source):
			label.value = value

	@property
	def span(self):
		return self.markerIntervals[self.__spanIndex]

	@property
	def spanIndex(self):
		return self.__spanIndex

	@spanIndex.setter
	def spanIndex(self, value):
		value = int(value)
		value = clamp(value, 0, len(self.markerIntervals) - 1)
		if self.__spanIndex != value:
			self.__spanIndex = value


# Section Day Labels
class DayLabels(HourLabels):
	__defaults__ = {
		'position': DisplayPosition.Top,
		'offset':   Size.Height(20, absolute=True),
		'height':   Centimeter(1.75),
		'format':   '%a',
		'opacity':  0.20,
	}

	spread = timedelta(days=1)

	def __init__(self, *args, **kwargs):
		super(DayLabels, self).__init__(*args, **kwargs)
		self.source.setInterval(timedelta(days=1))

	def labelFactory(self, **kwargs):
		kwargs.pop('spread', None)
		if 'value' not in kwargs:
			kwargs['value'] = now()
		kwargs['format'] = '%a'
		label = TimestampLabel(labelGroup=self, data=self, spread=self.spread, **kwargs)
		# label.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
		label.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, False)
		return label

	def refresh(self):
		if not self.enabled:
			for i in self:
				i.hide()

		if not self:
			s = now().replace(hour=0, minute=0, second=0, microsecond=0)
			for i in range(7):
				item = self.labelFactory(value=s)
				s += timedelta(days=1)
				self.append(item)

		self.source.reset()
		self.resize(len(self.source))
		self.source.reset()

		for label, value in zip(self, self.source):
			label.value = value


# Section Graph Annotations
class DayAnnotations(Surface, Stateful, tag=...):

	def __init__(self, graph: 'GraphPanel', **kwargs):
		self.graph = graph.parentItem()
		super(DayAnnotations, self).__init__(parent=graph)

		self.hourLabels = HourLabels(graph=self.graph, surface=self)
		self._dayLabels = DayLabels(graph=self.graph, surface=self)
		self.hourLines = TimeMarkers(self)

		self.state = self.prep_init(kwargs)

		app.clock.sync.connect(self.updateItem)
		self.setFlag(QGraphicsItem.ItemClipsChildrenToShape)
		self.setFlag(QGraphicsItem.ItemClipsToShape)

		self.scene().view.resizeFinished.connect(self.onFrameChange)
		self.graph.timeframe.changed.connect(self.onTimeScaleChange)
		self.graph.signals.resized.connect(self.onFrameChange)
		self.setZValue(-100)
		self.setCacheMode(QGraphicsItem.ItemCoordinateCache)

	# self.setVisible(False)

	@property
	def surface(self) -> 'GraphProxy':
		return self.parentItem()

	def _afterSetState(self):
		self.hourLabels.refresh()
		self.hourLines.refresh()
		self.dayLabels.refresh()

	@Slot(Axis)
	def onTimeScaleChange(self, axis: Axis):
		self.hourLabels.onDataChange(axis)
		self.hourLines.onAxisChange(axis)
		self.dayLabels.onDataChange(axis)

	def onFrameChange(self, axis: Axis = Axis.Both):
		self.setTransform(self.graph.proxy.t)
		self.hourLabels.onAxisTransform(axis)
		self.hourLines.onAxisChange(axis)
		self.dayLabels.onDataChange(axis)

	@StateProperty(key='enabled', default=True, allowNone=False, singleValue=True)
	def enabled(self) -> bool:
		return self.isVisible() and self.isEnabled()

	@enabled.setter
	def enabled(self, value: bool):
		self.setVisible(value)
		self.setEnabled(value)

	@enabled.after
	def enabled(self):
		self.hourLabels.refresh()
		self.hourLines.refresh()
		self.dayLabels.refresh()

	@StateProperty(key='lines', default=Stateful)
	def lines(self) -> TimeMarkers:
		return self.hourLines

	@StateProperty(key='hourLabels', default=Stateful)
	def labels(self) -> HourLabels:
		return self.hourLabels

	@StateProperty(key='dayLabels', default=Stateful)
	def dayLabels(self) -> DayLabels:
		return self._dayLabels

	def timeStart(self):
		figures = [figure.figureMinStart for figure in self.graph.figures if figure.plots]
		if figures:
			figures.append(self.graph.timeframe.historicalStart)
			return min(figures)
		return self.graph.timeframe.historicalStart

	def displayStart(self):
		return self.graph.timeframe.historicalStart

	def timeEnd(self):
		figures = [figure.figureMaxEnd for figure in self.graph.figures if figure.plots]
		if figures:
			return max(figures)
		return self.graph.timeframe.max

	def timeRange(self):
		return self.timeEnd() - self.timeStart()

	def rect(self):
		return self.graph.proxy.boundingRect()

	def boundingRect(self):
		return self.parentItem().rect()

	def updateChildren(self):
		for child in self.childItems():
			child.update()

	def updatePosition(self):
		rect = self._rect
		pos = rect.topLeft()
		self.setPos(pos)

	def updateItem(self):
		self.setTransform(self.graph.proxy.t)
		self.hourLabels.refresh()
		self.hourLines.refresh()
		self.dayLabels.refresh()


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


_Figure = ForwardRef('Figure')


class GraphPanel(Panel, tag='graph'):
	isEmpty = False
	figures: List[_Figure]
	timeframe: TimeFrameWindow
	_acceptsChildren: bool = False
	graphZoom: GraphZoom
	log = UILogger.getChild('Graph')
	savable = True

	if TYPE_CHECKING:
		def scene(self) -> LevityScene: ...

	# Section #GraphPanel
	def __init__(self, parent: Panel, **kwargs):
		self.__timescalar = 1
		super(GraphPanel, self).__init__(parent=parent, **kwargs)
		self.graphZoom = GraphZoom(self, self.timeframe)
		self.graphZoom.setZValue(1000)
		self.updateSyncTimer()
		self.scene().view.resizeFinished.connect(self.updateSyncTimer)

	def _init_defaults_(self):
		super()._init_defaults_()
		self.isEmpty = False
		self.setFlag(self.ItemClipsChildrenToShape, True)
		self.setFlag(self.ItemClipsToShape, True)
		self.setAcceptDrops(True)
		self.setAcceptHoverEvents(True)
		self.syncTimer = QTimer(timeout=self.syncDisplay, interval=300000)
		self.axisTransformed = AxisSignal(self)
		self.signals.resized.connect(self.updateSyncTimer)
		self.axisTransformed.connectSlot(self.onAxisChange)

	def _afterSetState(self):
		clearCacheAttr(self, 'plots, annotatedPlots')
		self.annotations.onFrameChange(Axis.Both)

	@cached_property
	def proxy(self) -> 'GraphProxy':
		return GraphProxy(graph=self)

	@StateProperty(default=Stateful, allowNone=False, dependencies={'items', 'timeframe'})
	def annotations(self) -> DayAnnotations:
		return self._annotations

	@annotations.setter
	def annotations(self, value: DayAnnotations):
		self._annotations = value

	@annotations.decode
	def annotations(self, value: dict):
		return DayAnnotations(self.proxy, **value)

	def highlightFigure(self, figure: 'Figure'):
		for i in self.figures:
			i.setOpacity(0.3 if i is not figure else 1)

	def clearHighlight(self):
		for i in self.figures:
			i.setOpacity(1)

	@cached_property
	def contextMenu(self):
		return GraphMenu(self)

	@Slot(Axis)
	def onAxisChange(self, axis: Axis):
		# @asyncSlot(Axis)
		# async def onAxisChange(self, axis: Axis):
		if axis & Axis.X:
			self.__clearCache()
			if annotations := getattr(self, '_annotations', None):
				annotations.onFrameChange(axis)
		self.updateSyncTimer()

	def parentResized(self, *args):
		super(GraphPanel, self).parentResized(*args)
		self.axisTransformed.announce(Axis.X)

	def __clearCache(self):
		clearCacheAttr(self, 'timescalar', 'contentsTimespan', 'contentsMaxTime', 'contentsMinTime', 'contentsRect')

	def setRect(self, rect: QRectF):
		super(GraphPanel, self).setRect(rect)
		self.__clearCache()

	def updateSyncTimer(self):
		self.syncTimer.stop()
		self.syncTimer.setInterval(self.msPerPixel)
		updateFrequency = Second(self.msPerPixel/1000).auto
		log.debug(f"Graph update frequency changed to {updateFrequency: unit: false} {type(updateFrequency).pluralName.lower()}")
		self.syncTimer.start()

	def syncDisplay(self):
		self.proxy.snapToTime(max(self.timeframe.displayPosition, min((figure.figureMinStart for figure in self.figures), default=self.timeframe.displayPosition)))

	def timeToX(self, time: datetime):
		pass

	def refresh(self):
		for figure in self.figures:
			figure.parentResized(self.rect())
		self.syncDisplay()

	@property
	def msPerPixel(self) -> int:
		'''
		Returns the number of milliseconds per pixel.  Useful for deciding how often to update
		the display.
		:return: How many milliseconds span each pixel
		:rtype: int
		'''
		return round(self._timeframe.seconds/self.width()*1000)

	@property
	def pixelsPerSecond(self) -> float:
		'''
		Returns the number of pixels per second.  Useful for determining the width of a bar.
		:return: How many pixels span each second
		:rtype: float
		'''
		return self.width()/self._timeframe.seconds

	@property
	def pixelsPerHour(self):
		return self.width()/self._timeframe.hours

	@property
	def pixelsPerDay(self):
		return self.width()/self._timeframe.days

	@property
	def secondsPerPixel(self):
		return self._timeframe.seconds/self.width()

	@property
	def minutesPerPixel(self):
		return self._timeframe.minutes/self.width()

	@property
	def hoursPerPixel(self):
		return self._timeframe.hours/self.width()

	@property
	def daysPerPixel(self):
		return self._timeframe.days/self.width()

	def wheelEvent(self, event: QGraphicsSceneWheelEvent):
		delta = event.delta()/120
		if event.modifiers() & Qt.ControlModifier:
			self.proxy.moveBy(self.rect().width()*delta*2/3, 0)
		else:
			self.proxy.moveBy(delta*self.pixelsPerHour, 0)

	def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent):
		self.graphZoom.setVisible(True)
		event.ignore()
		super(GraphPanel, self).hoverEnterEvent(event)

	def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent):
		self.graphZoom.setVisible(False)
		event.ignore()
		super(GraphPanel, self).hoverLeaveEvent(event)

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
		elif change == QGraphicsItem.ItemChildAddedChange:
			if isinstance(value, (Incrementer, IncrementerGroup)):
				value.setZValue(10000)
			elif isinstance(value, Figure):
				clearCacheAttr(self, 'plots', 'annotatedPlots', 'figures')
		elif change == QGraphicsItem.ItemChildRemovedChange:
			if isinstance(value, Figure):
				clearCacheAttr(self, 'plots', 'annotatedPlots', 'figures')
		return super(GraphPanel, self).itemChange(change, value)

	@classmethod
	def validate(cls, item: dict) -> bool:
		panelValidation = super(GraphPanel, cls).validate(item)
		timeframe = TimeFrameWindow.validate(item.get('timeframe', {}))
		return panelValidation and timeframe

	@cached_property
	def figures(self):
		return sorted([figure for figure in self.proxy.childItems() if isinstance(figure, Figure)], key=lambda x: x.zValue())

	@StateProperty(key='figures', default=[], sortOrder=-1, dependencies={'timeframe'})
	def items(self) -> list[_Figure]:
		return self.figures[::-1]

	@items.setter
	def items(self, items):
		existing = self.figures.copy()
		for figureState in reversed(items):
			ns = SimpleNamespace(**figureState)
			match existing:
				case []:
					Figure(graph=self, surface=self.proxy, **figureState)
				case [Figure(name=ns.figure) as fig, *_]:
					existing.remove(fig)
					fig.state = figureState
				case [*_]:
					fig = sorted(existing,
						key=lambda figure: len({f for f in figure.plotData} & {i for i, j in figureState.items() if isinstance(j, dict)}),
						reverse=True
					)[0]
					existing.remove(fig)
					fig.state = figureState
				case _:
					pass

	@items.after
	def items(self):
		self.figures.sort(key=lambda figure: figure.zValue())

	@StateProperty(key='timeframe', default=TimeFrameWindow(), sortOrder=0)
	def timeframe(self) -> TimeFrameWindow:
		return self._timeframe

	@timeframe.setter
	def timeframe(self, value):
		if isinstance(value, dict):
			value = TimeFrameWindow(**value)
		value.connectItem(self.updateSyncTimer)
		if hasattr(self, '_timeframe'):
			self._timeframe.disconnectItem(self.updateSyncTimer)
		self._timeframe = value

	@timeframe.encode
	def timeframe(value: TimeFrameWindow) -> dict:
		return value.state

	@timeframe.update
	def timeframe(self, value: dict):
		self.timeframe.state = value

	@timeframe.after
	def timeframe(self):
		self.syncTimer.setInterval(self.msPerPixel)

	@cached_property
	def contentsTimespan(self) -> timedelta:
		timeframe: TimeFrameWindow = self.timeframe
		if self.figures and any(figure.plots for figure in self.figures):
			figureMinStart = (*(figure.figureMinStart for figure in self.figures), timeframe.historicalStart)
			figureMaxEnd = (*(figure.figureMaxEnd for figure in self.figures), timeframe.end)
			return max(figureMaxEnd) - min(figureMinStart)
		return self.timeframe.range

	@cached_property
	def contentsMaxTime(self) -> datetime:
		if self.figures and any(figure.plots for figure in self.figures):
			return max(figure.figureMaxEnd for figure in self.figures)
		return self.timeframe.end

	@cached_property
	def contentsMinTime(self) -> datetime:
		if self.figures and any(figure.plots for figure in self.figures):
			return min(figure.figureMinStart for figure in self.figures)
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
	def plots(self) -> List[GraphItemData]:  # !TODO: make this more efficient
		# return a flat list of all the plots from all the figures
		return [plotList for figure in self.figures for plotList in figure.plotData]

	@cached_property
	def annotatedPlots(self) -> List[GraphItemData]:
		return [plot for plot in self.plots if plot.labeled]

	@cached_property
	def contentsRect(self) -> QRectF:
		width = self.contentsTimespan.total_seconds()/self.secondsPerPixel
		height = self.height()
		x = (self.contentsMinTime.timestamp() - now().timestamp())/self.secondsPerPixel
		y = 0
		return QRectF(x, y, width, height)


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
	graph: GraphPanel

	if TYPE_CHECKING:
		def scene(self) -> LevityScene: ...

	# Section #GraphProxy
	def __init__(self, graph):
		super(GraphProxy, self).__init__(graph)
		self.mouseDown = False
		self.graph = graph
		self._previous = graph.rect()

		self.geometry = self.graph.geometry
		self.setFlag(QGraphicsItem.ItemIsMovable)
		self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
		self.setFlag(QGraphicsItem.ItemIsFocusable, False)
		self.setAcceptHoverEvents(True)
		self.setFlag(self.ItemClipsChildrenToShape)
		self.setFlag(self.ItemClipsToShape)

		self.graph.timeframe.connectItem(self.onTimeFrameChange)
		# self.graph.axisTransformed.connectSlot(self.onTimeFrameChange)

		self.setHandlesChildEvents(False)
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

	@cached_property
	def pix(self) -> QPixmap:
		items = self.childItems()
		viewTransform = self.scene().view.transform()
		rect = reduce(operator.or_, (viewTransform.mapRect(i.sceneBoundingRect()) for i in items)).toRect().adjusted(-1, -1, 1, 1)
		pix = QPixmap(rect.size())
		pix.fill(Qt.transparent)
		painter = QPainter(pix)
		pix.initPainter(painter)
		painter.setRenderHint(QPainter.Antialiasing)
		opt = QStyleOptionGraphicsItem()
		painter.setWorldTransform(viewTransform)
		painter.setBrush(Qt.NoBrush)
		painter.setPen(Qt.NoPen)
		painter.setBackgroundMode(Qt.TransparentMode)

		def paintChildren(root, item, sceneRect):
			children = item.childItems() if hasattr(item, 'childItems') else ()
			localRect = item.mapRectFromScene(sceneRect).toRect()
			scenePos = item.mapToScene(item.pos())
			localPos = root.mapFromScene(scenePos)
			opt.exposedRect = localRect
			opt.rect = localRect
			t = QTransform.fromTranslate(*localPos.toTuple())
			# painter.setTransform(t)
			# if isinstance(item, QGraphicsItemGroup) or bool(item.flags() & QGraphicsItem.ItemHasNoContents):
			# 	pass
			# else:
			item.paint(painter, opt, None)
			for child in children:
				paintChildren(child, root, sceneRect)

		paintChildren(self, self, rect)
		pix.save('test.png', 'PNG')
		return pix

	def mousePressEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		self.parentItem().setSelected(True)
		self.parentItem().setFocus()
		self.parentItem().stackOnTop()
		self.mouseDown = True

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
		super(GraphProxy, self).mouseMoveEvent(event)

	# def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
	# 	if (incrementer := next(
	# 		(i for i in self.graph.graphZoom.childItems() if i.contains(i.mapFromScene(event.scenePos()))), None)
	# 	) is not None:
	# 		incrementer.mouseReleaseEvent(event)
	# 	super(GraphProxy, self).mouseReleaseEvent(event)

	def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
		event.accept()
		super(GraphProxy, self).hoverEnterEvent(event)

	def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
		event.accept()
		super(GraphProxy, self).hoverLeaveEvent(event)

	# def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
	# 	if any(figure.marginRect.contains(event.pos()) for figure in self.graph.figures):
	# 		event.accept()
	#
	# 		x = event.pos().x()
	# 		x = self.graph.timeframe.min + timedelta(milliseconds=(x*self.graph.msPerPixel))
	# 		differance = x - datetime.now(tz=LOCAL_TIMEZONE)
	# 		time = Second(differance.total_seconds()).hour
	# 		values = []
	# 		for figure in (i for i in self.graph.figures if i.plots):
	# 			if not figure.marginRect.contains(event.pos()):
	# 				continue
	# 			y = event.pos().y() - figure.marginRect.top()
	# 			minVal = figure.dataValueRange.min
	# 			maxVal = figure.dataValueRange.max
	# 			y = maxVal - (maxVal - minVal)*(y/figure.marginRect.height())
	# 			values.append((figure, figure.plots[0].dataType(y)))
	# 		if len(values):
	# 			values.sort(key=lambda x: len(x[0].plots), reverse=True)
	# 			value = f'{time} | {" | ".join(f"{i[0].sharedKey.key}: {i[1]}" for i in values)}'
	# 			QToolTip.showText(event.screenPos(), value)
	# 	else:
	# 		QToolTip.hideText()

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

	def contentsRect(self) -> QRectF:
		return self.graph.contentsRect

	def rect(self):
		return self.graph.contentsRect

	def boundingRect(self):
		return self.graph.contentsRect

	def shape(self):
		shape = self.graph.shape()
		shape = self.mapFromParent(shape)
		return shape

	def visibleRect(self):
		rect = self.graph.rect()
		rect = self.mapRectFromParent(rect)
		return rect

	@property
	def polygon(self) -> QPolygonF:
		rect = self.boundingRect()
		return QPolygonF([rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()])

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemPositionChange:
			maxX = -self.graph.timeframe.lookback.total_seconds()*self.graph.pixelsPerSecond
			minX = -self.contentsWidth() + self.graph.rect().right() + maxX
			value = QPointF(sorted((value.x(), minX, maxX))[1], 0)
		return super(GraphProxy, self).itemChange(change, value)

	@property
	def currentTimeFrame(self) -> DateTimeRange:
		visibleRect = self.boundingRect()
		beginningOffsetSeconds = visibleRect.left()/self.pixelsPerSecond
		endOffsetSeconds = visibleRect.right()/self.pixelsPerSecond
		return DateTimeRange(timedelta(seconds=beginningOffsetSeconds), timedelta(seconds=endOffsetSeconds))

	def contentsWidth(self):
		return self.graph.contentsRect.width()

	def contentsX(self):
		return 0

	def xForTime(self, time: datetime) -> float:
		x = (time - self.graph.timeframe.start).total_seconds()/3600
		return x*self.graph.pixelsPerHour

	def paint(self, painter, option, widget):
		top = self.graph.rect().top()
		bottom = self.graph.rect().bottom()
		painter.setPen(QPen(QColor('#ff9aa3'), 1))
		x = self.xForTime(datetime.now(tz=LOCAL_TIMEZONE))
		painter.drawLine(x, top, x, bottom)
		super(GraphProxy, self).paint(painter, option, widget)


class Figure(NonInteractivePanel, tag=...):
	_default: str = None
	_margins: Margins
	dataValueRange: Optional[AxisMetaData] = None
	plotData: list[GraphItemData]
	isEmpty: bool = False
	_acceptsChildren: bool = False
	axisTransformed: AxisSignal

	if TYPE_CHECKING:
		def scene(self) -> LevityScene: ...

	__exclude__ = {'geometry', 'movable', 'resizeable'}

	__defaults__ = {
		'margins':  ('0%', '10%', '0%', '10%'),
		'movable':  False,
		'geometry': ('0%', '0%', '100%', '100%'),
	}

	# Section Figure
	def __init__(self, graph: GraphPanel, surface: GraphProxy, **kwargs):
		self.plotData = []
		self.graph = graph
		self._transform = None
		self._lowerLimit = None
		self._upperLimit = None

		self.axisTransformed = AxisSignal(self)
		super(Figure, self).__init__(parent=graph)

		self.plotSurface = Surface(self)
		self.annotationSurface = Surface(self)
		self.state = kwargs
		self.setFlag(QGraphicsItem.ItemClipsChildrenToShape, not True)
		self.setFlag(QGraphicsItem.ItemClipsToShape, not True)

		self.resizeHandles.setParentItem(None)
		self.setFlag(QGraphicsItem.ItemHasNoContents, False)
		self.setFlag(self.ItemSendsGeometryChanges, False)
		self.marginHandles = FigureHandles(self)
		self.marginHandles.setParentItem(self)
		self.setAcceptedMouseButtons(Qt.NoButton)
		self.marginHandles.hide()
		self.marginHandles.setZValue(1000)

		self.graph.proxy.addToGroup(self)
		self.graph.signals.resized.connect(self.parentResized)
		self.graph.timeframe.changed.connect(self.onAxisResized)
		self.marginHandles.signals.action.connect(self.onAxisResized)
		self.axisTransformed.connectSlot(self.onAxisTransform)
		self.axisTransformed.connectSlot(self.graph.onAxisChange)
		self.setAcceptHoverEvents(False)

	# self.setCacheMode(QGraphicsItem.ItemCoordinateCache)

	def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
		if change is QGraphicsItem.ItemChildAddedChange:
			if isinstance(value, Plot):
				self.plotSurface.addToGroup(value)
		# print('added plot')
		return super(Figure, self).itemChange(change, value)

	def highlightItem(self, item):
		for i in self.plotData:
			i.graphic.setOpacity(0.5)
		# i.graphic.highlight(False)
		item.graphic.setOpacity(1)
		item.graphic.setZValue(1000)

	def clearHighlight(self):
		for i in self.plotData:
			i.graphic.setOpacity(i.graphic.opacity)

	@cached_property
	def contextMenu(self):
		return FigureMenu(self.graph, self)

	# Section Figure Events

	@asyncSlot(Axis)
	async def onGraphItemUpdate(self, axis: Axis):
		"""Called by a child GraphItem when its value has changed so that it can notify the other children to update"""
		clearCacheAttr(self, 'marginRect')
		self.axisTransformed.announce(axis)
		self.setRect(self.rect())

	@asyncSlot(Axis)
	async def onAxisTransform(self, axis: Axis):
		# Inform the graph that the axis has changed so that it can invalidate the timescalars
		# eventually, further action should wait for the graph to announce the change
		clearCacheAttr(self, 'marginRect')
		self.graph.axisTransformed.announce(axis)

	@asyncSlot(Axis)
	async def onAxisResized(self, axis: Axis):
		clearCacheAttr(self, 'marginRect')
		self.axisTransformed.announce(axis, instant=True)

	@Panel.parent.getter
	def parent(self) -> GraphPanel:
		parent = self.parentItem()
		graph = getattr(parent, 'graph', None)
		return graph or parent

	@property
	def figureTransform(self) -> QTransform:
		transform = QTransform()
		transform.translate(0, self.graph.height())
		transform.scale(1, -1)
		graphTimeRange = self.graph.timeframe.rangeSeconds
		xScale = self.graph.width()
		yScale = self.graph.height()
		transform.scale(xScale, yScale)
		marginTransform = self.margins.asTransform()
		return transform*marginTransform*self.graph.transform()

	def refresh(self):
		for plot in self.plotData:
			plot.refresh()

	@property
	def plots(self):
		return [i for i in self.plotData if i.hasData]

	@StateProperty(default=1.0)
	def opacity(self) -> float:
		return super().opacity()

	@opacity.setter
	def opacity(self, value):
		self.setOpacity(value)

	@StateProperty(unwrap=True, sortOrder=-1, sort=True, sortKey=lambda item: -item[1].z)
	def items(self) -> Dict[CategoryItem, GraphItemData] | dict:
		return {plot.key: plot for plot in reversed(self.plotData)}

	@items.setter
	def items(self, items: dict[str, dict]):
		existing = self.plotData[:]
		for itemKey, item in items.items():
			item['key'] = itemKey
			ns = SimpleNamespace(**item)
			match existing:
				case [GraphItemData(key=ns.key) as graphItem, *rest]:
					existing.remove(graphItem)
					graphItem.state = item
				case _:
					self.addItem(**item)
		for item in existing:
			self.removeItem(item)

	@items.decode
	def items(value: List[dict]) -> dict:
		return {i['figure']: i for i in value}

	@StateProperty(key='figure', sortOrder=0)
	def sharedKey(self) -> CategoryItem:
		keys = [i.key for i in self.plotData]
		i = keys.pop()
		for key in keys:
			i = i & key
		return i

	@sharedKey.encode
	def sharedKey(value: CategoryItem):
		return value.name

	@StateProperty(key='max', sortOrder=-2, default=inf)
	def upperLimit(self) -> float:
		return self._upperLimit if self._upperLimit is not None else inf

	@upperLimit.setter
	def upperLimit(self, value: float):
		self._upperLimit = value

	@StateProperty(key='min', sortOrder=-1, default=-inf)
	def lowerLimit(self) -> float:
		return self._lowerLimit if self._lowerLimit is not None else -inf

	@lowerLimit.setter
	def lowerLimit(self, value: float):
		self._lowerLimit = value

	def debugBreak(self):
		a = self.plotData[0]

	def setParentItem(self, parent: GraphPanel):
		if self.parentItem() is parent:
			return
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

	@property
	def figureMaxStart(self) -> datetime:
		return max((item.timeframe.min for item in self.plotData if item.hasData), default=self.graph.timeframe.start)

	@property
	def figureMinStart(self) -> datetime:
		return min((item.timeframe.min for item in self.plotData if item.hasData), default=self.graph.timeframe.start)

	@property
	def figureEnd(self) -> datetime:
		return max((item.timeframe.max for item in self.plotData if item.hasData), default=self.graph.timeframe.end)

	@property
	def figureMaxEnd(self) -> datetime:
		return max((item.timeframe.max for item in self.plotData if item.hasData), default=self.graph.timeframe.end)

	@property
	def figureMinEnd(self) -> datetime:
		return min((item.timeframe.max for item in self.plotData if item.hasData), default=self.graph.timeframe.end)

	@property
	def figureTimeRangeMin(self) -> timedelta:
		return self.figureMinEnd - self.figureMaxStart

	@property
	def figureTimeRangeMax(self) -> timedelta:
		return self.figureMaxEnd - self.figureMinStart

	@property
	def figureTimeRangeMaxMin(self) -> timedelta:
		return self.figureMinEnd - self.figureMinStart

	@property
	def contentsWidth(self) -> float:
		if self.plotData:
			return self.figureTimeRangeMax.total_seconds()*self.graph.pixelsPerSecond
		return self.frameRect.width()

	@property
	def contentsX(self) -> float:
		return self.graph.timeframe.lookback.total_seconds()*self.graph.pixelsPerSecond

	def setRect(self, rect: QRectF):
		rect.setWidth(self.contentsWidth)
		rect.moveLeft(self.contentsX)
		QGraphicsRectItem.setRect(self, rect)
		self._transform = None

		# TODO: move this announcement to the graph
		self.axisTransformed.announce(Axis.Both)

	def contentsRect(self) -> QRectF:
		rect = super(Figure, self).contentsRect()
		rect.setWidth(self.contentsWidth)
		rect.moveLeft(self.contentsX)
		return rect

	def visibleRect(self) -> QRectF:
		return self.parentItem().visibleRect()

	@property
	def marginPosition(self) -> QPointF:
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
	def name(self) -> str:
		return str(self.sharedKey.name)

	def __repr__(self):
		return f'Figure({self.name}{{{len(self.plotData)}}})'

	def addItem(self, key: CategoryItem, zOrder: Optional[int] = None, *args, **kwargs):
		cls = kwargs.pop('class', GraphItemData)

		item = cls(parent=self, key=key, **kwargs)

		# item.setZValue(max([i.zValue() for i in self.plotData], default=-1) + 1)
		item.z = len(self.plotData)
		self.plotData.append(item)
		return item

	def removeItem(self, item: GraphItemData):
		try:
			self.plotData.remove(item)
		except ValueError:
			pass

	def ensureFramed(self):
		self.setPos(self.clampPoint(self.pos()))

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
		"""My pathetic attempt to make a 'rubberband' scroll effect."""

		def elastic(x, xLimit):
			return xLimit - (xLimit*np.ma.log(xLimit/x))

		# return xLimit * np.ma.log(xLimit / x)
		if v > M:
			m = int(M)
			M = elastic(v, M)
		elif v < m:
			m = elastic(v, m)
		return min(max(m, v), M)


# Section .paint
# def paint(self, painter, option, widget):
# 	pen = painter.pen()
# 	color = QColor(Qt.red)
# 	pen.setColor(color)
# 	painter.setPen(pen)
# 	color.setAlpha(20)
# 	painter.setBrush(color)
# 	painter.drawRect(self.rect().adjusted(1, 1, -1, -1))


# Section Menus


class GraphMenu(BaseContextMenu):
	graph: GraphPanel
	figures: QMenu

	def __init__(self, graph: GraphPanel):
		self.graph = graph
		super(GraphMenu, self).__init__(graph)
		self.opacityState = {}
		self.adjustSize()
		self.aboutToShow.connect(self.getOpacities)
		self.aboutToHide.connect(self.restoreOpacity)

	def uniqueItems(self):
		self.figures = self.addMenu('Figures')
		for figure in reversed(self.graph.figures):
			self.figures.addMenu(figure.contextMenu)
			figure.contextMenu.parentMenu = self
		self.figures.adjustSize()
		sizeHint = self.figures.sizeHint()
		width = sizeHint.width()
		self.figures.setFixedWidth(width + 20)

	def clearHighlight(self):
		self.graph.clearHighlight()
		for figure in reversed(self.graph.figures):
			figure.clearHighlight()

	def getOpacities(self):
		self.opacityState = {}
		for figure in self.graph.figures:
			figureOpacity = {figure: figure.opacity}
			for item in figure.plotData:
				figureOpacity[item] = item.graphic.opacity
			self.opacityState[figure] = figureOpacity

	def restoreOpacity(self, figure: Figure = None):
		opacity = self.opacityState
		if figure in opacity:
			items = opacity[figure]
			for item, value in items.items():
				if isinstance(item, GraphItemData):
					item.graphic.opacity = value
		else:
			for figure, items in opacity.items():
				for item, value in items.items():
					if isinstance(item, GraphItemData):
						item.graphic.opacity = value
					else:
						item.opacity = value
			self.opacityState = {}


class FigureMenu(QMenu):
	parent: GraphMenu
	figure: Figure
	figureItems: List[GraphItemData]

	def __init__(self, parent: GraphMenu, figure: Figure):
		super(FigureMenu, self).__init__()
		self.items = []
		self.parent = parent
		self.figure = figure
		title = joinCase(figure.name, valueFilter=str.title)
		self.setTitle(title)
		self.updateItems()
		self.addSeparator()
		marginAction = self.addAction('Edit Margin', self.editMargins)
		self.adjustSize()
		sizeHint = self.sizeHint()
		width = sizeHint.width()
		self.setFixedWidth(width + 20)
		self.setSeparatorsCollapsible(True)
		self.aboutToShow.connect(self.highlight)
		self.aboutToHide.connect(self.restoreOpacity)

		if self.items:
			self._currentItem = self.items[0].item
		else:
			self._currentItem = None

	def restoreOpacity(self):
		if parentMenu := getattr(self, 'parentMenu', None):
			parentMenu.restoreOpacity(self.figure)

	def highlight(self):
		self.parent.highlightFigure(self.figure)

	def updateItems(self):
		items = [GraphItemMenu(parent=self, item=item) for item in reversed(self.figure.plotData)]
		self.items = items
		if len(items) > 1:
			for item in items:
				self.addSection(item.title())
				if platform.system() == 'Darwin':
					title = self.addAction(item.title())
					title.setEnabled(False)
				for action in item.actions():
					self.addAction(action)
		elif items:
			item = items[0]
			for action in item.actions():
				self.addAction(action)

	def editMargins(self):
		self.figure.scene().clearFocus()
		self.figure.marginHandles.setEnabled(True)
		self.figure.marginHandles.setVisible(True)
		self.figure.marginHandles.updatePosition()
		self.figure.marginHandles.setFocus()

	def mouseMoveEvent(self, event):
		menuItem = self.actionAt(event.pos())
		if menuItem and (parent := menuItem.parent()) is not self and parent is not self._currentItem:
			self._currentItem.figure.highlightItem(parent.item)
			self._currentItem = parent.item
		super(FigureMenu, self).mouseMoveEvent(event)


class TimeseriesSourceMenu(SourceMenu):

	def __init__(self, parentMenu, item):
		self.item = item
		super(TimeseriesSourceMenu, self).__init__(parentMenu)

	def updateItems(self):
		if self.sources:
			self.setEnabled(True)
		else:
			self.setEnabled(False)
		for action in self.actions():
			action.setChecked(action.source is self.item.currentSource)

	@property
	def sources(self):
		key = self.parent.item.key
		if key is not None:
			return [i for i in Plugins if key in i and i[key].isTimeseries]
		return []

	def addSources(self):
		for k in self.sources:
			name = k.name
			action = self.addAction(name, lambda k=k: self.changeSource(k))
			action.source = k
			action.setCheckable(True)
		# action.setChecked(k == self.item.currentSource)

	def changeSource(self, source):
		self.item.changeSource(source)


class GraphItemMenu(QMenu):
	parent: FigureMenu
	item: GraphItemData

	def __init__(self, parent: FigureMenu, item: GraphItemData):
		super().__init__(parent)
		self.parent = parent
		self.item = item
		title = joinCase(str(item.key.name), valueFilter=str.title)
		if len(stripedTitle := title.replace(parent.title(), '')) > 3:
			title = stripedTitle.strip()
		self.setTitle(title)

		self.sources = TimeseriesSourceMenu(self, item)
		self.addMenu(self.sources)

		labeledAction = self.addAction('Labeled', self.toggleLabeled)
		labeledAction.setCheckable(True)
		labeledAction.setChecked(item.labels.enabled)

		visibleAction = self.addAction('Visible', self.toggleVisible)
		visibleAction.setCheckable(True)

		smoothAction = self.addAction('Smoothing', self.toggleSmooth)
		smoothAction.setCheckable(True)
		smoothAction.setChecked(item.smooth)

	def toggleLabeled(self):
		self.item.labels.enabled = not self.item.labels.enabled

	def toggleVisible(self):
		val = self.item.graphic.isVisible()
		self.item.graphic.setVisible(not val)

	def toggleSmooth(self):
		self.item.smooth = not self.item.smooth
