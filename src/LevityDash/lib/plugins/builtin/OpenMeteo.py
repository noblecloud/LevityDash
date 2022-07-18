from asyncio import gather, create_task, get_event_loop

from LevityDash.lib.plugins.utils import ScheduledEvent
from LevityDash.lib.plugins.schema import SchemaSpecialKeys as tsk
from LevityDash.lib.plugins.web import Endpoint, REST, URLs
from datetime import datetime, timedelta

from LevityDash.lib.config import userConfig
from LevityDash.lib.plugins.web.errors import APIError

"""
Code	Description
0	Clear sky
1, 2, 3	Mainly clear, partly cloudy, and overcast
45, 48	Fog and depositing rime fog
51, 53, 55	Drizzle: Light, moderate, and dense intensity
56, 57	Freezing Drizzle: Light and dense intensity
61, 63, 65	Rain: Slight, moderate and heavy intensity
66, 67	Freezing Rain: Light and heavy intensity
71, 73, 75	Snow fall: Slight, moderate, and heavy intensity
77	Snow grains
80, 81, 82	Rain showers: Slight, moderate, and violent
85, 86	Snow showers slight and heavy
95 *	Thunderstorm: Slight or moderate
96, 99 *	Thunderstorm with slight and heavy hail
*) Thunderstorm forecast with hail is only available in Central Europe
"""

WMOCodes = {
	0:  {'description': 'Clear', 'icon': ''},
	1:  {'description': 'Light clouds', 'icon': ''},
	2:  {'description': 'Partly cloudy', 'icon': ''},
	3:  {'description': 'Overcast', 'icon': ''},
	45: {'description': 'Fog', 'icon': ''},
	48: {'description': 'Depositing rime fog', 'icon': ''},
	51: {'description': 'Light Drizzle', 'icon': ''},
	53: {'description': 'Drizzle', 'icon': ''},
	55: {'description': 'Heavy Drizzle', 'icon': ''},
	56: {'description': 'Freezing Drizzle', 'icon': ''},
	57: {'description': 'Heavy Freezing Drizzle', 'icon': ''},
	61: {'description': 'Light Rain', 'icon': ''},
	63: {'description': 'Rain', 'icon': ''},
	65: {'description': 'Heavy Rain', 'icon': ''},
	66: {'description': 'Light Freezing Rain', 'icon': ''},
	67: {'description': 'Freezing Rain', 'icon': ''},
	71: {'description': 'Light Snowfall', 'icon': ''},
	73: {'description': 'Snowfall', 'icon': ''},
	75: {'description': 'Heavy Snowfall', 'icon': ''},
	77: {'description': 'Snow grains', 'icon': ''},
	80: {'description': 'Light Rain showers', 'icon': ''},
	81: {'description': 'Rain showers', 'icon': ''},
	82: {'description': 'Heavy Rain showers', 'icon': ''},
	85: {'description': 'Light Snow showers', 'icon': ''},
	86: {'description': 'Heavy Snow showers', 'icon': ''},
	95: {'description': 'Thunderstorm', 'icon': ''},
	96: {'description': 'Thunderstorm with light hail', 'icon': ''},
	99: {'description': 'Thunderstorm with heavy hail', 'icon': ''},
}

schema = {
	'environment':                                  {'timeseriesOnly': True},
	'environment.clouds.cover.cover':               {'type': 'cloudcover', 'sourceUnit': '%', 'title': 'Cloud Cover', 'description': 'Cloud Coverage', 'sourceKey': 'cloudcover', 'timeseriesOnly': True},
	'environment.clouds.cover.high':                {'type': 'cloudcover', 'sourceUnit': '%', 'title': 'Cloud Cover High', 'description': 'Cloud cover high', 'sourceKey': 'cloudcover_high', 'timeseriesOnly': True},
	'environment.clouds.cover.low':                 {'type': 'cloudcover', 'sourceUnit': '%', 'title': 'Cloud Cover Low', 'description': 'Cloud cover low', 'sourceKey': 'cloudcover_low', 'timeseriesOnly': True},
	'environment.clouds.cover.mid':                 {'type': 'cloudcover', 'sourceUnit': '%', 'title': 'Cloud Cover Mid', 'description': 'Cloud cover mid', 'sourceKey': 'cloudcover_mid', 'timeseriesOnly': True},

	'environment.condition.weatherCode':            {'type': 'WeatherCode', 'sourceUnit': 'WeatherCode', 'title': 'Weather code', 'description': 'Weather code', 'sourceKey': 'weathercode', 'timeseriesOnly': True},
	'environment.condition.icon':                   {
		'type':      'icon', 'sourceUnit': 'int', 'title': 'Condition Icon', 'description': 'Condition Icon', 'dataKey': 'environment.condition.weatherCode', 'iconType': 'glyph',
		'glyphFont': 'WeatherIcons',
		'aliases':   '@conditionIcon'
	},
	'environment.condition.condition':              {'type': 'WeatherCode', 'sourceUnit': 'int', 'title': 'Condition', 'description': 'Condition', 'dataKey': 'environment.condition.weatherCode', 'aliases': '@condition'},

	'environment.humidity.humidity':                {'type': 'humidity', 'sourceUnit': '%', 'title': 'Humidity', 'description': 'Relative humidity at 2m height', 'sourceKey': 'relativehumidity_2m'},

	'environment.light.irradiance.daily':           {'type': 'radiation', 'sourceUnit': 'W/m^2', 'title': 'Total Shortwave Radiation', 'description': 'Total shortwave radiation for the day', 'sourceKey': 'shortwave_radiation_sum'},
	'environment.light.irradiance.diffuse':         {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Diffuse radiation', 'description': 'Diffuse radiation', 'sourceKey': 'diffuse_radiation', 'timeseriesOnly': True},
	'environment.light.irradiance.diffuseNormal':   {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Diffuse normal irradiance', 'description': 'Diffuse normal irradiance', 'sourceKey': 'diffuse_normal_irradiance'},
	'environment.light.irradiance.direct':          {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Direct radiation', 'description': 'Direct radiation', 'sourceKey': 'direct_radiation', 'timeseriesOnly': True},
	'environment.light.irradiance.directNormal':    {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Direct normal irradiance', 'description': 'Direct normal irradiance', 'sourceKey': 'direct_normal_irradiance'},
	'environment.light.irradiance.global':          {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Global irradiance', 'description': 'Global irradiance', 'sourceKey': 'global_irradiance', 'timeseriesOnly': True},
	'environment.light.irradiance.irradiance':      {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Shortwave radiation', 'description': 'Shortwave radiation', 'sourceKey': 'shortwave_radiation', 'timeseriesOnly': True},
	'environment.light.sunrise':                    {'type': 'datetime', 'sourceUnit': 'ISO8601', 'format': '%Y-%m-%dT%H:%M', 'title': 'Sunrise', 'description': 'Sunrise', 'sourceKey': 'sunrise', 'timeseriesOnly': True},
	'environment.light.sunset':                     {'type': 'datetime', 'sourceUnit': 'ISO8601', 'format': '%Y-%m-%dT%H:%M', 'title': 'Sunset', 'description': 'Sunset', 'sourceKey': 'sunset', 'timeseriesOnly': True},

	'environment.precipitation.daily':              {'type': 'precipitationDaily', 'sourceUnit': ['mm', 'day'], 'title': 'Precipitation Daily', 'description': 'Precipitation daily', 'sourceKey': 'precipitation_sum', 'timeseriesOnly': True},
	'environment.precipitation.showers':            {'type': 'precipitationHourly', 'sourceUnit': ['mm', 'hr'], 'title': 'Showers', 'description': 'Showers', 'sourceKey': 'showers', 'timeseriesOnly': True},
	'environment.precipitation.rain':               {'type': 'precipitationHourly', 'sourceUnit': ['mm', 'hr'], 'title': 'Rain', 'description': 'Rain', 'sourceKey': 'rain', 'timeseriesOnly': True},
	'environment.precipitation.show':               {'type': 'precipitationHourly', 'sourceUnit': ['mm', 'hr'], 'title': 'Snow', 'description': 'Snow', 'sourceKey': 'snowfall', 'timeseriesOnly': True},
	'environment.precipitation.showersDaily':       {'type': 'precipitationDaily', 'sourceUnit': ['mm', 'day'], 'title': 'Showers Daily', 'description': 'Showers Daily', 'sourceKey': 'showers', 'timeseriesOnly': True},
	'environment.precipitation.rainDaily':          {'type': 'precipitationDaily', 'sourceUnit': ['mm', 'day'], 'title': 'Rain Daily', 'description': 'Rain Daily', 'sourceKey': 'rain', 'timeseriesOnly': True},
	'environment.precipitation.showDaily':          {'type': 'precipitationDaily', 'sourceUnit': ['mm', 'day'], 'title': 'Snow Daily', 'description': 'Snow Daily', 'sourceKey': 'snowfall', 'timeseriesOnly': True},
	'environment.precipitation.precipitation':      {'type': 'precipitationHourly', 'sourceUnit': ['mm', 'hr'], 'title': 'Precipitation', 'description': 'Precipitation', 'sourceKey': 'precipitation', 'timeseriesOnly': True},
	'environment.precipitation.snowDepth':          {'type': 'precipitation', 'sourceUnit': 'm', 'title': 'Snow depth', 'description': 'Snow depth', 'sourceKey': 'snow_depth', 'timeseriesOnly': True},
	'environment.precipitation.time':               {'type': 'time', 'sourceUnit': 'hr', 'title': 'Precipitation Time', 'description': 'Precipitation time', 'sourceKey': 'precipitation_hours', 'timeseriesOnly': True},

	'environment.pressure.pressure':                {'type': 'pressure', 'sourceUnit': 'hPa', 'title': 'Pressure', 'description': 'Pressure at 2m height', 'sourceKey': 'pressure_msl'},
	'environment.pressure.surface':                 {'type': 'pressure', 'sourceUnit': 'hPa', 'title': 'Pressure', 'description': 'Pressure at 2m height', 'sourceKey': 'surface_pressure'},
	'environment.pressure.vaporPressureDeficit':    {'type': 'pressure', 'sourceUnit': 'kPa', 'title': 'Vapor Pressure Deficit', 'description': 'Vapor pressure deficit', 'sourceKey': 'vapor_pressure_deficit', 'timeseriesOnly': True},

	'environment.soil.freezingLevelHeight':         {'type': 'length', 'sourceUnit': 'm', 'title': 'Freezing level height', 'description': 'Freezing level height', 'sourceKey': 'freezinglevel_height', 'timeseriesOnly': True},
	'environment.soil.moisture.1-3cm':              {'type': 'soil', 'sourceUnit': '%', 'title': 'Soil Moisture [1-3cm]', 'description': 'Soil moisture at 1-3cm depth', 'sourceKey': 'soil_moisture_1_3cm', 'timeseriesOnly': True},
	'environment.soil.moisture.3-9cm':              {'type': 'soil', 'sourceUnit': '%', 'title': 'Soil Moisture [3-9cm]', 'description': 'Soil moisture at 3-9cm depth', 'sourceKey': 'soil_moisture_3_9cm', 'timeseriesOnly': True},
	'environment.soil.moisture.28-81cm':            {'type': 'soil', 'sourceUnit': '%', 'title': 'Soil Moisture [28-81cm]', 'description': 'Soil moisture at 28-81cm depth', 'sourceKey': 'soil_moisture_28_81cm', 'timeseriesOnly': True},
	'environment.soil.moisture.evapotranspiration': {'type': 'rate', 'sourceUnit': ['mm', 'hr'], 'title': 'Evapotranspiration', 'description': 'Evapotranspiration', 'sourceKey': 'evapotranspiration', 'timeseriesOnly': True},
	'environment.soil.moisture.moisture':           {'type': 'soil', 'sourceUnit': '%', 'title': 'Soil Moisture', 'description': 'Soil moisture', 'sourceKey': 'soil_moisture_0_1cm', 'timeseriesOnly': True},
	'environment.soil.temperature.6cm':             {'type': 'soil', 'sourceUnit': '°C', 'title': 'Soil Temperature [6cm]', 'description': 'Soil temperature at 6cm depth', 'sourceKey': 'soil_temperature_6cm', 'timeseriesOnly': True},
	'environment.soil.temperature.18cm':            {'type': 'soil', 'sourceUnit': '°C', 'title': 'Soil Temperature [12cm]', 'description': 'Soil temperature at 18cm depth', 'sourceKey': 'soil_temperature_18cm', 'timeseriesOnly': True},
	'environment.soil.temperature.54cm':            {'type': 'soil', 'sourceUnit': '°C', 'title': 'Soil Temperature [54cm]', 'description': 'Soil temperature at 54cm depth', 'sourceKey': 'soil_temperature_54cm', 'timeseriesOnly': True},
	'environment.soil.temperature.temperature':     {'type': 'soil', 'sourceUnit': '°C', 'title': 'Soil Temperature', 'description': 'Soil temperature', 'sourceKey': 'soil_temperature_0cm', 'timeseriesOnly': True},

	'environment.temperature.dewpoint':             {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Dew Point', 'description': 'Dew Point at 2m height', 'sourceKey': 'dewpoint_2m'},
	'environment.temperature.feelsLike':            {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Feels Like', 'description': 'Apparent temperature at 2m height', 'sourceKey': 'apparent_temperature'},
	'environment.temperature.feelsLikeHigh':        {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Feels Like High', 'description': 'Feels like high', 'sourceKey': 'apparent_temperature_max', 'timeseriesOnly': True},
	'environment.temperature.feelsLikeLow':         {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Feels Like Low', 'description': 'Feels like low', 'sourceKey': 'apparent_temperature_min', 'timeseriesOnly': True},
	'environment.temperature.high':                 {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Temperature High', 'description': 'Temperature high', 'sourceKey': 'temperature_2m_max', 'timeseriesOnly': True},
	'environment.temperature.low':                  {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Temperature Low', 'description': 'Temperature low', 'sourceKey': 'temperature_2m_min', 'timeseriesOnly': True},
	'environment.temperature.temperature':          {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Temperature', 'description': 'Temperature at 2m height', 'sourceKey': 'temperature_2m'},

	'environment.wind.direction.80m':               {'type': 'direction', 'sourceUnit': 'º', 'title': 'Wind Direction [80m]', 'description': 'Wind direction at 80m height', 'sourceKey': 'winddirection_80m', 'timeseriesOnly': True},
	'environment.wind.direction.120m':              {'type': 'direction', 'sourceUnit': 'º', 'title': 'Wind Direction [120m]', 'description': 'Wind direction at 120m height', 'sourceKey': 'winddirection_120m', 'timeseriesOnly': True},
	'environment.wind.direction.180m':              {'type': 'direction', 'sourceUnit': 'º', 'title': 'Wind Direction [180m]', 'description': 'Wind direction at 180m height', 'sourceKey': 'winddirection_180m', 'timeseriesOnly': True},
	'environment.wind.direction.direction':         {'type': 'direction', 'sourceUnit': 'º', 'title': 'Wind Direction', 'description': 'Wind direction at 10m height', 'sourceKey': 'winddirection_10m', 'timeseriesOnly': True},
	'environment.wind.direction.dominant':          {'type': 'direction', 'sourceUnit': 'º', 'title': 'Wind Direction', 'description': 'Wind direction', 'sourceKey': 'winddirection_10m_dominant', 'timeseriesOnly': True},
	'environment.wind.speed.80m':                   {'type': 'wind', 'sourceUnit': ['km', 'hr'], 'title': 'Wind Speed [80m]', 'description': 'Wind speed at 80m height', 'sourceKey': 'windspeed_80m', 'timeseriesOnly': True},
	'environment.wind.speed.120m':                  {'type': 'wind', 'sourceUnit': ['km', 'hr'], 'title': 'Wind Speed [120m]', 'description': 'Wind speed at 120m height', 'sourceKey': 'windspeed_120m', 'timeseriesOnly': True},
	'environment.wind.speed.180m':                  {'type': 'wind', 'sourceUnit': ['km', 'hr'], 'title': 'Wind Speed [180m]', 'description': 'Wind speed at 180m height', 'sourceKey': 'windspeed_180m', 'timeseriesOnly': True},
	'environment.wind.speed.gust':                  {'type': 'wind', 'sourceUnit': ['km', 'hr'], 'title': 'Wind Gusts', 'description': 'Wind gusts at 10m height', 'sourceKey': 'windgusts_10m', 'timeseriesOnly': True},
	'environment.wind.speed.gustMax':               {'type': 'wind', 'sourceUnit': ['km', 'hr'], 'title': 'Wind Gusts Max', 'description': 'Max wind gusts for the day at 10m height', 'sourceKey': 'windgusts_10m_max', 'timeseriesOnly': True},
	'environment.wind.speed.gustMin':               {'type': 'wind', 'sourceUnit': ['km', 'hr'], 'title': 'Wind Gusts Min', 'description': 'Min wind gusts for the day at 10m height', 'sourceKey': 'windgusts_10m_min', 'timeseriesOnly': True},
	'environment.wind.speed.max':                   {'type': 'wind', 'sourceUnit': ['km', 'hr'], 'title': 'Wind Speed Max', 'description': 'Wind speed max', 'sourceKey': 'windspeed_10m_max', 'timeseriesOnly': True},
	'environment.wind.speed.min':                   {'type': 'wind', 'sourceUnit': ['km', 'hr'], 'title': 'Wind Speed Min', 'description': 'Wind speed min', 'sourceKey': 'windspeed_10m_min', 'timeseriesOnly': True},
	'environment.wind.speed.speed':                 {'type': 'wind', 'sourceUnit': ['km', 'hr'], 'title': 'Wind Speed', 'description': 'Wind speed at 10m height', 'sourceKey': 'windspeed_10m', 'timeseriesOnly': True},
	'timestamp':                                    {
		'type':       'datetime', 'sourceUnit': 'ISO8601', 'format': {'hourly': '%Y-%m-%dT%H:%M', 'daily': '%Y-%m-%d'}, 'title': 'Time', 'description': 'Time', 'sourceKey': 'time',
		tsk.metaData: '@timestamp'
	},

	'dataMaps':                                     {
		'forecast': {
			'daily':  'daily',
			'hourly': 'hourly',
		}
	},
	'aliases':                                      {
		'@conditionIcon': {k: v['icon'] for k, v in WMOCodes.items()},
		'@condition':     {k: v['description'] for k, v in WMOCodes.items()},
	}

}

basicParams = [
	'temperature_2m',
	'relativehumidity_2m',
	'dewpoint_2m',
	'apparent_temperature',
	'pressure_msl',
	'surface_pressure',
	'cloudcover',
	'windspeed_10m',
	'winddirection_10m',
	'windgusts_10m',
	'shortwave_radiation',
	'direct_radiation',
	'diffuse_radiation',
	'precipitation',
	'rain',
	'showers',
	'snowfall',
	'weathercode',
	'snow_depth',
	'soil_moisture_0_1cm'
]
allParams = [
	'temperature_2m',
	'relativehumidity_2m',
	'dewpoint_2m',
	'apparent_temperature',
	'pressure_msl',
	'cloudcover',
	'cloudcover_low',
	'cloudcover_mid',
	'cloudcover_high',
	'windspeed_10m',
	'windspeed_80m',
	'windspeed_120m',
	'windspeed_180m',
	'winddirection_10m',
	'winddirection_80m',
	'winddirection_120m',
	'winddirection_180m',
	'windgusts_10m',
	'shortwave_radiation',
	'direct_radiation',
	'direct_normal_irradiance',
	'diffuse_radiation',
	'vapor_pressure_deficit',
	'evapotranspiration',
	'precipitation',
	'weathercode',
	'snow_depth',
	'freezinglevel_height',
	'soil_temperature_0cm',
	'soil_temperature_6cm',
	'soil_temperature_18cm',
	'soil_temperature_54cm',
	'soil_moisture_0_1cm',
	'soil_moisture_1_3cm',
	'soil_moisture_3_9cm',
	'soil_moisture_9_27cm',
	'soil_moisture_27_81cm',
]
dailyParams = ['weathercode',
	'temperature_2m_max',
	'temperature_2m_min',
	'apparent_temperature_max',
	'apparent_temperature_min',
	'sunrise',
	'sunset',
	'precipitation_sum',
	'precipitation_hours',
	'windspeed_10m_max',
	'windgusts_10m_max',
	'winddirection_10m_dominant',
	'shortwave_radiation_sum']


class OpenMeteoURLs(URLs, base='api.open-meteo.com/v1'):
	params = {'latitude': userConfig.lat, 'longitude': userConfig.lon, 'timezone': str(userConfig.tz), 'past_days': 1}
	forecast = Endpoint(url='forecast', params={'hourly': basicParams, 'daily': dailyParams})


class OpenMeteo(REST, realtime=False, hourly=True, daily=True):
	urls = OpenMeteoURLs()
	schema = schema
	name = 'OpenMeteo'
	requestTimer: ScheduledEvent

	def __init__(self, *args, **kwargs):
		super(OpenMeteo, self).__init__(*args, **kwargs)

	def start(self):
		self.pluginLog.info('OpenMeteo: starting')
		if self.running:
			self.pluginLog.info('OpenMeteo: already running')
			return
		self.requestTimer = ScheduledEvent(timedelta(minutes=15), self.getForecast).start()
		self.pluginLog.info('OpenMeteo: started')

	async def asyncStart(self):
		loop = get_event_loop()
		loop.call_soon(self.start)

	def stop(self):
		self.pluginLog.info('OpenMeteo: stopping')
		if not self.running:
			self.pluginLog.info('OpenMeteo: not running')
			return
		self.requestTimer.stop()
		self.pluginLog.info('OpenMeteo: stopped')

	async def asyncStop(self):
		loop = get_event_loop()
		loop.call_soon(self.stop)

	async def getForecast(self):
		try:
			data = await self.getData(self.urls.forecast)
		except APIError as e:
			self.pluginLog.warn('OpenMeteo: No data received')
			return
		data['source'] = [self.name, self.urls.forecast]
		create_task(self.hourly.asyncUpdate(data))
		create_task(self.daily.asyncUpdate(data))


__plugin__ = OpenMeteo
