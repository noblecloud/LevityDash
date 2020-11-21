from datetime import datetime, timedelta
from pytz import timezone, utc


class fields:
	REALTIME: list[str] = ['precipitation', 'precipitation_type', 'temp', 'feels_like', 'dewpoint', 'wind_speed',
						   'wind_gust', 'baro_pressure', 'visibility', 'humidity', 'wind_direction', 'sunrise',
						   'sunset',
						   'cloud_cover', 'cloud_ceiling', 'cloud_base', 'surface_shortwave_radiation', 'moon_phase',
						   'weather_code']
	NOWCAST: list[str] = ['precipitation', 'precipitation_type', 'temp', 'feels_like', 'dewpoint', 'wind_speed',
						  'wind_gust', 'baro_pressure', 'visibility', 'humidity', 'wind_direction', 'sunrise', 'sunset',
						  'cloud_cover', 'cloud_ceiling', 'cloud_base', 'surface_shortwave_radiation', 'weather_code']
	HOURLY: list[str] = ['precipitation', 'precipitation_type', 'precipitation_probability', 'temp', 'feels_like',
						 'dewpoint', 'wind_speed', 'wind_gust', 'baro_pressure', 'visibility', 'humidity',
						 'wind_direction', 'sunrise', 'sunset', 'cloud_cover', 'cloud_ceiling', 'cloud_base',
						 'surface_shortwave_radiation', 'moon_phase', 'weather_code']
	DAILY: list[str] = ['precipitation', 'precipitation_accumulation', 'temp', 'feels_like', 'wind_speed',
						'baro_pressure', 'visibility', 'humidity', 'wind_direction', 'sunrise', 'sunset', 'moon_phase',
						'weather_code']
	HISTORICAL: list[str] = ['precipitation', 'precipitation_type', 'temp', 'feels_like', 'dewpoint', 'wind_speed',
							 'wind_gust', 'baro_pressure', 'visibility', 'humidity', 'wind_direction', 'sunrise',
							 'sunset', 'cloud_cover', 'cloud_ceiling', 'cloud_base', 'surface_shortwave_radiation',
							 'weather_code']

	dictionary: dict[str, list[str]] = {'realtime': REALTIME, 'nowcast': NOWCAST, 'hourly': HOURLY, 'daily': DAILY}


FORECAST_TYPES = ['historical', 'realtime', 'nowcast', 'hourly', 'daily']

tz = timezone("US/Eastern")

class maxDates:

	def __init__(self):
		pass

	@staticmethod
	def historical() -> str:
		date = datetime.now() - timedelta(hours=3)
		print(date.strftime('%Y-%m-%d %H:%M:%S'))
		return date.strftime('%Y-%m-%d %H:%M:%S')

	@staticmethod
	def daily() -> str:
		date = datetime.now() + timedelta(days=14, hours=20)
		return date.strftime('%Y-%m-%d %H:%M:%S')

	@staticmethod
	def hourly() -> str:
		# date = datetime.now() + timedelta(hours=107, minutes=50)
		date = datetime.now() + timedelta(hours=72)
		return date.strftime('%Y-%m-%d %H:%M:%S')

	@staticmethod
	def realtime() -> str:
		date = datetime.now() + timedelta(minutes=2)
		return date.strftime('%Y-%m-%d %H:%M:%S')

	@staticmethod
	def nowcast() -> str:
		date = datetime.now() + timedelta(minutes=359)
		return date.strftime('%Y-%m-%d %H:%M:%S')
