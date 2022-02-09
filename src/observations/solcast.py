from src.observations import ObservationForecast, ObservationForecastItem
from src.utils import Period

unitDefinitions = {'irradiance':                  {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Irradiance', 'sourceKey': 'ghi'},
                   'irradianceHigh':              {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Irradiance High', 'sourceKey': 'ghi90'},
                   'irradianceLow':               {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Irradiance Low', 'sourceKey': 'ghi10'},
                   'irradianceDirectHorizontal':  {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Irradiance Direct Horizontal', 'sourceKey': 'ebh'},
                   'irradianceDirect':            {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Irradiance Direct', 'sourceKey': 'dni'},
                   'irradianceDirectLow':         {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Irradiance Direct Low', 'sourceKey': 'dni10'},
                   'irradianceDirectHigh':        {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Irradiance Direct High', 'sourceKey': 'dni90'},
                   'irradianceDiffuseHorizontal': {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Irradiance Diffuse Horizontal', 'sourceKey': 'dhi'},
                   'temperature':                 {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Temperature', 'sourceKey': 'air_temp'},
                   'solarZenith':                 {'type': 'angle', 'sourceUnit': 'ºa', 'title': 'Sun Zenith', 'sourceKey': 'zenith'},
                   'solarAzimuth':                {'type': 'angle', 'sourceUnit': 'ºa', 'title': 'Sun Azimuth', 'sourceKey': 'azimuth'},
                   'cloudCover':                  {'type': 'percentage', 'sourceUnit': '%c', 'title': 'Cloud Cover', 'sourceKey': 'cloud_opacity'},
                   'time':                        {'type': 'datetime', 'sourceUnit': 'ISO8601', 'format': '%Y-%m-%dT%H:%M:%S.%f0Z', 'title': 'Time', 'sourceKey': 'period_end'},
                   'period':                      {'type': 'timedelta', 'sourceUnit': 'ISO8601', 'title': 'Period', 'sourceKey': 'period'}
                   }


class SolcastObservation(ObservationForecastItem):
	subscriptionChannel = 'Solcast'
	_translator = unitDefinitions


class SolcastForecast(ObservationForecast):
	_translator = unitDefinitions
	_observationClass = SolcastObservation
	_period = Period.HalfHour
