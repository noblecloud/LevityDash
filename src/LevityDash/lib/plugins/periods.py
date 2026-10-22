"""A period label: the high of today, the low of yesterday, the average of the last 3 hours.

A connection can say `period: today` and `using: max` instead of writing
`max(environment.temperature.temperature, today)`. If a loaded plugin reports
that window under a key of its own (a forecast `temperature.high`), the label
picks that key. Otherwise it falls back to the matching expression, which the
computed layer works out from the readings.
"""
from datetime import timedelta
from typing import Callable, Optional

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.expressions import Expression, ExpressionError

__all__ = ['USING', 'PERIODS', 'periodExpression', 'reportedKey', 'resolvePeriod']

#: What `using:` may say. `high` and `low` are the everyday names for max and min.
USING = {'max': 'max', 'min': 'min', 'avg': 'avg', 'mean': 'avg', 'high': 'max', 'low': 'min'}

#: The calendar windows. Anything else is a duration such as `3h` or `7d`.
PERIODS = ('today', 'yesterday')

#: `(period, aggregation)` -> the keys a plugin may report it under, as suffixes
#: on the key's own path. `temperature.temperature` + today/max -> `temperature.high`.
_REPORTED = {
	('today', 'max'): ('high', 'max'),
	('today', 'min'): ('low', 'min'),
}


def _normalize(period, using):
	period = str(period).strip().lower()
	name = USING.get(str(using or 'max').strip().lower())
	if name is None:
		raise ValueError(f'using: {using!r} is not one of {", ".join(sorted(USING))}')
	if period in PERIODS:
		return period, name
	try:
		Expression.parse(f'{name}(environment.x.y, {period})')
	except ExpressionError:
		raise ValueError(f'period: {period!r} is not today, yesterday or a duration such as 3h')
	return period, name


def periodExpression(key, period, using='max') -> str:
	"""The expression text a period on `key` stands for."""
	period, name = _normalize(period, using)
	return f'{name}({key}, {period})'


def reportedKey(key: CategoryItem, period, using, reported: Callable[[CategoryItem], bool]) -> Optional[CategoryItem]:
	"""The key a plugin reports this window under, or None."""
	period, name = _normalize(period, using)
	text = str(key)
	if ':' in text:
		return None
	path, _, identity = text.partition('#')
	parts = path.split('.')
	# `temperature.temperature` is the reading; its siblings carry the windows.
	head = parts[:-1]
	for suffix in _REPORTED.get((period, name), ()):
		candidate = CategoryItem('.'.join([*head, suffix]))
		if reported(candidate):
			return candidate.withIdentity(identity) if identity else candidate
	return None


def resolvePeriod(key, period, using, reported: Callable[[CategoryItem], bool]) -> str:
	"""The key text a display should open: a reported key, else the expression."""
	if not isinstance(key, CategoryItem):
		key = CategoryItem(key)
	found = reportedKey(key, period, using, reported)
	if found is not None:
		return str(found)
	return periodExpression(key, period, using)
