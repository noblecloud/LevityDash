import logging as log
import threading
from time import sleep

from ambient_api.ambientapi import AmbientAPI

from classes.general import *


class Realtime(threading.Thread):
	api: AmbientAPI
	stations: list[Union[WeatherStation, AmbientWeatherStation]]
	interval: int
	liveUpdates = True

	def __init__(self, apiKey, appKey, url: str = 'https://api.ambientweather.net/v1', interval: int = 15):
		super().__init__()
		self.stations = []
		self.interval = interval
		self.api = AmbientAPI(AMBIENT_ENDPOINT=url,
		                      AMBIENT_API_KEY=apiKey,
		                      AMBIENT_APPLICATION_KEY=appKey)
		log.info('Fetching initial realtime data')
		self.getData()
		print('test')


	def getData(self):
		# self.stations.clear()
		stationArray = []
		devices = self.api.get_devices()
		for x in devices:
			stationArray.append(AmbientWeatherStation(x.last_data, x.info))
		self.stations = stationArray

	def run(self):
		while self.liveUpdates:
			log.info('updating realtime data')
			self.getData()
			sleep(self.interval)

	@property
	def nearest(self):
		return self.stations[0]

key = 'e574e1bfb9804a52a1084c9f1a4ee5d88e9e850fc1004aeaa5010f15c4a23260'
app = 'ec02a6c4e29d42e086d98f5db18972ba9b93d864471443919bb2956f73363395'
r = Realtime(key, app)
