from ambient_api.ambientapi import AmbientAPI

from classes.general import *


class NoRealtimeData(Exception):
	pass


class Realtime:
	api: AmbientAPI
	stations: list[Union[WeatherStation, AmbientWeatherStation]]
	interval: int
	live = True

	def __init__(self, apiKey, appKey, url: str = 'https://api.ambientweather.net/v1', interval: int = 15):
		self.stations = []
		self.interval = interval
		self.api = AmbientAPI(AMBIENT_ENDPOINT=url,
		                      AMBIENT_API_KEY=apiKey,
		                      AMBIENT_APPLICATION_KEY=appKey)

	def update(self):
		# self.stations.clear()
		stationArray = []
		devices = self.api.get_devices()
		if devices:
			for x in devices:
				x = apiDictionary(x)
				stationArray.append(AmbientWeatherStation(x))
			self.stations = stationArray
			self.live = True
		else:
			self.live = False
			raise NoRealtimeData

	@property
	def nearest(self):
		try:
			return self.stations[0]
		except IndexError:
			return NoRealtimeData




lat, lon = 37.40834, -76.54845
key = "q2W59y2MsmBLqmxbw34QGdtS5hABEwLl"
AmbKey = 'e574e1bfb9804a52a1084c9f1a4ee5d88e9e850fc1004aeaa5010f15c4a23260'
AmbApp = 'ec02a6c4e29d42e086d98f5db18972ba9b93d864471443919bb2956f73363395'

if __name__ == "__main__":
	print('something is wrong with realtime.py if you are seeing this in the main application')
	s = Realtime(AmbKey, AmbApp)
	s.update()
	print(s.nearest)
	from guppy import hpy
	h = hpy()
	print(h.heap().all)
	print(h.iso(1,[],{}))
