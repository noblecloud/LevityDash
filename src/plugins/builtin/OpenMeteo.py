from src.plugins.plugin import ScheduledEvent
from src.plugins.web import Endpoint, REST, URLs
from src import logging
from datetime import datetime, timedelta

from src import config

# from src.plugins import Plugins

log = logging.getLogger(__name__)

unitDefinitions = {
	'environment.temperature.temperature':          {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Temperature', 'description': 'Temperature at 2m height', 'sourceKey': 'temperature_2m'},
	'environment.humidity.humidity':                {'type': 'relativehumidity', 'sourceUnit': '%', 'title': 'Relative humidity', 'description': 'Relative humidity at 2m height', 'sourceKey': 'relativehumidity_2m'},
	'environment.temperature.dewpoint':             {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Dewpoint', 'description': 'Dewpoint at 2m height', 'sourceKey': 'dewpoint_2m'},
	'environment.temperature.feelsLike':            {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Feels Like', 'description': 'Apparent temperature at 2m height', 'sourceKey': 'apparent_temperature'},
	'environment.pressure.pressure':                {'type': 'pressure', 'sourceUnit': 'hPa', 'title': 'Pressure', 'description': 'Pressure at 2m height', 'sourceKey': 'pressure_msl'},
	'environment.clouds.cover.cover':               {'type': 'cloudcover', 'sourceUnit': '%', 'title': 'Cloud cover', 'description': 'Cloud cover', 'sourceKey': 'cloudcover'},
	'environment.clouds.cover.low':                 {'type': 'cloudcover', 'sourceUnit': '%', 'title': 'Cloud cover low', 'description': 'Cloud cover low', 'sourceKey': 'cloudcover_low'},
	'environment.clouds.cover.mid':                 {'type': 'cloudcover', 'sourceUnit': '%', 'title': 'Cloud cover mid', 'description': 'Cloud cover mid', 'sourceKey': 'cloudcover_mid'},
	'environment.clouds.cover.high':                {'type': 'cloudcover', 'sourceUnit': '%', 'title': 'Cloud cover high', 'description': 'Cloud cover high', 'sourceKey': 'cloudcover_high'},
	'environment.wind.speed.speed':                 {'type': 'wind', 'sourceUnit': ['km', 'hr'], 'title': 'Wind speed', 'description': 'Wind speed at 10m height', 'sourceKey': 'windspeed_10m'},
	'environment.wind.speed.80m':                   {'type': 'wind', 'sourceUnit': ['km', 'hr'], 'title': 'Wind speed [80m]', 'description': 'Wind speed at 80m height', 'sourceKey': 'windspeed_80m'},
	'environment.wind.speed.120m':                  {'type': 'wind', 'sourceUnit': ['km', 'hr'], 'title': 'Wind speed [120m]', 'description': 'Wind speed at 120m height', 'sourceKey': 'windspeed_120m'},
	'environment.wind.speed.180m':                  {'type': 'wind', 'sourceUnit': ['km', 'hr'], 'title': 'Wind speed [180m]', 'description': 'Wind speed at 180m height', 'sourceKey': 'windspeed_180m'},
	'environment.wind.direction.direction':         {'type': 'direction', 'sourceUnit': 'º', 'title': 'Wind direction', 'description': 'Wind direction at 10m height', 'sourceKey': 'winddirection_10m'},
	'environment.wind.direction.80m':               {'type': 'direction', 'sourceUnit': 'º', 'title': 'Wind direction [80m]', 'description': 'Wind direction at 80m height', 'sourceKey': 'winddirection_80m'},
	'environment.wind.direction.120m':              {'type': 'direction', 'sourceUnit': 'º', 'title': 'Wind direction [120m]', 'description': 'Wind direction at 120m height', 'sourceKey': 'winddirection_120m'},
	'environment.wind.direction.180m':              {'type': 'direction', 'sourceUnit': 'º', 'title': 'Wind direction [180m]', 'description': 'Wind direction at 180m height', 'sourceKey': 'winddirection_180m'},
	'environment.wind.speed.gusts':                 {'type': 'wind', 'sourceUnit': ['km', 'hr'], 'title': 'Wind Gusts', 'description': 'Wind gusts at 10m height', 'sourceKey': 'windgusts_10m'},
	'environment.wind.speed.gustsMax':              {'type': 'wind', 'sourceUnit': ['km', 'hr'], 'title': 'Wind Gusts Max', 'description': 'Max wind gusts for the day at 10m height', 'sourceKey': 'windgusts_10m_max'},
	'environment.wind.speed.gustsMin':              {'type': 'wind', 'sourceUnit': ['km', 'hr'], 'title': 'Wind Gusts Min', 'description': 'Min wind gusts for the day at 10m height', 'sourceKey': 'windgusts_10m_min'},
	'environment.light.irradiance.irradiance':      {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Shortwave radiation', 'description': 'Shortwave radiation', 'sourceKey': 'shortwave_radiation'},
	'environment.light.irradiance.direct':          {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Direct radiation', 'description': 'Direct radiation', 'sourceKey': 'direct_radiation'},
	'environment.light.irradiance.directNormal':    {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Direct normal irradiance', 'description': 'Direct normal irradiance', 'sourceKey': 'direct_normal_irradiance'},
	'environment.light.irradiance.diffuse':         {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Diffuse radiation', 'description': 'Diffuse radiation', 'sourceKey': 'diffuse_radiation'},
	'environment.light.irradiance.diffuseNormal':   {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Diffuse normal irradiance', 'description': 'Diffuse normal irradiance', 'sourceKey': 'diffuse_normal_irradiance'},
	'environment.light.irradiance.global':          {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Global irradiance', 'description': 'Global irradiance', 'sourceKey': 'global_irradiance'},
	'environment.pressure.vaporPressureDeficit':    {'type': 'pressure', 'sourceUnit': 'kPa', 'title': 'Vapor pressure deficit', 'description': 'Vapor pressure deficit', 'sourceKey': 'vapor_pressure_deficit'},
	'environment.soil.moisture.evapotranspiration': {'type': 'rate', 'sourceUnit': ['mm', 'hr'], 'title': 'Evapotranspiration', 'description': 'Evapotranspiration', 'sourceKey': 'evapotranspiration'},
	'environment.precipitation.precipitation':      {'type': 'precipitationHourly', 'sourceUnit': ['mm', 'hr'], 'title': 'Precipitation', 'description': 'Precipitation', 'sourceKey': 'precipitation'},
	'environment.conditions.weatherCode':           {'type': 'WeatherCode', 'sourceUnit': 'WeatherCode', 'title': 'Weather code', 'description': 'Weather code', 'sourceKey': 'weathercode'},
	'environment.precipitation.snowAccumulation':   {'type': 'precipitation', 'sourceUnit': 'm', 'title': 'Snow accumulation', 'description': 'Snow accumulation', 'sourceKey': 'snow_depth'},
	'environment.soil.freezingLevelHeight':         {'type': 'length', 'sourceUnit': 'm', 'title': 'Freezing level height', 'description': 'Freezing level height', 'sourceKey': 'freezinglevel_height'},
	'environment.soil.temperature.temperature':     {'type': 'soil', 'sourceUnit': '°C', 'title': 'Soil temperature', 'description': 'Soil temperature', 'sourceKey': 'soil_temperature_0cm'},
	'environment.soil.temperature.6cm':             {'type': 'soil', 'sourceUnit': '°C', 'title': 'Soil temperature [6cm]', 'description': 'Soil temperature at 6cm depth', 'sourceKey': 'soil_temperature_6cm'},
	'environment.soil.temperature.18cm':            {'type': 'soil', 'sourceUnit': '°C', 'title': 'Soil temperature [12cm]', 'description': 'Soil temperature at 18cm depth', 'sourceKey': 'soil_temperature_18cm'},
	'environment.soil.temperature.54cm':            {'type': 'soil', 'sourceUnit': '°C', 'title': 'Soil temperature [54cm]', 'description': 'Soil temperature at 54cm depth', 'sourceKey': 'soil_temperature_54cm'},
	'environment.soil.moisture.moisture':           {'type': 'soil', 'sourceUnit': ['m^3', 'm^3'], 'title': 'Soil moisture', 'description': 'Soil moisture', 'sourceKey': 'soil_moisture_0_1cm'},
	'environment.soil.moisture.1-3cm':              {'type': 'soil', 'sourceUnit': ['m^3', 'm^3'], 'title': 'Soil moisture [1-3cm]', 'description': 'Soil moisture at 1-3cm depth', 'sourceKey': 'soil_moisture_1_3cm'},
	'environment.soil.moisture.3-9cm':              {'type': 'soil', 'sourceUnit': ['m^3', 'm^3'], 'title': 'Soil moisture [3-9cm]', 'description': 'Soil moisture at 3-9cm depth', 'sourceKey': 'soil_moisture_3_9cm'},
	'environment.soil.moisture.28-81cm':            {'type': 'soil', 'sourceUnit': ['m^3', 'm^3'], 'title': 'Soil moisture [28-81cm]', 'description': 'Soil moisture at 28-81cm depth', 'sourceKey': 'soil_moisture_28_81cm'},
	'environment.temperature.high':                 {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Temperature High', 'description': 'Temperature high', 'sourceKey': 'temperature_2m_max'},
	'environment.temperature.low':                  {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Temperature Low', 'description': 'Temperature low', 'sourceKey': 'temperature_2m_min'},
	'environment.temperature.feelsLikeHigh':        {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Feels like high', 'description': 'Feels like high', 'sourceKey': 'apparent_temperature_max'},
	'environment.temperature.feelsLikeLow':         {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Feels like low', 'description': 'Feels like low', 'sourceKey': 'apparent_temperature_min'},
	'environment.precipitation.daily':              {'type': 'precipitationDaily', 'sourceUnit': 'mm', 'title': 'Precipitation Daily', 'description': 'Precipitation daily', 'sourceKey': 'precipitation_sum'},
	'environment.precipitation.time':               {'type': 'time', 'sourceUnit': 'hr', 'title': 'Precipitation Time', 'description': 'Precipitation time', 'sourceKey': 'precipitation_hours'},
	'environment.light.sunrise':                    {'type': 'datetime', 'sourceUnit': 'ISO8601', 'format': '%Y-%m-%dT%H:%M', 'title': 'Sunrise', 'description': 'Sunrise', 'sourceKey': 'sunrise'},
	'environment.light.sunset':                     {'type': 'datetime', 'sourceUnit': 'ISO8601', 'format': '%Y-%m-%dT%H:%M', 'title': 'Sunset', 'description': 'Sunset', 'sourceKey': 'sunset'},
	'environment.wind.speed.max':                   {'type': 'wind', 'sourceUnit': ['km', 'hr'], 'title': 'Wind Speed Max', 'description': 'Wind speed max', 'sourceKey': 'windspeed_10m_max'},
	'environment.wind.speed.min':                   {'type': 'wind', 'sourceUnit': ['km', 'hr'], 'title': 'Wind Speed Min', 'description': 'Wind speed min', 'sourceKey': 'windspeed_10m_min'},
	'environment.wind.direction.dominant':          {'type': 'direction', 'sourceUnit': 'º', 'title': 'Wind Direction', 'description': 'Wind direction', 'sourceKey': 'winddirection_10m_dominant'},
	'environment.light.irradiance.daily':           {'type': 'radiation', 'sourceUnit': 'W/m^2', 'title': 'Total Shortwave Radiation', 'description': 'Total shortwave radiation for the day', 'sourceKey': 'shortwave_radiation_sum'},
	'time.time':                                    {'type': 'datetime', 'sourceUnit': 'ISO8601', 'format': ['%Y-%m-%dT%H:%M', '%Y-%m-%d'], 'title': 'Time', 'description': 'Time', 'sourceKey': 'time'},

	'dataMaps':                                     {
		'daily':  ['daily'],
		'hourly': ['hourly'],
	},

}

basicParams = [
	'temperature_2m',
	'relativehumidity_2m',
	'dewpoint_2m',
	'apparent_temperature',
	'pressure_msl',
	'cloudcover',
	'windspeed_10m',
	'winddirection_10m',
	'windgusts_10m',
	'shortwave_radiation',
	'direct_radiation',
	'diffuse_radiation',
	'precipitation',
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
	params = {'latitude': config.lat, 'longitude': config.lon, 'timezone': config.tz, 'current_weather': 'true'}
	forecast = Endpoint(url='forecast', params={'hourly': basicParams, 'daily': dailyParams})


class OpenMeteo(REST, realtime=False, hourly=True, daily=True):
	urls = OpenMeteoURLs()
	translator = unitDefinitions
	name = 'OpenMeteo'

	def __init__(self, *args, **kwargs):
		super(OpenMeteo, self).__init__(*args, **kwargs)

	def start(self):
		self.requestTimer = ScheduledEvent(timedelta(minutes=15), self.getForecast)
		self.requestTimer.start(True)

	def normalizeData(self, rawData):
		if 'hourly' in rawData:
			hourlyData = rawData['hourly']
			timeArray = hourlyData.pop('time')
			hourly = {}
			for key, value in hourlyData.items():
				for measurement, time in zip(value, timeArray):
					if time not in hourly:
						hourly[time] = {'time': time}
					hourly[time][key] = measurement
			rawData['hourly'] = hourly
		if 'daily' in rawData:
			dailyData = rawData['daily']
			daily = {}
			for key, value in dailyData.items():
				for measurement, time in zip(value, dailyData['time']):
					if time not in daily:
						daily[time] = {'time': time}
					daily[time][key] = measurement
			rawData['daily'] = daily
		return rawData

	async def getForecast(self):
		data = await self.getData(self.urls.forecast)
		if data is None:
			print('OpenMeteo: No data received')
			return
		data['source'] = [self.name, self.urls.forecast]
		await self.hourly.asyncUpdate(data)
		await self.daily.asyncUpdate(data)


__plugin__ = OpenMeteo