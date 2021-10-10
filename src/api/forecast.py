import logging
from datetime import datetime, timedelta
from typing import Union

import numpy as np
import pylunar
import pysolar.solar as solar
from climacell_api.client import ClimacellApiClient
from climacell_api.climacell_response import ClimacellResponse, ObservationData
from pysolar import util
from pytz import utc

from src.api.errors import APIError, BadRequest, TooManyRequests, Unauthorized
from src import config
from src.constants import fields, FORECAST_TYPES, maxDates
from src.utils import formatDate, smoothData, interpData


class Forecast:
	live: bool = True
	forecastLength: timedelta
	tz = config.tz
	data: dict[str: Union[np.ndarray, list]] = {}
	lat: float
	lon: float
	fields: list[str]
	apiKey: str
	forecastType: str
	allowedFields: list[str]

	lastCall: datetime
	liveUpdate: bool = True

	def __init__(self, forecastType: str, measurementFields: Union[list[str], str] = None) -> None:

		super().__init__()

		if forecastType not in FORECAST_TYPES:
			raise ValueError("This is not a valid forecast type. Valid values are: {}".format(FORECAST_TYPES))
		if not set(measurementFields).issubset(set(fields.HOURLY)):
			raise ValueError("Measures are not valid.  Must be {}".format(fields.HOURLY))

		self.apiKey = config.cc['apiKey']
		self.forecastType = forecastType
		self.fields = measurementFields
		self.lat, self.lon = config.loc

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

	def update(self, apiCall, *args, **kwargs):
		response = apiCall(*args, **kwargs)

		if response.status_code == 200:
			self.live = True
			self.data = response.data()
		elif response.status_code == 400:
			self.live = False
			logging.error('Bad request:', response.data())
			raise BadRequest
		elif response.status_code == 401:
			self.live = False
			logging.error('Unauthorized:', response.data())
			raise Unauthorized
		elif response.status_code == 429:
			self.live = False
			logging.error('Too Many Requests:', response.data())
			raise TooManyRequests
		else:
			self.live = False
			logging.error(response.data())
			raise APIError

		return True

	def builddict(self):

		data: dict[str, Union[list, str]] = {'timestamp': [], 'timestampInt': [], 'type': self.forecastType,
		                                     'units':     {}}

		for value in self.fields:
			data[value] = []

		return data

	@staticmethod
	def decdeg2dms(dd):
		mnt, sec = divmod(dd * 3600, 60)
		deg, mnt = divmod(mnt, 60)
		return deg, mnt, sec

	@staticmethod
	def decdeg2dms2(dd):
		is_positive = dd >= 0
		dd = abs(dd)
		minutes, seconds = divmod(dd * 3600, 60)
		degrees, minutes = divmod(minutes, 60)
		degrees = degrees if is_positive else -degrees
		return degrees, minutes, seconds

	@staticmethod
	def daterange(start_date, end_date):
		for n in range(int((end_date - start_date).days)):
			yield start_date + timedelta(n)

	def celestialGraph(self, interval: int = 5):

		mi = pylunar.MoonInfo(self.decdeg2dms(self.lat), self.decdeg2dms(self.lon))
		sun = []
		moon = []
		moonPhase = []
		minutes = []
		index = 0
		for date in self.data['timestamp']:
			# for x in range(0, 60, interval):

			solarAltitude = solar.get_altitude_fast(self.lat, self.lon, date)

			sun.append(solarAltitude)

			mi.update(date)
			lunarAltitude = mi.altitude()

			moon.append(lunarAltitude)
			moonPhase.append(mi.age())
			index += 1

		start = self.data['timestamp'][0] - timedelta(days=1)
		end = start + timedelta(days=6)

		moonTransit = []
		sunTimes = []
		for day in self.dates:
			mi.update(day)
			lunarTransit = self.findTransit(day, mi)
			if lunarTransit:
				utcDate: datetime = lunarTransit.astimezone(utc)
				mi.update(utcDate)
				moonMaxAltitude = mi.altitude()
				moonAge = mi.age()
				lunarRotation = self.getAngle(lunarTransit, mi)

				moonTransit.append({'time': lunarTransit, 'maxAltitude': moonMaxAltitude,
				                    'age':  moonAge, 'rotation': lunarRotation})

			solarTransit = util.get_sunrise_sunset_transit(self.lat, self.lon, day)[2]
			solarMaxAltitude = solar.get_altitude_fast(self.lat, self.lon, solarTransit)

			sunTimes.append({'time': solarTransit, 'maxAltitude': solarMaxAltitude})

		self.data['sun'] = sun
		self.data['moon'] = moon
		self.data['moonPhase'] = moonPhase
		self.data['solarTransit'] = sunTimes
		self.data['lunarTransit'] = moonTransit
		self.data['minutes'] = minutes

	def getAngle(self, date, mi) -> float:

		sunalt = solar.get_altitude_fast(self.lat, self.lon, date)
		sunaz = solar.get_azimuth_fast(self.lat, self.lon, date)
		moonaz = mi.azimuth()
		moonalt = mi.altitude()

		dLon = (sunaz - moonaz)
		y = np.sin(np.deg2rad(dLon)) * np.cos(np.deg2rad(sunalt))
		x = np.cos(np.deg2rad(moonalt)) * np.sin(np.deg2rad(sunalt)) - np.sin(np.deg2rad(moonalt)) * np.cos(
				np.deg2rad(sunalt)) * np.cos(np.deg2rad(dLon))
		brng = np.arctan2(y, x)
		brng = np.rad2deg(brng)
		return brng

	def findTransit(self, date: datetime, mi) -> datetime:
		mi.update(date, )
		a = mi.rise_set_times(date.tzinfo.zone)
		for x in a:
			if 'transit' in x:
				return self.tuple2date(x[1], date.tzinfo)

	@staticmethod
	def tuple2date(dateTuple, tz=None) -> Union[datetime, None]:
		try:
			date = datetime(dateTuple[0], dateTuple[1], dateTuple[2], dateTuple[3], dateTuple[4], dateTuple[5])
			if tz:
				date = date.replace(tzinfo=tz)
		except TypeError:
			date = None
		return date

	def fieldFilter(self, requested: Union[list[str], str], forecastType: str) -> list[str]:
		# return list(set(requested).intersection(forecastType)) or list(forecastType)
		return list(set(requested).intersection(forecastType))

	def minMaxP2P(self) -> tuple[float, float, float]:
		arr = np.concatenate(((self.data['feels_like']), (self.data['temp']), (self.data['dewpoint'])), axis=0)
		return float(arr.min()), float(arr.max()), float(arr.ptp())

	def mapData(self, inputData: Union[list[ObservationData], ObservationData], interpolate: bool = True) -> dict[
		str, list[ObservationData]]:

		temp = False
		precipitation = False
		light = True
		x = {'precipitation':               True,
		     'temp':                        True,
		     'feels_like':                  True,
		     'dewpoint':                    True,
		     'cloud_cover':                 True,
		     'cloud_ceiling':               True,
		     'cloud_base':                  True,
		     'surface_shortwave_radiation': True,
		     'timestampInt':                True,
		     'timestamp':                   True,
		     'wind_speed':                  True,
		     'wind_direction':              True
		     }

		output: dict[str, Union[list, str, int]] = self.builddict()

		for measurement in inputData:
			time = formatDate(measurement.observation_time, config.tz, utc=True)
			output['timestampInt'].append(time.timestamp())
			output['timestamp'].append(time)
			for field in measurement.fields:
				if field in ['sunrise', 'sunset']:
					output[field].append(formatDate(measurement.measurements[field].value, config.tz.zone, utc=True))
				# elif field in ['cloud_base', 'cloud_ceiling']:
				# 	if value == None:
				# 		value = 0
				else:
					output[field].append(measurement.measurements[field].value)
					output['units'][field] = measurement.measurements[field].units
		if interpolate:
			for field in x.keys():
				if x[field] and None not in output[field]:
					if field == 'surface_shortwave_radiation':
						output[field] = smoothData(interpData(output[field], 4), 4, 1)
					elif field == 'cloud_cover':
						output[field] = smoothData(interpData(output[field], 4), 21, 1)
					else:
						output[field] = smoothData(interpData(output[field], 2), 5, 1)

		self.forecastLength = timedelta(seconds=(output['timestamp'][-1] - output['timestamp'][0]).total_seconds())

		output['splitDates'] = []
		today = datetime(output['timestamp'][0].year, output['timestamp'][0].month, output['timestamp'][0].day)
		for x in output['timestamp']:
			dif = (datetime(x.year, x.month, x.day) - today).days
			try:
				output['splitDates'][dif].append(x)
			except IndexError:
				output['splitDates'].append([x])

		for x in range(0, len(output['splitDates'])):
			output['splitDates'][x] = np.array(output['splitDates'][x])

		output['length'] = len(output['timestamp'])

		accumulation = []
		for x in range(0, len(output['precipitation'])):
			accumulation.append(sum(output['precipitation'][:x]))

		output['precipitation_accumulation'] = accumulation
		return output

	@property
	def dates(self) -> list[datetime]:
		return [item[round(item.size / 2)] for item in self.data['splitDates']]

	@property
	def dateRange(self):
		return self.data['timestamp'][0], self.data['timestamp'][-1]

	# def combineForecasts(self):
	# 	# def combineForecasts(self, forecasts: Union[list[str], str, None], fields: Union[list[str], str]) -> dict[str, np.array]:
	#
	# 	dict = {'timestamp': self.dateArray()}
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
	# 		dict[field] = np.array(valueArray)
	#
	# 	### TODO: add unit value
	# 	return dict

	def makeItRain(self, length: int) -> np.ndarray:
		np.random.seed(19680801)
		return np.random.random_integers(0, 100, length)


class hourlyForecast(Forecast):
	lastCall: datetime
	liveUpdate = True
	allowedFields: list[str] = ['precipitation', 'precipitation_type', 'precipitation_probability', 'temp',
	                            'feels_like', 'dewpoint', 'wind_speed', 'wind_gust', 'baro_pressure', 'visibility',
	                            'humidity', 'wind_direction', 'sunrise', 'sunset', 'cloud_cover', 'cloud_ceiling',
	                            'cloud_base', 'surface_shortwave_radiation', 'moon_phase', 'weather_code']

	def __init__(self) -> None:
		fields = ['temp', 'precipitation', 'sunrise', 'sunset',
		          'feels_like', 'dewpoint', 'precipitation_probability',
		          'cloud_cover', 'surface_shortwave_radiation',
		          'wind_speed',
		          'epa_aqi', 'cloud_ceiling', 'cloud_base',
		          'wind_direction']
		super().__init__('hourly', fields)
		self.client = ClimacellApiClient(self.apiKey)
		self.lastCall = datetime.now() - timedelta(minutes=1)
		self.update()
		self.celestialGraph()

	def update(self):
		if self.lastCall < datetime.now() - timedelta(seconds=5):
			super().update(self.client.forecast_hourly, lat=self.lat,
			               lon=self.lon,
			               end_time=maxDates.hourly(),
			               fields=self.fields,
			               units='us')
			self.data = self.mapData(self.data)

			self.lastCall = datetime.now()
			print('hourly updated at {}'.format(self.lastCall.strftime('%H:%M:%S')))
		return True

	@property
	def dd(self):
		return self.data


class dailyForecast(Forecast):
	lastCall: datetime
	liveUpdate = True
	data: ClimacellResponse
	allowedFields: list[str] = ['precipitation', 'precipitation_type', 'precipitation_probability', 'temp',
	                            'feels_like', 'dewpoint', 'wind_speed', 'wind_gust', 'baro_pressure', 'visibility',
	                            'humidity', 'wind_direction', 'sunrise', 'sunset', 'cloud_cover', 'cloud_ceiling',
	                            'cloud_base', 'surface_shortwave_radiation', 'moon_phase', 'weather_code']

	def __init__(self, measurementFields: Union[list[str], str] = None) -> None:
		super().__init__('hourly', measurementFields)
		self.client = ClimacellApiClient(self.apiKey)
		self.update()

	def update(self):
		super().update(self.client.forecast_daily, lat=self.lat,
		               lon=self.lon,
		               end_time=maxDates.hourly(),
		               fields=self.fields,
		               units='us')
		return True

	def mapData(self, inputData: Union[list[ObservationData], ObservationData], interpolate: bool = True) -> dict[
		str, list[ObservationData]]:
		pass


class nowcast(Forecast):
	allowedFields: list[str] = ['precipitation', 'precipitation_type', 'temp', 'feels_like', 'dewpoint', 'wind_speed',
	                            'wind_gust', 'baro_pressure', 'visibility', 'humidity', 'wind_direction', 'sunrise',
	                            'sunset', 'cloud_cover', 'cloud_ceiling', 'cloud_base', 'surface_shortwave_radiation',
	                            'weather_code']

	def __init__(self, measurementFields: Union[list[str], str] = None, interval: int = 1) -> None:
		super().__init__('nowcast', measurementFields, interval=interval)
		self.client = ClimacellApiClient(self.apiKey)
		self.lastCall = datetime.now() - timedelta(minutes=1)
		self.interval = interval
		self.dataUpdate()

	def dataUpdate(self):
		# if self.lastCall < datetime.now() - timedelta(seconds=5):

		self.data = self.mapData(self.client.nowcast(lat=self.lat,
		                                             lon=self.lon,
		                                             end_time=maxDates.nowcast(),
		                                             fields=self.fields,
		                                             units='us',
		                                             timestep=self.interval).data())

		self.lastCall = datetime.now()
		print('nowcast updated at {}'.format(self.lastCall.strftime('%H:%M:%S')))
		return True
