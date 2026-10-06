"""Tests for the value-source expression core (lib/plugins/expressions.py).

The evaluator reads its inputs through a Resolver, so these tests use a
dict-backed one and never start a plugin, Qt or the wire.
"""
from datetime import datetime, timedelta, timezone

import pytest
import WeatherUnits as wu
from WeatherUnits.length import Millimeter
from WeatherUnits.temperature import Celsius, Fahrenheit

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.expressions import Expression, ExpressionError, Missing, PointInput, SeriesInput, Window

TEMP = 'environment.temperature.temperature'
DEW = 'environment.temperature.dewpoint'
GUST = 'environment.wind.speed.gust'
SPEED = 'environment.wind.speed.speed'

NOW = datetime(2026, 10, 4, 15, 0, tzinfo=timezone(timedelta(hours=-5)))


class FakeResolver:
	def __init__(self, current=None, series=None):
		self._current = {CategoryItem(k): v for k, v in (current or {}).items()}
		self._series = {CategoryItem(k): v for k, v in (series or {}).items()}
		self.seriesRequests = []

	def current(self, key):
		return self._current.get(key)

	def series(self, key, start, end):
		self.seriesRequests.append((key, start, end))
		points = self._series.get(key)
		if points is None:
			return None
		return [(t, v) for t, v in points if start <= t <= end]

	def at(self, key, when):
		points = self._series.get(key)
		if not points:
			return None
		return min(points, key=lambda p: abs(p[0] - when))[1]


def hourly(*values, start=datetime(2026, 10, 4, 0, 0, tzinfo=timezone(timedelta(hours=-5)))):
	return [(start + timedelta(hours=i), v) for i, v in enumerate(values)]


# -- parsing --------------------------------------------------------------------

def test_plain_key_is_recognised():
	expression = Expression.parse(TEMP)
	assert expression.plainKey == CategoryItem(TEMP)
	assert expression.keys == {CategoryItem(TEMP)}


def test_key_affixes_survive_parsing():
	# '#' would start a Python comment and ':' is not valid in a name, so the
	# pre-pass must protect both.
	expression = Expression.parse('Govee-bedroom:indoor.temperature.temperature#bedroom')
	key = expression.plainKey
	assert key.source == ('Govee-bedroom',)
	assert key.identity == 'bedroom'


def test_window_and_point_inputs():
	expression = Expression.parse(f'max({TEMP}, today) - min({TEMP}, 24h) + at({DEW}, -3h) * 2')
	assert expression.plainKey is None
	assert expression.keys == frozenset()
	assert expression.series == {
		SeriesInput(CategoryItem(TEMP), Window()),
		SeriesInput(CategoryItem(TEMP), Window(timedelta(hours=24))),
	}
	assert expression.points == {PointInput(CategoryItem(DEW), timedelta(hours=-3))}
	assert expression.inputKeys == {CategoryItem(TEMP), CategoryItem(DEW)}


def test_same_meaning_same_key():
	a = Expression.parse(f'max({TEMP}, today)')
	b = Expression.parse(f'max( {TEMP} ,today )')
	c = Expression.parse(f'(max({TEMP}, today))')
	assert a.key == b.key == c.key
	assert a.key[0] == 'computed'
	# 24h and 1d are the same span.
	assert Expression.parse(f'max({TEMP}, 24h)').key == Expression.parse(f'max({TEMP}, 1d)').key


def test_different_meaning_different_key():
	assert Expression.parse(f'max({TEMP}, today)').key != Expression.parse(f'min({TEMP}, today)').key
	assert Expression.parse(f'max({TEMP}, 24h)').key != Expression.parse(f'max({TEMP}, 12h)').key


def test_parse_interns_identical_text():
	assert Expression.parse(f'avg({TEMP}, 7d)') is Expression.parse(f'avg({TEMP}, 7d)')


@pytest.mark.parametrize('text', [
	'',
	'__import__("os")',
	f'{TEMP}.__class__',
	f'"text"',
	f'open({TEMP})',
	f'max({TEMP}, today, key=1)',
	'temperature',                      # one atom is not a key
	f'{TEMP} + 3h',                     # a duration outside a window
	f'today',
	f'avg({TEMP})',
	f'avg(1, 24h)',
	f'at({TEMP}, today)',
	f'max',
	f'[{TEMP}]',
	f'lambda: 1',
	f'{TEMP} +',
])
def test_rejected(text):
	with pytest.raises(ExpressionError):
		Expression.parse(text)


# -- evaluation -----------------------------------------------------------------

def test_plain_key_evaluates_to_current_value():
	resolver = FakeResolver(current={TEMP: Fahrenheit(70)})
	assert Expression.parse(TEMP).evaluate(resolver, NOW) == Fahrenheit(70)


def test_missing_input_gives_missing():
	resolver = FakeResolver(current={TEMP: Fahrenheit(70)})
	assert Expression.parse(f'{TEMP} - {DEW}').evaluate(resolver, NOW) is Missing
	assert Expression.parse(f'max({TEMP}, today)').evaluate(resolver, NOW) is Missing


def test_today_window_covers_the_local_day():
	resolver = FakeResolver(series={TEMP: hourly(*[Fahrenheit(60 + i) for i in range(24)])})
	assert Expression.parse(f'max({TEMP}, today)').evaluate(resolver, NOW) == Fahrenheit(83)
	assert Expression.parse(f'min({TEMP}, today)').evaluate(resolver, NOW) == Fahrenheit(60)
	_, start, end = resolver.seriesRequests[0]
	assert (start.hour, end.hour, (end - start)) == (0, 0, timedelta(days=1))


def test_duration_window_covers_the_past():
	resolver = FakeResolver(series={TEMP: hourly(*[Fahrenheit(60 + i) for i in range(24)])})
	# NOW is 15:00, so the last 3 hours are 12:00 to 15:00: 72 to 75.
	assert Expression.parse(f'min({TEMP}, 3h)').evaluate(resolver, NOW) == Fahrenheit(72)
	assert Expression.parse(f'avg({TEMP}, 3h)').evaluate(resolver, NOW) == Fahrenheit(73.5)


def test_at_reads_an_offset_from_now():
	resolver = FakeResolver(series={TEMP: hourly(*[Fahrenheit(60 + i) for i in range(24)])})
	assert Expression.parse(f'at({TEMP}, -3h)').evaluate(resolver, NOW) == Fahrenheit(72)
	assert Expression.parse(f'at({TEMP}, 2h)').evaluate(resolver, NOW) == Fahrenheit(77)


def test_conditional_only_evaluates_the_branch_taken():
	resolver = FakeResolver(current={GUST: 20.0, SPEED: 10.0})
	text = f'{GUST} if {GUST} > {SPEED} * 1.5 else {SPEED}'
	assert Expression.parse(text).evaluate(resolver, NOW) == 20.0
	# DEW is missing, but the branch that reads it is not taken.
	resolver = FakeResolver(current={GUST: 20.0})
	assert Expression.parse(f'{GUST} if 1 > 0 else {DEW}').evaluate(resolver, NOW) == 20.0
	assert Expression.parse(f'{DEW} if 1 > 0 else {GUST}').evaluate(resolver, NOW) is Missing


def test_measurement_arithmetic_converts_units():
	resolver = FakeResolver(current={TEMP: Fahrenheit(70), DEW: Celsius(20)})
	result = Expression.parse(f'{TEMP} - {DEW}').evaluate(resolver, NOW)
	assert isinstance(result, Fahrenheit)
	assert float(result) == pytest.approx(2)


def test_bare_number_next_to_a_measurement_is_refused():
	resolver = FakeResolver(current={TEMP: Fahrenheit(70)})
	with pytest.raises(ExpressionError, match='ambiguous'):
		Expression.parse(f'{TEMP} - 5').evaluate(resolver, NOW)
	with pytest.raises(ExpressionError, match='ambiguous'):
		Expression.parse(f'{TEMP} > 90').evaluate(resolver, NOW)
	# Scaling by a bare number is fine.
	assert Expression.parse(f'{TEMP} * 2').evaluate(resolver, NOW) == Fahrenheit(140)


def test_zero_is_not_ambiguous_for_a_measure_that_starts_at_zero():
	rain = 'environment.precipitation.precipitation'
	resolver = FakeResolver(current={rain: wu.Precipitation.Hourly(Millimeter(2.0)), TEMP: Fahrenheit(70)})
	assert Expression.parse(f'{rain} > 0').evaluate(resolver, NOW) is True
	assert Expression.parse(f'{rain} == 0').evaluate(resolver, NOW) is False
	# A bare number other than zero, or a temperature, still names no unit.
	with pytest.raises(ExpressionError, match='ambiguous'):
		Expression.parse(f'{rain} > 1').evaluate(resolver, NOW)
	with pytest.raises(ExpressionError, match='ambiguous'):
		Expression.parse(f'{TEMP} > 0').evaluate(resolver, NOW)


def test_unit_literals_compare_in_the_measurements_own_unit():
	rain = 'environment.precipitation.precipitation'
	wind = 'environment.wind.speed.speed'
	resolver = FakeResolver(current={
		TEMP: Fahrenheit(95), rain: wu.Precipitation.Hourly(Millimeter(5.0)), wind: wu.Wind.MilesPerHour(30),
	})
	ev = lambda text: Expression.parse(text).evaluate(resolver, NOW)
	assert ev(f'{TEMP} > 90°F') is True
	assert ev(f'{TEMP} > 34°C') is True       # 93.2°F
	assert ev(f'{TEMP} > 36°C') is False      # 96.8°F
	assert ev(f'{TEMP} > 40 °C') is False
	assert ev(f'{rain} > 0.1 in/hr') is True  # 5 mm/hr is 0.2 in/hr
	assert ev(f'{rain} > 0.3 in/hr') is False
	assert ev(f'{wind} >= 30 mph') is True
	assert ev(f'{wind} < 20 kn') is False     # 20 kn is 23 mph
	assert ev(f'1 if {TEMP} > 90°F else 2') == 1
	assert ev(f'{TEMP} - 5°F') == Fahrenheit(90)


def test_a_unit_literal_must_match_what_it_is_compared_with():
	resolver = FakeResolver(current={TEMP: Fahrenheit(70)})
	with pytest.raises(ExpressionError, match='measures'):
		Expression.parse(f'{TEMP} > 30 mph').evaluate(resolver, NOW)
	with pytest.raises(ExpressionError):
		Expression.parse('5 mph > 3 mph').evaluate(resolver, NOW)


def test_unit_literals_do_not_swallow_durations_or_keywords():
	assert Expression.parse(f'max({TEMP}, 24h)').text
	assert Expression.parse(f'1 if {TEMP} > 3 else 2') is not None
	with pytest.raises(ExpressionError):
		Expression.parse(f'{TEMP} > 3 flurbs')


def test_negation_keeps_the_unit():
	resolver = FakeResolver(current={TEMP: Fahrenheit(70)})
	assert isinstance(Expression.parse(f'-{TEMP}').evaluate(resolver, NOW), Fahrenheit)


def test_value_refers_to_the_displayed_value():
	expression = Expression.parse('value * 2')
	assert expression.usesValue
	assert expression.evaluate(FakeResolver(), NOW, value=3) == 6
	assert expression.evaluate(FakeResolver(), NOW) is Missing


def test_division_by_zero_is_missing():
	resolver = FakeResolver(current={GUST: 20.0, SPEED: 0.0})
	assert Expression.parse(f'{GUST} / {SPEED}').evaluate(resolver, NOW) is Missing


def test_elementwise_min_max():
	resolver = FakeResolver(current={GUST: 20.0, SPEED: 10.0})
	assert Expression.parse(f'max({GUST}, {SPEED})').evaluate(resolver, NOW) == 20.0
	assert Expression.parse(f'min({GUST}, {SPEED}, 5)').evaluate(resolver, NOW) == 5
