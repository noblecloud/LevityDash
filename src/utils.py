import asyncio

from types import GenericAlias

from time import struct_time, time

from scipy.signal import savgol_filter

from src import config, logging
import re
from abc import ABC, ABCMeta, abstractmethod
from collections import deque, namedtuple
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime, timedelta
from enum import auto, Enum, EnumMeta, IntFlag
from functools import cached_property
from json import JSONEncoder
from pathlib import Path
from threading import RLock, Thread
from typing import Any, Callable, Dict, Hashable, Iterable, Iterator, List, NamedTuple, Optional, overload, Protocol, Set, Tuple, Type, TypeVar, Union

from sys import float_info

import numpy as np
import WeatherUnits as wu
from dateutil.parser import parse as dateParser
from numpy import cos, ndarray, radians, sin
from PySide2.QtCore import QLineF, QMargins, QMarginsF, QObject, QPoint, QPointF, QRect, QRectF, QRunnable, QSize, QSizeF, Qt, QThread, QTimer, Signal, Slot
from PySide2.QtGui import QBrush, QColor, QFont, QMatrix4x4, QPainter, QPainterPath, QPen, QPolygon, QPolygonF, QTransform, QVector2D
from PySide2.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsRectItem, QGraphicsScene, QWidget
from pytz import timezone, utc
from WeatherUnits import Measurement
from math import atan2, degrees as mathDegrees, floor, ceil, inf, nan

log = logging.getLogger(__name__)
Numeric = Union[int, float, complex, np.number]


class _Panel(QGraphicsRectItem):

	def isValid(self) -> bool:
		return self.rect().isValid()

	def size(self) -> QSizeF:
		return self.rect().size()


def threaded(fn):
	def wrapper(*args, **kwargs):
		Thread(target=fn, args=args, kwargs=kwargs).start()

	return wrapper


def utcCorrect(utcTime: datetime, tz: timezone = None):
	"""Correct a datetime from utc to local time zone"""
	return utcTime.replace(tzinfo=utc).astimezone(tz or config.tz)


# def closest(lst: List, value: Any):
# 	return lst[min(range(len(lst)), key=lambda i: abs(lst[i] - value))]

def matchWildCard(i, j, wildcard: str = '*') -> bool:
	return i == j or i == wildcard or j == wildcard


def removeSimilar(input_, compare):
	new = []
	for i, j in zip(input_, compare):
		if i != j:
			new.append(i)
	return new + list(input_[len(new) + 1:])


def overlaps(input_, compare, recursive=False):
	if not any(startArray := [matchWildCard(input_[0], i) for i in compare]):
		return []
	else:
		start = startArray.index(True)
		end = start

	it = iter(compare[start:])

	for i in input_:
		try:
			n = next(it)

			# if the value matches, continue
			if matchWildCard(i, n):
				end += 1
				continue
			else:
				remainder = compare[compare.index(input_[0], start + 1):]
				value = overlaps(input_, remainder)
				return value

		except StopIteration:
			return [(compare[start:end])]
	if end == len(compare):
		return compare[start:end]
	else:
		if recursive:
			remainder = overlaps(input_, compare[compare.index(input_[0], start + 1):], recursive=recursive)
			value = compare[start:end]
			if isinstance(remainder[0], list):
				return [value, *remainder]
			return [value, remainder]
		else:
			return [compare[start:end]]


## TODO: Look into LCS (Longest Common Subsequence) algorithms
def subsequenceCheck(input_: List[str], compare: List[str], strict: bool = False) -> bool:
	'''
	Compare two lists to determine if input is a subsequence of compare with wildcard _values respected
	:param input_: possible subsequence
	:type input_: Iterable
	:param compare: sequence to compare against
	:type compare: Iterable
	:return: True if input is a subsequence of compare, False otherwise
	:rtype: bool
	:param strict: if True, input length must match compare length
	:type strict: bool
	'''
	if strict:
		if len(input_) != len(compare):
			return False
	# if the first value of the input is not in the compare sequence, return False
	if not any(startArray := [matchWildCard(input_[0], i) for i in compare]):
		return False
	# otherwise, find the index of the that first value in compare
	else:
		start = startArray.index(True)

	# ignore everything before the first value of the input
	it = iter(compare[start:])

	# iterate through the input and compare against the compare sequence
	for i in input_:
		try:
			n = next(it)

			# if the value matches, continue
			if matchWildCard(i, n):
				continue
			else:
				# otherwise, start over with the remaining _values of the compare sequence
				remainder = list(it)
				return subsequenceCheck(input_, remainder, strict)

		# if the compare sequence is exhausted, return False
		except StopIteration:
			return False
	return True


def closest(lst: List, value, returnIndex: bool = False) -> Union[int, float, Tuple[int, float]]:
	lst = np.asarray(lst)
	idx = (np.abs(lst - value)).argmin()
	if returnIndex:
		return idx
	return lst[idx]


def closestCeil(lst: List, value):
	lst = np.asarray(lst)
	idx = (np.abs(lst - value)).argmin()
	newVal = lst[idx]
	if newVal > value:
		return newVal
	else:
		return lst[min(idx + 1, len(lst) - 1)]


def closestFloor(lst: List, value):
	lst = np.asarray(lst)
	idx = (np.abs(lst - value)).argmin()
	newVal = lst[idx]
	if newVal < value:
		return newVal
	else:
		return lst[max(0, idx - 1)]


def closestString(seq1, seq2):
	'''levenshtein algorithm'''
	oneago = None
	thisrow = range(1, len(seq2) + 1) + [0]
	for x in range(len(seq1)):
		twoago, oneago, thisrow = oneago, thisrow, [0]*len(seq2) + [x + 1]
		for y in range(len(seq2)):
			delcost = oneago[y] + 1
			addcost = thisrow[y - 1] + 1
			subcost = oneago[y - 1] + (seq1[x] != seq2[y])
			thisrow[y] = min(delcost, addcost, subcost)
	return thisrow[len(seq2) - 1]


def closestStringInList(value, lst: list):
	values = [(i, levenshtein(i, value)) for i in lst]
	return min(values, key=lambda x: x[1])[0]


def offsetAngle(point: tuple, angle: Union[float, int], offset: Union[float, int], radians: bool = False):
	'''
	:param point: tuple of x,y coordinates
	:type point: tuple[int, int]
	:param angle: angle in radians
	:type angle: float, int
	:param offset: distance to offset
	:type offset: float, int
	:return: x and y coordinates of point rotated by theta
	:rtype: tuple
	'''
	if not radians:
		angle = np.radians(angle)
	return (point[0] + offset*np.cos(angle), point[1] + offset*np.sin(angle))


def angleBetweenPoints(pointA: Union[QPointF, QPoint, tuple], pointB: Union[QPointF, QPoint, tuple] = None, degrees: bool = True) -> float:
	if isinstance(pointA, (QPointF, QPoint)):
		pointA = pointA.toTuple()
	if isinstance(pointB, (QPointF, QPoint)):
		pointB = pointB.toTuple()
	if pointB is None:
		pointB = (0, 0)

	xDiff = pointB[0] - pointA[0]
	yDiff = pointB[1] - pointA[1]
	if degrees:
		return mathDegrees(atan2(yDiff, xDiff))
	return atan2(yDiff, xDiff)


def levenshtein(source, target):
	if source is None or target is None:
		return inf
	if len(source) < len(target):
		return levenshtein(target, source)

	# So now we have len(source) >= len(target).
	if len(target) == 0:
		return len(source)

	# We call tuple() to force strings to be used as sequences
	# ('c', 'a', 't', 's') - numpy uses them as _values by default.
	source = np.array(tuple(source))
	target = np.array(tuple(target))

	# We use a dynamic programming algorithm, but with the
	# added optimization that we only need the last two rows
	# of the matrix.
	previous_row = np.arange(target.size + 1)
	for s in source:
		# Insertion (target grows longer than source):
		current_row = previous_row + 1

		# Substitution or matching:
		# Target and source items are aligned, and either
		# are different (cost of 1), or are the same (cost of 0).
		current_row[1:] = np.minimum(
			current_row[1:],
			np.add(previous_row[:-1], target != s))

		# Deletion (target grows shorter than source):
		current_row[1:] = np.minimum(
			current_row[1:],
			current_row[0:-1] + 1)

		previous_row = current_row

	return previous_row[-1]


MAX_TIMESTAMP_INT = datetime.max.timestamp()


# TODO: Look into using dateutil.parser.parse as a backup for if util.formatDate is given a string without a format
def formatDate(value, tz: Union[str, timezone], utc: bool = False, format: str = ''):
	"""
	Convert a date string, int or float into a datetime object with an optional timezone setting
	and converting UTC to local time

	:param value: The raw date two be converted into a datetime object
	:param tz: Local timezone
	:param utc: Specify if the time needs to be adjusted from UTC to the local timezone
	:param format: The format string needed to convert to datetime
	:param microseconds: Specify that the int value is in microseconds rather than seconds
	:type value: str, int, float
	:type tz: pytz.tzinfo
	:type utc: bool
	:type format: str
	:type microseconds: bool

	:return datetime:

	"""
	tz = (timezone(tz) if isinstance(tz, str) else tz) or config.tz

	if isinstance(value, str):
		try:
			if format:
				time = datetime.strptime(value, format)
			else:
				time = dateParser(value)
		except ValueError as e:
			logging.error('A format string must be provided.	Maybe dateutil.parser.parse failed?')
			raise e
	elif isinstance(value, (float, int)):
		if value > MAX_TIMESTAMP_INT:
			overBy = (value - MAX_TIMESTAMP_INT)//10
			if overBy > 0:
				value /= 10 ** overBy
		time = datetime.fromtimestamp(value)
	else:
		time = value
	return utcCorrect(time, tz) if utc else time.astimezone(tz)


def savitzky_golay(y, window_size, order, deriv=0, rate=1):
	'''https://scipy.github.io/old-wiki/pages/Cookbook/SavitzkyGolay'''
	r"""Smooth (and optionally differentiate) data with a Savitzky-Golay filter.
	The Savitzky-Golay filter removes high frequency noise from data.
	It has the advantage of preserving the original shape and
	features of the action better than other types of filtering
	approaches, such as moving averages techniques.
	Parameters
	----------
	y : array_like, shape (N,)
		the _values of the time history of the action.
	window_size : int
		the length of the window. Must be an odd integer number.
	order : int
		the order of the polynomial used in the filtering.
		Must be less then `window_size` - 1.
	deriv: int
		the order of the derivative to compute (default = 0 means only smoothing)
	Returns
	-------
	ys : ndarray, shape (N)
		the smoothed action (or it's n-th derivative).
	Notes
	-----
	The Savitzky-Golay is a type of low-pass filter, particularly
	suited for smoothing noisy data. The main idea behind this
	approach is to make for each point a least-square fit with a
	polynomial of high order over a odd-sized window centered at
	the point.
	Examples
	--------
	t = np.linspace(-4, 4, 500)
	y = np.exp( -t**2 ) + np.random.normal(0, 0.05, t.shape)
	ysg = savitzky_golay(y, window_size=31, order=4)
	import matplotlib.pyplot as plt
	plt.plot(t, y, label='Noisy action')
	plt.plot(t, np.exp(-t**2), 'k', lw=1.5, label='Original action')
	plt.plot(t, ysg, 'r', label='Filtered action')
	plt.legend()
	plt.show()
	References
	----------
	.. [1] A. Savitzky, M. J. E. Golay, Smoothing and Differentiation of
		 Data by Simplified Least Squares Procedures. Analytical
		 Chemistry, 1964, 36 (8), pp 1627-1639.
	.. [2] Numerical Recipes 3rd Edition: The Art of Scientific Computing
		 W.H. Press, S.A. Teukolsky, W.T. Vetterling, B.P. Flannery
		 Cambridge University Press ISBN-13: 9780521880688
	"""
	from math import factorial

	try:
		window_size = np.abs(np.int(window_size))
		order = np.abs(np.int(order))
	except ValueError as msg:
		raise ValueError("window_size and order have to be of type int")
	if window_size%2 != 1 or window_size < 1:
		raise TypeError("window_size minSize must be a positive odd number")
	if window_size < order + 2:
		raise TypeError("window_size is too small for the polynomials order")
	order_range = range(order + 1)
	half_window = (window_size - 1)//2
	# precompute coefficients
	b = np.mat([[k ** i for i in order_range] for k in range(-half_window, half_window + 1)])
	m = np.linalg.pinv(b).A[deriv]*rate ** deriv*factorial(deriv)
	# pad the action at the extremes with
	# _values taken from the action itself
	firstvals = y[0] - np.abs(y[1:half_window + 1][::-1] - y[0])
	lastvals = y[-1] + np.abs(y[-half_window - 1:-1][::-1] - y[-1])
	y = np.concatenate((firstvals, y, lastvals))
	return np.convolve(m[::-1], y, mode='valid')


def smoothData(data: np.ndarray, window: int = 25, order: int = 1) -> np.ndarray:
	if window % 2 == 0:
		window -= 1
	if not type(data[0]) is datetime:
		data = savgol_filter(data, window, order)
	return data


def valueWrapperToValueTimeArray(*T):
	array = np.array([[t.value, t.timestamp.timestamp()] for t in T])
	array = array.reshape(len(array), 2)


class Subscription(QObject):
	valueChanged = Signal(dict)
	api: 'API'
	key: str

	def __init__(self, plugins: 'API', key: str, subscriber: Any = None, signalFunction: Optional[Callable] = None, **kwargs):
		self._api: 'API' = api
		self._key: str = key
		self._subscriber: Any = subscriber
		self._signalFunction: Callable = signalFunction
		super(Subscription, self).__init__()

	@property
	def title(self):
		if hasattr(self.value, 'title'):
			return self.value.title
		return self.key

	@property
	def state(self):
		return {'key': self._key, 'plugins': self._api.name}

	@property
	def value(self):
		try:
			return self._api.realtime.get(self._key)
		except KeyError:
			return None


# cacheClearLog = log.getChild('cacheClear')


def clearCacheAttr(obj: object, *attr: str):
	for a in attr:
		# existing = getattr(obj, a, None)
		try:
			delattr(obj, a)
		except AttributeError:
			pass


# new = getattr(obj, a, None)


def timedeltaToDict(value: timedelta):
	ignored = ('microseconds', 'resolution', 'total_seconds', 'min', 'max')
	return {i: v for i in dir(value) if (v := getattr(value, i)) != 0 and i not in ignored and not i.startswith('_')}


def flattenArray(array: List[List[Any]]) -> List[Any]:
	return [item for sublist in array for item in sublist]


def getItemsWithType(*args: Union[List[Union[QObject, dict, Iterable]], type], recursive: bool = False) -> List[Any]:
	def isInstance(obj, args):
		args = tuple([arg for arg in args if isinstance(arg, type)])
		if isinstance(args, tuple):
			argNames = [arg.__name__ for arg in args]
			return obj.__class__.__name__ in argNames or isinstance(obj, args)
		return obj.__class__.__name__ == argNames.__name__ or isinstance(obj, args)

	def wrapAsIterable(item):
		if item is None:
			return None
		if hasattr(item, '__dict__'):
			item = [v for k, v in item.__dict__.items() if not k.startswith('_')]
		if isinstance(item, dict):
			item = list(item.values())
		if not isinstance(item, Iterable):
			return list(item)
		return [item]

	if args:
		T = tuple([item for item in args if isinstance(item, type)])
		if recursive:
			array = flattenArray([wrapAsIterable(item) for item in args if item is not None])
			array = [i for i in flattenArray([wrapAsIterable(item) for item in args]) if i is not None]
			return list({*flattenArray([[arg] if isInstance(arg, T) else [item for item in wrapAsIterable(arg) if isInstance(item, T)] for arg in array])})
		else:
			array = flattenArray([item if not isinstance(item, dict) else list(item.values()) for item in args if not isinstance(item, type)])
			return [i for i in array if isinstance(i, T)]
	return []


class termColors:
	HEADER = '\033[95m'
	OKBLUE = '\033[94m'
	OKCYAN = '\033[96m'
	OKGREEN = '\033[92m'
	WARNING = '\033[93m'
	FAIL = '\033[91m'
	ENDC = '\033[0m'
	BOLD = '\033[1m'
	UNDERLINE = '\033[4m'

	@staticmethod
	def bold(sting: str):
		return termColors.BOLD + sting + termColors.ENDC

	@staticmethod
	def underline(sting: str):
		return termColors.UNDERLINE + sting + termColors.ENDC

	@staticmethod
	def red(sting: str):
		return termColors.FAIL + sting + termColors.ENDC

	@staticmethod
	def green(sting: str):
		return termColors.OKGREEN + sting + termColors.ENDC

	@staticmethod
	def yellow(sting: str):
		return termColors.WARNING + sting + termColors.ENDC

	@staticmethod
	def blue(sting: str):
		return termColors.OKBLUE + sting + termColors.ENDC

	@staticmethod
	def cyan(sting: str):
		return termColors.OKCYAN + sting + termColors.ENDC

	@staticmethod
	def magenta(sting: str):
		return termColors.HEADER + sting + termColors.ENDC


class Axis(IntFlag):
	Neither = 0
	Vertical = auto()
	Horizontal = auto()
	Both = Vertical | Horizontal
	Y = Vertical
	X = Horizontal

	@classmethod
	def fromSize(cls, size: Union[QSize, QSizeF]) -> 'Axis':
		axis = Axis.Neither
		if size.width() != 0:
			axis |= Axis.Horizontal
		if size.height() != 0:
			axis |= Axis.Vertical
		return axis


def modifyTransformValues(transform: QTransform, xTranslate: float = None, yTranslate: float = None, xScale: float = None, yScale: float = None, xRotate: float = None, yRotate: float = None):
	"""Modifies the values of a QTransform inplace and also returns the modified transformation.
	All values are optional and if not specified will not be modified.

	Note: This function does not increase or decrease the transform parameters, it sets them.

	Parameters
	----------
		transform: QTransform
			The transform to modify
		xTranslate: float
			The x translation value
		yTranslate: float
			The y translation value
		xScale: float
			The x scale value
		yScale: float
			The y scale value
		xRotate: float
			The x rotation value
		yRotate: float
			The y rotation value

	Returns
	-------
		QTransform
			The modified transformation
	"""

	if xTranslate is None:
		xTranslate = transform.dx()
	if yTranslate is None:
		yTranslate = transform.dy()
	if xScale is None:
		xScale = transform.m11()
	if yScale is None:
		yScale = transform.m22()
	if xRotate is None:
		xRotate = transform.m12()
	if yRotate is None:
		yRotate = transform.m21()
	transform.setMatrix(xScale, xRotate, 0, yRotate, yScale, 0, xTranslate, yTranslate, 1)
	return transform


class DataTimeRange(QObject):
	'''
		DataTimeRange(source: GraphItemData)
		Ultimately this class needs to watch an entire figure rather than just a single plot item.

		When a plot item changes, it should inform its instance of this class that it's cache is invalid.
		Upon the next access, it compares the previous cached value to the current calculated value,
		if the value is different, it emits an axis changed signal.
	'''

	changed = Signal(Axis)
	source: 'GraphItemData'

	def __init__(self, source: 'GraphItemData'):
		self.__source = source
		self.__varify = True
		self.__range = None
		super(DataTimeRange, self).__init__()
		self.__timer = QTimer(singleShot=True, interval=200)
		self.__timer.timeout.connect(self.__emitChange)

	def invalidate(self):
		self.__varify = True

	@property
	def min(self):
		return self.__source.list[0].timestamp

	@property
	def max(self):
		return self.__source.list[-1].timestamp

	@property
	def range(self):
		if self.__varify:
			value = self.max - self.min
			if value != self.__range:
				self.__range = value
				self.delayedEmit()
				self.__varify = False
		return self.__range

	@property
	def source(self):
		return self.__source

	def delayedEmit(self):
		self.__timer.start()

	def __emitChange(self):
		self.__timer.stop()
		self.changed.emit(Axis.X)


TimeLineCollection = NamedTuple('TimeLineCollection', [('max', datetime), ('min', datetime), ('range', timedelta)])


@dataclass
class MinMax:
	min: Numeric
	max: Numeric

	def __init__(self, min: Numeric, max: Numeric):
		self._min = min
		self._max = max
		super().__init__()

	def setFromArray(self, arr: Iterable[Numeric] = None, key: str = None, plugins: 'API' = None) -> None:
		from src.observations import MeasurementTimeSeries
		if isinstance(arr, MeasurementTimeSeries):
			arr = arr.array
		else:
			arr = np.asarray([] if arr is None else arr)
		if api is not None and key is not None:
			try:
				arr = np.concatenate(api[key], arr)
			except KeyError:
				log.error(f"Key '{key}' not found in API: {api}")

		self.min = min(arr)
		self.max = max(arr)

	def __clearCache(self):
		if hasattr(self, 'range'):
			delattr(self, 'range')
		if hasattr(self, 'rawRange'):
			delattr(self, 'rawRange')

	@property
	def min(self) -> Numeric:
		if self.rawRange > 1:
			return floor(self._min)
		return self._min

	@min.setter
	def min(self, value: Numeric):
		if value > self._max:
			raise ValueError('min must be less than max')
		if value != self._min:
			self.__clearCache()
		self._min = value

	@property
	def max(self) -> Numeric:
		if self.rawRange > 1:
			return ceil(self._max)
		return self._max

	@max.setter
	def max(self, value: Numeric):
		if value < self._min:
			raise ValueError('max must be greater than min')
		if value != self._max:
			self.__clearCache()
		self._max = value

	@cached_property
	def range(self) -> Numeric:
		return self.max - self.min

	@cached_property
	def rawRange(self) -> Numeric:
		return self._max - self._min


class AxisMetaData(QObject):
	changed = Signal(Axis)
	min: Numeric
	max: Numeric
	range: Numeric
	_link: 'FigureRect' = None
	__min: Numeric = None
	__max: Numeric = None

	def __init__(self, link: 'FigureRect'):
		super().__init__()
		self._link = link
		self.__delayTimer = QTimer(singleShot=True, interval=500, timeout=self.__emitChanged)

	@property
	def min(self):
		value = makeNumerical(min([min(i.data[1]) for i in self._link.plotData.values() if i.value]), float, floor)
		if self.__min != value:
			self.__min = value
			self.emitChanged()
		return value

	@property
	def max(self):
		value = makeNumerical(max([max(i.data[1]) for i in self._link.plotData.values() if i.value]), float, ceil)
		if self.__max != value:
			self.__max = value
			self.emitChanged()
		return value

	@property
	def range(self):
		return self.max - self.min

	def emitChanged(self):
		self.__delayTimer.start()

	def __emitChanged(self):
		self.changed.emit(Axis.Vertical)

	@property
	def dataType(self):
		return self._link.plots[0].rawData[0].unit

	def __getitem__(self, item: slice) -> MinMax:
		if self._link.plots:
			# stop = min(item.stop, len(self._link.plots[0].data[0]
			stop = item.stop
			start = max(item.start, 0)
			l = np.stack([i.data[1][start:stop] for i in self._link.plots if i.rawData])
			return MinMax(float(l.min()), float(l.max()))
		m = 0
		M = 1
		return MinMax(m, M)


class TimeoutThread(QThread):

	def __init__(self, owner, func, timeout, **kwargs):
		super(TimeoutThread, self).__init__()
		self.__timeout = timeout
		self.__timer = QTimer(self, singleShot=True, interval=timeout, timeout=self.stop())
		self.owner = owner
		self.func = func
		self.kwargs = kwargs

	def run(self):
		self.__timer.start()
		self.func(self.owner, **self.kwargs)

	def stop(self):
		self.terminate()


class TimeFrameWindow(QObject):
	"""
	TimeFrameWindow provides a set length of time to display on a graph and notifications
	for when the time frame changes. The start and end time are generated from the current time and can not be changed.

	Attributes
	----------
	range : timedelta
		The length of time to display on the graph
	offset : timedelta
		The offset from the current time to display on the graph
	negativeOffset : timedelta
		The offset from the current time to display on the graph

	Properties
	----------
	start : datetime
		The start time of the time frame
	end : datetime
		The end time of the time frame
	seconds : int
		The number of seconds in the time frame
	minutes : int
		The number of minutes in the time frame
	hours : int
		The number of hours in the time frame
	days : int
		The number of days in the time frame
	weeks : int
		The number of weeks in the time frame

	Methods
	-------
	increase(amount: int)
		Increases the time frame by the given amount. If no amount is given,
		the amount is inferred from the current time frame.
	decrease(amount: int)
		Decreases the time frame by the given amount. If no amount is given,
		the amount is inferred from the current time frame.
	connectItem(slot: callable)
		Connects the given slot to the time frame changed signal.
	"""

	range: timedelta
	offset: timedelta
	negativeOffset: timedelta

	end: datetime
	start: datetime
	changed = Signal(Axis)

	def __init__(self, value: timedelta = None,
	             offset: timedelta = timedelta(seconds=0),
	             negativeOffset: timedelta = timedelta(hours=-6),
	             **kwargs):
		"""
		:param value: The length of time to display on the graph
		:type value: timedelta
		:param offset: The offset to apply to the start time
		:type offset: timedelta
		:param negativeOffset: The offset to apply to the end time
		:type negativeOffset: timedelta
		"""
		super(TimeFrameWindow, self).__init__()

		self.__delayTimer = QTimer(singleShot=True, interval=500, timeout=self.__emitChanged)

		self.offset = offset
		self.negativeOffset = negativeOffset

		if isinstance(value, dict):
			value = timedelta(**value)
		if value is None:
			value = timedelta(**kwargs)
		self._range = value
		self.__displayPosition = self.start + self.offset

	@cached_property
	def seconds(self) -> int:
		return self._range.total_seconds()

	@cached_property
	def minutes(self) -> int:
		return self.seconds/60

	@cached_property
	def hours(self) -> int:
		return self.minutes/60

	@cached_property
	def days(self) -> int:
		return self.hours/24

	@cached_property
	def weeks(self) -> int:
		return self.days/7

	@property
	def timeframe(self) -> timedelta:
		return self._range

	@property
	def offset(self) -> timedelta:
		return self._offset

	@offset.setter
	def offset(self, value: timedelta):
		if isinstance(value, dict):
			value = timedelta(**value)
		self._offset = value
		self.__clearCache()

	@property
	def historicalStart(self) -> datetime:
		return self.start + self._negativeOffset

	@property
	def start(self) -> datetime:
		start = datetime.now(tz=config.tz)
		return start

	@property
	def displayPosition(self):
		return self.__displayPosition

	@displayPosition.setter
	def displayPosition(self, value):
		if isinstance(value, timedelta):
			value = self.start + value
		self.__displayPosition = value

	@property
	def end(self):
		return self.start + self._range

	@property
	def min(self) -> datetime:
		return self.start

	@property
	def minEpoch(self) -> int:
		return int(self.min.timestamp())

	@property
	def max(self) -> datetime:
		return self.end

	@property
	def maxEpoch(self) -> int:
		return int(self.max.timestamp())

	@property
	def range(self) -> timedelta:
		return self._range

	@range.setter
	def range(self, value: timedelta):
		if self._range != value:
			if value < timedelta(hours=1):
				value = timedelta(hours=1)
			self.__clearCache()
			self._range = value
			self.changed.emit(Axis.Horizontal)

	@property
	def rangeSeconds(self) -> int:
		return int(self.range.total_seconds())

	@property
	def ptp(self):
		return self.range

	def refresh(self):
		self.__clearCache()

	def __clearCache(self):
		clearCacheAttr(self, 'seconds', 'minutes', 'hours', 'days', 'weeks')

	def decrease(self, value: timedelta):
		self.range -= value

	def increase(self, value: timedelta):
		self.range += value

	@property
	def negativeOffset(self):
		return self._negativeOffset

	@negativeOffset.setter
	def negativeOffset(self, value):
		if isinstance(value, dict):
			value = timedelta(**value)
		if value.total_seconds() > 0:
			value *= -1
		self._negativeOffset = value
		self.__clearCache()

	@property
	def combinedOffset(self):
		return self.offset + self.negativeOffset

	@classmethod
	def validate(cls, item: dict) -> bool:
		value = item.get('value', None) or item or {}
		return any(key in value for key in ['seconds', 'minutes', 'hours', 'days', 'weeks'])

	@staticmethod
	def __exportTimedelta(value: timedelta):
		value = value.total_seconds()
		weeks = int(value/(60*60*24*7))
		value -= weeks*60*60*24*7
		days = int(value/(60*60*24))
		value -= days*60*60*24
		hours = int(value/(60*60))
		value -= hours*60*60
		minutes = int(value/60)
		value -= minutes*60
		seconds = int(value)
		result = {}
		if weeks > 0:
			result['weeks'] = weeks
		if days > 0:
			result['days'] = days
		if hours > 0:
			result['hours'] = hours
		if minutes > 0:
			result['minutes'] = minutes
		if seconds > 0:
			result['seconds'] = seconds
		return result

	@property
	def state(self):
		state = {
			**self.__exportTimedelta(self.range),
			'offset':         self.__exportTimedelta(self.offset),
			'negativeOffset': self.__exportTimedelta(self.negativeOffset)
		}
		return {k: v for k, v in state.items() if v}

	def delayedEmit(self):
		self.__delayTimer.start()

	def __emitChanged(self):
		self.changed.emit(Axis.Horizontal)

	def connectItem(self, slot):
		self.changed.connect(slot)


def mostly(*args) -> bool:
	return sum(1 if bool(i) else 0 for i in args)/len(args) > 0.5


def normalize(a: Iterable, meta: Union[AxisMetaData, TimeFrameWindow] = None, useInterpolated: bool = True) -> np.ndarray:
	if useInterpolated and a.__class__.__name__ == 'GraphItemData':
		a = a.array

	# determine if array needs to be converted
	try:
		sum(a)
	except TypeError:
		a = list([makeNumerical(value) for value in a])

	if meta.__class__.__name__ == 'TimeFrameWindow':
		min = meta.minEpoch
		ptp = meta.rangeSeconds
	elif meta.__class__.__name__ == 'AxisMetaData':
		min = meta.min
		ptp = meta.range
	else:
		min = np.min(a)
		ptp = np.ptp(a)
	return -((a - min)/ptp) + 1
	return (np.array(a) - min)/(ptp if ptp else 1)


def invertScale(a: np.ndarray) -> np.ndarray:
	'''https://stackoverflow.com/a/53936504/2975046'''
	ax = np.argsort(a)
	aax = np.zeros(len(ax), dtype='int')
	aax[ax] = np.arange(len(ax), dtype='int')
	return a[ax[::-1]][aax]


def autoDType(a: Iterable) -> Optional[np.dtype]:
	if not a:
		return None
	if hasattr(a, 'array'):
		a = a.array
	a = np.array(a)
	mn = a.min()
	mx = a.max()

	if abs((a - a.astype(np.int64)).sum()) < 0.01:
		info = np.iinfo
		types = (np.int8, np.int16, np.int32, np.int64)
	else:
		info = np.finfo
		types = (np.float16, np.float32, np.float64)

	for t in types:
		if info(t).min <= mn and mx <= info(t).max:
			return t
	return


def makeNumerical(value: Any, castAs: type = int, using: Callable = None) -> Numeric:
	if isinstance(value, (int, float, complex, np.number)):
		value = castAs(value)
	elif isinstance(value, datetime):
		value = castAs(value.timestamp())
	elif isinstance(value, timedelta):
		value = castAs(value.total_seconds())
	else:
		value = using(value)
	if using is not None:
		value = using(value)
	return value


def closest_point_on_path(rect: QRectF, path: QPainterPath) -> QPointF:
	point = rect.center()

	if path.isEmpty():
		return point

	p = QPainterPath()
	p.addRect(rect)
	path = path.intersected(p)

	vec = QVector2D(point)
	poly = path.toFillPolygon()
	minDist = float_info.max

	for k in range(poly.count()):
		p = QVector2D(poly.at(k))
		if k == poly.count() - 1:
			k = -1
		q = QVector2D(poly.at(k + 1))
		v = q - p
		u = v.normalized()
		d = QVector2D.dotProduct(u, vec - p)

		if d < 0.0:
			d = (vec - p).lengthSquared()
			if d < minDist:
				minDist = d
				minVec = p
		elif d * d > v.lengthSquared():
			d = (vec - q).lengthSquared()
			if d < minDist:
				minDist = d
				minVec = q
		else:
			u *= d
			u += p
			d = (vec - u).lengthSquared()
			if d < minDist:
				minDist = d
				minVec = u

	if minDist >= float_info.max:
		return point

	return minVec.toPointF()


# return point

def cubic_interp1d(x0, x, y):
	"""
	https://stackoverflow.com/a/48085583/36061
	Interpolate a 1-D function using cubic splines.
		x0 : a float or an 1d-array
		x : (N,) array_like
			A 1-D array of real/complex _values.
		y : (N,) array_like
			A 1-D array of real _values. The length of y along the
			interpolation axis must be equal to the length of x.

	Implement a trick to generate at first step the cholesky matrice L of
	the tridiagonal matrice A (thus L is a bidiagonal matrice that
	can be solved in two distinct loops).

	additional ref: www.math.uh.edu/~jingqiu/math4364/spline.pdf
	"""
	x = np.asfarray(x)
	y = np.asfarray(y)

	# remove non finite _values
	# indexes = np.isfinite(x)
	# x = x[indexes]
	# y = y[indexes]

	# check if sorted
	if np.any(np.diff(x) < 0):
		indexes = np.argsort(x)
		x = x[indexes]
		y = y[indexes]

	size = len(x)

	xdiff = np.diff(x)
	ydiff = np.diff(y)

	# allocate buffer matrices
	Li = np.empty(size)
	Li_1 = np.empty(size - 1)
	z = np.empty(size)

	# fill diagonals Li and Li-1 and solve [L][y] = [B]
	Li[0] = np.sqrt(2 * xdiff[0])
	Li_1[0] = 0.0
	B0 = 0.0  # natural boundary
	z[0] = B0 / Li[0]

	for i in range(1, size - 1, 1):
		Li_1[i] = xdiff[i - 1] / Li[i - 1]
		Li[i] = np.sqrt(2 * (xdiff[i - 1] + xdiff[i]) - Li_1[i - 1] * Li_1[i - 1])
		Bi = 6 * (ydiff[i] / xdiff[i] - ydiff[i - 1] / xdiff[i - 1])
		z[i] = (Bi - Li_1[i - 1] * z[i - 1]) / Li[i]

	i = size - 1
	Li_1[i - 1] = xdiff[-1] / Li[i - 1]
	Li[i] = np.sqrt(2 * xdiff[-1] - Li_1[i - 1] * Li_1[i - 1])
	Bi = 0.0  # natural boundary
	z[i] = (Bi - Li_1[i - 1] * z[i - 1]) / Li[i]

	# solve [L.T][x] = [y]
	i = size - 1
	z[i] = z[i] / Li[i]
	for i in range(size - 2, -1, -1):
		z[i] = (z[i] - Li_1[i - 1] * z[i + 1]) / Li[i]

	# find index
	index = x.searchsorted(x0)
	np.clip(index, 1, size - 1, index)

	xi1, xi0 = x[index], x[index - 1]
	yi1, yi0 = y[index], y[index - 1]
	zi1, zi0 = z[index], z[index - 1]
	hi1 = xi1 - xi0

	# calculate cubic
	f0 = zi0 / (6 * hi1) * (xi1 - x0) ** 3 + \
	     zi1 / (6 * hi1) * (x0 - xi0) ** 3 + \
	     (yi1 / hi1 - zi1 * hi1 / 6) * (x0 - xi0) + \
	     (yi0 / hi1 - zi0 * hi1 / 6) * (xi1 - x0)
	return f0


def interpData(data: Union[list, np.ndarray], multiplier: Optional[int] = 6, newLength: int = None) -> np.array:
	if newLength is None:
		newLength = int(len(data) * multiplier)

	if isinstance(data, list):
		data = np.array(data).flatten()
	if isinstance(data[0], datetime):
		time = np.array(list(map((lambda i: i.timestamp()), data)))
		new_x = np.linspace(min(time), max(time), num=newLength)
		interpTime = np.interp(new_x, time, time)
		return np.array(list(map((lambda i: datetime.fromtimestamp(i, tz=config.tz)), interpTime))).flatten()
	else:
		new_x = np.linspace(min(data), max(data), num=newLength, dtype=data.dtype)
		y = np.linspace(min(data), max(data), num=len(data), dtype=data.dtype)
		return np.interp(new_x, y, data).astype(dtype=data.dtype)


def filterBest(arr, data, indexes: bool, high: bool):
	from math import inf
	newArr = []
	clusters = enumerate(arr)
	for i, cluster in clusters:
		if len(cluster) > 1:
			T = -inf if high else inf
			I: int = cluster[0]
			for j in cluster:
				IT = data[j]
				comparison = IT > T if high else IT < T
				I, T = (j, IT) if comparison else (I, T)
		else:
			I = cluster[0]
			T = data[I]

		newArr.append(I if indexes else T)

	return newArr


def plural(func):
	def wrapper(*value, **kwargs):
		value = func(*value, **kwargs)
		return value[0] if len(value) == 1 else tuple(value)

	return wrapper


@plural
def group(*arrays: list[Iterable], spread: int = 20):
	class CloseEnoughInt(int):
		span: int

		def __new__(cls, value, span: int = spread):
			return super(CloseEnoughInt, cls).__new__(cls, value)

		def __init__(self, value, span: int = spread):
			self.span = span
			int.__init__(value)

		def __eq__(self, other):
			lower = self - self.span
			higher = self + self.span
			return lower < other < higher

		@property
		def int(self) -> int:
			return int(self)

	returnedArrays = []
	for arr in arrays:
		try:
			arr.sort()
		except AttributeError:
			try:
				arr = list(arr)
				arr.sort()
			except Exception as e:
				print(e)
				break
		clusters = []
		cluster = []
		for i, x in enumerate(arr):
			x = CloseEnoughInt(x, span=spread)
			previous = arr[i - 1] if i > 0 else arr[-1]
			if i < len(arr) - 1:
				next = arr[i + 1]
			else:
				next = arr[0]
			if previous == x == next or previous == x:
				cluster.append(x.int)
			elif previous != x == next:
				if cluster:
					clusters.append(cluster)
				cluster = [x.int]
			elif previous != x != next:
				if cluster:
					clusters.append(cluster)
					cluster = [x.int]
				else:
					clusters.append([x.int])
					cluster = []
			else:
				if cluster:
					cluster.append(x.int)
					clusters.append(cluster)
					cluster = []
				else:
					clusters.append([x.int])
					cluster = []
		if cluster:
			clusters.append(cluster)
		returnedArrays.append(clusters)
	return returnedArrays


def peaksAndTroughs(data: ndarray) -> Tuple[List[int], List[int]]:
	# Still needs work but doesn't require scipy
	peaks, troughs = findPeaks(data, -data)
	peaks, troughs = group(peaks, troughs)
	peaks = filterBest(peaks, data, True)
	troughs = filterBest(troughs, data, False)
	return peaks, troughs


@plural
def findPeaks(*arrays: Union[list[Iterable], Iterable], spread: int = 2) -> tuple[list, ...]:
	"""
	Takes any number of arrays and finds the peaks for each one and returns a tuple containing the index of each peak
	To find peaks
	:param arrays: arrays that you want to process
	:return: tuple containing indexes of peaks for each array

	## non comprehensive example ##
	returned = []
	for array in arrays:
		peakBool = (array > np.roll(array, 1)) & (array > np.roll(data, -1))
		peaks = []
		for i, value in enumerate(peakBool):
			if value:
				peaks.append(i)
		returned.append(peaks)
	return tuple(returned)
	"""
	return [[i for (i, t) in enumerate((array > np.roll(array, spread)) & (array > np.roll(array, -spread))) if t] for array in arrays]


class TemporalGroups(object):
	def __init__(self, data: List, spread: timedelta = timedelta(hours=12), step: int = 1):
		self.data = data
		self.spread = spread
		self.current = 0
		self.step = step

	def __iter__(self):
		return self

	def __next__(self):
		i = self.current
		forI = i
		backI = i

		ahead = []
		behind = []
		if self.current >= len(self.data):
			raise StopIteration
		currentV = self.data[i]
		backV = self.data[i - 1]
		while backI > 0 and abs(backV.timestamp - currentV.timestamp) < self.spread:
			if len(behind) == 0:
				behind.append(backV)
			elif abs(behind[-1].value - backV.value) > 0.1:
				behind.append(backV)

			backI -= 1
			backV = self.data[backI]
		if i + 1 >= len(self.data):
			ahead = []
		else:
			forV = self.data[i + 1]
			while forI < len(self.data) - 1 and abs(forV.timestamp - currentV.timestamp) < self.spread:
				if len(ahead) == 0:
					ahead.append(forV)
				elif abs(ahead[-1].value - forV.value) > 0.1:
					ahead.append(forV)
				forI += 1
				forV = self.data[forI]
		i = self.current
		self.current += self.step
		return i, currentV, behind, ahead


def findPeaksAndTroughs(array: Iterable, spread: timedelta = 12) -> tuple[list, list]:
	log.debug('Finding Peaks and Troughs')
	peaks = []
	troughs = []

	maxI = len(array)
	groupGenerator = TemporalGroups(array, spread=spread)
	for i, t, behind, ahead in groupGenerator:
		# ahead = array[i: min(i + spread, maxI)]
		# behind = array[max(i - spread, 0):i]
		if not ahead:
			ahead = [array[-1]]
		if not behind:
			behind = [array[0]]

		tV = float(t.value)
		if float(min(behind).value) >= t <= float(min(ahead).value):
			if len(troughs) == 0:
				troughs.append(t)
			elif datetimeDiff(troughs[-1].timestamp, t.timestamp) <= timedelta(hours=6):
				troughs[-1] += t
				p = troughs[-1]
			else:
				troughs.append(t)

		# if troughs and troughs[-1][0] == i - len(troughs[-1]):
		# 	troughs[-1].append(t)
		# else:
		elif float(max(behind).value) <= t >= float(max(ahead).value):
			if len(peaks) == 0:
				peaks.append(t)
			elif datetimeDiff(peaks[-1].timestamp, t.timestamp) <= timedelta(hours=6):
				peaks[-1] += t
				p = peaks[-1]
			else:
				peaks.append(t)

	return peaks, troughs


def estimateTextFontSize(font: QFont, string: str, maxWidth: Union[float, int], maxHeight: Union[float, int], resize: bool = True) -> tuple[QRectF, QFont]:
	font = QFont(font)
	p = QPainterPath()
	p.addText(QtCore.QPoint(0, 0), font, string)
	rect = p.boundingRect()
	rect = estimateTextSize(font, string)
	while resize and (rect.width() > maxWidth or rect.width() > maxHeight):
		size = font.pixelSize()
		if font.pixelSize() < 10:
			break
		font.setPixelSize(size - 3)
		rect = estimateTextSize(font, string)
	return rect, font


def radialPoint(center: QPointF, radius: Numeric, angle: Numeric) -> QPointF:
	"""
	Returns a point given the center, radius and angle.
	:param center: Center of circle
	:type center: QPointF
	:param radius: How far from the center
	:type radius: Numeric
	:param angle: Angle starting at 3 O'clock
	:type angle: Numeric
	:return: Point on a circle
	:rtype: QPointF
	"""
	radI = radians(angle)
	cx, cy = center.toTuple()
	x = cx + radius*cos(radI)
	y = cy + radius*sin(radI)
	return QPointF(x, y)


def estimateTextSize(font: QFont, string: str) -> QRectF:
	p = QPainterPath()
	p.addText(QPoint(0, 0), font, string)
	return p.boundingRect()


class SubscriptionCollection(dict):

	def add(self, item: Subscription):
		self[item.name] = item

	def __getitem__(self, item: str):
		keys = [i for i in self.values() if i.key == item]
		if len(keys) == 1:
			return keys[0]
		if item in keys:
			return self[item]
		return super(SubscriptionCollection, self).__getitem__(item)


class Subscriber(QObject):
	subscriptions: SubscriptionCollection[str, Subscription]

	def __init__(self, subscriptions: list = None, *args, **kwargs):

		self.subscriptions = SubscriptionCollection()
		annotations = {k: v for d in [t.__annotations__ for t in self.__class__.mro() if hasattr(t, '__annotations__')] for k, v in d.items() if issubclass(v, Subscription)}
		for key, value in annotations.items():
			value: Type[Subscription]
			self.subscriptions.add(value(key))

		super(Subscriber, self).__init__(*args, **kwargs)

	def __getattr__(self, item: str):
		if item in self.subscriptions:
			return self.subscriptions[item]
		return super(Subscriber, self).__getattr__(item)


class SignalWrapper(QObject):
	signal = Signal(Measurement)

	def __init__(self, key: str, observation: 'ObservationRealtime', *args, **kwargs):
		self._key = key
		self._observation = observation
		super(SignalWrapper, self).__init__(*args, **kwargs)

	def emitUpdate(self):
		self.signal.emit(self.value)

	def emitValue(self, value: Measurement):
		self.signal.emit(value)

	@property
	def value(self):
		return self._observation[self._key]


class ObservationUpdateHandler(QObject):
	newKey = Signal(Subscription)
	_signals: Dict[str, Signal]
	_source: 'ObservationRealtime'

	def __init__(self, observation: 'ObservationRealtime'):
		self._signals = {}
		self._source = observation
		super(ObservationUpdateHandler, self).__init__()

	@property
	def source(self):
		return self._source

	def signalFor(self, key: str = None, measurement: Measurement = None) -> Signal:
		wrapper = None
		if key is not None:
			wrapper = self._produceKey(key)
		elif measurement is not None:
			wrapper = self._produceMeasurement(measurement.key)
		if wrapper is None:
			raise ValueError('No key or measurement provided')
		return wrapper.signal

	def _produceKey(self, key: str) -> 'TimeAwareValue':
		wrapper = self._signals.get(key, None)
		if wrapper is None:
			self._signals[key] = self.source[key]
			wrapper = self._signals[key]
		return wrapper

	def emitExisting(self, key: str):
		self._signals[key].emitUpdate()

	def new(self, key: str):
		wrapper = self._produceKey(key)
		self.newKey.emit(wrapper)

	def autoEmit(self, key: str):
		if key not in self._signals:
			self.new(key)
		self.emitExisting(key)

	@property
	def observation(self) -> 'ObservationRealtime':
		return self.source


class ForecastUpdateHandler(ObservationUpdateHandler):
	_source: 'ObservationForecast'

	def __init__(self, forecast: 'ObservationForecast'):
		super(ForecastUpdateHandler, self).__init__(forecast)

	def autoEmit(self, *keys: str):
		for key in keys:
			super(ForecastUpdateHandler, self).autoEmit(key)

	@property
	def forecast(self) -> 'ObservationForecast':
		return self.source


class SmartString(str):
	_title = ''
	_key = ''

	def __new__(cls, value: str, title: str = None, key: str = None, catagory: str = None):
		return str(value)

	def __init__(self, value: str, title: str = None, key: str = None, catagory: str = None):
		self._category = catagory
		self._key = key
		self._title = title
		super(SmartString, self).__init__(value)

	@property
	def title(self) -> str:
		return self._title

	@property
	def key(self) -> str:
		return self._key

	@property
	def category(self) -> str:
		return self._category


class ClosestMatchEnumMeta(EnumMeta):

	def __new__(metacls, cls, bases, classdict, **kwds):
		enum_class = super().__new__(metacls, cls, bases, classdict, **kwds)
		for k, v in metacls.__dict__.items():
			if not k.startswith('_'):
				setattr(enum_class, k, v)
		return enum_class

	def __getitem__(cls, name):

		if isinstance(name, str):
			if name not in cls.__members__:
				name = name.title()
				if name not in cls.__members__:
					name = closestStringInList(name, list(cls.__members__.keys()))
			return cls.__members__[name]

		if isinstance(name, int):
			if name not in cls.__dict__.values():
				name = closest(list(cls.__members__.values()), name)
			return cls(name)

	@classmethod
	def all(self):
		return [self.TopLeft, self.TopCenter, self.TopRight, self.CenterLeft, self.BottomLeft, self.BottomCenter, self.BottomRight, self.CenterRight]

	@cached_property
	def isCenter(self):
		return not bool(self & (self.Left | self.Top | self.Right | self.Bottom))

	@cached_property
	def isBottomLeft(self):
		return self.isBottom and self.isLeft

	@cached_property
	def isBottomRight(self):
		return self.isBottom and self.isRight

	@cached_property
	def isTopLeft(self):
		return self.isTop and self.isLeft

	@cached_property
	def isBottom(self):
		return bool(self & self.Bottom)

	@cached_property
	def isRight(self):
		return bool(self & self.Right)

	@cached_property
	def isLeft(self):
		return bool(self & self.Left)

	@cached_property
	def isCentered(self):
		return bool(self * self.Center)

	@cached_property
	def isTopRight(self):
		return self.isTop and self.isRight

	@cached_property
	def isTop(self):
		return bool(self & self.Top)


class LocationFlag(IntFlag, metaclass=ClosestMatchEnumMeta):
	Bottom = auto()
	Top = auto()
	Right = auto()
	Left = auto()
	Center = auto()
	BottomRight = Bottom | Right
	TopRight = Top | Right
	BottomLeft = Bottom | Left
	TopLeft = Top | Left
	TopCenter = Top | Center
	TopRight = Top | Right
	BottomLeft = Bottom | Left
	TopLeft = Top | Left
	CenterRight = Center | Right
	CenterLeft = Center | Left
	BottomCenter = Bottom | Center
	TopCenter = Top | Center

	Vertical = Top | Bottom
	Horizontal = Left | Right
	VerticalCentered = Top | Bottom | Center
	HorizontalCentered = Left | Right | Center

	@cached_property
	def asQtAlignment(self):
		if self.isLeft:
			return Qt.AlignLeft
		elif self.isRight:
			return Qt.AlignRight
		elif self.isTop:
			return Qt.AlignTop
		elif self.isBottom:
			return Qt.AlignBottom
		elif self.isCenter:
			return Qt.AlignCenter
		else:
			return Qt.AlignCenter

	@cached_property
	def isVertical(self):
		return self.isTop or self.isBottom or self.isCenter

	@cached_property
	def isHorizontal(self):
		return self.isLeft or self.isRight or self.isCenter

	@cached_property
	def asVertical(self):
		value = self.Vertical & self
		if value:
			return value
		else:
			return AlignmentFlag.Center

	@cached_property
	def asHorizontal(self):
		value = self.Horizontal & self
		if value:
			return value
		else:
			return AlignmentFlag.Center


class Alignment:
	__slots__ = ('__horizontal', '__vertical')

	@overload
	def __init__(self, alignment: AlignmentFlag):
		...

	@overload
	def __init__(self, horizontal: Union[str, int, AlignmentFlag] = AlignmentFlag.Center, vertical: Union[str, int, AlignmentFlag] = AlignmentFlag.Center):
		...

	@overload
	def __init__(self, horizontal: Union[str, int, AlignmentFlag], vertical: Union[str, int, AlignmentFlag]):
		...

	def __init__(self, horizontal: Union[str, int, AlignmentFlag], vertical: Union[str, int, AlignmentFlag] = None):
		if vertical is None:
			if isinstance(horizontal, AlignmentFlag):
				self.horizontal = horizontal
				self.vertical = horizontal
			else:
				self.horizontal = AlignmentFlag[horizontal]
				self.vertical = self.horizontal
		else:
			self.horizontal = AlignmentFlag[horizontal]
			self.vertical = AlignmentFlag[vertical]

	@property
	def horizontal(self):
		return self.__horizontal

	@horizontal.setter
	def horizontal(self, value: Union[str, int, AlignmentFlag]):
		if not isinstance(value, AlignmentFlag):
			value = AlignmentFlag[value]
		value = value.asHorizontal
		assert value.isHorizontal, 'Horizontal alignment can only be horizontal'
		self.__horizontal = value

	@property
	def vertical(self):
		return self.__vertical

	@vertical.setter
	def vertical(self, value: Union[str, int, AlignmentFlag]):
		if not isinstance(value, AlignmentFlag):
			value = AlignmentFlag[value]
		value = value.asVertical
		assert value.isVertical, 'Vertical alignment must be a vertical flag'
		self.__vertical = value

	def asDict(self):
		return {'horizontal': int(self.horizontal), 'vertical': int(self.vertical)}

	@property
	def asQtAlignment(self):
		return self.horizontal.asQtAlignment | self.vertical.asQtAlignment


Alignment.Center = Alignment(AlignmentFlag.Center)



class ActionTimer:
	__slots__ = ['_action', '_time', '_times']

	def __init__(self, action: str):
		self._action = action
		self._times = deque([0]*10, maxlen=10)
		self._time = time()

	def __call__(self):
		self._times.append(time())
		now = time()
		print(f'\r{self._action} took {1/((sum(self._times)/10) - self._times[0]):.3f}fps', end='')
		# print(f'\r{self._action} took {1/(now - self._time):.3f}fps', end='')
		self._time = now


def relativePosition(item: 'Panel', relativeTo: QRectF = None) -> LocationFlag:
	if isinstance(item, QGraphicsItem):
		center = item.sceneRect().center()
	elif isinstance(item, QPointF):
		center = item
	if relativeTo is None and isinstance(item, QGraphicsItem):
		relativeTo = item.scene().sceneRect().center()
	elif isinstance(relativeTo, QPointF):
		pass
	if center.x() < relativeTo.x():
		x = LocationFlag.Left
	else:
		x = LocationFlag.Right
	if center.y() < relativeTo.y():
		y = LocationFlag.Top
	else:
		y = LocationFlag.Bottom
	return x | y


def stringIsNumber(string: str) -> bool:
	try:
		float(string)
		return True
	except ValueError:
		return False


class MutableFloat:
	__slots__ = ('__value')
	__value: float

	def __init__(self, value: float):
		self.value = value

	@property
	def value(self) -> float:
		if not isinstance(self.__value, float):
			self.__value = float(self.__value)
		return self.__value

	@value.setter
	def value(self, value):
		self.__value = self.__parseValue(value)

	def _setValue(self, value):
		if value is None:
			value = nan
		try:
			value = float.__float__(self, value)
		except ValueError:
			raise ValueError(f'{value} is not a number')
		self.__value = value

	def __parseValue(self, value) -> float:
		if value is None:
			return nan
		try:
			return float(value)
		except ValueError:
			raise ValueError(f'{value} is not a number')

	def __get__(self, instance, owner):
		return self.__value

	def __set__(self, instance, value):
		self._setValue(value)

	def __call__(self):
		return self.__value

	def __add__(self, other):
		return self.__class__(self.__value + float(other))

	def __radd__(self, other):
		return self.__add__(other)

	def __iadd__(self, other):
		self.__value += float(other)
		return self

	def __sub__(self, other):
		return self.__class__(self.__value - float(other))

	def __rsub__(self, other):
		return self.__sub__(other)

	def __isub__(self, other):
		self.__value -= float(other)
		return self

	def __mul__(self, other):
		return self.__class__(self.__value * float(other))

	def __rmul__(self, other):
		return self.__mul__(other)

	def __imul__(self, other):
		self.__value *= float(other)
		return self

	def __truediv__(self, other):
		try:
			return self.__class__(self.__value / float(other))
		except ZeroDivisionError:
			return self.__class__(0)

	def __rtruediv__(self, other):
		return self.__truediv__(other)

	def __itruediv__(self, other):
		self.__value /= float(other)
		return self

	def __floordiv__(self, other):
		return self.__class__(self.__value // float(other))

	def __rfloordiv__(self, other):
		return self.__floordiv__(other)

	def __ifloordiv__(self, other):
		self.__value //= float(other)
		return self

	def __mod__(self, other):
		return self.__class__(self.__value % float(other))

	def __rmod__(self, other):
		return self.__mod__(other)

	def __imod__(self, other):
		self.__value %= float(other)
		return self

	def __pow__(self, other):
		return self.__class__(self.__value ** float(other))

	def __rpow__(self, other):
		return self.__pow__(other)

	def __neg__(self):
		return self.__class__(-self.__value)

	def __pos__(self):
		return self.__class__(+self.__value)

	def __abs__(self):
		return self.__class__(abs(self.__value))

	def __invert__(self):
		return self.__class__(~self.__value)

	def __round__(self, n=None):
		return self.__class__(round(self.__value, n))

	def __floor__(self):
		return self.__class__(self.__value.__floor__())

	def __ceil__(self):
		return self.__class__(self.__value.__ceil__())

	def __trunc__(self):
		return self.__class__(self.__value.__trunc__())

	def __lt__(self, other):
		return self.__value < float(other)

	def __le__(self, other):
		return self.__value <= float(other)

	def __eq__(self, other):
		try:
			return self.__value == float(other)
		except TypeError:
			return False

	def __ne__(self, other):
		return not self.__eq__(other)

	def __gt__(self, other):
		return self.__value > float(other)

	def __ge__(self, other):
		return self.__value >= float(other)

	def __hash__(self):
		return hash(self.__value)

	def __str__(self):
		return str(round(self.__value, 3)).rstrip('0').rstrip('.')

	def __repr__(self):
		return f'<{self.__class__.__name__}({self.__str__()})>'

	def __bool__(self):
		return bool(self.__value)

	def __int__(self):
		return int(self.__value)

	def __float__(self):
		return float(self.__value)

	def __complex__(self):
		return complex(self.__value)

	def __index__(self):
		return int(self.__value)

	def __len__(self):
		return 1

	def is_integer(self) -> bool:
		return self.__value.is_integer()


class DimensionTypeMeta(EnumMeta):

	def __getitem__(cls, name):
		try:
			return super(DimensionTypeMeta, cls).__getitem__(name)
		except KeyError:
			pass
		names = name.split('.')
		names.reverse()
		for name in names:
			name = name.lower()
			if name in cls.__members__:
				return cls.__members__[name]
		if name[0].isalpha() and name[1:].isdigit():
			return cls(int(name[1:]))
		raise KeyError(name)


class DimensionType(Enum, metaclass=DimensionTypeMeta):
	x = 1
	y = 2
	z = 3
	w = 4
	t = w
	width = x
	height = y
	depth = z
	column = x
	row = y
	layer = z
	columns = x
	rows = y
	layers = z
	left = x
	top = y
	right = z
	bottom = w


class Dimension(MutableFloat):
	__slots__ = ('_absolute', '_parent')
	_absolute: bool

	def __init__(self, value: Union[int, float], absolute: bool = None, relative: bool = None):
		super().__init__(float(value))

		# If absolute is not specified, absolute is True
		if relative is None and absolute is None:
			absolute = False

		# If both absolute and relative are specified, absolute takes precedence
		elif relative is not None and absolute is not None:
			absolute = relative

		# If Relative is specified, absolute is the opposite of relative
		elif relative is not None:
			absolute = not relative

		# If Absolute is specified, absolute is the same as absolute
		elif absolute is not None:
			pass

		self._absolute = absolute

	def __str__(self):
		if self._absolute:
			string = super(Dimension, self).__str__()
			if self.__absoluteDecorator__:
				string = f'{string}{self.__absoluteDecorator__}'
			return string

		string = f'{str(round(self.value * 100, 1)).rstrip("0").rstrip(".")}'
		if self.__relativeDecorator__:
			string = f'{string}{self.__relativeDecorator__}'
		return string

	@property
	def absolute(self) -> bool:
		return self._absolute

	def toggleAbsolute(self, parentSize: Union[int, float] = None, value: bool = None):
		if value is not None and parentSize is not None:
			if value:
				self.toAbsolute(parentSize)
			else:
				self.toRelative(parentSize)
		elif parentSize is not None:
			if self._absolute:
				self.toRelative(parentSize)
			else:
				self.toAbsolute(parentSize)
		else:
			self._absolute = not self._absolute

	def toggleRelative(self, parentSize: Union[int, float] = None, value: bool = None):
		if value is not None:
			value = not self.relative
		self.toggleAbsolute(parentSize, value)

	@property
	def relative(self) -> bool:
		return not self._absolute

	@property
	def name(self) -> str:
		return self.__class__.__name__.split('.')[-1]

	@property
	def fullName(self):
		return self.__class__.__name__

	@property
	def dimension(self) -> DimensionType:
		return self.__class__.__dimension__

	def toDict(self):
		return {
			'value':    round(self.value, 5),
			'absolute': self._absolute,
		}

	def toAbsolute(self, value: float) -> 'Dimension':
		if not self._absolute:
			return self.__class__(self*value, True)
		return self

	def toRelative(self, value: float) -> 'Dimension':
		if self._absolute:
			return self.__class__(self/value, False)
		return self

	def setAbsolute(self, value: float):
		self._absolute = True
		self.value = value

	def setRelative(self, value: float):
		self._absolute = False
		self.value = value

	def __parseValue(self, value: Union[int, float, str]) -> float:
		if isinstance(value, str):
			if '%' in value:
				self.relative = True
				value = value.replace('%', '')
			elif 'px' in value:
				self.absolute = True
				value = value.replace('px', '')
			value = re.sub(r'[^0-9.]', '', value, 0, re.DOTALL)
		return super(Dimension, self).__parseValue(value)

	def __truediv__(self, other):
		if isinstance(other, Dimension):
			return self.__class__(self.value / other.value, absolute=not (self.absolute and other.absolute))
		absolute = self > 1 and other > 1
		return self.__class__(self.value / other.value, absolute=absolute)

# def __mul__(self, other):
# 	if isinstance(other, Dimension):
# 		absolute = other.absolute
# 	else:
# 	if other > 1:
# 		absolute = True
#
# 	absolute = absolute or other > 1
# 	return self.__class__(self.value * other.value, absolute=self.absolute or absolute)


class NamedDimension:

	def __new__(cls, name: str, dimension: int, relativeDecorator: str = '%', absoluteDecorator: str = 'px'):
		cls = type(name, (Dimension,), {})
		cls.__dimension__ = DimensionType(dimension)
		cls.__relativeDecorator__ = relativeDecorator
		cls.__absoluteDecorator__ = absoluteDecorator
		return cls


def makePropertyGetter(key):
	def get(self):
		return getattr(self, f'__{key}')

	return get


def makePropertySetter(key):
	if isinstance(key, str) and key.isdigit():
		key = int(key)

	def set(self, value):
		try:
			getattr(self, f'__{key}').value = value
		except AttributeError:
			cls = self.__dimensions__[key]
			setattr(self, f'__{key}', cls(value))

	return set


class Validator(ABC):

	def __init__(self, cls: type):
		self.cls = cls
		self.valueSet = False

	def __set_name__(self, owner, name):
		self.private_name = '__' + name

	def __get__(self, obj, objtype=None):
		return getattr(obj, self.private_name)

	def __set__(self, obj, value):
		if not self.valueSet or not hasattr(obj, self.private_name):
			setattr(obj, self.private_name, value)
			self.valueSet = True
		elif self.valueSet:
			getattr(obj, self.private_name).value = value
		elif isinstance(value, self.cls):
			setattr(obj, self.private_name, value)
			self.valueSet = True
		else:
			log.warning(f'IMPROPER VALUE TYPE FOP {self.cls} {self.private_name}')
			setattr(obj, self.private_name, value)
			self.valueSet = True


class MultiDimensionMeta(type):

	def __new__(cls, name: str, bases: tuple, attrs: dict,
	            dimensions: Union[int, Iterable[str]] = None,
	            separator: str = None, relativeDecorator: str = '%',
	            absoluteDecorator: str = 'px',
	            extend: bool = False):
		if separator is not None:
			pass
		elif separator is None and bases:
			separator = bases[0].__separator__
		else:
			separator = ','

		if isinstance(dimensions, int):
			dimensions = MultiDimensionMeta.parseInt(dimensions)
		if dimensions:
			pass
		elif dimensions is None and bases:
			dimensionBases = [i for i in bases if hasattr(i, '__dimensions__')]
			dimensions = [a for a in dimensionBases[0].__dimensions__.keys()]
		elif dimensions is None:
			dimensions = []

		__dimensions__ = {d: NamedDimension(f'{name}.{d.title()}', i + 1, relativeDecorator, absoluteDecorator) for i, d in enumerate(dimensions)}
		if extend:
			__dimensions__ = {**[i for i in bases if hasattr(i, '__dimensions__')][0].__dimensions__, **__dimensions__}
		# subClasses = list(__dimensions__.values())

		# 	for s, item in __dimensions__.items():
		# 		attrs[s] = property(makePropertyGetter(f'{item.__dimension__.value}'), makePropertySetter(f'{item.__dimension__.value}'))
		if name != 'MultiDimension':
			if '__annotations__' in attrs:
				attrs['__annotations__'].update(__dimensions__)
			else:
				attrs['__annotations__'] = __dimensions__
			attrs['__dimensions__'] = __dimensions__
			for k, v in __dimensions__.items():
				# attrs[k] = property(lambda cls: getattr(cls, f'__{k}'), lambda cls, value: getattr(cls, f'__{k}')._setValue(value))
				attrs[k] = Validator(v)
				# attrs[k] = property(lambda k: v.__value, lambda k, value: v._setValue(v, value))
				# attrs[k] = property(makePropertyGetter(k), makePropertySetter(k))
				attrs[k.title()] = v
		attrs['__separator__'] = separator
		cls = type.__new__(cls, name, bases, attrs)
		cls.__slots__ = tuple((*__dimensions__, *[f'__{i}' for i in __dimensions__]))
		cls.cls = cls

		# if name != 'MultiDimension':
		# 	for k, v in __dimensions__.items():
		# 		globals(k.title(), v)

		# cls.__dimensions__ = {**{v.__dimension__.value: v for v in __dimensions__.values()}, **{v.__dimension__: v for v in __dimensions__.values()}, **__dimensions__}

		# slots = [f'__d{i}'.upper() for i in range(1, len(dimensions) + 1)]
		# cls.dimensions = tuple(dimensions)
		# slotAnnotations = {k: v for k, v in zip(slots, cls.__dimensions__.values())}
		return cls

	@staticmethod
	def parseInt(dimensions) -> list[str]:

		if 0 < dimensions < 5:
			dimensions = ['x', 'y', 'z', 't'][:dimensions]
		elif dimensions == 0:
			raise ValueError('Dimensions cannot be 0')
		else:
			dimensions = [f'd{i}' for i in range(1, dimensions + 1)]
		return dimensions


class MultiDimension(metaclass=MultiDimensionMeta):

	def __init__(self, *T: Union[int, float, QPoint, QPointF, QSize, QSizeF, dict], absolute: bool = None, relative: bool = None, **kwargs):
		if len(T) == 1:
			T = T[0]
		if isinstance(T, (int, float)):
			T = [T] * len(self.__dimensions__)
		elif isinstance(T, dict):
			T = tuple(T[k] for k in self.__dimensions__)
		elif isinstance(T, (QPoint, QPointF, QSize, QSizeF)):
			T = T.toTuple()
		elif len(T) != len(self.__dimensions__):
			T = tuple(kwargs.get(k, 0) for k in self.__dimensions__)
		else:
			T = list(T)

		assert (len(T) == len(self.__dimensions__), 'Dimensions do not match')

		# for i in range(1, len(self.__slots__) + 1):
		# 	j = self.__dimensions__[i].__name__.split('.')[-1].lower()
		# 	if j in kwargs:
		# 		try:
		# 			T[i] = kwargs[j]
		# 		except IndexError:
		# 			T.append(kwargs[j])

		if relative is None and absolute is None:
			# if relative and absolute are both unset, infer from the values
			# if any of the values are integers and greater than 50, then the dimension is absolute
			if isinstance(T, Iterable) and len(T) == 1:
				_T = T[0]
			else:
				_T = T
			if isinstance(_T, (QPoint, QPointF, QSize, QSizeF)):
				_T = _T.toTuple()
			absolute = any((isinstance(t, int) or t.is_integer()) and t > 1 for t in _T)
		elif relative is not None and absolute is not None:
			raise ValueError('Cannot set both absolute and relative')
		elif relative is not None:
			absolute = not relative
		elif absolute is not None:
			pass

		# n = len(self.__slots__)
		# if isinstance(T, dict):
		# 	if len(T) != n:
		# 		raise ValueError(f'Expected {n} values, got {len(T)}')
		# 	for key, attrs in T.items():
		# 		cls = self.__annotations__[key]
		# 		setattr(self, f'__D{cls.__dimension__.value}', cls(**attrs))

		# if len(T) == 1:
		# 	T = T[0]
		# 	if isinstance(T, (QPoint, QPointF, QSize, QSizeF)):
		# 		T = T.toTuple()
		# 	elif isinstance(T, (int, float)):
		# 		T = (T, T)
		# 	elif isinstance(T, (tuple, list)):
		# 		if len(T) == 2:
		# 			T = T
		# 		else:
		# 			raise ValueError(f'Expected a tuple of length {n}')
		# 	else:
		# 		raise ValueError(f'Expected a tuple of length {n}')
		# elif len(T) == n:
		# 	pass
		# else:
		# 	raise ValueError(f'Expected a tuple of length {n}')
		annotations = [i for k, i in self.__annotations__.items() if k in self.__dimensions__]
		for cls, t, s in zip(annotations, T, self.__slots__):
			if isinstance(t, Dimension):
				t._absolute = absolute
			if not isinstance(t, dict):
				t = {'value': t}
			if absolute is not None:
				t['absolute'] = absolute
			value = cls(**t)
			setattr(self, s, value)

	# def __setattr__(self, key, value):
	# 	if key in self.__slots__:
	# 		super(MultiDimension, self).__setattr__(key, value)
	# 	elif key in self.__annotations__:
	# 		getattr(self, f'__{key}').value = float(value)
	#
	# def __getattr__(self, item):
	# 	if item in self.__annotations__:
	# 		item = f'__{item}'
	# 	return super(MultiDimension, self).__getattribute__(item)

	@property
	def absolute(self):
		return any([x.absolute for x in self])

	@property
	def relative(self):
		return any([x.relative for x in self])

	def toRelative(self, *V):
		assert len(V) == len(self)
		if any(d is None for d in V):
			raise ValueError('Expected at least one argument')
		value = []
		for i, d in enumerate(self):
			if d is not None:
				value.append(d.toRelative(V[i]))
		return self.cls(*value, relative=True)

	def setRelative(self, *V):
		assert len(V) == len(self)
		if any(d is None for d in V):
			raise ValueError('Expected at least one argument')
		for v, d in zip(V, self):
			d.setRelative(v)

	def toAbsolute(self, *V, setValue: bool = False):
		assert len(V) == len(self)
		if any(d is None for d in V):
			raise ValueError('Expected at least one argument')
		value = []
		for i, d in enumerate(self):
			if d is not None:
				value.append(d.toAbsolute(V[i]))
		return self.cls(*value, absolute=True)

	def setAbsolute(self, *V):
		assert len(V) == len(self)
		if any(d is None for d in V):
			raise ValueError('Expected at least one argument')
		for v, d in zip(V, self):
			d.setAbsolute(v)

	def toDict(self) -> dict[str, Union[int, float, bool]]:
		value = {i.name.lower(): i.toDict() for i in self}
		if sum(int(i['absolute']) for i in value.values()) in (len(self), 0):
			return {'absolute': self.absolute, **{i.name.lower(): i.value for i in self}}
		return value

	def toTuple(self) -> tuple[Dimension]:
		return tuple(self)

	def __int__(self) -> int:
		return int(self.size)

	def __eq__(self, other) -> bool:
		return self.x == other.x and self.y == other.rows

	def __hash__(self) -> int:
		return hash((self.x, self.y))

	def __repr__(self) -> str:
		return f'{self.__class__.__name__}({self})'

	def __str__(self) -> str:
		return self.__separator__.join(str(d) for d in self)

	def __iter__(self):
		return iter(getattr(self, v) for v in self.__dimensions__)

	# @cached_property
	# def _tuple(self) -> tuple[Dimension]:
	# 	return tuple(getattr(self, d) for d in self.__dimensions__)

	def __len__(self):
		return 2

	def __wrapOther(self, other: Any) -> tuple[float]:
		if isinstance(other, MultiDimension):
			pass
		elif isinstance(other, Iterable):
			other = tuple(*other)
		elif isinstance(other, (QPoint, QPointF, QSize, QSizeF, QRect, QRectF)):
			other = other.toTuple()
		elif isinstance(other, (int, float)):
			other = tuple(other)
		elif isinstance(other, dict):
			other = tuple(float(d) for d in self.values())
		elif all(hasattr(other, dimension) for dimension in self.dimensions):
			other = tuple(getattr(other, dimension) for dimension in self.dimensions)
		s = len(self)
		o = len(other)
		if s == o or o == 1:
			return other
		elif s > o and (mul := s % o) % 2 == 0:
			return tuple(i for j in ([*other] for x in range(mul)) for i in j)

		raise TypeError(f'Cannot convert {type(other)} to Size')

	def __bool__(self):
		return all(d is not None for d in self)

	def __add__(self, other: 'MultiDimension') -> 'MultiDimension':
		other = self.__wrapOther(other)
		return self.cls(map(lambda x, y: x + y, self, other))

	def __sub__(self, other: 'MultiDimension') -> 'MultiDimension':
		other = self.__wrapOther(other)
		return self.cls(map(lambda x, y: x - y, self, other))

	def __mul__(self, other: int) -> 'MultiDimension':
		other = self.__wrapOther(other)
		return self.cls(map(lambda x, y: x * y, self, other))

	def __truediv__(self, other: int) -> 'MultiDimension':
		other = self.__wrapOther(other)
		return self.cls(list(map(lambda x, y: x / y, self, other)))

	def __floordiv__(self, other: int) -> 'MultiDimension':
		other = self.__wrapOther(other)
		return self.cls(map(lambda x, y: x // y, self, other))

	def __mod__(self, other: int) -> 'MultiDimension':
		other = self.__wrapOther(other)
		return self.cls(map(lambda x, y: x % y, self, other))

	def __pow__(self, other: int) -> 'MultiDimension':
		other = self.__wrapOther(other)
		return self.cls(map(lambda x, y: x ** y, self, other))

	def __gt__(self, other: 'MultiDimension') -> bool:
		other = self.__wrapOther(other)
		return all(x > y for x, y in zip(self, other))

	def __lt__(self, other: 'MultiDimension') -> bool:
		other = self.__wrapOther(other)
		return all(x < y for x, y in zip(self, other))

	def __ge__(self, other: 'MultiDimension') -> bool:
		other = self.__wrapOther(other)
		return all(x >= y for x, y in zip(self, other))

	def __le__(self, other: 'MultiDimension') -> bool:
		other = self.__wrapOther(other)
		return all(x <= y for x, y in zip(self, other))

	def __eq__(self, other: 'MultiDimension') -> bool:
		other = self.__wrapOther(other)
		return all(x == y for x, y in zip(self, other))

	def __ne__(self, other: 'MultiDimension') -> bool:
		other = self.__wrapOther(other)
		return all(x != y for x, y in zip(self, other))

	def __and__(self, other: 'MultiDimension') -> 'MultiDimension':
		return self.cls(map(lambda x, y: x & y, self, other))


class Size(MultiDimension, dimensions=('width', 'height'), separator='×'):

	@overload
	def __init__(self, width: float, height: float) -> None: ...

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	def asQSize(self):
		return QSize(self.x, self.y)

	def asQSizeF(self):
		return QSizeF(self.x, self.y)


class Position(MultiDimension, dimensions=('x', 'y'), separator=', '):

	def __init__(self, x: float, y: float) -> None:
		...

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	def asQPoint(self):
		return QPoint(self.x, self.y)

	def asQPointF(self):
		return QPointF(self.x, self.y)

	@property
	def relativeLocation(self) -> LocationFlag:
		if self.x > 0.5:
			x = LocationFlag.Right
		elif self.x < 0.5:
			x = LocationFlag.Left
		else:
			x = LocationFlag.Center

		if self.y > 0.5:
			y = LocationFlag.Bottom
		elif self.y < 0.5:
			y = LocationFlag.Top
		else:
			y = LocationFlag.Center

		return x | y

	def __and__(self, other: Union['MultiDimension', LocationFlag]) -> 'MultiDimension':
		if isinstance(other, LocationFlag):
			return self.relativeLocation & other
		return self.cls(*map(lambda x, y: x & y, self, other))


class Margins(MultiDimension, dimensions=('left', 'top', 'right', 'bottom'), separator=', '):
	surface: _Panel

	@overload
	def __init__(self, surface: _Panel, left: float, top: float, right: float, bottom: float) -> None:
		...

	def __init__(self, surface: _Panel, *args, **kwargs):
		assert isinstance(surface, _Panel)
		assert hasattr(surface, 'geometry')
		self.surface: 'Panel' = surface
		super().__init__(*args, **kwargs)

	@property
	def horizontalSpan(self) -> float:
		if mostly(self.left.relative, self.right.relative):
			return self.relativeHorizontalSpan
		return self.absoluteHorizontalSpan

	@property
	def relativeHorizontalSpan(self) -> float:
		return round(1 - self.relativeLeft - self.relativeRight, 3)

	@property
	def absoluteHorizontalSpan(self) -> float:
		return round(self.surface.geometry.absoulueWidth - (self.absoluteLeft + self.absoluteRight), 3)

	@property
	def verticalSpan(self) -> float:
		if mostly(self.top.relative, self.bottom.relative):
			return self.relativeVerticalSpan
		return self.absoluteVerticalSpan

	@property
	def relativeVerticalSpan(self) -> float:
		return round(1 - self.relativeTop - self.relativeBottom, 3)

	@property
	def absoluteVerticalSpan(self) -> float:
		return round(self.surface.geometry.absoluteHeight - (self.absoluteTop + self.absoluteBottom), 3)

	def __getMargin(self, attr: Union[str, LocationFlag]) -> Union['Margins.Left', 'Margins.Right', 'Margins.Top', 'Margins.Bottom']:
		if isinstance(attr, LocationFlag) and attr.isEdge:
			return getattr(self, attr.name.lower())
		elif isinstance(attr, str) and attr.lower() in self.__dimensions__:
			return getattr(self, attr.lower())
		raise AttributeError(f'{attr} is not a valid attribute')

	def __values(self, *attrs: Union[str, LocationFlag], absolute: bool = True, values: tuple[float] = None) -> Union[List[float], float]:
		attrs = [self.__getMargin(attr) for attr in attrs]

		if values:
			if not isinstance(values, Iterable):
				values = [values]
			assert len(attrs) == len(values) or len(values) == 1
			if len(values) == 1:
				values *= len(attrs)

		surfaceSize = self.surface.geometry.absoluteSize()

		if values:
			for i, attr in enumerate(attrs):
				if attr.absolute == absolute:
					attr.value = values[i]
				elif attr.relative != absolute:
					attr.value = values[i]
				else:
					other = surfaceSize.width.value if attr.name.lower() in ('left', 'right') else surfaceSize.height.value
					attr.value = capValue(other * values[i], 0, other) if attr.absolute else capValue(values[i] / other, 0, 1)
			return None

		for i, attr in enumerate(attrs):
			if attr.absolute and absolute:
				attrs[i] = attr.value
			elif attr.relative and not absolute:
				attrs[i] = attr.value
			else:
				other = surfaceSize.width.value if attr.name.lower() in ('left', 'right') else surfaceSize.height.value
				attrs[i] = attr.value / other if attr.absolute else attr.value * other

		if len(attrs) == 1:
			return attrs[0]
		return attrs

	@property
	def absoluteLeft(self):
		if self.left.absolute:
			return self.left.value
		return self.surface.rect().width() * self.left.value

	@absoluteLeft.setter
	def absoluteLeft(self, value):
		if self.left.absolute:
			self.left.value = value
		else:
			self.left.value = value / self.surface.rect().width()

	@property
	def absoluteTop(self):
		if self.top.absolute:
			return self.top
		return self.surface.rect().height() * self.top.value

	@absoluteTop.setter
	def absoluteTop(self, value):
		if self.top.absolute:
			self.top.value = value
		else:
			self.top.value = value / self.surface.rect().height()

	@property
	def absoluteRight(self):
		if self.right.absolute:
			return self.right.value
		return self.surface.rect().width() * self.right.value

	@absoluteRight.setter
	def absoluteRight(self, value):
		if self.right.absolute:
			self.right.value = value
		else:
			self.right.value = value / self.surface.rect().width()

	@property
	def absoluteBottom(self):
		if self.bottom.absolute:
			return self.bottom.value
		return self.surface.rect().height() * self.bottom.value

	@absoluteBottom.setter
	def absoluteBottom(self, value):
		if self.bottom.absolute:
			self.bottom.value = value
		else:
			self.bottom.value = value / self.surface.rect().height()

	@property
	def relativeLeft(self):
		if self.left.relative:
			return self.left.value
		return self.surface.rect().width() * self.left.value

	@relativeLeft.setter
	def relativeLeft(self, value):
		if self.left.relative:
			self.left.value = value
		else:
			self.left.value = value / self.surface.rect().width()

	@property
	def relativeTop(self):
		if self.top.relative:
			return self.top.value
		return self.surface.rect().height() * self.top.value

	@relativeTop.setter
	def relativeTop(self, value):
		if self.top.relative:
			self.top.value = value
		else:
			self.top.value = value / self.surface.rect().height()

	@property
	def relativeRight(self):
		if self.right.relative:
			return self.right.value
		return self.surface.rect().width() * self.right.value

	@relativeRight.setter
	def relativeRight(self, value):
		if self.right.relative:
			self.right.value = value
		else:
			self.right.value = value / self.surface.rect().width()

	@property
	def relativeBottom(self):
		if self.bottom.relative:
			return self.bottom.value
		return self.surface.rect().height() * self.bottom.value

	@relativeBottom.setter
	def relativeBottom(self, value):
		if self.bottom.relative:
			self.bottom.value = value
		else:
			self.bottom.value = value / self.surface.rect().height()

	def absoluteValues(self, edges: List[Union[str, LocationFlag]] = LocationFlag.edges()) -> List[float]:
		return self.__values(*edges)

	def setAbsoluteValues(self, values: list[float], edges: List[Union[str, LocationFlag]] = LocationFlag.edges()) -> List[float]:
		return self.__values(*edges, values=values)

	def relativeValues(self, edges: List[Union[str, LocationFlag]] = LocationFlag.edges()) -> List[float]:
		return self.__values(*edges, absolute=False)

	def setRelativeValues(self, values: list[float], edges: List[Union[str, LocationFlag]] = LocationFlag.edges()) -> List[float]:
		return self.__values(*edges, absolute=False, values=values)

	def asQMarginF(self) -> QMarginsF:
		return QMarginsF(self.absoluteLeft, self.absoluteTop, self.absoluteRight, self.absoluteBottom)

	def asQMargin(self) -> QMargins:
		return QMargins(*[int(i) for i in self.absoluteValues()])

	@property
	def state(self):
		return {
			'left':   self.left,
			'top':    self.top,
			'right':  self.right,
			'bottom': self.bottom,
		}


def ISOsplit(s, split):
	'''https://stackoverflow.com/a/64232786/2975046'''
	if split in s:
		n, s = s.split(split)
	else:
		n = 0
	return n, s


def ISOduration(s: str) -> timedelta:
	# Remove prefix
	s = s.split('P')[-1]

	# Step through letter dividers
	days, s = ISOsplit(s, 'D')
	_, s = ISOsplit(s, 'T')
	hours, s = ISOsplit(s, 'H')
	minutes, s = ISOsplit(s, 'M')
	seconds, s = ISOsplit(s, 'S')
	a = timedelta(days=1)
	a.days

	return timedelta(days=int(days), hours=int(hours), minutes=int(minutes), seconds=int(seconds))


def hasState(obj):
	return hasattr(obj, 'state') and hasattr(obj, 'savable') and obj.savable


class Indicator(QGraphicsPathItem):
	savable = False
	color: QColor

	def __init__(self, parent: 'Panel', *args, **kwargs):
		super(Indicator, self).__init__(*args, **kwargs)
		self.setPath(self._path())
		self.setParentItem(parent)
		parent.signals.resized.connect(self.updatePosition)
		self.updatePosition()

	@property
	def color(self):
		return self.brush().color()

	@color.setter
	def color(self, value: QColor):
		self.setBrush(QBrush(value))
		self.update()

	def _path(self):
		path = QPainterPath()
		rect = QRect(-5, -5, 10, 10)
		path.addEllipse(rect)
		return path

	def updatePosition(self):
		parentRect = self.parentItem().rect()
		p = parentRect.bottomRight() - QPointF(10, 10)
		self.setPos(p)

	def itemChange(self, change, value):
		if change == QGraphicsItem.ItemParentChange:
			if value is None and self.scene() is not None:
				self.scene().removeItem(self)
		return super(Indicator, self).itemChange(change, value)


SimilarEdges = namedtuple('SimilarEdges', 'edge, otherEdge')

SimilarValue = namedtuple('SimilarValue', 'value, otherValue, differance')

Edge = namedtuple('Edge', 'parent, location, pix')


def similarEdges(rect: QRectF, other: QRectF):
	rect = rect.toRect()
	other = other.toRect()
	locations = {}
	rectEdgesV = {rect.left(), rect.right()}
	rectEdgesH = {rect.top(), rect.bottom()}
	otherEdgesV = {other.left(), other.right()}
	otherEdgesH = {other.top(), other.bottom()}
	if len(rectEdgesV + rectEdgesH + otherEdgesV + otherEdgesH) == 8:
		return False
	for edge in rectEdgesV:
		if edge in otherEdgesV:
			locations['v'] = SimilarEdges(edge, otherEdgesV.pop(edge))


KeyData = NamedTuple('KeyData', sender=dict, keys=set)


class Period(Enum):
	Now = wu.Time.Millisecond(0)
	Realtime = Now
	Minute = wu.Time.Minute(1)
	QuarterHour = wu.Time.Hour(0.25)
	HalfHour = wu.Time.Hour(0.5)
	Hour = wu.Time.Hour(1)
	Day = wu.Time.Day(1)
	Week = wu.Time.Week(1)
	Month = wu.Time.Month(1)
	Year = wu.Time.Year(1)

	def __wrapOther(self, other):
		if isinstance(other, wu.Time):
			return other
		elif isinstance(other, (int, float)):
			return wu.Time.Second(other)
		elif isinstance(other, timedelta):
			return wu.Time.Second(other.total_seconds())
		elif isinstance(other, datetime):
			return wu.Time.Second(other.timestamp())
		else:
			return self.__class__(other)

	def __lt__(self, other):
		return self.value < self.__wrapOther(other)

	def __gt__(self, other):
		return self.value > self.__wrapOther(other)

	def __eq__(self, other):
		return self.value == self.__wrapOther(other)

	def __le__(self, other):
		return self.value <= self.__wrapOther(other)

	def __ge__(self, other):
		return self.value >= self.__wrapOther(other)

	def __ne__(self, other):
		return self.value != self.__wrapOther(other)

	def __hash__(self):
		return hash(self.value.second)

	def __str__(self):
		return self.name

	def __repr__(self):
		return self.name

	def __int__(self):
		return int(self.value.second)

	def __float__(self):
		return float(self.value.second)

	def __bool__(self):
		return float(self.value.second) != 0

	def __add__(self, other):
		return self.value + self.__wrapOther(other)

	def __radd__(self, other):
		return self.__wrapOther(other) + self.value

	def __sub__(self, other):
		return self.value - self.__wrapOther(other)

	def __rsub__(self, other):
		return self.__wrapOther(other) - self.value

	def __mul__(self, other):
		return self.value*self.__wrapOther(other)

	def __floordiv__(self, other):
		return self.value//self.__wrapOther(other)

	def __truediv__(self, other):
		return self.value/self.__wrapOther(other)

	def __mod__(self, other):
		return self.value%self.__wrapOther(other)

	def __divmod__(self, other):
		return divmod(self.value, self.__wrapOther(other))

	def __abs__(self):
		return abs(self.value.second)

	def total_seconds(self):
		return int(self.value.second)


class ChannelSignal(QObject):
	__signal = Signal(list)
	__connections: dict[Hashable: Callable]

	def __init__(self, source, key):
		self.__connections = {}
		self.__key = key
		self.__source = source
		super(ChannelSignal, self).__init__()

	def __repr__(self):
		return f'Signal for {self.__source.name}:{self.__key}'

	def connectSlot(self, slot):
		self.__connections.update({slot.__self__: slot})
		self.__signal.connect(slot)

	def publish(self, sources: list['ObservationDict']):
		self.__signal.emit(sources)

	def disconnectSlot(self, slot):
		try:
			self.__connections.pop(slot.__self__)
			self.__signal.disconnect(slot)
		except RuntimeError:
			pass

	@property
	def hasConnections(self) -> bool:
		return len(self.__connections) > 0

	@property
	def key(self):
		return self.__key


def boolFilter(value: Any, raiseError: bool = False) -> bool:
	if not isinstance(value, bool):
		try:
			value = bool(value)
		except ValueError:
			if raiseError:
				raise TypeError('resizable must be a boolean')
			return False
	return value


class StrEnum(str, Enum):
	def __new__(cls, *args):
		for arg in args:
			if not isinstance(arg, (str, auto)):
				raise TypeError(
					"Values of StrEnums must be strings: {} is a {}".format(
						repr(arg), type(arg)
					)
				)
		return super().__new__(cls, *args)

	def __str__(self):
		return self.value

	# The first argument to this function is documented to be the name of the
	# enum member, not `self`:
	# https://docs.python.org/3.6/library/enum.html#using-automatic-values
	def _generate_next_value_(name, *_):
		return name


class DisplayType(str, Enum, metaclass=ClosestMatchEnumMeta):
	Numeric = 'numeric'
	Text = 'text'
	Gauge = 'gauge'
	Graph = 'graph'
	LinePlot = 'plot'
	BarGraph = 'bargraph'
	WindVein = 'windVein'
	Custom = 'custom'


class JsonEncoder(JSONEncoder):
	def default(self, obj):
		if hasattr(obj, 'toDict'):
			return obj.toDict()
		if hasattr(obj, 'state'):
			return obj.state
		if hasattr(obj, 'toJSON'):
			return obj.toJSON()
		if isinstance(obj, datetime):
			return obj.isoformat()
		if isinstance(obj, timedelta):
			return timedeltaToDict(obj)
		if isinstance(obj, Enum):
			return str(obj.name)
		if is_dataclass(obj):
			return asdict(obj)
		if hasattr(obj, 'toTuple'):
			return obj.toTuple()
		if hasattr(obj, '__getstate__'):
			return obj.__getstate__()
		try:
			return JSONEncoder.default(self, obj)
		except TypeError:
			return {obj.__class__.__name__: str(obj)}

	@classmethod
	def removeNullValues(cls, obj):
		if isinstance(obj, dict):
			return {k: cls.removeNullValues(v) for k, v in obj.items() if v is not None}
		if isinstance(obj, list):
			return [cls.removeNullValues(v) for v in obj if v is not None]
		return obj


def half(*args):
	v = tuple(map(lambda x: x/2, args))
	return v[0] if len(v) == 1 else v


class JsonDecoder:

	def __init__(self, APIs: dict):
		self.APIs = APIs
		import widgets
		self.widgets = {k: v for k, v in widgets.__dict__.items() if not k.startswith('_')}

	def __call__(self, object: dict):
		if 'plugins' in object:
			try:
				object['plugins'] = self.APIs[object['plugins']]
			except KeyError:
				pass
		if 'class' in object:
			try:
				object['class'] = self.widgets[object['class']]
			except KeyError:
				pass
		if 'displayType' in object:
			try:
				object['displayType'] = DisplayType[object['displayType']]
			except KeyError:
				object['displayType'] = DisplayType.Numeric
		if 'margins' in object:
			try:
				object['margins'] = Margins(**object['margins'])
			except KeyError:
				pass
		if 'position' in object:
			try:
				object['position'] = Position(**object['position'])
			except KeyError:
				pass
			except TypeError:
				pass
		if 'size' in object:
			try:
				object['size'] = MultiDimension(**object['size'])
			except KeyError:
				pass
			except TypeError:
				pass
		# if 'grid' in object:
		# 	try:
		# 		from src.Grid import Grid
		# 		object['grid'] = Grid(**object['grid'])
		# 	except KeyError:
		# 		pass
		if 'snapping' in object:
			try:
				from src.Grid import Snapping
				object['snapping'] = Snapping(**object['snapping'])
			except KeyError:
				pass
		# if 'valueLink' in object:
		# 	try:
		# 		object['valueLink'] = Subscription(**object['valueLink'])
		# 	except KeyError:
		# 		pass
		if 'alignment' in object:
			object['alignment'] = Alignment(**object['alignment'])
		if len(object) == 2 and 'key' in object and 'plugins' in object:
			return Subscription(**object)
		return object


class SizeWatchDog:
	callback: Callable
	step: int
	value: List[int]
	thresholds: List[int]

	def __init__(self, callback: Callable, step: int = 20):
		self.__exc = False
		self.__callback = callback
		self.step = step

	@property
	def step(self):
		return self._step

	@step.setter
	def step(self, value):
		self._step = value
		if isinstance(self.value, float):
			pass

	def relativeCheck(self, value):
		diff = any()

	def setAbsoluteThresholds(self, relative: float):
		self.thresholds = [int(x*relative) for x in self.value]

	def checkValue(self, value: Union[QSizeF, QSize, QPointF, QPoint, QRect, QRectF]):
		if isinstance(value, (QRect, QRectF)):
			value = value.size()
		self.width, self.height = value.toTuple()[-2:]

	@property
	def height(self):
		return self.__height

	@height.setter
	def height(self, value):
		value = int(value)
		if self.valueAtThreshold(self.__height, value):
			self.callback()
			self.__height = value

	def update(self, value: Union[QSizeF, QSize, QPointF, QPoint, QRect, QRectF]):
		self.x, self.y = value.toTuple()

	@property
	def width(self):
		return self.__width

	@width.setter
	def width(self, value):
		value = round(value)
		if self.valueAtThreshold(self.__width, value):
			self.callback()
			self.__width = value

	def valueAtThreshold(self, originalValue: int, value: int) -> bool:
		"""
		Returns True if the value has increased or decreased by the threshold
		:param value: The value to check
		:type value: int
		:param originalValue: The original value
		:type originalValue: int
		:return: True if the value has changed by the step amount
		:rtype: bool
		"""
		return abs(value - originalValue) >= self.step


def addOrdinal(n: Union[int, str]) -> str:
	"""
	Adds an ordinal to a number
	:param n: The number to add the ordinal to
	:type n: int
	:return: The number with the ordinal
	:rtype: str
	"""

	if 10 <= n%100 < 20:
		return str(n) + 'th'
	else:
		return str(n) + {1: 'st', 2: 'nd', 3: 'rd'}.get(n%10, 'th')


def strToOrdinal(s: str) -> str:
	"""
	Converts all integers in a string to their ordinal form
	:param s: The string to convert
	:type s: str
	:return: The string with all integers converted to their ordinal form
	:rtype: str
	"""
	return re.sub(r'\b(\d+)\b', lambda m: addOrdinal(int(m.group(1))), s)


def toOrdinal(n: Union[str, int]) -> str:
	"""
	Converts a number to an ordinal number
	:param n: The number to convert
	:type n: int
	:return: The ordinal number
	:rtype: str
	"""
	if isinstance(n, str):
		if not n.isdigit():
			return n
		n = int(n)
	return 'th' if 10 <= n%100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n%10, 'th')


class ResizeRect(QRectF):

	def __normalizeInput(self, other: Union[QSize, QSizeF, QPoint, QPointF, QRect, QRectF, tuple, MultiDimension]) -> tuple[float, float]:
		if isinstance(other, (QSize, QSizeF, QPoint, QPointF)):
			other = other.toTuple()
		elif isinstance(other, (QRect, QRectF)):
			if any(other.toTuple()):
				other.translate(*(other.topLeft()*-1).toPoint().toTuple())
			other = other.size().toTuple()
		elif isinstance(other, Iterable):
			other = tuple(other)
		elif isinstance(other, MultiDimension):
			other = tuple(other)
		return other[:2]

	def __add__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		return QRectF(0, 0, self.width() + other[0], self.height() + other[1])

	def __iadd__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		self.setWidth(self.width() + other[0])
		self.setHeight(self.height() + other[1])
		return self

	def __sub__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		return QRectF(0, 0, self.width() - other[0], self.height() - other[1])

	def __isub__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		self.setWidth(self.width() - other[0])
		self.setHeight(self.height() - other[1])
		return self

	def __mul__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		return QRectF(0, 0, self.width()*other[0], self.height()*other[1])

	def __imul__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		self.setWidth(self.width()*other[0])
		self.setHeight(self.height()*other[1])
		return self

	def __truediv__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		return QRectF(0, 0, self.width()/other[0], self.height()/other[1])

	def __itruediv__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		self.setWidth(self.width()/other[0])
		self.setHeight(self.height()/other[1])
		return self

	def __floordiv__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		return QRectF(0, 0, self.width()//other[0], self.height()//other[1])

	def __mod__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		return QRectF(0, 0, self.width()%other[0], self.height()%other[1])

	def __divmod__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		return QRectF(0, 0, self.width()//other[0], self.height()//other[1])

	def __pow__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		return QRectF(0, 0, self.width() ** other[0], self.height() ** other[1])

	def changeWidth(self, other):
		other = self.__normalizeInput(other)
		self.setWidth(self.width() + other[0])

	def changeHeight(self, other):
		other = self.__normalizeInput(other)
		self.setHeight(self.height() + other[1])

	def changeSize(self, other):
		other = self.__normalizeInput(other)
		self.setWidth(self.width() + other[0])
		self.setHeight(self.height() + other[1])

	def setLeft(self, other: float):
		if self.right() - other < 20:
			return
		super(ResizeRect, self).setLeft(other)

	def setRight(self, other: float):
		if other - self.left() < 20:
			return
		super(ResizeRect, self).setRight(other)

	def setTop(self, other: float):
		if self.bottom() - other < 20:
			return
		super(ResizeRect, self).setTop(other)

	def setBottom(self, other: float):
		if other - self.top() < 20:
			return
		super(ResizeRect, self).setBottom(other)


def polygon_area(path: Union[QPolygonF, QPolygon, QPainterPath, list, tuple]) -> float:
	if isinstance(path, (QPolygonF, QPolygon)):
		path = path.toList()
	elif isinstance(path, QPainterPath):
		path.closeSubpath()
		path = path.toFillPolygon().toList()
	if len(path) < 3:
		return 0
	x = [p.x() for p in path]
	y = [p.y() for p in path]

	"""https://stackoverflow.com/a/49129646/2975046"""
	correction = x[-1]*y[0] - y[-1]*x[0]
	main_area = np.dot(x[:-1], y[1:]) - np.dot(y[:-1], x[1:])
	return 0.5*np.abs(main_area + correction)


def disconnectSignal(signal: QObject, slot: Callable):
	try:
		signal.disconnect(slot)
	except TypeError:
		pass
	except RuntimeError:
		pass


def connectSignal(signal: QObject, slot: Callable):
	try:
		signal.connect(slot)
	except TypeError:
		log.warning('connectSignal: TypeError')
	except RuntimeError:
		log.warning('connectSignal: RuntimeError')


def replaceSignal(newSignal: Signal, oldSignal: Signal, slot: Callable):
	disconnectSignal(oldSignal, slot)
	newSignal.connect(slot)


class GraphicsItemSignals(QObject):
	"""
	A QObject that emits signals for the GraphicsItem.
	"""
	#: Signal emitted when the item is preferredSource.
	selected = Signal()
	#: Signal emitted when the item is deselected.
	deselected = Signal()
	#: Signal emitted when the item is resized.
	resized = Signal(QRectF)
	#: Signal emitted when the item is deleted.
	deleted = Signal()
	#: Signal emitted when a child item is added.
	childAdded = Signal()
	#: Signal emitted when a child item is removed.
	childRemoved = Signal()
	#: Signal emitted when the visibility changes.
	visibility = Signal(bool)
	#: Signal emitted when the parent is changed.
	parentChanged = Signal()
	#: Signal emitted when the item is transformed.
	transformChanged = Signal(QTransform)


class TestMeta:

	def __new__(cls, name: str, bases: tuple, attrs: dict, signals: dict[str, Type]) -> type:
		# assert that all bases are QObjects
		assert all(issubclass(b, QObject) for b in bases)

		# assert that all action names are strings
		assert all(isinstance(k, 'str') for k in signals)

		# assert that all action types are types
		assert all(isinstance(v, type) for v in signals.values())

		signals = {k: Signal(v, name=k) for k, v in signals.items()}
		signals = {**signals, **{k: Signal for k in attrs.get('__signals__', {})}}

		attrs['__signals__'] = signals
		attrs.update(signals)


class HandleItemSignals(QObject):
	action = Signal(LocationFlag, Axis)
	resized = Signal(Axis, QRectF, QRectF)


# def __new__(cls, *args, **kwargs):
# 	for key, value in (i for i in kwargs.items() if i[1] is None or isinstance(i[1], Type)):
# 		value = kwargs.pop(key)
# 		value = Signal(name=key) if value is None else Signal(value, name=key)
# 		setattr(cls, key, value)
# 	return super().__new__(cls, *args, **kwargs)
#
#
# def __init__(self, parent: QGraphicsItem):
# 	super().__init__(parent)
# 	self.parent = parent
# # def __init__(self, parent=None):
# # 	super(HandleItemSignals, self).__init__(parent)
#
# # def emit(self):
# # 	self.action.emit()
# #
# # def connect(self, slot):
# # 	self.action.connect(slot)


def resetState(state: dict) -> dict:
	state['isMovable'] = True
	state['resizable'] = True
	return state


@dataclass
class FileLocation:
	path: Path
	name: str
	extension: str = '.levity'

	def __post_init__(self):
		if self.path.is_file():
			self.path = self.path.parent
		if self.name.endswith(self.extension):
			self.name = self.name[:-len(self.extension)].strip('.')
			self.extension = self.extension.strip('.')
		elif '.' in self.name:
			path = self.name.split('.')
			self.name = '.'.join(path[:-1])
			self.extension = '.' + path[-1]

	@property
	def fullPath(self) -> Path:
		return self.path.joinpath(self.fileName)

	@property
	def fileName(self):
		return f'{self.name.rstrip(".")}.{self.extension.lstrip(".")}'

	@property
	def asTuple(self) -> Tuple[Path, str]:
		return self.path, self.fileName


class EasyPath:
	__basePath: Path

	def __init__(self, basePath: Union[str, Path]):
		if hasattr(basePath, 'path'):
			basePath = basePath.path
		self.__basePath = Path(basePath)

	def __getattr__(self, name: str):
		return EasyPath(self.__basePath.joinpath(name))

	def __getitem__(self, name: str):
		return EasyPath(self.__basePath.joinpath(name))

	@property
	def path(self):
		return self.__basePath

	def up(self, n: int = 1) -> 'EasyPath':
		if n < 1:
			n = 1
		up = self.__basePath
		for _ in range(n):
			up = up.parent
		return EasyPath(up)

	def ls(self):
		return [EasyPath(x) for x in self.__basePath.iterdir()]

	def __repr__(self):
		return str(self.__basePath.name)

	def __str__(self):
		return str(self.__basePath.name)


def findScene(*args, **kwargs):
	if 'scene' in kwargs and isinstance(kwargs['scene'], QGraphicsScene):
		return kwargs
	parent = kwargs.get('parent', None)
	if parent is not None:
		if hasattr(parent, 'scene'):
			kwargs['scene'] = parent.scene()
			return kwargs
		elif isinstance(parent, QGraphicsScene):
			kwargs['scene'] = parent
			return kwargs
	args = getItemsWithType(args, kwargs, QGraphicsScene)
	if args:
		kwargs['scene'] = args.pop(0)
	return kwargs


def findSizePosition(*args, **kwargs):
	if 'size' in kwargs and kwargs['size'] is not None:
		pass
	elif 'width' in kwargs and 'height' in kwargs:
		width, height = kwargs['width'], kwargs['height']
		if width is not None and height is not None:
			kwargs['size'] = QSizeF(kwargs.pop('width'), kwargs.pop('height'))
	else:
		kwargs['size'] = None
	if 'position' in kwargs and kwargs['position'] is not None:
		pass
	elif 'x' in kwargs and 'y' in kwargs:
		x, y = kwargs['x'], kwargs['y']
		if x is not None and y is not None:
			kwargs['position'] = QPointF(kwargs.pop('x'), kwargs.pop('y'))
	else:
		kwargs['position'] = None

	position = getItemsWithType(args, kwargs, Position)
	size = getItemsWithType(args, kwargs, QSize, QSizeF)
	from src.Geometry import Geometry
	geometry = getItemsWithType(args, kwargs, Geometry)

	if kwargs['size'] is None and size:
		kwargs['size'] = size.pop(0)
	if kwargs['position'] is None and position:
		if len(position) == 2:
			kwargs['position'] = position
	if kwargs.get('geometry', None) is None and geometry:
		kwargs['geometry'] = geometry.pop(0)
	if kwargs['size'] is None:
		kwargs.pop('size')
	if kwargs['position'] is None:
		kwargs.pop('position')
	if 'geometry' in kwargs and kwargs['geometry'] is None:
		kwargs.pop('geometry')
	return kwargs

	return kwargs


def findGrid(*args, **kwargs):
	from src.Grid import Grid
	args = {arg.grid if hasattr(arg, 'grid') else arg for arg in args if isinstance(arg, Grid) or hasattr(arg, 'grid')}
	kwargsSet = {arg.grid if hasattr(arg, 'grid') else arg for arg in kwargs.values() if isinstance(arg, Grid) or hasattr(arg, 'grid')}
	args = list(args.union(kwargsSet))

	assigned = [grid for grid in args if grid.surface is not None]
	unassigned = [grid for grid in args if grid.surface is None]
	if 'grid' not in kwargs:
		if assigned:
			kwargs['grid'] = assigned.pop(0)
		elif unassigned:
			kwargs['grid'] = unassigned.pop(0)
		else:
			kwargs['grid'] = None
	if unassigned:
		if 'subGrid' not in kwargs:
			kwargs['subGrid'] = unassigned.pop(0)
		else:
			kwargs['subGrid'] = None
	return kwargs


def sloppyIsinstance(obj, *args):
	# return any(isinstance(obj, arg) for arg in args)
	names = {cls.__name__.split('.')[-1] for cls in obj.__class__.mro()}
	classes = set()
	for arg in args:
		if not isinstance(arg, type):
			arg = type(arg)
		classes.add(arg.__name__.split('.')[-1])
	return bool(names.intersection(classes))


def findGridItem(*args, **kwargs):
	from src.Grid import GridItem
	if 'gridItem' in kwargs:
		return kwargs
	args = {arg.gridItem if hasattr(arg, 'gridItem') else arg for arg in args if isinstance(arg, GridItem) or hasattr(arg, 'gridItem')}
	kwargsSet = {arg.gridItem if hasattr(arg, 'gridItem') else arg for arg in kwargs.values() if isinstance(arg, GridItem) or hasattr(arg, 'gridItem')}
	args = list(args.union(kwargsSet))

	if args:
		kwargs['gridItem'] = args.pop(0)
	return kwargs


class mouseTimer(QTimer):
	_startPosition: QPointF
	_position: QPointF
	_timeout: Callable

	def __init__(self, timeout: Callable, interval: int = 500, singleShot: bool = True):
		self._timeout = timeout
		super(mouseTimer, self).__init__(interval=interval, timeout=self._T, singleShot=singleShot)

	def _T(self):
		self._timeout()

	def start(self, position: QPointF, *args):
		self._startPosition = position
		self._position = position
		super().start(*args)

	def updatePosition(self, position: QPointF):
		self._position = position

	def stop(self) -> None:
		self._startPosition = None
		self._position = None
		super().stop()

	@property
	def position(self):
		return self._position


class mouseHoldTimer(mouseTimer):

	def __init__(self, *args, holdArea: QRectF = None, **kwargs):
		if holdArea is None:
			holdArea = QRectF(0, 0, 10, 10)
		self._holdArea = holdArea
		super(mouseHoldTimer, self).__init__(*args, **kwargs)

	def start(self, position: QPointF):
		super(mouseHoldTimer, self).start(position)
		self._holdArea.moveCenter(self._startPosition)

	def updatePosition(self, position: QPointF):
		super(mouseHoldTimer, self).updatePosition(position)
		if not self._holdArea.contains(self._position):
			self.stop()

	def _T(self):
		if self._holdArea.contains(self._startPosition):
			super(mouseHoldTimer, self)._T()


class GridItemSize(Size):
	pass


class GridItemPosition(Position, dimensions=('column', 'row')):
	index: Optional[int] = None

	def __init__(self, *args: int, grid: 'Grid' = None):
		if isinstance(args[0], GridItemPosition):
			super(GridItemPosition, self).__init__(args[0].column, args[0].row)
		elif isinstance(args[0], Iterable):
			args = args[0]
		if len(args) == 1:
			if grid is None:
				raise ValueError('Grid must be specified when passing index')
			self.index = args[0]
			column, row = self.index%grid.columns, self.index//grid.columns
		else:
			column, row = args[0], args[1]

		if grid is not None:
			self.index = row*grid.columns + column
		super().__init__(column, row)


def clamp(value: Numeric, minimum: Numeric, maximum: Numeric) -> Numeric:
	"""
	Clamps a value between a minimum and maximum value.
	:param value: The value to clamp.
	:type value: float
	:param minimum: The minimum value.
	:type minimum: float
	:param maximum: The maximum value.
	:type maximum: float
	:return: The clamped value.
	:rtype: float
	"""
	return max(minimum, min(value, maximum))


class DateKey(datetime):

	def __new__(cls, value, roundedTo: timedelta = None, *args, **kwargs):
		if roundedTo is not None:
			if isinstance(roundedTo, Period):
				roundedTo = roundedTo.value
			method = int if roundedTo.total_seconds() >= 3600 else round
			value = roundToPeriod(value, roundedTo, method=method)
		return datetime.__new__(cls, year=value.year, month=value.month, day=value.day, hour=value.hour, minute=value.minute, second=value.second, tzinfo=value.tzinfo, *args, **kwargs)

	def __init__(self, value: Union[datetime, int, str], roundedTo: timedelta = None, *args, **kwargs):
		if isinstance(roundedTo, Period):
			roundedTo = roundedTo.value
		self.__roundedTo = roundedTo
		if isinstance(value, str):
			value = int(value)
		if isinstance(value, int):
			value = datetime.fromtimestamp(value, tz=config.tz)
		super(DateKey, self).__init__()

	def __repr__(self):
		delta: timedelta = self - datetime.now(tz=self.tzinfo)
		a: wu.Time = wu.Time.Second(int(delta.total_seconds()))
		return f"{'+' if a.hour > 0 else ''}{a.hour}"

	def __str__(self):
		return self.__repr__()

	def __len__(self):
		return 1

	def __hash__(self):
		return super().__hash__()

	def __eq__(self, other):
		return super().__eq__(other)

	def __ne__(self, other):
		return super().__ne__(other)

	def __getComparable(self, other):
		if isinstance(other, datetime):
			return other
		if isinstance(other, int):
			return timedelta(seconds=other)
		if hasattr(other, 'value') and isinstance(other.value, (datetime, timedelta)):
			return other.value
		if hasattr(other, 'value') and isinstance(other.value, int):
			return timedelta(seconds=other.value)
		if hasattr(other, 'timestamp') and other.timestamp is not None:
			return other.timestamp

	def __add__(self, other):
		other = self.__getComparable(other)
		return DateKey(value=super().__add__(other), roundedTo=self.__roundedTo)

	def __radd__(self, other):
		other = self.__getComparable(other)
		return DateKey(value=super().__radd__(other), roundedTo=self.__roundedTo)

	def __iadd__(self, other):
		other = self.__getComparable(other)
		value = DateKey(value=super().__add__(other), roundedTo=self.__roundedTo)
		self.__dict__.update(value.__dict__)

	def __sub__(self, other):
		other = self.__getComparable(other)
		value = super().__sub__(other)
		return DateKey(value=value, roundedTo=self.__roundedTo)

	def __rsub__(self, other):
		other = self.__getComparable(other)
		return DateKey(value=super().__rsub__(other), roundedTo=self.__roundedTo)

	def __isub__(self, other):
		value = DateKey(value=super().__sub__(other), roundedTo=self.__roundedTo)
		self.__dict__.update(value.__dict__)

	def __lt__(self, other):
		other = self.__getComparable(other)
		return super().__lt__(other)

	def __le__(self, other):
		other = self.__getComparable(other)
		return super().__le__(other)

	def __gt__(self, other):
		other = self.__getComparable(other)
		return super().__gt__(other)

	def __ge__(self, other):
		other = self.__getComparable(other)
		return super().__ge__(other)


def addCrosshair(painter: QPainter, color: QColor = Qt.red, size: int = 2.5, weight=1, pos: QPointF = QPointF(0, 0), *args, **kwargs):
	pen = QPen(color, weight)
	# pen.setCosmetic(Fa)
	painter.setPen(pen)
	verticalLine = QLineF(-size, 0, size, 0)
	verticalLine.translate(pos)
	horizontalLine = QLineF(0, -size, 0, size)
	horizontalLine.translate(pos)
	painter.drawLine(verticalLine)
	painter.drawLine(horizontalLine)


class TranslatorProperty:
	def __init__(self, source: 'ObservationDict', data: dict):
		self.source = source
		self.data = data

	def __get__(self):
		data = self.data
		source = self.source
		allowZero = data.get('allowZero', True)
		value = self.fromKey or self.fromAttr or self.default
		if not allowZero:
			return value or 1
		return value

	@property
	def default(self) -> Optional[Any]:
		if self.data.get('default', None) is None:
			return None
		data = self.data
		source = self.source
		unitCls = data['default'].get('unit', None)
		unitCls = source.units.get(unitCls, str)
		if unitCls is not None:
			value = data['default']['value']
			value = unitCls(value)
		else:
			value = data['default']
			if isinstance(value, dict):
				value = value['value']
		return value

	@property
	def fromKey(self) -> Optional[Any]:
		if 'key' in self.data and self.data['key'] in self.source:
			return self.source[self.data['key']]
		return None

	@property
	def fromAttr(self) -> Optional[Any]:
		if 'attr' in self.data and hasattr(self.source, self.data['attr']):
			return getattr(self.source, self.data['attr'])
		return None

	def __set__(self, instance, value):
		pass

	def __delete__(self, instance):
		pass

	def __call__(self, *args, **kwargs):
		return self.__get__(*args, **kwargs)


def roundToPeriod(value: datetime, period: timedelta, method: Callable = round) -> datetime:
	tz = value.tzinfo
	if period is None:
		return value
	if isinstance(period, (timedelta, Period)):
		seconds = period.total_seconds()
	elif isinstance(period, int):
		seconds = period
		period = timedelta(seconds=seconds)
	elif isinstance(period, (str, float)):
		seconds = int(period)
		period = timedelta(seconds=seconds)
	else:
		raise TypeError(f'period must be a timedelta, int, str or float, not {type(period)}')
	if period >= timedelta(days=1):
		return datetime.utcfromtimestamp((method(value.timestamp()/seconds))*seconds).astimezone(tz)
	return datetime.fromtimestamp((method(value.timestamp()/seconds)*seconds)).astimezone(tz)


def isSorted(iterable: Iterable, key: Callable = None, reverse: bool = False) -> bool:
	"""
	Checks if an iterable is sorted.
	:param iterable: The iterable to check.
	:type iterable: Iterable
	:param key: The key to sort by.
	:type key: Callable
	:param reverse: Whether to reverse the sort.
	:type reverse: bool
	:return: Whether the iterable is sorted.
	:rtype: bool
	"""
	if key is None:
		key = lambda x: x
	if reverse:
		return all(key(a) >= key(b) for a, b in zip(iterable, iterable[1:]))
	return all(key(a) <= key(b) for a, b in zip(iterable, iterable[1:]))


def datetimeFilterMask(value: timedelta):
	_ = [1, 60, 3600, 86400, 604800, 2592000, 31536000]
	if value is None:
		return None
	s = value.total_seconds()
	return [i%s for i in _]


def mostFrequentValue(iterable: Iterable) -> Any:
	"""
	Returns the most frequent value in an iterable.
	:param iterable: The iterable to check.
	:type iterable: Iterable
	:return: The most frequent value.
	:rtype: Any
	"""
	return max(set(iterable), key=iterable.count)


from datetime import timezone


def UTC():
	return datetime.utcnow().replace(tzinfo=timezone.utc)


def timestampToTimezone(timestamp: int, tz: str = timezone.utc) -> datetime:
	return datetime.fromtimestamp(timestamp, tz=tz)


def datetimeDiff(a, b) -> timedelta:
	return timedelta(seconds=abs(a.timestamp() - b.timestamp()))


def filterInstance(instance: object, filterType: Type) -> Optional[object]:
	if isinstance(instance, filterType):
		return instance
	return None


class Infix:
	def __init__(self, function):
		self.function = function

	def __ror__(self, other):
		return Infix(lambda x, self=self, other=other: self.function(other, x))

	def __or__(self, other):
		return self.function(other)

	def __rlshift__(self, other):
		return Infix(lambda x, self=self, other=other: self.function(other, x))

	def __rshift__(self, other):
		return self.function(other)

	def __call__(self, value1, value2):
		return self.function(value1, value2)

	def __rmatmul__(self, other):
		return Infix(lambda x, self=self, other=other: self.function(other, x))

	def __matmul__(self, other):
		return self.function(other)


class InfixModifier:
	def __init__(self, function):
		self.function = function

	def __or__(self, other):
		return self.function(other)

	def __ror__(self, other):
		return self.function(other)

	def __call__(self, value):
		return self.function(value)

	def __matmul__(self, other):
		return self.function(other)

	def __rmatmul__(self, other):
		return self.function(other)

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		pass


def asTitleCamelCase(value: str) -> str:
	return value[0].upper() + value[1:]


TitleCamelCase = InfixModifier(asTitleCamelCase)

isa = Infix(lambda x, y: (isinstance(x, y) and x))
isnot = Infix(lambda x, y: not isinstance(x, y) and x)

hasEx = Infix(lambda x, y: hasattr(x, y) and getattr(x, y))

isOlderThan = Infix(lambda x, y: (x - datetime.now(tz=x.tzinfo)) < -y)


def mostCommonClass(iterable: Iterable) -> Type:
	"""
	Returns the most common class in an iterable object.
	:param iterable: The iterable to check.
	:type iterable: Iterable
	:return: The most common class.
	:rtype: Type
	"""
	classes = [type(i) for i in iterable]
	if len(set(classes)) == 1:
		return classes.pop()
	return max(classes, key=lambda x: classes.count(x))


def AttrWatcherDecorator(instance: object, attr: str, callback: Callable):
	"""
	A decorator that watches an attribute of an object and calls a callback when it changes.
	:param instance: The object to watch.
	:type instance: object
	:param attr: The attribute to watch.
	:type attr: str
	:param callback: The callback to call.
	:type callback: Callable
	"""

	def getter(self):
		return getattr(self, attr)

	def setter(self, value):
		setattr(self, attr, value)
		callback(self)

	if hasattr(instance, attr):
		setattr(instance, attr, getattr(instance, attr))
	else:
		setattr(instance, attr, None)

	setattr(instance, 'get' + attr, getter)
	setattr(instance, 'set' + attr, setter)


class AttrWatcher:
	"""
	A class that runs a small coroutine loop to watch an attribute of an object and calls a callback when it changes.
	:param instance: The object to watch.
	:type instance: object
	:param attr: The attribute to watch.
	:type attr: str
	:param callback: The callback to call.
	:type callback: Callable
	:frequency: The frequency in Milliseconds to run the loop at.
	:type frequency: int
	"""

	def __init__(self, instance: object, attr: str, callback: Callable, frequency: int = 200):
		self.instance = instance
		self.attr = attr
		self.callback = callback
		self.frequency = frequency
		self.run()

	def run(self):
		self.running = True
		self.loop = asyncio.get_event_loop()
		self.loop.create_task(self.watch())

	async def watch(self):
		while self.running:
			await asyncio.sleep(self.frequency/1000)
			if hasattr(self.instance, self.attr):
				if getattr(self.instance, self.attr) != getattr(self.instance, '_' + self.attr):
					self.callback(self.instance)
					setattr(self.instance, '_' + self.attr, getattr(self.instance, self.attr))
			else:
				self.callback(self.instance)
				setattr(self.instance, '_' + self.attr, None)

	def stop(self):
		self.running = False


class Accumulator(QObject):
	__signal = Signal(set)
	__connections: Dict['CategoryItem', ChannelSignal]
	_data: set

	def __init__(self, observation: 'ObservationDict'):
		self.__hash = hash((observation, hash(id)))
		self.__observation = observation
		self.__connections = {}
		self._data = set()
		super(Accumulator, self).__init__()

	def __hash__(self):
		return self.__hash

	def publishKeys(self, *keys):
		self._data.update(keys)
		if not self.muted:
			asyncio.create_task(self.__emitChange())

	def publishKey(self, key):
		self.publishKeys(key, )

	@property
	def muted(self) -> bool:
		return self.signalsBlocked()

	@muted.setter
	def muted(self, value):
		self.blockSignals(value)
		if not value:
			asyncio.create_task(self.__emitChange())

	@property
	def observation(self):
		return

	async def __emitChange(self):
		if hasattr(self.__observation, 'log'):
			self.__observation.log.debug(f'Announcing keys: {abbreviatedIterable(self._data)}')
		self.__signal.emit(KeyData(self.__observation, self._data))
		self._data.clear()

	def connectSlot(self, slot: Slot):
		self.__signal.connect(slot)

	def disconnectSlot(self, slot: Slot):
		try:
			self.__signal.disconnect(slot)
		except RuntimeError:
			pass

	def connectChannel(self, channel: 'CategoryItem', slot: Slot):
		signal = self.__signals.get(channel, self.__addChannel(channel))
		signal.connectSlot(slot)

	def __addChannel(self, channel: 'CategoryItem'):
		self.__signals[channel] = ChannelSignal(self.source, channel)
		return self.__signals[channel]

	@property
	def lock(self) -> bool:
		return self.__observation.lock

	def __enter__(self):
		self.blockSignals(True)

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.blockSignals(False)
		asyncio.create_task(self.__emitChange())


def abbreviatedIterable(iterable: Iterable, maxLength: int = 5) -> str:
	iterable = list(iterable)
	if len(iterable) > maxLength:
		return f'{", ".join(str(i) for i in iterable[:maxLength - 1])} ... {iterable[-1]}'
	return f'{", ".join(str(i) for i in iterable)}'


def toLiteral(value: Any) -> Union[int, float, str, datetime, timedelta, time, date, bool]:
	while hasattr(value, 'value'):
		value = value.value
	if len(type(value).mro()) <= 3:
		return value
	elif isinstance(value, Measurement):
		return value
	typ = tuple({*type(value).mro()}.intersection((int, float, str, datetime, timedelta, time, date, bool)))
	if len(typ) == 1:
		return typ[0](value)
	for parentClass in type(value).mro()[1::-1]:
		log.critical(f'Using the very intensive part of toLiteral function for value {value} of type {type(value)}.  Find a way to avoid this!')
		try:
			return parentClass(value)
		except TypeError:
			pass
	else:
		return value


def now() -> datetime:
	"""Returns the current time as a timezone aware datetime object."""
	return datetime.now().astimezone()


class Now(datetime):
	__instance = None
	"""A Singleton class that returns the current time as a timezone aware datetime object."""

	def __new__(cls):
		if cls.__instance is None:
			cls.__instance = super(Now, cls).__new__(cls, 1970, 1, 1, 0, 0, 0, 0, tzinfo=timezone.utc)
		return cls.__instance

	def __eq__(self, other):
		return self.now() == other

	def __ne__(self, other):
		return self.now() != other

	def __lt__(self, other):
		return self.now() < other

	def __le__(self, other):
		return self.now() <= other

	def __gt__(self, other):
		return self.now() > other

	def __ge__(self, other):
		return self.now() >= other

	def __hash__(self):
		return hash(self.now())

	def __str__(self):
		return str(self.now())

	def __repr__(self):
		return repr(self.now())

	def __add__(self, other):
		return self.now() + other

	def __sub__(self, other):
		return self.now() - other

	def __rsub__(self, other):
		return other - self.now()

	def __int__(self):
		return int(self.now().timestamp())

	def __float__(self):
		return float(self.now().timestamp())

	@classmethod
	def now(cls):
		return datetime.now().astimezone()

	def __getattr__(self, item):
		if item == 'now':
			return super().__getattribute__(item)
		return getattr(self.now(), item)


def get(obj: Mapping, *keys: [Hashable], default: Any = Unset) -> Any:
	"""
	Returns the value of the key in the mapping.

	:param obj: The mapping to search.
	:param key: The keys to search for.
	:param default: The default value to return if the key is not found.
	:return: The value of the key in the mapping or the default value.
	"""
	values = list({obj.get(key, Unset) for key in keys} - {Unset})
	match len(values):
		case 0:
			if default is Unset:
				raise KeyError(f'{keys} not found in {obj}')
			return default
		case 1:
			return values[0]
		case _:
			log.warning(f'Multiple values found for {keys} in {obj}, returning first value.')
			return values[0]


import operator as __operator

operators = [getattr(__operator, op) for op in dir(__operator) if not op.startswith('__')]
operatorList = [
	(__operator.add, ('+')),
	(__operator.sub, ('-')),
	(__operator.mul, ('*', 'x', 'X')),
	(__operator.truediv, ('/', '÷')),
	(__operator.floordiv, ('//', '÷')),
	(__operator.mod, ('%', 'mod')),
	(__operator.pow, ('**', '^')),
	(__operator.lshift, ('<<', '<')),
	(__operator.rshift, ('>>', '>')),
	(__operator.and_, ('&', 'and')),
	(__operator.or_, ('|', 'or')),
	(__operator.xor, ('^', 'xor')),
	(__operator.neg, ('-', 'neg')),
	(__operator.pos, ('+', 'pos')),
	(__operator.invert, ('~', 'invert')),
	(__operator.lt, ('<', 'lt', 'min', 'minimum')),
	(__operator.le, ('<=', 'le', 'min=', 'minimum=')),
	(__operator.eq, ('==', '=', 'eq', 'equal', 'equals')),
	(__operator.ne, ('!=', '<>', 'ne', 'neq', 'not equal', 'not equals')),
	(__operator.ge, ('>=', 'ge', 'max=', 'maximum=')),
	(__operator.gt, ('>', 'gt', 'max', 'maximum')),
	(__operator.is_, ('is', 'is_', 'is a', 'is an', 'is_a', 'is_an', 'isA', 'isAn', 'isinstance')),
	(__operator.is_not, ('is not', 'is_not', 'is not a', 'is not an', 'is_not_a', 'is_not_an', 'isNot', 'isNotA', 'isNotAn', 'isnot', 'isnotA', 'isnotAn', 'not idinstance')),
	(__operator.contains, ('in', 'contains', 'contains', 'range')),
]
operatorDict = {name: op for op, names in operatorList for name in names}
del operatorList
del operators
