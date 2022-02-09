from enum import Enum

from src.observations import ObservationRealtime, ObservationForecast, Observation
from src.utils import Period

unitDefinitions = {
	'time':                                {'type': 'datetime', 'sourceUnit': 'ISO8601', 'format': '%Y-%m-%dT%H:%M:%SZ', 'title': 'Time', 'sourceKey': 'time'},
	'temperature':                         {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Temperature', 'sourceKey': 'temperature'},
	'dewpoint':                            {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Dewpoint', 'sourceKey': 'dewPoint'},
	'feelsLike':                           {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Feels Like', 'sourceKey': 'temperatureApparent'},
	'humidity':                            {'type': 'humidity', 'sourceUnit': '%', 'title': 'Humidity', 'sourceKey': 'humidity'},
	'uvi':                                 {'type': 'index', 'sourceUnit': 'uvi', 'title': 'UVI', 'sourceKey': 'uv'},
	'irradiance':                          {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Irradiance', 'sourceKey': 'solarGHI'},
	'pressure':                            {'type': 'pressure', 'sourceUnit': 'hPa', 'title': 'Pressure', 'sourceKey': 'pressureSurfaceLevel'},
	'pressureSeaLevel':                    {'type': 'pressure', 'sourceUnit': 'hPa', 'title': 'Sea Level Pressure', 'sourceKey': 'pressureSeaLevel'},
	'windDirection':                       {'type': 'direction', 'sourceUnit': 'º', 'title': 'Wind Direction', 'sourceKey': 'windDirection'},
	'windSpeed':                           {'type': 'wind', 'sourceUnit': ['m', 's'], 'title': 'Wind Speed', 'sourceKey': 'windSpeed'},
	'gustSpeed':                           {'type': 'wind', 'sourceUnit': ['m', 's'], 'title': 'Gust Speed', 'sourceKey': 'windGust'},
	'precipitationRate':                   {'type': 'precipitationRate', 'sourceUnit': ['mm', 'min'], 'title': 'Precipitation Rate', 'sourceKey': 'precipitationIntensity'},
	'precipitationType':                   {'type': 'precipitationType', 'sourceUnit': '*', 'title': 'Precipitation Type', 'sourceKey': 'precipitationType'},
	'precipitationProbability':            {'type': 'probability', 'sourceUnit': '%p', 'title': 'Precipitation Probability', 'sourceKey': 'precipitationProbability'},
	'cloudCover':                          {'type': 'percentage', 'sourceUnit': '%c', 'title': 'Cloud Cover', 'sourceKey': 'cloudCover'},
	'cloudBase':                           {'type': 'length', 'sourceUnit': 'km', 'title': 'cloudBase', 'sourceKey': 'cloudBase'},
	'cloudCeiling':                        {'type': 'length', 'sourceUnit': 'km', 'title': 'cloudCeiling', 'sourceKey': 'cloudCeiling'},
	'epaHealthConcern':                    {'type': 'AQIHC', 'sourceUnit': 'AQIHC', 'title': 'epaHealthConcern', 'sourceKey': 'epaHealthConcern'},
	'epaIndex':                            {'type': 'AQI', 'sourceUnit': 'AQI', 'title': 'epaIndex', 'sourceKey': 'epaIndex'},
	'epaPrimaryPollutant':                 {'type': 'pollutant', 'sourceUnit': 'PrimaryPollutant', 'title': 'epaPrimaryPollutant', 'sourceKey': 'epaPrimaryPollutant'},
	'fireIndex':                           {'type': 'FWI', 'sourceUnit': 'FWI', 'title': 'fireIndex', 'sourceKey': 'fireIndex'},
	'grassGrassIndex':                     {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'grassGrassIndex', 'sourceKey': 'grassGrassIndex'},
	'grassIndex':                          {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'grassIndex', 'sourceKey': 'grassIndex'},
	'hailBinary':                          {'type': 'bool', 'sourceUnit': 'bool', 'title': 'hailBinary', 'sourceKey': 'hailBinary'},
	'iceAccumulation':                     {'type': 'length', 'sourceUnit': 'mm', 'title': 'iceAccumulation', 'sourceKey': 'iceAccumulation'},
	'mepHealthConcern':                    {'type': 'AQIHC', 'sourceUnit': 'AQIHC', 'title': 'mepHealthConcern', 'sourceKey': 'mepHealthConcern'},
	'mepIndex':                            {'type': 'AQI', 'sourceUnit': 'AQI', 'title': 'mepIndex', 'sourceKey': 'mepIndex'},
	'mepPrimaryPollutant':                 {'type': 'pollutant', 'sourceUnit': 'PrimaryPollutant', 'title': 'mepPrimaryPollutant', 'sourceKey': 'mepPrimaryPollutant'},
	'moonPhase':                           {'type': 'PhaseIndex', 'sourceUnit': 'MoonPhase', 'title': 'moonPhase', 'sourceKey': 'moonPhase'},
	'particulateMatter10':                 {'type': 'pollutionDensity', 'sourceUnit': ['μg', 'm^3'], 'title': 'particulateMatter10', 'sourceKey': 'particulateMatter10'},
	'particulateMatter25':                 {'type': 'pollutionDensity', 'sourceUnit': ['μg', 'm^3'], 'title': 'particulateMatter25', 'sourceKey': 'particulateMatter25'},
	'pollutantCO':                         {'type': 'partsPer', 'sourceUnit': 'ppb', 'title': 'pollutantCO', 'sourceKey': 'pollutantCO'},
	'pollutantNO2':                        {'type': 'partsPer', 'sourceUnit': 'ppb', 'title': 'pollutantNO2', 'sourceKey': 'pollutantNO2'},
	'pollutantO3':                         {'type': 'partsPer', 'sourceUnit': 'ppb', 'title': 'pollutantO3', 'sourceKey': 'pollutantO3'},
	'pollutantSO2':                        {'type': 'partsPer', 'sourceUnit': 'ppb', 'title': 'pollutantSO2', 'sourceKey': 'pollutantSO2'},
	'pressureSurfaceLevel':                {'type': 'pressure', 'sourceUnit': 'hPa', 'title': 'pressureSurfaceLevel', 'sourceKey': 'pressureSurfaceLevel'},
	'primarySwellWaveFromDirection':       {'type': 'direction', 'sourceUnit': 'º', 'title': 'primarySwellWaveFromDirection', 'sourceKey': 'primarySwellWaveFromDirection'},
	'primarySwellWaveSMeanPeriod':         {'type': 'time', 'sourceUnit': 's', 'title': 'primarySwellWaveSMeanPeriod', 'sourceKey': 'primarySwellWaveSMeanPeriod'},
	'primarySwellWaveSignificantHeight':   {'type': 'length', 'sourceUnit': 'm', 'title': 'primarySwellWaveSignificantHeight', 'sourceKey': 'primarySwellWaveSignificantHeight'},
	'secondarySwellWaveFromDirection':     {'type': 'direction', 'sourceUnit': 'º', 'title': 'secondarySwellWaveFromDirection', 'sourceKey': 'secondarySwellWaveFromDirection'},
	'secondarySwellWaveSMeanPeriod':       {'type': 'time', 'sourceUnit': 's', 'title': 'secondarySwellWaveSMeanPeriod', 'sourceKey': 'secondarySwellWaveSMeanPeriod'},
	'secondarySwellWaveSignificantHeight': {'type': 'length', 'sourceUnit': 'm', 'title': 'secondarySwellWaveSignificantHeight', 'sourceKey': 'secondarySwellWaveSignificantHeight'},
	'soilMoistureVolumetric0To10':         {'type': '%%', 'sourceUnit': '%', 'title': 'soilMoistureVolumetric0To10', 'sourceKey': 'soilMoistureVolumetric0To10'},
	'soilMoistureVolumetric10To40':        {'type': '%%', 'sourceUnit': '%', 'title': 'soilMoistureVolumetric10To40', 'sourceKey': 'soilMoistureVolumetric10To40'},
	'soilMoistureVolumetric40To100':       {'type': '%%', 'sourceUnit': '%', 'title': 'soilMoistureVolumetric40To100', 'sourceKey': 'soilMoistureVolumetric40To100'},
	'soilMoistureVolumetric100To200':      {'type': '%%', 'sourceUnit': '%', 'title': 'soilMoistureVolumetric100To200', 'sourceKey': 'soilMoistureVolumetric100To200'},
	'soilMoistureVolumetric0To200':        {'type': '%%', 'sourceUnit': '%', 'title': 'soilMoistureVolumetric0To200', 'sourceKey': 'soilMoistureVolumetric0To200'},
	'soilTemperature0To10':                {'type': 'temperature', 'sourceUnit': 'c', 'title': 'soilTemperature0To10', 'sourceKey': 'soilTemperature0To10'},
	'soilTemperature10To40':               {'type': 'temperature', 'sourceUnit': 'c', 'title': 'soilTemperature10To40', 'sourceKey': 'soilTemperature10To40'},
	'soilTemperature40To100':              {'type': 'temperature', 'sourceUnit': 'c', 'title': 'soilTemperature40To100', 'sourceKey': 'soilTemperature40To100'},
	'soilTemperature100To200':             {'type': 'temperature', 'sourceUnit': 'c', 'title': 'soilTemperature100To200', 'sourceKey': 'soilTemperature100To200'},
	'soilTemperature0To200':               {'type': 'temperature', 'sourceUnit': 'c', 'title': 'soilTemperature0To200', 'sourceKey': 'soilTemperature0To200'},
	'solarDIF':                            {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'solarDIF', 'sourceKey': 'solarDIF'},
	'solarDIR':                            {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'solarDIR', 'sourceKey': 'solarDIR'},
	'solarGHI':                            {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'solarGHI', 'sourceKey': 'solarGHI'},
	'snowAccumulation':                    {'type': 'length', 'sourceUnit': 'mm', 'title': 'snowAccumulation', 'sourceKey': 'snowAccumulation'},
	'tertiarySwellWaveFromDirection':      {'type': 'direction', 'sourceUnit': 'º', 'title': 'tertiarySwellWaveFromDirection', 'sourceKey': 'tertiarySwellWaveFromDirection'},
	'tertiarySwellWaveSMeanPeriod':        {'type': 'time', 'sourceUnit': 's', 'title': 'tertiarySwellWaveSMeanPeriod', 'sourceKey': 'tertiarySwellWaveSMeanPeriod'},
	'tertiarySwellWaveSignificantHeight':  {'type': 'length', 'sourceUnit': 'm', 'title': 'tertiarySwellWaveSignificantHeight', 'sourceKey': 'tertiarySwellWaveSignificantHeight'},
	'treeAcacia':                          {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeAcacia', 'sourceKey': 'treeAcacia'},
	'treeAsh':                             {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeAsh', 'sourceKey': 'treeAsh'},
	'treeBeech':                           {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeBeech', 'sourceKey': 'treeBeech'},
	'treeBirch':                           {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeBirch', 'sourceKey': 'treeBirch'},
	'treeCedar':                           {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeCedar', 'sourceKey': 'treeCedar'},
	'treeCottonwood':                      {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeCottonwood', 'sourceKey': 'treeCottonwood'},
	'treeCypress':                         {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeCypress', 'sourceKey': 'treeCypress'},
	'treeElder':                           {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeElder', 'sourceKey': 'treeElder'},
	'treeElm':                             {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeElm', 'sourceKey': 'treeElm'},
	'treeHemlock':                         {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeHemlock', 'sourceKey': 'treeHemlock'},
	'treeHickory':                         {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeHickory', 'sourceKey': 'treeHickory'},
	'treeIndex':                           {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeIndex', 'sourceKey': 'treeIndex'},
	'treeJuniper':                         {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeJuniper', 'sourceKey': 'treeJuniper'},
	'treeMahagony':                        {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeMahagony', 'sourceKey': 'treeMahagony'},
	'treeMaple':                           {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeMaple', 'sourceKey': 'treeMaple'},
	'treeMulberry':                        {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeMulberry', 'sourceKey': 'treeMulberry'},
	'treeOak':                             {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeOak', 'sourceKey': 'treeOak'},
	'treePine':                            {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treePine', 'sourceKey': 'treePine'},
	'treeSpruce':                          {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeSpruce', 'sourceKey': 'treeSpruce'},
	'treeSycamore':                        {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeSycamore', 'sourceKey': 'treeSycamore'},
	'treeWalnut':                          {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeWalnut', 'sourceKey': 'treeWalnut'},
	'treeWillow':                          {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeWillow', 'sourceKey': 'treeWillow'},
	'visibility':                          {'type': 'length', 'sourceUnit': 'km', 'title': 'visibility', 'sourceKey': 'visibility'},
	'weatherCode':                         {'type': 'WC', 'sourceUnit': 'WeatherCode', 'title': 'weatherCode', 'sourceKey': 'weatherCode'},
	'weedGrassweedIndex':                  {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'weedGrassweedIndex', 'sourceKey': 'weedGrassweedIndex'},
	'weedIndex':                           {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'weedIndex', 'sourceKey': 'weedIndex'},
	'waveSignificantHeight':               {'type': 'length', 'sourceUnit': 'm', 'title': 'waveSignificantHeight', 'sourceKey': 'waveSignificantHeight'},
	'waveFromDirection':                   {'type': 'direction', 'sourceUnit': 'º', 'title': 'waveFromDirection', 'sourceKey': 'waveFromDirection'},
	'waveMeanPeriod':                      {'type': 'time', 'sourceUnit': 's', 'title': 'waveMeanPeriod', 'sourceKey': 'waveMeanPeriod'},
	'windGust':                            {'type': 'wind', 'sourceUnit': ['m', 's'], 'title': 'windGust', 'sourceKey': 'windGust'},
	'windWaveSignificantHeight':           {'type': 'length', 'sourceUnit': 'm', 'title': 'windWaveSignificantHeight', 'sourceKey': 'windWaveSignificantHeight'},
	'windWaveFromDirection':               {'type': 'direction', 'sourceUnit': 'º', 'title': 'windWaveFromDirection', 'sourceKey': 'windWaveFromDirection'},
	'WindWaveMeanPeriod':                  {'type': 'time', 'sourceUnit': 's', 'title': 'WindWaveMeanPeriod', 'sourceKey': 'WindWaveMeanPeriod'}}


class AirQualityIndex(Enum):
	Good = 0
	Moderate = 1
	UnhealthyForSensitiveGroups = 2
	Unhealthy = 3
	VeryUnhealthy = 4
	Hazardous = 5


class MoonPhase(Enum):
	New = 0
	WaxingCrescent = 1
	FirstQuarter = 2
	WaxingGibbous = 3
	Full = 4
	WaningGibbous = 5
	ThirdQuarter = 6
	WaningCrescent = 7


class PrecipitationType(Enum):
	NA = 0
	Rain = 1
	Snow = 2
	FreezingRain = 3
	IcePellets = 4


unitDict = Observation.unitDict.copy()
unitDict.update({
		# 'ppm':              wu.Measurement,
		# 'ppb':              wu.Measurement,
		# 'μg/m^3':           wu.Measurement,
		# 'bool':             wu.Measurement,
		'MoonPhase': MoonPhase,
		# "WeatherCode":      wu.Measurement,
})
unitDict['special']['precipitationType'] = PrecipitationType


class TomorrowIOObservationRealtime(ObservationRealtime):
	unitDict = unitDict
	_translator = unitDefinitions


class TomorrowIOObservation(Observation):
	unitDict = unitDict
	_translator = unitDefinitions


class TomorrowIOForecast(ObservationForecast):
	_fieldsToPop = [*ObservationForecast._fieldsToPop, 'wind_direction_cardinal']
	unitDict = unitDict
	_translator = unitDefinitions
	_observationClass = TomorrowIOObservation
	_period = None


class TomorrowIOForecastHourly(TomorrowIOForecast):
	_period = Period.Hour


class TomorrowIOForecastDaily(TomorrowIOForecast):
	_period = Period.Day
