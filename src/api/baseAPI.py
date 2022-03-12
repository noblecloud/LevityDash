import random
from measurement.base import classproperty

import asyncio

from src import config, logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cached_property
from operator import attrgetter
from threading import Thread
from types import GenericAlias
from typing import Callable, Dict, Iterable, List, Optional, Union

import requests
import socketio
import websocket
from PySide2.QtCore import QObject, QRunnable, QThread, QThreadPool, QTimer, Signal, Slot
from PySide2.QtNetwork import QHostAddress, QNetworkDatagram, QUdpSocket

from src.catagories import CategoryItem
from src.api.errors import APIError, InvalidCredentials, RateLimitExceeded
from src.observations import Observation, ObservationDict, ObservationForecast, ObservationRealtime, MeasurementTimeSeries
from src.utils import APIUpdateSignaler, closest, Period

__all__ = ['URLs', 'EndpointList', 'API']

apiLog = logging.getLogger(f'API')

@dataclass
class URLs:
	def __post_init__(self, *args, **kwargs):
		self.base = self.base.strip('/')
		for key in [key for key in self.__dir__() if not key.startswith('_') and key not in ['base', 'default']]:
			value = getattr(self, key)
			if isinstance(value, str):
				endpoint = value.strip('/')
				setattr(self, key, f'{self.base}/{endpoint}')
		if self._forecastGrouped:
			if self._hasHourly:
				self.hourly = self.forecast
			if self._hasDaily:
				self.daily = self.forecast
			if self._hasMinutely:
				self.minutely = self.forecast

	def __init_subclass__(cls, realtime=False, forecast=None,
	                      hourly=True, daily=True, minutely=False,
	                      forecastGrouped=True, **kwargs):

		cls._hasRealtime = realtime

		if forecast is not None and not forecast:
			hourly = False
			daily = False
			minutely = False
		elif forecast is None:
			forecast = bool(hourly or daily or minutely)
		else:
			forecast = False

		cls._forecastGrouped = forecastGrouped if forecast else None
		if cls._forecastGrouped:
			forecast = True

		cls._hasForecast = forecast
		cls._hasHourly = hourly
		cls._hasDaily = daily
		cls._hasMinutely = minutely

		super(URLs, cls).__init_subclass__(**kwargs)

	@property
	def default(self):
		if hasattr(self, 'endpoint'):
			return self.endpoint
		return self.base

	def __repr__(self):
		return self.default

	def __str__(self):
		return self.default

	@property
	def forecastEnabled(self) -> bool:
		return any([self._hasForecast, self._hasHourly, self._hasDaily, self._hasMinutely])

	@property
	def realtimeEnabled(self) -> bool:
		return self._hasRealtime

	@property
	def hasHourly(self) -> bool:
		return self._hasHourly

	@property
	def hasDaily(self) -> bool:
		return self._hasDaily

	@property
	def hasMinutely(self) -> bool:
		return self._hasMinutely

	@property
	def forecastGrouped(self) -> bool:
		return self._forecastGrouped


class Socket(QObject):
	api: 'API'
	relay = Signal(dict)

	def __init__(self, api: 'API', *args, **kwargs):
		self.api = api
		self.log = logging.getLogger(f'{api.name}.{self.__class__.__name__}')
		super(Socket, self).__init__(*args, **kwargs)

	def push(self, message):
		self.relay.emit(message)

	def begin(self):
		self.log.warning(f'Socket.begin() is not implemented for {self.__class__.__name__,}')


class UDPSocket(Socket):
	last: QNetworkDatagram
	socket: QUdpSocket
	port: int

	def __init__(self, port: Optional[int] = None, address: Optional[str] = None, *args, **kwargs):
		self.address = QHostAddress(address)
		if port is not None:
			self.port = port
		super(UDPSocket, self).__init__(*args, **kwargs)
		self.socket = QUdpSocket(self)

	def connectUPD(self):
		self.socket.bind(address=self.address, port=self.port)

		self.log.debug('Listening UDP')
		self.socket.readyRead.connect(self.receiveUDP)
		self.last = self.socket.receiveDatagram(self.socket.pendingDatagramSize())

	def receiveUDP(self):
		while self.socket.hasPendingDatagrams():
			datagram = self.socket.receiveDatagram(self.socket.pendingDatagramSize())
			if self.last.data() != datagram.data():
				self.last = datagram
				self.parseDatagram(datagram)

	def begin(self):
		print('socketad-=-------------------------------------------------------------------------------------------------------------------------------------------------la')
		self.connectUPD()


class SocketIO(QThread):
	url: str
	params: dict
	socketParams: dict
	relay = Signal(dict)

	def __init__(self, params: dict = {}, *args, **kwargs):
		super(SocketIO, self).__init__()
		if 'api' in kwargs:
			self.api = kwargs['api']
		self.params = params
		self.socket.on("connect", self._connect)
		self.socket.on("disconnect", self._disconnect)
		self.socket.on('*', self._anything)

	def push(self, message):
		self.relay.emit(message)

	@property
	def url(self):
		return self.api.urls.socket

	@cached_property
	def socket(self):
		return socketio.Client(
			reconnection=True,
			reconnection_attempts=3,
			reconnection_delay=5,
			reconnection_delay_max=5
		)

	def run(self):
		self.socket.connect(url=self.url, **self.socketParams)

	def begin(self):
		self.start()

	def end(self):
		self.socket.disconnect()

	def _anything(self, data):
		self.log.warning('Catchall for SocketIO used')
		self.log.debug(data)

	def _connect(self):
		pass

	def _disconnect(self):
		pass


class Websocket(QThread, Socket):
	urlBase = ''

	@property
	def url(self):
		return self.urlBase

	def __init__(self, *args, **kwargs):
		super(Websocket, self).__init__(*args, **kwargs)
		self.socket = websocket.WebSocketApp(self.url,
		                                     on_open=self._open,
		                                     on_data=self._data,
		                                     on_message=self._message,
		                                     on_error=self._error,
		                                     on_close=self._close)

	def run(self):
		self.socket.run_forever()

	def begin(self):
		self.start()

	def end(self):
		self.socket.close()

	def _open(self, ws):
		self.log.info(f'Socket {self.__class__.__name__}')
		print("### opened ###")

	def _message(self, ws, message):
		pass

	def _data(self, ws, data):
		pass

	def _error(self, ws, error: bytes):
		pass

	def _close(self, ws):
		self.log.info(f'Socket {self.__class__.__name__}')
		print("### closed ###")

	def terminate(self):
		self.socket.close()


class EndpointList(list):

	def __init__(self, *args, **kwargs):
		super(EndpointList, self).__init__(*args, **kwargs)

	def insert(self, value: ObservationDict):
		if not isinstance(value, ObservationDict):
			raise ValueError(f"Can not add this type: {type(value)}")
		self.append(value)

	def append(self, value):
		super(EndpointList, self).append(value)
		self.sort()

	def extend(self, value: Iterable):
		super(EndpointList, self).extend(value)
		self.sort()

	def __add__(self, other):
		super(EndpointList, self).__add__(other)
		self.sort()

	def __iadd__(self, other):
		super(EndpointList, self).__iadd__(other)
		self.sort()

	def sort(self, key: object = None, reverse: object = False) -> None:
		super(EndpointList, self).sort(key=attrgetter('period'))

	def grab(self, value: timedelta, sensitivity: timedelta = timedelta(minutes=5), forecastOnly: bool = False) -> ObservationDict:

		if isinstance(value, int):
			value = timedelta(seconds=value)

		if isinstance(sensitivity, int):
			sensitivity = timedelta(seconds=sensitivity)

		selection = [obs for obs in self if obs.period.total_seconds() > 0] if forecastOnly else self
		if selection:
			grabbed = selection[min(range(len(selection)), key=lambda i: abs(selection[i].period - value))]

			low = value - sensitivity
			high = value + sensitivity
			if low < grabbed.period < high:
				return grabbed
			else:
				raise IndexError(f'{value} with sensitivity of {sensitivity} not found')
		else:
			raise IndexError(f'{value} with sensitivity of {sensitivity} not found')

	def selectBest(self, minTimeframe: timedelta,
	               minPeriod: timedelta = timedelta(minutes=1),
	               maxPeriod: timedelta = timedelta(hours=4)) -> Optional[ObservationForecast]:
		selection = [obs for obs in self if minPeriod <= obs.period <= maxPeriod and obs.timeframe > minTimeframe]
		if selection:
			return selection[min(range(len(selection)), key=lambda i: selection[i].period)]
		return None

	@cached_property
	def hourly(self) -> Optional[ObservationForecast]:
		try:
			return self.grab(Period.Hour, sensitivity=Period.QuarterHour, forecastOnly=True)
		except IndexError:
			return None

	@cached_property
	def realtime(self) -> Optional[ObservationRealtime]:
		try:
			return [i for i in self if i.period == timedelta()][0]
		except IndexError:
			return None

	@cached_property
	def daily(self) -> Optional[ObservationForecast]:
		try:
			return self.grab(Period.Day, sensitivity=Period.Hour, forecastOnly=True)
		except IndexError:
			return None


def keyProperty(endpoint, key: str):
	def getter(self):
		return endpoint[key]

	return property(getter)


class Container:
	api: 'API'
	key: CategoryItem
	now: ObservationRealtime
	daily: MeasurementTimeSeries
	hourly: Optional[MeasurementTimeSeries]
	forecast: Optional[MeasurementTimeSeries]
	title: str

	def __init__(self, api: 'API', key: CategoryItem):
		self.api = api
		self.key = key

	# keys = set()
	# for endpoint in self.api.endpoints:
	# 	if hasattr(endpoint, 'observationKeys'):
	# 		keys |= set(endpoint.observationKeys())
	# 	else:
	# 		keys.update(list(endpoint.keys()))
	# keys = [k for k in keys if self.key > k.category]

	def __getattr__(self, item):
		if item in super(Container, self).__getattribute__('__annotations__') or item == '__annotations__':
			return super(Container, self).__getattribute__(item)
		return getattr(super(Container, self).__getattribute__('value'), item)

	def __setattr__(self, key, value):
		if key in self.__annotations__:
			super(Container, self).__setattr__(key, value)
		else:
			self.value.__setattr__(key, value)

	def __repr__(self):
		return f'{self.api.name}({self.key[-1]}: {self.value})'

	def __str__(self):
		return str(self.value)

	def __hash__(self):
		return hash(self.key)

	def toDict(self):
		return {'key': self.key, 'value': self.value}

	def __eq__(self, other):
		if isinstance(other, str):
			return self.name == other
		else:
			return super(Container, self).__eq__(other)

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
			return self.hourly[0]
		elif self.daily is not None:
			return self.daily[0]
		return None

	@property
	def now(self):
		if self.api.realtime:
			value = self.api.realtime[self.key]
			if value == {}:
				self.log.warning(f'{self.api.name}({self.key}) is an empty dictionary')
				return None
			return value
		return None

	@property
	def hourly(self):
		if self.api.hourly:
			value = self.api.hourly[self.key]
			if value == {}:
				self.log.warning(f'{self.api.name}() is an empty dictionary')
				return None
			return value
		return None

	@property
	def daily(self):
		if self.api.daily:
			value = self.api.daily[self.key]
			if value == {}:
				self.log.warning(f'{self.api.name}({self.key}) is an empty dictionary')
				return None
			return value
		return None

	@property
	def forecast(self):
		if self.hourly is not None:
			return self.hourly
		elif self.daily is not None:
			return self.daily
		return None

	def customTimeFrame(self, timeframe: timedelta, sensitivity: timedelta = timedelta(minutes=1)) -> Optional[MeasurementTimeSeries]:
		try:
			return self.api.get(self.key, timeframe)
		except KeyError:
			return None


class PlaceholderContainer(Container):

	def __init__(self, key: CategoryItem):
		super().__init__(api=None, key=key)

	@property
	def value(self):
		return 'N/A'

	@property
	def title(self):
		return str(self.key).title()


class KeyTracker(QObject):
	__added = Signal(dict)
	__removed = Signal(dict)
	__data: dict[timedelta, set[CategoryItem]]

	def __init__(self, api: 'API'):
		self.api = api
		self.__data = {}
		super(KeyTracker, self).__init__()
		self.__timer = QTimer(singleShot=True, interval=200)
		self.__timer.timeout.connect(self.__emitChange)

	@Slot(KeyData)
	def addBulk(self, data: KeyData):
		sender = data.sender.period
		keys = data.keys
		if sender not in self.__data:
			self.__data[sender] = set()
		self.__data[sender].update(keys)
		self.__timer.start()

	def remove(self, key: CategoryItem):
		if key in self.keys:
			self.removed.emit(self.keys[key])
			del self.keys[key]

	def __emitChange(self):
		data = KeyData(self.api, self.__data)
		self.__added.emit(data)
		self.__data = {}

	def connectSlot(self, slot: Slot):
		self.__added.connect(slot)

	def disconnectSlot(self, slot: Slot):
		try:
			self.__added.disconnect(slot)
		except TypeError:
			pass



class Worker(QRunnable):

	def __init__(self, owner, func, **kwargs):
		super(Worker, self).__init__()
		self.owner = owner
		self.func = func
		self.kwargs = kwargs

	def run(self):
		try:
			self.func(self.owner, **self.kwargs)
		except APIError as e:
			self.log.error(f'API Error: {e}')


def asRunnable(func):
	def wrapper(value, **kwargs):
		worker = Worker(value, func, **kwargs)
		QThreadPool.globalInstance().start(worker)

	return wrapper


def tryConnection(func):
	def wrapper(*value, **kwargs):
		try:
			func(*value, **kwargs)
		except APIError as e:
			value[0].log.error(e)

	return wrapper


class WorkerSignals(QObject):
	finished = Signal(dict)
	error = Signal(tuple)
	result = Signal(dict)


class Worker(QRunnable):

	def __init__(self, owner, func, *args, **kwargs):
		super(Worker, self).__init__()
		self.owner = owner
		self.func = func
		self.args = args
		self.kwargs = kwargs
		self.signals = WorkerSignals()

	def run(self):
		print(f'Running {self.func.__name__} for {self.owner}')
		self.func(self.owner)


class ScheduledEvent:
	stagger: bool
	staggerAmount: timedelta
	when: datetime
	interval: timedelta
	func: Callable
	args: tuple
	kwargs: dict
	timer: asyncio.TimerHandle

	def __init__(self,
	             interval: timedelta,
	             func: Callable,
	             arguments: tuple = None,
	             keywordArguments: dict = None,
	             stagger: bool = None,
	             staggerAmount: timedelta = None,
	             fireImmediately: bool = True,
	             singleShot: bool = False,
	             pool=None):

		if arguments is None:
			arguments = ()
		if keywordArguments is None:
			keywordArguments = {}
		if stagger is None:
			stagger = False
		if staggerAmount is None:
			staggerAmount = timedelta(minutes=2.5)
		self.__interval = interval

		self.__func = func
		self.__args = arguments
		self.__kwargs = keywordArguments
		self.__stagger = stagger
		self.__staggerAmount = staggerAmount
		self.__singleShot = singleShot
		self.__fireImmediately = fireImmediately

	def start(self, immediately: bool = False, startTime: datetime = None):
		self.__fireImmediately = immediately
		self.__run(startTime)

	def stop(self):
		self.timer.stop()

	def reschedule(self, interval: timedelta = None, fireImmediately: bool = False):
		self.__fireImmediately = fireImmediately
		if interval is not None:
			self.interval = interval
		self.__run()

	@property
	def when(self) -> datetime:
		when = datetime.now() + self.__interval
		if self.__stagger:
			seconds = self.__staggerAmount.seconds * (random() * 2 - 1)
			loopTime = asyncio.get_event_loop().time()
			if seconds + loopTime < 0:
				seconds = self.__staggerAmount.seconds * random()
			when += timedelta(seconds=seconds)
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

	def __run(self, startTime: datetime = None):
		loop = asyncio.get_event_loop()
		when = self.when if startTime is None else startTime
		_when = (when - datetime.now()).total_seconds()
		self.timer = loop.call_soon(self.__fire) if self.fireImmediately else loop.call_at(_when, self.__fire)
		print(f'Scheduled {self.__func.__name__} to run at {when.strftime("%-I:%M:%S%p").lower()}')

	def __fire(self):
		asyncio.create_task(self.__func(*self.__args, **self.__kwargs))
		print(f'{self.__func.__name__} fired!')
		if not self.__singleShot:
			self.__run()

	@property
	def __timeTo(self) -> float:
		self.timer.when()


class API:
	_params: Dict = {}
	_headers: Dict = {}
	_baseParams: Dict = {}
	_baseHeaders: Dict[str, str] = {}
	_urls: URLs
	_endpoints: EndpointList[ObservationDict]
	_realtime: Optional[ObservationRealtime]
	_hourly: Optional[ObservationForecast]
	_daily: Optional[ObservationForecast]

	_realtimeRefreshTimer: QTimer
	_realtimeRefreshInterval: Optional[timedelta] = timedelta(minutes=1)
	_forecastRefreshTimer: QTimer
	_forecastRefreshInterval: Optional[timedelta] = timedelta(minutes=15)

	def __init__(self, mainEndpoint, callback: Callable = None):
		super(API, self).__init__()
		self.main = mainEndpoint
		self.containers = {}
		apiLog = logging.getLogger(f'API')

		self.log = logging.getLogger(f'API.{self.name}')
		self.log.setLevel(apiLog.level)
		self._endpoints = EndpointList()
		self.keySignal = KeyTracker(self)
		annotations = {k: v for d in [t.__annotations__ for t in self.__class__.mro() if issubclass(t, API) and t != API] for k, v in d.items()}
		# annotations.pop('_realtime')
		self._realtime = None
		for key, value in annotations.items():
			if not isinstance(value, type):
				continue
			if not isinstance(value, GenericAlias) and issubclass(value, ObservationDict):
				o = value(api=self)
				o.signals.valueAdded.connect(self.keySignal.add)
				self._endpoints.append(o)
			# setattr(self, key, o)
			elif issubclass(value, URLs):
				try:
					self._urls = value()
				except TypeError:
					try:
						self._urls = value(**{x: getattr(self, f'_{x}') for x in value.__init__.__annotations__.keys()})
					except AttributeError:
						pass
		if self._urls.realtimeEnabled:
			self._realtimeRefreshTimer = QTimer()
			if isinstance(self._realtimeRefreshInterval, int):
				self._realtimeRefreshTimer.setInterval(self._realtimeRefreshInterval * 60 * 1000)
			else:
				self._realtimeRefreshTimer.setInterval(self._realtimeRefreshInterval.total_seconds() * 1000)
			self._realtimeRefreshTimer.timeout.connect(self.getRealtime)
			self._realtimeRefreshTimer.start()
		if self._urls.forecastEnabled and self._urls.forecastGrouped:
			self._forecastRefreshTimer = QTimer()
			if isinstance(self._forecastRefreshInterval, int):
				self._forecastRefreshTimer.setInterval(self._forecastRefreshInterval * 60 * 1000)
			else:
				self._forecastRefreshTimer.setInterval(self._forecastRefreshInterval.total_seconds() * 1000)
			self._forecastRefreshTimer.timeout.connect(self.getForecast)
			self._forecastRefreshTimer.start()

		if callback:
			callback(self)

	@property
	def name(self) -> str:
		return self.__class__.__name__

	@property
	def endpoints(self) -> EndpointList[ObservationDict]:
		return self._endpoints

	def __hash__(self):
		return hash(self.name)

	def __getitem__(self, item):
		if isinstance(item, CategoryItem):
			if item not in self.containers:
				self.containers[item] = Container(self, item)
			return self.containers[item]
		return self._endpoints[item]

	def values(self):
		pass

	def items(self):
		items = {}
		for key in self.allKeys():
			items[key] = Container(self, key)
		# item = {}
		# for endpoint in self._endpoints:
		# 	try:
		# 		item[endpoint.period] = endpoint[key]
		# 	except KeyError:
		# 		pass
		# items[key] = item
		return items

	def get(self, key: CategoryItem, timeframe: timedelta = Period.Realtime) -> ObservationDict:
		endpoint = self.endpoints.grab(timeframe)
		if not endpoint:
			raise IndexError(f'No endpoint found for {timeframe}')
		return endpoint[key]

	# if isinstance(self._dataClass, dict):
	# 	for key, value in self._dataClass.items():
	# 		setattr(self, f'_{key}', value())
	# elif isinstance(self._dataClass, type):
	# 	self._data = self._dataClass()

	# def __contains__(self, item):
	# 	if isinstance(item, str):
	#

	def __getitem__(self, item: Union[str, datetime, timedelta]):
		# if item is a timedelta:
		if isinstance(item, timedelta):
			# add the current date to the item
			item = datetime.now() + item
		# if the item is a datetime:
		if isinstance(item, datetime):
			# find the observation that is the closest to the item
			# TODO: Fix this
			times = closest([a.time if isinstance(a, Observation) else a['time'][0] for a in self._endpoints], item)

		# get the value for all the endpoints
		if isinstance(item, (str, CategoryItem)):
			if item in self:
				return Container(self, item)
			elif any(item in endpoint.categories for endpoint in self._endpoints):
				return {endpoint.period: endpoint[item] for endpoint in self._endpoints if item in endpoint.categories}

	def containerValue(self, key: str):
		return Container(self, key)

	def containerValues(self) -> Dict[CategoryItem, Container]:
		return {key: Container(self, key) for key in self.allKeys()}

	def keys(self):
		keys = set()
		for endpoint in self._endpoints:
			keys |= set(endpoint.keys())
		return keys

	def allKeys(self):
		keys = set()
		for endpoint in self._endpoints:
			if hasattr(endpoint, 'observationKeys'):
				keys |= set(endpoint.observationKeys())
			else:
				keys.update(list(endpoint.keys()))
		return list(keys)

	def __contains__(self, item):
		if not isinstance(item, CategoryItem):
			item = CategoryItem(item)
		return any(item in endpoint for endpoint in self._endpoints)

	def sharedKeys(self, *periods: list[Union[Period, int, timedelta]]):
		keys = self.keys
		for endpoint in [self._endpoints.grab(period) for period in periods]:
			keys.intersection_update(set(endpoint.keys()))
		return list(keys)

	def getData(self, endpoint: str = None, params: dict = None, headers: dict = {}) -> dict:
		params = self.__combineParameters(params)
		headers = self.__combineHeaders(headers)

		url = self._urls.default if endpoint is None else endpoint
		try:
			request = requests.get(url, params=params, headers=headers, timeout=10)

		# TODO: Add retry logic
		except requests.exceptions.ConnectionError:
			self.log.error('ConnectionError')
			return
		except requests.exceptions.Timeout:
			self.log.error(f'{self.name} request timed out for {url}')
			return

		if request.status_code == 200:
			self.log.info(f'{self.name} request successful for {url}')
			self.log.debug(f'Returned: {str(request.json())[:300]} ... ')
			return self._normalizeData(request.json())
		elif request.status_code == 429:
			self.log.error('Rate limit exceeded', request.content)
			raise RateLimitExceeded
		elif request.status_code == 401:
			self.log.error('Invalid credentials', request.content)
			raise InvalidCredentials
		elif request.status_code == 404:
			self.log.error(f'404: Invalid URL: {request.url}')
		else:
			self.log.error('API Error', request.content)
			raise APIError(request)

	async def getData(self, endpoint: str = None, params: dict = None, headers: dict = {}) -> dict:
		loop = asyncio.get_event_loop()
		return await loop.run_in_executor(None, self.__getData, endpoint, params, headers)

	def hasForecastFor(self, item: str) -> bool:
		return any([item in endpoint.keys() and endpoint.isForecast for endpoint in self._endpoints])

	def loadData(self, data: Union[str, dict]):
		from json import load
		from os.path import exists
		if isinstance(data, str):
			if exists(data):
				with open(data, 'r') as fp:
					return self._normalizeData(load(fp))
			else:
				self.log.error(f'Path: {data} is invalid')

		return self._normalizeData(data)

	def _normalizeData(self, rawData):
		return rawData

	def __combineParameters(self, params: dict = None) -> dict:
		params = {} if params is None else params
		params = {**self._baseParams, **self._params, **params}
		return params

	def __combineHeaders(self, headers: dict = None) -> dict:
		headers = {} if headers is None else headers
		headers = {**self._baseHeaders, **self._headers, **headers}
		return headers

	@property
	def urls(self) -> URLs:
		return self._urls

	def socketUpdate(self, data: dict):
		data = self._normalizeData(data)
		self.realtime.update(data)

	@property
	def realtime(self):
		if self._realtime is None:
			self._realtime = self._endpoints.realtime
		return self._realtime

	@property
	def hourly(self):
		return self._endpoints.hourly

	@property
	def daily(self):
		return self._endpoints.daily

	@classmethod
	def getParent(cls):
		return cls.mro()[1]

	@property
	def state(self):
		return self.__class__.__name__
