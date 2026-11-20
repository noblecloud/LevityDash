"""Your comfort range: the temperatures that feel neutral to you.

The temperature scale (``$temperature``, ``TemperatureGradient``) is neutral, plain white, across a band of
comfortable temperatures and turns blue below it and orange to purple above it. Everything coloured by that
scale (the forecast line, the outdoor temperature's ``fill-gradient``, a gauge arc) follows one setting::

	[Comfort]
	low = 55°F      # colder than this is cool
	high = 72°F     # warmer than this is warm

A number with no unit is read in the temperature unit of ``[Units]``. Leave the section out for the built-in
band, 12 to 22 °C (about 54 to 72 °F). Pure Python, no Qt.
"""
from __future__ import annotations

from typing import Callable, Mapping, Optional

__all__ = ('DEFAULT_LOW', 'DEFAULT_HIGH', 'ComfortError', 'parse', 'configured', 'shift')

#: The band the built-in scale is neutral across, in degrees Celsius.
DEFAULT_LOW = 12.0
DEFAULT_HIGH = 22.0

SECTION = 'Comfort'


class ComfortError(ValueError):
	"""A comfort setting that is not a temperature, or a low that is not below the high."""


def parse(text, default_unit: str = 'C') -> float:
	"""``text`` as degrees Celsius. ``55°F``, ``13 C`` and ``286 K`` carry their unit; a bare number takes ``default_unit``."""
	from unitcorn.temperature import Temperature
	from LevityDash.lib.stopunits import StopUnitError, parseStop, toDataUnit

	found = parseStop(text)
	if found is None:
		raise ComfortError(f'{text!r} is not a temperature (try 55°F)')
	number, unit = found
	try:
		return toDataUnit(number, unit or default_unit, Temperature.Celsius)
	except StopUnitError as e:
		raise ComfortError(str(e)) from e


def _temperature_unit() -> str:
	try:
		from LevityDash.lib.config import userConfig
		return userConfig.get('Units', 'temperature', fallback='C') or 'C'
	except Exception:  # noqa: BLE001 - no config yet: Celsius
		return 'C'


def configured(section: Optional[Mapping[str, str]] = None, default_unit: Optional[str] = None, log: Optional[Callable[[str], None]] = None) -> tuple[float, float]:
	"""``(low, high)`` in degrees Celsius from ``[Comfort]`` of the user's config (or ``section``, a mapping, for tests).

	A missing section or key keeps the built-in value. A setting that cannot be read, or a low that is not
	below the high, is reported through ``log`` and the built-in band is used.
	"""
	if section is None:
		try:
			from LevityDash.lib.config import userConfig
			section = userConfig[SECTION] if userConfig.has_section(SECTION) else {}
		except Exception:  # noqa: BLE001
			section = {}
	if default_unit is None:
		default_unit = _temperature_unit() if section else 'C'
	low, high = DEFAULT_LOW, DEFAULT_HIGH
	try:
		if (text := section.get('low')) not in (None, ''):
			low = parse(text, default_unit)
		if (text := section.get('high')) not in (None, ''):
			high = parse(text, default_unit)
		# One end alone moves that end only; the band must still have a width.
		if not low < high:
			raise ComfortError(f'[Comfort] low must be below high (low {low:.1f} °C, high {high:.1f} °C)')
	except ComfortError as e:
		if log:
			log(f'[Comfort] ignored: {e}')
		return DEFAULT_LOW, DEFAULT_HIGH
	return low, high


def shift(value: float, low: float, high: float) -> float:
	"""Where a stop at ``value`` °C of the built-in scale sits for a comfort range of ``low`` to ``high``.

	The neutral band stretches to the new range. Stops below it keep their distance under the new low, and stops
	above it their distance over the new high, so the cold and hot ends of the scale slide with the band.
	"""
	if value <= DEFAULT_LOW:
		return value + (low - DEFAULT_LOW)
	if value >= DEFAULT_HIGH:
		return value + (high - DEFAULT_HIGH)
	return low + (value - DEFAULT_LOW) / (DEFAULT_HIGH - DEFAULT_LOW) * (high - low)
