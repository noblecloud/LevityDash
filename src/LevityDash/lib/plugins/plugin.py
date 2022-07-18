import asyncio
from asyncio import get_running_loop, sleep
from abc import abstractmethod
from datetime import datetime, timedelta
from functools import cached_property, lru_cache
from operator import attrgetter

from typing import Iterable, Optional, Type, Union, Mapping

from LevityDash.lib.config import pluginConfig, PluginConfig
from LevityDash.lib.plugins.categories import CategoryDict, CategoryItem
from LevityDash.lib.plugins.observation import (ArchivedObservationValue, Observation, ObservationDict,
                                                ObservationLog, ObservationRealtime, RealtimeSource, ObservationTimeSeries, ObservationValue,
                                                PublishedDict, RecordedObservationValue, Container)
from LevityDash.lib.plugins.schema import Schema
from LevityDash.lib.log import LevityPluginLog as pluginLog
from LevityDash.lib.utils.shared import closest, Period
from LevityDash.lib.plugins.utils import Publisher


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
	def grab(self, value: timedelta, sensitivity: timedelta = timedelta(minutes=5), timeseriesOnly: bool = False) -> Optional[ObservationDict]:
		if isinstance(value, int):
			value = timedelta(seconds=value)
		if isinstance(value, Period):
			value = value.value

		if isinstance(sensitivity, int):
			sensitivity = timedelta(seconds=sensitivity)
		if isinstance(sensitivity, Period):
			sensitivity = sensitivity.value

		selection = [obs for obs in self if isinstance(obs, ObservationTimeSeries)] if timeseriesOnly else self
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
			return self.grab(Period.Hour, sensitivity=Period.QuarterHour, timeseriesOnly=True)
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
			return self.grab(Period.Day, sensitivity=Period.Hour, timeseriesOnly=True)
		except IndexError:
			return None

	@cached_property
	def log(self) -> Optional[ObservationLog]:
		try:
			return self[0]
		except AttributeError:
			return None

	@property
	def timeseries(self) -> Iterable[ObservationTimeSeries]:
		return [obs for obs in self if not isinstance(obs, RealtimeSource)]


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

			if any(kwargs.get(k, False) for k in ('timeseries', 'hourly', 'daily', 'minutely')):
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


class SomePlugin(metaclass=PluginMeta, prototype=True):
	name = 'any'

	def __eq__(self, other):
		return isinstance(other, (Plugin, SomePlugin)) or other == 'any'

	def __repr__(self):
		return 'SomePlugin(any)'

	def __subclasscheck__(self, subclass):
		return issubclass(subclass, Plugin)

	def __instancecheck__(self, instance):
		return isinstance(instance, Plugin)

	def __hash__(self):
		return hash('any')


AnySource = SomePlugin()
SomePlugin.AnySource = AnySource


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
				o.accumulator.connectSlot(self.publisher.publish)
			self.observations.append(o)

		self.config = self.getConfig(self)

	@abstractmethod
	def start(self):
		raise NotImplementedError

	@abstractmethod
	async def asyncStart(self):
		raise NotImplementedError

	@abstractmethod
	def stop(self):
		raise NotImplementedError

	@abstractmethod
	async def asyncStop(self):
		raise NotImplementedError

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
			return value
		raise ValueError(f'No config for {cls.__name__}')

	@classmethod
	def _validateConfig(cls, cfg: pluginConfig):
		return True

	@property
	def running(self) -> bool:
		raise NotImplementedError

	def enabled(self) -> bool:
		return self.config['enabled']

	def setEnabled(self, value: bool = None):
		if value is None:
			value = not self.enabled()
		self.config.defaults()['enabled'] = value
		if value:
			self.start()

	@property
	def name(self) -> str:
		return self.__class__.__name__

	def __hash__(self):
		return hash(self.name)

	def __str__(self):
		return self.name

	def __repr__(self):
		return f'Plugin({self.name})'

	def __eq__(self, other) -> bool:
		if other is any:
			return True
		if isinstance(other, str):
			return self.name == other
		if isinstance(other, Plugin):
			return self.name == other.name
		return False

	def items(self):
		return self.containers.items()

	def get(self, key: CategoryItem, timeframe: timedelta = Period.Realtime) -> ObservationValue:
		endpoint = self.observations.grab(timeframe)
		if not endpoint:
			raise IndexError(f'No endpoint found for {timeframe}')
		return endpoint[key]

	def __getitem__(self, item: Union[str, CategoryItem, datetime, timedelta]):
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

	def hasTimeseriesFor(self, item: str | CategoryItem) -> bool:
		return any([item in endpoint.keys() and hasattr(endpoint, 'timeseries') for endpoint in self.observations if not isinstance(endpoint, RealtimeSource)])

	def hasRealtimeFor(self, item: str | CategoryItem) -> bool:
		return any([item in endpoint.keys() for endpoint in self.observations if isinstance(endpoint, RealtimeSource)])

	async def logValues(self):
		# if self.realtime.keyed:
		# 	values = {key: archived.rawValue for key, value in self.realtime.items() if not key.isAnonymous and (archived := value.archived) is not None}
		# else:
		# 	values = {key: archived for key, value in self.realtime.items() if (archived := value.archived) is not None}
		archive = self.realtime.archived
		if len(archive) > 0:
			await self.log.asyncUpdate(archive)


__all__ = ['Plugin', 'ObservationList', 'Classes']
