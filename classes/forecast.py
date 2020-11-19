from typing import Any, Union

import numpy as np
from climacell_api.client import ClimacellApiClient
from climacell_api.climacell_response import ObservationData

from .constants import fields, maxDates


class forecast:
	data: dict[str: Union[np.ndarray, list]] = {}

	def __init__(self, key, lat_lon: tuple[str, str], forecastTypes: Union[list[str], str],
				 measurementFields: Union[list[str], str] = None) -> None:
		self.apiKey = key
		self.dates = []
		self.forecastTypes = forecastTypes
		self.fields = measurementFields
		self.lat, self.lon = lat_lon
		self.getData()
		self.combineForecasts()

	def getData(self):

		lat, lon = self.lat, self.lon

		client = ClimacellApiClient(self.apiKey)

		def buildDictionary():

			data: dict[str, Union[list, str]] = {'timestamp': [], 'type': self.forecastTypes, 'units': {}}

			for value in self.fields:
				data[value] = []

			return data

		def mapData(data: Union[list[ObservationData], ObservationData], forecastType: str) -> dict[
			str, list[ObservationData]]:

			output = buildDictionary(data[0].fields, forecastType)

			if forecastType == 'realtime':
				for field in data.fields:
					self.data['units'][field] = data.units
					output['timestamp'].append(data.observation_time)
					output[field].append(data.measurements[field].value)

			elif forecastType == 'historical':
				# disables historical data for now
				pass
				for measurement in data:
					import json
					if "None" in json.load(measurement.raw_json):
						pass
					else:
						output['timestamp'].append(measurement.observation_time)
						for field in measurement.fields:
							self.units[field] = measurement.measurements[field].units
							output[field].append(measurement.measurements[field].value)

			else:
				for measurement in data:
					output['timestamp'].append(measurement.observation_time)
					for field in measurement.fields:
						self.units[field] = measurement.measurements[field].units
						output[field].append(measurement.measurements[field].value)

			return output

		def fieldFilter(requested: Union[list[str], str], forecastType: list[str]) -> [str]:
			# return list(set(requested).intersection(forecastType)) or list(forecastType)
			return list(set(requested).intersection(forecastType))

		def realtime(measurementFields: Union[list[str], str, None]):

			return mapData(client.realtime(lat=self.lat,
										   lon=self.lon,
										   fields=fields.REALTIME,
										   units='us'
										   ).data(), 'realtime')

		def nowcast(measurementFields: Union[list[str], str, None]):
			# requested = list(filter(measurementFields, fields.NOWCAST))
			return mapData(client.nowcast(lat=self.lat, lon=self.lon, end_time=maxDates.nowcast(),
										  fields=fields.NOWCAST, units='us',
										  timestep=1).data(), 'nowcast')

		def hourly(measurementFields: Union[list[str], str, None]):
			return mapData(client.forecast_hourly(lat=self.lat,
												  lon=self.lon,
												  start_time=maxDates.nowcast(),
												  end_time=maxDates.hourly(),
												  fields=fields.HOURLY,
												  units='us').data(), 'hourly')

		def daily(measurementFields: Union[list[str], str, None]):
			return mapData(client.forecast_daily(lat=self.lat,
												 lon=self.lon,
												 start_time=maxDates.hourly(),
												 end_time=maxDates.daily(),
												 fields=fields.DAILY,
												 units='us').data(), 'daily')

		def historical(measurementFields: Union[list[str], str, None]):
			return mapData(client.historical_climacell(lat=self.lat,
													   lon=self.lon,
													   timestep=5,
													   start_time=maxDates.historical(),
													   end_time='now',
													   fields=fields.HISTORICAL,
													   units='us').data(), 'historical')

		forecastData = {}
		if 'historical' in self.forecastTypes:
			forecastData['historical'] = historical()
		if 'realtime' in self.forecastTypes:
			forecastData['realtime'] = realtime()
		if 'nowcast' in self.forecastTypes:
			forecastData['nowcast'] = nowcast()
		if 'hourly' in self.forecastTypes:
			forecastData['hourly'] = hourly()
		if 'daily' in self.forecastTypes:
			forecastData['daily'] = daily()

		return forecastData

	def dateArray(self):
	# def dateArray(self, data: dict[str: Union[np.ndarray, list]], forecasts: Union[list[str], str, None]):

		array = []


		# for set(data.keys()).intersection(FORECAST_TYPES):


		if 'historical' in self.fields:
			array += self.historical['timestamp']
		if 'realtime' in forecasts:
			array += self.realtime['timestamp']
		if 'nowcast' in forecasts:
			array += self.nowcast['timestamp']
		if 'hourly' in forecasts:
			array += self.hourly['timestamp']
		if 'daily' in forecasts:
			array += self.daily['timestamp']

		return np.array(array)

	def combineForecasts(self)
	# def combineForecasts(self, forecasts: Union[list[str], str, None], fields: Union[list[str], str]) -> dict[str, np.array]:

		dictionary = {'timestamp': self.dateArray()}
		commonFields = set(self.fields)
		if self.historical:
			commonFields = set(self.historical.keys()).intersection(commonFields)
		if self.realtime:
			commonFields = set(self.realtime.keys()).intersection(commonFields)
		if self.nowcast:
			commonFields = set(self.nowcast.keys()).intersection(commonFields)
		if self.hourly:
			commonFields = set(self.hourly.keys()).intersection(commonFields)
		if self.daily:
			commonFields = set(self.daily.keys()).intersection(commonFields)

		for field in commonFields:

			valueArray: list[Any] = []

			if 'historical' in forecasts and field in self.historical.keys():
				valueArray += self.historical[field]

			if 'realtime' in forecasts and field in self.realtime.keys():
				valueArray += self.realtime[field]

			if 'nowcast' in forecasts and field in self.nowcast.keys():
				valueArray += self.nowcast[field]

			if 'hourly' in forecasts and field in self.hourly.keys():
				valueArray += self.hourly[field]

			if 'daily' in forecasts and field in self.daily.keys():
				valueArray += self.daily[field]
			dictionary[field] = np.array(valueArray)

		### TODO: add unit value
		return dictionary

	def makeItRain(self, length: int) -> np.ndarray:
		np.random.seed(19680801)
		return np.random.random_integers(0, 100, length)

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


