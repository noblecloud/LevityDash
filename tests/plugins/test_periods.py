"""Tests for the period label (lib/plugins/periods.py)."""
import pytest

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.expressions import Expression
from LevityDash.lib.plugins.periods import periodExpression, reportedKey, resolvePeriod

TEMP = 'environment.temperature.temperature'
HIGH = CategoryItem('environment.temperature.high')
LOW = CategoryItem('environment.temperature.low')


def reporting(*keys):
	return lambda key: key in keys


def test_expression_fallback():
	assert periodExpression(TEMP, 'today', 'max') == f'max({TEMP}, today)'
	assert periodExpression(TEMP, 'yesterday', 'low') == f'min({TEMP}, yesterday)'
	assert periodExpression(TEMP, '3h', 'mean') == f'avg({TEMP}, 3h)'
	assert periodExpression(TEMP, '3h') == f'max({TEMP}, 3h)'


def test_every_fallback_parses():
	for period in ('today', 'yesterday', '30m', '3h', '7d'):
		for using in ('max', 'min', 'avg', 'high', 'low'):
			assert Expression.parse(periodExpression(TEMP, period, using)).series


def test_reported_key_wins():
	assert resolvePeriod(TEMP, 'today', 'max', reporting(HIGH)) == str(HIGH)
	assert resolvePeriod(TEMP, 'today', 'min', reporting(HIGH, LOW)) == str(LOW)


def test_falls_back_without_a_reported_key():
	assert resolvePeriod(TEMP, 'today', 'max', reporting()) == f'max({TEMP}, today)'
	# a plugin reports the high, not the low
	assert resolvePeriod(TEMP, 'today', 'min', reporting(HIGH)) == f'min({TEMP}, today)'


def test_only_matching_windows_use_reported_keys():
	assert reportedKey(CategoryItem(TEMP), 'yesterday', 'max', reporting(HIGH)) is None
	assert reportedKey(CategoryItem(TEMP), '3h', 'max', reporting(HIGH)) is None
	assert reportedKey(CategoryItem(TEMP), 'today', 'avg', reporting(HIGH)) is None


def test_device_identity_is_kept():
	key = resolvePeriod(f'{TEMP}#bedroom', 'today', 'max', lambda k: k.identity is None and k == HIGH or k == HIGH)
	assert key == 'environment.temperature.high#bedroom'


@pytest.mark.parametrize('period,using', [('lately', 'max'), ('today', 'median'), ('', 'max')])
def test_bad_labels_are_refused(period, using):
	with pytest.raises(ValueError):
		resolvePeriod(TEMP, period, using, reporting())


def test_place_period_rewrites_the_key():
	from types import SimpleNamespace
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime import placePeriod
	schemaOf = SimpleNamespace(schema={HIGH})
	item = {'key': TEMP, 'period': 'today', 'using': 'max'}
	assert placePeriod(item, [schemaOf]) == ('today', 'max', TEMP)
	assert item == {'key': str(HIGH)}

	item = {'key': TEMP, 'period': 'yesterday', 'using': 'min'}
	assert placePeriod(item, [schemaOf]) == ('yesterday', 'min', TEMP)
	assert item == {'key': f'min({TEMP}, yesterday)'}


def test_place_period_ignores_bad_labels():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime import placePeriod
	item = {'key': TEMP, 'period': 'lately'}
	assert placePeriod(item, [])[0] == 'lately'
	assert item == {'key': TEMP}
	assert placePeriod({'key': TEMP}, []) is None
