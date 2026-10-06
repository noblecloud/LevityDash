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
import re
from collections.abc import Iterable
from typing import Type, TypeVar, Union

from numpy import number as np_number

from LevityDash.lib.utils.shared import factors, Unset
from WeatherUnits import Measurement, auto as auto_wu

#: The value types a gauge deals with, and the type variable the classes that
#: hold one are generic over. (`shared.Numeric` is the same union; this file's
#: copy is the one the meter package reads, and consolidating the two is a
#: separate, deliberate change.)
Numeric = Union[int, float, complex, np_number, Measurement]
GaugeValue = TypeVar('GaugeValue', bound=Numeric, covariant=True)

__all__ = [
	'CLOCK_HANDS', 'GaugeValue', 'Numeric', 'Scale', '_isWholeSteps', 'clockTurn', 'decode_measurement',
	'filter_factors', 'formatDuration', 'parseClockTime', 'shortestDelta',
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


_LEADING_NUMBER = re.compile(r'\s*[-+]?\d+(?:\.\d+)?')


def decode_measurement(value: str | int | float, default_type: Type[Measurement] | None = Unset) -> Measurement | float:
	"""A user's number as a measurement.

	With no usable `default_type` (`Unset`, or `None` while a gauge's states apply
	before its value class is known) a bare number stays a plain float, so the
	field keeps what the user wrote and the gauge converts it once the class is
	known.
	"""
	unknown = default_type is Unset or default_type is None
	match value:
		case str(v):
			try:
				value = auto_wu(v)
			except (TypeError, ValueError, NotImplementedError):
				# A bare number, or a unit `auto_wu` cannot place (`6`, `10 in/hr`): keep the number, in the gauge's own unit.
				found = _LEADING_NUMBER.match(v)
				if found is None:
					raise
				value = float(found.group()) if unknown else default_type(float(found.group()))
		case int(v) | float(v):
			value = float(v) if unknown else default_type(v)
		case _:
			raise TypeError(f'Invalid type for min: {type(value)}')
	return value


class Scale:
	"""A value range as fractions: where on the track a value sits.

	``t`` is the only currency a scale deals in - 0 is the minimum, 1 the
	maximum - so a caller never needs to know whether the track it lands on
	happens to be an arc, a line, or anything else. That mapping is the track's
	business, and the two used to be the same number only because the track was
	always a dial.

	The two constructors are the two shapes the app has: ``Scale(min, max)`` for
	a range as a user writes it, and `from_span(min, span)`, because what the
	gauge stores is ``rounded_min`` and ``rounded_range`` - a minimum and a span,
	which are not the same pair of floats. Each keeps the numbers it was given
	exactly, so neither path introduces a rounding the old code did not have.
	"""

	__slots__ = ('_min', '_span', 'wrap')

	def __init__(self, min: float, max: float, wrap: bool = False):
		self._min = float(min)
		self._span = float(max) - float(min)
		self.wrap = bool(wrap)

	@classmethod
	def from_span(cls, min: float, span: float, wrap: bool = False) -> 'Scale':
		scale = cls.__new__(cls)
		scale._min, scale._span, scale.wrap = float(min), float(span), bool(wrap)
		return scale

	def __repr__(self) -> str:
		return f'Scale({self.min:g}..{self.max:g}{", wrap" if self.wrap else ""})'

	@property
	def min(self) -> float:
		return self._min

	@property
	def max(self) -> float:
		return self._min + self._span

	@property
	def span(self) -> float:
		return self._span

	def toT(self, value) -> float:
		"""Where ``value`` sits, as a fraction of the span.

		Clamped to 0..1; on a wrapping scale it is taken modulo the span instead,
		which is what a dial that goes round does. Out of range is not an error
		on either - a needle at the end of its scale simply stays there.
		"""
		if not self._span:
			return 0.0
		offset = float(value) - self._min
		if self.wrap:
			return (offset % self._span) / self._span
		return min(1.0, max(0.0, offset / self._span))

	def fromT(self, t: float) -> float:
		"""The value at ``t``. The inverse of `toT` between the stops."""
		return self._min + self._span * float(t)

	def spanOf(self, t0: float, t1: float) -> float:
		"""The span between two positions, in the scale's own units."""
		return self._span * (float(t1) - float(t0))
