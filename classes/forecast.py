import threading
import time
from typing import Union

import numpy as np
from climacell_api.client import ClimacellApiClient
from climacell_api.climacell_response import ObservationData

from .constants import fields, FORECAST_TYPES, maxDates


class Forecast(threading.Thread):
	data: dict[str: Union[np.ndarray, list]] = {}
	lat: float
	lon: float
	fields: list[str]
	apiKey: str
	forecastType: str
	allowedFields: list[str]

	def __init__(self, key, lat_lon: tuple[float, float], forecastType: str,
	             measurementFields: Union[list[str], str] = None, interval: int = 5) -> None:

		super().__init__()
		self.interval = interval

		if forecastType not in FORECAST_TYPES:
			raise ValueError("This is not a valid forecast type. Valid values are: {}".format(FORECAST_TYPES))
		if not set(measurementFields).issubset(set(fields.HOURLY)):
			raise ValueError("Measures are not valid.  Must be {}".format(fields.HOURLY))

		self.apiKey = key
		self.forecastType = forecastType
		self.fields = measurementFields
		self.lat, self.lon = lat_lon

	def run(self):
		while True:
			print('This is just a while loop')
			time.sleep(5)

	def __getitem__(self, item):

		if isinstance(item, str):
			return self.data[item]

		if isinstance(item, int):
			result = {'timestamp': self.data['timestamp'][item],
			          'units':     self.data['units'],
			          'type':      self.data['type']}

			for field in self.fields:
				result[field] = self.data[field][item]

			return result

	def __iter__(self):
		self.n = 0
		self.max = len(self.data['timestamp']) - 1
		return self

	def __next__(self):
		if self.n <= self.max:

			result = {'timestamp': self.data['timestamp'][self.n],
			          'units':     self.data['units'],
			          'type':      self.data['type']}

			for field in self.fields:
				result[field] = self.data[field][self.n]

			self.n += 1

			return result
		else:
			raise StopIteration

	def buildDictionary(self):

		data: dict[str, Union[list, str]] = {'timestamp': [], 'type': self.forecastType, 'units': {}}

		for value in self.fields:
			data[value] = []

		return data

	def fieldFilter(self, requested: Union[list[str], str], forecastType: str) -> list[str]:
		# return list(set(requested).intersection(forecastType)) or list(forecastType)
		return list(set(requested).intersection(forecastType))

	def mapData(self, inputData: Union[list[ObservationData], ObservationData]) -> dict[
		str, list[ObservationData]]:

		import dateutil.parser
		from classes.constants import tz

		output: dict[str, Union[list, str]] = self.buildDictionary()

		for measurement in inputData:
			from classes.constants import utc
			utcTimestamp = measurement.observation_time
			localTimestamp = utcTimestamp.replace(tzinfo=utc)
			localTimestamp = localTimestamp.astimezone(tz)
			output['timestamp'].append(localTimestamp)
			for field in measurement.fields:
				if field in ['sunrise', 'sunset']:
					value = dateutil.parser.parse(measurement.measurements[field].value)

					localDate = value.replace(tzinfo=utc)
					localDate = localDate.astimezone(tz)

					output[field].append(localDate)
				else:
					output[field].append(measurement.measurements[field].value)
					output['units'][field] = measurement.measurements[field].units

		return output

	# def combineForecasts(self):
	# 	# def combineForecasts(self, forecasts: Union[list[str], str, None], fields: Union[list[str], str]) -> dict[str, np.array]:
	#
	# 	dictionary = {'timestamp': self.dateArray()}
	# 	commonFields = set(self.fields)
	# 	if self.historical:
	# 		commonFields = set(self.historical.keys()).intersection(commonFields)
	# 	if self.realtime:
	# 		commonFields = set(self.realtime.keys()).intersection(commonFields)
	# 	if self.nowcast:
	# 		commonFields = set(self.nowcast.keys()).intersection(commonFields)
	# 	if self.hourly:
	# 		commonFields = set(self.hourly.keys()).intersection(commonFields)
	# 	if self.daily:
	# 		commonFields = set(self.daily.keys()).intersection(commonFields)
	#
	# 	for field in commonFields:
	#
	# 		valueArray: list[Any] = []
	#
	# 		if 'historical' in forecasts and field in self.historical.keys():
	# 			valueArray += self.historical[field]
	#
	# 		if 'realtime' in forecasts and field in self.realtime.keys():
	# 			valueArray += self.realtime[field]
	#
	# 		if 'nowcast' in forecasts and field in self.nowcast.keys():
	# 			valueArray += self.nowcast[field]
	#
	# 		if 'hourly' in forecasts and field in self.hourly.keys():
	# 			valueArray += self.hourly[field]
	#
	# 		if 'daily' in forecasts and field in self.daily.keys():
	# 			valueArray += self.daily[field]
	# 		dictionary[field] = np.array(valueArray)
	#
	# 	### TODO: add unit value
	# 	return dictionary

	def makeItRain(self, length: int) -> np.ndarray:
		np.random.seed(19680801)
		return np.random.random_integers(0, 100, length)

	def update(self):
		while True:
			time.sleep(self.interval)


import asyncio
from datetime import datetime, timedelta


class hourlyForecast(Forecast):
	lastCall: datetime
	liveUpdate = True
	allowedFields: list[str] = ['precipitation', 'precipitation_type', 'precipitation_probability', 'temp',
	                            'feels_like',
	                            'dewpoint', 'wind_speed', 'wind_gust', 'baro_pressure', 'visibility', 'humidity',
	                            'wind_direction', 'sunrise', 'sunset', 'cloud_cover', 'cloud_ceiling', 'cloud_base',
	                            'surface_shortwave_radiation', 'moon_phase', 'weather_code']

	def __init__(self, key, lat_lon: tuple[float, float], forecastType: str,
	             measurementFields: Union[list[str], str] = None, interval: int = 60) -> None:
		super().__init__(key, lat_lon, forecastType, measurementFields, interval=interval)
		self.client = ClimacellApiClient(self.apiKey)
		self.lastCall = datetime.now() - timedelta(minutes=1)
		self.dataUpdate()

	def dataUpdate(self):

		# if self.lastCall < datetime.now() - timedelta(seconds=5):

		self.data = self.mapData(self.client.forecast_hourly(lat=self.lat,
		                                                     lon=self.lon,
		                                                     start_time='now',
		                                                     end_time=maxDates.hourly(),
		                                                     fields=self.fields,
		                                                     units='us').data())

		self.lastCall = datetime.now()
		print('hourly updated at {}'.format(self.lastCall.strftime('%H:%M:%S')))
		return True
			# else:
			# 	waitTime = (datetime.now() - self.lastCall).total_seconds()
			# 	print('api call too fast, waiting {} seconds'.format(waitTime))
			# 	asyncio.sleep(waitTime)

	def run(self):
		while self.liveUpdate:
			time.sleep(self.interval)
			self.dataUpdate()

	def stop(self):
		self.liveUpdate = False

# lastValue = 0
# for measurement in data:
# 	if measurement.measurements['temp'].value != lastValue:
# 		lastValue = measurement.measurements['temp'].value
# 		for field in fields:
# 			dictionary[field].append(measurement.measurements[field].value)
# 		dateArray.append(measurement.observation_time)
# 	else:
# 		pass
# # historicalDict[field].append(None)
