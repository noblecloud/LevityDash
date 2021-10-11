from src.observations import ObservationRealtime


class AWObservationRealtime(ObservationRealtime):
	subscriptionChannel = 'AmbientWeather'
	_indoorOutdoor = True
	_translator = {
			'time':                {'type': 'datetime', 'unit': 'epoch', 'title': 'Time', 'sourceKey': 'dateutc'},
			'temperature':         {'type': 'temperature', 'unit': 'f', 'title': 'Temperature', 'sourceKey': 'tempf'},
			'temperatureIndoor':   {'type': 'temperature', 'unit': 'f', 'title': 'Temperature', 'sourceKey': 'tempinf'},
			'dewpoint':            {'type': 'temperature', 'unit': 'f', 'title': 'Dewpoint', 'sourceKey': 'dewPoint'},
			'dewpointIndoor':      {'type': 'temperature', 'unit': 'f', 'title': 'Dewpoint', 'sourceKey': 'dewPointin'},
			'feelsLike':           {'type': 'temperature', 'unit': 'f', 'title': 'Feels Like', 'sourceKey': 'feelsLike'},
			'feelsLikeIndoor':     {'type': 'temperature', 'unit': 'f', 'title': 'Feels Like', 'sourceKey': 'feelsLikein'},
			'humidity':            {'type': 'humidity', 'unit': '%', 'title': 'Humidity', 'sourceKey': 'humidity'},
			'humidityIndoor':      {'type': 'humidity', 'unit': '%', 'title': 'Humidity', 'sourceKey': 'humidityin'},
			'uvi':                 {'type': 'index', 'unit': 'int', 'title': 'UVI', 'sourceKey': 'uv'},
			'irradiance':          {'type': 'irradiance', 'unit': 'W/m^2', 'title': 'Irradiance', 'sourceKey': 'solarradiation'},
			'illuminance':         {'type': 'illuminance', 'unit': 'lux', 'title': 'Illuminance', 'sourceKey': 'brightness'},
			'pressure':            {'type': 'pressure', 'unit': 'inHg', 'title': 'Pressure', 'sourceKey': 'baromrelin'},
			'absolute':            {'type': 'pressure', 'unit': 'inHg', 'title': 'Absolute Pressure', 'sourceKey': 'baromabsin'},
			'windDirection':       {'type': 'direction', 'unit': 'º', 'title': 'Wind Direction', 'sourceKey': 'winddir'},
			'windSpeed':           {'type': 'wind', 'unit': ['mi', 'hr'], 'title': 'Wind Speed', 'sourceKey': 'windspeedmph'},
			'gustSpeed':           {'type': 'wind', 'unit': ['mi', 'hr'], 'title': 'Gust Speed', 'sourceKey': 'windgustmph'},
			'maxSpeed':            {'type': 'wind', 'unit': ['mi', 'hr'], 'title': 'Max Wind Speed', 'sourceKey': 'maxdailygust'},
			'precipitationHourly': {'type': 'precipitationHourly', 'unit': ['in', 'hr'], 'title': 'Rain Rate', 'sourceKey': 'hourlyrainin'},
			'precipitationDaily':  {'type': 'precipitationDaily', 'unit': ['in', 'day'], 'title': 'Daily Rain', 'sourceKey': 'dailyrainin'},
			'precipitationEvent':  {'type': 'precipitation', 'unit': 'in', 'title': 'Event Rain', 'sourceKey': 'eventrainin'},
			'precipitationTotal':  {'type': 'precipitation', 'unit': 'in', 'title': 'Total Rain', 'sourceKey': 'totalrainin'},
			'precipitationLast':   {'type': 'date', 'unit': 'ISO8601', 'format': '%Y-%m-%dT%H:%M:%S.000Z', 'title': 'Last Rain', 'sourceKey': 'lastRain'}}

	def __init__(self, *args, **kwargs):
		super(AWObservationRealtime, self).__init__(*args, **kwargs)
