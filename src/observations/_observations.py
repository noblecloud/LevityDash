import logging
from datetime import datetime, timedelta
from operator import attrgetter
from typing import Any, Dict, Iterable, List, Optional, Tuple, Type, Union, TYPE_CHECKING

import numpy as np
import WeatherUnits as wu
from dateutil.parser import parse, parser
from PySide2.QtCore import Signal
from pytz import timezone
from WeatherUnits import Measurement
from WeatherUnits.base import DerivedMeasurement

from src import config
from src.translators import unitDict
from src.utils import closest, ForecastSignalDispatcher, ISOduration, NewKeyDispatcher, ObservationUpdateHandler

tz = config.tz

log = logging.getLogger(__name__)

__all__ = ['ObservationDict', 'Observation', 'ObservationRealtime', 'ObservationForecast', 'MeasurementForecast']


class DateKey(int):
	_datetime: datetime

	def __init__(self, value: Union[datetime, int, str]):
		if isinstance(value, str):
			value = int(value)
		if isinstance(value, int):
			self._datetime = datetime.fromtimestamp(value, tz=config.tz)
		elif isinstance(value, datetime):
			self._datetime = value
		int.__init__(int(self._datetime.timestamp()))

	def __repr__(self):
		delta: timedelta = self._datetime - datetime.now(tz=self._datetime.tzinfo)
		a: wu.Time = wu.Time.Second(int(delta.total_seconds()))
		return f'+{a.hour}'

	def __getattr__(self, attr):
		try:
			return getattr(self, attr)
		except AttributeError:
			pass
		try:
			return getattr(self._datetime, attr)
		except AttributeError:
			pass
		return getattr(self, attr)

	@property
	def datetime(self) -> datetime:
		return self._datetime

	@property
	def second(self):
		return self._datetime.second

	@property
	def minute(self):
		return self._datetime.minute

	@property
	def hour(self):
		return self._datetime.hour

	@property
	def day(self):
		return self._datetime.day

	@property
	def month(self):
		return self._datetime.month

	@property
	def year(self):
		return self._datetime.year

	@property
	def tzinfo(self):
		return self._datetime.tzinfo

	def __gt__(self, other):
		if isinstance(other, datetime):
			return self._datetime > other
		else:
			return super(DateKey, self).__gt__(other)

	def __eq__(self, other):
		if isinstance(other, datetime):
			return self._datetime == other
		else:
			return super(DateKey, self).__eq__(other)

	def __lt__(self, other):
		if isinstance(other, datetime):
			return self._datetime < other
		else:
			return super(DateKey, self).__lt__(other)

	def __le__(self, other):
		if isinstance(other, datetime):
			return self._datetime <= other
		else:
			return super(DateKey, self).__le__(other)

	def __ge__(self, other):
		if isinstance(other, datetime):
			return self._datetime >= other
		else:
			return super(DateKey, self).__ge__(other)

	def __hash__(self):
		return int.__hash__(self)


class ObservationDict(dict):
	_api: 'API'
	_time: datetime

	def __init__(self, api: 'API', *args, **kwargs):
		self._api = api
		super(ObservationDict, self).__init__()

	@property
	def period(self) -> timedelta:
		return timedelta(seconds=0)

	@property
	def timeframe(self) -> timedelta:
		return timedelta(seconds=0)

	@property
	def isForecast(self) -> bool:
		return self.timeframe >= timedelta(minutes=30)

	@property
	def isRealtime(self) -> bool:
		return self.period.total_seconds() == 0


class Observation(ObservationDict):
	unitDict = unitDict
	_translator: dict

	def __init__(self, *args, **kwargs):
		super(Observation, self).__init__(*args, **kwargs)
		if args:
			self.update(*args)

	def update(self, data: dict, **kwargs):
		data = self.__preprocess(data)
		for key, item in data.items():
			self._updateValue(key, item)
		self.calculateMissing()

	def __getitem__(self, item: str):
		if item in self.keys():
			return super(Observation, self).__getitem__(item)
		else:
			if isinstance(item, datetime) and item == self._time:
				return self
			return super(Observation, self).__getitem__(item)

	# def __setitem__(self, item: str, value):
	# 	self[item] = self.convertValue(item, value)

	def calculateMissing(self):
		keys = set(self.keys())
		light = {'illuminance', 'irradiance'}

		if 'humidity' in self.keys():
			if 'dewpoint' not in self.keys():
				self['dewpoint'] = self['temperature'].dewpoint(self['humidity'])

			if 'heatIndex' not in self.keys():
				self['heatIndex'] = self['temperature'].heatIndex(self['humidity'])

		if 'windChill' not in self.keys() and 'windSpeed' in self.keys():
			self['windChill'] = self['temperature'].windChill(self['windSpeed'])

		if keys.intersection(light) and not keys.issubset(light):
			if 'irradiance' in self.keys():
				self['illuminance'] = self['irradiance'].lux
			else:
				self['irradiance'] = self['illuminance'].wpm2

	def _updateValue(self, key, value):
		self[key] = self.convertValue(key, value)

	def __preprocess(self, data: dict):
		self._time = self.__processTime(data)
		normalizeDict = {value['sourceKey']: key for key, value in self.translator.items()}
		data = {normalizeDict[key]: value for key, value in data.items() if key in normalizeDict.keys()}
		return data

	def __processTime(self, data: dict, pop: bool = False) -> datetime:
		unitDefinition = self._translator['time']['unit']
		timeKey = self.timeKey(data)
		value = data.pop(timeKey)
		if isinstance(value, datetime):
			return value
		try:
			return parse(value).astimezone(config.tz)
		except TypeError:
			return datetime.fromtimestamp(value).astimezone(config.tz)

	# elif unitDefinition == 'ISO8601':
	# 	return parse(value).astimezone(config.tz)

	@property
	def api(self) -> 'API':
		return self._api

	@classmethod
	def timeKey(cls, data) -> str:
		if cls._translator['time']['sourceKey'] in data:
			return cls._translator['time']['sourceKey']
		else:
			return (set(data.keys()).intersection({'time', 'timestamp', 'day_start_local', 'date', 'datetime'})).pop()

	@classmethod
	def observationKey(cls, data) -> DateKey:
		timeData = cls._translator['time']
		timeValue = data[cls.timeKey(data)]
		if timeData['unit'] == 'epoch':
			return DateKey(timeValue)
		if timeData['unit'] == 'ISO8601':
			key = DateKey(int(parse(timeValue).timestamp()))
			return key

	def convertValue(self, key, value):
		measurementData = self.translator[key]
		unitDefinition = measurementData['unit']
		typeString = measurementData['type']
		title = measurementData['title']
		if isinstance(unitDefinition, list):
			n, d = [self.unitDict[cls] for cls in unitDefinition]
			comboCls: DerivedMeasurement = self.unitDict['special'][typeString]
			measurement = comboCls(n(value), d(1), title=title, subscriptionKey=key, timestamp=self._time)
		elif unitDefinition == '*':
			specialCls = self.unitDict['special'][typeString]
			kwargs = {'title': title, 'subscriptionKey': key, 'timestamp': self._time} if issubclass(specialCls, wu.Measurement) else {}
			measurement = specialCls(value, **kwargs)
		elif typeString == 'date':
			if isinstance(value, datetime):
				measurement = value
			else:
				if unitDefinition == 'epoch':
					measurement = datetime.fromtimestamp(value)
				elif unitDefinition == 'ISO8601':
					measurement = datetime.strptime(value, measurementData['format'])
				else:
					measurement = datetime.now()
					log.warning(f'Unable to convert date value "{value}" defaulting to current time')
		elif typeString == 'timedelta':
			if unitDefinition == 'epoch':
				measurement = self.unitDict['s'](value, title=title, subscriptionKey=key)
			elif unitDefinition == 'ISO8601':
				measurement = ISOduration(value)
		else:
			cls = self.unitDict[unitDefinition]
			if issubclass(cls, wu.Measurement):
				measurement = cls(value, title=title, subscriptionKey=key, timestamp=self._time)
			else:
				measurement = cls(value)

		if isinstance(measurement, wu.Measurement):
			measurement = measurement.localize

		return measurement

	@property
	def translator(self):
		return self._translator

	@property
	def time(self):
		return self._time


class ObservationRealtime(Observation):
	time: datetime
	timezone: timezone
	subscriptionChannel: str = None
	_indoorOutdoor: bool = False
	updateHandler: ObservationUpdateHandler

	def __init__(self, *args, **kwargs):
		# self.source = 'tcp'
		super(ObservationRealtime, self).__init__(*args, **kwargs)
		self.updateHandler = ObservationUpdateHandler(self)

	def convertValue(self, key, value):
		measurement = super(ObservationRealtime, self).convertValue(key, value)
		if self._indoorOutdoor and isinstance(measurement, wu.Measurement) and 'indoor' in measurement.subscriptionKey.lower():
			measurement.indoor = True
		return measurement

	def _updateValue(self, key, value):
		value = self.convertValue(key, value)
		if isinstance(value, wu.Measurement):
			if key in self.keys():
				self[key] |= value
			else:
				self[key] = value
		else:
			super(ObservationRealtime, self)._updateValue(key, value)
		self.updateHandler.autoEmit(key)

	def udpUpdate(self, data):
		self.update(data)

	def emitUpdate(self, key):
		if key in self.signals.keys():
			signal = self.signals[key]
			signal.emit(self[key])

	def tryToSubscribe(self, key):
		if key in self.signals.keys():
			self.signals[key]
		else:
			self.signals.update({key: [signal]})
		try:
			signal.emit(self[key])
		except KeyError:
			log.error(f'API does not have that {key} yet, will emit when added')


class ObservationForecast(ObservationDict):
	_knownKeys: list[str] = []
	observations: dict[DateKey, Observation]
	_fieldsToPop = []
	_maxTime: int = 24 * 3
	_observationClass: Type[Observation] = Observation
	period: timedelta
	timeframe: timedelta
	signalDispatcher: ForecastSignalDispatcher

	def __init__(self, *args, **kwargs):
		self.signalDispatcher = ForecastSignalDispatcher()
		self['time']: dict[DateKey, Observation] = {}
		super(ObservationForecast, self).__init__(*args, **kwargs)

	def calculateMissing(self):
		if 'precipitationAccumulation' not in self.knownKeys and (key := self.keySelector('precipitation', 'precipitationRate')):
			accumulation = self[key][0].__class__(0)
			for obs in self['time'].values():
				accumulation += obs[key]
				obs['precipitationAccumulation'] = accumulation
		self['datetime'] = [time.datetime for time in self['time'].keys()]

	def keySelector(self, *keys) -> Union[bool, str]:
		s = set(keys).intersection(self.knownKeys)
		if s:
			return list(s)[0]
		return False

	@property
	def knownKeys(self):
		return list(list(self['time'].values())[0].keys())

	def update(self, data: dict, **kwargs):
		raw = data

		if isinstance(raw, List):
			for rawObs in raw:
				key = self.__makeKey(rawObs)
				obs = self['time'].get(key)
				if obs is None:
					self['time'][key] = self._observationClass(rawObs)
				else:
					self['time'][key].update(rawObs)

		self.calculateMissing()
		for key in self.knownKeys:
			self.__updateObsKey(key)

		p = np.array(list(self['time'].keys()))
		self._period = timedelta(seconds=(p[1:, ] - p[:-1]).mean())
		self.signalDispatcher.signal.emit({'source': self})

	def __updateObsKey(self, key):
		# self[key] = {k1: value[key] for k1, value in self['time'].items() if key in value.keys()}
		# self[key] = MeasurementTimeline(self, key)
		self[key] = MeasurementForecast(self, key, [x[key] if key in x.keys() else None for x in self['time'].values()])

	def __genObsValueForKey(self, key):
		self[key] = [x[key] for x in self['time'].values()]

	@property
	def period(self) -> timedelta:
		return self._period

	@property
	def timeframe(self) -> timedelta:
		if self.timestamps:
			return self.timestamps[-1].datetime - self.timestamps[0].datetime
		else:
			return timedelta(0)

	@property
	def timestamps(self):
		return list(self['time'].keys())

	def __makeKey(self, data: dict):
		return self._observationClass.observationKey(data)

	def __getitem__(self, key) -> Union[List[Measurement], Observation]:
		# if key in self._knownKeys:
		# self[key] = {k1: value[key] for k1, value in self['time'].items() if key in value.keys()}
		if key not in self.keys():

			if isinstance(key, int):
				return list(self['time'].values())[key]

			if isinstance(key, datetime):
				timestamp = int(key.timestamp())
				key = closest(list(self['time'].keys()), timestamp)
				return self['time'][key]

			try:
				self.__genObsValueForKey(key)
			except AttributeError:
				pass

		if isinstance(key, int):
			key = list(self['time'].keys())[key]
			return self['time'][key]

		return super(ObservationForecast, self).__getitem__(key)

	def parseData(self, data):
		for field in self._fieldsToPop:
			data.pop(field)

		normalizeDict = {value['sourceKey']: key for key, value in self.translator.items()}
		data = {normalizeDict[key]: value for key, value in data.items()}

		finalData = {}
		for key, value in data.items():
			finalData[key] = self.convertValue(key, value)
		return finalData

	@property
	def translator(self):
		return self._translator

	@property
	def raw(self):
		return self['raw']


class MeasurementForecast(list):
	_key: str
	_source: ObservationForecast

	def __init__(self, source: ObservationForecast, key: str, values: Iterable):
		self._source = source
		self._key = key
		super(MeasurementForecast, self).__init__(values)

	def sort(self, *args, **kwargs):
		if not args and not kwargs:
			super(MeasurementForecast, self).sort(key=attrgetter('timestamp'))
		else:
			super(MeasurementForecast, self).sort(*args, **kwargs)
#
# def update(self, values: list):
#
# 	if self[0].timestamp == values[0].timestamp and self == values:
# 		return
# 	runway = [a.timestamp for a in self[:10]]
# 	if values[0] in runway:
# 		while self[0].timestamp != values[0].timestamp:
# 			self.pop(0)
