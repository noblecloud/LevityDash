from asyncio import Lock, gather, iscoroutine, get_running_loop
from types import coroutine

from builtins import isinstance
from collections import deque
from copy import copy

from operator import add

from dataclasses import dataclass, field

from uuid import uuid4
from abc import ABC, ABCMeta, abstractmethod
from datetime import datetime, timedelta, timezone as _timezones, tzinfo
from functools import cached_property, lru_cache, partial
from typing import (Any, Callable, ClassVar, Hashable, Iterable, List, Mapping, Optional, OrderedDict, Set, Tuple,
                    Type, Union, SupportsAbs, TYPE_CHECKING, Coroutine)

import numpy as np
from qasync import QThreadExecutor

import WeatherUnits as wu
from dateutil.parser import parse
from math import isinf
from PySide2.QtCore import QObject, Signal, Slot
from rich.progress import Progress

from LevityDash.lib.plugins.categories import CategoryItem, CategoryDict
from LevityDash.lib.plugins.schema import LevityDatagram
from LevityDash.lib.utils import (NoValue, isOlderThan, mostFrequentValue, clearCacheAttr, closest, DateKey, isa,
                                  mostCommonClass, now, Now, Period, roundToPeriod, toLiteral, UTC, LOCAL_TIMEZONE)

from LevityDash.lib.plugins import SchemaProperty, pluginLog, unitDict, Accumulator
from LevityDash.lib.log import LevityPluginLog as log
from LevityDash.lib.plugins.utils import ChannelSignal

if TYPE_CHECKING:
	from LevityDash.lib.plugins.plugin import Plugin
	from LevityDash.lib.plugins.categories import UnitMetaData

REALTIME_THRESHOLD = timedelta(hours=1.5)

loop = get_running_loop()

__all__ = [
	"ObservationDict",
	"Observation",
	"ObservationRealtime",
	"ObservationTimeSeries",
	"ObservationLog",
	"ObservationTimeSeriesItem",
	"MeasurementTimeSeries",
	"TimeSeriesItem",
	"TimeAwareValue",
	"ObservationValue",
	"RecordedObservationValue",
	"ArchivedObservationValue",
	"ArchivedObservation",
	"ObservationValueResult",
	"ObservationTimestamp",
	"MiniTimeSeries",
	"PublishedDict",
	"Container",
]

log = pluginLog.getChild('Observation')


def convertToCategoryItem(key, source: Hashable = None):
	if not isinstance(key, CategoryItem):
		key = CategoryItem(key, source=source)
	else:
		key.source = source or key.source
	return key


class RealtimeSource(ABC):
	pass


class TimeseriesSource(ABC):

	@property
	@abstractmethod
	def period(self) -> timedelta:
		pass


class RecordedObservation(ABC):
	pass


class Archivable(ABC):

	@property
	@abstractmethod
	def archived(self): ...


@dataclass(frozen=True)
class HashSlice:
	start: Hashable = field(init=True, compare=True, repr=True, hash=True)
	stop: Hashable = field(init=True, compare=True, repr=True, hash=True, default=None)
	step: Hashable = field(init=True, compare=True, repr=True, hash=True, default=None)

	def __iter__(self) -> Iterable:
		return iter((self.start, self.stop, self.step))


@dataclass
class PublishingInfo:
	observation: 'ObservationDict'
	source: 'Plugin'
	keys: Iterable


class TimeAwareValue(ABC):
	timestamp: datetime
	value: Any

	def __instancecheck__(self, instance):
		timestamp = getattr(instance, 'timestamp', None)
		value = getattr(instance, 'value', None)
		return timestamp is not None and value is not None


TimeAwareValue.register(wu.Measurement)


class ArchivableValue(Archivable, TimeAwareValue, ABC):
	pass


class Archived(ABC):
	pass


@ArchivableValue.register
class ObservationValue(TimeAwareValue):
	__metadata: 'UnitMetaData'
	__source: 'ObservationDict'
	__timestamp: Optional[datetime]

	def __init_subclass__(cls, **kwargs):
		super(ObservationValue, cls).__init_subclass__(**kwargs)

	def __init__(self,
		value: Any,
		key: Union[str, CategoryItem],
		source: Any,
		container: 'ObservationDict',
		metadata: 'UnitMetaData' = None,
		**kwargs):
		self.__rawValue = None
		self.__timestamp = None
		if isinstance(value, TimeSeriesItem):
			timeAware = value
			value = None
		elif isinstance(value, ObservationValue):
			rawValue = toLiteral(value.rawValue)
			timeAware = TimeSeriesItem(rawValue, value.timestamp)
			metadata = value.metadata
			value = rawValue
		else:
			timeAware = None
		if metadata is None:
			metadata = source.schema.getUnitMetaData(key, source)
			if metadata['key'] != key:
				metadata['sourceKey'] = key
				if isinstance(key, CategoryItem):
					kSource = key.source
				else:
					kSource = None
				if metadata['key'] == key and metadata['key'].vars:
					pass
				else:
					key = CategoryItem(metadata['key'], kSource)
				source.__sourceKeyMap__[metadata['sourceKey']] = metadata['key']
			metadata['key'] = key
		if isinstance(value, wu.Measurement):
			sourceUnit = metadata['sourceUnit']
			if value.unit != sourceUnit:
				try:
					value = value[sourceUnit].real
					if timeAware:
						timeAware.value = value

				except wu.errors.UnknownUnit:
					log.warning(f'Failed to convert {key} from {value.unit} to {sourceUnit}.  This may cause issues later conversion accuracy.')
		self.__metadata = metadata
		self.__source = source
		self.__container = container
		self.__value = None
		self.__convertFunc__: Callable = None
		self.value = timeAware or value

	def __getitem__(self, item):
		if item.startswith('@'):
			value = self.__getattribute__('value')
			result = getattr(value, item[1:], None)
			if result is not None:
				return result
			else:
				raise AttributeError
		if item in self.__metadata:
			return self.__metadata[item]
		return self.__getattribute__(item)

	def __getattr__(self, item):
		if item.startswith('@'):
			value = self.__getattribute__('value')
			return value.__getattribute__(item[1:])
		return self.__getattribute__(item)

	@property
	def isValid(self) -> bool:
		return self.rawValue is not None

	@property
	def value(self):
		if self.__value is None:
			try:
				value = self.convertFunc(self.rawValue)
			except Exception as e:
				value = self.rawValue
			if localized := getattr(value, 'localize', None):
				value = localized
			if not isinstance(self, ObservationTimestamp):
				if isinstance(value, datetime):
					value = wu.Time.Second((value - Now()).total_seconds()).autoAny
				elif isinstance(value, timedelta):
					value = wu.Time.Second(value.total_seconds()).autoAny
			self.__value = value
		return self.__value

	@value.setter
	def value(self, value):
		timestamp = None
		if isinstance(value, ObservationValue):
			timestamp = value.timestamp
			value = value.rawValue
		if isinstance(value, TimeSeriesItem):
			timestamp = value.timestamp
			value = value.value
		if isinstance(value, datetime):
			timestamp = value
		if timestamp is None and 'time' not in str(self.__metadata["key"]):
			log.warning(f'{self.__metadata["key"]} does not have a timestamp')
		self.__timestamp = timestamp
		self.__rawValue = value
		self.__value = None

	@property
	def sourceUnitValue(self):
		return self.convertFunc(self.rawValue)

	@property
	def rawValue(self):
		return self.__rawValue

	@property
	def convertFunc(self) -> Callable:
		if getattr(self.metadata, 'hasAliases', False):
			return self.metadata.mapAlias
		if self.__convertFunc__ is None:
			self.__convertFunc__ = self.metadata.getConvertFunc(self.source)
		return self.__convertFunc__

	def __str__(self):
		return str(self.value)

	@property
	def key(self) -> CategoryItem:
		return self.__metadata['key']

	def setTimestamp(self, timestamp: datetime):
		self.__timestamp = timestamp

	@property
	def timestamp(self) -> datetime:
		if self.__timestamp is None:
			return self.__source.timestamp
		return self.__timestamp

	def __repr__(self):
		if self.timestamp is None:
			timestamp = ' Unknown Time'
		elif self.timestamp != self.__source.timestamp:
			timestamp = f' @{self.timestamp:"%-I:%M%p %m/%d"}'
		else:
			timestamp = ''
		return f'{{\'{self.value.__class__.__name__}\'}} {self.value}{timestamp}'

	@property
	def archived(self) -> 'ArchivedObservationValue':
		return ArchivedObservationValue(self)

	@property
	def metadata(self) -> 'UnitMetaData':
		return self.__metadata

	@cached_property
	def source(self):
		return self.__source

	@property
	def container(self) -> 'Container':
		return self.__container

	def __eq__(self, other):
		if isinstance(other, ObservationValue):
			return self.value == other.value
		return self.value == other

	def __ne__(self, other):
		return not self.__eq__(other)

	def __lt__(self, other):
		if isinstance(other, ObservationValue):
			return self.value < other.value
		return self.value < other

	def __le__(self, other):
		if isinstance(other, ObservationValue):
			return self.value <= other.value
		return self.value <= other

	def __gt__(self, other):
		if isinstance(other, ObservationValue):
			return self.value > other.value
		return self.value > other

	def __ge__(self, other):
		if isinstance(other, ObservationValue):
			return self.value >= other.value
		return self.value >= other

	def __float__(self):
		return float(self.value)

	def __int__(self):
		return int(self.value)

	def __hash__(self):
		return hash((self.value, self.key, self.timestamp))

	def __len__(self):
		return 1

	def __iadd__(self, other):
		return ObservationValueResult(self, other)


@Archived.register
class ArchivedObservationValue(ObservationValue):
	__slots__ = ('value', 'rawValue', 'source', 'metadata', 'timestamp', 'sourceUnitValue')

	def __init__(self, origin: Archivable, **kwargs):
		self.value = kwargs.get('value', origin.value)
		self.metadata = kwargs.get('metadata', origin.metadata)
		self.source = kwargs.get('source', origin.source)
		self.timestamp = kwargs.get('timestamp', origin.timestamp)
		self.rawValue = kwargs.get('rawValue', origin.rawValue)
		self.sourceUnitValue = kwargs.get('sourceUnitValue', origin.sourceUnitValue)

	def __setattr__(self, name, value):
		if hasattr(self, name):
			raise AttributeError(f'{name} is read-only')
		elif name in self.__slots__:
			super().__setattr__(name, value)

	@ObservationValue.key.getter
	def key(self):
		return self.metadata['key']

	def __repr__(self):
		if self.timestamp is None:
			return f'{self.value} @ UnknownTime'
		if self.timestamp != self.source.timestamp:
			timestamp = f' @{self.timestamp.strftime("%-I:%M%p %m/%d")}'
		else:
			timestamp = ''
		return f'{{\'{self.value.__class__.__name__}\'}} {self.value}{timestamp}'

	def __str__(self):
		return str(self.__value)

	@property
	def archived(self):
		return self


@ArchivableValue.register
class ObservationValueResult(ObservationValue):
	__values: set

	def __init__(self, *values: tuple[TimeAwareValue], operation: Callable = add):
		self.__values = set()
		key = values[0].key
		source = values[0].source
		metadata = values[0].metadata
		self.operation = operation
		super().__init__(None, key, source, metadata)
		self.value = values

	@property
	def value(self):
		try:
			value = self.convertFunc(self.__rawValue)
		except TypeError:
			value = self.__rawValue
		if hasattr(value, 'localize'):
			value = value.localize
		return value

	@value.setter
	def value(self, values):
		if values is None:
			return
		if not isinstance(values, Iterable):
			values = [values]
		for v in values:
			if isinstance(v, ObservationValueResult):
				self.__values.update(v.values)
				continue
			if isinstance(v, ObservationValue):
				v = TimeSeriesItem(v.rawValue, v.timestamp)
			if isinstance(v, TimeSeriesItem):
				self.__values.add(v)
			elif isinstance(v, (int, float)):
				t = self.value.timestamp
				self.__values.add(TimeSeriesItem(v, t))

	@property
	def __rawValue(self):
		return TimeSeriesItem.average(*self.__values)

	@property
	def values(self):
		return self.__values

	def __iadd__(self, other):
		self.value = other
		return self

	@property
	def timestamp(self):
		return self.__rawValue.timestamp


class TimeSeriesItem(TimeAwareValue):
	__slots__ = ('value', 'timestamp')
	value: Hashable
	timestamp: datetime

	def __init__(self, value: Any, timestamp: datetime = None):
		if timestamp is None:
			if isinstance(value, TimeAwareValue):
				timestamp = value.timestamp
			else:
				timestamp = datetime.utcnow().replace(tzinfo=_timezones.utc)

		if isinstance(timestamp, SchemaProperty):
			timestamp = timestamp()
		elif isinstance(timestamp, ObservationTimestamp):
			timestamp = timestamp.value

		value = toLiteral(value)
		self.value = value
		self.timestamp = timestamp

	def __repr__(self):
		return f'{self.value} @ {self.timestamp}'

	def __add__(self, other):
		if type(other) is TimeSeriesItem:
			timestamp = datetime.fromtimestamp((self.timestamp.timestamp() + other.timestamp.timestamp())/2)
			other = other.value
		else:
			timestamp = self.timestamp
		value = self.value + other
		return TimeSeriesItem(value, timestamp)

	def __iadd__(self, other):
		if type(other) is TimeAwareValue:
			other = TimeSeriesItem(other.value, other.timestamp)
		if type(other) is TimeSeriesItem:
			return MultiValueTimeSeriesItem(self, other)
		return NotImplemented

	def __radd__(self, other):
		if not other:
			return self
		return self.__add__(other)

	def __sub__(self, other):
		if type(other) is TimeSeriesItem:
			timestamp = datetime.fromtimestamp((self.timestamp.timestamp() + other.timestamp.timestamp())/2)
			other = other.value
		else:
			timestamp = self.timestamp
		value = self.value - other
		return TimeSeriesItem(value, timestamp)

	def __rsub__(self, other):
		if not other:
			return self
		return self.__sub__(other)

	def __mul__(self, other):
		if type(other) is TimeSeriesItem:
			timestamp = datetime.fromtimestamp((self.timestamp.timestamp() + other.timestamp.timestamp())/2)
			other = other.value
		else:
			timestamp = self.timestamp
		value = self.value*other
		return TimeSeriesItem(value, timestamp)

	def __rmul__(self, other):
		if not other:
			return self
		return self.__mul__(other)

	def __truediv__(self, other):
		if type(other) is TimeSeriesItem:
			timestamp = datetime.fromtimestamp((self.timestamp.timestamp() + other.timestamp.timestamp())/2)
			other = other.value
		else:
			timestamp = self.timestamp
		value = self.value/other
		return TimeSeriesItem(value, timestamp)

	def __rtruediv__(self, other):
		if not other:
			return self
		return self.__truediv__(other)

	def __gt__(self, other):
		if isinf(other):
			return True
		if hasattr(other, 'value'):
			other = other.value
		if isinstance(other, datetime) and not isinstance(self.value, datetime):
			return self.timestamp > other
		return self.value > type(self.value)(other)

	def __lt__(self, other):
		if isinf(other):
			return True
		if hasattr(other, 'value'):
			other = other.value
		if isinstance(other, datetime) and not isinstance(self.value, datetime):
			return self.timestamp < other
		return self.value < type(self.value)(other)

	def __ge__(self, other):
		if isinf(other):
			return True
		if hasattr(other, 'value'):
			other = other.value
		if isinstance(other, datetime) and not isinstance(self.value, datetime):
			return self.timestamp >= other
		return self.value >= type(self.value)(other)

	def __le__(self, other):
		if isinf(other):
			return True
		if hasattr(other, 'value'):
			other = other.value
		if isinstance(other, datetime) and not isinstance(self.value, datetime):
			return self.timestamp <= other
		return self.value <= type(self.value)(other)

	def __eq__(self, other):
		if isinf(other):
			return True
		if hasattr(other, 'value'):
			other = other.value
		if isinstance(other, datetime) and not isinstance(self.value, datetime):
			return self.timestamp == other
		try:
			return type(self.value)(other) == self.value
		except (TypeError, ValueError):
			return False

	def __ne__(self, other):
		if isinf(other):
			return True
		if hasattr(other, 'value'):
			other = other.value
		if isinstance(other, datetime) and not isinstance(self.value, datetime):
			return self.timestamp != other
		return type(self.value)(other) != self.value

	def __hash__(self):
		return hash((self.value, self.timestamp))

	def __float__(self):
		try:
			return float(self.value)
		except ValueError as e:
			raise TypeError(f'{self.value} is not a float') from e

	def __int__(self):
		try:
			return int(self.value)
		except ValueError as e:
			raise TypeError(f'{self.value} is not an int') from e
		except TypeError as e:
			raise TypeError(f'{self.value} is not an int') from e

	def __str__(self):
		return str(self.value)

	def __bytes__(self):
		try:
			return bytes(self.value)
		except ValueError as e:
			raise TypeError(f'{self.value} is not a bytes') from e

	def __complex__(self):
		return complex(self.value)

	def __round__(self, n=None):
		if isinstance(n, timedelta):
			return roundToPeriod(self.value | isa | datetime or self.timestamp, n)
		return round(self.value, n)

	def __floor__(self):
		return int(self.value)

	def __ceil__(self):
		return int(self.value) + 1

	def __abs__(self):
		if isinstance(self.value, SupportsAbs):
			return abs(self.value)
		return 0

	@classmethod
	def average(cls, *items: 'TimeSeriesItem') -> 'TimeSeriesItem':
		valueCls = mostCommonClass(item.value for item in items)
		if valueCls is str:
			value = mostFrequentValue([str(item) for item in items])
			times = [item.timestamp.timestamp() for item in items if str(item) == value]
		else:
			values = [item.value for item in items]
			value = sum(values)/len(values)
			times = [item.timestamp.timestamp() for item in items]
		timestamp = datetime.fromtimestamp(sum(times)/len(times)).astimezone(_timezones.utc).astimezone(tz=LOCAL_TIMEZONE)
		if issubclass(valueCls, wu.Measurement) and {'denominator', 'numerator'}.intersection(valueCls.__init__.__annotations__.keys()):
			ref = values[0]
			n = type(ref.n)
			d = type(ref.d)(1)
			value = valueCls(numerator=n(value), denominator=d)
			return TimeSeriesItem(value, timestamp)
		return TimeSeriesItem(valueCls(value), timestamp)


@ArchivableValue.register
class MultiValueTimeSeriesItem(TimeSeriesItem):
	values: Set[TimeSeriesItem]

	def __init__(self, *values: Tuple[TimeSeriesItem]):
		self.__value = None
		if values:
			if not isinstance(values, set):
				values = set(values)
			self.values = values

	@property
	def value(self) -> Union[Hashable]:
		if self.__value is None:
			self.__value = self.average(*self.values)
		return self.__value.value

	@value.setter
	def value(self, value):
		if isinstance(value, str) or not isinstance(value, Iterable):
			value = (value,)
		self.values.update(value)
		self.__value = None

	@property
	def timestamp(self) -> datetime:
		if self.__value is None:
			self.__value = self.average(*self.values)
		return self.__value.timestamp

	def __iadd__(self, other):
		if isinstance(other, TimeSeriesItem):
			self.values.add(other)
			self.__value = None
			return self
		return NotImplemented


@TimeseriesSource.register
@ArchivableValue.register
class MiniTimeSeries(deque):
	__resolution: Union[timedelta, List[timedelta]]
	__superTimeSeries: Optional['MiniTimeSeries']
	__samples: int
	__timeOffset: int
	__itemType: Type
	__lastItem: Optional[TimeSeriesItem]

	def __init__(self, start: datetime, timespan: timedelta, resolution: timedelta, *args, **kwargs):
		self.__lastItem = None
		self.__resolution = resolution
		if start is Now():
			timespan = timedelta(minutes=-5)
		elif isinstance(timespan, Period):
			if timespan is Period.Now:
				timespan = timedelta(minutes=-5)
			else:
				timespan = timespan.value
		samples = max(int(max(timedelta(minutes=1), abs(timespan))/resolution), 1)
		self.__timespan = timespan
		self.__samples = samples
		if start is None:
			start = now()
		self.startTime = start
		super().__init__([list() for _ in range(samples)], maxlen=samples)

	@property
	def startTime(self) -> int:
		if self.__startTime is Now():
			return int(roundToPeriod(self.__startTime.now(), self.__resolution).timestamp())
		return int(self.__startTime.timestamp())

	@startTime.setter
	def startTime(self, value: datetime):
		if value is Now():
			self.__startTime = now()
			return
		value = value.astimezone(_timezones.utc)
		value = roundToPeriod(value, self.__resolution)
		self.__startTime = value

	@property
	def timestamp(self):
		value = self.last.timestamp
		value = roundToPeriod(value, self.__resolution)
		return value

	def filterKey(self, key: Union[int, datetime, timedelta]) -> int:
		seconds = int(self.__resolution.total_seconds())
		if isinstance(key, datetime):
			key = key.astimezone(_timezones.utc)
			index = int(((round(key.timestamp()/seconds)*seconds) - self.startTime)/seconds)
		elif isinstance(key, timedelta):
			index = round(key.total_seconds()/seconds)*seconds
		elif isinstance(key, int):
			index = key
		else:
			raise TypeError(f'Invalid key type {type(key)}')
		return self.__samples - 1 + index

	def setValue(self, value: Union[float, int, TimeSeriesItem], key: Union[int, datetime, timedelta] = None):
		if key is None:
			assert isinstance(value, TimeSeriesItem)
			key = value.timestamp
		index = self.filterKey(key)
		maxLength = self.__samples
		if index >= self.__samples:
			extendAmount = abs(index - self.__samples) + 1
			self.extend([list() for _ in range(extendAmount)])
			index = self.__samples - 1
			self.startTime = key
		if index < 0:
			earliest = self.startTime - len(self)*self.resolution.total_seconds()
			outOfBoundsBy = earliest - key.timestamp()
			if abs(outOfBoundsBy) > 900:
				log.warning(f'TimeSeries tried to set a value out of bounds by {wu.Time.Second(outOfBoundsBy).autoAny}')
			log.warning(f'TimeSeries tried to set a value out of bounds by {wu.Time.Second(outOfBoundsBy).autoAny}')
			return
		if not isinstance(value, TimeSeriesItem):
			value = TimeSeriesItem(value, key)
		self[index].append(value)
		if self.__lastItem is None or value.timestamp > self.__lastItem.timestamp:
			self.__lastItem = value

	def getValue(self, key: Union[int, datetime, timedelta]) -> Optional[TimeSeriesItem]:
		index = self.filterKey(key)
		if index >= self.__samples:
			index = self.__samples - 1
		value = self[index]
		if not value:
			return 0
		if len(value) == 1:
			return value[0]
		return TimeSeriesItem.average(*value)

	@property
	def value(self) -> Optional[TimeSeriesItem]:
		if last := self.last:
			return last.value
		return None

	@property
	def last(self) -> Optional[TimeSeriesItem]:
		return self.__lastItem

	@property
	def first(self):
		if all(len(item) == 0 for item in self):
			return None
		i = 0
		item = self[0]
		while len(item) == 0:
			i += 1
			item = self[i]
		return item[0]

	def __getitem__(self, item) -> TimeAwareValue:
		if isinstance(item, slice):
			if isinstance(item.start, datetime):
				start = item.start or self.timestamp
				end = item.stop or (start - self.__resolution*(self.__samples - 1))
				step = item.step

				# determine the start and end index
				startI, endI = sorted(i for i in [self.filterKey(start), self.filterKey(end)])

				# keep it in bounds and if the step is greater than 1 go one step out of bounds
				startI = min(max(0, startI - 1 if step else 0), len(self) - 1)
				endI = max(min(len(self), endI + 2 if step else 1), 0)
				if endI == startI:
					if startI >= len(self):
						raise IndexError(f'Index {startI} is out of bounds')
					elif startI < 0:
						raise IndexError(f'Index {startI} is out of bounds')
					values = [self[startI]]
				values = list(self)[startI:endI]

				if step and startI != 0 and endI != len(self):
					values = [i for j in values for i in j if start <= i.timestamp <= end]
					if isinstance(step, timedelta):
						resolution = step.total_seconds()
						span = (end - start).total_seconds()
						length = int(span/resolution) + 1
						items = [[] for _ in range(length)]
						for i in range(len(values)):
							index = round((values[i].timestamp - start).total_seconds()/resolution)
							items[index].append(values[i])
						values = [TimeSeriesItem.average(*i) for i in items if i]
					elif step > 1:
						values = values[::step]
				else:
					# If the step is zero, each slot is averaged to a single value
					values = [TimeSeriesItem.average(*i) for i in values if len(i)]

				return values
			if isinstance(item.start, float):
				values = [i for j in self for i in j]
		return super().__getitem__(item)

	def rollingAverage(self, *window: Union[int, timedelta, Tuple[datetime, datetime]]) -> TimeSeriesItem:
		if len(window) == 1:
			window = window[0]
		if isinstance(window, timedelta):
			if window.total_seconds() > 0:
				window = -window
			start = self.last.timestamp
			end = start + window
		elif isinstance(window, int):
			start = self.startTime
			end = start + self.__resolution*window
		elif isinstance(window, tuple):
			start, end = window
		values = self[start:end:1]
		if values:
			return TimeSeriesItem.average(*values)
		return None

	@property
	def resolution(self) -> timedelta:
		if isinstance(self.__resolution, timedelta):
			return self.__resolution
		return self.__resolution[0]

	@property
	def archived(self) -> TimeSeriesItem:
		return TimeSeriesItem(self.value, self.timestamp)

	def flatten(self) -> List[TimeSeriesItem]:
		return list(set(i for j in self for i in j))


@ArchivableValue.register
class RecordedObservationValue(ObservationValue):
	__history: MiniTimeSeries
	__resolution: timedelta

	"""
	Keeps a record of all the values that are reported to it in a deque. For this class, there
	is a fixed start and stop time for which the values are recorded.
	"""

	def __init__(self, value, key, source: Any,
		container: 'ObservationDict',
		metadata: dict = None, timeAnchor: datetime = None,
		duration: timedelta = None, resolution: timedelta = None):
		if duration is None:
			if hasattr(container, 'period'):
				duration = container.period
				if isinstance(duration, Period):
					duration = duration.value
			else:
				duration = timedelta(minutes=5)
		if isinstance(value, TimeAwareValue):
			timeAnchor = value.timestamp
		else:
			timeAnchor = timeAnchor or source.timestamp
		if isinstance(timeAnchor, ObservationTimestamp):
			timeAnchor = timeAnchor.value

		# This assumes that the observation time series keys are being rounded,
		# which is the case for the ObservationTimeSeries
		if isinstance(container, RealtimeSource):
			start = Now()
		else:
			start = roundToPeriod(timeAnchor - timedelta(seconds=1), duration) - duration/2

		self.__history = MiniTimeSeries(start=start, timespan=duration, resolution=resolution or timedelta(seconds=15))
		self.__lastCollection = datetime.now().astimezone(_timezones.utc)
		super().__init__(value, key, source, metadata)
		flat = self.__history.flatten()
		if not flat:
			self.__history = MiniTimeSeries(start=start, timespan=duration, resolution=resolution or timedelta(seconds=15))
			self.value = value

	@property
	def __rawValue(self):
		if self.__history:
			return self.__history.value
		return None

	@__rawValue.setter
	def __rawValue(self, value):
		self.__value = None

	@property
	def rawValue(self):
		return self.__rawValue

	@property
	def isValid(self):
		return self.__history.last is not None

	@property
	def value(self):
		if not self.isValid:
			return NoValue
		if self.__value is None:
			try:
				value = self.convertFunc(self.rawValue)
			except TypeError:
				value = self.rawValue
			if localized := getattr(value, 'localize', None):
				value = localized
			self.__value = value
		return self.__value

	@value.setter
	def value(self, value):
		if isinstance(value, ObservationValue):
			if isinstance(value.rawValue, TimeAwareValue):
				value = value.rawValue
			else:
				value = TimeSeriesItem(toLiteral(value.rawValue), value.timestamp)
		elif not isinstance(value, TimeSeriesItem):
			value = TimeSeriesItem(value, self.source.timestamp)
		self.__history.setValue(value)
		self.__value = None

	@property
	def history(self) -> MiniTimeSeries:
		return self.__history

	@property
	def resolution(self):
		return self.__resolution

	@resolution.setter
	def resolution(self, value):
		self.__resolution = value

	@property
	def timestamp(self):
		return self.__history.timestamp

	def archivedFrom(self, from_: datetime = None, to: datetime = None) -> Optional[TimeSeriesItem]:
		from_ = from_ or self.first.timestamp
		to = to or self.last.timestamp
		rawValue = self.history.rollingAverage(from_, to)
		if rawValue is None:
			return None
		try:
			value = self.convertFunc(rawValue.value)
			sourceUnitValue = self.convertFunc(rawValue.value)
		except Exception as e:
			log.error(f'Error converting value {rawValue.value} to {self.convertFunc}', exc_info=e)
			return None
		if hasattr(value, 'localize'):
			value = value.localize
		if value:
			return ArchivedObservationValue(origin=self, value=value, rawValue=rawValue, sourceUnitValue=sourceUnitValue)
		return None

	@property
	def archived(self):
		lastCollection = self.__lastCollection
		self.__lastCollection = thisCollection = UTC()
		value = self.archivedFrom(lastCollection, thisCollection)
		return value

	@property
	def first(self):
		return self.__history.first

	@property
	def last(self):
		return self.__history.last

	def rollingAverage(self, *window: Union[int, timedelta, Tuple[datetime, datetime]]) -> ObservationValue:
		value = self.history.rollingAverage(*window)
		if value:
			metadata = self.metadata
			source = self.source
			return ObservationValue(value, self.key, container=self.container, source=source, metadata=metadata)
		return None


class ObservationTimestamp(ObservationValue):

	# TODO: Convert to class generated for each PublishedDict with a set 'source' therefore 'source' is not need for initialization.
	#       Especially since the source is not the proper term here

	def __init__(self, data: dict, source: 'ObservationDict', extract: bool = True, roundedTo: timedelta = None):
		self.__roundedTo = roundedTo

		if isinstance(data, ObservationDict):
			value = data.timestamp
			key = 'timestamp'
		elif isinstance(data, LevityDatagram):
			key = '@meta.timestamp'
			value = data[key]
		elif isinstance(data, dict):
			if CategoryItem('timestamp') in data:
				key = 'timestamp'
			else:
				key = source.schema.findKey('timestamp', data)
			if extract:
				value = data.pop(key, None)
			else:
				value = data[key]
		elif isinstance(data, datetime):
			value = data
			key = CategoryItem('timestamp')
		else:
			log.warn(f'Unable to find valid timestamp in {data}.  Using current time.')
			value = datetime.now().astimezone(_timezones.utc)
			key = CategoryItem('timestamp')
		super(ObservationTimestamp, self).__init__(value, key, container=source, source=source)
		if isinstance(value, datetime):
			self.__value = value
			if self.__value.tzinfo is None:
				# This assumes the timezone for the provided timestamp is the local timezone
				preVal = self.__value
				self.__value = self.__value.astimezone().astimezone(_timezones.utc)
				postVal = self.__value.replace(tzinfo=None)
				pluginLog.warning(f"Timestamp {self} does not have a timezone.  "
				                  f"Assuming Local Timezone and converting to UTC with a "
				                  f"difference of {wu.Time.Second((abs((preVal - postVal)).total_seconds())).autoAny}")

	@ObservationValue.value.getter
	def value(self):
		value = super(ObservationTimestamp, self).value
		if self.__roundedTo:
			return roundToPeriod(value, self.__roundedTo)
		return value

	@property
	def __timestamp(self):
		if isinstance(self.rawValue, datetime):
			value = self.rawValue
		else:
			value = self.value
		if self.__roundedTo:
			return roundToPeriod(value, self.__roundedTo)
		return value

	def __repr__(self):
		return f'{self.value.strftime("%-I:%M%p %m/%d")}'

	def __str__(self):
		return self.__repr__()

	def __lt__(self, other):
		if isinstance(other, ObservationTimestamp):
			return self.__timestamp < other.__timestamp
		return self.__timestamp < other

	def __le__(self, other):
		if isinstance(other, ObservationTimestamp):
			return self.__timestamp <= other.__timestamp
		return self.__timestamp <= other

	def __eq__(self, other):
		if isinstance(other, ObservationTimestamp):
			return self.__timestamp == other.__timestamp
		return self.__timestamp == other

	def __ne__(self, other):
		if isinstance(other, ObservationTimestamp):
			return self.__timestamp != other.__timestamp
		return self.__timestamp != other

	def __gt__(self, other):
		if isinstance(other, ObservationTimestamp):
			return self.__timestamp > other.__timestamp
		return self.__timestamp > other

	def __ge__(self, other):
		if isinstance(other, ObservationTimestamp):
			return self.__timestamp >= other.__timestamp
		return self.__timestamp >= other

	def __hash__(self):
		return hash(self.__timestamp)


@ArchivedObservationValue.register
class MultiSourceValue(ObservationValue):

	def __init__(self, anonymousKey: CategoryItem, source: 'ObservationDict', metadata: dict = None):
		self.__key = anonymousKey.anonymous
		self.__source = source
		self.__rawValue = True

	@property
	def value(self):
		sourceValues: list[ObservationValue] = [self.__source[_] for _ in self.__source if not _.isAnonymous and _.anonymous == self.__key]
		sourceValues = sorted(sourceValues, key=lambda x: x.timestamp)
		return sourceValues[-1].value

	def __repr__(self):
		return f'MultiSource: {self.value}'

	@property
	def rawValue(self):
		return


from typing import Dict, List, Optional, Union

T = Dict[CategoryItem, ObservationValue]
SeriesData = Dict[Union[ObservationTimestamp, datetime], T]


class PublishedDict(T, metaclass=ABCMeta):
	accumulator: Optional[Accumulator]


class ObservationDict(PublishedDict):
	_source: 'Plugin'
	_time: datetime
	period = Period.Now
	_ignoredFields: set[str] = set()
	__timestamp: Optional[ObservationTimestamp] = None

	__sourceKeyMap__: ClassVar[Dict[str, CategoryItem]]
	__recorded: ClassVar[bool]
	__keyed: ClassVar[bool]
	itemClass: ClassVar[Type[ObservationValue]]

	accumulator: Accumulator
	dataName: Optional[str]

	@property
	def name(self):
		return self.dataName or self.__class__.__name__

	def __init_subclass__(cls, category: str = None,
		published: bool = None,
		recorded: bool = None,
		sourceKeyMap: Dict[str, CategoryItem] = None,
		itemClass: Union[Type[ObservationValue], Type['Observation']] = None,
		keyed: bool = False,
		**kwargs):
		cls.__sourceKeyMap__ = sourceKeyMap
		if cls.__sourceKeyMap__ is None:
			cls.__sourceKeyMap__ = {}
		k = kwargs.get('keyMap', {})

		if category is not None:
			cls.category = CategoryItem(category)

		if published is not None:
			cls.__published = published

		cls.__recorded = recorded

		cls.__keyed = keyed

		if itemClass is not None:
			cls.itemClass = itemClass
		else:
			if recorded:
				RecordedObservation.register(cls)
				cls.itemClass = type(cls.__name__ + 'Value', (RecordedObservationValue,), {})
				RecordedObservation.register(cls.itemClass)
				if 'Realtime' in cls.__name__ or issubclass(cls, RealtimeSource):
					RealtimeSource.register(cls.itemClass)
			else:
				cls.itemClass = type(cls.__name__ + 'Value', (ObservationValue,), {})

		cls.log = pluginLog.getChild(cls.__name__)
		return super(ObservationDict, cls).__init_subclass__()

	def __init__(self, published: bool = None, recorded: bool = None, timestamp: Optional[ObservationTimestamp] = None, *args, **kwargs):
		self._uuid = uuid4()
		self.__lock = kwargs.get('lock', None) or Lock()
		self.__timestamp = timestamp
		self._published = published
		self._recorded = recorded
		self.__dataName = None

		if self.published:
			self.accumulator = Accumulator(self)

		if not self.__class__.__recorded and recorded:
			RecordedObservation.register(self)
			self.__class__.__recorded = True

		super(ObservationDict, self).__init__()

	def __hash__(self):
		return hash(self._uuid)

	def __repr__(self):
		return f'{self.__class__.__name__}'

	def __contains__(self, item):
		item = convertToCategoryItem(item)
		return super(ObservationDict, self).__contains__(item)

	async def asyncUpdate(self, data, **kwargs):
		self.update(data, **kwargs)

	def update(self, data: dict, **kwargs):
		if self.published:
			self.accumulator.muted = True

		if self.dataName in data:
			if isinstance(data, LevityDatagram):
				data = data.get(self.dataName)
			else:
				data = data[self.dataName]
		if 'data' in data:
			data = data.pop('data')
		timestamp = ObservationTimestamp(data, self, extract=True).value
		for key, item in data.items():
			key = convertToCategoryItem(key, source=None)
			if not isinstance(item, TimeAwareValue):
				item = TimeSeriesItem(item, timestamp)
			self[key] = item

		self.calculateMissing(set(data.keys()))  # TODO: Use Requirements to handle this automatically based on schema

		if self.published:
			self.accumulator.muted = False

	def extractTimestamp(self, data: dict) -> datetime:
		if self.__timestamp is None:
			self.__timestamp = ObservationTimestamp(data, self, extract=True)
		return self.__timestamp

	def setTimestamp(self, timestamp: Union[datetime, dict, ObservationTimestamp]):
		if timestamp is None:
			return
		if isinstance(timestamp, ObservationTimestamp):
			self.__timestamp = timestamp
		elif isinstance(timestamp, dict):
			self.__timestamp = ObservationTimestamp(timestamp, self, extract=True)
		else:
			self.__timestamp = ObservationTimestamp(timestamp, self)

	def __setitem__(self, key, value):
		if key in self.__sourceKeyMap__:
			key = self.__sourceKeyMap__[key]
		key = convertToCategoryItem(key)
		noChange = False
		if (existing := self.get(key, None)) is not None:
			previousValue = existing.value
			existing.value = value
			noChange = previousValue == existing.value
		else:
			if isinstance(value, self.itemClass):
				super(ObservationDict, self).__setitem__(value.key, value)
			elif isinstance(value, ObservationValue):
				value = self.itemClass(value=value, key=key, source=value.source, container=self)
				super(ObservationDict, self).__setitem__(value.key, value)
			elif value is not None:
				value = self.itemClass(value=value, key=key, source=self, container=self)  # Eventually 'source' should be the gathered from 'update()
				valueKey = convertToCategoryItem(value.key)
				key = valueKey
				super(ObservationDict, self).__setitem__(valueKey, value)
			else:
				super(ObservationDict, self).__setitem__(key, None)
		if self.published:
			if noChange:
				self.accumulator.publishSilently(key)
			else:
				self.accumulator.publish(key)

	def __getitem__(self, item):
		item = convertToCategoryItem(item)

		if item not in self.keys() and item in self.__sourceKeyMap__:
			item = self.__sourceKeyMap__[item]

		try:
			if self.keyed and item.source is None:
				value = MultiSourceValue(anonymousKey=item, source=self)
				super(ObservationDict, self).__setitem__(item, value)
				return value
			return super(ObservationDict, self).__getitem__(item)
		except KeyError:
			pass
		# if key contains wildcards return a dict containing all the _values
		# Possibly later change this to return a custom subcategory
		if item.hasWildcard:
			return self.categories[item]
			# if the last value in the key assume all matching _values are being requested
			wildcardValues = {k: v for k, v in self.items() if k < item}
			if wildcardValues:
				return wildcardValues
			else:
				raise KeyError(f'No keys found matching {item}')
		else:
			return self.categories[item]

	def calculateMissing(self, keys: set = None):
		if keys is None:
			keys = set(self.keys()) - self._calculatedKeys
		light = {'environment.light.illuminance', 'environment.light.irradiance'}

		if 'environment.temperature.temperature' in keys:
			temperature = self['environment.temperature.temperature']
			timestamp = temperature.timestamp
			temperature = temperature.sourceUnitValue

			if 'environment.humidity.humidity' in keys:
				humidity = self['environment.humidity.humidity']

				if 'environment.temperature.dewpoint' not in keys:
					self._calculatedKeys.add('environment.temperature.dewpoint')
					dewpoint = temperature.dewpoint(humidity.value)
					dewpoint.key = CategoryItem('environment.temperature.dewpoint')
					dewpoint = TimeSeriesItem(dewpoint, timestamp=timestamp)
					self['environment.temperature.dewpoint'] = dewpoint

				if 'environment.temperature.heatIndex' not in keys and self.schema.get('environment.temperature.heatIndex', None):
					self._calculatedKeys.add('environment.temperature.heatIndex')
					heatIndex = temperature.heatIndex(humidity.value)
					heatIndex.key = CategoryItem('environment.temperature.heatIndex')
					heatIndex = TimeSeriesItem(heatIndex, timestamp=timestamp)
					self['environment.temperature.heatIndex'] = heatIndex
					keys.add('environment.temperature.heatIndex')

			if 'environment.wind.speed.speed' in keys:
				windSpeed = self['environment.wind.speed.speed']
				if isinstance(windSpeed, RecordedObservationValue):
					windSpeed = windSpeed.rollingAverage(timedelta(minutes=-5)) or windSpeed
				if 'environment.temperature.windChill' not in keys and self.schema.get('environment.temperature.windChill', None):
					self._calculatedKeys.add('environment.temperature.windChill')
					windChill = temperature.windChill(windSpeed.value)
					windChill.key = CategoryItem('environment.temperature.windChill')
					windChill = TimeSeriesItem(windChill, timestamp=timestamp)
					self['environment.temperature.windChill'] = windChill
					keys.add('environment.temperature.windChill')

			if 'environment.temperature.feelsLike' not in keys and all(i in keys for i in ['environment.temperature.windChill', 'environment.temperature.heatIndex']):
				self._calculatedKeys.add('environment.temperature.feelsLike')
				heatIndex = locals().get('heatIndex', None) or self['environment.temperature.heatIndex']
				windChill = locals().get('windChill', None) or self['environment.temperature.windChill']
				humidity = locals().get('humidity', None) or self['environment.humidity.humidity']
				if temperature.f > 80 and humidity.value > 40:
					feelsLike = heatIndex.value
				elif temperature.f < 50:
					feelsLike = windChill.value
				else:
					feelsLike = temperature
				feelsLike = TimeSeriesItem(float(feelsLike), timestamp=timestamp)
				self['environment.temperature.feelsLike'] = feelsLike

		if 'indoor.temperature.temperature' in keys:
			temperature = self['indoor.temperature.temperature']
			timestamp = self['indoor.temperature.temperature'].timestamp
			temperature = temperature.sourceUnitValue

			if 'indoor.humidity.humidity' in keys:
				humidity = self['indoor.humidity.humidity']

				if 'indoor.temperature.dewpoint' not in keys:
					self._calculatedKeys.add('indoor.temperature.dewpoint')
					dewpoint = temperature.dewpoint(humidity.value)
					dewpoint.key = CategoryItem('indoor.temperature.dewpoint')
					dewpoint = TimeSeriesItem(dewpoint, timestamp=timestamp)
					self['indoor.temperature.dewpoint'] = dewpoint

				if 'indoor.temperature.heatIndex' not in keys:
					self._calculatedKeys.add('indoor.temperature.heatIndex')
					heatIndex = temperature.heatIndex(humidity.value)
					heatIndex.key = CategoryItem('indoor.temperature.heatIndex')
					heatIndex = TimeSeriesItem(heatIndex, timestamp=timestamp)
					self['indoor.temperature.heatIndex'] = heatIndex

	def timeKey(self, data) -> str:
		if 'timestamp' in data:
			return 'timestamp'
		unitData = self.schema.getExact(CategoryItem('timestamp')) or {}
		srcKey = unitData.get('sourceKey', dict())
		if isinstance(srcKey, (str, CategoryItem)):
			return srcKey
		for key in srcKey:
			if key in data:
				return key
		else:
			return (set(data.keys()).intersection({'time', 'timestamp', 'day_start_local', 'date', 'datetime'})).pop()

	def timezoneKey(self, data) -> str | None:
		if 'time.timezone' in data:
			return 'time.timezone'
		if 'time.timezone' in self.schema:
			return self.schema['time.timezone']['sourceKey']
		else:
			value = set(data.keys()).intersection({'timezone', 'timezone_name', 'tz'})
			if value:
				return value.pop()
			else:
				return None

	@property
	def timestamp(self):
		return self.__timestamp

	@property
	def dataName(self):
		return self.__dataName

	@dataName.setter
	def dataName(self, value):
		self.__dataName = value

	@property
	def lock(self) -> Lock:
		return self.__lock

	@property
	def published(self) -> bool:
		if self._published is None:
			return self.__published
		else:
			return self._published

	@property
	def recorded(self):
		if self._recorded is None:
			return self.__recorded
		return self._recorded

	@property
	def keyed(self) -> bool:
		return self.__keyed

	@property
	def schema(self):
		return self.source.schema

	@cached_property
	def normalizeDict(self):
		return {value['sourceKey']: key for key, value in self.schema.items() if 'sourceKey' in value}

	@property
	def source(self):
		return self._source

	@source.setter
	def source(self, value):
		if hasattr(value, 'observations'):
			self._source = value
			if self.published:
				self.accumulator.connectSlot(value.publisher.publish)

	@cached_property
	def categories(self):
		return CategoryDict(self, self, None)


@Archivable.register
class Observation(ObservationDict, published=False, recorded=False):
	unitDict = unitDict
	_schema: dict
	_time: datetime = None
	_calculatedKeys: set

	def __init_subclass__(cls, **kwargs):
		super().__init_subclass__(**kwargs)
		cls._calculatedKeys = set()

	@property
	def sortKey(self):
		time: ObservationTimestamp = self.timestamp
		if time is None:
			return timedelta(0)
		if isinstance(time, ObservationTimestamp):
			time = time.value
		return datetime.now(tz=time.tzinfo) - time

	@property
	def archived(self):
		return ArchivedObservation(self)


@Archived.register
class ArchivedObservation(Observation, published=False, recorded=False):

	def __init__(self, source: Optional[Archivable] = None, *args, **kwargs):
		if source:
			values = {key: v for key, value in source.items() if (v := (value.archived if isinstance(value, ArchivableValue) else copy(value))) is not None}
			if values:
				times = [i.timestamp.timestamp() for i in values.values()]
				self.timestamp = datetime.fromtimestamp(sum(times)/len(times)).astimezone(_timezones.utc).astimezone(tz=LOCAL_TIMEZONE)
				dict.__init__(self, values)
				return
		dict.__init__(self)

	def __setattr__(self, key, value):
		if key == 'timestamp' and (not hasattr(self, 'timestamp') or self.timestamp is None):
			self.__dict__[key] = value
			return
		raise AttributeError('ArchivedObservation is immutable')

	def __delattr__(self, key):
		raise AttributeError('ArchivedObservation is immutable')

	def __setitem__(self, key, value):
		raise AttributeError('ArchivedObservation is immutable')

	def __delitem__(self, key):
		raise AttributeError('ArchivedObservation is immutable')

	def update(self, *args, **kwargs):
		if len(self) > 0:
			dict.update(*args, **kwargs)
		raise AttributeError('ArchivedObservation is immutable')

	def calculateMissing(self) -> None:
		return

	@property
	def timestamp(self):
		return self.__dict__.get('timestamp')


@RealtimeSource.register
class ObservationRealtime(Observation, published=True, recorded=True):
	time: datetime
	timezone: tzinfo
	subscriptionChannel: str = None
	_indoorOutdoor: bool = False

	def __init__(self, source: 'Plugin', *args, **kwargs):
		self._source = source
		super(ObservationRealtime, self).__init__(*args, **kwargs)

	def udpUpdate(self, data):
		self.update(data)

	@property
	def timestamp(self):
		timestamps = [value.timestamp.timestamp() for value in self.values() if isinstance(value, TimeAwareValue)] or [datetime.now().astimezone(_timezones.utc).timestamp()]
		average = sum(timestamps)/len(timestamps)
		return datetime.fromtimestamp(average).astimezone(LOCAL_TIMEZONE)


@TimeseriesSource.register
class ObservationTimeSeriesItem(Observation, published=False):

	def __init__(self, *args, timeseries: 'ObservationTimeSeries', **kwargs):
		super(ObservationTimeSeriesItem, self).__init__(*args, **kwargs)
		self.__timeseries = timeseries
		self.setTimestamp(kwargs.get('timestamp'))

	@property
	def timeseries(self):
		return self.__timeseries

	@property
	def dataName(self):
		return self.timeseries.dataName

	@property
	def period(self):
		return self.__timeseries.period

	@property
	def source(self):
		return self.__timeseries.source

	def archive(self):
		for key, value in self.items():
			if isinstance(value, ArchivableValue):
				if hasattr(value, 'history'):
					value = value.history.archived
				super(ObservationTimeSeriesItem, self).__setitem__(key, value)


@TimeseriesSource.register
class ObservationTimeSeries(ObservationDict, published=True):
	__knownKeys: set[CategoryItem]
	_ignoredFields: set[CategoryItem] = set()
	period: timedelta
	timeframe: timedelta
	__timeseries__: dict[DateKey, Observation]

	itemClass: Type[ObservationTimeSeriesItem]

	def __init_subclass__(cls, **kwargs):
		recorded = kwargs.get('recorded', None)
		sourceKeyMap = kwargs.get('sourceKeyMap', {})
		published = kwargs.get('published', False)
		itemClass = type(f'{cls.__name__}Item', (ObservationTimeSeriesItem,), {}, published=published, recorded=recorded, sourceKeyMap=sourceKeyMap)
		if recorded and hasattr(cls, 'FrozenValueClass'):
			itemClass.FrozenClass = cls.FrozenValueClass
		super().__init_subclass__(itemClass=itemClass, **kwargs)

	def __init__(self, source: 'Plugin', *args, **kwargs):
		self._source = source
		super(ObservationTimeSeries, self).__init__(*args, **kwargs)
		self.__knownKeys = set()
		self.__timeseries__ = {}

	def calculateMissing(self):
		# TODO: Add support for calculating high and lows from hourly and supplying them to daily observations
		if 'precipitationAccumulation' not in self.knownKeys and (key := self.keySelector('precipitation', 'precipitationRate')):
			accumulation = self[key][0].__class__(self[key][0].__class__.Millimeter(0)).localize
			for obs in self['time'].values():
				accumulation += obs[key]
				obs['precipitationAccumulation'] = accumulation
		self['datetime'] = [time.datetime for time in self['time'].keys()]

	def keySelector(self, *keys) -> Union[bool, str]:
		s = set(keys).intersection(self.knownKeys)
		if s:
			return list(s)[0]
		return False

	@property
	def knownKeys(self):
		return self.__knownKeys

	def update(self, data: dict, **kwargs):
		keyMap = data.get('keyMap', {})

		source = [self.source.name]
		if 'source' in kwargs:
			source.append(*kwargs['source'])
		if 'source' in data:
			source.append(data['source'])
		if self.dataName in data:
			data = data[self.dataName]
		if 'data' in data:
			raw = data.pop('data')
		else:
			raw = data

		if isinstance(raw, dict):
			# incoming item is a single observation
			if any(isinstance(value, (ObservationValue, int, float, str)) for value in raw.values()):
				raw = [raw]
			# incoming item is a list of observations
			else:
				raw = list(raw.values())

		keys = set()

		if not isinstance(raw, List):
			raise ValueError('ObservationTimeSeries.update: data must be a dict or a list of dicts')

		def updateWithProgress(raw: List[Dict], progress: Progress | None):
			for rawObs in raw:
				if not isinstance(rawObs, Mapping):
					rawObs = {k: v for k, v in zip(keyMap, rawObs)}
				key = ObservationTimestamp(rawObs, self, False, roundedTo=self.period)
				obs = self.__timeseries__.get(key, None) or self.buildObservation(key)
				obs.update(rawObs, source=source)
				keys.update(obs.keys())
				if progress is not None:
					progress.update(task, advance=1, refresh=True)
			if progress is not None:
				progress.update(task, complete=True, refresh=True)

		if len(raw) > 5:
			with Progress() as progress:
				task = progress.add_task(f'Updating [blue]{source[0]}.{self.dataName}', total=len(raw), transient=True)
				updateWithProgress(raw, progress)
				progress.refresh()
		else:
			updateWithProgress(raw, None)

		self.__knownKeys.update(keys)

		keys = {key for key in keys if key.category not in self._ignoredFields and key.category ^ 'time'}

		self.removeOldObservations()
		for key in keys.intersection(self.keys()):
			self[key].refresh()
		if self.published:
			self.accumulator.publish(*keys)

	def __missing__(self, key):
		if key in self.__knownKeys:
			timeseries = MeasurementTimeSeries(self, key)
			dict.__setitem__(self, key, timeseries)
			return timeseries
		else:
			raise KeyError(f'{key} is not a known key')

	def __contains__(self, key):
		if isinstance(key, str):
			key = CategoryItem(key)
		if isinstance(key, CategoryItem):
			return key in self.__knownKeys
		elif isinstance(key, ObservationTimestamp):
			return key in self.__timeseries__
		elif isinstance(key, datetime):
			return key in self.__timeseries__
		return False

	def removeOldObservations(self):
		return
		now = roundToPeriod(datetime.now(tz=LOCAL_TIMEZONE), self.period, method=int)
		toPass = {}
		for key in {(key, value) for key, value in self.__timeseries__.items() if key < now}:
			toPass[key] = self.destroyObservation(key)
		if toPass:
			self.accumulator.publish(*toPass.keys())
			self.source.ingestHistorical(toPass)

	def buildObservation(self, timestamp: ObservationTimestamp) -> Observation:
		item = self.itemClass(timeseries=self, source=self.source, timestamp=timestamp, published=False, lock=self.lock)
		self[timestamp] = item
		return item

	def destroyObservation(self, key: ObservationTimestamp):
		return
		return self.__timeseries__.pop(key)

	def calculatePeriod(self, data: list):
		if isinstance(data[0], dict):
			time = np.array([self._observationClass.observationKey(v).timestamp() for v in data])
		elif isinstance(data[0], list):
			time = np.array([x[0] for x in data])
		else:
			raise TypeError(f'{type(data[0])} is not supported yet')
		meanTime = datetime.fromtimestamp(int(np.mean(time)), tz=LOCAL_TIMEZONE)
		period = timedelta(seconds=((time - np.roll(time, 1))[1:].mean()))
		if period.total_seconds() > 0 and meanTime < datetime.now(tz=LOCAL_TIMEZONE):
			period = timedelta(-period.total_seconds())
		self._period = period

	def __updateObsKey(self, key):
		self[key] = MeasurementTimeSeries(self, key, [x[key] if key in x.keys() else None for x in self['time'].values()])

	def __genObsValueForKey(self, key):
		self[key] = [None if key not in x.keys() else x[key] for x in self['time'].values()]

	def observationKey(self, data) -> DateKey:
		timeData = self.schema['time']['time']
		timeValue = data[self.timeKey(data)]
		tz = data.get(self.timezoneKey(data), LOCAL_TIMEZONE)
		if timeData['sourceUnit'] == 'epoch':
			return DateKey(datetime.fromtimestamp(timeValue, tz))
		if timeData['sourceUnit'] == 'ISO8601':
			key = DateKey(parse(timeValue).astimezone(tz))
			return key

	def extractTimestamp(self, data: dict) -> datetime:
		key = self.schema.findKey('timestamp', data)
		self[key] = data.pop(key)

	@property
	def timeseries(self):
		return self.__timeseries__

	@property
	def period(self) -> wu.Time:
		if self._period is None:
			return wu.Time.Second(1)
		return self._period

	@property
	def timeframe(self) -> timedelta:
		if self.timestamps:
			return self.timestamps[-1].datetime - self.timestamps[0].datetime
		else:
			return timedelta(0)

	@property
	def timestamps(self):
		return list(self['time'].keys())

	@property
	def schema(self):
		return self.source.schema

	def observationKeys(self):
		return list({key for obs in (self['time'].values() if isinstance(self['time'], dict) else self['time']) for key in obs.keys()})

	def timeseriesValues(self):
		return self.__timeseries__.values()

	def timeseriesKeys(self):
		return self.__timeseries__.keys()

	def timeseriesItems(self):
		return self.__timeseries__.items()

	def keys(self):
		return self.__knownKeys

	def __iter__(self):
		return self.__timeseries__.__iter__()

	def __makeKey(self, data: dict):
		return self.observationKey(data)

	def __getitem__(self, key) -> Union[List[wu.Measurement], Observation]:
		if isinstance(key, CategoryItem):
			if key in self.__knownKeys:
				return super(ObservationTimeSeries, self).__getitem__(key)
			else:
				raise KeyError(f'{key} is not a known key')
		if isinstance(key, (ObservationTimestamp, datetime)):
			return self.__timeseries__[key]
		return super(ObservationTimeSeries, self).__getitem__(key)

	def __setitem__(self, key, value):
		if isinstance(key, ObservationTimestamp):
			if self._period is None:
				self.calculatePeriod(value)

			self.__timeseries__[key] = value
			self.__knownKeys.add(key)
		else:
			raise KeyError(f'Only "ObservationTimestamp" is supported as key')

	@cached_property
	def categories(self):
		return CategoryDict(self, {k: self[k] for k in self.__knownKeys}, '')

	@property
	def raw(self):
		return self['raw']

	@property
	def sortKey(self):
		return self.period


@TimeseriesSource.register
class ObservationLog(ObservationTimeSeries, published=False, recorded=True):
	archiveAfter: timedelta = timedelta(minutes=15)  # TODO: Make this a configurable option

	@ObservationTimeSeries.period.getter
	def period(self) -> timedelta:
		p = super(ObservationLog, self).period or timedelta(seconds=-1)
		if p.total_seconds() > 0:
			p *= -1
		return p

	def removeOldObservations(self):
		keepFor = timedelta(days=2)
		cutoff = roundToPeriod(datetime.now(tz=LOCAL_TIMEZONE), self.period) - keepFor
		for key in [k for k in self if k < cutoff]:
			del self.__timeseries__[key]

	def __setitem__(self, key, value):
		super(ObservationLog, self).__setitem__(key, value)

		if key.value | isOlderThan | timedelta(minutes=15):
			self.__timeseries__[key].archive()
		else:
			archiveAfter = self.archiveAfter.total_seconds() - (key.value.timestamp() - datetime.now().timestamp())
			loop.call_later(archiveAfter, self.__timeseries__[key].archive)

	def buildObservation(self, key: ObservationTimestamp) -> Observation:
		item = self.itemClass(timeseries=self, source=self.source, timestamp=key, published=False, lock=self.lock)
		self[key] = item
		return item


class TimeSeriesSignal(ChannelSignal):
	__lastHash: int
	_signal = Signal()
	_source: 'MeasurementTimeSeries'
	_singleShots: Dict[Hashable, coroutine]
	_conditionalSingleShots: Dict[coroutine, Callable[['MeasurementTimeSeries'], bool]]

	def __init__(self, parent: 'MeasurementTimeSeries'):
		self._singleShots = {}
		self._conditionalSingleShots = {}
		self.__lashHash = 0
		super(TimeSeriesSignal, self).__init__(parent, parent.key)

	def __repr__(self):
		return f'<{repr(self._source)}.Publisher>'

	@property
	def muted(self):
		return ChannelSignal.muted.fget(self)

	@muted.setter
	def muted(self, value: bool):
		ChannelSignal.muted.fset(self, value)
		if self._source.isMultiSource:
			sources = [s for s in self._source.sources if isinstance(s, MeasurementTimeSeries)]
			for source in sources:
				source.signals.muted = value

	def _emit(self):
		self._signal.emit()
		if self._singleShots and self._source.hasTimeseries:
			for coro in self._singleShots.values():
				loop.create_task(coro)
		self._singleShots.clear()
		coroutines = [coro for coro, condition in self._conditionalSingleShots.items() if condition(self._source)]
		list(self._conditionalSingleShots.pop(coro, None) for coro in coroutines)
		for coro in coroutines:
			loop.create_task(coro)

	def addCallback(self, callback: coroutine, guardHash=None):
		if not iscoroutine(callback):
			raise TypeError(f'{callback} is not a coroutine')
		guardHash = guardHash or hash(callback)
		if (existing := self._singleShots.pop(guardHash, None)) is not None:
			existing.close()
		self._singleShots[guardHash] = callback

	def addConditionalCallback(self, callback: coroutine, condition: Callable[['MeasurementTimeSeries'], bool]):
		if not iscoroutine(callback):
			raise TypeError(f'{callback} is not a coroutine')
		# if (existing := self._conditionalSingleShots.pop(callback, None)) is not None:
		# 	callback.close()
		self._conditionalSingleShots[callback] = condition

	def connectSlot(self, slot) -> bool:
		connected = super(TimeSeriesSignal, self).connectSlot(slot)
		if connected and not len(self._source):
			self._source.refresh()
		return connected

	@property
	def hasConnections(self) -> bool:
		return bool(len(self._connections) or len(self._singleShots))

	@property
	def connectedItems(self) -> List[Slot]:
		return list(self._connections.values())


class TimeHash:
	__slots__ = ('__interval')

	def __init__(self, interval: timedelta | int):
		if isinstance(interval, timedelta):
			interval = interval.total_seconds()
		self.__interval = interval

	def __hash__(self):
		return int(loop.time()//self.__interval)


TimeHash.Daily = TimeHash(timedelta(days=1))
HourLy = TimeHash(timedelta(hours=1))
TimeHash.HalfHour = TimeHash(timedelta(minutes=30))
TimeHash.QuarterHour = TimeHash(timedelta(minutes=15))
TimeHash.Minutely = TimeHash(timedelta(minutes=1))
TimeHash.Secondly = TimeHash(timedelta(seconds=1))


@TimeseriesSource.register
class MeasurementTimeSeries(OrderedDict):
	_key: CategoryItem
	_source: ObservationTimeSeries
	offset = 0
	log = pluginLog.getChild('MeasurementTimeSeries')
	__lastHash: int
	__references: Set[Hashable]
	__nullValue: Optional[TimeAwareValue]

	def __init__(
		self,
		source: Union[ObservationTimeSeries, 'Plugin'],
		key: Union[str, CategoryItem],
		minPeriod: Optional[timedelta] = None,
		maxPeriod: Optional[timedelta] = None
	):
		self.__minPeriod = minPeriod
		self.__maxPeriod = maxPeriod
		self.__lastHash = 0
		self.__references = set()
		self.__nullValue = None
		self._source = source
		self.key = key
		self.signals = TimeSeriesSignal(self)
		super(MeasurementTimeSeries, self).__init__()
		if self.isMultiSource:
			source: 'Plugin'
			source.publisher.connectChannel(self.key, self.sourceChanged)

	def __valuesHash(self) -> int:
		return hash(tuple(getattr(i, 'rawValue', i) for i in self.values()))

	@property
	def key(self) -> CategoryItem:
		return self._key

	@key.setter
	def key(self, key: CategoryItem | str):
		if isinstance(key, str):
			key = CategoryItem(key)
		self._key = key

	@property
	def lastHash(self) -> int:
		return self.__lastHash

	def __hash__(self):
		return hash((self._key, self.source, self.__minPeriod, self.__maxPeriod))

	@property
	def actualLength(self):
		if self.isMultiSource:
			return sum(len(s.__timeseries__ if isinstance(s, TimeseriesSource) else s) for s in self._source.observations if self.key in s)
		return len(self._source)

	def __repr__(self):
		return f'MeasurementTimeseries(key={self._key.name}, source={self.source!s}, length={len(self)}, actualLength={self.actualLength})'

	@property
	def name(self):
		if isinstance(self._source, ObservationTimeSeries):
			return f'{self._source.__class__.__name__}.{self._key.name}'
		else:
			return f'{self._source.name}.{self._key.name}'

	def __str__(self):
		return self.__repr__()

	def __len__(self):
		return len(self.keys())

	def sourceLen(self):
		pass

	def pullUpdate(self):
		self.update()

	def addReference(self, reference: Hashable):
		self.__references.add(reference)

	def refresh(self):
		self.__clearCache()
		if self.signals.hasConnections or len(self.__references) > 0:
			log.verbose(f'Refreshing {self!s}', verbosity=3)
			self.update()
		else:
			log.verbose(f'Aborting refresh for {self!s} due to lack of subscribers', verbosity=2)

	def sourceChanged(self, sources: Set['Observation']):
		# Ignore if none of the sources are timeseries
		if self.isMultiSource and all(isinstance(s, RealtimeSource) for s in sources):
			return
		elif not self.isMultiSource and self._source not in sources:
			return

		if self.signals.hasConnections or len(self.__references) > 0:
			lenBefore = len(self)
			self.__clearCache()
			with self.signals as signal:
				signal.publish(sources)
				self.update()
			self.log.debug(f'{repr(self)} refreshed: {lenBefore} -> {len(self)}')

	@property
	def hasTimeseries(self):
		if isinstance(self._source, ObservationTimeSeries):
			return True
		return any(
			item.hasTimeseries and item.hasValues
				for item in (e[self._key] for e in self._source.observations
				if self._key in e
				   and hasattr(e[self._key], 'hasTimeseries'))
		)

	def filter(self, obs: Observation) -> bool:
		minPeriod = self.__minPeriod or timedelta(days=-400)
		maxPeriod = self.__maxPeriod or timedelta(days=400)
		return minPeriod <= obs.period <= maxPeriod

	@property
	def sources(self):
		if self.isMultiSource:
			return [e[self._key] for e in self._source.observations if self._key in e and self.filter(e)]
		else:
			return [self._source]

	@property
	def source(self):
		return self._source

	@property
	def isMultiSource(self) -> bool:
		return not isinstance(self._source, ObservationTimeSeries)

	@property
	def hasValues(self):
		if self.isMultiSource:
			return any(e[self._key].hasValues for e in self._source.observations if self._key in e)
		else:
			return len(self._source) > 3 and self.key in self._source

	def update(self) -> None:
		# TODO: Add a lock to this operation
		currentLength = len(self)
		log.debug(f'{self} updating')
		self.clear()
		log.verbose(f'{self} cleared with length {len(self)}', verbosity=5)
		key = self._key
		if isinstance(self._source, ObservationTimeSeries):
			log.verbose(f'{self} updating from single source of length {len(self._source.timeseries)}', verbosity=4)
			itemCount = 0
			for item in (v[key] for v in self._source.timeseries.values() if key in v):
				itemCount += 1
				self[item.timestamp] = item
			log.verbose(
				f'{self} updated from single source with '
				f'{itemCount} expected items and a change of '
				f'{len(self) - currentLength} [{currentLength}'
				f' -> {len(self)}]',
				verbosity=5
			)
		else:
			values = self.__sourcePull()

			for item in values:
				self[item.timestamp] = item
			log.verbose(
				f'{self} updated from multiple sources with'
				f' {len(self) - currentLength} [{currentLength}'
				f' -> {len(self)}]',
				verbosity=5
			)
		# self.removeOldValues()

		thisHash = self.__valuesHash()
		if thisHash != self.__lastHash:
			log.verbose(f'{self} has changed, clearing cache and publishing changes', verbosity=3)
			self.__clearCache()
		else:
			log.verbose(f'{self} has not changed', verbosity=5)
		self.__lastHash = thisHash

	def __sourcePull(self) -> list[ObservationValue]:
		values: list[ObservationValue] = []
		sources: List[MeasurementTimeSeries, ObservationValue] = self.sources

		log.verbose(f'{self} refreshing sources', verbosity=3)
		for item in sources:
			if isinstance(item, MeasurementTimeSeries):
				item.addReference(self)
				item.refresh()
				log.verbose(f'{self} refreshed {item.source.dataName} source', verbosity=4)

		expectedLength = sum(len(s) for s in sources)
		for item in sources:
			log.verbose(f'Pulling from {item}', verbosity=3)
			if isinstance(item, MeasurementTimeSeries):
				values.extend(item)
				log.verbose(
					f'Collected {len(item)} item{"s" if len(item) > 1 else ""}'
					f'from {item.source.dataName}',
					verbosity=3
				)
			else:
				values.append(item)
				log.verbose(f'Collected value from {item.source.dataName}', verbosity=3)
		if len(values) == expectedLength:
			log.verbose(
				f'︎︎ ✔ {self} successfully collected {len(values)} from '
				f'source{"s" if self.sourceCount > 1 else ""} {self.sourcesString}',
				verbosity=3
			)
		else:
			log.verbose(
				f'︎︎ ✘ {self} pulled from source{"s" if self.sourceCount > 1 else ""} {self.sourcesString}, but failed. '
				f'Expected {expectedLength} items but collected only {len(values)}',
				verbosity=0
			)
		values.sort(key=lambda x: x.timestamp)
		return values

	@property
	def sourceCount(self) -> int:
		return len(self.sources)

	@property
	def sourcesString(self) -> str:
		if self.sources:
			names = [f'{i.source}.{i.source.dataName}' for i in self.sources]
		else:
			source = self.source
			if isinstance(source, MeasurementTimeSeries):
				names = [f'{source.source.dataName}']
			else:
				names = [f'{source.name}']
		return f'[{", ".join(names)}]'

	def roll(self):
		self.__clearCache()

	def removeOldValues(self):
		keysToPop = []
		for key in self.keys():
			if key < datetime.now(key.tzinfo):
				keysToPop.append(key)
		for key in keysToPop:
			self.pop(key)

	def __getitem__(self, key):
		if len(self) == 0:
			self.update()
		if isinstance(key, slice):
			hashArgs = HashSlice(key.start, key.stop, key.step)
			return self.__getSlice(hashArgs, self.__lastHash)
		if isinstance(key, (datetime, timedelta, Period)):
			if isinstance(key, timedelta):
				key = now() + key
			if isinstance(key, Period):
				key = key.value
			if key in self.keys():
				return super().__getitem__(key)
			if self.__withinExtendedRange(key):
				return self.__value(key, self._timeHashInvalidator, self.__lastHash)
		elif isinstance(key, int):
			return self.list[key]
		return super(MeasurementTimeSeries, self).__getitem__(key)

	@cached_property
	def _timeHashInvalidator(self) -> TimeHash:
		period = self.period
		match period:
			case Period() as p:
				period = int(p)
			case timedelta() as d:
				period = int(d.total_seconds())
			case _:
				period = int(period)
		period = min(abs(period), 300)
		return TimeHash(period)

	@lru_cache()
	def __now(self, timeHashInvalidator: TimeHash, valueHash: Optional[int] = 0) -> ObservationValue:
		key = closest(list(self.keys()), now())
		return super(MeasurementTimeSeries, self).__getitem__(key)

	@lru_cache()
	def __value(self, key, timeHashInvalidator: TimeHash, valueHash: Optional[int] = 0) -> ObservationValue:
		key = closest(list(self.keys()), key)
		return super(MeasurementTimeSeries, self).__getitem__(key)

	def __missing__(self, key):
		source = sorted(list(self._source.timeseriesKeys()), key=lambda x: x.timestamp or x.value)
		start = source[0].value
		if key < start and abs(key - start) >= self.period:
			key = start
		stop = source[-1].value
		if key > stop and abs(key - stop) >= self.period:
			key = stop
		if start <= key <= stop:
			if self.__nullValue is None:
				cls = self._source.itemClass.itemClass
				itemSource = self._source[key]
				self.__nullValue = cls(value=None, key=self._key, source=itemSource, metadata=self.first.metadata)
			return self.__nullValue
		else:
			raise KeyError(key)

	def __withinExtendedRange(self, key, extend: timedelta = None):
		period = extend or self.period
		match period:
			case wu.Time():
				period = timedelta(period.second)
			case Period():
				period = timedelta(period.value.second)
			case int() | float():
				period = timedelta(period)
			case _:
				pass
		if isinstance(period, Period):
			period = period.value
		start = self.first.timestamp - period
		stop = self.last.timestamp + period
		return start <= key <= stop

	def __contains__(self, key):
		if isinstance(key, datetime):
			return super(MeasurementTimeSeries, self).__contains__(key) or self.first.timestamp <= key <= self.last.timestamp
		return super().__contains__(key)

	def __convertKey(self, key) -> DateKey:
		if isinstance(key, int):
			key = datetime.now().astimezone(_timezones.utc) + timedelta(seconds=key*self.period.total_seconds())
		if isinstance(key, (datetime, timedelta)):
			key = DateKey(key)
		return key

	@lru_cache(maxsize=64)
	def __getSlice(self, key, lastHash: int = 0):
		if any(isinstance(item, datetime) for item in key):
			start = key.start or self.first.timestamp
			stop = key.stop or self.last.timestamp
			start, stop = sorted((start, stop))
			if start.tzinfo is None:
				start = start.replace(tzinfo=LOCAL_TIMEZONE)
			if stop.tzinfo is None:
				stop = stop.replace(tzinfo=LOCAL_TIMEZONE)
			return [k for k in self if start <= k.timestamp <= stop]

	def __delitem__(self, key):
		key = self.__convertKey(key)
		if key in self:
			super(MeasurementTimeSeries, self).__delitem__(key)
			self.__clearCache()

	def __iter__(self):
		return iter(self.list)

	def __clearCache(self):
		if len(self) != 0:
			log.verbose(f'Clearing cache for {self}', verbosity=3)
		clearCacheAttr(self, 'array', 'period', 'periodAverage', '_timeHashInvalidator', 'timeseries', 'timeseriesInts', 'start', 'list')

	def updateItem(self, value):
		key = DateKey(value.timestamp)
		self[key] = value

	@cached_property
	def period(self):
		if self.isMultiSource:
			return max(self._source.observations.timeseries, key=lambda x: len(x)).period
		return self._source.period

	@cached_property
	def periodAverage(self):
		if self.isMultiSource:
			timeSeriesSources = [ts for ts in self.sources if isinstance(ts, MeasurementTimeSeries)]
			return timedelta(seconds=sum(i.period.total_seconds() for i in timeSeriesSources)/len(timeSeriesSources))
		return self._source.period

	@cached_property
	def start(self):
		return self.list[0].timestamp

	@cached_property
	def array(self) -> np.array:
		return np.array([i.value for i in self.list])

	@cached_property
	def list(self):
		if len(self) == 0:
			self.update()
		l = list(self.values())
		return sorted(l, key=lambda x: x.timestamp)

	@cached_property
	def timeseries(self) -> np.array:
		return [i.timestamp for i in self.list]

	@cached_property
	def timeseriesInts(self) -> np.array:
		return np.array([x.timestamp.timestamp() for x in self.list])

	@property
	def last(self):
		return self.list[-1]

	@property
	def first(self):
		return self.list[0]


class Container:
	__containers__ = {}

	_awaitingRequirements: Dict[Hashable, Tuple[Callable[[Set['Observation']], bool], Callable]]

	source: 'Plugin'
	key: CategoryItem
	now: ObservationValue
	minutely: Optional[MeasurementTimeSeries]
	hourly: Optional[MeasurementTimeSeries]
	daily: Optional[MeasurementTimeSeries]
	forecast: Optional[MeasurementTimeSeries]
	historical: Optional[MeasurementTimeSeries]
	timeseriesOnly: bool

	title: str
	__hash_key__: CategoryItem
	log = log.getChild(__name__)

	@classmethod
	def __buildKey(cls, source: 'Plugin', key: CategoryItem) -> CategoryItem:
		return CategoryItem(key, source=[source.name])

	def __new__(cls, source: 'Plugin', key: CategoryItem):
		containerKey = cls.__buildKey(source, key)
		if containerKey not in cls.__containers__:
			cls.__containers__[containerKey] = super(Container, cls).__new__(cls)
		return cls.__containers__[containerKey]

	def __init__(self, source: 'Plugin', key: CategoryItem):
		self.__hash_key__ = Container.__buildKey(source, key)
		self.source = source
		self.key = key
		self.__channel = self.source.publisher.connectChannel(self.key, self.__sourceUpdated)
		self._awaitingRequirements = dict()

	@property
	def channel(self) -> 'ChannelSignal':
		if self.__channel is False:
			try:
				self.source.publisher.connectChannel(self.key, self.__sourceUpdated)
			except Exception as e:
				raise Exception(f'Failed to connect channel for {self.key}') from e
		return self.__channel

	@Slot()
	def __sourceUpdated(self, sources):
		if any(not isinstance(source, RealtimeSource) for source in sources):
			self.__clearCache()
		if self._awaitingRequirements:
			for requester, (requirement, callback) in self._awaitingRequirements.items():
				if requirement(sources):
					if iscoroutine(callback):
						loop.create_task(callback(), name=f'P{requester}RequirementsMet')
					else:
						loop.call_soon(callback)
					del self._awaitingRequirements[requester]

	@lru_cache(maxsize=8)
	def getFromTime(self, time: timedelta | datetime, timehash: TimeHash = TimeHash.Minutely) -> Optional[Observation]:
		if isinstance(time, timedelta):
			time = Now() + time
		return self.timeseriesAll[time]

	def __repr__(self):
		return f'Container({self.source.name}:{self.key[-1]} {self.value})'

	def __rich_repr__(self):
		yield 'key', self.key.name
		yield 'source', self.source.name
		yield 'value', (value := self.value)
		yield 'timestamp', f'{value.timestamp:%m-%d %H:%M:%S}'
		yield 'isRealtime', self.isRealtime
		yield 'isForecast', self.isForecast
		yield 'isTimeseries', self.isTimeseries
		yield 'isDaily', self.isDaily

	def __str__(self):
		return f'{self.value!s}'

	def __hash__(self):
		return hash(self.__hash_key__)

	def toDict(self):
		return {'key': self.key, 'value': self.value}

	def __eq__(self, other):
		return hash(self) == hash(other)

	def __clearCache(self):
		clearCacheAttr(self, 'nowFromTimeseries', 'hourly', 'daily')

	@property
	def title(self):
		if hasattr(self.value, 'title'):
			return self.value.title
		return str(self.key).title()

	@property
	def value(self) -> ObservationValue:
		if self.now is not None:
			return self.now
		elif self.hourly is not None:
			return self.hourly[Now()]
		elif self.daily is not None:
			return self.daily[Now()]
		elif self.timeseries is not None:
			return self.timeseries[Now()]
		return None

	@property
	def now(self) -> Optional[Observation]:
		if self.isRealtime:
			return self.source.realtime[self.key]
		elif self.metadata.get('isTimeseriesOnly', False) or not self.isRealtime:
			return self.nowFromTimeseries
		return None

	realtime = now

	@property
	def nowFromTimeseries(self):
		if self.hourly is not None:
			return self.hourly[now()]
		elif self.daily is not None:
			return self.daily[now()]
		return self.timeseriesAll[now()]

	@cached_property
	def hourly(self) -> Optional[MeasurementTimeSeries]:
		if self.source.hourly and self.key in self.source.hourly:
			return self.source.hourly[self.key]
		return None

	@cached_property
	def daily(self) -> Optional[MeasurementTimeSeries]:
		if self.source.daily and self.key in self.source.daily:
			return self.source.daily[self.key]
		return None

	@cached_property
	def timeseries(self) -> MeasurementTimeSeries:
		return MeasurementTimeSeries(self.source, self.key, minPeriod=timedelta(hours=-3), maxPeriod=timedelta(hours=3))

	@cached_property
	def timeseriesAll(self) -> MeasurementTimeSeries:
		return MeasurementTimeSeries(self.source, self.key)

	def customTimeFrame(self, timeframe: timedelta, sensitivity: timedelta = timedelta(minutes=1)) -> Optional[MeasurementTimeSeries | ObservationValue]:
		try:
			return self.source.get(self.key, timeframe)
		except KeyError:
			return None

	@property
	def metadata(self) -> 'UnitMetadata':
		return self.source.schema.getExact(self.key)

	@property
	def isRealtime(self) -> bool:
		return any(isinstance(obs, RealtimeSource) for obs in self.source.observations if self.key in obs)

	@property
	def isRealtimeApproximate(self) -> bool:
		return (
			not self.isRealtime
			and self.isTimeseriesOnly
			and any(obs.period < REALTIME_THRESHOLD
			for obs in self.source.observations
			if self.key in obs)
			or self.isDailyOnly
		)

	@property
	def isTimeseries(self) -> bool:
		return any(isinstance(obs, TimeseriesSource)
			for obs in self.source.observations
			if self.key in obs
			   and len(obs) > 3
			   and obs.period < timedelta(hours=6)
		)

	@property
	def isForecast(self) -> bool:
		for obs in self.source.observations:
			if self.key in obs and isinstance(obs, TimeseriesSource):
				if len(obs.__timeseries__) > 3:
					if obs.period < timedelta(hours=6):
						return True
		return False

	@property
	def isDaily(self) -> bool:
		return any(abs(obs.period) >= timedelta(days=1) for obs in self.source.observations if self.key in obs)

	@property
	def isDailyForecast(self) -> bool:
		return any(obs.period >= timedelta(days=1) for obs in self.source.observations if self.key in obs)

	@property
	def isTimeseriesOnly(self) -> bool:
		return self.metadata.get('isTimeseriesOnly', False) or not self.isRealtime

	@property
	def isDailyOnly(self) -> bool:
		return all(obs.period >= timedelta(days=1) for obs in self.source.observations if self.key in obs)

	def notifyOnRequirementsMet(self, requester: Hashable, requirements: Callable[[Set['Observation']], bool], callback: Coroutine):
		self._awaitingReuqirements[requester] = (requirements, callback)
