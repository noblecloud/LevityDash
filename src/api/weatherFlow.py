import json
import logging
from configparser import ConfigParser, SectionProxy
from dataclasses import dataclass, InitVar
from datetime import datetime
from typing import Any, Union

from PySide2.QtCore import QObject, Signal
from PySide2.QtNetwork import QHostAddress, QNetworkDatagram, QUdpSocket
from WeatherUnits.base import Measurement

from src.api.baseAPI import API, URLs
from src.observations import WFObservationRealtime, WFForecastHourly, WFForecastDaily
from src import config
from src.udp import weatherFlow as udp
from src.utils import Logger, SignalDispatcher

log = logging.getLogger(__name__)
log.setLevel(logging.CRITICAL)


class UDPMessenger(QObject):
	last: QNetworkDatagram
	udpSocket: QUdpSocket

	def __init__(self, station=None, *args, **kwargs):
		super(UDPMessenger, self).__init__(*args, **kwargs)
		self.station: WFStation = station
		self.udpSocket = QUdpSocket(self)

	def connectUPD(self):
		self.udpSocket.bind(50222)
		log.debug('Listening UDP')
		self.udpSocket.readyRead.connect(self.receiveUDP)
		self.last = self.udpSocket.receiveDatagram(self.udpSocket.pendingDatagramSize())

	def receiveUDP(self):
		messageTypes = {'rapid_wind': udp.WindMessage, 'evt_precip': udp.RainStart, 'evt_strike': udp.Lightning, 'obs_st': udp.TempestObservation, 'device_status': udp.DeviceStatus}
		while self.udpSocket.hasPendingDatagrams():
			datagram = self.udpSocket.receiveDatagram(self.udpSocket.pendingDatagramSize())
			if self.last.data() != datagram.data():
				self.last = datagram
				datagram = json.loads(str(datagram.data().data(), encoding='ascii'))
				if datagram['type'] in messageTypes:
					messageType = messageTypes[datagram['type']]
					message = messageType(datagram)
					log.debug(f'UDP message: {str(message)}')
					self.station.udpUpdate(message)


class WFURLs(URLs):
	base = 'https://swd.weatherflow.com/swd/rest/'
	__deviceID: InitVar[int]
	__stationID: int
	stations = 'stations'
	stationObservation = 'observations/station'
	deviceObservation = 'observations/device'
	station = 'stations'
	forecast = 'better_forecast'

	def __init__(self, deviceID: int, stationID: int):
		self.__station = self.station
		self.__stationObservation = self.stationObservation
		self.__deviceObservation = self.deviceObservation
		self.deviceID = deviceID
		self.stationID = stationID
		super(WFURLs, self).__init__()

	@property
	def deviceID(self) -> int:
		return self.__deviceID

	@deviceID.setter
	def deviceID(self, value: Union[str, int]):
		self.__deviceID = int(value)
		self.deviceObservation = f'{self.__deviceObservation}/{self.__deviceID}'

	@property
	def stationID(self) -> int:
		return self.__stationID

	@stationID.setter
	def stationID(self, value: Union[str, int]):
		self.__stationID = int(value)
		self.station = f'{self.__station}/{self.__stationID}'
		self.stationObservation = f'{self.__stationObservation}/{self.__stationID}'


class WeatherFlow(API):
	_stationID: int = int(config.wf['StationID'])
	_deviceID: int = int(config.wf['DeviceID'])
	_baseParams: dict[str, str] = {'token': config.wf['token']}

	_urls: WFURLs

	def __init__(self):
		super(WeatherFlow, self).__init__()
		# self.__urls = WFURLs(self._deviceID, self._stationID)
		pass


class WFStation(WeatherFlow):
	signalDispatcher = SignalDispatcher()
	_info: dict[str: Any]
	realtime: WFObservationRealtime
	hourly: WFForecastHourly
	daily: WFForecastDaily
	_messenger = UDPMessenger

	def __init__(self):
		super(WFStation, self).__init__()
		self._messenger = UDPMessenger(station=self)
		self._messenger.connectUPD()

	def _normalizeData(self, rawData):
		if 'forecast' in rawData:
			return rawData
		if 'obs' in rawData:
			return rawData.pop('obs')[0]
		return rawData

	def getData(self):
		self.getForecast()

	def getCurrent(self):
		self.realtime.source = 'tcp'
		data = super(WFStation, self).getData(endpoint=self._urls.stationObservation)
		observationData = self._normalizeData(data)
		self._info = data
		self.realtime.update(observationData)

	def getForecast(self):
		data = super(WFStation, self).getData(endpoint=self._urls.forecast, params={'station_id': self._stationID})
		self.hourly.update(data['forecast']['hourly'])
		self.daily.update(data['forecast']['daily'])
		# self.realtime.source = 'tcp'
		self.realtime.update(data['current_conditions'])

	def udpUpdate(self, data):
		if 'data' in data.keys():
			data = data['data']
		# self.realtime.source = 'udp'
		for key, value in data.items():
			if key in self.realtime.keys() and value is not None:
				self.realtime.emitUpdate(key)
				if isinstance(value, Measurement):
					self.realtime[key] |= value.localize
				else:
					self.realtime[key] = value
			else:
				self.realtime[key] = value
				self.realtime.signalDispatcher.valueAddedSignal.emit({'value': value, 'source': self.realtime})

	@property
	def messenger(self):
		return self._messenger


# class WFForecast(WeatherFlow):
# 	_info = dict[str: Any]
# 	_hourly: ObservationForecast
# 	_daily: ObservationForecast
#
# 	def __init__(self, **kwargs):
# 		## TODO: Add support for using units in config.ini
# 		super().__init__()
# 		self._endpoint = 'better_forecast'
# 		self._params.update({"station_id": config.wf['stationID'], **kwargs})
# 		self._observation = WFObservationHour()
#
# 	def getData(self, *args):
# 		translator = ConfigParser()
# 		translator.read('weatherFlow.ini')
# 		data: dict = super(WFForecast, self).getData()
# 		self._hourly = WFForecastHourly(data['forecast']['hourly'])
# 		self._daily = WFForecastHourly(data['forecast']['daily'])
#
# 	def translateData(self, section, data: Union[dict, list], translator, atlas) -> Union[dict, list]:
# 		if isinstance(data, list):
# 			newList = []
# 			for i in range(len(data)):
# 				newList.append(self.translateData(section, data[i], translator, atlas))
# 			return newList
# 		for key in section:
# 			newKey = section[key]
# 			if newKey[0] == '[':
# 				data[newKey[1:-1]] = self.translateData(translator[newKey[1:-1]], data.pop(key), translator, atlas)
# 			else:
# 				if key != newKey:
# 					value = data.pop(key)
# 					data[newKey] = data.pop(key)
# 				else:
# 					pass
# 		return data
#
# 	def buildClassAtlas(self, translator) -> dict[str, str]:
# 		atlas = {}
# 		for item in translator['unitGroups']:
# 			type = item
# 			group = [value.strip(' ') for value in translator['unitGroups'][type].split(',')]
# 			for value in group:
# 				atlas[value] = type
# 		return atlas
#
# 	@property
# 	def daily(self):
# 		return self._daily
#
# 	@property
# 	def hourly(self):
# 		return self._hourly


class ErrorNoConnection(Exception):

	def __init__(self, data, *args, **kwargs):
		logging.error(data)
		super(ErrorNoConnection, self).__init__(*args, **kwargs)

	pass


if __name__ == '__main__':
	logging.getLogger().setLevel(logging.DEBUG)
	wf = WFStation()
	wf.getForecast()
	print(wf.hourly[datetime.now()])
