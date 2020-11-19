from climacell_api.client import ClimacellApiClient

from classes.constants import fields
from classes.constants import maxDates
from datetime import datetime

lat, lon = float('37.40834'), float('-76.54845')
key = "q2W59y2MsmBLqmxbw34QGdtS5hABEwLl"
client = ClimacellApiClient(key)

REALTIME = client.realtime(lat=lat,
						   lon=lon,
						   fields=fields.REALTIME,
						   units='us')

NOWCAST = client.nowcast(lat=lat,
						 lon=lon,
						 start_time='now',
						 end_time=maxDates.nowcast(),
						 fields=fields.NOWCAST,
						 timestep=1)

HOURLY = client.forecast_hourly(lat=lat,
								lon=lon,
								start_time=maxDates.nowcast(),
								end_time=maxDates.hourly(),
								fields=fields.HOURLY,
								units='us')

DAILY = client.forecast_daily(lat=lat,
							  lon=lon,
							  start_time=maxDates.hourly(),
							  end_time=maxDates.daily(),
							  fields=fields.DAILY,
							  units='us')
