"""A key's samples as plain numbers, and the maths that builds one series from others.

Qt-free, so the plots and the tests share it. `Series` is what every polar plot reads. `derive`
evaluates an expression once per sample time, which is how `key: temperature - dewpoint` gets a
whole series where a computed key (one value, no history) cannot.
"""
from bisect import bisect_left, bisect_right
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence, Tuple

import WeatherUnits as wu

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.expressions import Expression, Missing

__all__ = ['Series', 'derive', 'number']


def number(value) -> Optional[float]:
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


class Series:
	"""Times and numbers of one key, with the unit its first sample came in.

	`raw` keeps each sample as the source held it (a measurement, say), so an expression can
	do unit-aware maths on it. It is None for a series built from bare numbers.
	"""
	__slots__ = ('times', 'values', 'unit', 'now', 'cls', 'raw')

	def __init__(self, times=(), values=(), unit: str = '', now: Optional[float] = None, cls: Optional[type] = None, raw=None):
		self.times: list[datetime] = list(times)
		self.values: list[float] = list(values)
		self.unit = unit
		self.now = now
		self.cls = cls
		self.raw: Optional[list] = None if raw is None else list(raw)

	def __len__(self) -> int:
		return len(self.values)

	def between(self, start: datetime, end: datetime) -> 'Series':
		keep = [i for i, t in enumerate(self.times) if start <= t < end]
		raw = None if self.raw is None else [self.raw[i] for i in keep]
		return Series([self.times[i] for i in keep], [self.values[i] for i in keep], self.unit, self.now, self.cls, raw)


class _Inputs:
	"""What an expression reads while it is evaluated at one sample time: each key's last sample at or before then."""
	__slots__ = ('lookup', 'when')

	def __init__(self, lookup: Mapping[CategoryItem, Tuple[list, list]]):
		self.lookup = lookup
		self.when: Optional[datetime] = None

	def _at(self, key: CategoryItem, when: datetime) -> Any:
		times, values = self.lookup.get(key, ((), ()))
		i = bisect_right(times, when)
		return values[i - 1] if i else None

	def current(self, key: CategoryItem) -> Any:
		return self._at(key, self.when)

	def at(self, key: CategoryItem, when: datetime) -> Any:
		return self._at(key, when)

	def series(self, key: CategoryItem, start: datetime, end: datetime) -> Optional[Sequence[Tuple[datetime, Any]]]:
		times, values = self.lookup.get(key, ((), ()))
		lo, hi = bisect_left(times, start), bisect_right(times, end)
		return list(zip(times[lo:hi], values[lo:hi])) or None


def _samples(series: Series) -> Tuple[list, list]:
	"""Sorted (times, values) with the source's own objects when it kept them."""
	raw = series.raw if series.raw is not None else series.values
	pairs = sorted(zip(series.times, raw), key=lambda pair: pair[0])
	return [t for t, _ in pairs], [v for _, v in pairs]


def derive(expression: Expression, inputs: Mapping[CategoryItem, Series], now: datetime) -> Series:
	"""One series from an expression over other series.

	The expression is evaluated at every time any of its current-value keys has a sample (or, with
	none, any key it reads over a window). At each time a key stands for its last sample at or before
	it; `max(key, 3h)` looks back from that time. A time where an input has no value yet is skipped.
	`now` is the series' current value, evaluated the same way. An `ExpressionError` from a value that
	cannot be combined (a bare number beside a temperature) reaches the caller.
	"""
	lookup = {key: _samples(series) for key, series in inputs.items()}
	driving = expression.keys or {i.key for i in expression.series} | {i.key for i in expression.points}
	moments = sorted({t for key in driving for t in lookup.get(key, ((), ()))[0]})
	resolver = _Inputs(lookup)
	times, values, raw, unit, cls = [], [], [], '', None

	def evaluate(when: datetime):
		resolver.when = when
		return expression.evaluate(resolver, now=when)

	for when in moments:
		result = evaluate(when)
		if result is Missing or (value := number(result)) is None:
			continue
		if cls is None and isinstance(result, wu.Measurement):
			cls, unit = type(result), str(getattr(result, 'unit', '') or '')
		times.append(when)
		values.append(value)
		raw.append(result)
	current = evaluate(now)
	return Series(times, values, unit, None if current is Missing else number(current), cls, raw)
