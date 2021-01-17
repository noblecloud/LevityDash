import json
import logging
from datetime import datetime, timedelta
from typing import Any

from PySide2.QtCore import QObject, Signal, Slot
from PySide2.QtNetwork import QUdpSocket

import utils
from api.errors import APIError, InvalidCredentials, RateLimitExceeded
from src import config
from observations import Observation, WFObservation, WFStationObservation
from translators import WFStationTranslator, WFTranslator
import requests
from src.udp import weatherFlow as udp


class UDPMessenger(QObject):
	signal = Signal(str)

	def __init__(self, station=None, *args, **kwargs):
		super(UDPMessenger, self).__init__(*args, **kwargs)
		self.station: WFStation = station
		self.udpSocket = QUdpSocket(self)

	def connectUPD(self):
		self.udpSocket.bind(50224)
		self.udpSocket.readyRead.connect(self.receiveUDP)

	def receiveUDP(self):
		messageTypes = {'rapid_wind': udp.Wind, 'evt_precip': udp.RainStart, 'evt_strike': udp.Lightning, 'obs_st': udp.Obs_st}
		while self.udpSocket.hasPendingDatagrams():
			datagram, host, port = self.udpSocket.readDatagram(self.udpSocket.pendingDatagramSize())
			datagram = json.loads(str(datagram, encoding='ascii'))
			if datagram['type'] in messageTypes:
				messageType = messageTypes[datagram['type']]
				message = messageType(datagram)
				print(self.station._current['speed'])
				self.station.udpUpdate(message)
				self.signal.emit('updated')
				print(self.station._current['speed'])


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

	_baseParams: dict[str, str] = {}

	_baseURL = 'https://swd.weatherflow.com/swd/rest/'

	def __init__(self):
		self._apiKey = config.wf['token']
		self._baseParams['token'] = config.wf['token']

	def getData(self, params: dict = None):

		params = {**self._baseParams, **params} if params else self._baseParams

		request = requests.get(self._url, params)

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
	def _url(self):
		return self._baseURL


class WFStation(WeatherFlow):
	_baseURL: str
	_id: int
	_prams: dict[str, str]
	_info = dict[str: Any]
	_current: Observation
	_hourlyForecast: Any
	_dailyForecast: Any
	_translator = WFStationTranslator()
	_messenger = UDPMessenger

	def __init__(self):
		super().__init__()

		self._id = config.wf['StationID']
		self._translator = WFStationTranslator()
		self._current = WFStationObservation()
		self._messenger = UDPMessenger(station=self)
		self._messenger.connectUPD()

	def getData(self):
		data = super(WFStation, self).getData()
		observationData: dict = data.pop('obs')[0]
		tz = data['timezone']
		time = observationData.pop('timestamp')
		date = utils.formatDate(time, tz)
		self._date = date
		self._info = data
		self._current.dataUpdate(observationData)
		self.localize()

	def localize(self):
		for key, value in self._current.items():
			try:
				self._current[key] = value.localized
			except AttributeError:
				pass

	def udpUpdate(self, data):
		data = data['data']
		self._current.update(data)

	@property
	def _url(self):
		return '{}observations/station/{}'.format(self._baseURL, self._id)

	@property
	def current(self):
		return self._current

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
	wf = WFStation()
	wf.getData()
	c = wf._current
	print(c.humidity)
	print()
