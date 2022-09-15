from LevityDash.lib.plugins.schema import SchemaSpecialKeys as tsk
from LevityDash.lib.plugins.web import REST, URLs

__disabled__ = True

class OWMURLs(URLs, base='api.openweathermap.org/data/2.5/'):
	pass
# auth = Auth(authType=AuthType.PARAMETER, authData={'appid': config.plugins.owm.apikey})

# oneCall = Endpoint(url='onecall', protocol='https', refreshInterval=timedelta(minutes=15))


schema = {
	'timestamp':                           {'type': 'datetime', 'sourceUnit': 'epoch', 'kwargs': {'tz': '@timezone'}, 'title': 'Time', 'sourceKey': 'dt', tsk.metaData: '@timestamp'},
	'environment.temperature':             {'type': 'temperature', 'sourceUnit': 'kelvin'},
	'environment.temperature.temperature': {'title': 'Temperature', 'sourceKey': 'temp'},
	'environment.temperature.feelsLike':   {'title': 'Feels like', 'sourceKey': 'feels_like'},
	'environment.temperature.dewpoint':    {'title': 'Dew Point', 'sourceKey': 'dew_point'},

	'environment.humidity.humidity':       {'type': 'humidity', 'sourceUnit': '%', 'title': 'Humidity', 'sourceKey': 'humidity'},

	'environment.pressure':                {'type': 'pressure', 'sourceUnit': 'hPa'},
	'environment.pressure.pressure':       {'title': 'Pressure', 'sourceKey': 'pressure'},

	'environment.light.uvi':               {'type': 'index', 'sourceUnit': 'uvi', 'title': 'UV Index', 'sourceKey': 'uvi'},

	'environment.clouds.coverage':         {'type': 'cloudCover', 'sourceUnit': '%', 'title': 'Cloud coverage', 'sourceKey': 'clouds'},
	'environment.visibility':              {'type': 'distance', 'sourceUnit': 'km', 'title': 'Visibility', 'sourceKey': 'visibility'},

	'environment.wind.speed':              {'type': 'wind', 'sourceUnit': ('m', 's')},
	'environment.wind.speed.speed':        {'title': 'Wind speed', 'sourceKey': 'wind_speed'},
	'environment.wind.speed.gust':         {'title': 'Wind gust', 'sourceKey': 'wind_gust'},
	'environment.wind.direction':          {'type': 'direction', 'sourceUnit': 'deg', 'title': 'Wind direction', 'sourceKey': 'wind_deg'},

}

_defaultConfig = """[plugin] 
	enabled: false
	"""


class OpenWeatherMap(REST, realtime=True, daily=True, hourly=True, logged=False):
	__defaultConfig__ = _defaultConfig
	schema = {}
# urls = OWMURLs()

# __plugin__ = OpenWeatherMap
