from src import logging
from datetime import datetime, timedelta

from PySide2.QtCore import QTimer

from src.observations.openmeteo import OpenMeteoForecastDaily, OpenMeteoForecastHourly, OpenMeteoObservation
from src import config
from src.api.baseAPI import API, URLs

log = logging.getLogger(__name__)


class OpenMeteoURLs(URLs, realtime=False, daily=True, hourly=True):
	base = 'https://api.open-meteo.com/v1/'
	forecast = 'forecast'


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
	'soil_moisture_27_81cm'
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


class OpenMeteo(API):
	_baseParams: dict[str, str] = {'latitude': config.lat, 'longitude': config.lon, 'timezone': config.tz, 'current_weather': 'true'}

	_urls: OpenMeteoURLs
	realtime: OpenMeteoObservation
	hourly: OpenMeteoForecastHourly
	daily: OpenMeteoForecastDaily
	_forecastRefreshInterval = timedelta(minutes=15)

	def __init__(self):
		super(OpenMeteo, self).__init__()
		self.getForecast()

	def _normalizeData(self, rawData):
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

	def getForecast(self):
		params = {'hourly': basicParams,
		          'daily':  dailyParams}
		data = super(OpenMeteo, self).getData(endpoint=self._urls.forecast, params=params)
		self.hourly.update(data['hourly'])
		self.daily.update(data['daily'])
		now = datetime.now()
		now = datetime(year=now.year, month=now.month, day=now.day, hour=now.hour if now.minute < 30 else now.hour + 1).strftime('%Y-%m-%dT%H:%M')
		realtimeISH = data['hourly'][now]
		realtimeISH['temperature_2m'] = data['current_weather']['temperature']
		realtimeISH['windspeed_10m'] = data['current_weather']['windspeed']
		realtimeISH['winddirection_10m'] = data['current_weather']['winddirection']
		realtimeISH['time'] = now
		self.realtime.update(realtimeISH)


if __name__ == '__main__':
	logging.getLogger().setLevel(logging.DEBUG)
	openMeteo = OpenMeteo()
	openMeteo.getData()
	pass
