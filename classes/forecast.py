from typing import Any, Union

import numpy as np
from climacell_api.client import ClimacellApiClient
from climacell_api.climacell_response import ObservationData

from .constants import fields, maxDates, FORECAST_TYPES


class Forecast:
	data: dict[str: Union[np.ndarray, list]] = {}
	lat: float
	lon: float
	fields: list[str]
	apiKey: str
	forecastType: str
	allowedFields: list[str]

	def __init__(self, key, lat_lon: tuple[float, float], forecastType: str,
				 measurementFields: Union[list[str], str] = None) -> None:

		if forecastType not in FORECAST_TYPES:
			raise ValueError("This is not a valid forecast type. Valid values are: {}".format(FORECAST_TYPES))
		if not set(measurementFields).issubset(set(fields.HOURLY)):
			raise ValueError("Measures are not valid.  Must be {}".format(fields.HOURLY))

		self.apiKey = key
		self.forecastType = forecastType
		self.fields = measurementFields
		self.lat, self.lon = lat_lon

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
					  'units': self.data['units'],
					  'type': self.data['type']}

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

		output: dict[str, Union[list, str]] = self.buildDictionary()

		for measurement in inputData:
			output['timestamp'].append(measurement.observation_time)
			for field in measurement.fields:
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


class hourlyForecast(Forecast):

	allowedFields: list[str] = ['precipitation', 'precipitation_type', 'precipitation_probability', 'temp', 'feels_like',
						 'dewpoint', 'wind_speed', 'wind_gust', 'baro_pressure', 'visibility', 'humidity',
						 'wind_direction', 'sunrise', 'sunset', 'cloud_cover', 'cloud_ceiling', 'cloud_base',
						 'surface_shortwave_radiation', 'moon_phase', 'weather_code']

	def __init__(self, key, lat_lon: tuple[float, float], forecastType: str,
				 measurementFields: Union[list[str], str] = None) -> None:

		super().__init__(key, lat_lon, forecastType, measurementFields)

		self.data = self.getData()

	def getData(self):

		client = ClimacellApiClient(self.apiKey)

		forecastData = {}

		data = client.forecast_hourly(lat=self.lat,
									  lon=self.lon,
									  start_time=maxDates.nowcast(),
									  end_time=maxDates.hourly(),
									  fields=self.fields,
									  units='us').data()
		print(data)
		forecastData = self.mapData(data)

		return forecastData


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

class display():
	def __init__(self, x, y, d):
		self.x = x
		self.y = y
		self.d = d

	@property
	def dpi(self):
		from math import sqrt
		diag = sqrt(self.x ** 2 + self.y ** 2)
		return round(diag / self.d)
