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

	def getData(self):
		self.stations.clear()
		devices = self.api.get_devices()
		for x in devices:
			self.stations.append(AmbientWeatherStation(x.last_data, x.info))

	def run(self):
		while self.liveUpdates:
			print('updating realtime data')
			self.getData()
			sleep(self.interval)

	@property
	def nearest(self):
		return self.stations[0]
# r = Realtime(key, app)
