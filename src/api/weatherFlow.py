import json
import logging
from datetime import datetime, timedelta
from typing import Any

from src import config
from observations import Observation, WFStationObservation
from translators import WFStationTranslator, WFTranslator
import requests


class _URLs:
	_base = 'https://swd.weatherflow.com/swd/rest/'
	_stationObservation = _base + 'observations/station/{}'
	_deviceObservation = _base + 'observations/device/{}'

	_stations = _base + 'stations/'
	_station = _base + 'stations/{}'

	_forecast = _base + 'better_forecast/'

	_stationID: int
	_deviceID: int

	# def __init__(self, stationID, deviceID):
	# 	self._stationID = stationID
	# 	self._deviceID = deviceID

	@property
	def forecast(self):
		return self._forecast

	@property
	def station(self):
		return self._stationObservation

	@property
	def device(self):
		return self._deviceObservation

	@property
	def stationData(self):
		return self._station


class WeatherFlow:
	_apiKey: str
	_stationID: int
	_deviceID: int
	_currentStationConditions = dict[str, str]

	_baseHeader: dict[str, str] = {'Accept': 'application/json'}
	_baseParams: dict[str, str] = {}

	_baseURL = 'https://swd.weatherflow.com/swd/rest/'
	_stationURL = _baseURL + 'observations/station/{}'

	def __init__(self):

		stationID = int(config.wf['stationID'])
		deviceID = int(config.wf['deviceID'])

		self._apiKey = config.wf['token']
		self._stationID = stationID
		self._deviceID = deviceID
		self._baseParams['token'] = config.wf['token']
		self._station = Station(stationID)

	def getData(self, url, params={}):
		params = {**self._baseParams, **params}
		request = requests.get(url, params)
		if request.status_code != 200:
			raise Error
		else:
			return json.loads(request.content)

	@property
	def station(self):
		return self._station


class Station:
	_baseURL: str
	_id: int
	_prams: dict[str, str]
	_info = dict[str: Any]
	_currentConditions: Observation
	_hourlyForecast: Any
	_dailyForecast: Any
	_translator = WFStationTranslator()

	def __init__(self, id: int):
		self._apiKey = config.wf['token']
		self._prams = {'token': self._apiKey}
		self._baseURL = 'https://swd.weatherflow.com/swd/rest/observations/station/{}'.format(id)
		self._id = id

	@property
	def currentConditions(self):
		return self._currentConditions

	def update(self):
		request = requests.get(self._baseURL, self._prams)
		data = request.json()

		observationData: dict = data.pop('obs')[0]
		self._info = data
		self._currentConditions = WFStationObservation(observationData)


class Error(Exception):
	pass


if __name__ == '__main__':
	logging.getLogger().setLevel(logging.WARNING)
	wf = WeatherFlow()
	wf._station.update()
	t = wf.station.currentConditions
	print(wf.station.currentConditions.precipitation.hourly)
	print(wf.station.currentConditions.wind.gust)
