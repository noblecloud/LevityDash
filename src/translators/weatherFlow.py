from src import SmartDictionary
from . import Translator, UnitTranslator

from WeatherUnits.defaults.WeatherFlow import *


class WFUnits(UnitTranslator):
	_time = SmartDictionary({'type': 'datetime', 'unit': 'date'})
	_temperature = SmartDictionary({'temperature': {'type': 'temperature', 'unit': 'c', 'title': 'Temperature'},
	                                'dewpoint':    {'type': 'temperature', 'unit': 'c', 'title': 'Dewpoint'},
	                                'wetbulb':     {'type': 'temperature', 'unit': 'c', 'title': 'Wet Bulb'},
	                                'feelsLike':   {'type': 'temperature', 'unit': 'c', 'title': 'Feels Like'},
	                                'heatIndex':   {'type': 'temperature', 'unit': 'c', 'title': 'Heat Index'},
	                                'windChill':   {'type': 'temperature', 'unit': 'c', 'title': 'Wind Chill'},
	                                'deltaT':      {'type': 'temperature', 'unit': 'c', 'title': 'Delta T'},
	                                'humidity':    {'type': 'humidity', 'unit': '%', 'title': 'Humidity'}})
	_pressure = SmartDictionary({'pressure':   {'type': 'pressure', 'unit': 'mb', 'title': 'Pressure'},
	                             'absolute':   {'type': 'pressure', 'unit': 'mb', 'title': 'Absolute'},
	                             'seaLevel':   {'type': 'pressure', 'unit': 'mb', 'title': 'Sea Level'},
	                             'airDensity': {'type': 'pressure', 'unit': 'mb', 'title': 'Air Density'},
	                             'trend':      {'type': 'str', 'unit': 'str', 'title': 'Trend'}})
	_wind = SmartDictionary({'direction': {'type': 'direction', 'unit': 'º', 'title': 'Direction'},
	                         'speed':     {'type': 'wind', 'unit': ('m', 's'), 'title': 'Speed'},
	                         'lull':      {'type': 'wind', 'unit': ('m', 's'), 'title': 'Lull'},
	                         'gust':      {'type': 'wind', 'unit': ('m', 's'), 'title': 'Gust'},
	                         'interval':  {'type': 'interval', 'unit': 's', 'title': 'Sample Interval'}})
	_light = SmartDictionary({'uvi':         {'type': 'index', 'unit': 'uvi', 'title': 'UVI'},
	                          'irradiance':  {'type': 'irradiance', 'unit': 'W/m^2', 'title': 'Irradiance'},
	                          'illuminance': {'type': 'illuminance', 'unit': 'lux', 'title': 'Illuminance'}})
	_precipitation = SmartDictionary({'type':                {'type': 'precipitationType', 'unit': 'precipitationType', 'title': 'Type'},
	                                  'typeYesterday':       {'type': 'precipitationType', 'unit': 'precipitationType', 'title': 'Type Yesterday'},
	                                  'rate':                {'type': 'precipitationRate', 'unit': ('mm', 'min'), 'title': 'Rate'},
	                                  'hourly':              {'type': 'precipitationHourly', 'unit': ('mm', 'hr'), 'title': 'Hourly'},
	                                  'daily':               {'type': 'precipitationDaily', 'unit': ('mm', 'day'), 'title': 'Daily'},
	                                  'yesterday':           {'type': 'precipitationDaily', 'unit': ('mm', 'day'), 'title': 'Yesterday'},
	                                  'yesterdayRaw':        {'type': 'precipitationDaily', 'unit': ('mm', 'day'), 'title': 'Yesterday'},
	                                  'minutes':             {'type': 'time', 'unit': 'min', 'title': 'Minutes'},
	                                  'minutesYesterday':    {'type': 'time', 'unit': 'min', 'title': 'Minutes Yesterday'},
	                                  'minutesYesterdayRaw': {'type': 'time', 'unit': 'min', 'title': 'Minutes Yesterday'}})
	_lightning = SmartDictionary({'strikeCount':       {'type': 'strikeCount', 'unit': 'strike', 'title': 'Strikes'},
	                              'lightningDistance': {'type': 'length', 'unit': 'km', 'title': 'Distance'},
	                              'lightning1hr':      {'type': 'strikeCount', 'unit': 'strike', 'title': '1hr'},
	                              'lightning3hr':      {'type': 'strikeCount', 'unit': 'strike', 'title': '3hrs'}})
	_battery = SmartDictionary({'type': 'power', 'unit': 'volts', 'title': 'Battery'})
	_meta = SmartDictionary({'time': _time, 'battery': _battery})
	_flat: dict

	def __init__(self, *args, **kwargs):
		super(WFUnits, self).__init__({
				'temperature':   self._temperature,
				'pressure':      self._pressure,
				'wind':          self._wind,
				'light':         self._light,
				'precipitation': self._precipitation,
				'lightning':     self._lightning,
				'meta':          self._meta}, *args, **kwargs)


class WFTranslator(Translator):
	_units: SmartDictionary = WFUnits()

	_time = SmartDictionary({'timestamp': 'time',
	                         'timezone':  'timezone'})


class WFStationTranslator(WFTranslator):
	_flat: SmartDictionary
	_light = SmartDictionary({'uv':              'uvi',
	                          'solar_radiation': 'irradiance',
	                          'brightness':      'illuminance'})
	_temperature = SmartDictionary({'air_temperature':      'temperature',
	                                'dew_point':            'dewpoint',
	                                'wet_bulb_temperature': 'wetbulb',
	                                'feels_like':           'feelsLike',
	                                'heat_index':           'heatIndex',
	                                'wind_chill':           'windChill',
	                                'delta_t':              'deltaT',
	                                'relative_humidity':    'humidity'})
	_wind = SmartDictionary({'wind_direction':     'direction',
	                         'wind_avg':           'speed',
	                         'wind_lull':          'lull',
	                         'wind_gust':          'gust',
	                         'windSampleInterval': 'interval'})
	_precipitation = SmartDictionary({'precip':                               'rate',
	                                  'precip_accum_last_1hr':                'hourly',
	                                  'precip_accum_local_day':               'daily',
	                                  'precip_accum_local_yesterday_final':   'yesterday',
	                                  'precip_accum_local_yesterday':         'yesterdayRaw',
	                                  'precip_minutes_local_day':             'minutes',
	                                  'precip_minutes_local_yesterday':       'minutesYesterdayRaw',
	                                  'precip_minutes_local_yesterday_final': 'minutesYesterday',
	                                  'precip_analysis_type':                 'type',
	                                  'precip_analysis_type_yesterday':       'typeYesterday'})
	_pressure = SmartDictionary({'barometric_pressure': 'pressure',
	                             'station_pressure':    'absolute',
	                             'sea_level_pressure':  'seaLevel',
	                             'air_density':         'airDensity',
	                             'pressure_trend':      'trend'})
	_lightning = SmartDictionary({'lightning_strike_count':          'strikeCount',
	                              'lightning_strike_count_last_1hr': 'lightning1hr',
	                              'lightning_strike_count_last_3hr': 'lightning3hr'})

	def __init__(self, *args, **kwargs):
		super(WFStationTranslator, self).__init__(
				{'temperature':   self._temperature,
				 'light':         self._light,
				 'pressure':      self._pressure,
				 'wind':          self._wind,
				 'precipitation': self._precipitation,
				 'lightning':     self._lightning}, *args, **kwargs)
		self._classes.update({
				'precipitationType': PrecipitationType
		})


class AWUDPDictionary(SmartDictionary):
	obs_st = [('time', 'datetime'),
	          ('lullSpeed', ('m', 's')),
	          ('windSpeed', ('m', 's')),
	          ('gustSpeed', ('m', 's')),
	          ('windDirection', 'º'),
	          ('windSampleInterval', 'sec'),
	          ('pressure', 'mb'),
	          ('temperature', 'c'),
	          ('humidity', '%'),
	          ('illuminance', 'lux'),
	          ('uvi', 'index'),
	          ('irradiance', 'W/m^2'),
	          ('precipitationHourlyRaw', ('mm', 'min')),
	          ('precipitationType', PrecipitationType),
	          ('lightningDistance', 'km'),
	          ('lightning', Strikes),
	          ('battery', 'volts'),
	          ('reportInterval', 'min')]

	def __init__(self, *args, **kwargs):
		super(AWUDPDictionary, self).__init__(*args, **kwargs)


# _obs_state = _SmartDictionary({
# 		0:  'time',
# 		# 1 - Wind Lull (m/s)
# 		1:  'lullSpeed',
# 		# 2 - Wind Avg (m/s)
# 		2:  'windSpeed',
# 		# 3 - Wind Gust (m/s)
# 		3:  'gustSpeed',
# 		# 4 - Wind Direction (degrees)
# 		4:  'windDirection',
# 		# 5 - Wind Sample Interval (seconds)
# 		5:  'windSampleInterval',
# 		# 6 - Pressure (MB)
# 		6:  'pressure',
# 		# 7 - Air Temperature (C)
# 		7:  'temperature',
# 		# 8 - Relative Humidity (%)
# 		8:  'humidity',
# 		# 9 - Illuminance (lux)
# 		9:  'illuminance',
# 		# 10 - UV (index)
# 		10: 'uvi',
# 		# 11 - Solar Radiation (W/m^2)
# 		11: 'irradiance',
# 		# 12 - Rain Accumulation (mm)
# 		12: 'precipitationHourlyRaw',
# 		# 13 - Precipitation Type (0 = none, 1 = rain, 2 = hail)
# 		13: 'precipitationType',
# 		# 14 - Average Strike Distance (km)
# 		14: 'lightningDistance',
# 		# 15 - Strike Count
# 		15: 'lightning',
# 		# 16 - Battery (volts)
# 		16: 'battery',
# 		# 17 - Report Interval (minutes)
# 		17: 'reportInterval', })


class WFDeviceTranslator(WFTranslator):
	precipitationType = ['none', 'rain', 'hail']

	udpDefault = {0: ('time', 'sec')}

	obs_st = {
			1:  ('lullSpeed', ('m', 's')),
			2:  ('windSpeed', ('m', 's')),
			3:  ('gustSpeed', ('m', 's')),
			4:  ('windDirection', 'º'),
			5:  ('windSampleInterval', 'sec'),
			6:  ('pressure', 'mb'),
			7:  ('temperature', 'c'),
			8:  ('humidity', '%'),
			9:  ('illuminance', 'lux'),
			10: ('uvi', 'index'),
			11: ('irradiance', 'W/m^2'),
			12: ('precipitationHourlyRaw', ('mm', 'min')),
			13: ('precipitationType', PrecipitationType),
			14: ('lightningDistance', 'km'),
			15: ('lightning', 'int'),
			16: ('battery', 'volts'),
			17: ('reportInterval', 'min'),
			18: ('precipitationDailyRaw', ('mm', 'day')),
			19: ('precipitationHourly', ('mm', 'hr')),
			20: ('precipitationDaily', ('mm', 'day')),
			21: ('precipitationCheck', 'bool')}


class WFUDPMessageDictionary(SmartDictionary):
	pass


_valueToIndex = {  # 0 - Epoch (Seconds UTC)
		'time':                   0,
		# 1 - Wind Lull (m/s)
		'lullSpeed':              1,
		# 2 - Wind Avg (m/s)
		'windSpeed':              2,
		# 3 - Wind Gust (m/s)
		'gustSpeed':              3,
		# 4 - Wind Direction (degrees)
		'windDirection':          4,
		# 5 - Wind Sample Interval (seconds)
		'windSampleInterval':     5,
		# 6 - Pressure (MB)
		'pressure':               6,
		# 7 - Air Temperature (C)
		'temperature':            7,
		# 8 - Relative Humidity (%)
		'humidity':               8,
		# 9 - Illuminance (lux)
		'illuminance':            9,
		# 10 - UV (index)
		'uvi':                    10,
		# 11 - Solar Radiation (W/m^2)
		'irradiance':             11,
		# 12 - Rain Accumulation (mm)
		'precipitationHourlyRaw': 12,
		# 13 - Precipitation Type (0 = none, 1 = rain, 2 = hail)
		'precipitationType':      13,
		# 14 - Average Strike Distance (km)
		'lightningDistance':      14,
		# 15 - Strike Count
		'lightning':              15,
		# 16 - Battery (volts)
		'battery':                16,
		# 17 - Report Interval (minutes)
		'reportInterval':         17,
		# 18 - Local Day precipitation Accumulation (mm)
		'precipitationDailyRaw':  18,
		# 19 - Rain Accumulation Final (Rain Check) (mm)
		'precipitationHourly':    19,
		# 20 - Local Day Rain Accumulation Final (Rain Check) (mm)
		'precipitationDaily':     20,
		# 21 - Precipitation Aanalysis Type (0 = none, 1 = Rain Check with user display on, 2 = Rain Check with user display off)
		'precipitationCheck':     21}
