import logging
from typing import Any

from _easyDict import SmartDictionary
from src.observations.AmbientWeather import AWObservation
from src.observations.WeatherFlow import WFObservation
from src.translators import Translator, WFTranslator


logging.getLogger().setLevel(logging.INFO)


class _WeatherStation:
	__indoor: AWObservation
	__outdoor: AWObservation
	__currentWeather: Any
	__translator = Translator


class WeatherFlowStation(_WeatherStation):
	__info = dict[str:Any]
	__currentWeather: Any
	__hourlyForecast: Any
	__dailyForecast: Any
	__translator: WFTranslator

	def __init__(self, data):
		observationData = data['obs'][0]
		__currentWeather = WFObservation(observationData)


class AmbientWeatherStation:
	__info: dict[str:Any]

	empty = {'dateutc':        None, 'tempinf': None, 'humidityin': None, 'baromrelin': None, 'baromabsin': None,
	         'tempf':          None,
	         'winddir':        None, 'windspeedmph': None, 'windgustmph': None, 'maxdailygust': None,
	         'hourlyrainin':   None,
	         'eventrainin':    None, 'dailyrainin': None, 'weeklyrainin': None, 'monthlyrainin': None,
	         'totalrainin':    None,
	         'solarradiation': None, 'uv': None, 'feelsLike': None, 'dewPoint': None, 'feelsLikein': None,
	         'dewPointin':     None,
	         'lastRain':       None, 'tz': None, 'date': None}

	def __init__(self, data: SmartDictionary):
		print(data)

	@property
	def coordinates(self) -> tuple[float, float]:
		return self.__info['coords']['coords']['lat'], self.__info['coords']['coords']['lon']

	@property
	def type(self) -> str:
		return self.__info['location']

	@property
	def address(self) -> str:
		return self.__info['coords']['address']

	@property
	def elevation(self) -> float:
		return self.__info['coords']['elevation']

	@property
	def city(self) -> str:
		return self.__info['coords']['location']

	@property
	def name(self) -> str:
		return self.__info['name']
