from src import logging
from datetime import datetime, timedelta
from json import dumps, loads
from typing import Any, Dict, Union

import websocket
from PySide2.QtCore import QObject, QThread, QTimer, Signal
from PySide2.QtNetwork import QHostAddress, QNetworkDatagram, QUdpSocket
from WeatherUnits.base import Measurement

from src.api.baseAPI import API, Socket, tryConnection, UDPSocket, URLs, Websocket
from src.observations import WFObservationRealtime, WFForecastHourly, WFForecastDaily
from src import config
from src.udp import weatherFlow as udp

log = logging.getLogger(__name__)


class WFURLs(URLs, realtime=True):
	base = 'https://swd.weatherflow.com/swd/'
	__deviceID: int
	__stationID: int
	stationObservation = 'rest/observations/station'
	deviceObservation = 'rest/observations/device'
	station = 'rest/stations'
	forecast = 'rest/better_forecast'
	realtime = stationObservation

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


class WFWebsocket(Websocket):
	urlBase = 'wss://swd.weatherflow.com/swd/data'

	@property
	def url(self):
		return self.urlBase

	def __init__(self, DeviceID: int, *args, **kwargs):
		self._deviceID = DeviceID
		super(WFWebsocket, self).__init__(*args, **kwargs)
		from secrets import token_urlsafe as genUUID
		self.uuid = genUUID(8)
		self.socket = websocket.WebSocketApp(self.url,
		                                     on_open=self._open,
		                                     on_data=self._data,
		                                     on_message=self._message,
		                                     on_error=self._error,
		                                     on_close=self._close)

	def genMessage(self, messageType: str) -> dict[str:str]:
		message = {"type":      messageType,
		           "device_id": self._deviceID,
		           "id":        self.uuid}
		return message

	def _open(self, ws):
		ws.send(dumps(self.genMessage('listen_start')))
		ws.send(dumps(self.genMessage('listen_rapid_start')))
		print("### opened ###")

	def _message(self, ws, message):
		self.push(loads(message))


class WFUDPSocket(UDPSocket):
	port = 50222
	messageTypes = {'rapid_wind': udp.WindMessage, 'evt_precip': udp.RainStart, 'evt_strike': udp.Lightning, 'obs_st': udp.TempestObservation, 'device_status': udp.DeviceStatus}

	def parseDatagram(self, datagram: QNetworkDatagram):
		datagram = loads(str(datagram.data().data(), encoding='ascii'))
		if datagram['type'] in self.messageTypes:
			print(datagram)
			messageType = self.messageTypes[datagram['type']]
			message = messageType(datagram)
			log.debug(f'UDP message: {str(message)}')
			self.push(message)


class WeatherFlow(API):
	_stationID: int = int(config.api.wf['StationID'])
	_deviceID: int = int(config.api.wf['DeviceID'])
	_baseParams: Dict[str, str] = {'token': config.api.wf['token']}

	_urls: WFURLs


class WFStation(WeatherFlow):
	_info: Dict[str, Any]
	realtime: WFObservationRealtime
	hourly: WFForecastHourly
	daily: WFForecastDaily
	# _udpSocket = WFUDPSocket
	_realtimeRefreshInterval = timedelta(minutes=15)
	_forecastRefreshInterval = timedelta(minutes=15)
	name = 'WeatherFlow'

	def __init__(self):
		super(WFStation, self).__init__()
		self._udpSocket = WFUDPSocket(api=self)
		if config.api.aw.getboolean('autoUpdate'):
			self._realtimeRefreshTimer.stop()
		# self._webSocket = WFWebsocket(self._deviceID)
		# self._webSocket.begin()
		# if config.api.wf.getboolean('socketUpdates'):
		# self._udpSocket.begin()
		self.getRealtime()
		self.getForecast()

	def _normalizeData(self, rawData):

		try:
			if 'forecast' in rawData:
				return rawData
			if 'obs' in rawData:
				obs = rawData.pop('obs')
				if len(obs) == 0:
					raise ValueError(rawData['status']['status_message'])
				else:
					return obs[0]
			return rawData
		except ValueError as e:
			log.error(e)
			return {}

	@tryConnection
	def getRealtime(self):
		data = self.getData(endpoint=self._urls.stationObservation)
		observationData = self._normalizeData(data)
		self.realtime.update(observationData)

	@tryConnection
	def getForecast(self):
		data = super(WFStation, self).getData(endpoint=self._urls.forecast, params={'station_id': self._stationID})
		self.hourly.update(data['forecast']['hourly'])
		try:
			self.daily.update(data['forecast']['daily'])
		except KeyError:
			pass
		# self.realtime.source = 'tcp'
		self.realtime.update(data['current_conditions'])

	def socketUpdate(self, data):
		if 'data' in data.keys():
			data = data['data']
		# self.realtime.source = 'udp'
		for key, value in data.items():
			if isinstance(value, Measurement):
				if key in self.realtime.keys():
					self.realtime[key] |= value
				else:
					self.realtime[key] = value
			else:
				self.realtime[key] = value
			self.realtime.updateHandler.autoEmit(key)

	@property
	def messenger(self):
		return self._udpSocket


# class WFForecast(WeatherFlow):
# 	_info = dict[str: Any]
# 	_hourly: ObservationForecast
# 	_daily: ObservationForecast
#
# 	def __init__(self, **kwargs):
# 		## TODO: Add support for using units in config.ini
# 		super().__init__()
# 		self._endpoint = 'better_forecast'
# 		self._params.update({"station_id": config.api.wf['stationID'], **kwargs})
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
