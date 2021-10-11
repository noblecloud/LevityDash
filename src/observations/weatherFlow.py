from src.observations import Observation, ObservationRealtime, ObservationForecast
from src.utils import Period

unitDefinitions = {'temperature':                        {'type': 'temperature', 'unit': 'c', 'title': 'Temperature', 'sourceKey': 'air_temperature'},
                   'dewpoint':                           {'type': 'temperature', 'unit': 'c', 'title': 'Dewpoint', 'sourceKey': 'dew_point'},
                   'wetBulb':                            {'type': 'temperature', 'unit': 'c', 'title': 'Wet Bulb', 'sourceKey': 'wet_bulb_temperature'},
                   'feelsLike':                          {'type': 'temperature', 'unit': 'c', 'title': 'Feels Like', 'sourceKey': 'feels_like'},
                   'heatIndex':                          {'type': 'temperature', 'unit': 'c', 'title': 'Heat Index', 'sourceKey': 'heat_index'},
                   'windChill':                          {'type': 'temperature', 'unit': 'c', 'title': 'Wind Chill', 'sourceKey': 'wind_chill'},
                   'deltaT':                             {'type': 'temperature', 'unit': 'c', 'title': 'Delta T', 'sourceKey': 'delta_t'},
                   'humidity':                           {'type': 'humidity', 'unit': '%', 'title': 'Humidity', 'sourceKey': 'relative_humidity'},
                   'uvi':                                {'type': 'index', 'unit': 'uvi', 'title': 'UVI', 'sourceKey': 'uv'},
                   'irradiance':                         {'type': 'irradiance', 'unit': 'W/m^2', 'title': 'Irradiance', 'sourceKey': 'solar_radiation'},
                   'illuminance':                        {'type': 'illuminance', 'unit': 'lux', 'title': 'Illuminance', 'sourceKey': 'brightness'},
                   'pressure':                           {'type': 'pressure', 'unit': 'mb', 'title': 'Pressure', 'sourceKey': 'barometric_pressure'},
                   'pressureAbsolute':                   {'type': 'pressure', 'unit': 'mb', 'title': 'Absolute', 'sourceKey': 'station_pressure'},
                   'pressureSeaLevel':                   {'type': 'pressure', 'unit': 'mb', 'title': 'Sea Level', 'sourceKey': 'sea_level_pressure'},
                   'airDensity':                         {'type': 'airDensity', 'unit': ['kg', 'm'], 'title': 'Air Density', 'sourceKey': 'air_density'},
                   'pressureTrend':                      {'type': 'pressureTrend', 'unit': '*', 'title': 'Trend', 'sourceKey': 'pressure_trend'},
                   'windDirection':                      {'type': 'direction', 'unit': 'º', 'title': 'Direction', 'sourceKey': 'wind_direction'},
                   'windSpeed':                          {'type': 'wind', 'unit': ['m', 's'], 'title': 'Speed', 'sourceKey': 'wind_avg'},
                   'lullSpeed':                          {'type': 'wind', 'unit': ['m', 's'], 'title': 'Lull', 'sourceKey': 'wind_lull'},
                   'gustSpeed':                          {'type': 'wind', 'unit': ['m', 's'], 'title': 'Gust', 'sourceKey': 'wind_gust'},
                   'windSampleInterval':                 {'type': 'interval', 'unit': 's', 'title': 'Sample Interval', 'sourceKey': 'windSampleInterval'},
                   'reportInterval':                     {'type': 'interval', 'unit': 'min', 'title': 'Report Interval', 'sourceKey': 'reportInterval'},
                   'precipitationRate':                  {'type': 'precipitationRate', 'unit': ['mm', 'min'], 'title': 'Rate', 'sourceKey': 'precip'},
                   'precipitationHourly':                {'type': 'precipitationHourly', 'unit': ['mm', 'hr'], 'title': 'Hourly', 'sourceKey': 'precip_accum_last_1hr'},
                   'precipitationDaily':                 {'type': 'precipitationDaily', 'unit': ['mm', 'day'], 'title': 'Daily', 'sourceKey': 'precip_accum_local_day'},
                   'precipitationYesterday':             {'type': 'precipitationDaily', 'unit': ['mm', 'day'], 'title': 'Yesterday', 'sourceKey': 'precip_accum_local_yesterday_final'},
                   'precipitationYesterdayRaw':          {'type': 'precipitationDaily', 'unit': ['mm', 'day'], 'title': 'Yesterday Raw', 'sourceKey': 'precip_accum_local_yesterday'},
                   'precipitationMinutes':               {'type': 'time', 'unit': 'min', 'title': 'Minutes', 'sourceKey': 'precip_minutes_local_day'},
                   'precipitationMinutesYesterdayRaw':   {'type': 'time', 'unit': 'min', 'title': 'Minutes Yesterday Raw', 'sourceKey': 'precip_minutes_local_yesterday'},
                   'precipitationMinutesYesterday':      {'type': 'time', 'unit': 'min', 'title': 'Minutes Yesterday', 'sourceKey': 'precip_minutes_local_yesterday_final'},
                   'precipitationType':                  {'type': 'precipitationType', 'unit': '*', 'title': 'Precipitation Type', 'sourceKey': 'precip_type'},
                   'precipitationAnalysisType':          {'type': 'rainCheckType', 'unit': 'int', 'title': 'Type', 'sourceKey': 'precip_analysis_type'},
                   'precipitationAnalysisTypeYesterday': {'type': 'rainCheckType', 'unit': 'int', 'title': 'Type Yesterday', 'sourceKey': 'precip_analysis_type_yesterday'},
                   'precipitationProbability':           {'type': 'probability', 'unit': '%p', 'title': 'Precipitation Probability', 'sourceKey': 'precip_probability'},
                   'lightningLast':                      {'type': 'date', 'unit': 'epoch', 'title': 'Last Strike', 'sourceKey': 'lightning_strike_last_epoch'},
                   'lightningLastDistance':              {'type': 'length', 'unit': 'km', 'title': 'Last Strike Distance', 'sourceKey': 'lightning_strike_last_distance'},
                   'lightning':                          {'type': 'strikeCount', 'unit': 'strike', 'title': 'Strike Count', 'sourceKey': 'lightning_strike_count'},
                   'lightningEnergy':                    {'type': 'energy', 'unit': 'int', 'title': 'Strike Energy', 'sourceKey': 'strikeEnergy'},
                   'lightning1hr':                       {'type': 'strikeCount', 'unit': 'strike', 'title': 'Lightning 1hr', 'sourceKey': 'lightning_strike_count_last_1hr'},
                   'lightning3hr':                       {'type': 'strikeCount', 'unit': 'strike', 'title': 'Lightning 3hrs', 'sourceKey': 'lightning_strike_count_last_3hr'},
                   'time':                               {'type': 'datetime', 'unit': 'epoch', 'title': 'Time', 'sourceKey': 'timestamp'},
                   'hour':                               {'type': 'time', 'unit': 'int', 'title': 'Hour', 'sourceKey': 'local_hour'},
                   'day':                                {'type': 'time', 'unit': 'int', 'title': 'Day', 'sourceKey': 'local_day'},
                   'battery':                            {'type': 'voltage', 'unit': 'volts', 'title': 'Battery', 'sourceKey': 'battery'},
                   'deviceSerial':                       {'type': 'status', 'unit': 'str', 'title': 'Device SN', 'sourceKey': 'serial_number'},
                   'hubSerial':                          {'type': 'status', 'unit': 'str', 'title': 'Hub SN', 'sourceKey': 'hub_sn'},
                   'uptime':                             {'type': 'status', 'unit': 's', 'title': 'Uptime', 'sourceKey': 'uptime'},
                   'firmware':                           {'type': 'status', 'unit': 'int', 'title': 'Firmware', 'sourceKey': 'battery'},
                   'deviceRSSI':                         {'type': 'status', 'unit': 'rssi', 'title': 'Device Signal', 'sourceKey': 'rssi'},
                   'hubRSSI':                            {'type': 'status', 'unit': 'rssi', 'title': 'Hub Signal', 'sourceKey': 'hub_rssi'},
                   'sensorStatus':                       {'type': 'status', 'unit': 'str', 'title': 'Sensor Status', 'sourceKey': 'sensor_status'},
                   'debug':                              {'type': 'status', 'unit': 'bool', 'title': 'Debug', 'sourceKey': 'debug'},
                   'resetFlags':                         {'type': 'status', 'unit': 'str', 'title': 'Reset Flags', 'sourceKey': 'reset_flags'},
                   'conditionIcon':                      {'type': 'icon', 'unit': 'str', 'title': 'Condition Icon', 'sourceKey': 'icon'},
                   'precipitationIcon':                  {'type': 'icon', 'unit': 'str', 'title': 'Precipitation Icon', 'sourceKey': 'precip_icon'},
                   'conditions':                         {'type': 'description', 'unit': 'str', 'title': 'Condition', 'sourceKey': 'conditions'},
                   'sunrise':                            {'type': 'date', 'unit': 'epoch', 'title': 'Sunrise', 'sourceKey': 'sunrise'},
                   'sunset':                             {'type': 'date', 'unit': 'epoch', 'title': 'Sunset', 'sourceKey': 'sunset'},
                   'temperatureHigh':                    {'type': 'temperature', 'unit': 'c', 'title': 'Temperature High', 'sourceKey': 'air_temp_high'},
                   'temperatureLow':                     {'type': 'temperature', 'unit': 'c', 'title': 'Temperature Low', 'sourceKey': 'air_temp_low'},
                   }

unitDefinitionsForecast = unitDefinitions.copy()
unitDefinitionsForecast.update({'time':              {'type': 'datetime', 'unit': 'epoch', 'title': 'Time', 'sourceKey': 'time'},
                                'precipitation':     {'type': 'precipitation', 'unit': 'mm', 'title': 'Precipitation', 'sourceKey': 'precip'},
                                'precipitationType': {'type': 'description', 'unit': 'str', 'title': 'Precipitation Type', 'sourceKey': 'precip_type'},
                                })


class WFObservationRealtime(ObservationRealtime):
	subscriptionChannel = 'WeatherFlow'
	_translator = unitDefinitions


class WFObservationHour(Observation):
	_translator = unitDefinitionsForecast


class WFObservationDay(Observation):
	_translator = unitDefinitionsForecast.copy()
	_translator.update({'time': {'type': 'datetime', 'unit': 'epoch', 'title': 'Time', 'sourceKey': 'day_start_local'}})


class WFForecastHourly(ObservationForecast):
	_observationClass = WFObservationHour
	_period = Period.Hour


class WFForecastDaily(ObservationForecast):
	_observationClass = WFObservationDay
	_period = Period.Day
