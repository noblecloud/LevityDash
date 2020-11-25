from datetime import datetime, timedelta
from pytz import timezone, utc
from math import log, sin, pi


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


class Colors:

	kelvin = {3000: '#FFB16E', 3500: '#FFC18D', 4000: '#FFCEA6', 4500: '#FFDABB', 5000: '#FFE4CE', 5500: '#FFEDDE',
			  6000: '#FFF6ED'}

	def kelvinToHEX(self, temp: int) -> str:

		value = self.kelvinToRGB(temp)
		return '#%02x%02x%02x' % value

	def kelvinToRGB(self, temp: int) -> tuple[int, int, int]:

		def cleanup(value, limit):
			if value < 0:
				value = 0
			elif value > limit:
				value = limit
			else:
				value = int(value)
			return value

		# https://tannerhelland.com/2012/09/18/convert-temperature-rgb-algorithm-code.html

		if temp == 0:
			return 0, 0, 0

		temp /= 100

		# calculate red
		if temp <= 66:
			red = 255
		else:
			red = temp - 60
			red = 329.698727446 * pow(red, -0.1332047592)

		red = cleanup(red, 255)

		# calculate green
		if temp <= 66:
			green = temp
			green = 99.4708025861 * log(green) - 161.1195681661
		else:
			green = temp - 60
			green = 288.1221695283 * pow(green, -0.0755148492)

		green = cleanup(green, 255)

		# calculate blue
		if temp >= 66:
			blue = 255
		else:
			if temp <= 19:
				blue = 0
			else:
				blue = temp - 10
				blue = 138.5177312231 * log(blue) - 305.0447927307

		blue = cleanup(blue, 255)

		# print("{}, {}, {}, {}, ".format(red, green, blue, temp))

		return red, green, blue
