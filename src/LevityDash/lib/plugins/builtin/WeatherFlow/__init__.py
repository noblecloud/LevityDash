
from LevityDash.lib.plugins.schema import LevityDatagram, SchemaSpecialKeys as tsk
from LevityDash.lib.plugins.web.socket import UDPSocket
from LevityDash.lib.plugins.plugin import ScheduledEvent
from LevityDash.lib.plugins.web import Auth, AuthType, Endpoint, REST, URLs
from LevityDash.lib.utils.shared import LOCAL_TIMEZONE

from datetime import datetime, timedelta, timezone

__all__ = ["WeatherFlow", '__plugin__']


class WFURLs(URLs, base='swd.weatherflow.com/swd'):
	auth = Auth(authType=AuthType.PARAMETER, authData={'token': '{token}'})

	rest = Endpoint(url='rest', auth=auth, protocol='https', refreshInterval=timedelta(minutes=15))
	websocket = Endpoint(url='data', protocol='wss')

	stationObservation = Endpoint(base=rest, url=f'observations/station/{{stationID}}')
	deviceObservation = Endpoint(base=rest, url=f'observations/device/{{deviceID}}')
	station = Endpoint(base=rest, url='stations')

	forecast = Endpoint(base=rest, url='better_forecast', params={'station_id': '{{stationID}}'}, period=[timedelta(hours=1), timedelta(days=1)])

	realtime = Endpoint(base=stationObservation)
	historical = Endpoint(base=deviceObservation)


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


schema = {
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
	'environment.precipitation.precipitationNearCast':   {'type': 'precipitationRate', 'sourceUnit': ['mm', '@period'], 'title': 'Rate', 'sourceKey': 'precip_nc'},
	'environment.precipitation.hourly':                  {'type': 'precipitationHourly', 'sourceUnit': ['mm', 'hr'], 'title': 'Hourly', 'sourceKey': 'precip_accum_last_1hr'},
	'environment.precipitation.daily':                   {'type': 'precipitationDaily', 'sourceUnit': ['mm', 'day'], 'title': 'Daily', 'sourceKey': 'precip_accum_local_day'},
	'environment.precipitation.dailyNearCast':           {'type': 'precipitationDaily', 'sourceUnit': ['mm', 'day'], 'title': 'Daily', 'sourceKey': 'precip_accum_local_day_final'},
	'environment.precipitation.icon':                    {
		'type':    'icon', 'sourceUnit': 'str', 'title': 'Precipitation Icon', 'forecastOnly': True, 'sourceKey': 'precip_icon', 'iconType': 'glyph', 'glyphFont': 'WeatherIcons',
		'aliases': '@precipitationIcon'
	},
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

	'timestamp':                                         {'type': 'datetime', 'sourceUnit': 'epoch', 'kwargs': {'tz': '@timezone'}, 'title': 'Time', 'sourceKey': ('time', 'timestamp', 'day_start_local'), tsk.metaData: '@timestamp'},
	'time.hour':                                         {'type': 'time', 'sourceUnit': 'hr', 'title': 'Hour', 'sourceKey': 'local_hour', tsk.metaData: '@hour'},
	'time.day':                                          {'type': 'time', 'sourceUnit': 'day', 'title': 'Day', 'sourceKey': ('local_day', 'day_num'), tsk.metaData: '@day'},
	'time.month':                                        {'type': 'time', 'sourceUnit': 'month', 'title': 'Month', 'sourceKey': 'month_num', tsk.metaData: '@month'},

	'device.@deviceSerial.sampleInterval.wind':          {'type': 'interval', 'sourceUnit': 's', 'title': 'Sample Interval', 'sourceKey': 'windSampleInterval', 'property': '@windSampleInterval'},
	'device.@deviceSerial.sampleInterval.report':        {'type': 'interval', 'sourceUnit': 'min', 'title': 'Report Interval', 'sourceKey': 'reportInterval', 'property': '@period'},

	'device.@deviceSerial.battery':                      {'type': 'voltage', 'sourceUnit': 'volts', 'title': 'Battery', 'sourceKey': ('battery', 'voltage')},
	'device.@deviceSerial':                              {'type': 'status'},
	'device.@deviceSerial.serial':                       {'sourceUnit': 'str', 'title': 'Name', 'sourceKey': ['hub_sn', 'serial_number']},

	'device.@deviceSerial.uptime':                       {'sourceUnit': 's', 'title': 'Uptime', 'sourceKey': 'uptime'},
	'device.@deviceSerial.firmware':                     {'sourceUnit': 'int', 'title': 'Firmware', 'sourceKey': 'battery'},
	'device.@deviceSerial.deviceRSSI':                   {'sourceUnit': 'rssi', 'title': 'Device Signal', 'sourceKey': 'rssi'},
	'device.@deviceSerial.RSSI':                         {'sourceUnit': 'rssi', 'title': 'Hub Signal', 'sourceKey': 'hub_rssi'},
	'device.@deviceSerial.sensorStatus':                 {'sourceUnit': 'str', 'title': 'Sensor Status', 'sourceKey': 'sensor_status'},
	'device.@deviceSerial.debug':                        {'sourceUnit': 'bool', 'title': 'Debug', 'sourceKey': 'debug'},
	'device.@deviceSerial.resetFlags':                   {'sourceUnit': 'str', 'title': 'Reset Flags', 'sourceKey': 'reset_flags'},
	'environment.condition.icon':                        {
		'type':         'icon', 'sourceUnit': 'str', 'title': 'Condition Icon', 'sourceKey': 'icon', 'iconType': 'glyph', 'glyphFont': 'WeatherIcons', 'aliases': '@conditionIcon',
		'forecastOnly': True
	},
	'environment.condition.condition':                   {'type': 'description', 'sourceUnit': 'str', 'title': 'Condition', 'sourceKey': 'conditions', 'forecastOnly': True},
	'environment.sunrise':                               {'type': 'date', 'sourceUnit': 'epoch', 'title': 'Sunrise', 'sourceKey': 'sunrise', 'forecastOnly': True},
	'environment.sunset':                                {'type': 'date', 'sourceUnit': 'epoch', 'title': 'Sunset', 'sourceKey': 'sunset', 'forecastOnly': True},
	'@type':                                             {'sourceKey': 'type', tsk.metaData: True, tsk.sourceData: True},
	'@period':                                           {
		'key':        'device.@deviceSerial.sampleInterval.report',
		'attr':       'period',
		'default':    {'value': 1, 'unit': 'min'},
		'allowZero':  False,
		'sourceKey':  'bucket_step_minutes',
		tsk.metaData: True
	},
	'@windSampleInterval':                               {'key': 'device.@deviceSerial.sampleInterval.wind', 'default': {'value': 3, 'unit': 's'}},
	'@timezone':                                         {'dataType': timezone, 'key': 'timezone', 'attr': 'timezone', 'default': {'value': LOCAL_TIMEZONE}, 'setter': '@plugin', tsk.metaData: True},
	'@timestamp':                                        {'key': 'timestamp', 'attr': 'timestamp', 'default': {'value': datetime.now, 'kwargs': {'tz': '@timezone'}}, 'setter': '@source', tsk.metaData: True},
	'@hubSerial':                                        {'sourceKey': ['hub_sn', 'serial_number'], 'key': 'device.@deviceSerial.serial', tsk.sourceData: True},
	'@deviceSerial':                                     {'sourceKey': 'serial_number', 'key': 'device.@deviceSerial.serial', tsk.sourceData: True, 'alt': '@deviceID'},
	'@deviceID':                                         {'sourceKey': 'device_id', 'key': 'device.@deviceID.deviceID', tsk.sourceData: True, 'alt': '@deviceSerial'},
	'@latitude':                                         {'sourceKey': 'latitude', 'attr': 'latitude', 'setter': '@plugin', tsk.metaData: True},
	'@longitude':                                        {'sourceKey': 'longitude', 'attr': 'longitude', 'setter': '@plugin', tsk.metaData: True},
	'meta@stationID':                                    {'sourceKey': 'station_id', 'filter.match': '@plugin', tsk.metaData: True},
	# '@source':                                           {'sourceKey': [] 'source', 'key': 'device.status.@.source'},
	# '@wind':                                             {'type': 'vector', 'source': ['environment.wind.speed', 'environment.wind.direction.direction'], 'title': 'Wind'}

	'ignored':                                           ['wind_direction_cardinal', 'lightning_strike_last_distance_msg', 'is_precip_local_day_rain_check', 'is_precip_local_yesterday_rain_check', 'firmware_revision'],

	'keyMaps':                                           {
		'obs_st': {
			'obs': {
				18: (basic := ['timestamp', 'environment.wind.speed.lull', 'environment.wind.speed.speed', 'environment.wind.speed.gust', 'environment.wind.direction.direction',
					'device.@deviceSerial.sampleInterval.wind', 'environment.pressure.pressure', 'environment.temperature.temperature', 'environment.humidity.humidity',
					'environment.light.illuminance', 'environment.light.uvi', 'environment.light.irradiance', 'environment.precipitation.precipitation',
					'environment.precipitation.type', 'environment.lightning.distance', 'environment.lightning.lightning',
					'device.@deviceSerial.battery', 'device.@deviceSerial.sampleInterval.report']),
				22: [*basic,
					'environment.precipitation.daily',
					'environment.precipitation.precipitationNearCast',
					'environment.precipitation.dailyNearCast',
					'environment.yesterday.precipitation.analysis'
				]
			},

		},

		'obs_sky':       {
			'obs': {
				iter: ['timestamp', 'environment.light.illuminance', 'environment.light.uvi', 'environment.precipitation.precipitation',
					'environment.wind.speed.lull', 'environment.wind.speed.speed', 'environment.wind.speed.gust', 'environment.wind.direction.direction',
					'device.@deviceSerial.battery', 'device.@deviceSerial.sampleInterval.report', 'environment.light.irradiance', 'environment.precipitation.type',
					'device.@deviceSerial.sampleInterval.wind']
			}
		},

		'obs_air':       {
			'obs': {
				iter: ['timestamp', 'environment.pressure.pressure', 'environment.temperature.temperature', 'environment.humidity.humidity',
					'environment.lightning.lightning', 'environment.lightning.distance', 'device.@deviceSerial.battery', 'device.@deviceSerial.sampleInterval.report']
			}
		},

		'rapid_wind':    {'ob': ['timestamp', 'environment.wind.speed.speed', 'environment.wind.direction.direction']},
		'device_status': {filter: ['type', 'serial_number', 'hub_sn', 'timestamp', 'uptime', 'voltage', 'rssi', 'hub_rssi']},
		'hub_status':    {filter: ['type', 'serial_number', 'timestamp', 'uptime', 'rssi']}
	},
	'dataMaps':                                          {
		'realtime':      {
			'realtime': ('obs', 0)
		},
		'forecast':      {
			'realtime': 'current_conditions',
			'hourly':   ('forecast', 'hourly', 0),
			'daily':    ('forecast', 'daily', 0)
		},
		'historical':    {'log': ('obs', 0)},
		'obs_st':        {'realtime': ('obs', 0)},
		'obs_sky':       {'realtime': ('obs', 0)},
		'obs_air':       {'realtime': ('obs', 0)},
		'rapid_wind':    {'realtime': 'ob'},
		'device_status': {'realtime': ()},
		'hub_status':    {'realtime': ()}
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
}


class WeatherFlow(REST, realtime=True, daily=True, hourly=True, logged=True):
	urls: WFURLs = WFURLs()
	schema = schema
	name = 'WeatherFlow'

	def __init__(self, *args, **kwargs):
		super(WeatherFlow, self).__init__(*args, **kwargs)
		self.udp = UDPSocket(self, port=50222)
		self.udp.handler.connectSlot(self.socketUpdate)

	@property
	def timezone(self):
		return self._timezone

	@timezone.setter
	def timezone(self, value):
		if isinstance(value, str):
			from zoneinfo import ZoneInfo
			self._timezone = ZoneInfo(value)
		self._timezone = value

	def socketUpdate(self, datagram):
		message = LevityDatagram(datagram, schema=self.schema, sourceData={'socket': self.udp})
		self.pluginLog.verbose(f'{self.name} received {message}')
		for observation in self.observations:
			if observation.dataName in message:
				observation.update(message)

	def start(self):
		if self.config['socketUpdates']:
			self.udp.start()

		self.realtimeTimer = ScheduledEvent(self.urls.realtime.refreshInterval, self.getRealtime)
		self.realtimeTimer.start(True)
		# self.realtimeTimer.start(immediately=False, startTime=self.urls.realtime.refreshInterval.total_seconds() / 2)

		self.forecastTimer = ScheduledEvent(timedelta(minutes=15), self.getForecast)
		self.forecastTimer.start(True)

		self.loggingTimer = ScheduledEvent(timedelta(minutes=1), self.logValues)
		self.loggingTimer.start(False)
		self.__running = True

		if self.config['fetchHistory']:
			ScheduledEvent(interval=timedelta(seconds=30), singleShot=True, func=self.getHistorical, fireImmediately=False).start()

	async def getRealtime(self):
		urls = self.urls
		endpoint = urls.realtime
		data = await self.getData(endpoint)
		await self.realtime.asyncUpdate(data, source=[self.name, self.urls.realtime])

	async def getForecast(self):
		data = await self.getData(self.urls.forecast)
		for observation in self.observations:
			if observation.dataName in data:
				await observation.asyncUpdate(data)

	async def getHistorical(self, start: datetime = None, end: datetime = None):
		if end is None:
			end = datetime.now(tz=LOCAL_TIMEZONE)
		if start is None:
			start = end - timedelta(days=.5)
		params = self.urls.historical.params.copy()
		start = start.astimezone(tz=timezone.utc)
		end = end.astimezone(tz=timezone.utc)
		params.update({'time_start': int(start.timestamp()), 'time_end': int(end.timestamp())})
		data = await self.getData(self.urls.historical, params=params)
		await self.log.asyncUpdate(data)

	@property
	def messenger(self):
		return self._udpSocket


__plugin__ = WeatherFlow
