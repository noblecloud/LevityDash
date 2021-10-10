from .units import unitDict


class ConditionValue:
	_description: str
	_glyph: chr

	def __init__(self, data):
		self._description = data['description']
		self._glyph = data['icon']

	def __str__(self):
		return self._description

	def __repr__(self):
		return self._glyph

	@property
	def description(self):
		return self._description

	@property
	def glyph(self) -> chr:
		return self._glyph


class ConditionInterpreter:
	_library: dict[str, dict[str, str]]

	def __getitem__(self, item):
		return ConditionValue(self._library[item])


class ClimacellConditionInterpreter(ConditionInterpreter):
	_library = {
			'rain_heavy':          {'description': 'Substantial rain', 'icon': ''},
			'rain':                {'description': 'Rain', 'icon': ''},
			'rain_light':          {'description': 'Light rain', 'icon': ''},
			'freezing_rain_heavy': {'description': 'Substantial freezing rain', 'icon': ''},
			'freezing_rain':       {'description': 'Freezing rain', 'icon': ''},
			'freezing_rain_light': {'description': 'Light freezing rain', 'icon': ''},
			'freezing_drizzle':    {'description': 'Light freezing rain falling in fine pieces', 'icon': ''},
			'drizzle':             {'description': 'Light rain falling in very fine drops', 'icon': ''},
			'ice_pellets_heavy':   {'description': 'Substantial ice pellets', 'icon': ''},
			'ice_pellets':         {'description': 'Ice pellets', 'icon': ''},
			'ice_pellets_light':   {'description': 'Light ice pellets', 'icon': ''},
			'snow_heavy':          {'description': 'Substantial snow', 'icon': ''},
			'snow':                {'description': 'Snow', 'icon': ''},
			'snow_light':          {'description': 'Light snow', 'icon': ''},
			'flurries':            {'description': 'Flurries', 'icon': ''},
			'tstorm':              {'description': 'Thunderstorm conditions', 'icon': ''},
			'fog_light':           {'description': 'Light fog', 'icon': ''},
			'fog':                 {'description': 'Fog', 'icon': ''},
			'cloudy':              {'description': 'Cloudy', 'icon': ''},
			'mostly_cloudy':       {'description': 'Mostly cloudy', 'icon': ''},
			'partly_cloudy':       {'description': 'Partly cloudy', 'icon': ''},
			'mostly_clear':        {'description': 'Mostly clear', 'icon': ''},
			'clear':               {'description': 'Clear, sunny', 'icon': ''}
	}
