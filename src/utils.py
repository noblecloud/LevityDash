import logging
import re
from abc import ABC, ABCMeta, abstractmethod
from collections import namedtuple
from dataclasses import asdict, dataclass, field, InitVar
from datetime import datetime, timedelta
from enum import auto, Enum, EnumMeta, IntFlag
from functools import cached_property
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Tuple, Union

from sys import float_info

import numpy as np
from dateutil.parser import parse as dateParser
from numpy import ceil, floor, ndarray
from PySide2 import QtCore
from PySide2.QtCore import QObject, QPoint, QPointF, QRectF, Signal, Slot
from PySide2.QtGui import QFont, QPainterPath, QVector2D
from PySide2.QtWidgets import QGraphicsTextItem, QWidget
from pytz import timezone, utc
from WeatherUnits import Measurement

from src._config import config
from src.colorLog import ColoredLogger

logging.setLoggerClass(ColoredLogger)
log = logging.getLogger(__name__)

Numeric = Union[int, float, complex, np.number]


def utcCorrect(utcTime: datetime, tz: timezone = None):
	"""Correct a datetime from utc to local time zone"""
	return utcTime.replace(tzinfo=utc).astimezone(tz if tz else config.tz)


# def closest(lst: List, value: Any):
# 	return lst[min(range(len(lst)), key=lambda i: abs(lst[i] - value))]


def closest(lst: List, value):
	lst = np.asarray(lst)
	idx = (np.abs(lst - value)).argmin()
	return lst[idx]


# TODO: Look into using dateutil.parser.parse as a backup for if util.formatDate is given a string without a format
def formatDate(value, tz: Union[str, timezone], utc: bool = False, format: str = '', microseconds: bool = False):
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
	tz = timezone(tz) if isinstance(tz, str) else tz
	tz = tz if tz else config.tz

	if isinstance(value, str):
		try:
			if format:
				time = datetime.strptime(value, format)
			else:
				time = dateParser(value)
		except ValueError as e:
			logging.error('A format string must be provided.  Maybe dateutil.parser.parse failed?')
			raise e
	elif isinstance(value, int):
		time = datetime.fromtimestamp(value * 0.001 if microseconds else value)
	else:
		time = value
	return utcCorrect(time, tz) if utc else time.astimezone(tz)


def savitzky_golay(y, window_size, order, deriv=0, rate=1):
	'''https://scipy.github.io/old-wiki/pages/Cookbook/SavitzkyGolay'''
	r"""Smooth (and optionally differentiate) data with a Savitzky-Golay filter.
	The Savitzky-Golay filter removes high frequency noise from data.
	It has the advantage of preserving the original shape and
	features of the signal better than other types of filtering
	approaches, such as moving averages techniques.
	Parameters
	----------
	y : array_like, shape (N,)
		the values of the time history of the signal.
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
		the smoothed signal (or it's n-th derivative).
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
	plt.plot(t, y, label='Noisy signal')
	plt.plot(t, np.exp(-t**2), 'k', lw=1.5, label='Original signal')
	plt.plot(t, ysg, 'r', label='Filtered signal')
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
	if window_size % 2 != 1 or window_size < 1:
		raise TypeError("window_size minSize must be a positive odd number")
	if window_size < order + 2:
		raise TypeError("window_size is too small for the polynomials order")
	order_range = range(order + 1)
	half_window = (window_size - 1) // 2
	# precompute coefficients
	b = np.mat([[k ** i for i in order_range] for k in range(-half_window, half_window + 1)])
	m = np.linalg.pinv(b).A[deriv] * rate ** deriv * factorial(deriv)
	# pad the signal at the extremes with
	# values taken from the signal itself
	firstvals = y[0] - np.abs(y[1:half_window + 1][::-1] - y[0])
	lastvals = y[-1] + np.abs(y[-half_window - 1:-1][::-1] - y[-1])
	y = np.concatenate((firstvals, y, lastvals))
	return np.convolve(m[::-1], y, mode='valid')


def smoothData(data: np.ndarray, window: int = 25, order: int = 1) -> np.ndarray:
	if window % 2 == 0:
		window += 1
	if not type(data[0]) is datetime:
		data = savitzky_golay(data, window, order)
	return data


Size = namedtuple("Size", "h w")


@dataclass
class Subscription:
	api: 'API'
	key: str

	def __init__(self, api: 'API', key: str, subscriber: Any = None, signalFunction: Optional[Callable] = None):
		self._api: 'API' = api
		self._key: str = key
		self._subscriber: Any = subscriber
		self._signalFunction: Callable = signalFunction
		super(Subscription, self).__init__()

	@property
	def subscriber(self):
		return self._subscriber

	@subscriber.setter
	def subscriber(self, value):
		self._subscriber = value

	@property
	def key(self) -> str:
		return self._key

	@key.setter
	def key(self, value: str):
		self._key = value
		self.__updateSignal()

	@property
	def api(self):
		return self._api

	@api.setter
	def api(self, value: 'API'):
		self._api = value
		self.__updateSignal()

	def __updateSignal(self):
		if self.subscriber is not None:
			if self._signalFunction is not None:
				self.signal.disconnect(self._signalFunction)
				delattr(self, 'signal')
				self.signal.connect(self._signalFunction)
			else:
				self.signal.disconnect()
				delattr(self, 'signal')

	@property
	def signalFunction(self):
		return self._signalFunction

	@signalFunction.setter
	def signalFunction(self, value):
		self.signal.disconnect(self._signalFunction)
		self._signalFunction = value
		self.signal.connect(self._signalFunction)

	@cached_property
	def signal(self) -> Signal:
		return self._api.realtime.updateHandler.signalFor(self._key)

	def subscribe(self, func: Callable, subscriber: Any = None):
		if subscriber is None and self._subscriber is None:
			pass
		if subscriber is None:
			pass
		else:
			self._subscriber = subscriber
		self.signalFunction = func


class Axis(Enum):
	Vertical = 1
	Horizontal = 0
	y = Vertical
	x = Horizontal


@dataclass
class TimeFrame:
	minEpoch: int
	maxEpoch: int
	range: timedelta
	rangeSeconds: int
	__max: datetime = None
	__min: datetime = None

	def __init__(self, timeFrame: timedelta):
		self.__max = datetime.now() + timeFrame

	@property
	def min(self) -> datetime:
		return self.__min if self.__min is not None else datetime.now()

	@min.setter
	def min(self, value: datetime):
		self.__min = value

	@property
	def minEpoch(self) -> int:
		return int(self.min.timestamp())

	@property
	def max(self) -> datetime:
		return self.__max

	@max.setter
	def max(self, value: Union[datetime, timedelta]):
		if isinstance(value, timedelta):
			value = self.min + value
		self.__max = value

	@property
	def maxEpoch(self) -> int:
		return int(self.max.timestamp())

	@property
	def range(self) -> timedelta:
		return self.max - self.min

	@range.setter
	def range(self, value: timedelta):
		self.max = self.min + value

	@property
	def rangeSeconds(self) -> int:
		return int(self.range.total_seconds())

	@property
	def ptp(self):
		return self.range


@dataclass
class TimeLine(TimeFrame):
	__source: 'GraphItemData' = None

	def __init__(self, source: 'GraphItemData'):
		self.__source = source

	@property
	def max(self):
		return max(self._array)

	@property
	def min(self):
		return min(self._array)

	@property
	def _array(self):
		return [item.timestamp for item in self.__source.rawData]


TimeLineCollection = NamedTuple('TimeLineCollection', [('max', datetime), ('min', datetime), ('range', timedelta)])


@dataclass
class ArrayMetaData:
	min: Numeric
	max: Numeric
	range: Numeric
	_link: 'Figure' = None

	def __init__(self, link: 'Figure'):
		self._link = link

	@property
	def min(self):
		return makeNumerical(min([min(i.rawData) for i in self._link.data.values()]))

	@property
	def max(self):
		return makeNumerical(max([max(i.rawData) for i in self._link.data.values()]))

	@property
	def range(self):
		return self.max - self.min


@dataclass
class Margins:
	top: float = 0.1
	bottom: float = 0.1
	left: float = 0.0
	right: float = 0.0

	# def __init__(self, top, bottom, left, right):
	# 	self.top = top
	# 	self.bottom = bottom
	# 	self.left = left
	# 	self.right = right

	@property
	def vertical(self) -> float:
		return round(1.0 - max(self.top, self.bottom) - min(self.top, self.bottom), 2)

	@property
	def horizontal(self) -> float:
		return round(1.0 - max(self.right, self.left) - min(self.right, self.left), 2)

	def span(self, axis: Axis):
		return self.vertical if axis.value == 1 else self.horizontal

	@property
	def state(self):
		return asdict(self)


defaultMargins = Margins(0, 0, 0, 0)
temperatureMargins = Margins(0.1, 0.1, 0.0, 0)
precipitationMargins = Margins(top=0.7, bottom=0, left=0, right=0)


def normalize(a: Iterable, meta: Union[ArrayMetaData, TimeFrame] = None, useInterpolated: bool = True) -> np.ndarray:
	if useInterpolated and a.__class__.__name__ == 'GraphItemData':
		a = a.array

	# determine if array needs to be converted
	try:
		sum(a)
	except TypeError:
		a = list([makeNumerical(value) for value in a])

	if meta.__class__.__name__ == 'TimeFrame':
		min = meta.minEpoch
		ptp = meta.rangeSeconds
	elif meta.__class__.__name__ == 'ArrayMetaData':
		min = meta.min
		ptp = meta.range
	else:
		min = np.min(a)
		ptp = np.ptp(a)

	return (np.array(a) - min) / (ptp if ptp else 1)


def invertScale(a: np.ndarray) -> np.ndarray:
	'''https://stackoverflow.com/a/53936504/2975046'''
	ax = np.argsort(a)
	aax = np.zeros(len(ax), dtype='int')
	aax[ax] = np.arange(len(ax), dtype='int')
	return a[ax[::-1]][aax]


def autoDType(a: Iterable) -> Optional[np.dtype]:
	if not a:
		return None
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


def makeNumerical(value: Any, castAs: type = int) -> Numeric:
	if isinstance(value, (int, float, complex, np.number)):
		return castAs(value)
	elif isinstance(value, datetime):
		return castAs(value.timestamp())
	elif isinstance(value, timedelta):
		return castAs(value.total_seconds())
	return castAs(value)


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
		  A 1-D array of real/complex values.
	  y : (N,) array_like
		  A 1-D array of real values. The length of y along the
		  interpolation axis must be equal to the length of x.

	Implement a trick to generate at first step the cholesky matrice L of
	the tridiagonal matrice A (thus L is a bidiagonal matrice that
	can be solved in two distinct loops).

	additional ref: www.math.uh.edu/~jingqiu/math4364/spline.pdf
	"""
	x = np.asfarray(x)
	y = np.asfarray(y)

	# remove non finite values
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


def findPeaksAndTroughs(array: Iterable, spread: int = 12) -> tuple[list[list[int]], list[list[int]]]:
	peaks = []
	troughs = []
	maxI = len(array)
	for i, t in enumerate(array):
		ahead = array[i: min(i + spread, maxI)]
		behind = array[max(i - spread, 0):i]

		if not ahead:
			ahead = [array[-1]]
		if not behind:
			behind = [array[0]]
		t = t
		if min(behind) >= t <= min(ahead):
			if troughs and troughs[-1][0] == i - len(troughs[-1]):
				troughs[-1].append(i)
			else:
				troughs.append([i])
		if max(behind) <= t >= max(ahead):
			if peaks and peaks[-1][0] == i - len(peaks[-1]):
				peaks[-1].append(i)
			else:
				peaks.append([i])

	return peaks, troughs


def estimateTextFontSize(font: QFont, string: str, maxWidth: Union[float, int], maxHeight: Union[float, int]) -> tuple[float, float, QFont]:
	font = QFont(font)
	p = QPainterPath()
	p.addText(QtCore.QPoint(0, 0), font, string)
	rect = p.boundingRect()
	x, y = estimateTextSize(font, string)
	while x > maxWidth or y > maxHeight:
		size = font.pixelSize()
		if font.pixelSize() < 10:
			break
		font.setPixelSize(size - 3)
		x, y = estimateTextSize(font, string)
	return x, y, font


def estimateTextSize(font: QFont, string: str) -> tuple[float, float]:
	p = QPainterPath()
	p.addText(QtCore.QPoint(0, 0), font, string)
	rect = p.boundingRect()
	return rect.width(), rect.height()


def grabWidget(layout, index):
	item = layout.itemAt(index)
	if not isinstance(item, QWidget):
		item = item.widget()
	return item


# @dataclass
# class Subscription:
# 	name: 'str'
# 	key: InitVar[str] = field(init=True, default=None, repr=True)
# 	_key: str = field(init=False, default=None, repr=False)
# 	api: str = field(init=True, default=None)
# 	_api: 'API' = field(init=False, default=None, repr=False)
# 	signal: InitVar[Signal] = field(init=True, default=None)
# 	_signal: Signal = field(init=False, default=None, repr=False)
#
# 	def __init__(self, name: str, key: str = None, api: 'API' = None, signal: Signal = None):
# 		self.name = name
# 		self._key = key
# 		self._api = api
# 		self._signal = signal
#
# 	@property
# 	def key(self):
# 		return self._key
#
# 	@key.setter
# 	def key(self, value: str):
# 		self._key = value
#
# 	@property
# 	def api(self):
# 		return self._api
#
# 	@api.setter
# 	def api(self, value: 'API'):
# 		self._api = value
#
# 	@property
# 	def signal(self):
# 		return self._signal
#
# 	@signal.setter
# 	def signal(self, value: Signal):
# 		self._signal = value
#
# 	def connect(self, key: str, api: 'API'):
# 		self._key = key
# 		self._api = api
# 		self._signal = api.updateHandler.signalFor(key=self.key)
# 		curframe = currentframe()
# 		caller = getouterframes(curframe, 2)
# 		if isinstance(caller, 'Subscriber'):
# 			print('hi')


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
	newKey = Signal(Measurement)
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

	def _produceKey(self, key: str) -> SignalWrapper:
		wrapper = self._signals.get(key, None)
		if wrapper is None:
			wrapper = SignalWrapper(key, self.source)
			self._signals[key] = wrapper
		return wrapper

	def emitExisting(self, key: str):
		self._signals[key].emitUpdate()

	def new(self, key: str):
		self._signals[key] = SignalWrapper(key, self.source)
		value = self.source.get(key)
		self.newKey.emit(value)

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

	def autoEmit(self, keys: list[str]):
		for key in keys:
			super(ForecastUpdateHandler, self).autoEmit(key)

	@property
	def forecast(self) -> 'ObservationForecast':
		return self.source


class NewKeyDispatcher(QObject):
	_signal = Signal(str)
	_observation: 'ObservationRealtime'

	def __init__(self, observation: 'ObservationRealtime', *args, **kwargs):
		self._observation = observation
		super(NewKeyDispatcher, self).__init__(*args, **kwargs)

	@property
	def signal(self) -> Signal:
		return self._signal

	@property
	def observation(self) -> 'ObservationRealtime':
		return self._observation


class SmartString(str):
	_title = ''
	_subscriptionKey = ''

	def __new__(cls, value: str, title: str = None, subscriptionKey: str = None):
		return str(value)

	def __init__(self, value: str, title: str = None, subscriptionKey: str = None):
		self._subscriptionKey = subscriptionKey
		self._title = title
		super(SmartString, self).__init__(value)

	@property
	def title(self):
		return self._title

	@property
	def subscriptionKey(self):
		return self._subscriptionKey


def Logger(cls):
	cls._log = logging.getLogger(cls.__name__)
	return cls


# class Logger(object):
#
# 	def __init__(self, name: str = None):
# 		self.name = name
#
# 	def __call__(self, cls):
# 		class WrappedLogger(cls):
# 			test = self.name
# 			_log = logging.getLogger(self.name if self.name else cls.__name__)
#
# 			@property
# 			def log(self):
# 				return self._log
#
# 		return WrappedLogger


def climbFamilyTree(child, expectedClass):
	if isinstance(child, expectedClass):
		return child

	found = [child]
	overDrop = child

	try:
		while None not in (overDrop, overDrop.parent()) and not isinstance(overDrop, expectedClass):
			found.append(overDrop)
			overDrop = overDrop.parent()
	except (ValueError, AttributeError) as e:
		log.debug(f'FamilyTreeClimb hit the top ending with the final ancestor of {found[-1]}')
		log.debug(found)

	if overDrop is not None:
		child = overDrop
	else:
		child = found[-1]
	return child


def goToNewYork(start: Union[QWidget, QPoint], end: Union[QWidget, QPoint]):
	if isinstance(start, QWidget):
		start = start.geometry().center()
	if isinstance(end, QWidget):
		end = end.geometry().center()
	return (start - end).manhattanLength()


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


def relativePosition(item: 'Panel') -> LocationFlag:
	center = item.sceneRect().center()
	sceneRect = item.scene().sceneRect()
	if center.x() < sceneRect.center().x():
		x = LocationFlag.Left
	else:
		x = LocationFlag.Right
	if center.y() < sceneRect.center().y():
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
			return self.__class__(self * value, True)
		return self

	def toRelative(self, value: float) -> 'Dimension':
		if self._absolute:
			return self.__class__(self / value, False)
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


@dataclass
class Period:
	Minute: timedelta = timedelta(minutes=1)
	QuarterHour: timedelta = timedelta(minutes=15)
	HalfHour: timedelta = timedelta(minutes=30)
	Hour: timedelta = timedelta(hours=1)
	Day: timedelta = timedelta(days=1)
	Week: timedelta = timedelta(weeks=1)
	Month: timedelta = timedelta(days=31)
	Year: timedelta = timedelta(days=365)
