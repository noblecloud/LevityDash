from src.observations import ObservationRealtime


class AWObservationRealtime(ObservationRealtime):
	subscriptionChannel = 'AmbientWeather'
	category = 'environment'
	_indoorOutdoor = True
	_translator = {
		'time.time':                            {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Time', 'sourceKey': 'dateutc'},
		'time.date':                            {'type': 'datetime', 'sourceUnit': 'ISO8601', 'format': '%Y-%m-%dT%H:%M:%S.000Z', 'title': 'Date', 'sourceKey': 'date'},
		'time.timezone':                        {'type': 'timezone', 'sourceUnit': 'tz', 'title': 'Time Zone', 'sourceKey': 'tz'},
		'environment.temperature.temperature':  {'type': 'temperature', 'sourceUnit': 'f', 'title': 'Temperature', 'sourceKey': 'tempf'},
		'environment.temperature.dewpoint':     {'type': 'temperature', 'sourceUnit': 'f', 'title': 'Dewpoint', 'sourceKey': 'dewPoint'},
		'environment.temperature.feelsLike':    {'type': 'temperature', 'sourceUnit': 'f', 'title': 'Feels Like', 'sourceKey': 'feelsLike'},
		'environment.humidity':                 {'type': 'humidity', 'sourceUnit': '%', 'title': 'Humidity', 'sourceKey': 'humidity'},
		'indoor.temperature.temperature':       {'type': 'temperature', 'sourceUnit': 'f', 'title': 'Temperature', 'sourceKey': 'tempinf'},
		'indoor.temperature.dewpoint':          {'type': 'temperature', 'sourceUnit': 'f', 'title': 'Dewpoint', 'sourceKey': 'dewPointin'},
		'indoor.temperature.feelsLike':         {'type': 'temperature', 'sourceUnit': 'f', 'title': 'Feels Like', 'sourceKey': 'feelsLikein'},
		'indoor.humidity':                      {'type': 'humidity', 'sourceUnit': '%', 'title': 'Humidity', 'sourceKey': 'humidityin'},
		'environment.light.uvi':                {'type': 'index', 'sourceUnit': 'int', 'title': 'UVI', 'sourceKey': 'uv'},
		'environment.light.irradiance':         {'type': 'irradiance', 'sourceUnit': 'W/m^2', 'title': 'Irradiance', 'sourceKey': 'solarradiation'},
		'environment.light.illuminance':        {'type': 'illuminance', 'sourceUnit': 'lux', 'title': 'Illuminance', 'sourceKey': 'brightness'},
		'environment.pressure.pressure':        {'type': 'pressure', 'sourceUnit': 'inHg', 'title': 'Pressure', 'sourceKey': 'baromrelin'},
		'environment.pressure.absolute':        {'type': 'pressure', 'sourceUnit': 'inHg', 'title': 'Absolute Pressure', 'sourceKey': 'baromabsin'},
		'environment.wind.direction.direction': {'type': 'direction', 'sourceUnit': 'º', 'title': 'Wind Direction', 'sourceKey': 'winddir'},
		'environment.wind.speed.speed':         {'type': 'wind', 'sourceUnit': ['mi', 'hr'], 'title': 'Wind Speed', 'sourceKey': 'windspeedmph'},
		'environment.wind.speed.gust':          {'type': 'wind', 'sourceUnit': ['mi', 'hr'], 'title': 'Gust Speed', 'sourceKey': 'windgustmph'},
		'environment.wind.speed.max':           {'type': 'wind', 'sourceUnit': ['mi', 'hr'], 'title': 'Max Wind Speed', 'sourceKey': 'maxdailygust'},
		'environment.precipitation.hourly':     {'type': 'precipitationHourly', 'sourceUnit': ['in', 'hr'], 'title': 'Rain Rate', 'sourceKey': 'hourlyrainin'},
		'environment.precipitation.daily':      {'type': 'precipitationDaily', 'sourceUnit': ['in', 'day'], 'title': 'Daily Rain', 'sourceKey': 'dailyrainin'},
		'environment.precipitation.weekly':     {'type': 'precipitationDaily', 'sourceUnit': ['in', 'week'], 'title': 'Daily Rain', 'sourceKey': 'weeklyrainin'},
		'environment.precipitation.monthly':    {'type': 'precipitationDaily', 'sourceUnit': ['in', 'month'], 'title': 'Daily Rain', 'sourceKey': 'monthlyrainin'},
		'environment.precipitation.event':      {'type': 'precipitation', 'sourceUnit': 'in', 'title': 'Event Rain', 'sourceKey': 'eventrainin'},
		'environment.precipitation.total':      {'type': 'precipitation', 'sourceUnit': 'in', 'title': 'Total Rain', 'sourceKey': 'totalrainin'},
		'environment.precipitation.last':       {'type': 'date', 'sourceUnit': 'ISO8601', 'format': '%Y-%m-%dT%H:%M:%S.000Z', 'title': 'Last Rain', 'sourceKey': 'lastRain'}}

	def __init__(self, *args, **kwargs):
		super(AWObservationRealtime, self).__init__(*args, **kwargs)
