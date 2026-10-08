"""An expression key gives a polar plot a whole series: evaluated at every sample, not once."""
from datetime import datetime, timedelta, timezone

import pytest
import WeatherUnits as wu

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.expressions import Expression
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.series import Series, derive

T = CategoryItem('environment.temperature.temperature')
D = CategoryItem('environment.temperature.dewpoint')
START = datetime(2026, 10, 7, 0, 0, tzinfo=timezone.utc)


def hourly(values, make=wu.Temperature.Fahrenheit, start=START):
	raw = [make(v) for v in values]
	return Series([start + timedelta(hours=i) for i in range(len(raw))], [float(r) for r in raw], 'f', None, type(raw[0]), raw)


def test_a_difference_is_evaluated_at_every_sample_with_units():
	out = derive(Expression.parse(f'{T} - {D}'), {T: hourly([70, 72, 75]), D: hourly([60, 61, 60])}, START + timedelta(hours=2))
	assert out.values == [10.0, 11.0, 15.0]
	assert out.times == hourly([0, 0, 0]).times
	assert out.now == 15.0 and out.cls is wu.Temperature.Fahrenheit


def test_a_sample_before_an_input_has_a_value_is_left_out_and_a_slow_input_holds():
	late = hourly([60], start=START + timedelta(hours=1))
	out = derive(Expression.parse(f'{T} - {D}'), {T: hourly([70, 72, 75]), D: late}, START + timedelta(hours=2))
	assert out.times == [START + timedelta(hours=1), START + timedelta(hours=2)]
	assert out.values == [12.0, 15.0]


def test_a_window_function_looks_back_from_each_sample():
	out = derive(Expression.parse(f'max({T}, 2h)'), {T: hourly([1, 5, 2, 2, 2])}, START + timedelta(hours=4))
	assert out.values == [1.0, 5.0, 5.0, 5.0, 2.0]


def test_a_condition_draws_as_zero_or_one():
	out = derive(Expression.parse(f'{T} > {D}'), {T: hourly([70, 50]), D: hourly([60, 60])}, START + timedelta(hours=1))
	assert out.values == [1.0, 0.0]


def test_a_bare_number_beside_a_temperature_raises_so_the_feed_can_say_why():
	from LevityDash.lib.plugins.expressions import ExpressionError
	with pytest.raises(ExpressionError):
		derive(Expression.parse(f'{T} - 5'), {T: hourly([70])}, START)


def test_an_item_rejects_text_that_is_neither_a_key_nor_an_expression():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.item import _expression
	assert _expression('key', ' environment.temperature.temperature - environment.temperature.dewpoint ') == (
		'environment.temperature.temperature - environment.temperature.dewpoint')
	assert _expression('key', '') is None and _expression('key', None) is None
	with pytest.raises(ValueError, match='speed'):
		_expression('speed', 'environment.wind.speed.speed +')
