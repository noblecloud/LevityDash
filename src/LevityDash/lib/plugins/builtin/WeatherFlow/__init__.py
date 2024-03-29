import asyncio
from datetime import datetime, timedelta, timezone
from functools import partial
from json import dumps, loads
from typing import Callable

from aiohttp import ClientSession, ClientWebSocketResponse, WSMsgType

from LevityDash.lib.plugins.errors import InvalidData
from LevityDash.lib.plugins.schema import LevityDatagram, SchemaSpecialKeys as tsk
from LevityDash.lib.plugins.utils import ScheduledEvent
from LevityDash.lib.plugins.web import Auth, AuthType, Endpoint, REST, URLs
from LevityDash.lib.plugins.web.errors import APIError
from LevityDash.lib.plugins.web.socket_ import UDPSocket
from LevityDash.lib.utils.shared import LOCAL_TIMEZONE, Now

__all__ = ["WeatherFlow", '__plugin__']

class WFURLs(URLs, base='swd.weatherflow.com/swd'):
	auth = Auth(authType=AuthType.PARAMETER, authData={'token': '{token}'})

	rest = Endpoint(url='rest', auth=auth, protocol='https', refreshInterval=timedelta(minutes=15))
	websocket = Endpoint(url='data', protocol='wss')

	stationObservation = Endpoint(base=rest, url=f'observations/station/{{stationID}}')
	deviceObservation = Endpoint(base=rest, url=f'observations/device/{{deviceID}}')
	station = Endpoint(base=rest, url='stations')

	forecast = Endpoint(base=rest, url='better_forecast', params={'station_id': '{{stationID}}'}, period=[timedelta(hours=1), timedelta(days=1)])

	realtime = Endpoint(base=stationObservation, refreshInterval=timedelta(minutes=5))
	historical = Endpoint(base=deviceObservation)


schema = {
	'environment.temperature':                           {'type': 'temperature', 'sourceUnit': 'c'},
	'environment.temperature.temperature':               {'title': 'Temperature', 'sourceKey': 'air_temperature'},
	'environment.temperature.dewpoint':                  {'title': 'Dew Point', 'sourceKey': 'dew_point'},
	'environment.temperature.wetBulb':                   {'title': 'Wet Bulb', 'sourceKey': 'wet_bulb_temperature'},
	'environment.temperature.wetBulbGlobe':              {'title': 'Wet Bulb Globe', 'sourceKey': ['wet_bulb_temperature_globe', 'wet_bulb_globe_temperature']},
	'environment.temperature.feelsLike':                 {'title': 'Feels Like', 'sourceKey': 'feels_like', 'calculation': 'feelsLike'},
	'environment.temperature.heatIndex':                 {'title': 'Heat Index', 'sourceKey': 'heat_index'},
	'environment.temperature.windChill':                 {'title': 'Wind Chill', 'sourceKey': 'wind_chill'},
	'environment.temperature.deltaT':                    {'title': 'Delta T', 'sourceKey': 'delta_t'},
	'environment.temperature.high':                      {'title': 'Temperature High', 'sourceKey': 'air_temp_high', 'timeseriesOnly': True},
	'environment.temperature.low':                       {'title': 'Temperature Low', 'sourceKey': 'air_temp_low', 'timeseriesOnly': True},

	'environment.humidity.humidity':                     {'type': 'humidity', 'sourceUnit': '%', 'title': 'Humidity', 'sourceKey': 'relative_humidity'},

	'environment.light.uvi':                             {'type': 'index', 'sourceUnit': 'uvi', 'title': 'UVI', 'sourceKey': 'uv'},
	'environment.light.irradiance':                      {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Irradiance', 'sourceKey': 'solar_radiation'},
	'environment.light.illuminance':                     {'type': 'illuminance', 'sourceUnit': 'lux', 'title': 'Illuminance', 'sourceKey': 'brightness'},
	'environment.pressure':                              {'type': 'pressure', 'sourceUnit': 'mb'},
	'environment.pressure.pressure':                     {'title': 'Pressure', 'sourceKey': 'barometric_pressure'},
	'environment.pressure.pressureAbsolute':             {'title': 'Absolute', 'sourceKey': 'station_pressure'},
	'environment.pressure.pressureSeaLevel':             {'title': 'Sea Level', 'sourceKey': 'sea_level_pressure'},
	# 'environment.pressure.airDensity':                   {'type': 'airDensity', 'sourceUnit': ['kg', 'm³'], 'title': 'Air Density', 'sourceKey': 'air_density'},
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
	'environment.precipitation.hourly':                  {'type': 'precipitationHourly', 'sourceUnit': ['mm', 'hr'], 'title': 'Hourly', 'sourceKey': ('precip_accum_last_1hr', 'precip_total_1h')},
	'environment.precipitation.daily':                   {'type': 'precipitationDaily', 'sourceUnit': ['mm', 'day'], 'title': 'Daily', 'sourceKey': 'precip_accum_local_day'},
	'environment.precipitation.dailyNearCast':           {'type': 'precipitationDaily', 'sourceUnit': ['mm', 'day'], 'title': 'Daily', 'sourceKey': 'precip_accum_local_day_final'},
	'environment.precipitation.icon':                    {
		'type':    'icon', 'sourceUnit': 'str', 'title': 'Precipitation Icon', 'timeseriesOnly': True, 'sourceKey': 'precip_icon', 'iconType': 'glyph', 'iconPack': 'WeatherIcons',
		'aliases': '@precipitationIcon'
	},
	'environment.precipitation.time':                    {'type': 'time', 'sourceUnit': 'min', 'title': 'Minutes', 'sourceKey': 'precip_minutes_local_day'},
	'environment.precipitation.type':                    {'type': 'precipitationType', 'sourceUnit': '*', 'title': 'Precipitation Type', 'sourceKey': 'precip_type'},
	'environment.precipitation.analysis':                {'type': 'rainCheckType', 'sourceUnit': 'int', 'title': 'Type', 'sourceKey': 'precip_analysis_type'},
	'environment.precipitation.probability':             {'type': 'probability', 'sourceUnit': '%p', 'title': 'Precipitation Probability', 'sourceKey': 'precip_probability'},
	'environment.precipitation.description':             {'type': 'description', 'sourceUnit': 'str', 'title': 'Precipitation Description', 'sourceKey': 'precip_description'},

	'environment.yesterday.precipitation.precipitation': {'type': 'precipitationDaily', 'sourceUnit': ['mm', 'day'], 'title': 'Yesterday', 'sourceKey': ('precip_accum_local_yesterday_final', 'precip_accum_local_yesterday')},
	'environment.yesterday.precipitation.time':          {'type': 'time', 'sourceUnit': 'min', 'title': 'Minutes Yesterday', 'sourceKey': 'precip_minutes_local_yesterday_final'},
	'environment.yesterday.precipitation.timeRaw':       {'type': 'time', 'sourceUnit': 'min', 'title': 'Minutes Yesterday Raw', 'sourceKey': 'precip_minutes_local_yesterday'},
	'environment.yesterday.precipitation.analysis':      {'type': 'rainCheckType', 'sourceUnit': 'int', 'title': 'Type Yesterday', 'sourceKey': 'precip_analysis_type_yesterday'},

	'environment.lightning.last':                        {'type': 'date', 'sourceUnit': 'epoch', 'title': 'Last Strike', 'sourceKey': ('lightning_strike_last_epoch', 'strike_last_epoch')},
	'environment.lightning.distance':                    {'type': 'length', 'sourceUnit': 'km', 'title': 'Last Strike Distance', 'sourceKey': ('lightning_strike_last_distance', 'strike_last_dist')},
	'environment.lightning.distanceAverage':             {'type': 'length', 'sourceUnit': 'km', 'title': 'Last Strike Distance', 'sourceKey': 'lightning_strike_last_distance_msg'},
	'environment.lightning.lightning':                   {'type': 'strikeCount', 'sourceUnit': 'strike', 'title': 'Strike Count', 'sourceKey': 'lightning_strike_count'},
	'environment.lightning.energy':                      {'type': 'energy', 'sourceUnit': 'int', 'title': 'Strike Energy', 'sourceKey': 'strikeEnergy'},
	'environment.lightning.count1hr':                    {'type': 'strikeCount', 'sourceUnit': 'strike', 'title': 'Lightning 1hr', 'sourceKey': ('lightning_strike_count_last_1hr', 'strike_count_1h')},
	'environment.lightning.count3hr':                    {'type': 'strikeCount', 'sourceUnit': 'strike', 'title': 'Lightning 3hrs', 'sourceKey': ('lightning_strike_count_last_3hr', 'strike_count_3h')},

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
		'type': 'icon', 'sourceUnit': 'str', 'title': 'Condition Icon', 'sourceKey': 'icon', 'iconType': 'glyph', 'iconPack': 'WeatherIcons', 'aliases': '@conditionIcon'
	},
	'environment.condition.condition':                   {'type': 'description', 'sourceUnit': 'str', 'title': 'Condition', 'sourceKey': 'conditions'},
	'environment.sunrise':                               {'type': 'date', 'sourceUnit': 'epoch', 'title': 'Sunrise', 'sourceKey': 'sunrise', 'timeseriesOnly': True},
	'environment.sunset':                                {'type': 'date', 'sourceUnit': 'epoch', 'title': 'Sunset', 'sourceKey': 'sunset', 'timeseriesOnly': True},
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

	'ignored':                                           ['wind_direction_cardinal', 'lightning_strike_last_distance_msg',
	                                                      'is_precip_local_day_rain_check', 'is_precip_local_yesterday_rain_check', 'firmware_revision', 'air_density',
	                                                      'raining_minutes', 'pulse_adj_ob_time', 'pulse_adj_ob_wind_avg', 'pulse_adj_ob_temp'
	                                                      ],

	'keyMaps':                                           {
		'obs_st':        {
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
		'evt_strike':    {'evt': ['timestamp', 'environment.lightning.distance', ...]},
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
		'summary':       {'realtime': ()},
		'historical':    {'log': ('obs', 0)},
		'obs_st':        {'realtime': ('obs', 0)},
		'obs_sky':       {'realtime': ('obs', 0)},
		'evt_strike':    {'realtime': 'evt'},
		'obs_air':       {'realtime': ('obs', 0)},
		'rapid_wind':    {'realtime': 'ob'},
		'device_status': {'realtime': ()},
		'hub_status':    {'realtime': ()}
	},
	'aliases':                                           {
		'@conditionIcon':     {
			'wind':                        'wi:strong-wind',
			'rain':                        'wi:rain',
			'cloud':                       'wi:cloud',
			'pressure':                    'wi:barometer',
			'humidity':                    'wi:humidity',
			'lightning':                   'wi:thunderstorm',
			'temperature':                 'wi:thermometer',
			'light':                       'wi:day-sunny',
			'condition':                   'wi:day-cloudy',
			'clear-day':                   'wi:day-sunny',
			'clear-night':                 'wi:night-clear',
			'cloudy':                      'wi:cloudy',
			'foggy':                       'wi:fog',
			'partly-cloudy-day':           'wi:day-sunny-overcast',
			'partly-cloudy-night':         'wi:night-alt-cloudy',
			'possibly-rainy-day':          'wi:day-rain',
			'possibly-rainy-night':        'wi:night-alt-rain',
			'possibly-sleet-day':          'wi:day-sleet',
			'possibly-sleet-night':        'wi:night-alt-sleet',
			'possibly-snow-day':           'wi:day-snow',
			'possibly-snow-night':         'wi:night-alt-snow-wind',
			'possibly-thunderstorm-day':   'wi:day-thunderstorm',
			'possibly-thunderstorm-night': 'wi:night-alt-thunderstorm',
			'rainy':                       'wi:rain',
			'sleet':                       'wi:sleet',
			'snow':                        'wi:snow',
			'thunderstorm':                'wi:thunderstorm',
			'windy':                       'wi:strong-wind'
		},
		'@precipitationIcon': {
			'chance-rain':  'wi:rain',
			'chance-snow':  'wi:snow',
			'chance-sleet': 'wi:sleet'
		}
	}
}

ignore = {'rapid_wind'}


class WFWebsocket:
	socket: ClientWebSocketResponse | None

	def __init__(self, plugin: 'WeatherFlow', *args, **kwargs):
		self.socket = None
		self.plugin = plugin
		self.loop = plugin.loop
		from secrets import token_urlsafe as genUUID
		self.uuid = genUUID(8)

	def _genMessage(self, messageType: str) -> str:
		return dumps(
			{
				"type":      messageType,
				"device_id": self.deviceID,
				"id":        self.uuid
			}
		)

	def start(self):
		self.loop.create_task(self.run())

	def stop(self):
		self.loop.create_task(self.astop())

	async def astop(self):
		if self.socket is None:
			return
		self.plugin.pluginLog.info('WeatherFlow: disconnecting Websocket')
		await self.socket.send_str(self._genMessage('listen_stop'))
		await self.socket.close()
		self.socket = None
		self.plugin.pluginLog.info('WeatherFlow: socket disconnected')

	async def run(self):
		self.plugin.pluginLog.info('WeatherFlow: connecting Websocket')
		async with ClientSession() as session:
			async with session.ws_connect(self.url, params=self.endpoint.params) as ws:
				self.socket = ws
				await self._open(ws)
				async for msg in ws:
					if msg.type == WSMsgType.TEXT:
						try:
							await self._handleMessage(msg.data)
						except Exception as e:
							self.plugin.pluginLog.exception(f'WeatherFlow: error handling message: {e}')
					elif msg.type == WSMsgType.ERROR:
						break
				else:
					self.plugin.pluginLog.info('WeatherFlow: socket closed')

	async def _handleMessage(self, data: str):
		datagram = loads(data)
		match datagram:
			case {'type': 'connection_opened'}:
				self.plugin.pluginLog.info("Websocket connected to WeatherFlow")
				return
			case {'type': 'ack', **rest}:
				self.plugin.pluginLog.info("Websocket acknowledged connection")
				return
			case {'summary': dict(summary), **rest}:
				summaryDatagram = LevityDatagram({'type': 'summary', **summary}, schema=self.plugin.schema, sourceData={'websocket': self})
				message = LevityDatagram(rest, schema=self.plugin.schema, sourceData={'websocket': self})
				message['realtime'].update(summaryDatagram['realtime'])
				self.loop.call_soon(partial(self.plugin.observations.realtime.update, message))
			case dict(datagram) if 'type' in datagram:
				message = LevityDatagram(datagram, schema=self.plugin.schema, sourceData={'websocket': self})
				asyncio.create_task(self.plugin.observations.realtime.asyncUpdate(message))
			case {'type': 'connection_closed'}:
				self.plugin.pluginLog.info("Websocket disconnected from WeatherFlow")
			case _:
				self.plugin.pluginLog.warning(f"Unknown message from WeatherFlow: {datagram}")

	@property
	def running(self) -> bool:
		if self.socket is None:
			return False
		return self.socket.closed is False

	@property
	def url(self):
		return self.plugin.urls.websocket.url

	@property
	def endpoint(self):
		return self.plugin.urls.websocket

	@property
	def deviceID(self):
		return self.plugin.config['deviceID']

	async def _open(self, ws):
		await ws.send_str(self._genMessage('listen_start'))
		await ws.send_str(self._genMessage('listen_rapid_start'))


_enableMessage = ("Enable WeatherFlow?  "
                  "This will require an authentication token and a Tempest Weather station to connect.  "
                  "You can find more information at https://levitydash.app/#/plugin_config?id=weatherflowtempest")

_defaultConfig = f""";All independent configs must have a plugin section

[plugin]
enabled = @ask(bool:False).message({_enableMessage})
token = @ask(str:).message(Enter Token)
stationID = @ask(str:).message(Enter Station ID)
deviceID = @ask(str:).message(Enter Device ID)
socketUpdates = @ask(bool:True).message(Enable Socket Updates?)
socketType = @askChoose(str:websocket,udp).message(Select a socket type)
fetchHistory = @ask(bool:False).message(Enable History Fetching?)
defaultFor = temperature wind pressure humidity light lightning
"""


class WeatherFlow(REST, realtime=True, daily=True, hourly=True, logged=True):
	urls: WFURLs = WFURLs()
	schema = schema
	name = 'WeatherFlow'
	windIndex = 0

	__defaultConfig__ = _defaultConfig
	__configRequired = ['stationID', 'deviceID', 'token']

	realtimeTimer: ScheduledEvent
	forecastTimer: ScheduledEvent
	loggingTimer: ScheduledEvent

	def __init__(self, *args, **kwargs):
		super(WeatherFlow, self).__init__(*args, **kwargs)
		self.udp = UDPSocket(self, port=50222)
		self.udp.handler.connectSlot(self.socketUpdate)
		self.websocket = WFWebsocket(self)

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
		self.__logItem(message)
		for observation in self.observations:
			if observation.dataName in message:
				observation.update(message)

	def __logItem(self, message: LevityDatagram):
		messageType = message.metaData.get('@type', 'unknown')
		if messageType == 'rapid_wind':
			self.windIndex += 1
			if self.windIndex < 20:
				return
			self.windIndex = 0
		self.pluginLog.verbose(f'{self.name} received {message}', verbosity=5)

	def start(self):

		self.pluginLog.info('WeatherFlow: starting')

		async def async_bootstrap():
			loop = self.loop

			if self.config['socketUpdates']:
				section = self.config.default_section
				if self.config.getOrSet(section, 'socketType', 'web') == 'web':
					ScheduledEvent(Now(), self.websocket.start, singleShot=True, loop=loop).start()
				else:
					ScheduledEvent(Now(), self.udp.start, singleShot=True, loop=loop).start()

			realtimeRefreshInterval = self.urls.realtime.refreshInterval
			self.realtimeTimer = ScheduledEvent(realtimeRefreshInterval, self.getRealtime, loop=loop).start()
			self.forecastTimer = ScheduledEvent(timedelta(minutes=15), self.getForecast, loop=loop).start()
			self.loggingTimer = ScheduledEvent(timedelta(minutes=1), self.logValues, loop=loop).schedule()

			if self.config['fetchHistory']:
				ScheduledEvent(timedelta(hours=6), self.getHistorical, loop=loop).delayedStart(timedelta(seconds=10))

			self.pluginLog.info('WeatherFlow: started')
			await self.future

		def bootstrap():
			self._task = async_bootstrap()
			self.loop.run_until_complete(self._task)
			del self.loop
			self.pluginLog.info('WeatherFlow: shutdown complete')

		self.loop.run_in_executor(None, bootstrap)

		return self

	def stop(self, callback: Callable = None):
		self.pluginLog.info('WeatherFlow: stopping')

		async def continue_shutdown():
			self.future.set_result(True)
			self.future.cancel()
			await self.loop.shutdown_asyncgens()
			ScheduledEvent.cancelAll(self)
			try:
				await self.websocket.asyncStop()
			except AttributeError:
				pass
			try:
				self.udp.stop()
			except AttributeError:
				pass

		asyncio.run_coroutine_threadsafe(continue_shutdown(), self.loop)
		self.pluginLog.info('WeatherFlow: starting shutdown')

	async def getRealtime(self):
		urls = self.urls
		endpoint = urls.realtime
		try:
			data = await self.getData(endpoint)
			asyncio.create_task(self.realtime.asyncUpdate(data, source=[self.name, self.urls.realtime]))
		except TimeoutError as e:
			self.pluginLog.warning(f'WeatherFlow: realtime request timed out: {e}')
			self.realtimeTimer.retry(timedelta(minutes=1))
		except InvalidData as e:
			self.pluginLog.error(f'WeatherFlow: realtime request failed')
			self.pluginLog.exception(e)
		except APIError as e:
			self.pluginLog.exception(e)
		except Exception as e:
			self.pluginLog.exception(e)

	async def getForecast(self):
		try:
			data = await self.getData(self.urls.forecast)
			for obs in self.observations:
				if obs.dataName in data:
					obs.update(data)
		except TimeoutError as e:
			self.pluginLog.warning(f'WeatherFlow: forecast request timed out: {e}')
			self.forecastTimer.retry(timedelta(minutes=1))
		except InvalidData as e:
			self.pluginLog.error(f'WeatherFlow: realtime request failed')
			self.pluginLog.exception(e)
		except APIError as e:
			self.pluginLog.exception(e)
		except Exception as e:
			self.pluginLog.exception(e)

	async def getHistorical(self, start: datetime = None, end: datetime = None):
		# TODO: Investigate possible crashing bug on first scheduled run after launch
		#       run.  This has only been observed on some hardware
		if end is None:
			end = datetime.now(tz=LOCAL_TIMEZONE)
		if start is None:
			start = end - timedelta(days=2)
		params = self.urls.historical.params.copy()
		start = start.astimezone(tz=timezone.utc)
		end = end.astimezone(tz=timezone.utc)
		params.update({'time_start': int(start.timestamp()), 'time_end': int(end.timestamp())})
		try:
			data = await self.getData(self.urls.historical, params=params)
			await self.log.asyncUpdate(data)
		except TimeoutError as e:
			self.pluginLog.warning(f'WeatherFlow: historical request timed out: {e}')
			self.loggingTimer.retry(timedelta(minutes=1))
		except InvalidData as e:
			self.pluginLog.error(f'WeatherFlow: realtime request failed')
			self.pluginLog.exception(e)
		except APIError as e:
			self.pluginLog.exception(e)
		except Exception as e:
			self.pluginLog.exception(e)

	@property
	def messenger(self):
		return self._udpSocket

	@property
	def running(self):
		return super().running or self.udp.running or self.websocket.running


__plugin__ = WeatherFlow
