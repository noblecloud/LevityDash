from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from functools import cached_property
from typing import Callable, Coroutine, Dict, Iterable, List, Set

from itertools import groupby
from PySide6.QtCore import Signal, Slot, QTimer
from rich.repr import auto as auto_rich_repr

from LevityDash import LevityDashboard
from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.plugins.categories import CategoryEndpointDict, CategoryItem
from LevityDash.lib.plugins.observation import MeasurementTimeSeries, Observation, Container
from LevityDash.lib.plugins.plugin import AnySource, Plugin, SomePlugin
from LevityDash.lib.plugins.utils import Request, GuardedRequest, ChannelSignal, MutableSignal
from LevityDash.lib.utils.data import KeyData
from LevityDash.lib.utils.shared import clearCacheAttr, Period

log = LevityPluginLog.getChild('Dispatcher')


@auto_rich_repr
class MultiSourceContainer(dict):
	key: CategoryItem
	period: Period
	value: Container
	_value: Container
	preferredSource: str
	timeOffset: timedelta
	relay: 'MultiSourceChannel'

	waitingForAnyRealtime: Dict[Plugin | SomePlugin, Set[Request]]
	waitingForTrueRealtime: Dict[Plugin | SomePlugin, Set[Request]]
	waitingForTimeseries: Dict[Plugin | SomePlugin, Set[Request]]
	waitingForDaily: Dict[Plugin | SomePlugin, Set[Request]]

	def __init__(self, key, value: Container = None, preferredSource: str = None, timeOffset: timedelta = None):
		self.waitingForAnyRealtime = defaultdict(set)
		self.waitingForTimeseries = defaultdict(set)
		self.waitingForTrueRealtime = defaultdict(set)
		self.waitingForDaily = defaultdict(set)
		self.preferredSource = preferredSource
		self.key = key

		# Relay listens to container updates
		# data in > update > changed keys > plugin collects > relay updates > data out
		self.relay = MultiSourceChannel(self, key)
		self.timeOffset = timeOffset

		super(MultiSourceContainer, self).__init__(value if value else {})

	def __getitem__(self, item: str | Plugin) -> Container:
		if isinstance(item, Plugin):
			item = item.name
		return super(MultiSourceContainer, self).__getitem__(item)

	def __hash__(self):
		return hash((self.key, type(self)))

	def __contains__(self, item) -> bool:
		return super(MultiSourceContainer, self).__contains__(item) or any(i.name == item for i in self.plugins)

	def __rich_repr__(self):
		yield 'key', self.key.name
		if self.values():
			yield 'sources', list(self.keys())
			yield 'value', self.value
			yield 'isRealtime', self.isRealtime
			yield 'isForecast', self.isForecast
			yield 'isTimeseries', self.isTimeseries
			yield 'isDaily', self.isDaily
		else:
			yield 'sources', 'None'

	def __bool__(self) -> bool:
		return len(self) > 0

	@property
	def value(self) -> Container:
		if self.preferredSource and self.preferredSource in self.keys():
			value = self[self.preferredSource]
		else:
			clearCacheAttr(self, 'defaultContainer')
			value = self.defaultContainer
		return value

	@property
	def hourly(self) -> MeasurementTimeSeries | None:
		if self.value.source.hourly is not None and self.key in self.value.source.hourly:
			value = self.value.hourly
			return value
		else:
			containersWithHourly = [container for container in self.values()
				if hasattr(container, 'hourly')
				   and container.hourly is not None]
			try:
				return containersWithHourly[0].hourly
			except IndexError:
				return None

	@property
	def daily(self) -> MeasurementTimeSeries | None:
		if self.value.source.daily is not None and self.key in self.value.source.daily:
			value = self.value.daily
			return value
		else:
			containersWithDaily = [container for container in self.values()
				if hasattr(container, 'daily')
				   and container.daily is not None]
			try:
				return containersWithDaily[0].daily
			except IndexError:
				return None

	@property
	def timeseries(self) -> MeasurementTimeSeries | None:
		if self.value.source.hasTimeseriesFor(self.key):
			return self.value.timeseries
		return next((plugin[self.key].timeseries for plugin in self.plugins if plugin.hasTimeseriesFor(self.key)), None)

	@property
	def realtime(self) -> Observation | None:
		if self.timeseriesOnly:
			return self.nowFromTimeseries
		if self.value.source.hasRealtimeFor(self.key):
			return self.value.now
		return next((plugin[self.key].realtime for plugin in self.plugins if plugin.hasRealtimeFor(self.key)), None)

	def getRealtimeContainer(self, preferredSource: Plugin | SomePlugin = AnySource, strict=False) -> Container | None:
		"""
		Returns a container that has realtime source.  If a source is specified, it will try to return that
		source first, but will always fall back to any container with a realtime or approximate realtime source.
		If strict is True, it will only return containers that have True realtime sources.
		:param preferredSource: The preferred source to return.
		:param strict: If True, only return containers that have strict realtime sources.

		:return: A container with realtime data.
		"""

		try:
			return self[preferredSource if preferredSource is not AnySource else None or self.preferredSource]
		except KeyError:
			pass
		realtimeContainers = sorted(
			[container for container
				in self.values()
				if container.isRealtime
				   or (container.isRealtimeApproximate and not strict)],
			key=lambda c: (c.isRealtime, len(c.source.config.defaultFor)), reverse=True
		)
		try:
			return realtimeContainers[0]
		except IndexError:
			return None

	def getTimeseries(self, preferredSource: Plugin | SomePlugin = AnySource, strict=False) -> Container | None:
		"""
		Returns a container that has timeseries source.  If a source is specified, it will try to return that
		source first, but will always fall back to any container with a timeseries source.
		If strict is True, it will only return containers have forecast data.
		:param preferredSource: The preferred source to return.
		:param strict: If True, only return containers that have forcasting sources.

		:return: A container with timeseries data.
		"""

		try:
			preferred = self[preferredSource if preferredSource is not AnySource else None or self.preferredSource]
			if preferred.isForecast or (not strict and (preferred.isTimeseries or preferred.isDaily)):
				return preferred
		except KeyError:
			pass
		timeseriesContainers = sorted(
			[
				c for c in self.values()
				if c.isForecast or ((c.isTimeseries or c.isDaily) and not strict)
			],
			key=lambda c: (c.isForecast, len(c.source.config.defaultFor)), reverse=True
		)
		try:
			return timeseriesContainers[0]
		except IndexError:
			return None

	def getDaily(self, preferredSource: Plugin | SomePlugin = AnySource) -> Container | None:
		"""
		Returns a container that has a daily source.  If a source is specified, it will try to return that
		source first, but will always fall back to any container with a daily source.
		If strict is True, it will only return containers have daily data.

		:param preferredSource: The preferred source to return.

		:return: A container with daily data.
		"""

		try:
			preferred = self[preferredSource if preferredSource is not AnySource else None or self.preferredSource]
			if preferred.isDailyForecast:
				return preferred
		except KeyError:
			pass
		dailyContainers = sorted(
			[
				c for c in self.values()
				if c.isDaily
			],
			key=lambda c: (c.isDailyForecast, len(c.source.config.defaultFor)), reverse=True
		)
		try:
			return dailyContainers[0]
		except IndexError:
			return None

	@property
	def timeseriesOnly(self):
		return all(container.metadata.get('isTimeseriesOnly', False) for container in self.values())

	@property
	def nowFromTimeseries(self) -> Observation | None:
		if (default := self.defaultContainer).isTimeseriesOnly:
			return default.nowFromTimeseries
		return next((container.nowFromTimeseries for container in self.values() if container.isTimeseriesOnly), None)

	@property
	def plugins(self) -> List['Plugin']:
		return [value.source for value in self.values()]

	@property
	def title(self):
		if self.plugins and hasattr(self.value, 'title'):
			return self.value.title
		try:
			return self.default_source.schema[self.key].title
		except AttributeError:
			return str(self.key.name)

	@cached_property
	def default_source(self) -> Plugin | None:
		for plugin in self.valid_sources:
			for i in self.key[::-1]:
				if i in plugin.config.defaultFor:
					return plugin
		return next(iter(self.valid_sources), None)

	@property
	def valid_sources(self) -> List[Plugin]:
		_plugins = [i for i in LevityDashboard.plugins if self.key in i.schema]
		_plugins.sort(key=lambda p: (0 if not p.enabled else 2 if p.running else 1, len(p.config.defaultFor)), reverse=True)
		return _plugins

	@cached_property
	def defaultContainer(self) -> 'Container':
		if len(self) == 1:
			return list(self.values())[0]
		_plugins = [i for i in LevityDashboard.plugins if i.config['enabled'] and i.name in self]
		for i in self.key[::-1]:
			for plugin in _plugins:
				if i in plugin.config.defaultFor:
					return self[plugin.name]
		for plugin in _plugins:
			if LevityDashboard.dispatcher[plugin.name] in self:
				return self[plugin.name]
		options = list(self.values())
		if len(options) == 1:
			return options[0]
		elif len(options) > 1:
			options = sorted(options, key=lambda x: len(x.source.config.defaultFor), reverse=True)
			return options[0]
		else:
			raise ValueError('No default container found for {}'.format(self.key))

	def checkAwaiting(self, container: Container):
		plugin = container.source
		if container.isRealtime and (self.waitingForTrueRealtime[plugin] or self.waitingForTrueRealtime[AnySource]):
			log.verbose(f"{plugin.name} is ready with a strict realtime value for {self.key}", verbosity=1)
			for request in (*self.waitingForTrueRealtime.pop(plugin, []), *self.waitingForTrueRealtime.pop(AnySource, [])):
				log.verbose(f"Issuing callback for {request.requester!s}", verbosity=1)
				# LevityDashboard.main_thread_pool.run_in_thread(request.callback)
				# request.callback()
				QTimer.singleShot(1, request.callback)

		if (container.isRealtime or container.isRealtimeApproximate) and (
			self.waitingForAnyRealtime[plugin] or self.waitingForAnyRealtime[AnySource]
		):
			log.verbose(f"{plugin!s} is ready with an approximate realtime value for {self.key.name}", verbosity=1)
			for request in (*self.waitingForAnyRealtime.pop(plugin, []), *self.waitingForAnyRealtime.pop(AnySource, [])):
				log.verbose(f"Issuing callback for {request.requester!s}", verbosity=1)
				if container.isTimeseriesOnly:
					container.prepare_for_ts_connection(request.callback)
				else:
					# LevityDashboard.main_thread_pool.run_in_thread(request.callback)
					QTimer.singleShot(1, request.callback)

		if requesters := (self.waitingForTimeseries[plugin] or self.waitingForTimeseries[AnySource]):
			if plugin[self.key].isForecast:
				log.verbose(f"{plugin.name} timeseries is ready for {self.key}", verbosity=1)
				for request in (*self.waitingForTimeseries.pop(plugin, []), *self.waitingForTimeseries.pop(AnySource, [])):
					log.verbose(f"Issuing callback for {request.requester!s}", verbosity=1)
					container.prepare_for_ts_connection(request.callback)
			elif plugin is not AnySource:
				plugin_container = self[plugin]

				for request in requesters:

					if isinstance(request, Request):
						request = GuardedRequest.from_request(request, guard = lambda container: container.isTimeseries)

					plugin_container.notifyOnRequirementsMet(request)

		if self.waitingForDaily[plugin] or self.waitingForDaily[AnySource]:
			if plugin[self.key].isDailyForecast:
				log.verbose(f"{plugin.name} daily is ready for {self.key}", verbosity=1)
				for request in (*self.waitingForDaily.pop(plugin, []), *self.waitingForDaily.pop(AnySource, [])):
					log.verbose(f"Issuing callback for {request.requester!s}", verbosity=1)
					container.prepare_for_ts_connection(request.callback)

	def addValue(self, plugin: Plugin, container: Container):
		self[plugin.name] = container
		self.relay.listen_to_container(container)
		clearCacheAttr(self, 'defaultContainer', 'default_source')
		log.verbose(f'Added {plugin.name} to {self.key}', verbosity=0)
		self.checkAwaiting(container)

	def onUpdates(self, observations: Iterable[Observation]):
		containers = {obs.source[self.key] for obs in observations}
		for container in containers:
			self.checkAwaiting(container)

	def toDict(self):
		state = {'key': str(self.key)}
		if self.preferredSource:
			state['preferredSource'] = self.preferredSource
		if self.period:
			state['period'] = self.period
		if self.timeOffset:
			state['startTime'] = self.timeOffset
		return state

	@property
	def valueChanged(self):
		return self.defaultContainer.valueChanged

	def getPreferredSourceContainer(self, requester, plugin: Plugin | SomePlugin, callback: Callable, timeseriesOnly: bool = False):
		log.verbose(f'{requester!s} requested {"timeseries" if timeseriesOnly else "approximate realtime value"} '
		          f'from {"any source" if (plugin is AnySource) else str(plugin)} for {self.key.name}', verbosity=4)
		if timeseriesOnly:
			self.waitingForTimeseries[plugin].add(Request(requester, callback))
		else:
			self.waitingForAnyRealtime[plugin].add(Request(requester, callback))

	def getTrueRealtimeContainer(self, requester, source: Plugin | SomePlugin, callback: Callable):
		log.verbose(f'{requester!s} requested true realtime value from '
		          f'{str(source) if source is not AnySource else "any source"} for {self.key.name}', verbosity=4)
		self.waitingForTrueRealtime[source].add(Request(requester, callback))

	def getDailyContainer(self, requester, source: Plugin | SomePlugin, callback: Callable):
		log.verbose(f'{requester!s} requested daily value from '
		          f'{str(source) if source is not AnySource else "any source"} for {self.key.name}', verbosity=4)
		self.waitingForDaily[source].add(Request(requester, callback))

	@property
	def hasPendingRealtime(self):
		return sum(len(i) for i in self.waitingForAnyRealtime.values())

	@property
	def hasPendingTrueRealtime(self):
		return sum(len(i) for i in self.waitingForTrueRealtime.values())

	@property
	def isRealtime(self):
		return any(container.isRealtime for container in self.values())

	@property
	def isRealtimeApproximate(self):
		return any(container.isRealtimeApproximate for container in self.values())

	@property
	def isTimeseries(self):
		return any(container.isTimeseries for container in self.values())

	@property
	def isForecast(self):
		return any(container.isForecast for container in self.values())

	@property
	def isDaily(self):
		return any(container.isDaily for container in self.values())

	@property
	def isDailyForecast(self):
		return any(container.isDailyForecast for container in self.values())

	@property
	def isTimeseriesOnly(self):
		return all(container.isTimeseries and not container.isRealtime for container in self.values())

	@property
	def isDailyOnly(self):
		return all(container.isDaily for container in self.values())


class MultiSourceChannel(ChannelSignal):
	"""
	Emits changed sub-containers.
	"""
	_source: MultiSourceContainer
	_pending = Dict[Container, Set['Observation']]

	def __init__(self, container: MultiSourceContainer, key):
		super(MultiSourceChannel, self).__init__(container, key)
		self._pending = defaultdict(set)

	def publish(self, observations: Set['Observation']):
		if isinstance(observations, set):
			containers = {key: set(values) for key, values in groupby(observations, lambda obs: obs.source[self.key])}
		else:
			containers = {observations.source[self.key]: {observations}}

		for container, observations in containers.items():
			self._pending[container].update(observations)
		if not self.muted and self._pending:
			self._emit()

	def __repr__(self):
		return f'Signal for MultiSourceContainer {self._key}'

	def _emit(self):
		self._signal.emit(self._source)
		self._source.onUpdates(self._pending)
		self._pending.clear()

	def listen_to_container(self, container: 'Container'):
		container.channel.connectSlot(self.publish)


@dataclass
class MonitoredKey:
	key: CategoryItem = field()
	period: Period = field(init=False)
	source: str = field(init=False)
	value: MultiSourceContainer = field(init=False)
	requesters: set = field(init=False)
	attempts: int = field(init=False)

	def __post_init__(self):
		self.period = None
		self.source = None
		self.value = None
		self.requesters = set()
		self.attempts = 0

	@property
	def success(self) -> bool:
		return not self.requesters


class PluginValueDirectory(MutableSignal):
	__plugins = 'Plugins'
	__singleton = None
	__signal = Signal(set)
	categories = None
	_values = {}
	_pending: Dict[CategoryItem, Set['Container']]
	__channels: Dict['CategoryItem', MultiSourceChannel] = {}
	__awaitingKey: Dict['CategoryItem', Set[Coroutine]] = defaultdict(set)
	name: str = 'PluginValueDirectory'

	def __new__(cls, *args, **kwargs):
		if cls.__singleton is None:
			cls.__singleton = super(PluginValueDirectory, cls).__new__(cls, *args, **kwargs)
			LevityDashboard.dispatcher = cls.__singleton
			LevityDashboard.get_container = cls.__singleton.getContainer
			LevityDashboard.get_channel = cls.__singleton.getChannel
		return cls.__singleton

	def __init__(self, manager: 'Plugins'):
		super(PluginValueDirectory, self).__init__()
		self._pending = defaultdict(set)
		self.__plugins = manager
		for plugin in self.plugins:
			if plugin is AnySource:
				continue
			plugin.publisher.connectSlot(self.keyAdded)
		self.categories = CategoryEndpointDict(self, self._values, None)

	def connect_plugin(self, plugin: Plugin) -> bool:
		return plugin.publisher.connectSlot(self.keyAdded)

	@property
	def new_keys_signal(self) -> Signal:
		return self.__signal

	@property
	def muted(self):
		return self._muted

	@MutableSignal.muted.setter
	def muted(self, value):
		MutableSignal.muted.fset(self, value)
		list(map(lambda x: x.setMute(value), self.__channels.values()))

	def _emit(self):
		self.__signal.emit(self._pending)
		self._pending.clear()

	def publish(self, data: Dict[CategoryItem, 'Container']):
		# Add to pending keys
		for key, value in data.items():
			self._pending[key].add(value)

		if not self.muted:
			# Publish to global channel
			self._emit()

	def keys(self) -> Iterable[CategoryItem]:
		return self._values.keys()

	def values(self):
		return self._values.values()

	def containers(self):
		return [i for i in self._values.values() if len(i)]

	def items(self):
		return self._values.items()

	def __hash__(self):
		return hash(str(self.__class__.__name__))

	@Slot(KeyData)
	def keyAdded(self, data: KeyData):
		# This is probably not the correct name for this slot...
		# It is called when a publisher has a new value not a new key
		keys = data.keys
		if isinstance(keys, dict):
			keys = set(*data.keys.values())
		values = {key: data.sender[key] for key in keys}
		self.update(values)
		for key in keys & set(self.__awaitingKey.keys()):
			raise NotImplementedError('Awaiting keys not implemented')

	def __getitem__(self, item):
		if item in self.__plugins:
			return self.__plugins[item]
		return self._values[item]

	def __getContainer(self, key) -> MultiSourceContainer:
		if (container := self._values.get(key, None)) is None:
			container = self._values[key] = MultiSourceContainer(key)
		return container

	def getContainer(self, key, default=None) -> MultiSourceContainer:
		return self._values.get(key, default) or self.__getContainer(key)

	def __setitem__(self, key, value):
		container = self.__getContainer(key)
		if value.source.name not in container:
			container.addValue(value.source, value)

	def update(self, values: dict[CategoryItem, Container]):
		# log.debug(f'Updating {values}')
		with self as signal:
			for key, value in values.items():
				self[key] = value
			self.publish(values)

	def getChannel(self, key: CategoryItem) -> ChannelSignal:
		if key not in self.__channels:
			container = self.__getContainer(key)
			channel = MultiSourceChannel(container, key)
			self.__channels[key] = channel
		return self.__channels[key]

	def notifyWhenKeyAdded(self, key: CategoryItem, callback: Coroutine):
		self.__awaitingKey[key].add(callback)

	@property
	def hasAwaiting(self) -> bool:
		return bool(sum(len(x) for x in self.__awaitingKeys.values()))

	def fromState(self, state: dict):
		for key in state:
			self._values[key] = state[key]

	@property
	def plugins(self) -> 'Plugins':
		return self.__plugins

__all__ = ("PluginValueDirectory", "MultiSourceContainer", "MultiSourceChannel")
