import logging
from datetime import datetime

import requests

from api import errors
from src import utils
from src.api.errors import InvalidCredentials, RateLimitExceeded, APIError
from src import SmartDictionary, config
from src.observations import ObservationSingle
from src.observations.ambientWeather import AWIndoor, AWOutdoor
from src.translators import AWTranslator
from utils import Logger


class _AmbientWeather:
	_stations = []
	_data: dict
	_apiKey: str
	_translator = AWTranslator()

	_baseHeader: dict[str, str] = {'Accept': 'application/json'}

	_url = 'https://api.ambientweather.net/v1/devices'
	_deviceURL = '{}/{{}}/'.format(_url)

	def __init__(self):
		self._apiKey = config.aw['apiKey']
		self._appKey = config.aw['appKey']

	def getData(self, params: dict = None):

		params = {**self._params, **params}
		try:
			request = requests.get(self.url, params, timeout=1)
			if request.status_code == 200:
				return request.json()
			elif request.status_code == 429:
				logging.error("Rate limit exceeded for {} API".format(self.__class__.__name__))
				raise RateLimitExceeded
			elif request.status_code == 401:
				logging.error("Invalid credentials for {} API".format(self.__class__.__name__))
				raise InvalidCredentials
			else:
				raise APIError
		except requests.RequestException as e:
			raise errors.APIError(e)

	@property
	def _device(self):
		config.update()
		return config.aw['device']

	@property
	def _baseParams(self) -> dict:
		params = {'applicationKey': self._appKey, 'apiKey': self._apiKey}
		return params

	@property
	def _params(self):
		return self._baseParams

	@property
	def url(self):
		return self._url


class AmbientWeather(_AmbientWeather):
	_stations = []

	def getData(self):
		pass
		# data = super(AmbientWeather, self).getData()
		# for stationData in data:
		# 	self._stations.append(AWStation(stationData))

	@property
	def _device(self):
		config.update()
		return config.aw['device']

	@property
	def _baseParams(self) -> dict:
		params = {'applicationKey': self._appKey, 'apiKey': self._apiKey}
		return params

	@property
	def _limit(self):
		config.update()
		return config.aw['limit']


@Logger
class AWStation(_AmbientWeather):
	_deviceURL: str
	_mac: str
	_info = SmartDictionary
	_current: ObservationSingle
	_indoor: AWIndoor
	_outdoor: AWOutdoor

	def __init__(self):
		super().__init__()
		self._id = config.aw['device']
		self._url = '{}/{}/'.format(self._url, self._id)
		self._indoor = AWIndoor()
		self._outdoor = AWOutdoor()
		self._translator = AWTranslator()

	def getCurrent(self):
		params = {'limit': 1}
		self._params.update(params)

	def getData(self, params: dict = None):
		try:
			data = super(AWStation, self).getData({'limit': 5})[0]
			timeName = self._translator['time']['time']
			tz = self._translator.tz()
			self._time = utils.formatDate(data.pop(timeName), tz.zone, utc=True, microseconds=True)
			self._outdoor.dataUpdate(data)
			self._indoor.dataUpdate(data)
			self._log.info('Updated')
		except APIError as e:
			self._log.error('Unable to fetch data', e)

	def _parseInfo(self, data):
		_macAddress = data['macAddress']
		data = data['info']
		_coord = data['coords']
		_location = {'name':        data['location'],
		             'address':     _coord['address'],
		             'city':        _coord['location'],
		             'elevation':   _coord['elevation'],
		             'coordinates': SmartDictionary(_coord['coords'])}

		data = SmartDictionary({'id':     _macAddress,
		                      'name':     data['name'],
		                      'location': SmartDictionary(_location)})
		self._info = data

	def getHistorical(self, limit: int = None, endDate: datetime = None):
		limit = limit if limit else int(config.aw[limit])
		endDate = endDate if endDate else ''
		params = {'limit': limit, 'endDate': endDate}
		self._params.update(params)

	def update(self):
		self.getData()

	@property
	def indoor(self):
		return self._indoor

	@property
	def outdoor(self):
		return self._outdoor

	@property
	def _limit(self):
		config.update()
		return config.aw['limit']

class Error(Exception):
	pass


if __name__ == '__main__':
	aw = AWStation()
	aw.getData()
	print(aw)
