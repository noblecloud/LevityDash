import time

import uuid

from dataclasses import dataclass, field

from PySide2.QtCore import QMutex, QObject, QThread, QTimer, Signal
from PySide2.QtWidgets import QApplication

from src import logging
from datetime import timedelta
from functools import cached_property
from typing import Any, NamedTuple

import src.api as api
from src.api.baseAPI import Container, PlaceholderContainer
from src.catagories import CategoryDict, CategoryEndpointDict, CategoryItem
import src.config as config
from src import config
from src.utils import Period

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

__all__ = ["MergedEndpoint", "MergedValue", "endpoints"]


class MergedValue(dict):
	key: CategoryItem
	period: Period
	value: Any
	_value: Any
	preferredSource: str
	timeOffset: timedelta

	def __init__(self, key, value=None, selected=None, timeOffset=None):
		self.key = key
		self.preferredSource = selected
		self.timeOffset = timeOffset

		super(MergedValue, self).__init__(value if value else {})

	def __str__(self):
		return self.value.__str__()

	def __getattr__(self, item):
		attr = getattr(self.__getattribute__('value').value, item, None)
		if attr is None:
			if item in dir(self):
				return self.__getattribute__(item)
			else:
				return self.default.__getattr__(item)
		return attr.value

	# def __getattribute__(self, item):
	# 	try:
	# 		return dict.__getattribute__(self, item)
	# 	except AttributeError:
	# 		return getattr(self.value, item)
	# 	super(MergedValue, self).__getattribute__(item)

	def __setattr__(self, key, value):
		if key in self.__annotations__:
			self.__dict__[key] = value
		else:
			self.value.__setattr__(key, value)

	@property
	def value(self) -> Container:
		if self.preferredSource and self.preferredSource in self.keys():
			value = self[self.preferredSource]
		else:
			value = self.default
		periods = ['now', 'minute', 'hour', 'day', 'week', 'month', 'year']
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
		# if self.timeOffset and period != 0:
		# 	pass

		return value

	@property
	def hourly(self) -> 'MeasurementTimeSeries':
		if self.value.api.hourly is not None and self.key in self.value.api.hourly.observations:
			if endpoints.mutex.tryLock(2000):
				value = self.value.hourly
				endpoints.mutex.unlock()
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
	def default(self):
		sections = [i for i in config.api.values() if i.getboolean('enabled') and i.name in self]
		for i in self.key[::-1]:
			for section in sections:
				if 'defaultFor' in section and i in section['defaultFor']:
					return self[section.name]
		for section in sections:
			if section.name in endpoints.endpoints and endpoints[section.name] in self:
				return self[section.name]
		return list(self.values())[0]

	def addValue(self, endpoint, value):
		self[endpoint.name] = value

	def toDict(self):
		state = {'key': str(self.key)}
		if self.preferredSource:
			state['preferredSource'] = self.preferredSource
		if self.period:
			state['period'] = self.period
		if self.timeOffset:
			state['timeOffset'] = self.timeOffset
		return state

	@property
	def valueChanged(self):
		return self.default.valueChanged


@dataclass
class MonitoredKey:
	key: CategoryItem = field(init=True)
	period: Period = field(init=False)
	source: str = field(init=False)
	value: MergedValue = field(init=False)
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
				key.value = value
				self.signal.emit(key)
				key.attempts += 1
				self.announcedKeys[key.key] = self.monitoredKeys.pop(key.key)
			if key := self.monitoredKeysForecastKeys.get(value.key, False):
				key.value = value
				if value.forecast:
					self.requirementsSignal.emit(key)
					log.info(f'Announcing {key.key} with forecast')
					key.attempts += 1
				self.announcedKeysForecastKeys[key.key] = self.monitoredKeysForecastKeys.pop(key.key)

	# if self.announcedKeys or self.announcedKeysForecastKeys:
	# self.clearSuccess.start()

	def __contains__(self, item):
		return item in self.monitoredKeys

	def hasRequirements(self, value: MergedValue) -> bool:
		return value.key in self.monitoredKeysForecastKeys and any(container.forecast for container in value.values())


class MergedEndpoint(QObject):
	endpoints = {}
	__singleton = None
	categories = None
	_values = {}

	def __new__(cls, *args, **kwargs):
		if cls.__singleton is None:
			cls.__singleton = super(MergedEndpoint, cls).__new__(cls, *args, **kwargs)
		return cls.__singleton

	def __init__(self):
		super(MergedEndpoint, self).__init__()
		self.mutex = QMutex()
		self.monitoredKeys = MonitoredKeySignalWrapper(self)
		self.newKeys = newKeysSignalWrapper()
		self.clearSuccess = QTimer(singleShot=True, interval=1000, timeout=self.clearSuccessful)

	def clearSuccessful(self):
		monitor = self.monitoredKeys
		monitor.announcedKeys = {key: value for key, value in monitor.announcedKeys.items() if not value.success}
		monitor.announcedKeysForecastKeys = {key: value for key, value in monitor.announcedKeysForecastKeys.items() if not value.success}

		for key in monitor.announcedKeys.values():
			key.attempts += 1
			monitor.signal.emit(key)
			log.info(f'Announcing {key.key}')
		for key in monitor.announcedKeysForecastKeys.values():
			if key.value.forecast:
				key.attempts += 1
				monitor.requirementsSignal.emit(key)
				log.info(f'Announcing {key.key} with forecast')
			if key.attempts > 5:
				log.info(f'{key.key} failed to announce after {key.attempts} attempts')
		if monitor.announcedKeys or monitor.announcedKeysForecastKeys:
			self.clearSuccess.start()

	def keys(self):
		return self._values.keys()

	def values(self):
		return self._values.values()

	def items(self):
		return self._values.items()

	def loadEndpoints(self):
		# self.newKeys.blockSignals(True)
		if 'AmbientWeather' not in self.endpoints:
			if config.api.getboolean('AmbientWeather', 'enabled'):
				api.ambientWeather.AWStation(callback=self.onAPIFinishLoading, mainEndpoint=self)

		if 'WeatherFlow' not in self.endpoints:
			if config.api.getboolean('WeatherFlow', 'enabled'):
				api.weatherFlow.WFStation(callback=self.onAPIFinishLoading, mainEndpoint=self)

		if 'OpenMeteo' not in self.endpoints:
			if config.api.getboolean('OpenMeteo', 'enabled'):
				api.OpenMeteo(callback=self.onAPIFinishLoading, mainEndpoint=self)

		if 'TomorrowIO' not in self.endpoints:
			if config.api.getboolean('TomorrowIO', 'enabled'):
				api.TomorrowIO(callback=self.onAPIFinishLoading, mainEndpoint=self)

		# for endpoint in self.endpoints._values():
		# 	endpoint.keySignal.added.connect(self.keyAdded)
		# 	for key in endpoint.keys():
		# 		self[key] = endpoint.containerValue(key)
		# self.newKeys.blockSignals(False)

		self.categories = CategoryEndpointDict(self, self._values, None)
		self.newKeys.newKeys.emit(list(self.keys()))

	def onAPIFinishLoading(self, api):
		self.endpoints[api.name] = api
		log.info(f'{api.name} loaded')
		self.update(api.containerValues())
		self.clearSuccess.start()

	def __hash__(self):
		return hash(str(self.__class__.__name__))

	def keyAdded(self, values):
		for value in values:
			self._values[value.key] = value

	def __getitem__(self, item):
		if item in self.endpoints:
			return self.endpoints[item]
		return super(MergedEndpoint, self).__getitem__(item)

	def __setitem__(self, key, value):
		if key not in self._values:
			self._values[key] = MergedValue(key)
		mergedValue = self._values[key]
		mergedValue.addValue(value.api, value)

	def update(self, values: dict):
		log.debug(f'Updating {values}')
		for value in values:
			self[value.key] = value
		if values:
			toAnnouce = [self._values[value.key] for value in values]
			self.monitoredKeys.announce(toAnnouce)

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
# period: int = None


endpoints = MergedEndpoint()


class MergedEndpointThread(QThread):
	def __init__(self):
		super(MergedEndpointThread, self).__init__()
		self.endpoints = MergedEndpoint()

	def run(self):
		self.endpoints.loadEndpoints()

# thread = MergedEndpointThread()
# endpoints = thread.endpoints
# thread.start(priority=QThread.LowPriority)
# thread.
