from src import logging
from datetime import datetime
from typing import Optional, Union
from urllib.parse import urlencode

from src.observations import AWObservationRealtime
from src.api.baseAPI import API, SocketIO, tryConnection, URLs, Websocket
from src.api.errors import InvalidCredentials, RateLimitExceeded, APIError
from src import config
from src.observations import ObservationRealtime
from src.utils import formatDate, Logger

log = logging.getLogger(__name__)


class AWURLs(URLs, realtime=True, forecast=False):
	base = 'https://api.ambientweather.net/v1'
	device = 'devices'
	socket = f"?{urlencode({'api': 1, 'applicationKey': config.api.aw['appKey']})}"
	realtime = device


class AWMessenger(SocketIO):
	socketParams = {'transports': ['websocket']}
	_device: str

	def __init__(self, device: Optional[str] = None, *args, **kwargs):
		super(AWMessenger, self).__init__(*args, **kwargs)
		if device is not None:
			self._device = device
		if 'api' in kwargs:
			self.api = kwargs['api']
		self.socket.on('subscribed', self._subscribed)
		self.socket.on('subscribe', self._subscribe)
		self.socket.on('data', self._data)

	def _connect(self):
		print('connect')
		self.socket.emit('subscribe', {"apiKeys": [config.api.aw['apiKey']]})

	def _message(self, data):
		# print(data)
		self.push(data)

	def _data(self, data):
		# print(data)
		self.push(data)

	def _subscribed(self, data):
		for device in data['devices']:
			if device['macAddress'] == self._device:
				# print(device['lastData'])
				self.push(device['lastData'])

	def _subscribe(self, data):
		print(data)


class AmbientWeather(API):
	_baseParams = {'applicationKey': config.api.aw['appKey'], 'apiKey': config.api.aw['apiKey']}
	_baseHeaders: dict[str, str] = {'Accept': 'application/json'}


class AWStation(AmbientWeather):
	_deviceID: str = config.api.aw['device']
	_params = {'macAddress': _deviceID}
	_urls: AWURLs
	realtime: AWObservationRealtime
	_realtimeRefreshInterval = 15
	name = 'AmbientWeather'

	def __init__(self):
		super().__init__()
		self._id = config.api.aw['device']
		# self.socketIO = AWMessenger(api=self, device=self._deviceID)
		# if config.api.aw.getboolean('socketUpdates'):
		# 	self.socketIO.begin()
		self.getRealtime()

	@tryConnection
	def getRealtime(self):
		params = {'limit': 1}
		try:
			data = self.getData(endpoint=self._urls.realtime)
			self.realtime.update(data)
		except APIError:
			pass

	def _normalizeData(self, rawData):
		try:
			data = rawData[0]['lastData']
		except KeyError:
			data = rawData
		data['dateutc'] = int(data['dateutc'] / 1000)
		return data

	def _parseInfo(self, data):
		_macAddress = data['macAddress']
		data = data['info']
		_coord = data['coords']
		_location = {'name':        data['location'],
		             'address':     _coord['address'],
		             'city':        _coord['location'],
		             'elevation':   _coord['elevation'],
		             'coordinates': dict(_coord['coords'])}

		data = dict({'id':       _macAddress,
		             'name':     data['name'],
		             'location': dict(_location)})
		self._info = data

	def getHistorical(self, limit: int = None, endDate: datetime = None):
		limit = limit if limit else int(config.api.aw[limit])
		endDate = endDate if endDate else ''
		params = {'limit': limit, 'endDate': endDate}
		self._params.update(params)

	@property
	def _limit(self):
		return config.api.aw['limit']


class Error(Exception):
	pass


if __name__ == '__main__':
	aw = AWStation()
	aw.connectSocket()
	# aw.getData()
	print(aw)
