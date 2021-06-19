from datetime import datetime
from enum import Enum, Flag
from typing import Iterable, Union
import numpy as np
from PySide2 import QtCore
from PySide2.QtGui import QFont, QPainterPath
from pytz import timezone, utc

from _config import config
from dateutil.parser import parse as dateParser

import logging
from colorLog import ColoredLogger

logging.setLoggerClass(ColoredLogger)


def utcCorrect(utcTime: datetime, tz: timezone = None):
	"""Correct a datetime from utc to local time zone"""
	return utcTime.replace(tzinfo=utc).astimezone(tz if tz else config.tz)


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
		raise TypeError("window_size size must be a positive odd number")
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


def interpData(data: Union[list, np.ndarray], multiplier: int = 6) -> np.array:
	if type(data) is list:
		newLength = len(data) * multiplier
	elif type(data) is np.ndarray:
		newLength = data.size * multiplier
	else:
		newLength = 500

	if isinstance(data, list):
		data = np.array(data).flatten()
	if isinstance(data[0], datetime):
		time = np.array(list(map((lambda i: i.timestamp()), data)))
		new_x = np.linspace(min(time), max(time), num=newLength)
		interpTime = np.interp(new_x, time, time)
		return np.array(list(map((lambda i: datetime.fromtimestamp(i, tz=config.tz)), interpTime))).flatten()
	else:
		new_x = np.linspace(min(data), max(data), num=newLength)
		y = np.linspace(min(data), max(data), num=len(data))
		return np.interp(new_x, y, data)


def filterBest(arr, data, high: bool):
	from math import inf
	newArr = []
	clusters = enumerate(arr)
	for i, cluster in clusters:
		if cluster:
			T = -inf
			I: int = cluster[0]
			for j in cluster:
				IT = data[j]
				comparison = IT > T if high else IT < T
				I, T = (j, IT) if comparison else (I, T)
			newArr.append(I)
	return newArr


def randomColor(min: int = 0, max: int = 255, prefix: str = '#') -> str:
	from random import randrange
	rgb = [0, 0, 0]
	while sum(rgb) < 300 or any(map(lambda x: x > 200, rgb)) and any(map(lambda x: x < 50, rgb)):
		rgb = list(map(lambda _: randrange(min, max, 1), rgb))
	return prefix + ''.join([f'{i:02x}' for i in rgb]).upper()


def plural(func):
	def wrapper(*value):
		value = func(*value)
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


@plural
def findPeaks(*arrays: list[Iterable], spread: int = 9) -> tuple[list, ...]:
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


def estimateTextFontSize(font: QFont, string: str, maxSize: tuple[Union[float, int], Union[float, int]]) -> tuple[float, float, QFont]:
	font = QFont(font)
	p = QPainterPath()
	p.addText(QtCore.QPoint(0, 0), font, string)
	rect = p.boundingRect()
	x, y = estimateTextSize(font, string)
	while x > maxSize[0] or y > maxSize[1]:
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


def Logger(cls):
	cls._log = logging.getLogger(cls.__name__)
	return cls


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
