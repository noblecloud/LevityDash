"""Value to fraction, and the pure helpers that go with it.

`Scale` is the whole of "where on the track does this value sit": a minimum, a
maximum, and optionally a `wrap` join, with `t` (0..1) as the only currency it
deals in. Everything that used to convert a value to degrees, or a degree to a
value, goes through here — the arc's angle only ever entered those conversions
because the track it sits on happens to be round.

The rest of this module is the small pure helpers `Gauge.py` kept beside its
widgets: factor filtering for tick intervals, duration and clock formatting, and
the marker text decoder. They are here because they are the arithmetic the scale
and the tracks are built on, and because a bar needs the same ones.

None of this imports Qt, `Gauge.py`, or anything that does.
"""
from collections.abc import Iterable
from typing import Type

from LevityDash.lib.utils.shared import factors, Unset
from WeatherUnits import Measurement, auto as auto_wu

__all__ = [
	'CLOCK_HANDS', '_isWholeSteps', 'clockTurn', 'decode_measurement', 'filter_factors',
	'formatDuration', 'parseClockTime', 'shortestDelta',
]


def filter_factors(
	numbers: Iterable[int],
	required_factors: set[int] = None,
	included_factors: set[int] = None,
	excluded_factors: set[int] = None,
) -> set[int]:
	if required_factors is None:
		required_factors = set()

	return {
		n for n in numbers
		if required_factors <= (f := factors(int(n)))
		and (not included_factors or included_factors & f)
		and (not excluded_factors or not excluded_factors & f)
	}


def _isWholeSteps(span, interval) -> bool:
	"""Whether `interval` divides `span` into a whole number of steps, within float error."""
	try:
		span, interval = float(span), float(interval)
		steps = round(span / interval, 9)
	except (TypeError, ValueError, ZeroDivisionError, OverflowError):
		return False
	return steps == int(steps)


def formatDuration(minutes) -> str:
	"""A number of minutes as ``4h 49m``, or ``49m`` under an hour. Pure."""
	try:
		total = int(round(float(minutes)))
	except (TypeError, ValueError):
		return '\u22ef'
	sign, total = ('-' if total < 0 else ''), abs(total)
	hours, mins = divmod(total, 60)
	return f'{sign}{hours}h {mins:02d}m' if hours else f'{sign}{mins}m'


def shortestDelta(current: float, target: float, span: float = 360.0) -> float:
	"""The signed turn from ``current`` to ``target`` that crosses the join the short way.

	``span`` is one full turn of the scale. The result lies in ``[-span/2, span/2]``.
	"""
	delta = (target - current) % span
	return delta - span if delta > span / 2 else delta


#: What a marker's ``time:`` can follow. Each is one turn of the dial, whatever
#: the range: ``hour`` a 12 hour turn, ``minute`` and ``second`` 60 s, ``day`` 24 hours.
CLOCK_HANDS = ('hour', 'minute', 'second', 'day')


def clockTurn(hand: str, hours: int, minutes: int, seconds: float) -> float:
	"""How far round the dial a clock ``hand`` is at a time of day, from 0 up to (not including) 1. Pure.

	The hour and minute hands carry the smaller units, so they sweep rather than step.
	"""
	match hand:
		case 'hour':
			return ((hours % 12) + minutes / 60 + seconds / 3600) / 12
		case 'minute':
			return (minutes + seconds / 60) / 60
		case 'second':
			return seconds / 60
		case 'day':
			return (hours + minutes / 60 + seconds / 3600) / 24
	raise ValueError(f'a clock hand is one of {", ".join(CLOCK_HANDS)}, not {hand!r}')


def parseClockTime(text: str) -> tuple[int, int, float]:
	"""``'10:08'`` or ``'10:08:36'`` as ``(hours, minutes, seconds)``."""
	parts = str(text).strip().split(':')
	if not 2 <= len(parts) <= 3:
		raise ValueError(f'a clock time is HH:MM or HH:MM:SS, not {text!r}')
	hours, minutes = int(parts[0]), int(parts[1])
	seconds = float(parts[2]) if len(parts) == 3 else 0.0
	if not (0 <= hours < 24 and 0 <= minutes < 60 and 0 <= seconds < 60):
		raise ValueError(f'{text!r} is not a time of day')
	return hours, minutes, seconds


def decode_measurement(value: str | int | float, default_type: Type[Measurement] = Unset) -> Measurement:
	match value:
		case str(v):
			value = auto_wu(v)
		case int(v) | float(v):
			value = default_type(v)
		case _:
			raise TypeError(f'Invalid type for min: {type(value)}')
	return value
