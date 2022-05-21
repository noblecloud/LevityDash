from types import FunctionType, GeneratorType

import operator as __operator
from sys import float_info

from collections import namedtuple

import re
import WeatherUnits as wu
from datetime import date, datetime, timedelta, timezone

import numpy as np
from dateutil.parser import parse as dateParser
from math import inf
from numpy import cos, radians, sin
from PySide2.QtGui import QPainterPath, QVector2D
from pytz import utc
from WeatherUnits import Measurement

from time import time
from typing import Any, Callable, Hashable, Iterable, List, Mapping, Optional, Tuple, Type, TypeVar, Union

from enum import auto, Enum, EnumMeta

from PySide2.QtCore import QObject, QPointF, QRectF, QSizeF, Signal
from PySide2.QtWidgets import QGraphicsRectItem

from LevityDash.lib.utils import utilLog


def simpleRequest(url: str) -> dict:
	from urllib.request import urlopen, Request
	from json import loads
	r = Request(url)
	with urlopen(r) as response:
		return loads(response.read())


class _Panel(QGraphicsRectItem):

	def isValid(self) -> bool:
		return self.rect().isValid()

	def size(self) -> QSizeF:
		return self.rect().size()


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
			if name == 0:
				return cls
			return cls(name)

	def representer(cls, dumper, data):
		return dumper.represent_scalar('tag:yaml.org,2002:str', str(data))


class IgnoreOr(object):

	def __or__(self, other):
		return other

	def __ror__(self, other):
		return other


Unset = IgnoreOr()
Auto = object()
DType = TypeVar('DimensionType')
Numeric = Union[int, float, complex, np.number]
LOCAL_TIMEZONE = datetime.now(timezone.utc).astimezone().tzinfo


def utcCorrect(utcTime: datetime, tz: timezone = None):
	"""Correct a datetime from utc to local time zone"""
	return utcTime.replace(tzinfo=utc).astimezone(tz or LOCAL_TIMEZONE)


def matchWildCard(x, y, wildcard: str = '*', namedWildcard: str = '@') -> bool:
	return x == y or any(str(i).startswith(namedWildcard) or i == wildcard for i in (x, y))


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


MAX_TIMESTAMP_INT = 253402318800


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
	tz = (timezone(tz) if isinstance(tz, str) else tz) or LOCAL_TIMEZONE

	if isinstance(value, str):
		try:
			if format:
				time = datetime.strptime(value, format)
			else:
				time = dateParser(value)
		except ValueError as e:
			utilLog.error('A format string must be provided.	Maybe dateutil.parser.parse failed?')
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


def clearCacheAttr(obj: object, *attr: str):
	for a in attr:
		try:
			delattr(obj, a)
		except AttributeError:
			pass


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


class ColorStr(str):
	__last__ = ''

	BOLD = '\033[1m'
	UNDERLINE = '\033[4m'
	ITALIC = '\033[3m'

	MAGENTA = '\033[95m'
	BLUE = '\033[94m'
	CYAN = '\033[96m'
	GREEN = '\033[92m'
	YELLOW = '\033[93m'
	RED = '\033[91m'

	CLEAR = '\033[0m'

	@classmethod
	def bold(cls, string: str = None):
		string = str(string) or cls.__last__
		cls.__last__ = f'{ColorStr.BOLD}{string}{ColorStr.CLEAR}'
		return cls.__last__

	@classmethod
	def underline(cls, string: str = None):
		string = str(string) or cls.__last__
		cls.__last__ = f'{ColorStr.UNDERLINE}{string}{ColorStr.CLEAR}'

	@classmethod
	def italic(cls, string: str = None):
		string = str(string) or cls.__last__
		cls.__last__ = f'{ColorStr.ITALIC}{string}{ColorStr.CLEAR}'

	@classmethod
	def magenta(cls, string: str = None):
		string = str(string) or cls.__last__
		cls.__last__ = f'{ColorStr.MAGENTA}{string}{ColorStr.CLEAR}'
		return cls.__last__

	@classmethod
	def blue(cls, string: str = None):
		string = str(string) or cls.__last__
		cls.__last__ = f'{ColorStr.BLUE}{string}{ColorStr.CLEAR}'
		return cls.__last__

	@classmethod
	def cyan(cls, string: str = None):
		string = str(string) or cls.__last__
		cls.__last__ = f'{ColorStr.CYAN}{string}{ColorStr.CLEAR}'
		return cls.__last__

	@classmethod
	def green(cls, string: str = None):
		string = str(string) or cls.__last__
		cls.__last__ = f'{ColorStr.GREEN}{string}{ColorStr.CLEAR}'
		return cls.__last__

	@classmethod
	def yellow(cls, string: str = None):
		string = str(string) or cls.__last__
		cls.__last__ = f'{ColorStr.YELLOW}{string}{ColorStr.CLEAR}'
		return cls.__last__

	@classmethod
	def red(cls, string: str = None):
		string = str(string) or cls.__last__
		cls.__last__ = f'{ColorStr.RED}{string}{ColorStr.CLEAR}'
		return cls.__last__

	@classmethod
	def clear(cls, string: str = None):
		string = str(string) or cls.__last__
		cls.__last__ = f'{string}{ColorStr.CLEAR}'
		return cls.__last__


def mostly(*args) -> bool:
	return sum(1 if bool(i) else 0 for i in args)/len(args) > 0.5


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
		elif d*d > v.lengthSquared():
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


def plural(func):
	def wrapper(*value, **kwargs):
		value = func(*value, **kwargs)
		return value[0] if len(value) == 1 else tuple(value)

	return wrapper


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


SimilarValue = namedtuple('SimilarValue', 'value, otherValue, differance')


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


def half(*args):
	v = tuple(map(lambda x: x/2, args))
	return v[0] if len(v) == 1 else v


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
		utilLog.warning('connectSignal: TypeError')
	except RuntimeError:
		utilLog.warning('connectSignal: RuntimeError')


def replaceSignal(newSignal: Signal, oldSignal: Signal, slot: Callable):
	disconnectSignal(oldSignal, slot)
	newSignal.connect(slot)


def sloppyIsinstance(obj, *args):
	# return any(isinstance(obj, arg) for arg in args)
	names = {cls.__name__.split('.')[-1] for cls in obj.__class__.mro()}
	classes = set()
	for arg in args:
		if not isinstance(arg, type):
			arg = type(arg)
		classes.add(arg.__name__.split('.')[-1])
	return bool(names.intersection(classes))


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
	return sorted([value, minimum, maximum])[1]


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
			value = datetime.fromtimestamp(value, tz=LOCAL_TIMEZONE)
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
		utilLog.critical(f'Using the very intensive part of toLiteral function for value {value} of type {type(value)}.  Find a way to avoid this!')
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
			utilLog.warning(f'Multiple values found for {keys} in {obj}, returning first value.')
			return values[0]


operators = [getattr(__operator, op) for op in dir(__operator) if not op.startswith('__')]
operatorList = [
	(__operator.add, ('+')),
	(__operator.sub, ('-')),
	(__operator.mul, ('*', 'x', 'X')),
	(__operator.truediv, ('/', '÷')),
	(__operator.floordiv, ('//', '÷')),
	(__operator.mod, ('mod', '%')),
	(__operator.pow, ('^', '**')),
	(__operator.lshift, ('<<',)),
	(__operator.rshift, ('>>',)),
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
operatorDict = {**{name: op for op, names in operatorList for name in names}, **{func: names[0] for func, names in operatorList}}


def getOrSet(d: dict, key: Hashable, value: Any, *args, **kwargs) -> Any:
	if key in d:
		return d[key]

	match value:
		case int() | float() | str() | bool() | list() | tuple() | dict() | set() | type(None):
			pass
		case GeneratorType(value):
			value = list(value)
		case [FunctionType() as _value, valueKwargs, valueArgs]:
			value = _value(*valueArgs, **valueKwargs)
		case FunctionType():
			value = value(*args, **kwargs)
		case [FunctionType() as _value, tuple(valueArgs) | list(valueArgs)]:
			value = _value(*valueArgs)
		case [FunctionType() as _value, dict(valueKwargs)]:
			value = _value(**valueKwargs)

	d[key] = value
	return value


def getOr(d: dict, *keys: Hashable, default: Any = Unset, expectedType: Type = Any) -> Any:
	for key in keys:
		if key in d and isinstance(d[key], expectedType):
			return d[key]
	if default is not Unset:
		return default
	raise KeyError(f'{keys} not found in {d}')
