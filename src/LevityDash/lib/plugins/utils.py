import asyncio
from datetime import datetime
from typing import Any, Callable, Dict, Hashable, Mapping, Optional, Type, Union

import WeatherUnits as wu
from PySide2.QtCore import QObject, Signal, Slot
from pytz import timezone

from LevityDash.lib.utils import abbreviatedIterable, KeyData, SmartString
from LevityDash.lib.log import LevityPluginLog as log

unitDict: Dict[str, Union[Type[wu.Measurement], Type[bool], Dict[str, Union[Type[wu.base.Measurement], Type[wu.base.DerivedMeasurement]]]]] = {
	'f':                wu.temperature.Fahrenheit,
	'c':                wu.temperature.Celsius,
	'kelvin':           wu.temperature.Kelvin,
	'%':                wu.others.Humidity,
	'%c':               wu.others.Coverage,
	'%p':               wu.others.Probability,
	'%%':               wu.others.Percentage,
	'º':                wu.others.Direction,
	'ºa':               wu.others.Angle,
	'str':              SmartString,
	'int':              wu.base.Measurement,
	'mmHg':             wu.pressure.MillimeterOfMercury,
	'inHg':             wu.pressure.InchOfMercury,
	'W/m^2':            wu.others.light.Irradiance,
	'lux':              wu.others.light.Illuminance,
	'mb':               wu.Pressure.Millibar,
	'mbar':             wu.Pressure.Millibar,
	'bar':              wu.Pressure.Bar,
	'hPa':              wu.Pressure.Hectopascal,
	'in':               wu.length.Inch,
	'mi':               wu.length.Mile,
	'mm':               wu.length.Millimeter,
	'm':                wu.length.Meter,
	'km':               wu.length.Kilometer,
	'month':            wu.Time.Month,
	'week':             wu.Time.Week,
	'day':              wu.Time.Day,
	'hr':               wu.Time.Hour,
	'min':              wu.Time.Minute,
	's':                wu.Time.Second,
	'ug':               wu.mass.Microgram,
	'μg':               wu.mass.Microgram,
	'mg':               wu.mass.Milligram,
	'g':                wu.mass.Gram,
	'kg':               wu.mass.Kilogram,
	'lb':               wu.mass.Pound,
	'm^3':              wu.Volume.CubicMeter,
	'ft^3':             wu.Volume.CubicFoot,
	'volts':            wu.Voltage,
	'date':             datetime,
	'uvi':              wu.others.light.UVI,
	'strike':           wu.others.Strikes,
	'timezone':         timezone,
	'datetime':         datetime,
	'epoch':            datetime.fromtimestamp,
	'rssi':             wu.RSSI,
	'ppt':              wu.derived.PartsPer.Thousand,
	'ppm':              wu.derived.PartsPer.Million,
	'ppb':              wu.derived.PartsPer.Billion,
	'pptr':             wu.derived.PartsPer.Trillion,
	'bool':             bool,
	'PI':               wu.PollutionIndex,
	'PrimaryPollutant': wu.PrimaryPollutant,
	'AQI':              wu.AQI,
	'AQIHC':            wu.HeathConcern,
	'MoonPhase':        wu.Measurement,
	"WeatherCode":      wu.Measurement,
	'tz':               timezone,
	'special':          {
		'precipitation':       wu.Precipitation,
		'precipitationDaily':  wu.Precipitation.Daily,
		'precipitationHourly': wu.Precipitation.Hourly,
		'precipitationRate':   wu.Precipitation.Hourly,
		'wind':                wu.derived.Wind,
		'airDensity':          wu.derived.Density,
		'pollutionDensity':    wu.derived.Density,
		'precipitationType':   wu.Precipitation.Type,
		'pressureTrend':       SmartString
	}
}


class SchemaProperty:
	def __init__(self, source: 'ObservationDict', data: dict):
		self.source = source
		self.data = data

	def get(self, source: 'ObservationDict' = None):
		data = self.data
		source = source or self.source
		allowZero = data.get('allowZero', True)
		value = self.fromKey(source) or self.fromAttr(source) or self.default
		if not allowZero:
			return value or 1
		return value

	@property
	def default(self) -> Optional[Any]:
		if self.data.get('default', None) is None:
			return None
		data = self.data
		source = self.source
		unitCls = data.get('unit', None)
		unitCls = data.get(unitCls, None) or data.get('dataType', None)
		if unitCls is not None:
			value = data['default']['value']
			if not isinstance(value, unitCls):
				value = unitCls(value)
		else:
			value = data['default']
			if isinstance(value, dict):
				cls = value.get('dataType', None) or unitDict.get(value.get('unit', None), value.get('unit', None))
				if cls is not None:
					return cls(value['value'])
				value = value['value']

		return value

	def fromKey(self, source: Union[Mapping, 'Plugin'] = None) -> Optional[Any]:
		source = source or self.source
		if 'key' in self.data and self.data['key'] in source:
			return source[self.data['key']]
		return None

	def fromAttr(self, source: Union[Mapping, 'Plugin']) -> Optional[Any]:
		source = source or self.source
		if 'attr' in self.data and hasattr(source, self.data['attr']):
			return getattr(source, self.data['attr'])
		return None

	def __delete__(self, instance):
		pass

	def __call__(self, source: Union[Mapping, 'Plugin'], *args, **kwargs):
		return self.get(source=source, *args, **kwargs)


class ChannelSignal(QObject):
	__signal = Signal(list)
	__connections: dict[Hashable: Callable]

	def __init__(self, source, key):
		self.__connections = {}
		self.__key = key
		self.__source = source
		super(ChannelSignal, self).__init__()

	def __repr__(self):
		return f'Signal for {self.__source.name}:{self.__key}'

	def connectSlot(self, slot):
		self.__connections.update({slot.__self__: slot})
		self.__signal.connect(slot)

	def publish(self, sources: list['ObservationDict']):
		self.__signal.emit(sources)

	def disconnectSlot(self, slot):
		try:
			self.__connections.pop(slot.__self__)
			self.__signal.disconnect(slot)
		except RuntimeError:
			pass

	@property
	def hasConnections(self) -> bool:
		return len(self.__connections) > 0

	@property
	def key(self):
		return self.__key


class Accumulator(QObject):
	__signal = Signal(set)
	__connections: Dict['CategoryItem', ChannelSignal]
	_data: set

	def __init__(self, observation: 'ObservationDict'):
		self.__hash = hash((observation, hash(id)))
		self.__observation = observation
		self.__connections = {}
		self._data = set()
		super(Accumulator, self).__init__()

	def __hash__(self):
		return self.__hash

	def publishKeys(self, *keys):
		self._data.update(keys)
		if not self.muted:
			asyncio.create_task(self.__emitChange())

	def publishKey(self, key):
		self.publishKeys(key, )

	@property
	def muted(self) -> bool:
		return self.signalsBlocked()

	@muted.setter
	def muted(self, value):
		self.blockSignals(value)
		if not value:
			asyncio.create_task(self.__emitChange())

	@property
	def observation(self):
		return

	async def __emitChange(self):
		if hasattr(self.__observation, 'log'):
			log.debug(f'Announcing keys: {abbreviatedIterable(self._data)}')
		self.__signal.emit(KeyData(self.__observation, self._data))
		self._data.clear()

	def connectSlot(self, slot: Slot):
		self.__signal.connect(slot)

	def disconnectSlot(self, slot: Slot):
		try:
			self.__signal.disconnect(slot)
		except RuntimeError:
			pass

	def connectChannel(self, channel: 'CategoryItem', slot: Slot):
		signal = slot.__self__.get(channel, self.__addChannel(channel))
		signal.connectSlot(slot)

	def __addChannel(self, channel: 'CategoryItem'):
		self.__signals[channel] = ChannelSignal(self.source, channel)
		return self.__signals[channel]

	@property
	def lock(self) -> bool:
		return self.__observation.lock

	def __enter__(self):
		self.blockSignals(True)

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.blockSignals(False)
		asyncio.create_task(self.__emitChange())


__all__ = ['unitDict', 'Accumulator', 'ChannelSignal', 'SchemaProperty']
