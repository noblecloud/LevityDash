from asyncio import get_event_loop, TimerHandle, create_task, get_running_loop, iscoroutinefunction
from random import random as randomFloat
from abc import abstractmethod
from asyncio import iscoroutine, coroutine
from collections import defaultdict
from datetime import datetime, timedelta
from functools import partial
from typing import Any, Callable, Dict, Hashable, Mapping, Optional, Type, Union, Set, ClassVar, TYPE_CHECKING, Coroutine

import WeatherUnits as wu
from PySide2.QtCore import QObject, Signal, Slot
from pytz import timezone

from LevityDash.lib.utils import abbreviatedIterable, SmartString, Now, KeyData, Mutable, now
from LevityDash.lib.log import LevityPluginLog as log

if TYPE_CHECKING:
	from LevityDash.lib.plugins.categories import CategoryItem
	from LevityDash.lib.plugins.observation import Observation
	from LevityDash.lib.plugins import Plugin

unitDict: Dict[str, Union[Type[wu.Measurement], Type[bool], Dict[str, Union[Type[wu.Measurement], Type[wu.DerivedMeasurement]]]]] = {
	'f':                wu.temperature.Fahrenheit,
	'c':                wu.temperature.Celsius,
	'kelvin':           wu.temperature.Kelvin,
	'%':                wu.others.Humidity,
	'%h':               wu.others.Humidity,
	'%c':               wu.others.Coverage,
	'%p':               wu.others.Probability,
	'%%':               wu.others.Percentage,
	'%bat':             wu.others.BatteryPercentage,
	'º':                wu.others.Direction,
	'ºa':               wu.others.Angle,
	'str':              SmartString,
	'int':              wu.Measurement,
	'mmHg':             wu.pressure.MillimeterOfMercury,
	'inHg':             wu.pressure.InchOfMercury,
	'W/m^2':            wu.others.light.Irradiance,
	'lux':              wu.others.light.Illuminance,
	'mb':               wu.Pressure.Millibar,
	'mbar':             wu.Pressure.Millibar,
	'bar':              wu.Pressure.Bar,
	'hPa':              wu.Pressure.Hectopascal,
	'in':               wu.length.Inch,
	'mi':               wu.length.Mile,
	'mm':               wu.length.Millimeter,
	'm':                wu.length.Meter,
	'km':               wu.length.Kilometer,
	'month':            wu.Time.Month,
	'week':             wu.Time.Week,
	'day':              wu.Time.Day,
	'hr':               wu.Time.Hour,
	'min':              wu.Time.Minute,
	's':                wu.Time.Second,
	'ug':               wu.mass.Microgram,
	'μg':               wu.mass.Microgram,
	'mg':               wu.mass.Milligram,
	'g':                wu.mass.Gram,
	'kg':               wu.mass.Kilogram,
	'lb':               wu.mass.Pound,
	# 'm³':              wu.Volume.CubicMeter,
	# 'ft³':             wu.Volume.CubicFoot,
	'volts':            wu.Voltage,
	'date':             datetime,
	'uvi':              wu.others.light.UVI,
	'strike':           wu.others.LightningStrike,
	'timezone':         timezone,
	'datetime':         datetime,
	'epoch':            datetime.fromtimestamp,
	'rssi':             wu.Digital.RSSI,
	'ppt':              wu.derived.PartsPer.Thousand,
	'ppm':              wu.derived.PartsPer.Million,
	'ppb':              wu.derived.PartsPer.Billion,
	'pptr':             wu.derived.PartsPer.Trillion,
	'bool':             bool,
	'PI':               wu.AirQuality.PollutionIndex,
	'PrimaryPollutant': wu.AirQuality.PrimaryPollutant,
	'AQI':              wu.AirQuality.AQI,
	'AQIHC':            wu.AirQuality.HeathConcern,
	'MoonPhase':        wu.Measurement,
	"WeatherCode":      wu.Measurement,
	'tz':               timezone,
	'special':          {
		'precipitation':       wu.Precipitation,
		'precipitationDaily':  wu.Precipitation.Daily,
		'precipitationHourly': wu.Precipitation.Hourly,
		'precipitationRate':   wu.Precipitation.Hourly,
		'wind':                wu.derived.Wind,
		'airDensity':          wu.derived.Density,
		'pollutionDensity':    wu.derived.Density,
		'precipitationType':   wu.Precipitation.Type,
		'pressureTrend':       SmartString
	}
}


class SchemaProperty:
	def __init__(self, source: 'ObservationDict', data: dict):
		self.source = source
		self.data = data

	def get(self, source: 'ObservationDict' = None):
		data = self.data
		source = source or self.source
		allowZero = data.get('allowZero', True)
		value = self.fromKey(source) or self.fromAttr(source) or self.default
		if not allowZero:
			return value or 1
		return value

	@property
	def default(self) -> Optional[Any]:
		if self.data.get('default', None) is None:
			return None
		data = self.data
		source = self.source
		unitCls = data.get('unit', None)
		unitCls = data.get(unitCls, None) or data.get('dataType', None)
		if unitCls is not None:
			value = data['default']['value']
			if not isinstance(value, unitCls):
				value = unitCls(value)
		else:
			value = data['default']
			if isinstance(value, dict):
				cls = value.get('dataType', None) or unitDict.get(value.get('unit', None), value.get('unit', None))
				if cls is not None:
					return cls(value['value'])
				value = value['value']

		return value

	def fromKey(self, source: Union[Mapping, 'Plugin'] = None) -> Optional[Any]:
		source = source or self.source
		if 'key' in self.data and self.data['key'] in source:
			return source[self.data['key']]
		return None

	def fromAttr(self, source: Union[Mapping, 'Plugin']) -> Optional[Any]:
		source = source or self.source
		if 'attr' in self.data and hasattr(source, self.data['attr']):
			return getattr(source, self.data['attr'])
		return None

	def __delete__(self, instance):
		pass

	def __call__(self, source: Union[Mapping, 'Plugin'], *args, **kwargs):
		return self.get(source=source, *args, **kwargs)


class MutableSignal(QObject):
	_signal = Signal(object)
	_pending: Set[Hashable]
	_muteLevel: int

	def __init__(self, *args, **kwargs):
		self.__muteLevel = 0
		self._pending = set()
		super().__init__(*args, **kwargs)

	def __enter__(self):
		self.muted = True
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.muted = False

	def setMute(self, value: bool):
		self.muted = value

	@property
	def _muteLevel(self):
		return self.__muteLevel

	@_muteLevel.setter
	def _muteLevel(self, value):
		self.__muteLevel = max(value, 0)

	@property
	def muted(self) -> bool:
		return bool(self._muteLevel)

	@muted.setter
	def muted(self, value):
		self._muteLevel += 1 if value else -1
		self.blockSignals(bool(self._muteLevel))
		if not self._muteLevel and self._pending:
			self._emit()

	@abstractmethod
	def publish(self, *args): ...

	@abstractmethod
	def _emit(self): ...


class ChannelSignal(MutableSignal):
	"""
	Emits all observations that have changed in a Plugin specific to a channel.
	"""

	_connections: dict[Hashable: Callable]
	_signal = Signal(object)
	_source: 'Plugin'
	_key: 'CategoryItem'
	_singleShots: Dict[Hashable, Coroutine]
	_conditionalSingleShots: Dict[Coroutine, Callable[['Container'], bool]]

	def __init__(self, source: 'Plugin', key: 'CategoryItem'):
		self._connections = {}
		self._key = key
		self._source = source
		self._singleShots = {}
		self._conditionalSingleShots = {}
		super(ChannelSignal, self).__init__()

	def __repr__(self):
		return f'Signal for {self._source.name}:{self._key}'

	def connectSlot(self, slot: Callable) -> bool:
		self._connections.update({slot.__self__: slot})
		return self._signal.connect(slot)

	def publish(self, observations: Set['Observation']):
		if isinstance(observations, set):
			self._pending.update(observations)
		else:
			self._pending.add(observations)
		if not self.muted and self._pending:
			self._emit()

	def _emit(self):
		self._signal.emit(self._pending)
		self._pending.clear()

	def disconnectSlot(self, slot):
		try:
			self._connections.pop(slot.__self__)
			return self._signal.disconnect(slot)
		except RuntimeError:
			pass
		except KeyError:
			pass
		return False

	@property
	def hasConnections(self) -> bool:
		return len(self._connections) > 0

	@property
	def key(self):
		return self._key

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
		self._conditionalSingleShots[callback] = condition


class Accumulator(MutableSignal):
	__signal = Signal(set)
	__connections: Dict['CategoryItem', ChannelSignal]
	_data: set

	def __init__(self, observation: 'ObservationDict'):
		self.__hash = hash((observation, hash(id)))
		self._pendingSilent = set()
		self.__observation = observation
		self.__connections = {}
		super(Accumulator, self).__init__()

	def __hash__(self):
		return self.__hash

	def __repr__(self):
		return f'Accumulator for {self.__observation}'

	def publish(self, *keys: 'CategoryItem'):
		self._pending.update(keys)
		if not self.muted:
			self._emit()

	def publishSilently(self, *keys: 'CategoryItem'):
		self._pendingSilent.update(keys)

	def publishKey(self, key: 'CategoryItem'):
		self._pending.add(key)
		if not self.muted:
			self._emit()

	def _emit(self):
		if not self._pending and not self._pendingSilent:
			return
		if self._pending:
			log.debug(f'{self.__observation.__class__.__name__} announcing ({len(self._pending)}) changed values: {abbreviatedIterable([key.name for key in self._pending])}')
		self.__signal.emit(KeyData(self.__observation, {*self._pending, *self._pendingSilent}))
		self._pending.clear()

	def connectSlot(self, slot: Callable):
		self.__signal.connect(slot)

	def disconnectSlot(self, slot: Callable):
		try:
			self.__signal.disconnect(slot)
		except RuntimeError:
			pass

	def connectChannel(self, channel: 'CategoryItem', slot: Slot):
		signal = slot.__self__.get(channel, self.__addChannel(channel))
		signal.connectSlot(slot)

	def __addChannel(self, channel: 'CategoryItem'):
		self.__signals[channel] = ChannelSignal(self.source, channel)
		return self.__signals[channel]


class Publisher(MutableSignal):
	"""
	Publishes changes within a plugin to the global publisher.
	"""

	__added = Signal(dict)
	__changed = Signal(dict)
	_pending: dict['Observation', Set['CategoryItem']]
	__channels: dict['CategoryItem', ChannelSignal]

	def __init__(self, source: 'Plugin'):
		super(Publisher, self).__init__()
		self.source = source
		self._pending = defaultdict(set)
		self.__channels = {}

	@Slot(KeyData)
	def publish(self, data: KeyData):
		sender = data.sender
		keys = data.keys
		self._pending[sender].update(keys)
		if not self.muted:
			self._emit()

	def remove(self, key: 'CategoryItem'):
		if key in self.keys:
			self.removed.emit(self.keys[key])
			del self.keys[key]

	def _emit(self):
		data = KeyData(self.source, self._pending)
		if len(self.__channels):
			keys = set([i for j in [d for d in data.keys.values()] for i in j])

			# relay changed observations to channels
			for s in (signal for key, signal in self.__channels.items() if key in keys):
				s.publish(set(source for source, sourceKeys in self._pending.items() if s.key in sourceKeys))

		self.__added.emit(data)
		self._pending.clear()

	def connectSlot(self, slot: Callable) -> bool:
		try:
			return self.__added.connect(slot)
		except RuntimeError:
			return False

	def disconnectSlot(self, slot: Slot) -> bool:
		try:
			return self.__added.disconnect(slot)
		except TypeError:
			return False

	def connectChannel(self, channel: 'CategoryItem', slot: Slot | Callable) -> bool | ChannelSignal:
		channel = self.__channels.get(channel, None) or self.__addChannel(channel)
		return channel if channel.connectSlot(slot) else False

	def disconnectChannel(self, channel: 'CategoryItem', slot: Slot | Callable) -> bool:
		channel = self.__channels.get(channel, None)
		if channel:
			return channel.disconnectSlot(slot)
		return True

	def __addChannel(self, channel: 'CategoryItem') -> ChannelSignal:
		self.__channels[channel] = ChannelSignal(self.source, channel)
		return self.__channels[channel]


class ScheduledEvent(object):
	instances: ClassVar[dict['Plugin', ['ScheduledEvent']]] = {}

	stagger: bool
	staggerAmount: timedelta
	when: datetime
	interval: timedelta
	func: Callable
	args: tuple
	kwargs: dict
	timer: TimerHandle
	log = log.getChild('ScheduledEvent')

	def __init__(self,
		interval: timedelta | int | float | Now,
		func: Callable,
		arguments: tuple = None,
		keywordArguments: dict = None,
		stagger: bool = None,
		staggerAmount: timedelta = None,
		fireImmediately: bool = True,
		singleShot: bool = False,
		pool=None
	):
		if arguments is None:
			arguments = ()
		if keywordArguments is None:
			keywordArguments = {}
		if stagger is None:
			stagger = False
		if staggerAmount is None:
			if isinstance(interval, Now):
				interval_float = 0.0
			elif isinstance(interval, timedelta):
				interval_float = interval.total_seconds()
			else:
				interval_float = interval
			staggerAmount = timedelta(min(interval_float*0.1, 5*3600))
		self.__interval = interval

		self.__owner = func.__self__
		if self.__owner in self.instances:
			self.instances[self.__owner].append(self)
		else:
			self.instances[self.__owner] = [self]
		self.__func = func
		self.__args = arguments
		self.__kwargs = keywordArguments
		self.__stagger = stagger
		self.__staggerAmount = staggerAmount
		self.__singleShot = singleShot
		self.__fireImmediately = fireImmediately

	def schedule(self, *, startTime: datetime | timedelta = None, immediately: bool = False) -> 'ScheduledEvent':
		self.__fireImmediately = immediately
		if self.__singleShot:
			name = getattr(self.__owner, 'name', self.__owner.__class__.__name__)
			self.log.debug(f'{name} - Scheduled single shot event: {self.__func.__name__}')
		else:
			interval = wu.Time.Second(self.__interval.total_seconds())
			stagger = wu.Time.Second(abs(self.__staggerAmount.total_seconds()))
			self.log.debug(f'{self.__owner.name} - Scheduled recurring event: {self.__func.__name__} every {interval} ±{stagger}')

		self.__run(startTime)
		return self

	def retry(self, after: timedelta | datetime = None) -> 'ScheduledEvent':
		if after is None:
			after = self.__interval
		if isinstance(after, timedelta):
			after = now() + after
		self.__run(after)
		return self

	def start(self) -> 'ScheduledEvent':
		self.schedule(immediately=True)
		return self

	def delayedStart(self, delay: timedelta) -> 'ScheduledEvent':
		self.schedule(startTime=datetime.now() + delay)
		return self

	def __del__(self):
		self.instances[self.__owner].remove(self)

	def stop(self):
		self.timer.cancel()

	def reschedule(self, interval: timedelta = None, fireImmediately: bool = False) -> 'ScheduledEvent':
		self.__fireImmediately = fireImmediately
		if interval is not None:
			self.interval = interval
		self.__run()
		return self

	@property
	def running(self) -> bool:
		return self.timer is not None and not self.timer.cancelled()

	@property
	def when(self) -> datetime | timedelta:
		if self.__singleShot and self.__interval is Now():
			return timedelta()
		when = self.__interval.total_seconds()
		if self.__stagger:
			seconds = self.__staggerAmount.seconds*(randomFloat()*2 - 1)
			loopTime = get_event_loop().time()
			if seconds + loopTime < 0:
				seconds = self.__staggerAmount.seconds*randomFloat()
			when += seconds
			when = timedelta(seconds=when)
		return when

	@when.setter
	def when(self, value: datetime):
		pass

	@property
	def interval(self):
		return self.__interval

	@interval.setter
	def interval(self, value):
		if value != self.__interval:
			self.__interval = value
			self.timer.cancel()
			self.__run()
		self.__interval = value

	@property
	def fireImmediately(self) -> bool:
		value = self.__fireImmediately
		self.__fireImmediately = False
		return value

	def __errorCatcher(self):
		try:
			self.__func(*self.__args, **self.__kwargs)
		except Exception as e:
			self.log.exception(e)

	def __run(self, startTime: datetime = None):
		loop = get_event_loop()
		when = self.when if startTime is None else startTime
		if isinstance(when, datetime):
			when = abs(datetime.now() - when)
		if isinstance(when, timedelta):
			when = when.total_seconds()
		if (timer := getattr(self, 'timer', None)) is not None:
			timer.cancel()
		self.timer = loop.call_soon(self.__fire) if self.fireImmediately else loop.call_later(when, self.__fire)

	# print(f'Scheduled {self.__func.__name__} to run at {when.strftime("%-I:%M:%S%p").lower()}')

	def __fire(self):
		if iscoroutine(self.__func) or iscoroutinefunction(self.__func):
			create_task(self.__func(*self.__args, **self.__kwargs))
		else:
			loop = get_running_loop()
			func = partial(self.__func, *self.__args, **self.__kwargs)
			loop.call_soon(func)
		name = getattr(self.__owner, 'name', self.__owner.__class__.__name__)
		self.log.verbose(f'{self.__func.__name__}() fired for {name}', verbosity=0)
		if not self.__singleShot:
			self.__run()

	@property
	def __timeTo(self) -> float:
		return self.timer.when()

	@classmethod
	def cancelAll(cls, owner=None):
		if owner is None:
			for owner in cls.instances:
				for event in cls.instances[owner]:
					event.stop()
		else:
			for event in cls.instances[owner]:
				event.stop()


__all__ = ['unitDict', 'Accumulator', 'ChannelSignal', 'SchemaProperty', 'MutableSignal', 'ScheduledEvent',
	'Publisher']
