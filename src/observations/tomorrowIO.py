from enum import Enum

from src.observations import ObservationRealtime, ObservationForecast, Observation
from src.utils import Period

unitDefinitions = {
	'time.time':                                            {'type': 'datetime', 'sourceUnit': 'ISO8601', 'format': '%Y-%m-%dT%H:%M:%S%z', 'title': 'Time', 'sourceKey': 'time'},
	'environment.temperature.temperature':                  {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Temperature', 'sourceKey': 'temperature'},
	'environment.temperature.dewpoint':                     {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Dewpoint', 'sourceKey': 'dewPoint'},
	'environment.temperature.feelsLike':                    {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Feels Like', 'sourceKey': 'temperatureApparent'},
	'environment.humidity.humidity':                        {'type': 'humidity', 'sourceUnit': '%', 'title': 'Humidity', 'sourceKey': 'humidity'},
	'environment.light.uvi':                                {'type': 'index', 'sourceUnit': 'uvi', 'title': 'UVI', 'sourceKey': 'uv'},
	'environment.light.irradiance':                         {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Irradiance', 'sourceKey': 'solarGHI'},
	'environment.pressure.pressure':                        {'type': 'pressure', 'sourceUnit': 'hPa', 'title': 'Pressure', 'sourceKey': 'pressureSurfaceLevel'},
	'environment.pressure.pressureSeaLevel':                {'type': 'pressure', 'sourceUnit': 'hPa', 'title': 'Sea Level Pressure', 'sourceKey': 'pressureSeaLevel'},
	'environment.wind.direction.direction':                 {'type': 'direction', 'sourceUnit': 'º', 'title': 'Wind Direction', 'sourceKey': 'windDirection'},
	'environment.wind.speed.speed':                         {'type': 'wind', 'sourceUnit': ['m', 's'], 'title': 'Wind Speed', 'sourceKey': 'windSpeed'},
	'environment.wind.speed.gust':                          {'type': 'wind', 'sourceUnit': ['m', 's'], 'title': 'Gust Speed', 'sourceKey': 'windGust'},
	'environment.precipitation.precipitation':              {'type': 'precipitationRate', 'sourceUnit': ['mm', 'min'], 'title': 'Precipitation Rate', 'sourceKey': 'precipitationIntensity'},
	'environment.precipitation.type':                       {'type': 'precipitationType', 'sourceUnit': '*', 'title': 'Precipitation Type', 'sourceKey': 'precipitationType'},
	'environment.precipitation.probability':                {'type': 'probability', 'sourceUnit': '%p', 'title': 'Precipitation Probability', 'sourceKey': 'precipitationProbability'},
	'environment.cloud.cover':                              {'type': 'percentage', 'sourceUnit': '%c', 'title': 'Cloud Cover', 'sourceKey': 'cloudCover'},
	'environment.cloud.base':                               {'type': 'length', 'sourceUnit': 'km', 'title': 'cloudBase', 'sourceKey': 'cloudBase'},
	'environment.cloud.ceiling':                            {'type': 'length', 'sourceUnit': 'km', 'title': 'cloudCeiling', 'sourceKey': 'cloudCeiling'},
	'environment.airQuality.epaHealthConcern':              {'type': 'AQIHC', 'sourceUnit': 'AQIHC', 'title': 'epaHealthConcern', 'sourceKey': 'epaHealthConcern'},
	'environment.airQuality.epaIndex':                      {'type': 'AQI', 'sourceUnit': 'AQI', 'title': 'epaIndex', 'sourceKey': 'epaIndex'},
	'environment.airQuality.epaPrimaryPollutant':           {'type': 'pollutant', 'sourceUnit': 'PrimaryPollutant', 'title': 'epaPrimaryPollutant', 'sourceKey': 'epaPrimaryPollutant'},
	'environment.fire.fireIndex':                           {'type': 'FWI', 'sourceUnit': 'FWI', 'title': 'fireIndex', 'sourceKey': 'fireIndex'},
	'environment.pollution.grassGrassIndex':                {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'grassGrassIndex', 'sourceKey': 'grassGrassIndex'},
	'environment.pollution.grassIndex':                     {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'grassIndex', 'sourceKey': 'grassIndex'},
	'environment.precipitation.hail':                       {'type': 'bool', 'sourceUnit': 'bool', 'title': 'hailBinary', 'sourceKey': 'hailBinary'},
	'environment.precipitation.iceAccumulation':            {'type': 'length', 'sourceUnit': 'mm', 'title': 'iceAccumulation', 'sourceKey': 'iceAccumulation'},
	'environment.airQuality.mepHealthConcern':              {'type': 'AQIHC', 'sourceUnit': 'AQIHC', 'title': 'mepHealthConcern', 'sourceKey': 'mepHealthConcern'},
	'environment.airQuality.mepIndex':                      {'type': 'AQI', 'sourceUnit': 'AQI', 'title': 'mepIndex', 'sourceKey': 'mepIndex'},
	'environment.airQuality.mepPrimaryPollutant':           {'type': 'pollutant', 'sourceUnit': 'PrimaryPollutant', 'title': 'mepPrimaryPollutant', 'sourceKey': 'mepPrimaryPollutant'},
	'environment.sky.moonPhase':                            {'type': 'PhaseIndex', 'sourceUnit': 'MoonPhase', 'title': 'moonPhase', 'sourceKey': 'moonPhase'},
	'environment.pollution.particulateMatter10':            {'type': 'pollutionDensity', 'sourceUnit': ['μg', 'm^3'], 'title': 'particulateMatter10', 'sourceKey': 'particulateMatter10'},
	'environment.pollution.particulateMatter25':            {'type': 'pollutionDensity', 'sourceUnit': ['μg', 'm^3'], 'title': 'particulateMatter25', 'sourceKey': 'particulateMatter25'},
	'environment.pollution.pollutantCO':                    {'type': 'partsPer', 'sourceUnit': 'ppb', 'title': 'pollutantCO', 'sourceKey': 'pollutantCO'},
	'environment.pollution.pollutantNO2':                   {'type': 'partsPer', 'sourceUnit': 'ppb', 'title': 'pollutantNO2', 'sourceKey': 'pollutantNO2'},
	'environment.pollution.pollutantO3':                    {'type': 'partsPer', 'sourceUnit': 'ppb', 'title': 'pollutantO3', 'sourceKey': 'pollutantO3'},
	'environment.pollution.pollutantSO2':                   {'type': 'partsPer', 'sourceUnit': 'ppb', 'title': 'pollutantSO2', 'sourceKey': 'pollutantSO2'},
	'environment.pressure.surfaceLevel':                    {'type': 'pressure', 'sourceUnit': 'hPa', 'title': 'pressureSurfaceLevel', 'sourceKey': 'pressureSurfaceLevel'},
	'environment.wave.primarySwellWaveFromDirection':       {'type': 'direction', 'sourceUnit': 'º', 'title': 'primarySwellWaveFromDirection', 'sourceKey': 'primarySwellWaveFromDirection'},
	'environment.wave.primarySwellWaveSMeanPeriod':         {'type': 'time', 'sourceUnit': 's', 'title': 'primarySwellWaveSMeanPeriod', 'sourceKey': 'primarySwellWaveSMeanPeriod'},
	'environment.wave.primarySwellWaveSignificantHeight':   {'type': 'length', 'sourceUnit': 'm', 'title': 'primarySwellWaveSignificantHeight', 'sourceKey': 'primarySwellWaveSignificantHeight'},
	'environment.wave.secondarySwellWaveFromDirection':     {'type': 'direction', 'sourceUnit': 'º', 'title': 'secondarySwellWaveFromDirection', 'sourceKey': 'secondarySwellWaveFromDirection'},
	'environment.wave.secondarySwellWaveSMeanPeriod':       {'type': 'time', 'sourceUnit': 's', 'title': 'secondarySwellWaveSMeanPeriod', 'sourceKey': 'secondarySwellWaveSMeanPeriod'},
	'environment.wave.secondarySwellWaveSignificantHeight': {'type': 'length', 'sourceUnit': 'm', 'title': 'secondarySwellWaveSignificantHeight', 'sourceKey': 'secondarySwellWaveSignificantHeight'},
	'environment.soil.moisture.volumetric0To10':            {'type': '%%', 'sourceUnit': '%', 'title': 'soilMoistureVolumetric0To10', 'sourceKey': 'soilMoistureVolumetric0To10'},
	'environment.soil.moisture.volumetric10To40':           {'type': '%%', 'sourceUnit': '%', 'title': 'soilMoistureVolumetric10To40', 'sourceKey': 'soilMoistureVolumetric10To40'},
	'environment.soil.moisture.volumetric40To100':          {'type': '%%', 'sourceUnit': '%', 'title': 'soilMoistureVolumetric40To100', 'sourceKey': 'soilMoistureVolumetric40To100'},
	'environment.soil.moisture.volumetric100To200':         {'type': '%%', 'sourceUnit': '%', 'title': 'soilMoistureVolumetric100To200', 'sourceKey': 'soilMoistureVolumetric100To200'},
	'environment.soil.moisture.volumetric0To200':           {'type': '%%', 'sourceUnit': '%', 'title': 'soilMoistureVolumetric0To200', 'sourceKey': 'soilMoistureVolumetric0To200'},
	'environment.soil.temperature.0To10':                   {'type': 'temperature', 'sourceUnit': 'c', 'title': 'soilTemperature0To10', 'sourceKey': 'soilTemperature0To10'},
	'environment.soil.temperature.10To40':                  {'type': 'temperature', 'sourceUnit': 'c', 'title': 'soilTemperature10To40', 'sourceKey': 'soilTemperature10To40'},
	'environment.soil.temperature.40To100':                 {'type': 'temperature', 'sourceUnit': 'c', 'title': 'soilTemperature40To100', 'sourceKey': 'soilTemperature40To100'},
	'environment.soil.temperature.100To200':                {'type': 'temperature', 'sourceUnit': 'c', 'title': 'soilTemperature100To200', 'sourceKey': 'soilTemperature100To200'},
	'environment.soil.temperature.0To200':                  {'type': 'temperature', 'sourceUnit': 'c', 'title': 'soilTemperature0To200', 'sourceKey': 'soilTemperature0To200'},
	'environment.solar.dif':                                {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'solarDIF', 'sourceKey': 'solarDIF'},
	'environment.solar.dir':                                {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'solarDIR', 'sourceKey': 'solarDIR'},
	'environment.solar.ghi':                                {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'solarGHI', 'sourceKey': 'solarGHI'},
	'environment.precipitation.snowAccumulation':           {'type': 'length', 'sourceUnit': 'mm', 'title': 'snowAccumulation', 'sourceKey': 'snowAccumulation'},
	'environment.water.wave.tertiary.fromDirection':        {'type': 'direction', 'sourceUnit': 'º', 'title': 'tertiarySwellWaveFromDirection', 'sourceKey': 'tertiarySwellWaveFromDirection'},
	'environment.water.wave.tertiary.sMeanPeriod':          {'type': 'time', 'sourceUnit': 's', 'title': 'tertiarySwellWaveSMeanPeriod', 'sourceKey': 'tertiarySwellWaveSMeanPeriod'},
	'environment.water.wave.tertiary.significantHeight':    {'type': 'length', 'sourceUnit': 'm', 'title': 'tertiarySwellWaveSignificantHeight', 'sourceKey': 'tertiarySwellWaveSignificantHeight'},
	'environment.pollution.treeAcacia':                     {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeAcacia', 'sourceKey': 'treeAcacia'},
	'environment.pollution.treeAsh':                        {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeAsh', 'sourceKey': 'treeAsh'},
	'environment.pollution.treeBeech':                      {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeBeech', 'sourceKey': 'treeBeech'},
	'environment.pollution.treeBirch':                      {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeBirch', 'sourceKey': 'treeBirch'},
	'environment.pollution.treeCedar':                      {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeCedar', 'sourceKey': 'treeCedar'},
	'environment.pollution.treeCottonwood':                 {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeCottonwood', 'sourceKey': 'treeCottonwood'},
	'environment.pollution.treeCypress':                    {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeCypress', 'sourceKey': 'treeCypress'},
	'environment.pollution.treeElder':                      {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeElder', 'sourceKey': 'treeElder'},
	'environment.pollution.treeElm':                        {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeElm', 'sourceKey': 'treeElm'},
	'environment.pollution.treeHemlock':                    {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeHemlock', 'sourceKey': 'treeHemlock'},
	'environment.pollution.treeHickory':                    {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeHickory', 'sourceKey': 'treeHickory'},
	'environment.pollution.treeIndex':                      {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeIndex', 'sourceKey': 'treeIndex'},
	'environment.pollution.treeJuniper':                    {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeJuniper', 'sourceKey': 'treeJuniper'},
	'environment.pollution.treeMahagony':                   {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeMahagony', 'sourceKey': 'treeMahagony'},
	'environment.pollution.treeMaple':                      {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeMaple', 'sourceKey': 'treeMaple'},
	'environment.pollution.treeMulberry':                   {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeMulberry', 'sourceKey': 'treeMulberry'},
	'environment.pollution.treeOak':                        {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeOak', 'sourceKey': 'treeOak'},
	'environment.pollution.treePine':                       {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treePine', 'sourceKey': 'treePine'},
	'environment.pollution.treeSpruce':                     {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeSpruce', 'sourceKey': 'treeSpruce'},
	'environment.pollution.treeSycamore':                   {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeSycamore', 'sourceKey': 'treeSycamore'},
	'environment.pollution.treeWalnut':                     {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeWalnut', 'sourceKey': 'treeWalnut'},
	'environment.pollution.treeWillow':                     {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'treeWillow', 'sourceKey': 'treeWillow'},
	'environment.visibility':                               {'type': 'length', 'sourceUnit': 'km', 'title': 'visibility', 'sourceKey': 'visibility'},
	'environment.conditions.weatherCode':                   {'type': 'WC', 'sourceUnit': 'WeatherCode', 'title': 'weatherCode', 'sourceKey': 'weatherCode'},
	'environment.pollution.weedGrassweedIndex':             {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'weedGrassweedIndex', 'sourceKey': 'weedGrassweedIndex'},
	'environment.pollution.weedIndex':                      {'type': 'PollutionIndex', 'sourceUnit': 'PI', 'title': 'weedIndex', 'sourceKey': 'weedIndex'},
	'environment.wave.significantHeight':                   {'type': 'length', 'sourceUnit': 'm', 'title': 'waveSignificantHeight', 'sourceKey': 'waveSignificantHeight'},
	'environment.wave.fromDirection':                       {'type': 'direction', 'sourceUnit': 'º', 'title': 'waveFromDirection', 'sourceKey': 'waveFromDirection'},
	'environment.wave.meanPeriod':                          {'type': 'time', 'sourceUnit': 's', 'title': 'waveMeanPeriod', 'sourceKey': 'waveMeanPeriod'},
	'environment.wind.speed.gust':                          {'type': 'wind', 'sourceUnit': ['m', 's'], 'title': 'windGust', 'sourceKey': 'windGust'},
	'environment.wind.wave.significantHeight':              {'type': 'length', 'sourceUnit': 'm', 'title': 'windWaveSignificantHeight', 'sourceKey': 'windWaveSignificantHeight'},
	'environment.wind.wave.fromDirection':                  {'type': 'direction', 'sourceUnit': 'º', 'title': 'windWaveFromDirection', 'sourceKey': 'windWaveFromDirection'},
	'environment.wind.wave.meanPeriod':                     {'type': 'time', 'sourceUnit': 's', 'title': 'WindWaveMeanPeriod', 'sourceKey': 'WindWaveMeanPeriod'},
}


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
