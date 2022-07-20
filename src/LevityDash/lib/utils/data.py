from enum import Enum
from functools import cached_property

from dataclasses import asdict, dataclass, is_dataclass
from json import JSONEncoder

from math import ceil, floor, inf
from numpy import ndarray
from typing import Any, Iterable, List, NamedTuple, Tuple, Union, Callable, Type, Set, Dict

from datetime import datetime, timedelta
import numpy as np
from PySide2.QtCore import QObject, QTimer, Signal
from scipy.signal import savgol_filter
from rich.repr import auto as auto_rich_repr

from LevityDash.lib.utils import Axis, clearCacheAttr, datetimeDiff, Infix, LOCAL_TIMEZONE, makeNumerical, Numeric, plural

from LevityDash.lib.utils import utilLog as log, timedeltaToDict


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
	if window%2 == 0:
		window -= 1
	if not type(data[0]) is datetime:
		data = savgol_filter(data, window, order)
	return data


@auto_rich_repr
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

	# self.__timer = QTimer(singleShot=True, interval=200)
	# self.__timer.timeout.connect(self.__emitChange)

	def invalidate(self):
		self.__varify = True

	@property
	def min(self) -> datetime:
		return self.__source.list[0].timestamp

	@property
	def max(self) -> datetime:
		try:
			return self.__source.list[-1].timestamp
		except IndexError:
			delattr(self.__source, 'list')
			return self.__source.list[-1].timestamp

	@property
	def range(self) -> timedelta:
		value = self.max - self.min
		if value != self.__range:
			self.__range = value
			self.__emitChange()
		return self.__range

	@property
	def source(self) -> 'GraphItemData':
		return self.__source

	def __emitChange(self):
		self.changed.emit(Axis.X)

	def __rich_repr__(self):
		yield 'source', self.__source.key.name
		if self.__source.hasData:
			yield 'range', self.range
			yield 'min', f'{self.min:%m-%d %H:%M}'
			yield 'max', f'{self.max:%m-%d %H:%M}'


TimeLineCollection = NamedTuple('TimeLineCollection', [('max', datetime), ('min', datetime), ('range', timedelta)])


@dataclass
class MinMax:
	min: Numeric
	max: Numeric

	def __init__(self, min: Numeric, max: Numeric):
		self._min = min
		self._max = max
		super().__init__()

	def setFromArray(self, arr: Iterable[Numeric] = None, key: str = None, plugin: 'Plugin' = None) -> None:
		from LevityDash.lib.plugins.observation import MeasurementTimeSeries
		if isinstance(arr, MeasurementTimeSeries):
			arr = arr.array
		else:
			arr = np.asarray([] if arr is None else arr)
		if plugin is not None and key is not None:
			try:
				arr = np.concatenate(plugin[key], arr)
			except KeyError:
				log.error(f"Key '{key}' not found in API: {plugin}")

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
	_link: 'Figure' = None
	__min: Numeric = None
	__max: Numeric = None

	def __init__(self, link: 'FigureRect'):
		super().__init__()
		self._link = link
		self.__delayTimer = QTimer(singleShot=True, interval=500, timeout=self.__emitChanged)

	@property
	def __actualMin(self) -> Numeric:
		if plots := self._link.plots:
			value = min(min(i.data[1]) for i in plots)
		else:
			value = self.__limits[0]
		value = max(value, self._link.lowerLimit)
		return max(value, self.__limits[0])

	@property
	def __limits(self) -> Tuple[float, float]:
		limits = getattr(self.dataType, 'typedLimits', (-inf, inf))
		return limits

	@property
	def dataType(self) -> Type[float]:
		return next((i.dataType for i in self._link.plots if i.hasData), float)

	@property
	def min(self):
		value = makeNumerical(self.__actualMin, float, self.__minModifier)
		if self.__min != value:
			self.__min = value
			self.emitChanged()
		return value

	@property
	def __actualMax(self) -> Numeric:
		if plots := self._link.plots:
			value = max(max(i.data[1]) for i in plots)
		else:
			value = self.__limits[1]
		value = min(self._link.upperLimit, value)
		return min(value, self.__limits[1])

	@property
	def max(self):
		figureMax = getattr(self._link, 'upperLimit', None)
		value = makeNumerical(self.__actualMax, float, self.__maxModifier)
		if self.__max != value:
			self.__max = value
			self.emitChanged()
		if figureMax is not inf and value < figureMax:
			return figureMax
		return value

	@property
	def range(self):
		return self.max - self.min

	@property
	def absoluteRange(self):
		return

	def emitChanged(self):
		self.changed.emit(Axis.Vertical)

	# self.__delayTimer.start()

	def __emitChanged(self):
		self.changed.emit(Axis.Vertical)

	@property
	def __maxModifier(self) -> Callable:
		diff = abs(self.__actualMax - self.__actualMin)
		if diff > 1:
			return ceil
		return lambda v: roundToPrecision(v, mask=diff, maxVal=True)

	@property
	def __minModifier(self) -> Callable:
		diff = abs(self.__actualMax - self.__actualMin)
		if diff > 1:
			return floor
		return lambda v: roundToPrecision(v, mask=diff, maxVal=False)

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

	def __repr__(self):
		d = self.dataType
		m = d(self.min)
		M = d(self.max)
		r = d(self.range)
		return f'AxisMetaData(figure={self._link}, min={m}, max={M}, range={r})'


def roundToPrecision(value: Numeric, mask: Numeric | None = None, maxVal: bool = True) -> Numeric:
	floatString = str(float(mask or value)).split('.')[1]
	roundTo = floatString.count('0', 1) + 1 if floatString[0] == '0' else 2
	incrementBy = float(f'0.{"".join(["0" for i in range(roundTo - 1)])}1')
	rounded = round(value, roundTo)
	if maxVal:
		if rounded < value:
			rounded += incrementBy
	else:
		if rounded > value:
			rounded -= incrementBy
	return rounded


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
	lookback : timedelta
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

	# TODO: Currently gets ignored when saving the settings.

	range: timedelta
	offset: timedelta
	negativeOffset: timedelta

	end: datetime
	start: datetime
	changed = Signal(Axis)

	def __init__(self, value: timedelta = None,
		offset: timedelta = timedelta(hours=-6),
		lookback: timedelta = timedelta(hours=-18),
		**kwargs):
		"""
		:param value: The length of time to display on the graph
		:type value: timedelta
		:param offset: The offset to apply to the start time
		:type offset: timedelta
		:param lookback: The offset to apply to the end time
		:type lookback: timedelta
		"""
		super(TimeFrameWindow, self).__init__()

		self.__delayTimer = QTimer(singleShot=True, interval=500, timeout=self.__emitChanged)

		self.offset = offset
		self.lookback = lookback

		if isinstance(value, dict):
			value = timedelta(**value)
		if value is None:
			value = timedelta(**kwargs)
		self._range = value

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
		if value is None:
			return
		if isinstance(value, dict):
			value = timedelta(**value)
		self._offset = value
		self.__clearCache()

	@property
	def historicalStart(self) -> datetime:
		return self.start + self._negativeOffset

	@property
	def start(self) -> datetime:
		start = datetime.now(tz=LOCAL_TIMEZONE).replace(second=0, microsecond=0)
		return start

	@property
	def displayPosition(self):
		return self.start + self.offset

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
		if value is None:
			return
		if self._range != value:
			if value < timedelta(hours=1):
				value = timedelta(hours=1)
			self.__clearCache()
			self._range = value
			self.changed.emit(Axis.Horizontal)
		print(self.range)

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
	def lookback(self):
		return self._negativeOffset

	@lookback.setter
	def lookback(self, value):
		if value is None:
			return
		if isinstance(value, dict):
			value = timedelta(**value)
		if value.total_seconds() > 0:
			value *= -1
		self._negativeOffset = value
		self.__clearCache()

	@property
	def combinedOffset(self):
		return self.offset + self.lookback

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
			'offset':   self.__exportTimedelta(self.offset),
			'lookback': self.__exportTimedelta(self.lookback)
		}
		return {k: v for k, v in state.items() if v}

	@state.setter
	def state(self, value):
		self.offset = value.pop('offset', None)
		self.lookback = value.pop('lookback', None)
		if isinstance(value, dict):
			value = timedelta(**value)
		self._range = value
		self.__clearCache()

	def delayedEmit(self):
		self.__delayTimer.start()

	def __emitChanged(self):
		self.changed.emit(Axis.Horizontal)

	def connectItem(self, slot):
		self.changed.connect(slot)

	def disconnectItem(self, slot):
		self.changed.disconnect(slot)

	def scoreSimilarity(self, other):
		if isinstance(other, dict):
			other = TimeFrameWindow(**other)
		rangeDiff = abs(self.range - other.range).total_seconds()
		offsetDiff = abs(self.offset - other.offset).total_seconds()
		lookbackDiff = abs(self.lookback - other.lookback).total_seconds()
		return (rangeDiff + offsetDiff + lookbackDiff)/3600


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
	Li[0] = np.sqrt(2*xdiff[0])
	Li_1[0] = 0.0
	B0 = 0.0  # natural boundary
	z[0] = B0/Li[0]

	for i in range(1, size - 1, 1):
		Li_1[i] = xdiff[i - 1]/Li[i - 1]
		Li[i] = np.sqrt(2*(xdiff[i - 1] + xdiff[i]) - Li_1[i - 1]*Li_1[i - 1])
		Bi = 6*(ydiff[i]/xdiff[i] - ydiff[i - 1]/xdiff[i - 1])
		z[i] = (Bi - Li_1[i - 1]*z[i - 1])/Li[i]

	i = size - 1
	Li_1[i - 1] = xdiff[-1]/Li[i - 1]
	Li[i] = np.sqrt(2*xdiff[-1] - Li_1[i - 1]*Li_1[i - 1])
	Bi = 0.0  # natural boundary
	z[i] = (Bi - Li_1[i - 1]*z[i - 1])/Li[i]

	# solve [L.T][x] = [y]
	i = size - 1
	z[i] = z[i]/Li[i]
	for i in range(size - 2, -1, -1):
		z[i] = (z[i] - Li_1[i - 1]*z[i + 1])/Li[i]

	# find index
	index = x.searchsorted(x0)
	np.clip(index, 1, size - 1, index)

	xi1, xi0 = x[index], x[index - 1]
	yi1, yi0 = y[index], y[index - 1]
	zi1, zi0 = z[index], z[index - 1]
	hi1 = xi1 - xi0

	# calculate cubic
	f0 = zi0/(6*hi1)*(xi1 - x0) ** 3 + \
	     zi1/(6*hi1)*(x0 - xi0) ** 3 + \
	     (yi1/hi1 - zi1*hi1/6)*(x0 - xi0) + \
	     (yi0/hi1 - zi0*hi1/6)*(xi1 - x0)
	return f0


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
	peaks = []
	troughs = []

	groupGenerator = TemporalGroups(array, spread=spread)
	for i, t, behind, ahead in groupGenerator:
		if not ahead:
			ahead = [array[-1]]
		if not behind:
			behind = [array[0]]

		if float(min(behind).value) >= t <= float(min(ahead).value):
			if len(troughs) == 0:
				troughs.append(t)
			elif datetimeDiff(troughs[-1].timestamp, t.timestamp) <= timedelta(hours=6):
				troughs[-1] += t
				p = troughs[-1]
			else:
				troughs.append(t)

		elif float(max(behind).value) <= t >= float(max(ahead).value):
			if len(peaks) == 0:
				peaks.append(t)
			elif datetimeDiff(peaks[-1].timestamp, t.timestamp) <= timedelta(hours=6):
				peaks[-1] += t
				p = peaks[-1]
			else:
				peaks.append(t)

	return peaks, troughs


KeyData = NamedTuple('KeyData', sender='Plugin', keys=Set['CategoryItem'] | Dict['Plugin', Set['CategoryItem']])


def mostFrequentValue(iterable: Iterable) -> Any:
	"""
	Returns the most frequent value in an iterable.
	:param iterable: The iterable to check.
	:type iterable: Iterable
	:return: The most frequent value.
	:rtype: Any
	"""
	return max(set(iterable), key=iterable.count)


isOlderThan = Infix(lambda x, y: (x - datetime.now(tz=x.tzinfo)) < -y)
