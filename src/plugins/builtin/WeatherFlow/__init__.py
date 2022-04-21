from zoneinfo import ZoneInfo

import asyncio

from src.plugins.web.socket import UDPSocket
from src import logging
from src.plugins.plugin import ScheduledEvent
from src.plugins.web import Auth, AuthType, Endpoint, REST, URLs

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from src import config
from .socket import *

log = logging.getLogger(__name__)

__all__ = ["WeatherFlow", '__plugin__']


class WFURLs(URLs, base='swd.weatherflow.com/swd'):
	stationID: int = int(config.plugins.wf['StationID'])
	deviceID: int = int(config.plugins.wf['DeviceID'])

	auth = Auth(authType=AuthType.PARAMETER, authData={'token': config.plugins.wf['token']})

	rest = Endpoint(url='rest', auth=auth, protocol='https', refreshInterval=timedelta(minutes=5))
	websocket = Endpoint(url='data', protocol='wss')

	stationObservation = Endpoint(base=rest, url=f'observations/station/{stationID}')
	deviceObservation = Endpoint(base=rest, url=f'observations/device/{deviceID}')
	station = Endpoint(base=rest, url='stations')

	forecast = Endpoint(base=rest, url='better_forecast', params={'station_id': stationID}, period=[timedelta(hours=1), timedelta(days=1)])

	realtime = Endpoint(base=stationObservation, )
	historical = Endpoint(base=deviceObservation)


# @property
# def deviceID(self) -> int:
# 	return self.__deviceID
#
# @deviceID.setter
# def deviceID(self, value: Union[str, int]):
# 	self.__deviceID = int(value)
#
# @property
# def stationID(self) -> int:
# 	return self.__stationID
#
# @stationID.setter
# def stationID(self, value: Union[str, int]):
# 	self.__stationID = int(value)
# 	self.station = f'{self.__station}/{self.__stationID}'
# 	self.stationObservation = f'{self.__stationObservation}/{self.__stationID}'


# class WFWebsocket(Websocket):
# 	urlBase = 'wss://swd.weatherflow.com/swd/data'
#
# 	@property
# 	def url(self):
# 		return self.urlBase
#
# 	def __init__(self, DeviceID: int, *args, **kwargs):
# 		self._deviceID = DeviceID
# 		super(WFWebsocket, self).__init__(*args, **kwargs)
# 		from secrets import token_urlsafe as genUUID
# 		self.uuid = genUUID(8)
# 		self.socket = websocket.WebSocketApp(self.url,
# 		                                     on_open=self._open,
# 		                                     on_data=self._data,
# 		                                     on_message=self._message,
# 		                                     on_error=self._error,
# 		                                     on_close=self._close)
#
# 	def genMessage(self, messageType: str) -> dict[str:str]:
# 		message = {"type":      messageType,
# 		           "device_id": self._deviceID,
# 		           "id":        self.uuid}
# 		return message
#
# 	def _open(self, ws):
# 		ws.send(dumps(self.genMessage('listen_start')))
# 		ws.send(dumps(self.genMessage('listen_rapid_start')))
# 		print("### opened ###")
#
# 	def _message(self, ws, message):
# 		self.push(loads(message))
#
#
# class WFUDPSocket(UDPSocket):
# 	port = 50222
messageTypes = {
	'rapid_wind': WindMessage,
	'evt_precip': RainStart,
	'evt_strike': Lightning,
	'obs_st':     TempestObservation,
	# 'device_status': DeviceStatus,
	# 'hub_status': HubStatus
}  # , 'light': udp.Light}
#
# 	def parseDatagram(self, datagram: ):
# 		datagram = loads(str(datagram.data().data(), encoding='ascii'))
# 		if datagram['type'] in self.messageTypes:
# 			messageType = self.messageTypes[datagram['type']]
# 			message = messageType(datagram)
# 			log.debug(f'UDP message: {str(message)}')
# 			self.push(message)
#

unitDefinitions = {
	'environment.temperature':                           {'type': 'temperature', 'sourceUnit': 'c'},
	'environment.temperature.temperature':               {'title': 'Temperature', 'sourceKey': 'air_temperature'},
	'environment.temperature.dewpoint':                  {'title': 'Dewpoint', 'sourceKey': 'dew_point'},
	'environment.temperature.wetBulb':                   {'title': 'Wet Bulb', 'sourceKey': 'wet_bulb_temperature'},
	'environment.temperature.wetBulbGlobe':              {'title': 'Wet Bulb Globe', 'sourceKey': ['wet_bulb_temperature_globe', 'wet_bulb_globe_temperature']},
	'environment.temperature.feelsLike':                 {'title': 'Feels Like', 'sourceKey': 'feels_like', 'calculation': 'feelsLike'},
	'environment.temperature.heatIndex':                 {'title': 'Heat Index', 'sourceKey': 'heat_index'},
	'environment.temperature.windChill':                 {'title': 'Wind Chill', 'sourceKey': 'wind_chill'},
	'environment.temperature.deltaT':                    {'title': 'Delta T', 'sourceKey': 'delta_t'},
	'environment.temperature.high':                      {'title': 'Temperature High', 'sourceKey': 'air_temp_high', 'forecastOnly': True},
	'environment.temperature.low':                       {'title': 'Temperature Low', 'sourceKey': 'air_temp_low', 'forecastOnly': True},

	'environment.humidity.humidity':                     {'type': 'humidity', 'sourceUnit': '%', 'title': 'Humidity', 'sourceKey': 'relative_humidity'},

	'environment.light.uvi':                             {'type': 'index', 'sourceUnit': 'uvi', 'title': 'UVI', 'sourceKey': 'uv'},
	'environment.light.irradiance':                      {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Irradiance', 'sourceKey': 'solar_radiation'},
	'environment.light.illuminance':                     {'type': 'illuminance', 'sourceUnit': 'lux', 'title': 'Illuminance', 'sourceKey': 'brightness'},
	'environment.pressure':                              {'type': 'pressure', 'sourceUnit': 'mb'},
	'environment.pressure.pressure':                     {'title': 'Pressure', 'sourceKey': 'barometric_pressure'},
	'environment.pressure.pressureAbsolute':             {'title': 'Absolute', 'sourceKey': 'station_pressure'},
	'environment.pressure.pressureSeaLevel':             {'title': 'Sea Level', 'sourceKey': 'sea_level_pressure'},
	'environment.pressure.airDensity':                   {'type': 'airDensity', 'sourceUnit': ['kg', 'm'], 'title': 'Air Density', 'sourceKey': 'air_density'},
	'environment.pressure.trend':                        {'type': 'pressureTrend', 'sourceUnit': 'str', 'title': 'Trend', 'sourceKey': 'pressure_trend'},

	'environment.wind.direction':                        {'type': 'direction', 'requires': {'environment.wind.speed.speed': {'gt': 0}}},
	'environment.wind.direction.direction':              {'sourceUnit': 'º', 'title': 'Direction', 'sourceKey': 'wind_direction'},
	'environment.wind.direction.cardinal':               {'sourceUnit': 'º[cardinal]', 'title': 'Cardinal Direction', 'sourceKey': 'wind_direction_cardinal'},
	'environment.wind.speed':                            {'type': 'wind', 'sourceUnit': ['m', 's']},
	'environment.wind.speed.speed':                      {'title': 'Speed', 'sourceKey': 'wind_avg'},
	'environment.wind.speed.lull':                       {'title': 'Lull', 'sourceKey': 'wind_lull'},
	'environment.wind.speed.gust':                       {'title': 'Gust', 'sourceKey': 'wind_gust'},

	'environment.precipitation.precipitation':           {'type': 'precipitationRate', 'sourceUnit': ['mm', '@period'], 'title': 'Rate', 'sourceKey': 'precip'},
	'environment.precipitation.hourly':                  {'type': 'precipitationHourly', 'sourceUnit': ['mm', 'hr'], 'title': 'Hourly', 'sourceKey': 'precip_accum_last_1hr'},
	'environment.precipitation.daily':                   {'type': 'precipitationDaily', 'sourceUnit': ['mm', 'day'], 'title': 'Daily', 'sourceKey': 'precip_accum_local_day'},
	'environment.precipitation.dailyFinal':              {'type': 'precipitationDaily', 'sourceUnit': ['mm', 'day'], 'title': 'Daily', 'sourceKey': 'precip_accum_local_day_final'},
	'environment.precipitation.icon':                    {'type':    'icon', 'sourceUnit': 'str', 'title': 'Precipitation Icon', 'forecastOnly': True, 'sourceKey': 'precip_icon', 'iconType': 'glyph', 'glyphFont': 'WeatherIcons',
	                                                      'aliases': '@precipitationIcon'},
	'environment.precipitation.time':                    {'type': 'time', 'sourceUnit': 'min', 'title': 'Minutes', 'sourceKey': 'precip_minutes_local_day'},
	'environment.precipitation.type':                    {'type': 'precipitationType', 'sourceUnit': '*', 'title': 'Precipitation Type', 'sourceKey': 'precip_type'},
	'environment.precipitation.analysis':                {'type': 'rainCheckType', 'sourceUnit': 'int', 'title': 'Type', 'sourceKey': 'precip_analysis_type'},
	'environment.precipitation.probability':             {'type': 'probability', 'sourceUnit': '%p', 'title': 'Precipitation Probability', 'sourceKey': 'precip_probability'},
	'environment.precipitation.description':             {'type': 'description', 'sourceUnit': 's', 'title': 'Precipitation Description', 'sourceKey': 'precip_description'},

	'environment.yesterday.precipitation.precipitation': {'type': 'precipitationDaily', 'sourceUnit': ['mm', 'day'], 'title': 'Yesterday', 'sourceKey': ('precip_accum_local_yesterday_final', 'precip_accum_local_yesterday')},
	'environment.yesterday.precipitation.time':          {'type': 'time', 'sourceUnit': 'min', 'title': 'Minutes Yesterday', 'sourceKey': 'precip_minutes_local_yesterday_final'},
	'environment.yesterday.precipitation.timeRaw':       {'type': 'time', 'sourceUnit': 'min', 'title': 'Minutes Yesterday Raw', 'sourceKey': 'precip_minutes_local_yesterday'},
	'environment.yesterday.precipitation.analysis':      {'type': 'rainCheckType', 'sourceUnit': 'int', 'title': 'Type Yesterday', 'sourceKey': 'precip_analysis_type_yesterday'},

	'environment.lightning.last':                        {'type': 'date', 'sourceUnit': 'epoch', 'title': 'Last Strike', 'sourceKey': 'lightning_strike_last_epoch'},
	'environment.lightning.distance':                    {'type': 'length', 'sourceUnit': 'km', 'title': 'Last Strike Distance', 'sourceKey': 'lightning_strike_last_distance'},
	'environment.lightning.distanceAverage':             {'type': 'length', 'sourceUnit': 'km', 'title': 'Last Strike Distance', 'sourceKey': 'lightning_strike_last_distance_msg'},
	'environment.lightning.lightning':                   {'type': 'strikeCount', 'sourceUnit': 'strike', 'title': 'Strike Count', 'sourceKey': 'lightning_strike_count'},
	'environment.lightning.energy':                      {'type': 'energy', 'sourceUnit': 'int', 'title': 'Strike Energy', 'sourceKey': 'strikeEnergy'},
	'environment.lightning.count1hr':                    {'type': 'strikeCount', 'sourceUnit': 'strike', 'title': 'Lightning 1hr', 'sourceKey': 'lightning_strike_count_last_1hr'},
	'environment.lightning.count3hr':                    {'type': 'strikeCount', 'sourceUnit': 'strike', 'title': 'Lightning 3hrs', 'sourceKey': 'lightning_strike_count_last_3hr'},

	'time.time':                                         {'type': 'datetime', 'sourceUnit': 'epoch', 'kwargs': {'tz': '@timezone'}, 'title': 'Time', 'sourceKey': ('time', 'timestamp', 'day_start_local')},
	'time.hour':                                         {'type': 'time', 'sourceUnit': 'hr', 'title': 'Hour', 'sourceKey': 'local_hour'},
	'time.day':                                          {'type': 'time', 'sourceUnit': 'day', 'title': 'Day', 'sourceKey': ('local_day', 'day_num')},
	'time.month':                                        {'type': 'time', 'sourceUnit': 'month', 'title': 'Month', 'sourceKey': ('local_day', 'month_num')},

	'device.sampleInterval.wind':                        {'type': 'interval', 'sourceUnit': 's', 'title': 'Sample Interval', 'sourceKey': 'windSampleInterval', 'property': '@windSampleInterval'},
	'device.sampleInterval.report':                      {'type': 'interval', 'sourceUnit': 'min', 'title': 'Report Interval', 'sourceKey': 'reportInterval', 'property': '@period'},

	'device.status.battery':                             {'type': 'voltage', 'sourceUnit': 'volts', 'title': 'Battery', 'sourceKey': 'battery'},
	'device.status':                                     {'type': 'status'},
	'device.status.*.serial':                            {'sourceUnit': 'str', 'title': 'Name', 'sourceKey': ['hub_sn', 'serial_number']},
	'device.status.*.type':                              {'@metaKey': True, 'sourceKey': 'serial_number'},
	'device.status.*.uptime':                            {'sourceUnit': 's', 'title': 'Uptime', 'sourceKey': 'uptime'},
	'device.status.*.firmware':                          {'sourceUnit': 'int', 'title': 'Firmware', 'sourceKey': 'battery'},
	'device.status.*.deviceRSSI':                        {'sourceUnit': 'rssi', 'title': 'Device Signal', 'sourceKey': 'rssi'},
	'device.status.*.RSSI':                              {'sourceUnit': 'rssi', 'title': 'Hub Signal', 'sourceKey': 'hub_rssi'},
	'device.status.*.sensorStatus':                      {'sourceUnit': 'str', 'title': 'Sensor Status', 'sourceKey': 'sensor_status'},
	'device.status.*.debug':                             {'sourceUnit': 'bool', 'title': 'Debug', 'sourceKey': 'debug'},
	'device.status.*.resetFlags':                        {'sourceUnit': 'str', 'title': 'Reset Flags', 'sourceKey': 'reset_flags'},
	'environment.condition.icon':                        {'type':         'icon', 'sourceUnit': 'str', 'title': 'Condition Icon', 'sourceKey': 'icon', 'iconType': 'glyph', 'glyphFont': 'WeatherIcons', 'aliases': '@conditionIcon',
	                                                      'forecastOnly': True},
	'environment.condition.condition':                   {'type': 'description', 'sourceUnit': 'str', 'title': 'Condition', 'sourceKey': 'conditions', 'forecastOnly': True},
	'environment.sunrise':                               {'type': 'date', 'sourceUnit': 'epoch', 'title': 'Sunrise', 'sourceKey': 'sunrise', 'forecastOnly': True},
	'environment.sunset':                                {'type': 'date', 'sourceUnit': 'epoch', 'title': 'Sunset', 'sourceKey': 'sunset', 'forecastOnly': True},

	'@period':                                           {'key': 'device.sampleInterval.report', 'attr': 'period', 'default': {'value': 1, 'unit': 'min'}, 'allowZero': False},
	'@windSampleInterval':                               {'key': 'device.sampleInterval.wind', 'default': {'value': 3, 'unit': 's'}},
	'@timezone':                                         {'key': 'time.timezone', 'attr': 'timezone', 'default': {'value': config.tz}, 'setter': '@plugins'},
	'@timestamp':                                        {'key': 'time.time', 'attr': 'timestamp', 'default': {'value': datetime.now, 'kwargs': {'tz': '@timezone'}}, 'setter': '@source'},
	'@hubSerial':                                        {'sourceKey': ['hub_sn', 'serial_number'], 'key': 'device.status.@.serial'},
	'@deviceSerial':                                     {'sourceKey': 'serial_number', 'key': 'device.status.@.serial'},
	'@latitude':                                         {'sourceKey': 'latitude', 'attr': 'latitude', 'setter': '@plugins'},
	'@longitude':                                        {'sourceKey': 'longitude', 'attr': 'longitude', 'setter': '@plugins'},
	# '@source':                                           {'sourceKey': [] 'source', 'key': 'device.status.@.source'},
	# '@wind':                                             {'type': 'vector', 'source': ['environment.wind.speed', 'environment.wind.direction.direction'], 'title': 'Wind'}

	'ignored':                                           ['wind_direction_cardinal', 'lightning_strike_last_distance_msg', 'is_precip_local_day_rain_check', 'is_precip_local_yesterday_rain_check'],

	'keyMaps':                                           {
		'obs_st':  ['time.time', 'environment.wind.speed.lull', 'environment.wind.speed.speed', 'environment.wind.speed.gust', 'environment.wind.direction.direction',
		            'device.sampleInterval.wind', 'environment.pressure.pressure', 'environment.temperature.temperature', 'environment.humidity.humidity',
		            'environment.light.illuminance', 'environment.light.uvi', 'environment.light.irradiance', 'environment.precipitation.precipitation',
		            'environment.precipitation.type', 'environment.lightning.distance', 'environment.lightning.lightning',
		            'device.status.battery', 'device.sampleInterval.report'],

		'obs_sky': ['time.time', 'environment.light.illuminance', 'environment.light.uvi', 'environment.precipitation.precipitation',
		            'environment.wind.speed.lull', 'environment.wind.speed.speed', 'environment.wind.speed.gust', 'environment.wind.direction.direction',
		            'device.status.battery', 'device.sampleInterval.report', 'environment.light.irradiance', 'environment.precipitation.type',
		            'device.sampleInterval.wind'],

		'obs_air': ['time.time', 'environment.pressure.pressure', 'environment.temperature.temperature', 'environment.humidity.humidity',
		            'environment.lightning.lightning', 'environment.lightning.distance', 'device.status.battery', 'device.sampleInterval.report'],
	},
	'dataMaps':                                          {
		'realtime': ['current_conditions', 'obs>0'],
		'daily':    ['forecast>daily'],
		'hourly':   ['forecast>hourly'],
		'log':      ['obs'],
	},
	'aliases':                                           {
		'@conditionIcon':     {
			'wind':                        '',
			'rain':                        '',
			'cloud':                       '',
			'pressure':                    '',
			'humidity':                    '',
			'lightning':                   '',
			'temperature':                 '',
			'light':                       '',
			'condition':                   '',
			'clear-day':                   '',
			'clear-night':                 '',
			'cloudy':                      '',
			'foggy':                       '',
			'partly-cloudy-day':           '',
			'partly-cloudy-night':         '',
			'possibly-rainy-day':          '',
			'possibly-rainy-night':        '',
			'possibly-sleet-day':          '',
			'possibly-sleet-night':        '',
			'possibly-snow-day':           '',
			'possibly-snow-night':         '',
			'possibly-thunderstorm-day':   '',
			'possibly-thunderstorm-night': '',
			'rainy':                       '',
			'sleet':                       '',
			'snow':                        '',
			'thunderstorm':                '',
			'windy':                       ''
		},
		'@precipitationIcon': {
			'chance-rain':  '',
			'chance-snow':  '',
			'chance-sleet': '',
		}
	}
	# 'calculations':                                      {
	#   'feelsLike': {
	#     'vars': {
	#       'temp':      'environment.temperature.temperature',
	#       'heatIndex': 'environment.temperature.heatIndex',
	#       'windChill': 'environment.temperature.windChill'
	#     },
	#     'calc': lambda obs, vars: vars['heatIndex'] if (vars['temp'] > Temperature.Fahrenheit(80) and vars['humidity'] < 0.4) else False or vars['windChill'] if vars['temp'] < Temperature.Fahrenheit(50) else False
	#                                                                                                                                                                                                       or vars['temp']
	#   }
	# }
}


def getCalculatedValue(obs, key):
	args = obs.translator.calculations[key]
	vars = {k: obs[v] for k, v in args['vars'].items()}
	return args['calc'](obs, vars)


def getMetaKey(key, data):
	meta = unitDefinitions[key]
	newKey = meta['key']
	value = data[meta['sourceKey']]
	if '@' in newKey:
		newKey = newKey.replace('@', value)
	return newKey


class WeatherFlow(REST, realtime=True, daily=True, hourly=True, logged=True):
	# _stationID: int = int(config.plugins.wf['StationID'])
	# _deviceID: int = int(config.plugins.wf['DeviceID'])
	urls: WFURLs = WFURLs()
	translator = unitDefinitions
	name = 'WeatherFlow'

	def __init__(self, *args, **kwargs):
		super(WeatherFlow, self).__init__(*args, **kwargs)
		for item in messageTypes.values():
			item.source = self
		self.udp = UDPSocket(self, port=50222)
		self.udp.handler.connectSlot(self.socketUpdate)

	@property
	def timezone(self):
		return self._timezone

	@timezone.setter
	def timezone(self, value):
		if isinstance(value, str):
			self._timezone = ZoneInfo(value)
		self._timezone = value

	def socketUpdate(self, datagram):
		if datagram['type'] in messageTypes:
			messageType = messageTypes[datagram['type']]
			message = messageType(datagram)
			message.pop('source', None)
			self.realtime.update(message)

	def start(self):
		# pass
		ScheduledEvent(interval=timedelta(seconds=45), singleShot=True, func=self.getHistorical, fireImmediately=True).start()
		self.realtimeTimer = ScheduledEvent(self.urls.realtime.refreshInterval, self.getRealtime)
		self.realtimeTimer.start(True)

		if config.plugins.wf.getboolean('socketUpdates'):
			self.udp.start()

		self.forecastTimer = ScheduledEvent(timedelta(minutes=15), self.getForecast)
		self.forecastTimer.start(True)

		self.loggingTimer = ScheduledEvent(timedelta(minutes=1), self.logValues)
		self.loggingTimer.start(False)

	# def normalizeData(self, rawData):

	# try:
	# 	if 'forecast' in rawData:
	# 		source = rawData['forecast']
	# 		data = {'data': {}}
	# 		return data
	# 	if 'obs' in rawData:
	# 		obs = rawData.pop('obs')
	# 		source = [rawData.pop('source'), rawData.pop('device_id'), rawData.pop('type')]
	# 		data = {'source': source}
	# 		if len(obs) == 0:
	# 			raise ValueError(rawData['status']['status_message'])
	# 		elif len(obs) == 1:
	# 			data['data'] = obs[0]
	# 		else:
	# 			data['data'] = obs
	# 	return data
	# except ValueError as e:
	# 	log.error(e)
	# 	return {}

	async def getRealtime(self):
		data = await self.getData(self.urls.realtime)
		await self.realtime.asyncUpdate(data, source=[self.name, self.urls.realtime])

	async def getForecast(self):
		data = await self.getData(self.urls.forecast)
		data['source'] = [self.name, self.urls.forecast]
		data.pop('realtime', None)
		for observation in self.observations:
			if observation.dataName in data:
				await observation.asyncUpdate(data)

	# self.realtime.update(data)
	# if 'daily' in data:
	# 	self.daily.update(data)
	# if 'hourly' in data:
	# 	self.hourly.update(data)

	async def getHistorical(self, start: datetime = None, end: datetime = None):
		if end is None:
			end = datetime.now(tz=config.tz)
		if start is None:
			start = end - timedelta(days=.5)
		params = self.urls.historical.params.copy()
		start = start.astimezone(tz=timezone.utc)
		end = end.astimezone(tz=timezone.utc)
		params.update({'time_start': int(start.timestamp()), 'time_end': int(end.timestamp())})
		data = await self.getData(self.urls.historical, params=params)
		source = [self.urls.historical.name]
		# if 'source' in data:
		# 	source.append(data.pop('source'))
		# if 'device_id' in data:
		# 	source.append(data.pop('device_id'))
		if 'type' in data:
			source.append(data.pop('type'))
		await self.log.asyncUpdate(data, source=source)

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
# 		self._params.update({"station_id": config.plugins.wf['stationID'], **kwargs})
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


# while True:
# 	await asyncio.sleep(1)


class ErrorNoConnection(Exception):

	def __init__(self, data, *args, **kwargs):
		logging.error(data)
		super(ErrorNoConnection, self).__init__(*args, **kwargs)

	pass


__plugin__ = WeatherFlow

if __name__ == '__main__':
	logging.getLogger().setLevel(logging.DEBUG)
	wf = WeatherFlow()
	wf.getForecast()
	print(wf.hourly[datetime.now()])
