from enum import Enum

from src.observations import ObservationRealtime, ObservationForecast, Observation
from src.utils import Period, SignalDispatcher

unitDefinitions = {
		'time':                                {'type': 'datetime', 'unit': 'ISO8601', 'format': '%Y-%m-%dT%H:%M:%SZ', 'title': 'Time', 'sourceKey': 'time'},
		'temperature':                         {'type': 'temperature', 'unit': 'c', 'title': 'Temperature', 'sourceKey': 'temperature'},
		'dewpoint':                            {'type': 'temperature', 'unit': 'c', 'title': 'Dewpoint', 'sourceKey': 'dewPoint'},
		'feelsLike':                           {'type': 'temperature', 'unit': 'c', 'title': 'Feels Like', 'sourceKey': 'temperatureApparent'},
		'humidity':                            {'type': 'humidity', 'unit': '%', 'title': 'Humidity', 'sourceKey': 'humidity'},
		'uvi':                                 {'type': 'index', 'unit': 'uvi', 'title': 'UVI', 'sourceKey': 'uv'},
		'irradiance':                          {'type': 'irradiance', 'unit': 'W/m^2', 'title': 'Irradiance', 'sourceKey': 'solarGHI'},
		'pressure':                            {'type': 'pressure', 'unit': 'hPa', 'title': 'Pressure', 'sourceKey': 'pressureSurfaceLevel'},
		'pressureSeaLevel':                    {'type': 'pressure', 'unit': 'hPa', 'title': 'Sea Level Pressure', 'sourceKey': 'pressureSeaLevel'},
		'windDirection':                       {'type': 'direction', 'unit': 'º', 'title': 'Wind Direction', 'sourceKey': 'windDirection'},
		'windSpeed':                           {'type': 'wind', 'unit': ['m', 's'], 'title': 'Wind Speed', 'sourceKey': 'windSpeed'},
		'gustSpeed':                           {'type': 'wind', 'unit': ['m', 's'], 'title': 'Gust Speed', 'sourceKey': 'windGust'},
		'precipitationRate':                   {'type': 'precipitationRate', 'unit': ['mm', 'min'], 'title': 'Precipitation Rate', 'sourceKey': 'precipitationIntensity'},
		'precipitationType':                   {'type': 'precipitationType', 'unit': '*', 'title': 'Precipitation Type', 'sourceKey': 'precipitationType'},
		'precipitationProbability':            {'type': 'probability', 'unit': '%p', 'title': 'Precipitation Probability', 'sourceKey': 'precipitationProbability'},
		'cloudCover':                          {'type': 'percentage', 'unit': '%c', 'title': 'Cloud Cover', 'sourceKey': 'cloudCover'},
		'cloudBase':                           {'type': 'length', 'unit': 'km', 'title': 'cloudBase', 'sourceKey': 'cloudBase'},
		'cloudCeiling':                        {'type': 'length', 'unit': 'km', 'title': 'cloudCeiling', 'sourceKey': 'cloudCeiling'},
		'epaHealthConcern':                    {'type': 'AQIHC', 'unit': 'AQIHC', 'title': 'epaHealthConcern', 'sourceKey': 'epaHealthConcern'},
		'epaIndex':                            {'type': 'AQI', 'unit': 'AQI', 'title': 'epaIndex', 'sourceKey': 'epaIndex'},
		'epaPrimaryPollutant':                 {'type': 'pollutant', 'unit': 'PrimaryPollutant', 'title': 'epaPrimaryPollutant', 'sourceKey': 'epaPrimaryPollutant'},
		'fireIndex':                           {'type': 'FWI', 'unit': 'FWI', 'title': 'fireIndex', 'sourceKey': 'fireIndex'},
		'grassGrassIndex':                     {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'grassGrassIndex', 'sourceKey': 'grassGrassIndex'},
		'grassIndex':                          {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'grassIndex', 'sourceKey': 'grassIndex'},
		'hailBinary':                          {'type': 'bool', 'unit': 'bool', 'title': 'hailBinary', 'sourceKey': 'hailBinary'},
		'iceAccumulation':                     {'type': 'length', 'unit': 'mm', 'title': 'iceAccumulation', 'sourceKey': 'iceAccumulation'},
		'mepHealthConcern':                    {'type': 'AQIHC', 'unit': 'AQIHC', 'title': 'mepHealthConcern', 'sourceKey': 'mepHealthConcern'},
		'mepIndex':                            {'type': 'AQI', 'unit': 'AQI', 'title': 'mepIndex', 'sourceKey': 'mepIndex'},
		'mepPrimaryPollutant':                 {'type': 'pollutant', 'unit': 'PrimaryPollutant', 'title': 'mepPrimaryPollutant', 'sourceKey': 'mepPrimaryPollutant'},
		'moonPhase':                           {'type': 'PhaseIndex', 'unit': 'MoonPhase', 'title': 'moonPhase', 'sourceKey': 'moonPhase'},
		'particulateMatter10':                 {'type': 'pollutionDensity', 'unit': ['μg', 'm^3'], 'title': 'particulateMatter10', 'sourceKey': 'particulateMatter10'},
		'particulateMatter25':                 {'type': 'pollutionDensity', 'unit': ['μg', 'm^3'], 'title': 'particulateMatter25', 'sourceKey': 'particulateMatter25'},
		'pollutantCO':                         {'type': 'partsPer', 'unit': 'ppb', 'title': 'pollutantCO', 'sourceKey': 'pollutantCO'},
		'pollutantNO2':                        {'type': 'partsPer', 'unit': 'ppb', 'title': 'pollutantNO2', 'sourceKey': 'pollutantNO2'},
		'pollutantO3':                         {'type': 'partsPer', 'unit': 'ppb', 'title': 'pollutantO3', 'sourceKey': 'pollutantO3'},
		'pollutantSO2':                        {'type': 'partsPer', 'unit': 'ppb', 'title': 'pollutantSO2', 'sourceKey': 'pollutantSO2'},
		'pressureSurfaceLevel':                {'type': 'pressure', 'unit': 'hPa', 'title': 'pressureSurfaceLevel', 'sourceKey': 'pressureSurfaceLevel'},
		'primarySwellWaveFromDirection':       {'type': 'direction', 'unit': 'º', 'title': 'primarySwellWaveFromDirection', 'sourceKey': 'primarySwellWaveFromDirection'},
		'primarySwellWaveSMeanPeriod':         {'type': 'time', 'unit': 's', 'title': 'primarySwellWaveSMeanPeriod', 'sourceKey': 'primarySwellWaveSMeanPeriod'},
		'primarySwellWaveSignificantHeight':   {'type': 'length', 'unit': 'm', 'title': 'primarySwellWaveSignificantHeight', 'sourceKey': 'primarySwellWaveSignificantHeight'},
		'secondarySwellWaveFromDirection':     {'type': 'direction', 'unit': 'º', 'title': 'secondarySwellWaveFromDirection', 'sourceKey': 'secondarySwellWaveFromDirection'},
		'secondarySwellWaveSMeanPeriod':       {'type': 'time', 'unit': 's', 'title': 'secondarySwellWaveSMeanPeriod', 'sourceKey': 'secondarySwellWaveSMeanPeriod'},
		'secondarySwellWaveSignificantHeight': {'type': 'length', 'unit': 'm', 'title': 'secondarySwellWaveSignificantHeight', 'sourceKey': 'secondarySwellWaveSignificantHeight'},
		'soilMoistureVolumetric0To10':         {'type': '%%', 'unit': '%', 'title': 'soilMoistureVolumetric0To10', 'sourceKey': 'soilMoistureVolumetric0To10'},
		'soilMoistureVolumetric10To40':        {'type': '%%', 'unit': '%', 'title': 'soilMoistureVolumetric10To40', 'sourceKey': 'soilMoistureVolumetric10To40'},
		'soilMoistureVolumetric40To100':       {'type': '%%', 'unit': '%', 'title': 'soilMoistureVolumetric40To100', 'sourceKey': 'soilMoistureVolumetric40To100'},
		'soilMoistureVolumetric100To200':      {'type': '%%', 'unit': '%', 'title': 'soilMoistureVolumetric100To200', 'sourceKey': 'soilMoistureVolumetric100To200'},
		'soilMoistureVolumetric0To200':        {'type': '%%', 'unit': '%', 'title': 'soilMoistureVolumetric0To200', 'sourceKey': 'soilMoistureVolumetric0To200'},
		'soilTemperature0To10':                {'type': 'temperature', 'unit': 'c', 'title': 'soilTemperature0To10', 'sourceKey': 'soilTemperature0To10'},
		'soilTemperature10To40':               {'type': 'temperature', 'unit': 'c', 'title': 'soilTemperature10To40', 'sourceKey': 'soilTemperature10To40'},
		'soilTemperature40To100':              {'type': 'temperature', 'unit': 'c', 'title': 'soilTemperature40To100', 'sourceKey': 'soilTemperature40To100'},
		'soilTemperature100To200':             {'type': 'temperature', 'unit': 'c', 'title': 'soilTemperature100To200', 'sourceKey': 'soilTemperature100To200'},
		'soilTemperature0To200':               {'type': 'temperature', 'unit': 'c', 'title': 'soilTemperature0To200', 'sourceKey': 'soilTemperature0To200'},
		'solarDIF':                            {'type': 'irradiance', 'unit': 'W/m^2', 'title': 'solarDIF', 'sourceKey': 'solarDIF'},
		'solarDIR':                            {'type': 'irradiance', 'unit': 'W/m^2', 'title': 'solarDIR', 'sourceKey': 'solarDIR'},
		'solarGHI':                            {'type': 'irradiance', 'unit': 'W/m^2', 'title': 'solarGHI', 'sourceKey': 'solarGHI'},
		'snowAccumulation':                    {'type': 'length', 'unit': 'mm', 'title': 'snowAccumulation', 'sourceKey': 'snowAccumulation'},
		'tertiarySwellWaveFromDirection':      {'type': 'direction', 'unit': 'º', 'title': 'tertiarySwellWaveFromDirection', 'sourceKey': 'tertiarySwellWaveFromDirection'},
		'tertiarySwellWaveSMeanPeriod':        {'type': 'time', 'unit': 's', 'title': 'tertiarySwellWaveSMeanPeriod', 'sourceKey': 'tertiarySwellWaveSMeanPeriod'},
		'tertiarySwellWaveSignificantHeight':  {'type': 'length', 'unit': 'm', 'title': 'tertiarySwellWaveSignificantHeight', 'sourceKey': 'tertiarySwellWaveSignificantHeight'},
		'treeAcacia':                          {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeAcacia', 'sourceKey': 'treeAcacia'},
		'treeAsh':                             {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeAsh', 'sourceKey': 'treeAsh'},
		'treeBeech':                           {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeBeech', 'sourceKey': 'treeBeech'},
		'treeBirch':                           {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeBirch', 'sourceKey': 'treeBirch'},
		'treeCedar':                           {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeCedar', 'sourceKey': 'treeCedar'},
		'treeCottonwood':                      {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeCottonwood', 'sourceKey': 'treeCottonwood'},
		'treeCypress':                         {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeCypress', 'sourceKey': 'treeCypress'},
		'treeElder':                           {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeElder', 'sourceKey': 'treeElder'},
		'treeElm':                             {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeElm', 'sourceKey': 'treeElm'},
		'treeHemlock':                         {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeHemlock', 'sourceKey': 'treeHemlock'},
		'treeHickory':                         {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeHickory', 'sourceKey': 'treeHickory'},
		'treeIndex':                           {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeIndex', 'sourceKey': 'treeIndex'},
		'treeJuniper':                         {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeJuniper', 'sourceKey': 'treeJuniper'},
		'treeMahagony':                        {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeMahagony', 'sourceKey': 'treeMahagony'},
		'treeMaple':                           {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeMaple', 'sourceKey': 'treeMaple'},
		'treeMulberry':                        {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeMulberry', 'sourceKey': 'treeMulberry'},
		'treeOak':                             {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeOak', 'sourceKey': 'treeOak'},
		'treePine':                            {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treePine', 'sourceKey': 'treePine'},
		'treeSpruce':                          {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeSpruce', 'sourceKey': 'treeSpruce'},
		'treeSycamore':                        {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeSycamore', 'sourceKey': 'treeSycamore'},
		'treeWalnut':                          {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeWalnut', 'sourceKey': 'treeWalnut'},
		'treeWillow':                          {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'treeWillow', 'sourceKey': 'treeWillow'},
		'visibility':                          {'type': 'length', 'unit': 'km', 'title': 'visibility', 'sourceKey': 'visibility'},
		'weatherCode':                         {'type': 'WC', 'unit': 'WeatherCode', 'title': 'weatherCode', 'sourceKey': 'weatherCode'},
		'weedGrassweedIndex':                  {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'weedGrassweedIndex', 'sourceKey': 'weedGrassweedIndex'},
		'weedIndex':                           {'type': 'PollutionIndex', 'unit': 'PI', 'title': 'weedIndex', 'sourceKey': 'weedIndex'},
		'waveSignificantHeight':               {'type': 'length', 'unit': 'm', 'title': 'waveSignificantHeight', 'sourceKey': 'waveSignificantHeight'},
		'waveFromDirection':                   {'type': 'direction', 'unit': 'º', 'title': 'waveFromDirection', 'sourceKey': 'waveFromDirection'},
		'waveMeanPeriod':                      {'type': 'time', 'unit': 's', 'title': 'waveMeanPeriod', 'sourceKey': 'waveMeanPeriod'},
		'windDirection':                       {'type': 'direction', 'unit': 'º', 'title': 'windDirection', 'sourceKey': 'windDirection'},
		'windGust':                            {'type': 'wind', 'unit': ['m', 's'], 'title': 'windGust', 'sourceKey': 'windGust'},
		'windSpeed':                           {'type': 'wind', 'unit': ['m', 's'], 'title': 'windSpeed', 'sourceKey': 'windSpeed'},
		'windWaveSignificantHeight':           {'type': 'length', 'unit': 'm', 'title': 'windWaveSignificantHeight', 'sourceKey': 'windWaveSignificantHeight'},
		'windWaveFromDirection':               {'type': 'direction', 'unit': 'º', 'title': 'windWaveFromDirection', 'sourceKey': 'windWaveFromDirection'},
		'WindWaveMeanPeriod':                  {'type': 'time', 'unit': 's', 'title': 'WindWaveMeanPeriod', 'sourceKey': 'WindWaveMeanPeriod'}}


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
	subscriptionChannel = 'TomorrowIO'
	_translator = unitDefinitions
	signalDispatcher = SignalDispatcher()


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
