import re
from dataclasses import asdict, dataclass
from datetime import timedelta
from json import loads
from math import inf
from typing import Dict, List, Optional, Union

import requests

paid: bool = False


@dataclass
class TimeFrame:
	__t = {'h': 'hours', 'm': 'minutes', 'd': 'days'}
	__regexTimeFilter = r"(?P<value>[+|-][\d|\.]*)\s?(?P<key>\w*)"
	end: timedelta
	start: timedelta
	inclusive: bool
	allowed: set

	def __init__(self, *args):
		if args:
			data = args[0]
			if isinstance(data, str):
				self.allowed = {'best', '1d', '1h', '30m', '15m', '5m', '1m', 'current'}
				self.start, self.end, self.inclusive = self.__parseFrame(data)
			elif isinstance(data, dict):
				self.allowed = data['allowed']
				self.start = data['start']
				self.end = data['end']
				self.inclusive = data['inclusive']

	@classmethod
	def __parseTimeFrame(cls, timeFrame: str) -> timedelta:
		t = cls.__t
		value, key = re.search(cls.__regexTimeFilter, timeFrame, re.DOTALL).groups()

		if key in t.keys():
			key = t[key]

		params = {key: float(value)}
		return timedelta(**params)

	def removeIncrement(self, string: str):
		self.allowed.remove(string)

	@classmethod
	def __parseFrame(cls, item: str) -> tuple[timedelta, timedelta, bool]:
		global paid
		inclusive = item[0] == '['
		item = item.strip('[]()')

		item = item.replace('for free, up to', '|').replace('for paying accounts', '')
		if ',' in item:
			start, end = item.replace(' ', '').split(',')
			start = start.split('|')
			start = start[1] if paid else start[0]
			start = cls.__parseTimeFrame(start)
		else:
			end = item
			start = timedelta(0)
		end = cls.__parseTimeFrame(end)
		return start, end, inclusive

	def __contains__(self, other: Union[timedelta, int, str]):
		if isinstance(other, str):
			return other in self.allowed
		if self.inclusive:
			return self.start <= other <= self.end
		return self.start < other < self.end


@dataclass
class Interface:
	timeframe: bool
	event: bool
	map: bool
	route: bool

	def __init__(self, *args):
		if args:
			data = args[0]
			if isinstance(data, str):
				string = data.split(' ')
				self.timeframe = 'T' in string
				self.event = 'E' in string
				self.map = 'M' in string
				self.route = 'R' in string
			if isinstance(data, dict):
				self.timeframe = data['timeframe']
				self.event = data['event']
				self.map = data['map']
				self.route = data['route']


@dataclass
class Suffix:
	min: bool
	max: bool
	average: bool
	time: bool

	def __init__(self, *args):
		if args:
			data = args[0]
			if isinstance(data, str):
				self.min = '∧' in data
				self.max = '∨' in data
				self.average = '~' in data
				self.time = '⧖' in data
			else:
				self.min = data['min']
				self.max = data['max']
				self.average = data['average']
				self.time = data['time']


@dataclass
class Area:
	value: str


@dataclass
class Field:
	name: str
	description: str
	timeframe: Optional[TimeFrame]
	interface: Optional[Interface]
	suffix: Optional[Suffix]
	area: Optional[Area]
	units: dict

	def __init__(self, *args, **kwargs):
		if args:
			data = args[0]
			if isinstance(data, list):
				name, units, parameters = data
				self.name, self.description = [i.strip('`') for i in name.split('\n\n')][:2]
				self.units = Units(units, self.name)

				parameters = {k: v for k, v in [i.split(': ') for i in parameters.split('\n')[:4] if i and not i.endswith(':')]}

				def valueOrEmpty(i):
					if i in parameters:
						return parameters[i]
					return ''

				self.timeframe = TimeFrame(valueOrEmpty('F'))
				if 'I' in parameters:
					self.interface = Interface(valueOrEmpty('I'))
				else:
					self.interface = Interface(valueOrEmpty('D'))
				self.area = Area(valueOrEmpty('A'))
				self.suffix = Suffix(valueOrEmpty('S'))

			elif isinstance(data, dict):
				self.name = data['name']
				self.description = data['description']
				self.timeframe = TimeFrame(data['timeframe'])
				self.interface = Interface(data['interface'])
				self.suffix = Suffix(data['suffix'])
				self.area = Area(data['area']['value'])
				self.units = None

	def __hash__(self):
		return self.name.__hash__()


def floatOrInt(value: str) -> Union[float, int, str]:
	if not value.isalpha():
		value = float(value)
		if value.is_integer():
			value = int(value)
		return value
	else:
		return str(value)


@dataclass
class Range:
	min: Union[float, int]
	max: Union[float, int]

	def __init__(self, value: Union[str, float]):
		if value == inf:
			self.min = inf
			self.max = inf
		else:
			item = value.strip('([])')
			if '-' in item or ',' in item:
				self.min, self.max = self.__minMax(*[floatOrInt(i) for i in item.split('-' if '-' in item else ',')])
			elif '>' in item:
				self.min = floatOrInt(item.strip('>'))
				self.max = inf
			elif '<' in item:
				self.max = floatOrInt(item.strip('<'))
				self.min = -inf

	@staticmethod
	def __minMax(a, b):
		return (a, b) if (a < b) else (b, a)


class GetAttr(type):
	def __getitem__(cls, x: Union[str, int]):
		return getattr(cls, x)


# class Index(Enum):
# 	__metaclass__ = GetAttr


@dataclass
class System:
	metric: str
	imperial: str

	def __init__(self, value: Union[List, str]):
		self.metric, self.imperial = value


class Units:

	@staticmethod
	def parseIndexValues(item: str) -> Union[str, Dict[str, str]]:
		if '(' in item:
			i = item.index('(')
			return item[:i - 1]
		else:
			return item

	def __new__(cls, item: str, name: str):
		# System or Index
		if '\n' in item:
			item = [i for i in item.split('\n') if i]
			# System
			if len(item) == 2:
				return System(item)

			# Index
			else:
				print()
				# item = {cls.parseIndexValues(v): floatOrInt(k) if k.isnumeric() else k for k, v in [i.split(': ') for i in item]}
				d = {}
				for i in [i.split(': ') for i in item]:
					k, v = i[0], i[1]
					k = floatOrInt(k) if k.isnumeric() else k
					v = cls.parseIndexValues(v)
					d[v] = k
					name = name[0].upper() + name[1:]
				return d
		# return Enum(name, item, qualname=f'TomorrowIO.{name}')

		# Range
		elif 'ISO' in item:
			return item
		elif '-' in item or ',' in item:
			return Range(item)

		# String
		else:
			return item.split(' ')[0]


class FieldSet(set):

	def __str__(self):
		return ','.join([i.name.strip() for i in self])

	def __repr__(self):
		return str(self)


import os


class Fields:
	os.path.dirname(os.path.abspath(__file__))
	_path: str = f"{os.path.dirname(os.path.abspath(__file__))}/fields.pickle"
	_layers: Dict[str, Dict[str, Field]]

	def __init__(self, **kwargs):
		if 'path' in kwargs.keys():
			self._path = kwargs['path']
			self.load()
		elif 'values' in kwargs.keys():
			self._layers: Dict[str, Dict[str, Field]] = kwargs['values']
		else:
			self.load()

	def __getitem__(self, item: str) -> Union[Field, FieldSet]:
		if item in self._layers:
			return FieldSet(self._layers[item].values())
		elif item in (allF := self.allFields):
			return allF[item]
		else:
			raise KeyError(f"Unknown field: {item}")

	def __contains__(self, item: str):
		inSuper = super(Fields, self).__contains__(item)
		if inSuper:
			return inSuper
		else:
			return item in self.allFields

	def fixError(self, message: str):
		for i in message.split('\n')[1:]:
			if 'timestep' in i:
				self.removeFieldTimeStep(i)
		self.save()

	def load(self, path: Optional[str] = None):
		if path is None:
			path = self._path
		from pickle import load
		with open(path, 'rb') as f:
			layers = load(f, fix_imports=True)
			self._layers = {k: {kk: Field(vv) for kk, vv in v.items()} for k, v in layers.items()}

	def save(self, filename: Optional[str] = None):
		from pickle import dump
		filename = filename if filename is not None else 'fields.pickle'
		a = {k: {kk: asdict(vv) for kk, vv in v.items()} for k, v in self._layers.items()}
		with open(filename, 'wb') as f:
			dump(a, f, fix_imports=True)

	def removeFieldTimeStep(self, error):
		field = error[(start := error.find('The field') + 10):error.find(' ', start)]
		timeframe = error.split(' ')[-1]
		self[field].timeframe.allowed.discard(timeframe)

	@property
	def allFields(self) -> dict[str, Field]:
		a = {}
		for group in self._layers.values():
			for item in group.values():
				a[item.name.strip()] = item
		return a

	@property
	def layers(self) -> list[str]:
		return list(self._layers.keys())

	@layers.setter
	def layers(self, value):
		self._layers = value

	def withinTime(self, end: timedelta, start: timedelta = timedelta(0)) -> FieldSet:
		fields = FieldSet()
		for group in self._layers.values():
			for item in group.values():
				if end in item.timeframe:
					fields.add(item)
		return fields

	def allowedTimeStep(self, timestep: str) -> FieldSet:
		fields = FieldSet()
		for item in self.allFields.values():
			if timestep in item.timeframe:
				fields.add(item)
		return fields

	def get(self, **params):
		l: List[FieldSet] = []
		wantedFields = FieldSet()

		if 'params' in params:
			params.update(params.pop('params'))

		if 'end' in params.keys():
			l.append(self.withinTime(params['end']))
		if 'timesteps' in params.keys():
			steps = [s for s in params['timesteps'].split(',') if s]
			for step in steps:
				l.append(self.allowedTimeStep(step))
		if 'layer' in params.keys():
			wantedFields.add(self[params['layer']])
		if (layers := params.get('layers'), None) is not None:
			if isinstance(layers, list):
				for layer in layers:
					wantedFields.update(self[layer])
			else:
				raise TypeError("Layers must be list of strings")

		if 'fields' in params:
			fields = params['fields']
			if isinstance(fields, str):
				fields = fields.split(',')
			wantedFields.update(fields)
		elif l:
			wantedFields = FieldSet(l.pop(0))

		if l:
			for i in l:
				wantedFields.intersection_update(i)

		if 'apikey' in params:
			return [i.name.strip() for i in wantedFields]

		return wantedFields


if __name__ == '__main__':
	# layers = {
	# 		'core':          'https://docs.tomorrow.io/reference/data-layers-core',
	# 		'air':           'https://docs.tomorrow.io/reference/data-layers-air',
	# 		'fire':          'https://docs.tomorrow.io/reference/data-layers-air',
	# 		'land':          'https://docs.tomorrow.io/reference/land',
	# 		'lightning':     'https://docs.tomorrow.io/reference/lightning',
	# 		'maritime':      'https://docs.tomorrow.io/reference/maritime',
	# 		'pollen':        'https://docs.tomorrow.io/reference/data-layers-pollen',
	# 		'precipitation': 'https://docs.tomorrow.io/reference/data-layers-precipitation',
	# 		'solar':         'https://docs.tomorrow.io/reference/solar'
	# }
	#
	# data = {
	# 		"data": {
	# 				"h-0":  "Field",
	# 				"h-1":  "[Values](https://docs.tomorrow.io/reference-link/data-layers-overview#field-descriptors) (Metric, Imperial)",
	# 				"0-0":  "`temperature`\n\nThe real temperature measurement (at 2m)",
	# 				"1-0":  "`temperatureApparent`\n\nThe temperature equivalent perceived by humans, caused by the combined effects of air temperature, relative humidity, and wind speed (at 2m)",
	# 				"2-0":  "`dewPoint`\n\nThe temperature to which air must be cooled to become saturated with water vapor (at 2m)",
	# 				"3-0":  "`humidity`\n\nThe concentration of water vapor present in the air",
	# 				"4-0":  "`windSpeed`\n\nThe fundamental atmospheric quantity caused by air moving from high to low pressure, usually due to changes in temperature (at 10m)",
	# 				"5-0":  "`windDirection`\n\nThe direction from which it originates, measured in degrees clockwise from due north (at 10m)",
	# 				"6-0":  "`windGust`\n\nThe maximum brief increase in the speed of the wind, usually less than 20 seconds (at 10m)",
	# 				"7-0":  "`pressureSurfaceLevel`\n\nThe force exerted against a surface by the weight of the air above the surface (at the surface level)",
	# 				"8-0":  "`pressureSeaLevel`\n\nThe force exerted against a surface by the weight of the air above the surface (at the mean sea level)",
	# 				"9-0":  "`precipitationIntensity`\n\nThe amount of precipitation that falls over time, covering the ground in a period of time",
	# 				"10-0": "`precipitationProbability`\n\nThe chance of precipitation that at least some minimum quantity of precipitation will occur within a specified forecast period and location",
	# 				"11-0": "`precipitationType`\n\nThe various types of precipitation often include the character or phase of the precipitation which is falling to ground level (Schuur classification)",
	# 				"16-0": "`sunsetTime`\n\nThe daily disappearance of the Sun below the horizon due to Earth\'s rotation",
	# 				"17-0": "`solarGHI `\n\nThe total amount of shortwave radiation received from above by a surface horizontal to the ground",
	# 				"15-0": "`sunriseTime`\n\nThe daily appearance of the Sun on the horizon due to Earth\'s rotation",
	# 				"18-0": "`visibility`\n\nThe measure of the distance at which an object or light can be clearly discerned",
	# 				"19-0": "`cloudCover`\n\nThe fraction of the sky obscured by clouds when observed from a particular location",
	# 				"20-0": "`cloudBase`\n\nThe lowest altitude of the visible portion of a cloud (above ground level)",
	# 				"21-0": "`cloudCeiling`\n\nThe highest altitude of the visible portion of a cloud (above ground level)",
	# 				"22-0": "`moonPhase`\n\nThe shape of the directly sunlit portion of the Moon as viewed from Earth",
	# 				"25-0": "`weatherCode`\n\nThe text description that conveys the most prominent weather condition",
	# 				"25-1": "0: Unknown\n1000: Clear\n1001:  Cloudy\n1100: Mostly Clear\n1101: Partly Cloudy\n1102: Mostly Cloudy\n2000: Fog\n2100: Light Fog\n3000: Light Wind\n3001: Wind\n3002: Strong Wind\n4000: Drizzle\n4001: Rain\n4200: Light Rain\n4201: Heavy Rain\n5000: Snow\n5001: Flurries\n5100: Light Snow\n5101: Heavy Snow\n6000: Freezing Drizzle\n6001: Freezing Rain\n6200: Light Freezing Rain\n6201: Heavy Freezing Rain\n7000: Ice Pellets\n7101: Heavy Ice Pellets\n7102: Light Ice Pellets\n8000: Thunderstorm",
	# 				"22-1": "0: New (0.0625-0.9375)\n1: Waxing Crescent (0.0625-0.1875)\n2: First Quarter (0.1875-0.3125)\n3: Waxing Gibbous (0.3125-0.4375)\n4: Full (0.4375-0.5625)\n5: Waning Gibbous (0.5625-0.6875)\n6: Third Quarter (0.6875-0.8125)\n7: Waning Crescent (0.8125-0.9375)",
	# 				"21-1": "km  or null\nmi or null",
	# 				"20-1": "km or null\nmi or null",
	# 				"19-1": "%",
	# 				"18-1": "km\nmi",
	# 				"17-1": "W/m^2\nBtu/ft^2",
	# 				"16-1": "UTC ISO-8601",
	# 				"15-1": "UTC ISO-8601",
	# 				"11-1": "0: N/A \n1: Rain\n2: Snow\n3: Freezing Rain\n4: Ice Pellets",
	# 				"10-1": "%",
	# 				"9-1":  "mm/hr\nin/hr",
	# 				"8-1":  "hPa\ninHg",
	# 				"7-1":  "hPa\ninHg",
	# 				"6-1":  "m/s\nmph",
	# 				"5-1":  "degrees or null",
	# 				"4-1":  "m/s\nmph",
	# 				"3-1":  "%",
	# 				"2-1":  "Celsius [0,100]\nFahrenheit",
	# 				"1-1":  "Celsius [-90,60]\nFahrenheit",
	# 				"0-1":  "Celsius [-90,60]\nFahrenheit",
	# 				"h-2":  "[Availability](https://docs.tomorrow.io/reference-link/data-layers-overview#field-availability)",
	# 				"h-3":  "Map",
	# 				"9-3":  "",
	# 				"9-2":  "F: [-6 h for free, up to -48h for paying accounts, +15d]\nI: T E M R (map from 6h back to 6h out)\nA: WW\nS: ∧ ∨ ~ ⧖\n\n![precip-si](https://files.readme.io/fabcf3d-weather-precipitation-sample.png)\n\n![precip-si](https://files.readme.io/d3c3987-precipitation-si-spectrum.png)\n![precip-us](https://files.readme.io/7e4fe00-precipitation-us-spectrum.png)",
	# 				"0-2":  "F: [-6 h for free, up to -48h for paying accounts, +15d]\nI: T E M R\nA: WW\nS: ∧ ∨ ~ ⧖\n\n![temperature](https://files.readme.io/0b2763f-weather-temperature-sample.png)\n\n![temperature-si](https://files.readme.io/e19fcb3-temperature-si-spectrum.png)\n![temperature-us](https://files.readme.io/f68d431-temperature-us-spectrum.png)",
	# 				"4-2":  "F: [-6 h for free, up to -48h for paying accounts, +15d]\n\nI: T E M R\nA: WW\nS: ∧ ∨ ~ ⧖\n\n![wind-speed](https://files.readme.io/c231f99-weather-wind-speed-sample.png)\n\n![wind-speed-si](https://files.readme.io/e8317b1-wind-speed-si-spectrum.png)\n![wind-speed-us](https://files.readme.io/08756c3-wind-speed-us-spectrum.png)",
	# 				"5-2":  "F: [-6 h for free, up to -48h for paying accounts, +15d]\nI: T E M R\nA: WW\nS: \n\n![wind-direction](https://files.readme.io/990c7f3-weather-wind-direction-sample.png)\n\n![wind-direction](https://files.readme.io/bf5392a-wind-direction-spectrum.png)",
	# 				"6-2":  "F: [-6 h for free, up to -48h for paying accounts, +15d]\nI: T E M R\nA: WW\nS: ∧ ∨ ~ ⧖\n\n![wind-gust](https://files.readme.io/9bc8317-weather-wind-gust-sample.png)\n\n![wind-gust-si](https://files.readme.io/4aa5c43-weather-wind-gust-si-legend.png)\n![wind-gust-us](https://files.readme.io/2fb88cd-weather-wind-gust-us-legend.png)",
	# 				"18-2": "F: [-6 h for free, up to -48h for paying accounts, +15d]\nI: T E M R\nA: WW\nS: ∧ ∨ ~ ⧖\n\n![visibility](https://files.readme.io/c64b19c-weather-visibility-sample.png)\n\n![visibility-si](https://files.readme.io/8f1ec52-visibility-si-spectrum.png)\n![visibility-us](https://files.readme.io/f686a0f-visibility-us-spectrum.png)",
	# 				"2-2":  "F: [-6 h for free, up to -48h for paying accounts, +15d]\nI: T E M R\nA: WW\nS: ∧ ∨ ~ ⧖\n\n![dewpoint](https://files.readme.io/bcda574-weather-dewpoint-sample.png)\n\n![dewpoint-si](https://files.readme.io/88969f0-dewpoint-si-spectrum.png)\n![dewpoint-us](https://files.readme.io/5993af6-dewpoint-us-spectrum.png)",
	# 				"8-2":  "F: [-6 h for free, up to -48h for paying accounts, +15d]\nI: T M R\nA: WW\nS: ∧ ∨ ~ ⧖\n\n![pressure](https://files.readme.io/537b3b2-weather-pressure-sample.png)\n\n![pressure-si](https://files.readme.io/81206f5-pressure-si-spectrum.png)\n![pressure-us](https://files.readme.io/4158b02-pressure-us-spectrum.png)",
	# 				"3-2":  "F: [-6 h for free, up to -48h for paying accounts, +15d]\nI: T E M R\nA: WW\nS: ∧ ∨ ~ ⧖\n\n![humidity](https://files.readme.io/ae87ced-weather-humidity-sample.png)\n\n![humidity](https://files.readme.io/70de95d-humidity-spectrum.png)",
	# 				"19-2": "F: [-6 h for free, up to -48h for paying accounts, +15d]\nI: T E M R\nA: WW\nS: ∧ ∨ ~ ⧖\n\n![cloud-cover](https://files.readme.io/ed6a069-weather-cloud-cover-sample.png)\n\n![cloud-cover](https://files.readme.io/168dd28-cloud-cover-spectrum.png)",
	# 				"20-2": "F: [-6 h for free, up to -48h for paying accounts, +15d]\nI: T E M R\nA: WW\nS: ∧ ∨ ~ ⧖\n\n![cloud-base](https://files.readme.io/9d6a48c-weather-cloud-base-sample.png)\n\n![cloud-base-si](https://files.readme.io/bbbd913-cloud-base-si-spectrum.png)\n![cloud-base-us](https://files.readme.io/a6a3618-cloud-base-us-spectrum.png)",
	# 				"21-2": "F: [-6 h for free, up to -48h for paying accounts, +15d]\nI: T E M R\nA: WW\nS: ∧ ∨ ~ ⧖\n\n![cloud-ceiling](https://files.readme.io/377c7a1-weather-cloud-ceiling-sample.png)\n\n![cloud-ceiling-si](https://files.readme.io/2f87e43-cloud-ceiling-si-spectrum.png)\n![cloud-ceiling-us](https://files.readme.io/2b01058-cloud-ceiling-us-spectrum.png)",
	# 				"1-2":  "F: [-6 h for free, up to -48h for paying accounts, +15d]\nI: T E M R\nA: WW\nS: ∧ ∨ ~ ⧖",
	# 				"7-2":  "F: [-6 h for free, up to -48h for paying accounts, +15d]\nI: T E R\nA: WW\nS: ∧ ∨ ~ ⧖",
	# 				"10-2": "F: [-6 h for free, up to -48h for paying accounts, +15d]\nI: T R\nA: WW\nS: ∧ ∨ ~ ⧖",
	# 				"11-2": "F: [-6 h for free, up to -48h for paying accounts, +15d]\nI: T E R\nA: WW\nS: ∧ ∨ ~ ⧖",
	# 				"15-2": "F: [-6 h for free, up to -48h for paying accounts, +15d]\nI: T E\nA: WW\nS: ∧ ∨ ~",
	# 				"16-2": "F: [-6 h for free, up to -48h for paying accounts, +15d]\nI: T E\nA: WW\nS: ∧ ∨ ~",
	# 				"17-2": "F: [-6 h for free, up to -48h for paying accounts, +15d]\nI: T E R\nA: WW\nS: ∧ ∨ ~ ⧖",
	# 				"22-2": "F: [-6 h for free, up to -48h for paying accounts, +15d]\nI: T\nA: WW\nS: ∧ ∨ ~",
	# 				"25-2": "F: [-6 h for free, up to -48h for paying accounts, +15d]\nI: T R\nA: WW\nS: ∧ ∨ ⧖",
	# 				"13-0": "`snowAccumulation`\n\nThe trailing amount of new snowfall that has or will have occurred over the last hour of the requested time",
	# 				"13-1": "mm\nin",
	# 				"13-2": "F: [-6 h for free, up to -48h for paying accounts, +15d]\nD: T \nA: WW\nS: ∧ ∨ ~ ⧖",
	# 				"14-0": "`iceAccumulation`\n\nThe trailing amount of ice that that has or will have occurred over the last hour of the requested time",
	# 				"14-1": "mm\nin",
	# 				"14-2": "F: [-6 h for free, up to -48h for paying accounts, +15d]\nD: T \nA: WW\nS: ∧ ∨ ~ ⧖",
	# 				"23-0": "`uvIndex`\n\nStandard measurement of the strength of sunburn producing UV radiation at a particular place and time.",
	# 				"24-0": "`uvHealthConcern `\n\nWhen the predicted UV index is within these numerical ranges, the recommended need for protection is indicated by the qualitative description of the values.",
	# 				"23-2": "F: [-6 h for free, up to -48h for paying accounts, +15d]\nD: T \nA: WW\nS: ∧ ∨ ~ ⧖",
	# 				"24-2": "F: [-6 h for free, up to -48h for paying accounts, +15d]\nD: T \nA: WW\nS: ∧ ∨ ~ ⧖",
	# 				"23-1": "0-2: Low\n3-5: Moderate\n6-7: High\n8-10: Very High\n11+: Extreme",
	# 				"24-1": "0-2: Low\n3-5: Moderate\n6-7: High\n8-10: Very High\n11+: Extreme",
	# 				"12-0": "`rainAccumulation`\n\nThe amount of liquid rain that has occurred or will have occurred within a given timeframe.",
	# 				"12-2": "F: [+4.5 days]\nD: T \nA: WW\nS: ∧ ∨ ~ ⧖",
	# 				"12-1": "mm\nin"
	# 		},
	# 		"cols": 3,
	# 		"rows": 26
	# }
	# rows, cols, data = data['rows'], data['cols'], data['data']
	#
	# from datetime import timedelta
	#
	# v = {'name':        'temperature',
	#      'description': 'The "real" temperature measurement (at 2m)',
	#      'timeframe':   {'end':       timedelta(days=15),
	#                      'start':     timedelta(days=-1, seconds=64800),
	#                      'inclusive': True,
	#                      'allowed':   {'15m', '1d', '1h', '1m', '30m', '5m', 'best', 'current'}},
	#      'interface':   {'timeframe': True, 'event': True, 'map': True, 'route': True},
	#      'suffix':      {'min': True, 'max': True, 'average': True, 'time': True},
	#      'area':        {'value': 'WW'},
	#      'units':       {'metric': 'Celsius [-90,60]', 'imperial': 'Fahrenheit'}}
	#
	# f = Field(v)
	# print(f)
	#
	# values = {}
	# for row in range(rows):
	# 	v = Field([data[f'{row}-{col}'] for col in range(cols)])
	#
	# for name, value in layers.items():
	#
	# 	soup = BeautifulSoup(requests.get(value).content, "html.parser")
	# 	data = loads(soup.find(id='readme-data-docs')['data-json'])[0]['body']
	# 	start = data.find('[block:parameters]') + 18
	# 	end = data.find('[/block]', start)
	# 	data = loads(data[start:end])
	# 	rows, cols, data = data['rows'], data['cols'], data['data']
	#
	# 	values = {}
	# 	for row in range(rows):
	# 		itemData = [data[f'{row}-{col}'] for col in range(cols)]
	# 		if itemData[0].count('`') > 4:
	# 			split = itemData[0].split('\n')
	# 			des = str(split[-1])
	# 			names = split[:-2]
	# 			for i in names:
	# 				itemData[0] = f'{i}\n\n{des}'
	# 				v = Field(itemData)
	# 				values[v.name] = v
	# 		else:
	# 			v = Field(itemData)
	# 			values[v.name] = v
	# 	layers[name] = values
	# 	pass

	# for a in ['best', '1d', '1h', '30m', '15m', '5m', '1m', 'current']:

	fa = Fields()
	fa.load()

	url = "https://api.tomorrow.io/v4/timelines"
	params = {
			"location":  "37.409121118319156, -76.54907590734848",
			"fields":    None,
			"timesteps": "5m",
			"apikey":    "DALOZbzLA2WwWHKAIuvcAP5swaSaKm76",
	}

	f = list(fa.allFields)
	n = 50
	f = [f[i * n:(i + 1) * n] for i in range((len(f) + n - 1) // n)]
	f = [','.join(i) for i in f]

	for i in f:
		params['fields'] = i
		data = requests.get("https://api.tomorrow.io/v4/timelines", params=params)
		if data.status_code == 400:
			fa.fixError(data.json()['message'])

	print(fa)
