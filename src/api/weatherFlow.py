import json
import logging
from configparser import ConfigParser, SectionProxy
from typing import Any, Union

import requests
from PySide2.QtCore import QObject, Signal
from PySide2.QtNetwork import QUdpSocket

import utils
from api.errors import APIError, InvalidCredentials, RateLimitExceeded
from observations import Observation, WFStationObservation
from src import config
from src.udp import weatherFlow as udp
import src.units.defaults.weatherFlow as units
from translators import WFStationTranslator


class UDPMessenger(QObject):
	signal = Signal(str)

	def __init__(self, station=None, *args, **kwargs):
		super(UDPMessenger, self).__init__(*args, **kwargs)
		self.station: WFStation = station
		self.udpSocket = QUdpSocket(self)

	def connectUPD(self):
		self.udpSocket.bind(50222)
		self.udpSocket.readyRead.connect(self.receiveUDP)

	def receiveUDP(self):
		messageTypes = {'rapid_wind': udp.Wind, 'evt_precip': udp.RainStart, 'evt_strike': udp.Lightning, 'obs_st': udp.Obs_st}
		while self.udpSocket.hasPendingDatagrams():
			datagram, host, port = self.udpSocket.readDatagram(self.udpSocket.pendingDatagramSize())
			datagram = json.loads(str(datagram, encoding='ascii'))
			if datagram['type'] in messageTypes:
				messageType = messageTypes[datagram['type']]
				message = messageType(datagram)
				self.station.udpUpdate(message)
				self.signal.emit('updated')


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
	_stationID: int
	_deviceID: int

	_baseParams: dict[str, str] = {}
	_params: dict[str, str] = {}

	_baseURL = 'https://swd.weatherflow.com/swd/rest/'
	_endpoint = ''

	def __init__(self):
		self._baseParams['token'] = config.wf['token']

	def getData(self, params: dict = None):

		params = {**self._baseParams, **self._params, **params} if params else {**self._baseParams, **self._params}

		request = requests.get(self.url, params)

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
	def url(self):
		return self._baseURL + self._endpoint


class WFForecast(WeatherFlow):
	_info = dict[str: Any]
	# _hourly: Observation
	# _daily: ObservationSet
	_translator = WFStationTranslator()

	def __init__(self, **kwargs):
		## TODO: Add support for using units in config.ini
		super().__init__()
		self._endpoint = 'better_forecast'
		self._params.update({"station_id": config.wf['stationID'], **kwargs})
		self._translator = WFStationTranslator()
		self._observation = WFStationObservation()

	def getData(self, *args):
		translator = ConfigParser()
		translator.read('weatherFlow.ini')
		self.data: dict = super(WFForecast, self).getData()
		atlas = self.buildClassAtlas(translator)
		self.translateData(translator['root'], self.data, translator, atlas)

	# for item in infoConfig:
	# 	newKey = infoConfig[item]
	# 	if item != newKey:
	# 		self.data[newKey] = self.data.pop(item)
	# 	else:
	# 		pass

	def translateData(self, section, data: Union[dict, list], translator, atlas) -> Union[dict, list]:
		if isinstance(data, list):
			newList = []
			for i in range(len(data)):
				newList.append(self.translateData(section, data[i], translator, atlas))
			return newList
		for key in section:
			newKey = section[key]
			if newKey[0] == '[':
				data[newKey[1:-1]] = self.translateData(translator[newKey[1:-1]], data.pop(key), translator, atlas)
			else:
				if key != newKey:
					value = data.pop(key)
					data[newKey] = data.pop(key)
				else:
					pass
		return data

	def buildClassAtlas(self, translator) -> dict[str, str]:
		atlas = {}
		for item in translator['unitGroups']:
			type = item
			group = [value.strip(' ') for value in translator['unitGroups'][type].split(',')]
			for value in group:
				atlas[value] = type
		return atlas


class WFStation(WeatherFlow):
	_id: int
	_info = dict[str: Any]
	_observation: Observation
	_translator = WFStationTranslator()
	_messenger = UDPMessenger

	def __init__(self):
		super().__init__()

		self._id = config.wf['StationID']
		self._endpoint = 'observations/station/{id}'.format(id=self._id)
		self._translator = WFStationTranslator()
		self._observation = WFStationObservation()
		self._messenger = UDPMessenger(station=self)
		self._messenger.connectUPD()

	def getData(self, *args):
		data = super(WFStation, self).getData()
		observationData: dict = data.pop('obs')[0]
		tz = data['timezone']
		time = observationData.pop('timestamp')
		date = utils.formatDate(time, tz)
		self._date = date
		self._info = data
		self._observation.dataUpdate(observationData)
		self.localize()

	def getForecast(self):
		data = super(WFStation, self).getData()
		observationData: dict = data.pop('obs')[0]
		tz = data['timezone']
		time = observationData.pop('timestamp')
		date = utils.formatDate(time, tz)
		self._date = date
		self._info = data
		self._observation.dataUpdate(observationData)
		self.localize()

	def localize(self):
		for key, value in self._observation.items():
			try:
				self._observation[key] = value.localized
			except AttributeError:
				pass

	def udpUpdate(self, data):
		data = data['data']
		self._observation.update(data)

	@property
	def obs(self):
		return self._observation

	@property
	def messenger(self):
		return self._messenger


class ErrorNoConnection(Exception):

	def __init__(self, data, *args, **kwargs):
		logging.error(data)
		super(ErrorNoConnection, self).__init__(*args, **kwargs)

	pass


if __name__ == '__main__':
	logging.getLogger().setLevel(logging.DEBUG)
	wf = WFForecast()
	wf.getData()
	print(wf)
