from typing import List, Literal

from src.utils import Period
from src.observations import Observation, ObservationRealtime, ObservationForecast

unitDefinitions = {'irradiance':                  {'type': 'irradiance', 'unit': 'W/m^2', 'title': 'Irradiance', 'sourceKey': 'ghi'},
                   'irradianceHigh':              {'type': 'irradiance', 'unit': 'W/m^2', 'title': 'Irradiance High', 'sourceKey': 'ghi90'},
                   'irradianceLow':               {'type': 'irradiance', 'unit': 'W/m^2', 'title': 'Irradiance Low', 'sourceKey': 'ghi10'},
                   'irradianceDirectHorizontal':  {'type': 'irradiance', 'unit': 'W/m^2', 'title': 'Irradiance Direct Horizontal', 'sourceKey': 'ebh'},
                   'irradianceDirect':            {'type': 'irradiance', 'unit': 'W/m^2', 'title': 'Irradiance Direct', 'sourceKey': 'dni'},
                   'irradianceDirectLow':         {'type': 'irradiance', 'unit': 'W/m^2', 'title': 'Irradiance Direct Low', 'sourceKey': 'dni10'},
                   'irradianceDirectHigh':        {'type': 'irradiance', 'unit': 'W/m^2', 'title': 'Irradiance Direct High', 'sourceKey': 'dni90'},
                   'irradianceDiffuseHorizontal': {'type': 'irradiance', 'unit': 'W/m^2', 'title': 'Irradiance Diffuse Horizontal', 'sourceKey': 'dhi'},
                   'temperature':                 {'type': 'temperature', 'unit': 'c', 'title': 'Temperature', 'sourceKey': 'air_temp'},
                   'solarZenith':                 {'type': 'angle', 'unit': 'ºa', 'title': 'Sun Zenith', 'sourceKey': 'zenith'},
                   'solarAzimuth':                {'type': 'angle', 'unit': 'ºa', 'title': 'Sun Azimuth', 'sourceKey': 'azimuth'},
                   'cloudCover':                  {'type': 'percentage', 'unit': '%c', 'title': 'Cloud Cover', 'sourceKey': 'cloud_opacity'},
                   'time':                        {'type': 'datetime', 'unit': 'ISO8601', 'format': '%Y-%m-%dT%H:%M:%S.%f0Z', 'title': 'Time', 'sourceKey': 'period_end'},
                   'period':                      {'type': 'timedelta', 'unit': 'ISO8601', 'title': 'Period', 'sourceKey': 'period'}
                   }


class SolcastObservation(Observation):
	subscriptionChannel = 'Solcast'
	_translator = unitDefinitions


class SolcastForecast(ObservationForecast):
	_translator = unitDefinitions
	_observationClass = SolcastObservation
	_period = Period.HalfHour
