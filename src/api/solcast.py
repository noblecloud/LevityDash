from src import logging
from datetime import timedelta

from typing import List, Literal, Union

from .baseAPI import URLs, API
from src.observations.solcast import SolcastForecast, SolcastObservation
from src import config

log = logging.getLogger(__name__)


class SolcastURLs(URLs):
	base = 'https://api.solcast.com.au'
	forecast = 'world_radiation/forecasts'


class Solcast(API):
	_urls: SolcastURLs
	_baseParams: dict[str, Literal] = {'apikey':    config.api.solcast['apiKey'],
	                                   'hours':     168,
	                                   "latitude":  config.lat,
	                                   "longitude": config.lon,
	                                   "format":    "json",
	                                   }
	_headers: dict = {'Authorization': f'Bearer {config.api.solcast["apiKey"]}'}
	forecast: SolcastForecast
	realtime: SolcastObservation
	_forecastRefreshInterval = timedelta(minutes=120)

	def getForecast(self):
		data = super(Solcast, self).getData()
		self.forecast.update(data)
		self.realtime = self.forecast[0]

	# noinspection PySameParameterValue
	def loadData(self, data: Union[str, dict]):
		data = super(Solcast, self).loadData(data)
		self.forecast.update(data)
		if self.realtime is None:
			self.realtime = self.forecast[0]

	def _normalizeData(self, rawData) -> List[dict[str: Literal]]:
		rawData: List[dict[str:int]] = rawData.pop('forecasts')
		return rawData


if __name__ == '__main__':
	c = Solcast()
	c.loadData('solcast.json')
	x = c.realtime['illuminance']
	f = c.realtime['irradiance']
	# c.getData()
	pass
