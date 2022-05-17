from dataclasses import dataclass, field
from datetime import timedelta
from functools import cached_property
from PySide2.QtCore import QObject, QTimer, Signal, Slot
from typing import Any

from LevityDash.lib.plugins.observation import MeasurementTimeSeries
from LevityDash.lib.plugins.plugin import Container
from LevityDash.lib.plugins import Plugins, Accumulator
from LevityDash.lib.plugins.categories import CategoryEndpointDict, CategoryItem
from LevityDash.lib.utils.data import KeyData
from LevityDash.lib.utils.shared import clearCacheAttr, Period
from LevityDash.lib.log import LevityPluginLog

log = LevityPluginLog.getChild('Dispatcher')


class MultiSourceContainer(dict):
	key: CategoryItem
	period: Period
	value: Any
	_value: Any
	preferredSource: str
	timeOffset: timedelta

	def __init__(self, key, value: Container = None, preferredSource: str = None, timeOffset: timedelta = None):
		self.key = key
		self.preferredSource = preferredSource
		self.timeOffset = timeOffset

		super(MultiSourceContainer, self).__init__(value if value else {})

	def __str__(self):
		return self.value.__str__()

	def __getattr__(self, item):
		if item == 'defaultContainer':
			return self.__getattribute__(item)
		attr = getattr(self.__getattribute__('value').value, item, None)
		if attr is None:
			if item in dir(self):
				return self.__getattribute__(item)
			else:
				return self.defaultContainer.__getattr__(item)
		if isinstance(attr, Container):
			return attr.value
		return attr

	def __setattr__(self, key, value):
		if key in self.__annotations__:
			self.__dict__[key] = value
		else:
			self.value.__setattr__(key, value)

	def __setitem__(self, key, value):
		super(MultiSourceContainer, self).__setitem__(key, value)
		clearCacheAttr(self, 'defaultContainer')

	@property
	def value(self) -> Container:
		if self.preferredSource and self.preferredSource in self.keys():
			value = self[self.preferredSource]
		else:
			clearCacheAttr(self, 'defaultContainer')
			value = self.defaultContainer
		# if self.period:
		# 	if self.period in 'realtime,now' or self.period == Period.Now:
		# 		period = 0
		# 	elif self.period in 'minutely' or self.period == Period.Minute:
		# 		period = 1
		# 	elif self.period in 'hourly' or self.period == Period.Hour:
		# 		period = 2
		# 	elif self.period in 'daily' or self.period == Period.Day:
		# 		period = 3
		# 	else:
		# 		period = 4
		# 	while not (hasattr(value, period) and getattr(value, period)) and period >= 0:
		# 		period -= 1
		# 	if period >= 0:
		# 		value = getattr(value, periods[period])
		#
		# if self.timespan and period != 0:
		# 	pass

		return value

	@property
	def hourly(self) -> 'MeasurementTimeSeries':
		if self.value.source.hourly is not None and self.key in self.value.source.hourly:
			value = self.value.hourly
			return value
		else:
			containersWithHourly = [container for container in self.values()
				if hasattr(container, 'hourly')
				   and container.hourly is not None]

			if containersWithHourly:
				return containersWithHourly[0].hourly
			else:
				return None

	@property
	def forecast(self):
		return self.hourly

	@property
	def title(self):
		if hasattr(self.value, 'title'):
			return self.value.title
		return self.key

	@cached_property
	def defaultContainer(self) -> 'Container':
		if len(self) == 1:
			return list(self.values())[0]
		_plugins = [i for i in Plugins if i.config['enabled'] and i.name in self]
		for i in self.key[::-1]:
			for plugin in _plugins:
				if i in plugin.config.defaultFor:
					return self[plugin.name]
		for plugin in _plugins:
			if ValueDirectory[plugin.name] in self:
				return self[plugin.name]
		options = list(self.values())
		if len(options) == 1:
			return options[0]
		elif len(options) > 1:
			options = sorted(options, key=lambda x: len(x.config.defaultFor), reverse=False)
			return options[0]
		else:
			raise ValueError('No default container found for {}'.format(self.key))

	def addValue(self, endpoint, value):
		self[endpoint.name] = value

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


@dataclass
class MonitoredKey:
	key: CategoryItem = field(init=True)
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


class newKeysSignalWrapper(QObject):
	newKeys = Signal(list)


class MonitoredKeySignalWrapper(QObject):
	signal = Signal(MonitoredKey)
	requirementsSignal = Signal(MonitoredKey)
	monitoredKeys = {}
	monitoredKeysForecastKeys = {}

	announcedKeys = {}
	announcedKeysForecastKeys = {}

	def __init__(self, source):
		self.source = source
		super(MonitoredKeySignalWrapper, self).__init__()

	def add(self, key, requester, requires=None):
		if requires:
			if key not in self.monitoredKeysForecastKeys:
				self.monitoredKeysForecastKeys[key] = MonitoredKey(key)
			self.monitoredKeysForecastKeys[key].requesters.add(requester)
		else:
			if key not in self.monitoredKeys:
				self.monitoredKeys[key] = MonitoredKey(key)
			self.monitoredKeys[key].requesters.add(requester)

	def announce(self, values):
		for value in values:
			if key := self.monitoredKeys.get(value.key, False):
				key.value = self.source[value.key]
				self.signal.emit(key)
				key.attempts += 1
				self.announcedKeys[key.key] = self.monitoredKeys.pop(key.key)
			if key := self.monitoredKeysForecastKeys.get(value.key, False):
				key.value = value
				if value.forecast.hasForecast:
					value.forecast.update()
					self.requirementsSignal.emit(key)
					log.info(f'Announcing {key.key} with forecast')
					key.attempts += 1
				self.announcedKeysForecastKeys[key.key] = self.monitoredKeysForecastKeys.pop(key.key)

	# if self.announcedKeys or self.announcedKeysForecastKeys:
	# self.clearSuccess.start()

	def __contains__(self, item):
		return item in self.monitoredKeys

	def hasRequirements(self, value: MultiSourceContainer) -> bool:
		return value.key in self.monitoredKeysForecastKeys and any(container.forecast for container in value.values())


class PluginValueDirectory:
	__plugins = Plugins
	__singleton = None
	categories = None
	_values = {}

	def __new__(cls, *args, **kwargs):
		if cls.__singleton is None:
			cls.__singleton = super(PluginValueDirectory, cls).__new__(cls, *args, **kwargs)
		return cls.__singleton

	def __init__(self):
		super(PluginValueDirectory, self).__init__()
		self.monitoredKeys = MonitoredKeySignalWrapper(self)
		self.newKeys = Accumulator(self)
		self.clearSuccess = QTimer(singleShot=True, interval=5000, timeout=self.clearSuccessful)
		for plugin in self.plugins:
			plugin.publisher.connectSlot(self.keyAdded)
		self.categories = CategoryEndpointDict(self, self._values, None)

	def clearSuccessful(self):
		monitor = self.monitoredKeys
		monitor.announcedKeys = {key: value for key, value in monitor.announcedKeys.items() if not value.success}
		monitor.announcedKeysForecastKeys = {key: value for key, value in monitor.announcedKeysForecastKeys.items() if not value.success}

		for key in monitor.announcedKeys.values():
			key.attempts += 1
			monitor.signal.emit(key)
			log.info(f'Announcing {key.key}')
		for key in monitor.announcedKeysForecastKeys.values():
			if key.value.forecast.hasForecast:
				if len(key.value.forecast) < 5:
					key.value.forecast.update()
				key.attempts += 1
				monitor.requirementsSignal.emit(key)
				log.info(f'Announcing {key.key} with forecast')
			if key.attempts > 5:
				log.info(f'{key.key} failed to announce after {key.attempts} attempts')
			elif key.attempts > 15:
				log.info(f'{key.key} failed to announce after {key.attempts} attempts, removing')
				self.monitoredKeys.monitoredKeys.pop(key.key)
		if monitor.announcedKeys or monitor.announcedKeysForecastKeys:
			self.clearSuccess.start()

	def keys(self):
		return self._values.keys()

	def values(self):
		return self._values.values()

	def items(self):
		return self._values.items()

	def __hash__(self):
		return hash(str(self.__class__.__name__))

	@Slot(KeyData)
	def keyAdded(self, data: KeyData):
		keys = data.keys
		if isinstance(keys, dict):
			keys = set().union(*data.keys.values())
		values = {key: data.sender[key] for key in keys}
		self.update(values)

	def __getitem__(self, item):
		if item in self.__plugins:
			return self.__plugins[item]
		return self._values[item]

	def __setitem__(self, key, value):
		if key not in self._values:
			self._values[key] = MultiSourceContainer(key)
			self.newKeys.publishKey(key)
		mergedValue = self._values[key]
		if value.source.name not in mergedValue:
			mergedValue.addValue(value.source, value)

	def update(self, values: dict):
		# log.debug(f'Updating {values}')
		with self.newKeys as muted:
			for key, value in values.items():
				self[key] = value
			if values:
				# toAnnouce = [self._values[value.key] for value in values]
				self.monitoredKeys.announce(list(values.values()))
				self.clearSuccess.start()

	def request(self, requester, item):
		if item in self._values:
			return self._values[item]
		else:
			if isinstance(item, CategoryItem):
				self.monitoredKeys.add(item, requester)
				return PlaceholderSignal(signal=self.monitoredKeys.signal, key=item)

	def getHourly(self, key, requester, source=None):
		if key in self._values and self._values[key].hourly:
			return self._values[key]
		else:
			self.monitoredKeys.add(key, requester, requires=True)
			return ForecastPlaceholderSignal(signal=self.monitoredKeys.requirementsSignal, key=key)

	def fromState(self, state: dict):
		for key in state:
			self._values[key] = state[key]

	@property
	def plugins(self) -> Plugins:
		return self.__plugins


@dataclass
class PlaceholderSignal:
	signal: Signal
	key: CategoryItem
	preferredSource: str = None


@dataclass
class ForecastPlaceholderSignal:
	signal: Signal
	key: CategoryItem
	preferredSource: str = None


ValueDirectory = PluginValueDirectory()

__all__ = ["PluginValueDirectory", "MultiSourceContainer", "ValueDirectory", 'MonitoredKey', 'PlaceholderSignal', 'ForecastPlaceholderSignal']
