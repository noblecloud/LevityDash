import asyncio
import random
from abc import abstractmethod
from datetime import datetime, timedelta
from functools import cached_property, lru_cache
from operator import attrgetter

import WeatherUnits
from PySide2.QtCore import QObject, QTimer, Signal, Slot
from typing import Callable, Iterable, Optional, Type, Union, ClassVar

from LevityDash.lib.config import pluginConfig, PluginConfig
from LevityDash.lib.plugins.categories import CategoryDict, CategoryItem
from LevityDash.lib.plugins.observation import (ArchivedObservationValue, MeasurementTimeSeries, Observation, ObservationDict,
                                                ObservationLog, ObservationRealtime, ObservationTimeSeries, ObservationValue,
                                                PublishedDict, RecordedObservationValue)
from LevityDash.lib.plugins.schema import Schema
from LevityDash.lib.plugins.utils import ChannelSignal
from LevityDash.lib.utils.data import KeyData
from LevityDash.lib.log import LevityPluginLog as pluginLog
from LevityDash.lib.utils.shared import clearCacheAttr, closest, Now, Period


class ObservationList(list):
	source: 'Plugin'

	def __init__(self, source, *args, **kwargs):
		self.source = source
		super(ObservationList, self).__init__(*args, **kwargs)

	def insert(self, value: ObservationDict):
		if not isinstance(value, ObservationDict):
			raise ValueError(f"Can not add this type: {type(value)}")
		self.append(value)

	def append(self, value):
		super(ObservationList, self).append(value)
		self.sort()

	def extend(self, value: Iterable):
		super(ObservationList, self).extend(value)
		self.sort()

	def __add__(self, other):
		super(ObservationList, self).__add__(other)
		self.sort()

	def __iadd__(self, other):
		super(ObservationList, self).__iadd__(other)
		self.sort()

	def sort(self, key: object = None, reverse: object = False) -> None:
		# self.grab.cache_clear()
		super(ObservationList, self).sort(key=attrgetter('sortKey'))

	def __hash__(self):
		return hash(self.source.name)

	@lru_cache(maxsize=12)
	def grab(self, value: timedelta, sensitivity: timedelta = timedelta(minutes=5), forecastOnly: bool = False) -> Optional[ObservationDict]:
		if isinstance(value, int):
			value = timedelta(seconds=value)
		if isinstance(value, Period):
			value = value.value

		if isinstance(sensitivity, int):
			sensitivity = timedelta(seconds=sensitivity)
		if isinstance(sensitivity, Period):
			sensitivity = sensitivity.value

		selection = [obs for obs in self if isinstance(obs, ObservationTimeSeries)] if forecastOnly else self
		if selection:
			grabbed = selection[min(range(len(selection)), key=lambda i: abs(selection[i].period - value))]

			low = value - sensitivity
			high = value + sensitivity
			if low < grabbed.period < high:
				return grabbed
			else:
				return None
		else:
			return None

	def selectBest(self, minTimeframe: timedelta,
		minPeriod: timedelta = timedelta(minutes=1),
		maxPeriod: timedelta = timedelta(hours=4)) -> Optional[ObservationTimeSeries]:
		selection = [obs for obs in self if minPeriod <= obs.period <= maxPeriod and obs.timeframe > minTimeframe]
		if selection:
			return selection[min(range(len(selection)), key=lambda i: selection[i].period)]
		return None

	@cached_property
	def hourly(self) -> Optional[ObservationTimeSeries]:
		try:
			return self.grab(Period.Hour, sensitivity=Period.QuarterHour, forecastOnly=True)
		except IndexError:
			return None

	@cached_property
	def realtime(self) -> Optional[ObservationRealtime]:
		for observation in self:
			if isinstance(observation, ObservationRealtime):
				return observation
		else:
			return None

	@cached_property
	def daily(self) -> Optional[ObservationTimeSeries]:
		try:
			return self.grab(Period.Day, sensitivity=Period.Hour, forecastOnly=True)
		except IndexError:
			return None

	@cached_property
	def log(self) -> Optional[ObservationLog]:
		try:
			return self[0]
		except AttributeError:
			return None

	@property
	def forecasts(self) -> Iterable[ObservationTimeSeries]:
		return [obs for obs in self if isinstance(obs, ObservationTimeSeries) and obs.period.total_seconds() > 0]


class Container:
	__containers__ = {}

	source: 'Plugin'
	key: CategoryItem
	now: ObservationValue
	minutely: Optional[MeasurementTimeSeries]
	hourly: Optional[MeasurementTimeSeries]
	daily: Optional[MeasurementTimeSeries]
	forecast: Optional[MeasurementTimeSeries]
	historical: Optional[MeasurementTimeSeries]
	forecastOnly: bool

	title: str
	__hash_key__: CategoryItem
	log = pluginLog.getChild(__name__)

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
		self.source.publisher.connectChannel(self.key, self.__clearCache)

	def __getattr__(self, item):
		if item.startswith('__') or item in super(Container, self).__getattribute__('__annotations__') or item == '__annotations__':
			return super(Container, self).__getattribute__(item)
		return getattr(super(Container, self).__getattribute__('value'), item)

	def __setattr__(self, key, value):
		if key in self.__annotations__:
			super(Container, self).__setattr__(key, value)
		else:
			self.value.__setattr__(key, value)

	@lru_cache(maxsize=8)
	def getFromTime(self, time: timedelta | datetime) -> Optional[Observation]:
		if isinstance(time, timedelta):
			time = Now() + time
		return self.forecast[time]

	def __repr__(self):
		return f'{self.source.name}({self.key[-1]}: {self.value})'

	def __str__(self):
		return str(self.value)

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
	def value(self):
		if self.now is not None:
			return self.now
		elif self.hourly is not None:
			return self.hourly[Now()]
		elif self.daily is not None:
			return self.daily[Now()]
		return None

	@property
	def now(self):
		if self.sourceHasRealtime and self.source.realtime and self.key in self.source.realtime:
			return self.source.realtime[self.key]
		elif self.metadata.get('forecastOnly', False) or not self.sourceHasRealtime:
			return self.nowFromTimeseries
		return None

	@cached_property
	def nowFromTimeseries(self):
		return self.forecast[Now()]

	@cached_property
	def hourly(self):
		if self.source.hourly and self.key in self.source.hourly:
			return self.source.hourly[self.key]
		return None

	@cached_property
	def daily(self):
		if self.source.daily and self.key in self.source.daily:
			return self.source.daily[self.key]
		return None

	@cached_property
	def forecast(self):
		return MeasurementTimeSeries(self.source, self.key)

	def customTimeFrame(self, timeframe: timedelta, sensitivity: timedelta = timedelta(minutes=1)) -> Optional[MeasurementTimeSeries | ObservationValue]:
		try:
			return self.source.get(self.key, timeframe)
		except KeyError:
			return None

	@property
	def metadata(self):
		return self.source.schema.getExact(self.key)

	@property
	def sourceHasRealtime(self):
		return hasattr(self.source, 'realtime')

	@property
	def forecastOnly(self) -> bool:
		return self.metadata.get('forecastOnly', False) or not self.sourceHasRealtime


class Publisher(QObject):
	__added = Signal(dict)
	__changed = Signal(dict)
	__data: dict['Plugin', set[CategoryItem]]
	__signals: dict[CategoryItem, ChannelSignal]

	def __init__(self, source: 'Plugin'):
		self.source = source
		self.__data = {}
		self.__signals = {}
		super(Publisher, self).__init__()
		self.__timer = QTimer(singleShot=True, interval=200)
		self.__timer.timeout.connect(self.__emitChange)

	@Slot(KeyData)
	def addBulk(self, data: KeyData):
		sender = data.sender
		keys = data.keys
		if sender not in self.__data:
			self.__data[sender] = set()
		self.__data[sender].update(keys)
		if sum(len(d) for d in self.__data.values()) < 10:
			self.__timer.stop()
			self.__emitChange()
		else:
			self.__timer.start()

	def remove(self, key: CategoryItem):
		if key in self.keys:
			self.removed.emit(self.keys[key])
			del self.keys[key]

	def __emitChange(self):
		data = KeyData(self.source, self.__data)
		if len(self.__signals):
			keys = set([i for j in [d for d in data.keys.values()] for i in j])
			True
			for s in (signal for key, signal in self.__signals.items() if key in keys):
				sources = tuple([d for d in data.keys if s.key in d])
				s.publish(sources)
		self.__added.emit(data)
		self.__data = {}

	def connectSlot(self, slot: Slot):
		self.__added.connect(slot)

	def disconnectSlot(self, slot: Slot):
		try:
			self.__added.disconnect(slot)
		except TypeError:
			pass

	def connectChannel(self, channel: CategoryItem, slot: Slot):
		signal = self.__signals.get(channel, None) or self.__addChannel(channel)
		signal.connectSlot(slot)

	def disconnectChannel(self, channel: CategoryItem, slot: Slot):
		signal = self.__signals.get(channel, None)
		if signal:
			signal.disconnectSlot(slot)

	def __addChannel(self, channel: CategoryItem):
		self.__signals[channel] = ChannelSignal(self.source, channel)
		return self.__signals[channel]


class ScheduledEvent(object):
	instances: ClassVar[dict['Plugin', ['ScheduledEvent']]] = {}

	stagger: bool
	staggerAmount: timedelta
	when: datetime
	interval: timedelta
	func: Callable
	args: tuple
	kwargs: dict
	timer: asyncio.TimerHandle
	log = pluginLog.getChild('ScheduledEvent')

	def __init__(self,
		interval: timedelta,
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
			staggerAmount = timedelta(minutes=2.5)
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

	def start(self, immediately: bool = False, startTime: datetime = None):
		self.__fireImmediately = immediately
		if self.__singleShot:
			self.log.debug(f'{self.__owner.name} - Scheduled single shot event: {self.__func.__name__}')
		else:
			interval = WeatherUnits.Time.Second(self.__interval.total_seconds())
			stagger = WeatherUnits.Time.Second(abs(self.__staggerAmount.total_seconds()))
			self.log.debug(f'{self.__owner.name} - Scheduled recurring event: {self.__func.__name__} every {interval} ±{stagger}')
		self.__run(startTime)

	def __del__(self):
		self.instances[self.__owner].remove(self)

	def stop(self):
		self.timer.stop()

	def reschedule(self, interval: timedelta = None, fireImmediately: bool = False):
		self.__fireImmediately = fireImmediately
		if interval is not None:
			self.interval = interval
		self.__run()

	@property
	def when(self) -> datetime:
		when = self.__interval.total_seconds()
		if self.__stagger:
			seconds = self.__staggerAmount.seconds*(random()*2 - 1)
			loopTime = asyncio.get_event_loop().time()
			if seconds + loopTime < 0:
				seconds = self.__staggerAmount.seconds*random()
			when += seconds
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
		loop = asyncio.get_event_loop()
		when = self.when if startTime is None else startTime
		if isinstance(when, timedelta):
			when = when.total_seconds()
		self.timer = loop.call_soon(self.__fire) if self.fireImmediately else loop.call_later(when, self.__fire)

	# print(f'Scheduled {self.__func.__name__} to run at {when.strftime("%-I:%M:%S%p").lower()}')

	def __fire(self):
		asyncio.create_task(self.__func(*self.__args, **self.__kwargs))
		self.log.verbose(f'{self.__func.__name__}() fired for {self.__owner.name}')
		if not self.__singleShot:
			self.__run()

	@property
	def __timeTo(self) -> float:
		return self.timer.when()


class Classes:
	Container: Type[Container]
	__slot__ = ('__classes',)
	__classes: dict

	def __init__(self, **classes):
		self.__classes = {}
		self.__classes.update(classes)

	def __getitem__(self, key):
		return self.__classes[key]

	def __setitem__(self, key, value):
		self.__classes[key] = value

	# def __getattr__(self, key):
	# 	if key in self.__slot__:
	# 		return super().__getattribute__(key)
	# 	return self.__classes[key]
	#
	# def __setattr__(self, key, value):
	# 	if key in self.__slot__:
	# 		super().__setattr__(key, value)
	# 	self.__classes[key] = value

	def __contains__(self, key):
		if isinstance(key, timedelta):
			return any(key == cls.period for cls in self.__classes.values())
		return key in self.__classes

	def __iter__(self):
		return iter(self.__classes.items())

	def __len__(self):
		return len(self.__classes)

	def __repr__(self):
		return repr(self.__classes)

	def __str__(self):
		return str(self.__classes)

	@property
	def Container(self) -> Type[Container]:
		return self.__classes['Container']


class PluginMeta(type):

	def __new__(mcs, name, bases, attrs, **kwargs):
		mcs.__APIKeyMap__ = {}

		if bases and not kwargs.get('prototype', False):
			ObservationClass = type(f'{name}Observation', (ObservationDict,), {})
			classes = {
				'Container':          type(f'{name}Container', (Container,), {}),
				'FrozenValueClass':   type(f'{name}FrozenValue', (ArchivedObservationValue,), {}),
				'ValueClass':         type(f'{name}Value', (ObservationValue,), {}),
				'RecordedValueClass': type(f'{name}RecordedValue', (RecordedObservationValue,), {}),
			}

			if kwargs.get('realtime', False):
				realtime = type(f'{name}Realtime', (ObservationRealtime,), {}, sourceKeyMap=mcs.__APIKeyMap__, recorded=True)
				classes['Realtime'] = realtime
				attrs['realtime'] = property(lambda self: self.observations.realtime)

			if l := kwargs.get('logged') or kwargs.get('recorded'):
				if isinstance(l, timedelta):
					period = l
				elif isinstance(l, bool):
					period = timedelta(minutes=5)
				elif isinstance(l, int):
					period = timedelta(minutes=l)
				else:
					period = kwargs.get('logFrequency', False) or kwargs.get('recordFrequency', False) or kwargs.get('frequency', Period.Minute)

				obsLog = type(f'{name}Log', (ObservationLog,), {'_period': period, 'FrozenValueClass': classes['FrozenValueClass']}, sourceKeyMap=mcs.__APIKeyMap__, recorded=True)
				classes['Log'] = obsLog
				attrs['log'] = property(lambda self: self.observations.log)

			if any(kwargs.get(k, False) for k in ('forecast', 'hourly', 'daily', 'minutely')):
				forecast = type(f'{name}Forecast', (ObservationTimeSeries,), {'_period': None}, sourceKeyMap=mcs.__APIKeyMap__, recorded=False)
				classes['Forecast'] = forecast

				if kwargs.get('hourly', False):
					hourly = type(f'{name}Hourly', (forecast,), {'_period': Period.Hour}, sourceKeyMap=mcs.__APIKeyMap__)
					classes['Hourly'] = hourly
					attrs['hourly'] = property(lambda self: self.observations.grab(Period.Hour))

				if kwargs.get('daily', False):
					daily = type(f'{name}Daily', (forecast,), {'_period': timedelta(days=1)}, sourceKeyMap=mcs.__APIKeyMap__)
					classes['Daily'] = daily
					attrs['daily'] = property(lambda self: self.observations.grab(Period.Day))

				if m := kwargs.get('minutely', False):
					if isinstance(m, int):
						period = timedelta(minutes=m)
					elif isinstance(m, timedelta):
						period = m
					else:
						period = Period.Minute
					minutely = type(f'{name}Minutely', (forecast,), {'_period': period}, sourceKeyMap=mcs.__APIKeyMap__)
					classes['Minutely'] = minutely
					attrs['minutely'] = property(lambda self: self.observations.grab(period))

			attrs['classes'] = Classes(**classes)
			attrs['pluginLog'] = pluginLog.getChild(name)

		return super().__new__(mcs, name, bases, attrs)


# observationClasses = {}
# observationAnnotations = {k: obs for k, obs in attrs['__annotations__'].items()
#                           if isinstance(obs, type)
#                           and not isinstance(obs, GenericAlias)
#                           and issubclass(obs, ObservationDict)}
#
# for obsName, observation in observationAnnotations.items():
# 	value = attrs.get(obsName, None)
# 	if isinstance(value, timedelta):
# 		if value.total_seconds() < 0:
# 			observationClasses[obsName] = type(f'{name}{obsName.title()}', (obsLog,), {'_period': value}, sourceKeyMap=mcs.__APIKeyMap__, recorded=True)
# 		else:
# 			observationClasses[obsName] = type(f'{name}{obsName.title()}', (forecast,), {'_period': value}, sourceKeyMap=mcs.__APIKeyMap__)
# 		continue
# 	if value is ObservationRealtime or observation is ObservationRealtime:
# 		observationClasses[obsName] = realtime
# 		continue
# 	if value is ObservationLog:
# 		observationClasses[obsName] = history
# 		continue
# 	if value is ObservationTimeSeries:
# 		observationClasses[obsName] = forecast
# 		continue
# 	# attrs[obsName] = property(fget=lambda self: getattr(self, f'__{obsName}'))
# attrs['__annotations__'].update(observationClasses)
# attrs.update(observationClasses)


class Plugin(metaclass=PluginMeta):
	schema: Schema
	publisher: Publisher
	classes: Classes
	observations: ObservationList[ObservationDict]

	realtime: Optional[ObservationRealtime]
	log: Optional[ObservationLog]

	def __init__(self):
		self.__running = False
		self.containers = {}
		self.containerCategories = CategoryDict(self, self.containers, None)

		self.pluginLog = pluginLog.getChild(f'{self.name}')

		self.observations = ObservationList(self)
		self.publisher = Publisher(self)

		if isinstance(self.schema, dict):
			self.schema = Schema(plugin=self, source=self.schema, category=self.name)

		for key, value in self.classes:
			if not issubclass(value, PublishedDict):
				continue
			if hasattr(value, 'period') and value.period is None:
				continue
			o = value(source=self)
			o.dataName = key.lower()
			if o.published:
				o.accumulator.connectSlot(self.publisher.addBulk)
			self.observations.append(o)

		self.config = self.getConfig(self)

	@abstractmethod
	def start(self):
		pass

	async def asyncStart(self):
		asyncio.get_running_loop().call_soon(self.start)

	@classmethod
	def getConfig(cls, plugin: 'Plugin'):
		cls.configFileName = f'{cls.__name__}.ini'

		# Look in the userPlugins directory for config files.
		# Plugin configs can either be in userPlugins/PluginName/config.ini or userPlugins/PluginName.ini
		match pluginConfig.userPluginsDir.asDict(depth=2):
			case {cls.__name__: {'config.ini': file}}:
				del cls.configFileName
				value = PluginConfig(path=file.path, plugin=plugin)
				if plugin._validateConfig(value):
					return value
			case {cls.configFileName: file}:
				del cls.configFileName
				value = PluginConfig(path=file.path, plugin=plugin)
				if plugin._validateConfig(value):
					return value
		del cls.configFileName
		# configsDict = config.userPath['plugins'].asDict(depth=3)
		# if cls.__name__ in configsDict and isinstance(d := configsDict[cls.__name__], dict) and 'config.ini' in d:
		# 	value = PluginConfig(path=config.userPath['plugins'][cls.__name__].path, plugin=plugin)
		# 	if plugin._validateConfig(value):
		# 		return value
		# elif cls.configFileName in configsDict and isinstance(d := configsDict[cls.configFileName], File):
		# 	del cls.configFileName
		# 	value = PluginConfig(path=config.userPath['plugins'][cls.configFileName].path, plugin=plugin)
		# 	if plugin._validateConfig(value):
		# 		return value

		# Look in the userConfig file for sections with the plugin name
		if pluginConfig.has_section(cls.__name__):
			value = PluginConfig(plugin=plugin)
			if cls._validateConfig(value):
				return value
		raise ValueError(f'No config for {cls.__name__}')

	@classmethod
	def _validateConfig(cls, cfg: pluginConfig):
		return True

	@property
	def running(self) -> bool:
		return self.__running

	def enabled(self) -> bool:
		return self.config['enabled']

	def setEnabled(self, value: bool = None):
		if value is None:
			value = not self.enabled()
		self.config.defaults()['enabled'] = value
		if value:
			self.start()

	# self.config.save()

	@property
	def name(self) -> str:
		return self.__class__.__name__

	def __hash__(self):
		return hash(self.name)

	def items(self):
		return self.containers.items()

	def get(self, key: CategoryItem, timeframe: timedelta = Period.Realtime) -> ObservationValue:
		endpoint = self.observations.grab(timeframe)
		if not endpoint:
			raise IndexError(f'No endpoint found for {timeframe}')
		return endpoint[key]

	def __getitem__(self, item: Union[str, datetime, timedelta]):
		# if item is a timedelta:
		if isinstance(item, timedelta):
			# add the current date to the item
			item = datetime.now() + item
		# if the item is a datetime:
		if isinstance(item, datetime):
			# find the observation that is the closest to the item
			# TODO: Fix this
			times = closest([a.time if isinstance(a, Observation) else a['time'][0] for a in self.observations], item)

		# get the value for all the observations
		if isinstance(item, (str, CategoryItem)):
			if item in self:
				return self.containers.get(item, self.__buildContainer(item))
			elif any(item in endpoint for endpoint in self.observations):
				return {endpoint.period: endpoint[item] for endpoint in self.observations if item in endpoint.categories}

	def __buildContainer(self, key: CategoryItem):
		self.containers[key] = self.classes.Container(self, key)
		if 'low' in str(key):
			a = self.containers[key].daily
		return self.containers[key]

	def keys(self):
		keys = set()
		for endpoint in self.observations:
			keys |= set(endpoint.keys())
		return keys

	def values(self):
		return self.containers.values()

	def __contains__(self, item):
		if not isinstance(item, CategoryItem):
			item = CategoryItem(item)
		return any(item in endpoint for endpoint in self.observations)

	def sharedKeys(self, *periods: list[Union[Period, int, timedelta]]):
		keys = self.keys
		for endpoint in [self.observations.grab(period) for period in periods]:
			keys.intersection_update(set(endpoint.keys()))
		return list(keys)

	def hasForecastFor(self, item: str) -> bool:
		return any([item in endpoint.keys() and endpoint.isForecast for endpoint in self.observations])

	async def logValues(self):
		# if self.realtime.keyed:
		# 	values = {key: archived.rawValue for key, value in self.realtime.items() if not key.isAnonymous and (archived := value.archived) is not None}
		# else:
		# 	values = {key: archived for key, value in self.realtime.items() if (archived := value.archived) is not None}
		archive = self.realtime.archived
		if len(archive) > 0:
			await self.log.asyncUpdate(archive)


__all__ = ['Plugin', 'ObservationList', 'Container', 'Publisher', 'ScheduledEvent', 'Classes']
