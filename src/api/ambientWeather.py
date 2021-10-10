import logging
from dataclasses import InitVar
from datetime import datetime
from typing import Optional, Union

from PySide2.QtNetwork import QTcpSocket
from weblib.http import urlencode

from src.observations import AWObservationRealtime
from src.api.baseAPI import API, SocketIOMessenger, URLs, WSMessenger
from src.api.errors import InvalidCredentials, RateLimitExceeded, APIError
from src import config
from src.observations import ObservationRealtime
from src.utils import formatDate, Logger, SignalDispatcher

log = logging.getLogger(__name__)


class AWURLs(URLs):
	base = 'https://api.ambientweather.net/v1'
	device = 'devices'
	socket = f"?{urlencode({'api': 1, 'applicationKey': config.aw['appKey']})}"

	def __init__(self):
		super(AWURLs, self).__init__()


class AWMessenger(SocketIOMessenger):
	socketParams = {'transports': ['websocket']}
	_device: str

	def __init__(self, device: Optional[str] = None, *args, **kwargs):
		super(AWMessenger, self).__init__(*args, **kwargs)
		if device is not None:
			self._device = device
		self.socket.on('subscribed', self._subscribed)
		self.socket.on('data', self._data)

	def _connect(self):
		print('connect')
		self.socket.emit('subscribe', {"apiKeys": [config.aw['apiKey']]})

	def _data(self, data):
		self.push(data)

	def _subscribed(self, data):
		for device in data['devices']:
			if device['macAddress'] == self._device:
				self.push(device['lastData'])


class AmbientWeather(API):
	_baseParams = {'applicationKey': config.aw['appKey'], 'apiKey': config.aw['apiKey']}
	_baseHeaders: dict[str, str] = {'Accept': 'application/json'}


class AWStation(AmbientWeather):
	_deviceID: str = config.aw['device']
	_params = {'macAddress': _deviceID}
	_urls: AWURLs
	realtime: AWObservationRealtime

	def __init__(self):
		super().__init__()
		self._id = config.aw['device']

	def getCurrent(self):
		params = {'limit': 1}
		self._params.update(params)

	def connectSocket(self):
		self.socket = AWMessenger(station=self, device=self._deviceID, url=self._urls.socket)
		self.socket.begin()
		super(AWStation, self).connectSocket()

	def getData(self, params: dict = None):
		try:
			data = super(AWStation, self).getData(endpoint=self._urls.device)
			# timeName = self._translator['time']['time']
			self.realtime.update(data)
			log.info('Updated')
		except APIError as e:
			log.error('Unable to fetch data', e)

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
		limit = limit if limit else int(config.aw[limit])
		endDate = endDate if endDate else ''
		params = {'limit': limit, 'endDate': endDate}
		self._params.update(params)

	def update(self):
		self.getData()

	@property
	def _limit(self):
		return config.aw['limit']


class Error(Exception):
	pass


if __name__ == '__main__':
	aw = AWStation()
	aw.connectSocket()
	# aw.getData()
	print(aw)
