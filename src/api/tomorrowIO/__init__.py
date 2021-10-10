import logging
from configparser import ConfigParser
from datetime import datetime, timedelta
from enum import Enum
from typing import Union

import requests

from src.api import APIError
from src.api.baseAPI import API, URLs
from src.api.tomorrowIO.field import *
from src.observations import ObservationForecast
from src.observations.tomorrowIO import TomorrowIOForecastDaily, TomorrowIOForecastHourly, TomorrowIOObservationRealtime
from src import config

log = logging.getLogger(__name__)

WeatherCode = {
		0:    "Unknown",
		1000: "Clear",
		1001: "Cloudy",
		1100: "Mostly Clear",
		1101: "Partly Cloudy",
		1102: "Mostly Cloudy",
		2000: "Fog",
		2100: "Light Fog",
		3000: "Light Wind",
		3001: "Wind",
		3002: "Strong Wind",
		4000: "Drizzle",
		4001: "Rain",
		4200: "Light Rain",
		4201: "Heavy Rain",
		5000: "Snow",
		5001: "Flurries",
		5100: "Light Snow",
		5101: "Heavy Snow",
		6000: "Freezing Drizzle",
		6001: "Freezing Rain",
		6200: "Light Freezing Rain",
		6201: "Heavy Freezing Rain",
		7000: "Ice Pellets",
		7101: "Heavy Ice Pellets",
		7102: "Light Ice Pellets",
		8000: "Thunderstorm"
}

t = {
		'PrimaryPollutant': 'pollutant',
		'PI':               'PollutionIndex',
		'AQI':              'AQI',
		'km':               'length',
		'c':                'temperature',
		'bool':             bool,
		'%':                'precentage',
		'mm':               'length',
		'MoonPhase':        int,
		'μg/m^3':           'concentration',
		'ppb':              'concentration',
		'mm/hr':            'PrecipitationRate',
		'hPa':              'pressure',
		'º':                'direction',
		's':                'time',
		'm':                'length',
		'W/m^2':            'irradiance',
		'm/s':              'wind',
		"weatherCode":      "WeatherCode",

}

v = {
		"cloudBase":                           "km",
		"cloudCeiling":                        "km",
		"cloudCover":                          "%",
		"dewPoint":                            "c",
		"epaHealthConcern":                    "AQI",
		"epaIndex":                            "AQI",
		"epaPrimaryPollutant":                 "PrimaryPollutant",
		"fireIndex":                           "FWI",
		"grassGrassIndex":                     "PI",
		"grassIndex":                          "PI",
		"hailBinary":                          "bool",
		"humidity":                            "%",
		"iceAccumulation":                     "mm",
		"mepHealthConcern":                    "AQI",
		"mepIndex":                            "AQI",
		"mepPrimaryPollutant":                 "PrimaryPollutant",
		"moonPhase":                           "MoonPhase",
		"particulateMatter10":                 "μg/m^3",
		"particulateMatter25":                 "μg/m^3",
		"pollutantCO":                         "ppb",
		"pollutantNO2":                        "ppb",
		"pollutantO3":                         "ppb",
		"pollutantSO2":                        "ppb",
		"precipitationIntensity":              "mm/hr",
		"precipitationProbability":            "%",
		"precipitationType":                   "PrecipitationType",
		"pressureSeaLevel":                    "hPa",
		"pressureSurfaceLevel":                "hPa",
		"primarySwellWaveFromDirection":       "º",
		"primarySwellWaveSMeanPeriod":         "s",
		"primarySwellWaveSignificantHeight":   "m",
		"secondarySwellWaveFromDirection":     "º",
		"secondarySwellWaveSMeanPeriod":       "s",
		"secondarySwellWaveSignificantHeight": "m",
		"soilMoistureVolumetric0To10":         "%",
		"soilMoistureVolumetric10To40":        "%",
		"soilMoistureVolumetric40To100":       "%",
		"soilMoistureVolumetric100To200":      "%",
		"soilMoistureVolumetric0To200":        "%",
		"soilTemperature0To10":                "c",
		"soilTemperature10To40":               "c",
		"soilTemperature40To100":              "c",
		"soilTemperature100To200":             "c",
		"soilTemperature0To200":               "c",
		"solarDIF":                            "W/m^2",
		"solarDIR":                            "W/m^2",
		"solarGHI":                            "W/m^2",
		"snowAccumulation":                    "mm",
		"temperature":                         "c",
		"temperatureApparent":                 "c",
		"tertiarySwellWaveFromDirection":      "º",
		"tertiarySwellWaveSMeanPeriod":        "s",
		"tertiarySwellWaveSignificantHeight":  "m",
		"treeAcacia":                          "PI",
		"treeAsh":                             "PI",
		"treeBeech":                           "PI",
		"treeBirch":                           "PI",
		"treeCedar":                           "PI",
		"treeCottonwood":                      "PI",
		"treeCypress":                         "PI",
		"treeElder":                           "PI",
		"treeElm":                             "PI",
		"treeHemlock":                         "PI",
		"treeHickory":                         "PI",
		"treeIndex":                           "PI",
		"treeJuniper":                         "PI",
		"treeMahagony":                        "PI",
		"treeMaple":                           "PI",
		"treeMulberry":                        "PI",
		"treeOak":                             "PI",
		"treePine":                            "PI",
		"treeSpruce":                          "PI",
		"treeSycamore":                        "PI",
		"treeWalnut":                          "PI",
		"treeWillow":                          "PI",
		"visibility":                          "km",
		"weatherCode":                         "WeatherCode",
		"weedGrassweedIndex":                  "PI",
		"weedIndex":                           "PI",
		"waveSignificantHeight":               "m",
		"waveFromDirection":                   "º",
		"waveMeanPeriod":                      "s",
		"windDirection":                       "º",
		"windGust":                            "m/s",
		"windSpeed":                           "m/s",
		"windWaveSignificantHeight":           "m",
		"windWaveFromDirection":               "º",
		"WindWaveMeanPeriod":                  "s",
}

values = {
		"cloudBase":                           "km",
		"cloudCeiling":                        "km",
		"cloudCover":                          "%",
		"dewPoint":                            "c",
		"epaHealthConcern":                    "airQualityIndex",
		"epaIndex":                            int,
		"epaPrimaryPollutant":                 "epaPrimaryPollutant",
		"fireIndex":                           int,
		"grassGrassIndex":                     'pollutionIndex',
		"grassIndex":                          'pollutionIndex',
		"hailBinary":                          "Binary Prediction",
		"humidity":                            "%",
		"iceAccumulation":                     "mm",
		"mepHealthConcern":                    "AQI",
		"mepIndex":                            "MEP AQI",
		"mepPrimaryPollutant":                 "PrimaryPollutant",
		"moonPhase":                           {
				0: "New",
				1: "Waxing Crescent",
				2: "First Quarter",
				3: "Waxing Gibbous",
				4: "Full",
				5: "Waning Gibbous",
				6: "Third Quarter",
				7: "Waning Crescent"
		},
		"particulateMatter10":                 "μg/m^3",
		"particulateMatter25":                 "μg/m^3",
		"pollutantCO":                         "ppb",
		"pollutantNO2":                        "ppb",
		"pollutantO3":                         "ppb",
		"pollutantSO2":                        "ppb",
		"precipitationIntensity":              "mm/hr",
		"precipitationProbability":            "%",
		"precipitationType":                   {
				0: "N/A",
				1: "Rain",
				2: "Snow",
				3: "Freezing Rain",
				4: "Ice Pellets"
		},
		"pressureSeaLevel":                    "hPa",
		"pressureSurfaceLevel":                "hPa",
		"primarySwellWaveFromDirection":       "º",
		"primarySwellWaveSMeanPeriod":         "s",
		"primarySwellWaveSignificantHeight":   "m",
		"secondarySwellWaveFromDirection":     "º",
		"secondarySwellWaveSMeanPeriod":       "s",
		"secondarySwellWaveSignificantHeight": "m",
		"soilMoistureVolumetric0To10":         "%",
		"soilMoistureVolumetric10To40":        "%",
		"soilMoistureVolumetric40To100":       "%",
		"soilMoistureVolumetric100To200":      "%",
		"soilMoistureVolumetric0To200":        "%",
		"soilTemperature0To10":                "c",
		"soilTemperature10To40":               "c",
		"soilTemperature40To100":              "c",
		"soilTemperature100To200":             "c",
		"soilTemperature0To200":               "c",
		"solarDIF":                            "W/m^2",
		"solarDIR":                            "W/m^2",
		"solarGHI":                            "W/m^2",
		"snowAccumulation":                    "mm",
		"temperature":                         "c",
		"temperatureApparent":                 "c",
		"tertiarySwellWaveFromDirection":      "º",
		"tertiarySwellWaveSMeanPeriod":        "s",
		"tertiarySwellWaveSignificantHeight":  "m",
		"treeAcacia":                          "PI",
		"treeAsh":                             "PI",
		"treeBeech":                           "PI",
		"treeBirch":                           "PI",
		"treeCedar":                           "PI",
		"treeCottonwood":                      "PI",
		"treeCypress":                         "PI",
		"treeElder":                           "PI",
		"treeElm":                             "PI",
		"treeHemlock":                         "PI",
		"treeHickory":                         "PI",
		"treeIndex":                           "PI",
		"treeJuniper":                         "PI",
		"treeMahagony":                        "PI",
		"treeMaple":                           "PI",
		"treeMulberry":                        "PI",
		"treeOak":                             "PI",
		"treePine":                            "PI",
		"treeSpruce":                          "PI",
		"treeSycamore":                        "PI",
		"treeWalnut":                          "PI",
		"treeWillow":                          "PI",
		"visibility":                          "km",
		"weatherCode":                         {
				0:    "Unknown",
				1000: "Clear",
				1001: "Cloudy",
				1100: "Mostly Clear",
				1101: "Partly Cloudy",
				1102: "Mostly Cloudy",
				2000: "Fog",
				2100: "Light Fog",
				3000: "Light Wind",
				3001: "Wind",
				3002: "Strong Wind",
				4000: "Drizzle",
				4001: "Rain",
				4200: "Light Rain",
				4201: "Heavy Rain",
				5000: "Snow",
				5001: "Flurries",
				5100: "Light Snow",
				5101: "Heavy Snow",
				6000: "Freezing Drizzle",
				6001: "Freezing Rain",
				6200: "Light Freezing Rain",
				6201: "Heavy Freezing Rain",
				7000: "Ice Pellets",
				7101: "Heavy Ice Pellets",
				7102: "Light Ice Pellets",
				8000: "Thunderstorm"
		},
		"weedGrassweedIndex":                  "PI",
		"weedIndex":                           "PI",
		"waveSignificantHeight":               "m",
		"waveFromDirection":                   "º",
		"waveMeanPeriod":                      "s",
		"windDirection":                       "º",
		"windGust":                            "m/s",
		"windSpeed":                           "m/s",
		"windWaveSignificantHeight":           "m",
		"windWaveFromDirection":               "º",
		"WindWaveMeanPeriod":                  "s",
}


class TomorrowIOURLs(URLs):
	base = 'https://api.tomorrow.io/v4/'
	endpoint = 'timelines'


parameters = {'location': config.locStr,
              'fields':   ['temperature',
                           'temperatureApparent',
                           'dewPoint',
                           'humidity',
                           'windSpeed',
                           'windDirection',
                           'windGust',
                           'pressureSurfaceLevel',
                           'pressureSeaLevel',
                           'precipitationIntensity',
                           'precipitationProbability',
                           'precipitationType',
                           'solarGHI',
                           'cloudCover',
                           'weatherCode']
              }


class TomorrowIO(API):
	_urls: TomorrowIOURLs
	currently: TomorrowIOObservationRealtime
	hourly: TomorrowIOForecastHourly
	daily: TomorrowIOForecastDaily
	_baseParams: dict[str, str] = {'apikey': config.tmrrow['apiKey']}
	_params = {}

	def __init__(self):
		self.fields = Fields()
		# self.fields.save()
		self._params['fields'] = self.fields['core']
		super(TomorrowIO, self).__init__()

	def getCurrent(self):
		# params = {'location': config.locStr, 'timesteps': 'current,1h', 'endTime': timedelta(days=3)}
		params = {'location': config.locStr, 'timesteps': 'current,1h', 'timezone': config.tz}
		params = self._API__combineParameters(params)
		params = self.__filterParameters(params)
		if isinstance(params['fields'], list):
			data = self.multiRequest(params)
		else:
			data = self.getData(params=params).json()
		data = self.dataParser(data)
		# import pickle as p
		# import os, sys
		# fp = f"{os.path.dirname(os.path.abspath(__file__))}/test.pickle"
		# with open(fp, 'rb') as f:
		# 	data = p.load(f)
		self.realtime.update(data['current'])
		self.hourly.update(data['1h'])

	def getData(self, params=None):
		data = requests.get(self._urls, params=params)
		if data.status_code == 400:
			self.fields.fixError(data.json()['message'])
		return data

	def multiRequest(self, params):
		params = self.__filterParameters(params)
		f = params['fields']
		if isinstance(f, list):
			dataList = []
			for i in f:
				p = params
				p['fields'] = i
				dataList.append(self.getData(params=p))
		if len(dataList) == 1:
			return dataList[0]

	def __filterParameters(self, params):
		f = list(self.fields.get(params=params, layers=['core', 'air']))
		n = 50
		f = [f[i * n:(i + 1) * n] for i in range((len(f) + n - 1) // n)]
		f = [','.join(i) for i in f]
		params['fields'] = f if len(f) > 1 else f[0]
		if 'endTime' in params:
			params['endTime']: timedelta = (datetime.now() + params['endTime']).strftime("%Y-%m-%dT%H:%M:%SZ")
		if 'startTime' in params:
			params['startTime']: timedelta = (datetime.now() + params['startTime']).strftime("%Y-%m-%dT%H:%M:%SZ")
		return params

	def dataParser(self, rawData):
		def parseTimestep(value):
			def addTime(item):
				item['values']['time'] = item['startTime']
				return item['values']

			return [addTime(i) for i in value]

		timelines = {i['timestep']: parseTimestep(i['intervals']) for i in rawData['data']['timelines']}

		if (current := timelines.get('current', None)) is not None:
			timelines['current'] = current[0]

		return timelines

	def removeFieldTimeStep(self, a):
		field = a[(start := a.find('The field') + 10):a.find(' ', start)]
		timeframe = a.split(' ')[-1]
		self.fields[field].timeframe.allowed.discard(timeframe)

	@property
	def url(self):
		return f'{self._baseURL}{self._endpoint}'


class TomorrowIOForecast(TomorrowIO):
	_hourly: ObservationForecast
	_daily: ObservationForecast

	def __init__(self, **kwargs):
		## TODO: Add support for using units in config.ini
		super().__init__()

	def getData(self, *args):
		translator = ConfigParser()
		translator.read('weatherFlow.ini')
		data: dict = super(TomorrowIOForecast, self).getData()

	def translateData(self, section, data: Union[dict, list], translator, atlas) -> Union[dict, list]:
		if isinstance(data, list):
			newList = []
			for i in range(len(data)):
				newList.append(self.translateData(section, data[i], translator, atlas))
			return newList
		for key in section:
			newKey = section[key]
			if newKey[0] == '[':
				data[newKey[1:-1]] = self.translateData(translator[newKey[1:-1]], data.pop(key), translator, atlas)
			else:
				if key != newKey:
					value = data.pop(key)
					data[newKey] = data.pop(key)
				else:
					pass
		return data

	def buildClassAtlas(self, translator) -> dict[str, str]:
		atlas = {}
		for item in translator['unitGroups']:
			type = item
			group = [value.strip(' ') for value in translator['unitGroups'][type].split(',')]
			for value in group:
				atlas[value] = type
		return atlas


class ErrorNoConnection(Exception):

	def __init__(self, data, *args, **kwargs):
		log.error(data)
		super(ErrorNoConnection, self).__init__(*args, **kwargs)


if __name__ == '__main__':
	logging.getLogger().setLevel(logging.DEBUG)
	wf = TomorrowIO()
	wf.getCurrent()
	print(wf)
