import asyncio
from datetime import timedelta, timezone, datetime
from typing import Callable

from LevityDash import LevityDashboard as LD
from LevityDash.lib.plugins.errors import InvalidData
from LevityDash.lib.plugins.schema import SchemaSpecialKeys as tsk
from LevityDash.lib.plugins.utils import ScheduledEvent
from LevityDash.lib.plugins.web import REST, URLs, Endpoint

from LevityDash.lib.plugins.web.errors import APIError
from LevityDash.lib.utils.shared import LOCAL_TIMEZONE


class PWURLs(URLs, base='api.pirateweather.net'):
	forecast = Endpoint(
		url=f'forecast/{{apikey}}/{LD.config.lat},{LD.config.lon}',
		protocol='https', params={'units': 'si', 'extend': 'hourly'},
	)


schema = {
	'timestamp': {'type': 'datetime', 'sourceUnit': 'epoch', 'kwargs': {'tz': '@timezone'}, 'title': 'Time', 'sourceKey': 'time', tsk.metaData: '@timestamp'},

	'environment.condition.condition': {'type': 'summary', 'sourceUnit': 'str', 'title': 'Summary', 'sourceKey': 'summary'},

	'environment.condition.icon': {
		'type': 'icon', 'sourceUnit': 'str', 'title': 'Condition Icon',
		'sourceKey': 'icon', 'iconType': 'glyph', 'iconPack': 'WeatherIcons',
		'aliases': '@conditionIcons'
	},

	# Nearest storm
	'environment.storm.distance': {'type': 'length', 'sourceUnit': 'km', 'title': 'Nearest Storm', 'sourceKey': 'nearestStormDistance'},
	'environment.storm.bearing': {'type': 'bearing', 'sourceUnit': 'º', 'title': 'Nearest Storm Bearing', 'sourceKey': 'nearestStormBearing', 'requires': {'environment.storm.distance': {'gt': 0}}},

	# Precipitation
	'environment.precipitation': {'sourceUnit': ['mm', '@period']},
	'environment.precipitation.precipitation': {'type': 'precipitationRate', 'title': 'Precipitation', 'sourceKey': 'precipIntensity'},
	'environment.precipitation.error': {'type': 'precipitationRate', 'title': 'Precipitation Error', 'sourceKey': 'precipIntensityError'},
	'environment.precipitation.accumulation': {'type': 'precipitationRate', 'title': 'Precipitation Accumulation', 'sourceKey': 'precipAccumulation', 'timeSeriesOnly': True},
	'environment.precipitation.probability': {'type': 'probability', 'sourceUnit': '%p', 'title': 'Precipitation Probability', 'sourceKey': 'precipProbability'},

	# Temperature
	'environment.temperature': {'type': 'temperature', 'sourceUnit': 'c'},
	'environment.temperature.temperature': {'title': 'Temperature', 'sourceKey': 'temperature'},
	'environment.temperature.feelsLike': {'title': 'Feels like', 'sourceKey': 'apparentTemperature'},
	'environment.temperature.dewpoint': {'title': 'Dew Point', 'sourceKey': 'dewPoint'},

	'environment.humidity.humidity': {'type': 'humidity', 'sourceUnit': '%', 'title': 'Humidity', 'sourceKey': 'humidity'},

	# Pressure
	'environment.pressure': {'type': 'pressure', 'sourceUnit': 'hPa'},
	'environment.pressure.pressure': {'title': 'Pressure', 'sourceKey': 'pressure'},

	# Wind
	'environment.wind': {'type': 'wind', 'sourceUnit': ('m', 's')},
	'environment.wind.speed.speed': {'title': 'Wind speed', 'sourceKey': 'windSpeed'},
	'environment.wind.speed.gust': {'title': 'Wind gust', 'sourceKey': 'windGust'},
	'environment.wind.direction': {'type': 'direction', 'sourceUnit': 'deg', 'title': 'Wind direction', 'sourceKey': 'windBearing'},

	# Clouds
	'environment.clouds.coverage': {'type': 'cloudCover', 'sourceUnit': '%', 'title': 'Cloud coverage', 'sourceKey': 'cloudCover'},
	'environment.light.uvi': {'type': 'index', 'sourceUnit': 'uvi', 'title': 'UV Index', 'sourceKey': 'uvIndex'},
	'environment.visibility': {'type': 'distance', 'sourceUnit': 'km', 'title': 'Visibility', 'sourceKey': 'visibility'},

	'environment.ozone': {'type': 'length', 'sourceUnit': 'mm', 'title': 'Ozone Thickness', 'sourceKey': 'ozone'},

	# Daily Specific

	'astronomy.sun.rise': {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Sunrise', 'sourceKey': 'sunriseTime', 'timeseriesOnly': True},
	'astronomy.sun.set': {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Sunset', 'sourceKey': 'sunsetTime', 'timeseriesOnly': True},
	'astronomy.moon.phase': {'type': 'percentage', 'sourceUnit': '%%', 'title': 'Moon Phase', 'sourceKey': 'moonPhase', 'timeseriesOnly': True},

	'environment.precipitation.max': {'type': 'precipitationRate', 'sourceUnit': ('mm', 'hr'), 'title': 'Max Precipitation', 'sourceKey': 'precipIntensityMax', 'timeseriesOnly': True},
	'environment.precipitation.maxTime': {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Max Precipitation Time', 'sourceKey': 'precipIntensityMaxTime', 'timeseriesOnly': True},
	# 'environment.precipitation.daily': {'type': 'precipitationRate', 'title': 'Daily Precipitation', 'sourceKey': 'precipIntensity', 'timeseriesOnly': True},

	'environment.temperature.high': {'title': 'Temperature High', 'sourceKey': 'temperatureHigh', 'timeseriesOnly': True},
	'environment.temperature.highTime': {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Temperature High Time', 'sourceKey': 'temperatureHighTime', 'timeseriesOnly': True},
	'environment.temperature.low': {'title': 'Temperature Low', 'sourceKey': 'temperatureLow', 'timeseriesOnly': True},
	'environment.temperature.lowTime': {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Temperature Low Time', 'sourceKey': 'temperatureLowTime', 'timeseriesOnly': True},

	'environment.temperature.max': {'title': 'Max Temperature', 'sourceKey': 'temperatureMax', 'timeseriesOnly': True},
	'environment.temperature.maxTime': {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Max Temperature Time', 'sourceKey': 'temperatureMaxTime', 'timeseriesOnly': True},
	'environment.temperature.min': {'title': 'Min Temperature', 'sourceKey': 'temperatureMin', 'timeseriesOnly': True},
	'environment.temperature.minTime': {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Min Temperature Time', 'sourceKey': 'temperatureMinTime', 'timeseriesOnly': True},

	'environment.temperature.feelsLikeHigh': {'title': 'Feels Like High', 'sourceKey': 'apparentTemperatureHigh', 'timeseriesOnly': True},
	'environment.temperature.feelsLikeHighTime': {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Feels Like High Time', 'sourceKey': 'apparentTemperatureHighTime', 'timeseriesOnly': True},
	'environment.temperature.feelsLikeLow': {'title': 'TFeels Like Low', 'sourceKey': 'apparentTemperatureLow', 'timeseriesOnly': True},
	'environment.temperature.feelsLikeLowTime': {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Feels Like Low Time', 'sourceKey': 'apparentTemperatureLowTime', 'timeseriesOnly': True},

	'environment.temperature.feelsLikeMax': {'title': 'Max Feels Like', 'sourceKey': 'apparentTemperatureMax', 'timeseriesOnly': True},
	'environment.temperature.feelsLikeMaxTime': {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Max Feels Like Time', 'sourceKey': 'apparentTemperatureMaxTime', 'timeseriesOnly': True},
	'environment.temperature.feelsLikeMin': {'title': 'Min Feels Like', 'sourceKey': 'apparentTemperatureMin', 'timeseriesOnly': True},
	'environment.temperature.feelsLikeMinTime': {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Min Feels Like Time', 'sourceKey': 'apparentTemperatureMinTime', 'timeseriesOnly': True},

	'@period': {
		'attr': 'period',
		'default': {'value': 1, 'unit': 'hr'},
		'allowZero': False,
		tsk.metaData: True
	},

	'@timezone': {
		'dataType': timezone,
		'key': 'timezone',
		'attr': 'timezone',
		'default': {'value': LOCAL_TIMEZONE},
		'setter': '@plugin', tsk.metaData: True
		},
	'@timestamp':
		{'key': 'timestamp', 'attr': 'timestamp', 'default': {'value': datetime.now, 'kwargs': {'tz': '@timezone'}}, 'setter': '@source', tsk.metaData: True},

	'dataMaps': {
		'forecast': {
			'realtime': 'currently',
			'minutely': ('minutely', 'data', 0),
			'hourly': ('hourly', 'data', 0),
			'daily': ('daily', 'data', 0),
		},
	},

	'aliases': {
		'@conditionIcons': {
			'clear-day': 'wi:day-sunny',
			'clear-night': 'wi:night-clear',
			'rain': 'wi:rain',
			'snow': 'wi:snow',
			'sleet': 'wi:sleet',
			'wind': 'wi:strong-wind',
			'fog': 'wi:fog',
			'cloudy': 'wi:cloudy',
			'partly-cloudy-day': 'wi:day-cloudy',
			'partly-cloudy-night': 'wi:night-cloudy',
		},
	},

	'ignored': ['precipType', 'windGustTime', 'uvIndexTime'],

}

_enableMessage = (
	"Enable PirateWeather?  "
	"This will require an API key to connect. You can find more "
	"information at https://pirateweather.net/en/latest/API/"
)

_defaultConfig = f""";All independent configs must have a plugin section

[plugin]
enabled = @ask(bool:False).message({_enableMessage})
apikey = @ask(str:).message(Enter API Key)
defaultFor = temperature precipitation wind pressure humidity storm
"""


class PirateWeather(REST, realtime=True, daily=True, hourly=True, minutely=True, logged=False):
	urls: PWURLs = PWURLs()
	schema = schema
	name = 'PirateWeather'

	__defaultConfig__ = _defaultConfig
	__configRequired = ['apikey']

	forecastTimer: ScheduledEvent

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	async def getForecast(self):
		try:
			data = await self.getData(self.urls.forecast)
			for obs in self.observations:
				if obs.dataName in data:
					obs.update(data)
		except TimeoutError as e:
			self.pluginLog.warning(f'Pirate Weather: update request timed out: {e}')
			self.forecastTimer.retry(timedelta(minutes=1))
		except InvalidData as e:
			self.pluginLog.error('Pirate Weather: request failed due to invalid data')
			self.pluginLog.exception(e)
		except APIError as e:
			self.pluginLog.error('Pirate Weather: request failed due to an API error')
			self.pluginLog.exception(e)
		except Exception as e:
			self.pluginLog.error(f'Pirate Weather: request failed due to an unknown error {e.__class__.__name__}')
			self.pluginLog.exception(e)

	def start(self):

		self.pluginLog.info("Starting Pirate Weather")

		if self.running:
			self.pluginLog.info("Pirate Weather already running")
			return self

		async def async_bootstrap():
			self.pluginLog.info('Pirate Weather: started')
			await self.future
			self.pluginLog.info('Pirate Weather: starting shutdown')

		def bootstrap():
			self.forecastTimer = ScheduledEvent(timedelta(minutes=15), self.getForecast, loop=self.loop).start()
			self._task = async_bootstrap()
			self.loop.run_until_complete(self._task)
			self.stop()
			del self.loop
			self.pluginLog.info('Pirate Weather: shutdown complete')

		self.loop.run_in_executor(None, bootstrap)

		return self

	def stop(self, callback: Callable = None):

		async def continue_shutdown():
			self.future.set_result(True)
			self.future.cancel()
			await self.loop.shutdown_asyncgens()
			ScheduledEvent.cancelAll(self)

		asyncio.run_coroutine_threadsafe(continue_shutdown(), self.loop)
		self.pluginLog.info('Pirate Weather: stopping')


__plugin__ = PirateWeather
