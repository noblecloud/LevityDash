import asyncio
from datetime import datetime, timedelta, timezone
from typing import Callable

from LevityDash import LevityDashboard as LD
from LevityDash.lib.plugins.errors import InvalidData
from LevityDash.lib.plugins.schema import SchemaSpecialKeys as tsk
from LevityDash.lib.plugins.utils import ScheduledEvent
from LevityDash.lib.plugins.web import REST, URLs, Endpoint
from LevityDash.lib.plugins.web.errors import APIError
from LevityDash.lib.utils.shared import LOCAL_TIMEZONE


class OWMURLs(URLs, base='api.openweathermap.org/data/2.5'):
	params = {'lat': LD.config.lat, 'lon': LD.config.lon}
	weather = Endpoint(url='weather', params={'appid': '{apikey}', 'units': 'metric'})


schema = {
	'timestamp': {'type': 'datetime', 'sourceUnit': 'epoch', 'kwargs': {'tz': '@timezone'}, 'title': 'Time', 'sourceKey': 'dt', tsk.metaData: '@timestamp'},

	'environment.condition.condition': {'type': 'summary', 'sourceUnit': 'str', 'title': 'Condition', 'sourceKey': 'weather_description'},
	'environment.condition.icon': {
		'type': 'icon', 'sourceUnit': 'str', 'title': 'Condition Icon',
		'sourceKey': 'weather_icon', 'iconType': 'glyph', 'iconPack': 'WeatherIcons',
		'aliases': '@conditionIcons',
	},

	'environment.temperature': {'type': 'temperature', 'sourceUnit': 'c'},
	'environment.temperature.temperature': {'title': 'Temperature', 'sourceKey': 'temp'},
	'environment.temperature.feelsLike': {'title': 'Feels like', 'sourceKey': 'feels_like'},
	'environment.temperature.high': {'title': 'Temperature High', 'sourceKey': 'temp_max'},
	'environment.temperature.low': {'title': 'Temperature Low', 'sourceKey': 'temp_min'},
	# No sourceKey - the free Current Weather endpoint doesn't return
	# dewpoint directly, but ObservationDict.calculateMissing (observation.py)
	# unconditionally derives it from temperature+humidity whenever both are
	# present, regardless of what a plugin's schema declares. It has no
	# metadata to attach without an entry here (unlike calculateMissing's
	# very next check, for heatIndex, which does guard on the schema having
	# that key - dewpoint's guard appears to be missing, a separate
	# pre-existing inconsistency). This entry just needs to exist; it
	# inherits type/sourceUnit from the 'environment.temperature' parent.
	'environment.temperature.dewpoint': {'title': 'Dew Point'},

	'environment.humidity.humidity': {'type': 'humidity', 'sourceUnit': '%', 'title': 'Humidity', 'sourceKey': 'humidity'},

	'environment.pressure': {'type': 'pressure', 'sourceUnit': 'hPa'},
	'environment.pressure.pressure': {'title': 'Pressure', 'sourceKey': 'pressure'},

	'environment.visibility': {'type': 'distance', 'sourceUnit': 'm', 'title': 'Visibility', 'sourceKey': 'visibility'},

	'environment.wind': {'type': 'wind', 'sourceUnit': ('m', 's')},
	'environment.wind.speed.speed': {'title': 'Wind speed', 'sourceKey': 'wind_speed'},
	'environment.wind.speed.gust': {'title': 'Wind gust', 'sourceKey': 'wind_gust'},
	'environment.wind.direction': {'type': 'direction', 'sourceUnit': 'deg', 'title': 'Wind direction', 'sourceKey': 'wind_deg'},

	'environment.clouds.cover.cover': {'type': 'cloudCover', 'sourceUnit': '%', 'title': 'Cloud Cover', 'sourceKey': 'clouds'},

	'environment.light.sunrise': {'type': 'datetime', 'sourceUnit': 'epoch', 'kwargs': {'tz': '@timezone'}, 'title': 'Sunrise', 'sourceKey': 'sunrise'},
	'environment.light.sunset': {'type': 'datetime', 'sourceUnit': 'epoch', 'kwargs': {'tz': '@timezone'}, 'title': 'Sunset', 'sourceKey': 'sunset'},

	'@period': {
		'attr': 'period',
		'default': {'value': 1, 'unit': 'hr'},
		'allowZero': False,
		tsk.metaData: True,
	},

	'@timezone': {
		'dataType': timezone,
		'key': 'timezone',
		'attr': 'timezone',
		'default': {'value': LOCAL_TIMEZONE},
		'setter': '@plugin', tsk.metaData: True,
	},
	'@timestamp': {
		'key': 'timestamp', 'attr': 'timestamp', 'default': {'value': datetime.now, 'kwargs': {'tz': '@timezone'}},
		'setter': '@source', tsk.metaData: True,
	},

	# The free Current Weather Data endpoint has no nested forecast
	# sections to pick between - normalizeData() below already flattens
	# main/wind/clouds/weather[0]/sys into one flat dict, so the whole
	# datagram (path=()) becomes the single 'realtime' section.
	'dataMaps': {
		'weather': {'realtime': ()},
	},

	'aliases': {
		# OpenWeatherMap's icon codes (https://openweathermap.org/weather-conditions)
		# mapped to WeatherIcons glyph names, following the same pattern as
		# PirateWeather's @conditionIcons.
		'@conditionIcons': {
			'01d': 'wi:day-sunny', '01n': 'wi:night-clear',
			'02d': 'wi:day-cloudy', '02n': 'wi:night-alt-cloudy',
			'03d': 'wi:cloud', '03n': 'wi:cloud',
			'04d': 'wi:cloudy', '04n': 'wi:cloudy',
			'09d': 'wi:showers', '09n': 'wi:showers',
			'10d': 'wi:day-rain', '10n': 'wi:night-alt-rain',
			'11d': 'wi:day-thunderstorm', '11n': 'wi:night-alt-thunderstorm',
			'13d': 'wi:snow', '13n': 'wi:snow',
			'50d': 'wi:fog', '50n': 'wi:fog',
		},
	},
}

_enableMessage = (
	"Enable OpenWeatherMap?  "
	"This will require an API key to connect. You can find more "
	"information at https://openweathermap.org/api"
)

_defaultConfig = f""";All independent configs must have a plugin section

[plugin]
enabled = @ask(bool:False).message({_enableMessage})
apikey = @ask(str:).message(Enter API Key)
defaultFor =
"""


class OpenWeatherMap(REST, realtime=True, daily=False, hourly=False, logged=False):
	urls: OWMURLs = OWMURLs()
	schema = schema
	name = 'OpenWeatherMap'

	__defaultConfig__ = _defaultConfig
	__configRequired = ['apikey']

	weatherTimer: ScheduledEvent

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	def normalizeData(self, rawData: dict) -> dict:
		"""Flatten the Current Weather Data response's nested main/wind/
		clouds/weather[0]/sys sub-objects into one flat dict, so the schema
		can address every field with a plain top-level sourceKey - the same
		shape a onecall-style response's 'current' block already has. This
		keeps the reshaping entirely plugin-local rather than teaching the
		shared schema engine to merge sibling sub-objects into one section."""
		# Every key returned here must have a matching schema sourceKey - an
		# unmapped key reaches ObservationValue.__init__ with no metadata
		# and crashes (a real, separate gap in the schema engine's handling
		# of unrecognized keys; out of scope for a plugin-only change - see
		# the follow-up task). weather[0]'s 'id'/'main' fields are dropped
		# for exactly this reason: nothing below maps them, only
		# 'description'/'icon' are used.
		main = rawData.get('main') or {}
		wind = rawData.get('wind') or {}
		clouds = rawData.get('clouds') or {}
		sys_ = rawData.get('sys') or {}
		weather = (rawData.get('weather') or [{}])[0]
		return {
			'dt':                   rawData.get('dt'),
			'temp':                 main.get('temp'),
			'feels_like':           main.get('feels_like'),
			'temp_min':             main.get('temp_min'),
			'temp_max':             main.get('temp_max'),
			'humidity':             main.get('humidity'),
			'pressure':             main.get('pressure'),
			'visibility':           rawData.get('visibility'),
			'wind_speed':           wind.get('speed'),
			'wind_deg':             wind.get('deg'),
			'wind_gust':            wind.get('gust'),
			'clouds':               clouds.get('all'),
			'weather_description':  weather.get('description'),
			'weather_icon':         weather.get('icon'),
			'sunrise':              sys_.get('sunrise'),
			'sunset':               sys_.get('sunset'),
		}

	async def getWeather(self):
		try:
			data = await self.getData(self.urls.weather)
			for obs in self.observations:
				if obs.dataName in data:
					obs.update(data)
		except TimeoutError as e:
			self.pluginLog.warning(f'OpenWeatherMap: update request timed out: {e}')
			self.weatherTimer.retry(timedelta(minutes=1))
		except InvalidData as e:
			self.pluginLog.error('OpenWeatherMap: request failed due to invalid data')
			self.pluginLog.exception(e)
		except APIError as e:
			self.pluginLog.error('OpenWeatherMap: request failed due to an API error')
			self.pluginLog.exception(e)
		except Exception as e:
			self.pluginLog.error(f'OpenWeatherMap: request failed due to an unknown error {e.__class__.__name__}')
			self.pluginLog.exception(e)

	def start(self):
		self.pluginLog.info("Starting OpenWeatherMap")

		if self.running:
			self.pluginLog.info("OpenWeatherMap already running")
			return self

		async def async_bootstrap():
			self.pluginLog.info('OpenWeatherMap: started')
			await self.future
			self.pluginLog.info('OpenWeatherMap: starting shutdown')

		def bootstrap():
			self.weatherTimer = ScheduledEvent(timedelta(minutes=15), self.getWeather, loop=self.loop).start()
			self._task = async_bootstrap()
			self.loop.run_until_complete(self._task)
			self.stop()
			del self.loop
			self.pluginLog.info('OpenWeatherMap: shutdown complete')

		self.loop.run_in_executor(None, bootstrap)

		return self

	def stop(self, callback: Callable = None):
		async def continue_shutdown():
			self.future.set_result(True)
			self.future.cancel()
			await self.loop.shutdown_asyncgens()
			ScheduledEvent.cancelAll(self)

		asyncio.run_coroutine_threadsafe(continue_shutdown(), self.loop)
		self.pluginLog.info('OpenWeatherMap: stopping')


__plugin__ = OpenWeatherMap
