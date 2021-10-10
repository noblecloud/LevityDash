import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cached_property
from operator import attrgetter
from typing import Dict, Iterable, List, Optional, Union

import requests
import socketio
import websocket
from PySide2.QtCore import QObject, QThread, QTimer, Signal, Slot

from src.api.errors import APIError, InvalidCredentials, RateLimitExceeded
from src.observations import Observation, ObservationDict, ObservationForecast, ObservationRealtime, MeasurementForecast
from src.utils import closest, Period

log = logging.getLogger(__name__)

__all__ = ['URLs', 'EndpointList', 'API']


@dataclass
class URLs:
	def __post_init__(self, *args, **kwargs):
		self.base = self.base.strip('/')
		for key in [key for key in self.__dir__() if not key.startswith('_') and key not in ['base', 'default']]:
			value = getattr(self, key)
			if isinstance(value, str):
				endpoint = value.strip('/')
				setattr(self, key, f'{self.base}/{endpoint}')

	@property
	def default(self):
		if hasattr(self, 'endpoint'):
			return self.endpoint
		return self.base

	def __repr__(self):
		return self.default

	def __str__(self):
		return self.default


class Messenger(QObject):
	signal: Signal = Signal(Observation)

	def __init__(self, *args, **kwargs):
		super(Messenger, self).__init__(*args, **kwargs)

	def push(self, message: Observation):
		self.signal.emit(message)


class SocketIOMessenger(QThread, Messenger):
	connected = Signal()
	disconnected = Signal()
	error_ocurred = Signal(object, name="errorOcurred")
	data_changed = Signal(str, name="dataChanged")
	station: 'API'

	url: str
	params: dict
	socketParams: dict

	def __init__(self, station: 'API', url: str, params: dict = {}, *args, **kwargs):
		self.url = url
		self.station = station
		self.params = params
		super(SocketIOMessenger, self).__init__(*args, **kwargs)
		self.socket.on("connect", self._connect)
		self.socket.on("disconnect", self._disconnect)
		self.socket.on('*', self._anything)

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
		log.warning('Catchall for SocketIO used')
		log.debug(data)

	def _connect(self):
		pass

	def _disconnect(self):
		pass


class WSMessenger(QThread, Messenger):
	urlBase = ''

	@property
	def url(self):
		return self.urlBase

	def __init__(self, parent=None):
		super(WSMessenger, self).__init__(parent)
		self.socket = websocket.WebSocketApp(self.url,
		                                     on_open=self.on_open,
		                                     on_message=self.on_message,
		                                     on_error=self.on_error,
		                                     on_close=self.on_close)

	def run(self):
		self.WS.run_forever()

	def begin(self):
		self.start()

	def end(self):
		self.socket.close()

	def on_open(self, ws):
		pass

	def on_message(self, ws, message):
		pass

	def on_error(self, ws, error: bytes):
		pass

	def on_close(self, ws):
		log.info(f'Socket {self.__class__.__name__}')
		print("### closed ###")

	def terminate(self):
		self.socket.close()


class EndpointList(list):

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

	def sort(self):
		super(EndpointList, self).sort(key=attrgetter('period'))

	def grab(self, value: timedelta, sensitivity: timedelta = timedelta(minutes=5), forecastOnly: bool = False) -> ObservationDict:

		if isinstance(value, int):
			value = timedelta(seconds=value)

		if isinstance(sensitivity, int):
			sensitivity = timedelta(seconds=sensitivity)

		selection = [obs for obs in self if obs.period.total_seconds() > 0] if forecastOnly else self
		grabbed = selection[min(range(len(selection)), key=lambda i: abs(selection[i].period - value))]

		low = value - sensitivity
		high = value + sensitivity
		if low < grabbed.period < high:
			return grabbed
		else:
			raise IndexError(f'{value} with sensitivity of {sensitivity} not found')

	def selectBest(self, minTimeframe: timedelta,
	               minPeriod: timedelta = timedelta(minutes=1),
	               maxPeriod: timedelta = timedelta(hours=4)) -> Optional[ObservationForecast]:
		selection = [obs for obs in self if minPeriod <= obs.period <= maxPeriod and obs.timeframe > minTimeframe]
		if selection:
			return selection[min(range(len(selection)), key=lambda i: selection[i].period)]
		return None

	@property
	def hourly(self) -> Optional[ObservationForecast]:
		try:
			return self.grab(Period.Hour, sensitivity=Period.QuarterHour, forecastOnly=True)
		except IndexError:
			return None

	@property
	def realtime(self) -> Optional[ObservationRealtime]:
		try:
			return [i for i in self if i.period == timedelta()][0]
		except IndexError:
			return None

	@property
	def daily(self) -> Optional[ObservationForecast]:
		try:
			return self.grab(Period.Day, sensitivity=Period.Hour, forecastOnly=True)
		except IndexError:
			return None


class API:
	_params: Dict = {}
	_headers: Dict = {}
	_baseParams: Dict = {}
	_baseHeaders: Dict[str, str] = {}
	_urls: URLs
	_endpoints: EndpointList[ObservationDict]
	_realtime: Optional[ObservationRealtime]

	def __init__(self):
		self._endpoints = EndpointList()
		annotations = {k: v for d in [t.__annotations__ for t in self.__class__.mro() if issubclass(t, API) and t != API] for k, v in d.items()}
		# annotations.pop('_realtime')
		self._realtime = None
		for key, value in annotations.items():
			if issubclass(value, ObservationDict):
				o = value(source=self)
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

	@property
	def name(self) -> str:
		return self.__class__.__name__

	# if isinstance(self._dataClass, dict):
	# 	for key, value in self._dataClass.items():
	# 		setattr(self, f'_{key}', value())
	# elif isinstance(self._dataClass, type):
	# 	self._data = self._dataClass()

	# def __contains__(self, item):
	# 	if isinstance(item, str):
	#

	def __getitem__(self, item: Union[str, datetime, timedelta]):
		if isinstance(item, timedelta):
			item = datetime.now() + item
		if isinstance(item, datetime):
			times = closest([a.time if isinstance(a, Observation) else a['time'][0] for a in self._endpoints], item)

		if isinstance(item, str) and item in self.keys:
			a = [endpoint[item] if isinstance(endpoint[item], Iterable) else [endpoint[item]] for endpoint in self._endpoints if item in endpoint]
			result = MeasurementForecast(self, item, [x for y in a for x in y])
			result.sort()
			return result

	@property
	def keys(self):
		keys = set()
		for endpoint in self._endpoints:
			keys |= set(endpoint.keys())
		return keys

	def sharedKeys(self, *periods: list[Union[Period, int, timedelta]]):
		keys = self.keys
		for endpoint in [self._endpoints.grab(period) for period in periods]:
			keys.intersection_update(set(endpoint.keys()))
		return list(keys)

	def getData(self, endpoint: str = None, params: dict = None, headers: dict = {}) -> dict:
		params = self.__combineParameters(params)
		headers = self.__combineHeaders(headers)

		url = self._urls.default if endpoint is None else endpoint
		request = requests.get(url, params=params, headers=headers)

		if request.status_code == 200:
			log.info('Updated')
			return self._normalizeData(request.json())
		elif request.status_code == 429:
			log.error('Rate limit exceeded', request.content)
			raise RateLimitExceeded
		elif request.status_code == 401:
			log.error('Invalid credentials', request.content)
			raise InvalidCredentials
		elif request.status_code == 404:
			log.error(f'404: Invalid URL: {request.url}')
		else:
			log.error('API Error', request.content)
			raise APIError(request)

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
				log.error(f'Path: {data} is invalid')

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

	def connectSocket(self):
		self.socket.signal.connect(self.socketUpdate)

	@Slot(dict)
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
