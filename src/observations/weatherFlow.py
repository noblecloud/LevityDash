from src.observations.environment import EnvironmentObservationForecast, EnvironmentObservationForecastItem, EnvironmentObservationRealtime
from src.utils import Period

# unitDefinitions = {'temperature':                        {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Temperature', 'sourceKey': 'air_temperature', 'category': 'weather.temperature'},
#                    'dewpoint':                           {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Dewpoint', 'sourceKey': 'dew_point', 'category': 'weather.temperature'},
#                    'wetBulb':                            {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Wet Bulb', 'sourceKey': 'wet_bulb_temperature', 'category': 'weather.temperature'},
#                    'feelsLike':                          {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Feels Like', 'sourceKey': 'feels_like', 'category': 'weather.temperature'},
#                    'heatIndex':                          {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Heat Index', 'sourceKey': 'heat_index', 'category': 'weather.temperature'},
#                    'windChill':                          {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Wind Chill', 'sourceKey': 'wind_chill', 'category': 'weather.temperature'},
#                    'deltaT':                             {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Delta T', 'sourceKey': 'delta_t', 'category': 'weather.temperature'},
#                    'humidity':                           {'type': 'humidity', 'sourceUnit': '%', 'title': 'Humidity', 'sourceKey': 'relative_humidity', 'category': 'weather.humidity'},
#                    'uvi':                                {'type': 'index', 'sourceUnit': 'uvi', 'title': 'UVI', 'sourceKey': 'uv', 'category': 'weather.light.irradiance'},
#                    'irradiance':                         {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Irradiance', 'sourceKey': 'solar_radiation', 'category': 'weather.light.irradiance'},
#                    'illuminance':                        {'type': 'illuminance', 'sourceUnit': 'lux', 'title': 'Illuminance', 'sourceKey': 'brightness', 'category': 'weather.light.brightness'},
#                    'pressure':                           {'type': 'pressure', 'sourceUnit': 'mb', 'title': 'Pressure', 'sourceKey': 'barometric_pressure', 'category': 'weather.atmosphere.pressure'},
#                    'pressureAbsolute':                   {'type': 'pressure', 'sourceUnit': 'mb', 'title': 'Absolute', 'sourceKey': 'station_pressure', 'category': 'weather.atmosphere.pressure'},
#                    'pressureSeaLevel':                   {'type': 'pressure', 'sourceUnit': 'mb', 'title': 'Sea Level', 'sourceKey': 'sea_level_pressure', 'category': 'weather.atmosphere.pressure'},
#                    'airDensity':                         {'type': 'airDensity', 'sourceUnit': ['kg', 'm'], 'title': 'Air Density', 'sourceKey': 'air_density', 'category': 'weather.atmosphere.density'},
#                    'pressureTrend':                      {'type': 'pressureTrend', 'sourceUnit': '*', 'title': 'Trend', 'sourceKey': 'pressure_trend', 'category': 'weather.atmosphere.pressure.trend'},
#                    'windDirection':                      {'type': 'direction', 'sourceUnit': 'º', 'title': 'Direction', 'sourceKey': 'wind_direction', 'category': 'weather.wind.direction'},
#                    'windSpeed':                          {'type': 'wind', 'sourceUnit': ['m', 's'], 'title': 'Speed', 'sourceKey': 'wind_avg', 'category': 'weather.wind.speed'},
#                    'lullSpeed':                          {'type': 'wind', 'sourceUnit': ['m', 's'], 'title': 'Lull', 'sourceKey': 'wind_lull', 'category': 'weather.wind.speed'},
#                    'gustSpeed':                          {'type': 'wind', 'sourceUnit': ['m', 's'], 'title': 'Gust', 'sourceKey': 'wind_gust', 'category': 'weather.wind.speed'},
#                    'windSampleInterval':                 {'type': 'interval', 'sourceUnit': 's', 'title': 'Sample Interval', 'sourceKey': 'windSampleInterval', 'category': 'interval.wind'},
#                    'reportInterval':                     {'type': 'interval', 'sourceUnit': 'min', 'title': 'Report Interval', 'sourceKey': 'reportInterval', 'category': 'interval.weather'},
#                    'precipitationRate':                  {'type': 'precipitationRate', 'sourceUnit': ['mm', 'min'], 'title': 'Rate', 'sourceKey': 'precip', 'category': 'weather.precipitation.rate'},
#                    'precipitationHourly':                {'type': 'precipitationHourly', 'sourceUnit': ['mm', 'hr'], 'title': 'Hourly', 'sourceKey': 'precip_accum_last_1hr', 'category': 'weather.precipitation.rate.hourly'},
#                    'precipitationDaily':                 {'type': 'precipitationDaily', 'sourceUnit': ['mm', 'day'], 'title': 'Daily', 'sourceKey': 'precip_accum_local_day', 'category': 'weather.precipitation.rate.daily'},
#                    'precipitationYesterday':             {'type': 'precipitationDaily', 'sourceUnit': ['mm', 'day'], 'title': 'Yesterday', 'sourceKey': 'precip_accum_local_yesterday_final', 'category': 'weather.precipitation.rate.daily'},
#                    'precipitationYesterdayRaw':          {'type': 'precipitationDaily', 'sourceUnit': ['mm', 'day'], 'title': 'Yesterday Raw', 'sourceKey': 'precip_accum_local_yesterday', 'category': 'weather.precipitation.rate.daily'},
#                    'precipitationTime':                  {'type': 'time', 'sourceUnit': 'min', 'title': 'Minutes', 'sourceKey': 'precip_minutes_local_day', 'category': 'weather.precipitation.time'},
#                    'precipitationTimeYesterdayRaw':      {'type': 'time', 'sourceUnit': 'min', 'title': 'Minutes Yesterday Raw', 'sourceKey': 'precip_minutes_local_yesterday', 'category': 'weather.precipitation.time'},
#                    'precipitationTimeYesterday':         {'type': 'time', 'sourceUnit': 'min', 'title': 'Minutes Yesterday', 'sourceKey': 'precip_minutes_local_yesterday_final', 'category': 'weather.precipitation.time'},
#                    'precipitationType':                  {'type': 'precipitationType', 'sourceUnit': '*', 'title': 'Precipitation Type', 'sourceKey': 'precip_type', 'category': 'weather.precipitation.type'},
#                    'precipitationAnalysisType':          {'type': 'rainCheckType', 'sourceUnit': 'int', 'title': 'Type', 'sourceKey': 'precip_analysis_type', 'category': 'weather.precipitation.analysis.type'},
#                    'precipitationAnalysisTypeYesterday': {'type': 'rainCheckType', 'sourceUnit': 'int', 'title': 'Type Yesterday', 'sourceKey': 'precip_analysis_type_yesterday', 'category': 'weather.precipitation.analysis.type'},
#                    'precipitationProbability':           {'type': 'probability', 'sourceUnit': '%p', 'title': 'Precipitation Probability', 'sourceKey': 'precip_probability', 'category': 'weather.precipitation.probability'},
#                    'lightningLast':                      {'type': 'date', 'sourceUnit': 'epoch', 'title': 'Last Strike', 'sourceKey': 'lightning_strike_last_epoch', 'category': 'weather.lightning.last'},
#                    'lightningLastDistance':              {'type': 'length', 'sourceUnit': 'km', 'title': 'Last Strike Distance', 'sourceKey': 'lightning_strike_last_distance', 'category': 'weather.lightning.last'},
#                    'lightning':                          {'type': 'strikeCount', 'sourceUnit': 'strike', 'title': 'Strike Count', 'sourceKey': 'lightning_strike_count', 'category': 'weather.lightning'},
#                    'lightningEnergy':                    {'type': 'energy', 'sourceUnit': 'int', 'title': 'Strike Energy', 'sourceKey': 'strikeEnergy', 'category': 'weather.lightning'},
#                    'lightning1hr':                       {'type': 'strikeCount', 'sourceUnit': 'strike', 'title': 'Lightning 1hr', 'sourceKey': 'lightning_strike_count_last_1hr', 'category': 'weather.lightning'},
#                    'lightning3hr':                       {'type': 'strikeCount', 'sourceUnit': 'strike', 'title': 'Lightning 3hrs', 'sourceKey': 'lightning_strike_count_last_3hr', 'category': 'weather.lightning'},
#                    'time':                               {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Time', 'sourceKey': 'timestamp', 'category': 'weather.time'},
#                    'hour':                               {'type': 'time', 'sourceUnit': 'int', 'title': 'Hour', 'sourceKey': 'local_hour', 'category': 'weather.time'},
#                    'day':                                {'type': 'time', 'sourceUnit': 'int', 'title': 'Day', 'sourceKey': 'local_day', 'category': 'weather.time'},
#                    'battery':                            {'type': 'voltage', 'sourceUnit': 'volts', 'title': 'Battery', 'sourceKey': 'battery', 'category': 'weather.device.battery'},
#                    'deviceSerial':                       {'type': 'status', 'sourceUnit': 'str', 'title': 'Device SN', 'sourceKey': 'serial_number', 'category': 'weather.device'},
#                    'hubSerial':                          {'type': 'status', 'sourceUnit': 'str', 'title': 'Hub SN', 'sourceKey': 'hub_sn', 'category': 'weather.device'},
#                    'uptime':                             {'type': 'status', 'sourceUnit': 's', 'title': 'Uptime', 'sourceKey': 'uptime', 'category': 'weather.device'},
#                    'firmware':                           {'type': 'status', 'sourceUnit': 'int', 'title': 'Firmware', 'sourceKey': 'battery', 'category': 'weather.device'},
#                    'deviceRSSI':                         {'type': 'status', 'sourceUnit': 'rssi', 'title': 'Device Signal', 'sourceKey': 'rssi', 'category': 'weather.device'},
#                    'hubRSSI':                            {'type': 'status', 'sourceUnit': 'rssi', 'title': 'Hub Signal', 'sourceKey': 'hub_rssi', 'category': 'weather.device'},
#                    'sensorStatus':                       {'type': 'status', 'sourceUnit': 'str', 'title': 'Sensor Status', 'sourceKey': 'sensor_status', 'category': 'weather.device'},
#                    'debug':                              {'type': 'status', 'sourceUnit': 'bool', 'title': 'Debug', 'sourceKey': 'debug', 'category': 'weather.device'},
#                    'resetFlags':                         {'type': 'status', 'sourceUnit': 'str', 'title': 'Reset Flags', 'sourceKey': 'reset_flags', 'category': 'weather.device'},
#                    'conditionIcon':                      {'type': 'icon', 'sourceUnit': 'str', 'title': 'Condition Icon', 'sourceKey': 'icon', 'category': 'weather.condition'},
#                    'precipitationIcon':                  {'type': 'icon', 'sourceUnit': 'str', 'title': 'Precipitation Icon', 'sourceKey': 'precip_icon', 'category': 'weather.precipitation'},
#                    'conditions':                         {'type': 'description', 'sourceUnit': 'str', 'title': 'Condition', 'sourceKey': 'conditions', 'category': 'weather.condition'},
#                    'sunrise':                            {'type': 'date', 'sourceUnit': 'epoch', 'title': 'Sunrise', 'sourceKey': 'sunrise', 'category': 'weather.sun'},
#                    'sunset':                             {'type': 'date', 'sourceUnit': 'epoch', 'title': 'Sunset', 'sourceKey': 'sunset', 'category': 'weather.sun'},
#                    'temperatureHigh':                    {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Temperature High', 'sourceKey': 'air_temp_high', 'category': 'weather.temperature'},
#                    'temperatureLow':                     {'type': 'temperature', 'sourceUnit': 'c', 'title': 'Temperature Low', 'sourceKey': 'air_temp_low', 'category': 'weather.temperature'},
#                    }

unitDefinitions = {
	'environment.temperature':                           {'type': 'temperature', 'sourceUnit': 'c'},
	'environment.temperature.temperature':               {'title': 'Temperature', 'sourceKey': 'air_temperature'},
	'environment.temperature.dewpoint':                  {'title': 'Dewpoint', 'sourceKey': 'dew_point'},
	'environment.temperature.wetBulb':                   {'title': 'Wet Bulb', 'sourceKey': 'wet_bulb_temperature'},
	'environment.temperature.feelsLike':                 {'title': 'Feels Like', 'sourceKey': 'feels_like'},
	'environment.temperature.heatIndex':                 {'title': 'Heat Index', 'sourceKey': 'heat_index'},
	'environment.temperature.windChill':                 {'title': 'Wind Chill', 'sourceKey': 'wind_chill'},
	'environment.temperature.deltaT':                    {'title': 'Delta T', 'sourceKey': 'delta_t'},
	'environment.temperature.high':                      {'title': 'Temperature High', 'sourceKey': 'air_temp_high'},
	'environment.temperature.low':                       {'title': 'Temperature Low', 'sourceKey': 'air_temp_low'},

	'environment.humidity.humidity':                     {'type': 'humidity', 'sourceUnit': '%', 'title': 'Humidity', 'sourceKey': 'relative_humidity'},

	'environment.light.uvi':                             {'type': 'index', 'sourceUnit': 'uvi', 'title': 'UVI', 'sourceKey': 'uv'},
	'environment.light.irradiance':                      {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Irradiance', 'sourceKey': 'solar_radiation'},
	'environment.light.illuminance':                     {'type': 'illuminance', 'sourceUnit': 'lux', 'title': 'Illuminance', 'sourceKey': 'brightness'},
	'environment.pressure':                              {'type': 'pressure', 'sourceUnit': 'mb'},
	'environment.pressure.pressure':                     {'title': 'Pressure', 'sourceKey': 'barometric_pressure'},
	'environment.pressure.pressureAbsolute':             {'title': 'Absolute', 'sourceKey': 'station_pressure'},
	'environment.pressure.pressureSeaLevel':             {'title': 'Sea Level', 'sourceKey': 'sea_level_pressure'},
	'environment.pressure.airDensity':                   {'type': 'airDensity', 'sourceUnit': ['kg', 'm'], 'title': 'Air Density', 'sourceKey': 'air_density'},
	'environment.pressure.trend':                        {'type': 'pressureTrend', 'sourceUnit': '*', 'title': 'Trend', 'sourceKey': 'pressure_trend'},

	'environment.wind.direction.direction':              {'type': 'direction', 'sourceUnit': 'º', 'title': 'Direction', 'sourceKey': 'wind_direction'},
	'environment.wind.direction.cardinal':               {'type': None, 'sourceUnit': None, 'title': None, 'sourceKey': 'wind_direction_cardinal'},
	'environment.wind.speed':                            {'type': 'wind', 'sourceUnit': ['m', 's']},
	'environment.wind.speed.speed':                      {'title': 'Speed', 'sourceKey': 'wind_avg'},
	'environment.wind.speed.lull':                       {'title': 'Lull', 'sourceKey': 'wind_lull'},
	'environment.wind.speed.gust':                       {'title': 'Gust', 'sourceKey': 'wind_gust'},

	'environment.precipitation.precipitation':           {'type': 'precipitationRate', 'sourceUnit': ['mm', 'min'], 'title': 'Rate', 'sourceKey': 'precip'},
	'environment.precipitation.hourly':                  {'type': 'precipitationHourly', 'sourceUnit': ['mm', 'hr'], 'title': 'Hourly', 'sourceKey': 'precip_accum_last_1hr'},
	'environment.precipitation.daily':                   {'type': 'precipitationDaily', 'sourceUnit': ['mm', 'day'], 'title': 'Daily', 'sourceKey': 'precip_accum_local_day'},
	'environment.precipitation.dailyFinal':              {'type': 'precipitationDaily', 'sourceUnit': ['mm', 'day'], 'title': 'Daily', 'sourceKey': 'precip_accum_local_day_final'},
	'environment.precipitation.icon':                    {'type': 'icon', 'sourceUnit': 'str', 'title': 'Precipitation Icon', 'sourceKey': 'precip_icon'},
	'environment.precipitation.time':                    {'type': 'time', 'sourceUnit': 'min', 'title': 'Minutes', 'sourceKey': 'precip_minutes_local_day'},
	'environment.precipitation.type':                    {'type': 'precipitationType', 'sourceUnit': '*', 'title': 'Precipitation Type', 'sourceKey': 'precip_type'},
	'environment.precipitation.analysis':                {'type': 'rainCheckType', 'sourceUnit': 'int', 'title': 'Type', 'sourceKey': 'precip_analysis_type'},
	'environment.precipitation.probability':             {'type': 'probability', 'sourceUnit': '%p', 'title': 'Precipitation Probability', 'sourceKey': 'precip_probability'},

	'environment.yesterday.precipitation.precipitation': {'type': 'precipitationDaily', 'sourceUnit': ['mm', 'day'], 'title': 'Yesterday', 'sourceKey': ('precip_accum_local_yesterday_final', 'precip_accum_local_yesterday')},
	'environment.yesterday.precipitation.time':          {'type': 'time', 'sourceUnit': 'min', 'title': 'Minutes Yesterday', 'sourceKey': 'precip_minutes_local_yesterday_final'},
	'environment.yesterday.precipitation.timeRaw':       {'type': 'time', 'sourceUnit': 'min', 'title': 'Minutes Yesterday Raw', 'sourceKey': 'precip_minutes_local_yesterday'},
	'environment.yesterday.precipitation.analysis':      {'type': 'rainCheckType', 'sourceUnit': 'int', 'title': 'Type Yesterday', 'sourceKey': 'precip_analysis_type_yesterday'},

	'environment.lightning.last':                        {'type': 'date', 'sourceUnit': 'epoch', 'title': 'Last Strike', 'sourceKey': 'lightning_strike_last_epoch'},
	'environment.lightning.distance':                    {'type': 'length', 'sourceUnit': 'km', 'title': 'Last Strike Distance', 'sourceKey': 'lightning_strike_last_distance'},
	# 'environment.lightning.distance':                    {'type': 'length', 'sourceUnit': 'km', 'title': 'Last Strike Distance', 'sourceKey': 'lightning_strike_last_distance_msg'},
	'environment.lightning.lightning':                   {'type': 'strikeCount', 'sourceUnit': 'strike', 'title': 'Strike Count', 'sourceKey': 'lightning_strike_count'},
	'environment.lightning.energy':                      {'type': 'energy', 'sourceUnit': 'int', 'title': 'Strike Energy', 'sourceKey': 'strikeEnergy'},
	'environment.lightning.count1hr':                    {'type': 'strikeCount', 'sourceUnit': 'strike', 'title': 'Lightning 1hr', 'sourceKey': 'lightning_strike_count_last_1hr'},
	'environment.lightning.count3hr':                    {'type': 'strikeCount', 'sourceUnit': 'strike', 'title': 'Lightning 3hrs', 'sourceKey': 'lightning_strike_count_last_3hr'},

	'time.time':                                         {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Time', 'sourceKey': ('time', 'timestamp', 'day_start_local')},
	'time.hour':                                         {'type': 'time', 'sourceUnit': 'hr', 'title': 'Hour', 'sourceKey': 'local_hour'},
	'time.day':                                          {'type': 'time', 'sourceUnit': 'day', 'title': 'Day', 'sourceKey': ('local_day', 'day_num')},
	'time.month':                                        {'type': 'time', 'sourceUnit': 'month', 'title': 'Month', 'sourceKey': ('local_day', 'month_num')},

	'device.sampleInterval.wind':                        {'type': 'interval', 'sourceUnit': 's', 'title': 'Sample Interval', 'sourceKey': 'windSampleInterval'},
	'device.sampleInterval.report':                      {'type': 'interval', 'sourceUnit': 'min', 'title': 'Report Interval', 'sourceKey': 'reportInterval'},

	'device.status.battery':                             {'type': 'voltage', 'sourceUnit': 'volts', 'title': 'Battery', 'sourceKey': 'battery'},
	'device.status':                                     {'type': 'status'},
	'device.status.deviceSerial':                        {'sourceUnit': 'str', 'title': 'Device SN', 'sourceKey': 'serial_number'},
	'device.status.hubSerial':                           {'sourceUnit': 'str', 'title': 'Hub SN', 'sourceKey': 'hub_sn'},
	'device.status.uptime':                              {'sourceUnit': 's', 'title': 'Uptime', 'sourceKey': 'uptime'},
	'device.status.firmware':                            {'sourceUnit': 'int', 'title': 'Firmware', 'sourceKey': 'battery'},
	'device.status.deviceRSSI':                          {'sourceUnit': 'rssi', 'title': 'Device Signal', 'sourceKey': 'rssi'},
	'device.status.hubRSSI':                             {'sourceUnit': 'rssi', 'title': 'Hub Signal', 'sourceKey': 'hub_rssi'},
	'device.status.sensorStatus':                        {'sourceUnit': 'str', 'title': 'Sensor Status', 'sourceKey': 'sensor_status'},
	'device.status.debug':                               {'sourceUnit': 'bool', 'title': 'Debug', 'sourceKey': 'debug'},
	'device.status.resetFlags':                          {'sourceUnit': 'str', 'title': 'Reset Flags', 'sourceKey': 'reset_flags'},
	'environment.condition.icon':                        {'type': 'icon', 'sourceUnit': 'str', 'title': 'Condition Icon', 'sourceKey': 'icon'},
	'environment.condition.condition':                   {'type': 'description', 'sourceUnit': 'str', 'title': 'Condition', 'sourceKey': 'conditions'},
	'environment.sunrise':                               {'type': 'date', 'sourceUnit': 'epoch', 'title': 'Sunrise', 'sourceKey': 'sunrise'},
	'environment.sunset':                                {'type': 'date', 'sourceUnit': 'epoch', 'title': 'Sunset', 'sourceKey': 'sunset'}
}

unitDefinitionsForecast = unitDefinitions.copy()
unitDefinitionsForecast.update({'time.time':                               {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Time', 'sourceKey': 'time', 'category': 'weather.time'},
                                'environment.precipitation.precipitation': {'type': 'precipitation', 'sourceUnit': 'mm', 'title': 'Precipitation', 'sourceKey': 'precip', 'category': 'weather.precipitation'},
                                'environment.precipitation.type':          {'type': 'description', 'sourceUnit': 'str', 'title': 'Precipitation Type', 'sourceKey': 'precip_type', 'category': 'weather.precipitation'},
                                })


class WFObservationRealtime(EnvironmentObservationRealtime):
	subscriptionChannel = 'WeatherFlow'
	_translator = unitDefinitions


class WFObservationHour(EnvironmentObservationForecastItem):
	_translator = unitDefinitionsForecast


class WFObservationDay(EnvironmentObservationForecastItem):
	_translator = unitDefinitionsForecast.copy()
	_translator.update({'time.time': {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Time', 'sourceKey': 'day_start_local'}})


class WFForecastHourly(EnvironmentObservationForecast):
	_observationClass = WFObservationHour
	_period = Period.Hour


class WFForecastDaily(EnvironmentObservationForecast):
	_observationClass = WFObservationDay
	_period = Period.Day
