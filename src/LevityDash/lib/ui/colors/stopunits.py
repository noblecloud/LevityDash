"""Gradient stops written as measured values: `99°F`, `30 mph`, `1.2 in/hr`.

A stop key is a number with an optional unit. `parseStop` splits the two. `toDataUnit`
converts the stop into the unit of the data a display shows, so the colour sits at the same
reading whatever unit the data arrives in.

WeatherUnits does the unit lookup and the conversion (`auto`, the unit classes). It does not
parse a degree sign, a rate such as `in/hr`, or `km/h`, so this module handles those first and
leaves the rest to WeatherUnits. WeatherUnits also converts across dimensions without a word
(`Fahrenheit(MilesPerHour(30))` is `30°F`), so `toDataUnit` checks that both units measure the
same kind of thing before it converts.
"""
import re
from typing import Optional, Tuple, Type

from WeatherUnits import Length, Measurement, Time, Wind, auto

__all__ = ('StopUnitError', 'parseStop', 'measure', 'toDataUnit', 'formatStop', 'family')

_STOP = re.compile(r'^\s*(?P<number>[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(?P<unit>.*?)\s*$')

#: Speed units WeatherUnits has no class for, as metres per second in one of them.
_SPEEDS = {'kn': 0.514444, 'kt': 0.514444, 'kts': 0.514444, 'knot': 0.514444, 'knots': 0.514444,
           'kph': 1 / 3.6, 'kmh': 1 / 3.6}
#: Time units a rate may divide by that WeatherUnits does not know by that spelling.
_PER = {'h': 'hr', 'hour': 'hr', 'hours': 'hr', 'sec': 's', 'second': 's', 'min': 'min', 'minute': 'min', 'day': 'd'}

#: Class names that name a dimension, and the group each one belongs to.
_DIMENSIONS = {
	'Temperature': 'temperature', 'Pressure': 'pressure', 'Length': 'length', 'Time': 'time', 'DistanceOverTime': 'speed',
	'Dimensionless': 'ratio', 'Percentage': 'ratio', 'PartsPer': 'ratio', 'Mass': 'mass', 'Volume': 'volume', 'Density': 'density',
	'Angle': 'angle', 'Direction': 'angle', 'Irradiance': 'irradiance', 'Light': 'light', 'Illuminance': 'light',
}


class StopUnitError(ValueError):
	"""A stop's unit is unknown, or measures something other than the data."""


def parseStop(text) -> Optional[Tuple[float, Optional[str]]]:
	"""`(number, unit)` for a stop key such as `99°F`, `30 mph` or `70`; `unit` is None when there is none. None when `text` is not a stop.

	A degree sign on its own (`45°`) is no unit: it is how a bare number reads in a temperature or an angle.
	The unit keeps the spelling it was written in, so a file writes back as it was read.
	"""
	if isinstance(text, bool):
		return None
	if isinstance(text, (int, float)):
		return float(text), None
	if not isinstance(text, str):
		return None
	found = _STOP.match(text)
	if found is None:
		return None
	unit = found.group('unit')
	if unit in ('', '°', 'º', '˚'):
		return float(found.group('number')), None
	return float(found.group('number')), unit


def _plain(unit: str) -> str:
	"""A unit with the degree sign removed: `°F` is `F`."""
	return re.sub(r'^[°º˚]\s*', '', unit.strip())


def _unitClass(unit: str) -> Type[Measurement]:
	try:
		found = auto(unit)
	except Exception as e:  # noqa: BLE001 - WeatherUnits raises several kinds for a unit it does not know
		raise StopUnitError(f'unknown unit {unit!r}') from e
	if isinstance(found, tuple):
		found = found[0] if len(found) == 1 else None
	if found is None or not isinstance(found, type):
		raise StopUnitError(f'unknown unit {unit!r}')
	return found


def measure(number: float, unit: str) -> Measurement:
	"""The measurement `number` `unit` names. Raises `StopUnitError` for a unit it cannot read."""
	text = _plain(unit)
	if text.lower() in _SPEEDS:
		return Wind.MetersPerSecond(number * _SPEEDS[text.lower()])
	if '/' in text:
		top, _, bottom = (part.strip() for part in text.partition('/'))
		bottom = _PER.get(bottom.lower(), bottom)
		if not top or not bottom:
			raise StopUnitError(f'unknown unit {unit!r}')
		length, span = _unitClass(top), _unitClass(bottom)
		if family(length) != 'length' or family(span) != 'time':
			raise StopUnitError(f'unknown unit {unit!r}')
		# Through metres per second: WeatherUnits converts from there to every speed and rate it has.
		return Wind.MetersPerSecond(float(Length.Meter(length(number))) / float(Time.Second(span(1))))
	return _unitClass(text)(number)


def family(cls: type) -> str:
	"""The kind of thing a unit class measures: `temperature`, `speed`, `length` and so on."""
	for base in cls.__mro__:
		if base.__name__ in _DIMENSIONS:
			return _DIMENSIONS[base.__name__]
	for base in cls.__mro__:
		if base.__name__ not in ('Measurement', 'SmartFloat', 'float', 'object', 'ScalingMeasurement', 'DerivedMeasurement'):
			return base.__name__
	return cls.__name__


def toDataUnit(number: float, unit: Optional[str], valueClass: type) -> float:
	"""`number` `unit` as a plain number in the unit of `valueClass`. A bare number (no unit) is returned as it is.

	Raises `StopUnitError` when the unit is unknown or does not measure what `valueClass` does.
	"""
	if not unit:
		return float(number)
	if not (isinstance(valueClass, type) and issubclass(valueClass, Measurement)):
		raise StopUnitError(f'{unit!r} cannot apply: the data has no unit')
	measurement = measure(number, unit)
	if family(type(measurement)) != family(valueClass):
		raise StopUnitError(f'{unit!r} measures {family(type(measurement))}, but the data is {family(valueClass)} ({valueClass.__name__})')
	return float(valueClass(measurement))


def formatNumber(number: float) -> str:
	text = f'{round(float(number), 4):.4f}'.rstrip('0').rstrip('.')
	return '0' if text in ('-0', '') else text


def formatStop(number: float, unit: Optional[str]) -> str:
	"""A stop key for `number` `unit`: `99°F`, `30 mph`, `1.2 in/hr`. A degree or percent sign sits against the number."""
	text = formatNumber(number)
	if not unit:
		return text
	if unit[0] in '°%º':
		return f'{text}{unit}'
	return f'{text} {unit}'
