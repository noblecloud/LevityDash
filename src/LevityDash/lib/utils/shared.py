from abc import abstractmethod
from asyncio import get_event_loop, iscoroutine
from collections.abc import MutableSet, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import cached_property, lru_cache, partial, wraps
from traceback import format_exc, print_exc

from gc import get_referrers
from PySide2 import QtCore

try:
	from locale import setlocale, LC_ALL, nl_langinfo, RADIXCHAR, THOUSEP

	setlocale(LC_ALL, '')
	RADIX_CHAR = nl_langinfo(RADIXCHAR) or '.'
	GROUPING_CHAR = nl_langinfo(THOUSEP) or ','
except ImportError:
	RADIX_CHAR = '.'
	GROUPING_CHAR = ','

import operator as __operator
from sys import exc_info, float_info

from collections import namedtuple, defaultdict, ChainMap

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
from typing import (
	Any, Awaitable, Callable, Coroutine, ForwardRef, Hashable, Iterable, List, Mapping, NamedTuple, Optional, Tuple, Type,
	TYPE_CHECKING, TypeVar, Union, Set, Final, ClassVar, Dict, Protocol, runtime_checkable, get_args
)
from types import NoneType, GeneratorType, FunctionType, UnionType

from enum import Enum, EnumMeta, IntFlag

from PySide2.QtCore import QObject, QPointF, QRectF, QSizeF, QThread, Signal, Qt, Slot
from PySide2.QtWidgets import QApplication, QGraphicsRectItem, QGraphicsItem

from LevityDash.lib.utils import utilLog

numberRegex = re.compile(fr"""
	(?P<number>
	[-+]?
	([\d{GROUPING_CHAR}]+)?
	([{RADIX_CHAR}]\d+)?)
	""", re.VERBOSE)


def simpleRequest(url: str) -> dict:
	from urllib.request import urlopen, Request
	from json import loads
	r = Request(url)
	with urlopen(r) as response:
		return loads(response.read())


T_ = TypeVar('T_')


class _Panel(QGraphicsRectItem):

	def isValid(self) -> bool:
		return self.rect().isValid()

	def size(self) -> QSizeF:
		return self.rect().size()


class ClosestMatchEnumMeta(EnumMeta):
	_allMembersUnique: bool
	_firstLetters: Set[str]

	def __new__(metacls, cls, bases, classdict, **kwds):
		if IntFlag in bases:
			pass
		enum_class = super().__new__(metacls, cls, bases, classdict, **kwds)
		for k, v in metacls.__dict__.items():
			if not k.startswith('_'):
				setattr(enum_class, k, v)
		uniqueLetters = {k[0].casefold() for k in enum_class.__members__.keys()}
		setattr(enum_class, '_firstLetters', uniqueLetters)
		setattr(enum_class, '_allMembersUnique', len(uniqueLetters) == len(enum_class.__members__))
		return enum_class

	def __getitem__(cls, name):
		if isinstance(name, str):
			if name not in cls.__members__:
				name = name.title()
				if name not in cls.__members__:
					firstLetter = name[0].casefold()
					if cls._allMembersUnique and firstLetter in cls._firstLetters:
						weightedName = next(v for k, v in cls.__members__.items() if k.startswith(name[0]))
						if len(name) == 1 and name.casefold() == weightedName.name[0].casefold():
							return weightedName
						weightedName = weightedName.name
					else:
						weightedName = None

					# Truncate the member names to the length of the shortest member name
					# This prevents bad matches where short names are scored lower than long names
					# even when the short name is more similar to the long name
					maxNameLength = max(len(k) for k in cls.__members__.keys())
					truncatedNames = [i.ljust(maxNameLength) for i in list(cls.__members__.keys())]
					guessedMame = closestStringInList(name, truncatedNames).strip()
					if weightedName is not None and weightedName != name:
						weightedNameScore = levenshtein(name, weightedName)
						guessedNameScore = levenshtein(name, guessedMame)
						ratio = guessedNameScore/weightedNameScore
						if ratio < 0.8:
							return cls.__members__[weightedName]
					return cls.__members__[guessedMame]
			return cls.__members__[name]

		if isinstance(name, int):
			if name == 0:
				return cls
			return cls(name)

	def representer(cls, dumper, data):
		if isinstance(data.value, str):
			return dumper.represent_str(data.value)
		return dumper.represent_scalar('tag:yaml.org,2002:str', data.name)


def find_name(obj):
	for referrer in get_referrers(obj):
		if isinstance(referrer, dict):
			for k, v in referrer.items():
				if v is obj:
					return k
	return None


class IgnoreOr(object):

	def __init__(self, name: str):
		self.__name__ = name

	def copy(self):
		return self

	def __copy__(self):
		return self

	def __repr__(self):
		return f'<{self.__name__}>'

	def __or__(self, other):
		return other

	def __ror__(self, other):
		return other

	def __bool__(self):
		return False

	def __neg__(self):
		return self

	def __invert__(self):
		return self

	def __eq__(self, other):
		return self is other

	def __ne__(self, other):
		return self is not other

	def __hash__(self):
		return hash((self.__name__, type(self)))

	def __instancecheck__(self, instance):
		return self is instance

	def get(self, *args, **kwargs):
		return self


Unset: Final = IgnoreOr('Unset')
UnsetKwarg: Final = IgnoreOr('UnsetKwarg')

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
			del obj.__dict__[a]
			continue
		except AttributeError:
			pass
		except KeyError:
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


@runtime_checkable
class Mutable(Protocol):
	muted: bool
	_muteLevel: int

	def __hash__(self) -> int: ...

	def __enter__(self): ...

	def __exit__(self, exc_type, exc_val, exc_tb): ...

	@abstractmethod
	def setMute(self, mute: bool): ...


class BusyContext:
	blocker: ClassVar[QGraphicsItem | None] = None

	_tasks: ClassVar[Dict[Hashable, int]] = defaultdict(int)

	def __init__(self, mutable: Mutable | None = None, task: Hashable | None = None):
		self._mutable = mutable
		self._task = task

	@property
	def __taskHash__(self):
		hash_ = []
		if self._mutable is not None:
			hash_.append(hash(self._mutable))
		if self._task is not None:
			hash_.append(hash(self._task))
		return hash(*hash_)

	def __enter__(self):
		if isinstance(self._mutable, Mutable):
			self._mutable.muted = True
		qApp.setOverrideCursor(Qt.WaitCursor)
		BusyContext._tasks[self.__taskHash__] += 1
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		BusyContext._tasks[self.__taskHash__] -= 1
		qApp.restoreOverrideCursor()
		if not BusyContext._tasks[self.__taskHash__]:
			BusyContext._tasks.pop(self.__taskHash__, None)
			if isinstance(self._mutable, Mutable):
				self._mutable.muted = False

	@classmethod
	@property
	def isBusy(cls) -> bool:
		return sum(cls._tasks.values()) > 0


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


def getFirstList(a: List, default: Any = None) -> Any:
	if a:
		return a[0]
	return default


def getLastList(a: List, default: Any = None) -> Any:
	if len(a):
		return a[-1]
	return default


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
		if isinstance(value, str):
			match value.lower():
				case 'true' | 't' | '1' | 'yes' | 'y' | 'on':
					return True
				case 'false' | 'f' | '0' | 'no' | 'n' | 'off' | 'none' | 'null' | 'nil':
					return False
				case _:
					raise ValueError(f"Invalid boolean string value: {value}")
		try:
			value = bool(value)
		except ValueError:
			if raiseError:
				raise TypeError(f"Invalid boolean value: {value}")
			return False
	return value


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

	if 10 <= int(n) % 100 < 20:
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


def chainFunctions(*functions: Callable[[T_], T_]) -> Callable[[T_], T_]:
	"""
	Combines multiple functions into one with each value passed to the next function
	:param functions: The functions to combine
	:type functions: Callable
	:return: The combined function
	:rtype: Callable
	"""
	def combinedFunction(value):
		for function in functions:
			value = function(value)
		return value
	return combinedFunction


class FunctionEnumFlagMeta(ClosestMatchEnumMeta):

	class FlagFunctionDict(dict):

		def __init__(self, enum, *args, **kwargs):
			self.__enum = enum
			super().__init__(*args, **kwargs)

		@property
		def enum(self):
			enum = self.__enum
			if isinstance(enum, str | ForwardRef):
				if isinstance(enum, str):
					enum = ForwardRef(enum)
				self.__enum = enum = enum._evaluate(globals(), locals(), set())
			return enum

		def __missing__(self, key: int):
			functions = []
			for name, member in self.enum.__members__.items():
				if member.value & key:
					functions.append(self[member.value])
			if not functions:
				raise KeyError(key)
			self[key] = chainFunctions(*functions)
			return functions


	def __new__(mcs, name, bases, namespace, **kwargs):
		functions = FunctionEnumFlagMeta.FlagFunctionDict(name)
		namespace._last_values.clear()
		namespace._member_names.clear()
		for key in (k for k, v in tuple(namespace.items()) if not k.startswith('_') and callable(v)):
			func = namespace.pop(key)
			value = IntFlag._generate_next_value_(name, 1, len(functions), functions)
			functions[value] = func
			namespace[key] = value

		namespace['__functions__'] = functions

		return super().__new__(mcs, name, bases, namespace, **kwargs)


class TextFilter(IntFlag, metaclass=FunctionEnumFlagMeta):
	__functions__: Dict[int, Callable[[str], str]]
	value: int

	Ordinal = toOrdinal
	AddOrdinal = strToOrdinal
	Lower = str.lower
	Upper = str.upper
	Title = str.title
	Capitalize = str.capitalize

	def __repr__(self):
		return f'TextFilter({self.name})'

	def __call__(self, value):
		return self.__functions__[self.value](value)


def disconnectSignal(signal: Signal, slot: Callable) -> bool:
	try:
		return signal.disconnect(slot)
	except TypeError:
		pass
	except RuntimeError:
		pass
	except Exception as e:
		utilLog.warning("Error disconnecting signal", exc_info=True)
		utilLog.exception(e)
	return False


def connectSignal(signal: Signal, slot: Callable) -> bool:
	try:
		return signal.connect(slot)
	except TypeError:
		utilLog.warning('connectSignal: TypeError')
	except RuntimeError:
		utilLog.warning('connectSignal: RuntimeError')
	except Exception as e:
		utilLog.warning('connectSignal: %s', e)
		utilLog.exception(e)
	return False


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


def clamp(value: Numeric, minimum: Numeric, maximum: Numeric, key: Callable = None) -> Numeric:
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
	return sorted([value, minimum, maximum], key=key)[1]


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


def floorToPeriod(value: datetime, period: timedelta) -> datetime:
	return roundToPeriod(value, period, method=int)


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


def __or__(a, b):
	if isinstance(a, IgnoreOr):
		return b
	elif isinstance(b, IgnoreOr):
		return a
	return a


def atomizeString(var: str | list[str], itemFilter: Callable = None) -> List[str]:
	"""
	Splits a string into a list of words.
	:param var: The string to split.
	:type var: str
	:return: The list of words.
	:rtype: List[str]
	"""
	if isinstance(var, (tuple, list)):
		var = ' '.join(var)
	# TODO: Improve so that it breaks up on numbers.
	var = re.findall(r'((?=[A-Z_\d]?)[A-Z\d]?[A-Za-z\d][a-z\d]+)', var)
	if itemFilter is not None:
		var = [itemFilter(i) for i in var]
	return var


def camelCase(value: List[str] | str, titleCase=True, itemFilter: Callable = None) -> str:
	"""
	Converts a list of words into a camel case string.
	:param value: The list of words to convert.
	:type value: List[str]
	:param titleCase: Whether to capitalize the first letter of the first word.
	:type titleCase: bool
	:return: The camel case string.
	:rtype: str
	"""
	value = atomizeString(value)
	value = [i.lower().title() for i in value]
	if not titleCase:
		value[0] = value[0].lower()
	value = ''.join(value)
	if itemFilter is not None:
		value = itemFilter(value)
	return value


def joinCase(value: List[str] | str, joiner: str | List[str] = ' ', valueFilter: Callable = None, itemFilter: Callable = None) -> str | List[str]:
	"""
	Converts a list or string of words into a new case joined by string.
	:param value: The list of words to convert.
	:type value: List[str]
	:param joiner: The string to join the words with.
	:type joiner: str
	:return: The snake case string.
	:rtype: str
	"""
	value = atomizeString(value, itemFilter)
	if isinstance(joiner, (list, tuple)):
		val = [joinCase(value, joiner=j, valueFilter=valueFilter) for j in joiner]
		return list(unwrap(val))
	value = joiner.join(value)
	if valueFilter is not None:
		value = valueFilter(value)
	return value


TitleCamelCase = InfixModifier(camelCase)
isa = Infix(lambda x, y: (isinstance(x, y) and x))
isnot = Infix(lambda x, y: not isinstance(x, y) and x)
hasEx = Infix(lambda x, y: hasattr(x, y) and getattr(x, y))
OrUnset = Infix(__or__)


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


def __get(obj: Mapping, key, default=UnsetKwarg):
	"""getter for mappings"""
	if default is not UnsetKwarg:
		return obj.get(key, default)
	return obj.get(key)


@lru_cache(maxsize=128)
def genAltVarNames(varName: str) -> Iterable[str]:
	camel = camelCase(varName)
	screamingCamel = camel.upper()
	joinedCase = joinCase(varName, joiner=['_', '-', '.'], valueFilter=lambda x: x.lower())
	titleJoinedCase = joinCase(varName, joiner=['_', '-', '.'], valueFilter=lambda x: x.title())
	screamingJoinedCase = joinCase(varName, joiner=['_', '-', '.'], valueFilter=lambda x: x.upper())
	arr = [varName, camel, screamingCamel, joinedCase, titleJoinedCase, screamingJoinedCase]
	result = unwrap(arr)
	return result


def unwrap(arr: List[str | List[str]]) -> Set[str]:
	result = set()
	for i in arr:
		if isinstance(i, str):
			result.add(i)
		else:
			result.update(i)
	return result


def get(
	obj: Mapping | object,
	*keys: [Hashable],
	default: Any = UnsetKwarg,
	expectedType: Type | UnionType | Tuple[Type, ...] = object,
	castVal: bool = False,
	getter: Callable = __get,
) -> Any:
	"""
	Returns the value of the key in the mapping or object

	:param obj: The mapping to search.
	:param key: The keys to search for.
	:param default: The default value to return if the key is not found.
	:return: The value of the key in the mapping or the default value.
	"""
	values = tuple(r for key in keys if (r := getter(obj, key, Unset)) is not Unset)
	match len(values):
		case 0:
			if default is Unset:
				raise KeyError(f'{keys} not found in {obj}')
			return default
		case 1:
			value = values[0]
			if castVal:
				try:
					return expectedType(value)
				except TypeError as e:
					utilLog.warning(f'Could not cast {value} to {expectedType}', e.__traceback__)
			return value
		case _:
			utilLog.warning(f'Multiple values found for {keys} in {obj}, returning first value.')
			for value in (k for key in keys if isinstance(k := getter(obj, key, Unset), expectedType) or (castVal and k is not Unset)):
				if castVal:
					return expectedType(value)
				return value


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
		case int() | float() | str() | bool() | list() | tuple() | dict() | set() | NoneType():
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


def hasState(obj):
	return 'state' in dir(obj) and getattr(obj, 'savable', False)


class DotDict(dict):

	def __init__(self, *args, **kwargs):
		args = list(args)
		self.parent = kwargs.get('parent', Unset)
		self.key = kwargs.get('key', Unset)
		dicts = [args.pop(i) for i, item in enumerate(list(args)) if isinstance(item, dict)]
		super(DotDict, self).__init__(*args, **kwargs)
		for d in dicts:
			self.update(d)

	@property
	def key(self):
		if self.parent:
			return '.'.join([self.parent.key, self.__key])

	@key.setter
	def key(self, value):
		value = self.makeKey(value)
		if self.parent:
			parentKey = self.parent.key
		else:
			parentKey = ()
		if len(value) > 1 and value[:-1] == parentKey:
			value = value[-1]
		self.__key = value

	@staticmethod
	def makeKey(key: str) -> tuple:
		if isinstance(key, tuple):
			return key
		elif isinstance(key, Hashable) and not isinstance(key, str):
			return key,
		return tuple(re.findall(rf"[\w|\-|\_]+", key), )

	def __setitem__(self, key, value):
		key = self.makeKey(key)
		if len(key) == 1:
			dict.__setitem__(self, key[0], value)
		else:
			if key[0] not in self:
				self[key[0]] = DotDict(key=key[0], parent=self)
			dict.__getitem__(self, key[0]).__setitem__(key[1:], value)

	def __contains__(self, key):
		key = self.makeKey(key)
		if len(key) == 1:
			return dict.__contains__(self, key[0])
		else:
			if key[0] not in self:
				return False
			return dict.__getitem__(self, key[0]).__contains__(key[1:])

	def popValue(self):
		return self.popitem()[1]

	def __getitem__(self, item):
		key = self.makeKey(item)
		if len(key) == 1:
			return dict.__getitem__(self, key[0])
		else:
			if key[0] not in self:
				raise KeyError(key)
			return dict.__getitem__(self, key[0]).__getitem__(key[1:])

	def get(self, key, default: Any = UnsetKwarg):
		key = self.makeKey(key)
		if key in self:
			return self[key]
		else:
			if default is UnsetKwarg:
				raise KeyError
			return default

	def update(self, data: dict):
		for key, value in data.items():
			self[key] = value


def recursiveDictUpdate(d: dict, u: dict, copy: bool = True) -> dict:
	if copy:
		d = dict(d)
	for k, v in u.items():
		if isinstance(v, dict):
			d[k] = recursiveDictUpdate(d.get(k, {}), v)
		else:
			d[k] = v
	return d


def recursiveRemove(existingDict: dict, subtracting: dict) -> dict:
	for key, subtractingValue in subtracting.items():
		existing = existingDict.get(key, None)
		if existing is None:
			continue
		if isinstance(subtractingValue, dict):
			if isinstance(existing, dict):
				if existing == subtractingValue:
					existingDict.pop(key)
				else:
					existingDict[key] = recursiveRemove(existingDict.get(key, {}), subtractingValue)
					if not existingDict[key]:
						existingDict.pop(key)
			elif subtractingValue:
				existingDict[key] = subtractingValue
			else:
				existingDict.pop(key, None)
			continue
		if existing == subtractingValue:
			existingDict.pop(key, None)
	return existingDict


def deepCopy(d: dict) -> dict:
	return recursiveDictUpdate(dict(), d, copy=False)


class DeepChainMap(ChainMap):
	"""A recursive subclass of ChainMap"""

	def __init__(self, *maps: Mapping, origin: 'Stateful' = None):
		self._originMap = {}
		self.origin = origin
		super().__init__(self._originMap, *maps)

	def __getitem__(self, key):
		submaps = [mapping for mapping in self.maps if key in mapping]
		if not submaps:
			return self.__missing__(key)
		if isinstance(submaps[0][key], Mapping):
			return DeepChainMap(*(submap[key] for submap in submaps))
		return super().__getitem__(key)

	def to_dict(self, d: dict | Mapping = None) -> dict:
		d = d or {}
		for mapping in reversed(self.maps):
			self._depth_first_update(d, mapping)
		return d

	def _depth_first_update(self, target: dict, source: Mapping) -> None:
		for key, val in source.items():
			if not isinstance(val, Mapping):
				target[key] = val
				continue
			if key not in target:
				target[key] = {}
			self._depth_first_update(target[key], val)

	@property
	def originMap(self) -> dict:
		return self._originMap

	def new_child(self, origin: 'Stateful') -> 'DeepChainMap':
		return self.__class__(*self.maps, origin=origin)


class ScaleFloatMeta(type):

	def __instancecheck__(self, instance):
		return isinstance(instance, float | int) and 0 <= instance <= 1

	def __subclasscheck__(self, subclass):
		return issubclass(subclass, float | int)


class ScaleFloat(metaclass=ScaleFloatMeta):

	def __new__(cls, value):
		value = sorted((value, 0, 1))[1]
		return super().__new__(cls, value)


def __scoreState(a, b):
	return SequenceMatcher(lambda x: x == " ", str(a).casefold(), str(b).casefold()).ratio()


def scoreNumber(n1, n2):
	""" calculates a similarity score between 2 numbers """
	return 1 - abs(n1 - n2)/(n1 + n2)


def scoreDict(a, b):
	sharedKeys = set(a.keys()) & set(b.keys())
	score = 0
	for key in sharedKeys:
		aValue = a[key]
		bValue = b[key]
		if isinstance(aValue, type(bValue)):
			match aValue:
				case dict():
					score += scoreDict(aValue, bValue)
				case bool():
					score += int(aValue == bValue)
				case int() | float():
					score += scoreNumber(aValue, bValue)

	return score


def sortDict(d: dict, reverse: bool = False) -> dict:
	return {key: value for key, value in sorted(d.items(), key=lambda x: x[0], reverse=reverse)}


def mostSimilarDict(ref: dict, choices: Iterable[dict], sharedKeysOnly: bool = True, cuttoff: float = 0.0) -> Tuple[int, dict]:
	"""
	Find the most similar dict in choices to reference.
	:param ref: The reference dict.
	:param choices: The choices to compare against.
	:return: The index of the most similar dict, and the dict itself.
	"""
	if sharedKeysOnly:
		choices = [{k: v for k, v in choice.items() if k in ref} if isinstance(choice, Mapping) else choice for choice in choices]
	scores = [(i, choice, score) for i, choice in enumerate(choices) if (score := __scoreState(ref, choice)) >= cuttoff]
	return max(scores, key=lambda x: x[2])[:2]


class guarded_cached_property(cached_property):

	def __new__(cls, *args, guardFunc: Callable[[Any], bool], default: Any):
		if not args:
			return partial(guarded_cached_property, guardFunc=guardFunc, default=default)
		return cached_property.__new__(cls)

	def __init__(self, *args, guardFunc: Callable[[Any], bool], default: Any):
		super().__init__(*args)
		self.guardFunc = guardFunc
		self.default = default

	def __call__(self, *args, **kwargs):
		pass

	def __get__(self, instance, owner=None):
		value = super().__get__(instance, owner)
		if self.guardFunc(value):
			return value
		else:
			instance.__dict__.pop(self.attrname, None)
			if isinstance(defaultFunc := self.default, Callable):
				if 'self' in get_args(defaultFunc):
					return defaultFunc(instance)
				return self.default()
			elif isinstance(defaultFunc, property):
				return defaultFunc.__get__(instance, owner)
			return self.default


def split(a, n):
	k, m = divmod(len(a), n)
	return (a[i*k+min(i, m):(i+1)*k+min(i+1, m)] for i in range(n))


T = TypeVar("T")


Index = NamedTuple("Index", [("previous", Any), ("current", Any), ("next", Any)])

@dataclass(slots=True)
class Index:

	value: Hashable | None = field(hash=True)
	previous: Optional['Index'] = field(hash=False, compare=False, default=None)
	next: Optional['Index'] = field(hash=False, compare=False, default=None)

	def __post_init__(self):
		if self.previous is None:
			self.previous = self
		if self.next is None:
			self.next = self

	def __iter__(self):
		yield self.value
		yield self.previous
		yield self.next


class OrderedSet(MutableSet[T]):

	map = cached_property(lambda self: {})
	sub_maps = cached_property(lambda self: {})

	def __init__(self, iterable=None):
		self.end = end = Index(None)

		if iterable is not None:
			self |= iterable

	def __len__(self):
		return len(self.map)

	def __contains__(self, key):
		return key in self.map

	def add(self, key: T):
		if key not in self.map:
			end = self.end
			curr = end.previous
			curr.next = end.previous = self.map[key] = Index(key, curr, end)

	def add_at_beginning(self, key: T):
		if key not in self.map:
			end = self.end
			curr = end.next
			curr.previous = end.next = self.map[key] = Index(key, end, curr)

	def discard(self, key):
		if key in self.map:
			key, prev, nxt = self.map.pop(key)
			prev.next = nxt
			nxt.previous = prev

	def remove(self, key):
		if key not in self.map:
			raise KeyError(key)
		self.discard(key)

	def __iter__(self):
		end = self.end
		curr = end.next
		while curr is not end:
			yield curr.value
			curr = curr.next

	def __reversed__(self):
		end = self.end
		curr = end.previous
		while curr is not end:
			yield curr.value
			curr = curr.previous

	def pop(self, last=True):
		if not self:
			raise KeyError('set is empty')
		key = next(reversed(self)) if last else next(iter(self))
		self.discard(key)
		return key

	def clear(self) -> None:
		self.map.clear()
		self.end = end = []
		end += [None, end, end]  # sentinel node for doubly linked list

	def __repr__(self):
		if not self:
			return f'{self.__class__.__name__}()'
		return f'{self.__class__.__name__}({list(self)!r})'

	def __eq__(self, other):
		if isinstance(other, OrderedSet):
			return len(self) == len(other) and list(self) == list(other)
		return set(self) == set(other)

	def __del__(self):
		self.clear()  # remove circular references

	def __reduce__(self):
		return self.__class__, (list(self),)


class ActionPool(OrderedSet):
	up: 'ActionPool'
	__len: int = cached_property(lambda self: 0)
	__contextLevel: int = cached_property(lambda self: 0)
	__active: bool = cached_property(lambda self: False)
	__callbacks: List[Tuple[Callable, Tuple, Dict]] = cached_property(lambda self: [])


	class Status(Enum):
		Idle = 0
		Queued = 1
		Running = 2
		Finished = 3
		Canceled = 4
		Failed = 5
		Removed = 6


	def __init__(self, instance: 'Stateful', trace = None):
		self.status = self.Status.Idle
		self.instance = instance
		self.root = self
		self.up = self
		super().__init__()

	def __enter__(self):
		self.__contextLevel += 1
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.__contextLevel -= 1
		if self.__contextLevel <= 0:
			self.__contextLevel = 0
			if self.can_execute: self.execute()

	def __repr__(self):
		return f'{self.__class__.__name__}({type(self.instance).__name__} items: {len(list(self))}, total: {self.total_length})'

	def __hash__(self):
		return id(self)

	def __len__(self):
		return self.__len

	def __true_len__(self):
		return super().__len__()

	def __bool__(self) -> bool:
		return bool(self.__len) and all(bool(pool) for pool in self.sub_maps.values())

	def new(self, instance: 'Stateful') -> 'ActionPool':
		self.add(a := ActionPool(instance, trace='new'))
		return a

	def add_at_beginning(self, key: T):
		super().add_at_beginning(key)

	def add(self, other, first: bool = False):
		super().add(other) if not first else self.add_at_beginning(other)
		if isinstance(other, ActionPool):
			other.up = self
			other.root = self.root
			self.sub_maps[other.instance] = other
		self.__len += 1

	def discard(self, other):
		super().discard(other)
		self.__len = self.__true_len__()

	def clear(self):
		list(map(ActionPool.clear, self.sub_maps.values()))
		self.sub_maps.clear()
		super().clear()
		self.__len = 0

	def pop(self, last=True):
		popped = super().pop(last)
		self.__len -= 1
		return popped

	def remove(self, key):
		super().remove(key)
		self.__len -= 1

	@property
	def total_length(self) -> int:
		return sum(pool.total_length for pool in self.sub_maps.values()) + self.__len

	@property
	def can_execute(self) -> bool:
		if self.up is self:
			return not self.instance.is_loading and not self.__contextLevel and not self.__active
		return not self.instance.state_is_loading and not self.__contextLevel and not self.__active# and self.up.can_execute

	def execute(self):
		self.__active = True
		utilLog.verbose(f"Executing {len(self)} items in afterPool for {self.__class__.__name__}", verbosity=5)
		if type(self.instance).__name__ in {'HourLabels', 'DayLabels', 'WeekLabels', 'MonthLabels', 'YearLabels'}:
			return
		for action in self:
			self.discard(action)
			if isinstance(action, ActionPool):
				action.execute()
			else:
				if action.__code__.co_argcount:
					action(self.instance)
				else:
					action()
		while self.__callbacks:
			callback, args, kwargs = self.__callbacks.pop(0)
			callback(*args, **kwargs)
		self.__active = False

	def delete(self):
		self.__delete__(self)

	def __delete__(self, instance):
		self.status = self.Status.Canceled
		for pool in list(self.sub_maps.values()):
			pool.__del__()
		self.up.discard(self)
		try:
			instance.discard(self)
		except:
			pass
		self.clear()

	def add_callback(self, callback: Callable, *args, **kwargs):
		self.__callbacks.append((callback, args, kwargs))


def defer(func):

	@wraps(func)
	def wrapper(self, *args, **kwargs):
		if (pool := getattr(self, '_actionPool', None)) is not None:
			if pool.can_execute:
				return func(self, *args, **kwargs)
			else:
				pool.add(func)

	return wrapper


def thread_safe(func):

	@wraps(func)
	def wrapper(self, *args, **kwargs):
		return func(self, *args, **kwargs)

	return wrapper


class WorkerSignals(QtCore.QObject):
	finished = QtCore.Signal()
	error = QtCore.Signal(tuple)
	result = QtCore.Signal(object)
	progress = QtCore.Signal(int)


class _BaseWorker:

	class Status(Enum):
		Idle = 0
		Queued = 1
		Running = 2
		Finished = 3
		Canceled = 4
		Failed = 5

		@property
		def is_active(self) -> bool:
			return 0 < self._value_ < 3

	signals: WorkerSignals
	status: Status = Status.Idle


class Worker(Generic[Self], _BaseWorker, QtCore.QRunnable):

	_pool: 'Pool' = None
	args: Tuple[Any, ...]
	kwargs: Dict[str, Any]

	_direct: bool = False

	_on_finish: List[Callable[[], None]]
	_on_result: List[Callable[[Any], None]]
	on_error: Callable[[Exception], None] = None
	on_progress: Callable[[int|float], None] = None

	_debug: bool = False
	current_thread: Callable[[], QThread] = QThread.currentThread

	def __init__(self: Self, fn, *args, **kwargs):
		super().__init__()
		self.status = Worker.Status.Idle
		self.fn = fn
		self.args = args
		self.kwargs = kwargs
		self.signals = WorkerSignals()
		self.signals.moveToThread(LevityDashboard.app.thread())

	def __rich_repr__(self):
		yield 'status', self.status.name
		yield 'fn', self.fn
		if self.args:
			yield 'args', self.args
		if self.kwargs:
			yield 'kwargs', self.kwargs
		if p := getattr(self, 'pool', None):
			yield 'pool', p

	def __copy__(self: Self) -> Self:
		clone = Worker.create_worker(self.fn, *self.args, **self.kwargs)
		clone.setAutoDelete(self.autoDelete())
		return clone

	@cached_property
	def _on_finish(self) -> List[Callable[[], None]]:
		return []

	def on_finish(self):
		for func in self._on_finish:
			func()

	@cached_property
	def _on_result(self) -> List[Callable[[Any], None]]:
		return []

	def on_result(self, result):
		for func in self._on_result:
			func(result)

	@classmethod
	def new_immortal_worker(cls, func: Callable, *args, **kwargs) -> 'Worker':
		worker = cls(func, *args, **kwargs)
		worker.setAutoDelete(False)
		return worker

	@property
	def pool(self) -> 'Pool':
		return self._pool or Pool.globalInstance()

	@pool.setter
	def pool(self, pool: 'Pool'):
		self._pool = pool

	def start(self, priority: int = None):
		if priority is not None:
			args = self, priority
		else:
			try:
				args = self, self.priority
			except AttributeError:
				args = self,
		pool = self.pool
		pool.start(*args)

	@Slot()
	def run(self):
		self.status = Worker.Status.Running
		"""Initialise the runner function with passed args, kwargs."""
		utilLog.verbose(f'Running {self.fn!r} in thread: {self.current_thread()}', verbosity=5)
		if QApplication.instance().thread() is self.signals.thread():
			self.signals.moveToThread(QApplication.instance().thread())
		try:
			result = self.fn(
				*self.args, **self.kwargs,
			)
			QApplication.sync()
			self.current_thread().yieldCurrentThread()
		except Exception as e:
			self.status = Worker.Status.Failed
			print_exc()
			exec_type, value = exc_info()[:2]
			if self._direct and self.on_error:
				self.on_error(e)
			else:
				self.signals.error.emit((exec_type, value, format_exc()))
			utilLog.error(f'Error running {self.fn.__name__}')
			utilLog.exception(e)
		else:
			self.status = Worker.Status.Finished
			if self._direct and self.on_result:
				self.on_result(result)
			else:
				self.signals.result.emit(result)
		finally:
			if self._direct and self.on_finish:
				self.on_finish()
			else:
				self.signals.finished.emit()
			utilLog.verbose(f'Finished {self.fn!r} in thread', verbosity=5)

	def cancel(self):
		if self.status is Worker.Status.Running:
			try:
				self.pool.cancel(self)
				self.status = Worker.Status.Canceled
			except RuntimeError:
				pass
			except Exception as e:
				utilLog.exception(e)

	@classmethod
	def create_worker(
		cls: Type[Self],

		func: Callable | Awaitable,
		*args,
		func_kwargs: Dict[str, Any] = None,

		on_finish: Callable[[], None] = None,
		on_result: Callable[[T], Any] = None,
		on_error: Callable[[Exception], Any] = None,

		immortal: bool = False,
		**kwargs: Dict[str, Any],

	) -> Self:
		func_kwargs = func_kwargs or {}
		func_kwargs.update(kwargs)
		worker = cls(func, *args, **func_kwargs)
		worker.setAutoDelete(not immortal)

		if on_finish is not None:
			worker._on_finish.append(on_finish)
			connectSignal(worker.signals.finished, on_finish)

		if on_result is not None:
			worker._on_result.append(on_result)
			connectSignal(worker.signals.result, on_result)

		if on_error is not None:
			worker.on_error = on_error
			connectSignal(worker.signals.error, on_error)

		return worker

	def link_worker(self, worker: 'Worker'):
		connectSignal(worker.signals.finished, self.start)
		return worker

	def link_worker_result(
		self,
		worker: 'Worker' = None,
		arg_index: int = None,
		kwarg_name: str = None,
		pre_func: Callable[['Worker', Any], 'Worker'] = None,
		inplace: bool = True,
		priority: int = None,
	):

		if not inplace:
			worker = worker.__copy__()

		def _on_result(result, worker_: 'Worker' = None):
			if pre_func is not None:
				pre_func(worker_, result)
			elif arg_index is not None:
				worker_args = getfullargspec(worker.fn).args
				try:
					worker_args[arg_index] = result
				except IndexError:
					worker_args.append(result)
				worker_.args = *worker_args,
			elif kwarg_name is not None:
				worker_.kwargs[kwarg_name] = result
			else:
				if isinstance(result, str):
					result = result,
				worker_.args = result,
			self.current_thread().yieldCurrentThread()
			QTimer.singleShot(100, lambda: worker_.start(priority=priority))


		connectSignal(self.signals.result, partial(_on_result, worker_=worker))
		return worker

	@cached_property
	def handoff_delay(self):
		return QTimer(singleShot=True, interval=100)


@rich_repr
class PluginThread(Thread):
	"""PluginThread"""

	plugin: 'Plugin'

	def __init__(self, plugin: 'Plugin'):
		super().__init__()
		self.signals = WorkerSignals()
		self.plugin = plugin
		self._target = plugin.start

_PoolTypeVar: TypeAlias = TypeVar('_PoolTypeVar', bound='_BasePool')


class _BasePool:

	worker_class: ClassVar[Type[Worker|PluginThread]]
	__instances__: ClassVar[List[_PoolTypeVar]]
	__global_instance: ClassVar[_PoolTypeVar]

	def __init_subclass__(cls):
		cls.__instances__ = []

	def __new__(cls, *args, **kwargs):
		instance = super().__new__(cls)
		cls.__instances__.append(instance)
		return instance

	@classmethod
	def globalInstance(cls) -> _PoolTypeVar:
		try:
			instance = cls.__global_instance
			try:
				instance.activeThreadCount()
			except RuntimeError:
				del cls.__global_instance
				del instance
				raise AttributeError
		except AttributeError:
			instance = cls.__global_instance = cls()

		return instance

class Pool(_BasePool, QtCore.QThreadPool):

	worker_class: ClassVar[Type[Worker]] = Worker

	@classmethod
	def shutdown_all(cls):
		utilLog.info(f"Shutting down {len(cls.__instances__)} thread pools")
		for instance in cls.__instances__:
			instance.shutdown()

	def shutdown(self):
		self.clear()
		self.waitForDone(1000)
		if self.activeThreadCount():
			utilLog.warning(f"Pool still has {self.activeThreadCount()} active threads after waiting 500ms")
			self.thread().quit()

	def run_threaded_process(
		self,
		func: Callable | Awaitable,
		*args,
		func_kwargs: dict = None,
		on_finish: Callable[[], None] | Coroutine = None,
		on_result: Callable[[T], Any] | Coroutine = None,
		on_error: Callable[[Exception], Any] | Coroutine = None,
		priority: int = 3,
		immortal: bool = False,
		**kwargs: Dict[str, Any]
	) -> Worker:
		"""Execute a function in the background with a worker"""

		worker = self.worker_class.create_worker(
			func,
			*args,
			func_kwargs=func_kwargs,
			on_finish=on_finish,
			on_result=on_result,
			on_error=on_error,
			immortal=immortal,
			**kwargs
		)
		worker.pool = self

		self.start(worker, priority)

		return worker

	run_in_thread = run_threaded_process

	def start(self, runnable: Worker, priority: int = 3):
		runnable.pool = self
		try:
			runnable.status = Worker.Status.Queued
		except Exception:
			pass
		super().start(runnable, priority)

	def run_with_worker(self, worker: Worker, callback: Callable = None) -> Worker:
		"""Execute a function in the background with a worker"""
		self.start(worker)
		worker.signals.result.connect(callback)
		return worker

	def start_workers(self, *workers: Worker, priority: int = 3):
		for worker in workers:
			self.start(worker, priority)


pool = Pool()
threadPool: Pool = pool
LevityDashboard.main_thread_pool = pool
run_in_thread = pool.run_threaded_process


class PluginPool(_BasePool, ThreadPool):

	worker_class: ClassVar[Type[PluginThread]] = PluginThread


def in_thread(func, priority=3):
	"""Decorator to run a function in a background thread"""

	@wraps(func)
	def wrapper(*args, **kwargs):
		return run_in_thread(func, *args, **kwargs, priority=priority)

	return wrapper


def parse_bool(value: str | int) -> bool | None:
	if isinstance(value, str):
		value = value.lower()
		if value in {'1', 'true', 't', 'yes', 'y', 'on'}:
			return True
		elif value in {'0', 'false', 'f', 'no', 'n', 'off'}:
			return False
		else:
			return None
	elif isinstance(value, int):
		return bool(value)


def pseudo_bound_method(instance: Any = None, func: Callable = None) -> MethodType:
	"""
	Bind a function to an instance, but without actually binding it.
	Similar to functools.partial, but with a different signature.
	"""
	if func is None:
		return partial(pseudo_bound_method, instance)
	return MethodType(func, instance)
