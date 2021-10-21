import logging
from collections import namedtuple
from dataclasses import asdict, dataclass, field, InitVar
from datetime import datetime, timedelta
from enum import Enum, Flag
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


class Position(Flag):
	Top = 1
	Center = 2
	Bottom = 4
	Left = 8
	Right = 16

	TopLeft = Top | Left
	TopCenter = Top | Center
	TopRight = Top | Right

	CenterRight = Center | Right
	CenterLeft = Center | Left

	BottomLeft = Bottom | Left
	BottomCenter = Bottom | Center
	BottomRight = Bottom | Right

	Corners = TopLeft | TopRight | BottomLeft | BottomRight


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
