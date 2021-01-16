import logging
from datetime import datetime

import requests

from api.errors import InvalidCredentials, RateLimitExceeded, APIError
from src import SmartDictionary, config
from observations import Observation
from observations.AmbientWeather import AWIndoor, AWOutdoor
from translators import AWTranslator


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

	def getData(self):

		request = requests.get(self.url, self._params)
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


class AWStation(_AmbientWeather):
	_deviceURL: str
	_mac: str
	_info = SmartDictionary
	_current: Observation
	_indoor: AWIndoor
	_outdoor: AWOutdoor

	def __init__(self):
		super().__init__()
		self._id = config.aw['device']
		self._url = '{}/{}/'.format(self._url, self._id)
		self._indoor = AWIndoor()
		self._outdoor = AWOutdoor()

	def getCurrent(self):
		params = {'limit': 1}
		self._params.update(params)

	def getData(self, params: dict = None):
		data = super(AWStation, self).getData()
		self._indoor.update(data)
		self._outdoor.update(data)


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


	@property
	def currentConditions(self):
		return self._current

	def update(self):
		pass

	@property
	def _limit(self):
		config.update()
		return config.aw['limit']

class Error(Exception):
	pass


if __name__ == '__main__':
	wf = AmbientWeather()
	print(wf)
