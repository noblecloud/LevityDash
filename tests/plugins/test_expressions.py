"""Tests for the value-source expression core (lib/plugins/expressions.py).

The evaluator reads its inputs through a Resolver, so these tests use a
dict-backed one and never start a plugin, Qt or the wire.
"""
from datetime import datetime, timedelta, timezone

import pytest
import WeatherUnits as wu
from WeatherUnits.length import Millimeter
from WeatherUnits.temperature import Celsius, Fahrenheit, FahrenheitChange

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.expressions import Expression, ExpressionError, Missing, PlacedKey, PointInput, SeriesInput, Window

TEMP = 'environment.temperature.temperature'
DEW = 'environment.temperature.dewpoint'
GUST = 'environment.wind.speed.gust'
SPEED = 'environment.wind.speed.speed'

NOW = datetime(2026, 10, 4, 15, 0, tzinfo=timezone(timedelta(hours=-5)))


class FakeResolver:
	def __init__(self, current=None, series=None, members=None):
		self._current = {CategoryItem(k): v for k, v in (current or {}).items()}
		self._series = {CategoryItem(k): v for k, v in (series or {}).items()}
		self.seriesRequests = []
		self._members = members or {}

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

	def members(self, placed):
		self.placesAsked = getattr(self, 'placesAsked', []) + [placed]
		return self._members.get((str(placed.key), placed.place), [])


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


def test_avg_of_several_keys_is_their_mean():
	other = 'indoor.temperature.temperature'
	resolver = FakeResolver(current={TEMP: Fahrenheit(70), other: Fahrenheit(80)})
	assert Expression.parse(f'avg({TEMP}, {other})').evaluate(resolver, NOW) == Fahrenheit(75)
	assert Expression.parse(f'avg({TEMP}, {other}, {TEMP})').evaluate(resolver, NOW) == Fahrenheit(70 + 80 + 70) / 3


def test_mean_is_avg():
	other = 'indoor.temperature.temperature'
	resolver = FakeResolver(current={TEMP: Fahrenheit(70), other: Fahrenheit(80)}, series={TEMP: hourly(*[Fahrenheit(60 + i) for i in range(24)])})
	assert Expression.parse(f'mean({TEMP}, {other})') == Expression.parse(f'avg({TEMP}, {other})')
	assert Expression.parse(f'mean({TEMP}, {other})').evaluate(resolver, NOW) == Fahrenheit(75)
	assert Expression.parse(f'mean({TEMP}, 3h)').evaluate(resolver, NOW) == Fahrenheit(73.5)


def test_avg_of_several_keys_is_missing_if_any_is():
	other = 'indoor.temperature.temperature'
	resolver = FakeResolver(current={TEMP: Fahrenheit(70)})
	assert Expression.parse(f'avg({TEMP}, {other})').evaluate(resolver, NOW) is Missing


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
	assert isinstance(result, wu.temperature.FahrenheitChange)
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
	assert ev(f'{TEMP} - 5°F') == Fahrenheit(90)  # a reading less a change is a reading


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


def test_a_spaced_time_unit_is_not_a_unit_literal():
	# `3 min` and `10 hr` were syntax errors before unit literals and still are: spans are durations.
	for text in (f'{TEMP} * 3 min', f'max({TEMP}, 10 hr)', f'{TEMP} > 3 min'):
		with pytest.raises(ExpressionError):
			Expression.parse(text)
	assert Expression.parse(f'max({TEMP}, 3h)').text


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


# -- rates and durations -------------------------------------------------------------

RAIN = 'environment.precipitation.rate'
TOTAL = 'environment.precipitation.hourly'


def test_a_rate_times_a_duration_is_an_amount():
	rate = wu.Precipitation.Hourly(Millimeter(2), wu.Time.Hour(1))
	result = Expression.parse(f'{RAIN} * 3h').evaluate(FakeResolver(current={RAIN: rate}), NOW)
	assert isinstance(result, wu.Length) and result.unit == 'mm' and float(result) == pytest.approx(6)


def test_a_duration_times_a_rate_is_the_same_amount():
	rate = wu.Precipitation.Hourly(Millimeter(2), wu.Time.Hour(1))
	result = Expression.parse(f'90m * {RAIN}').evaluate(FakeResolver(current={RAIN: rate}), NOW)
	assert isinstance(result, wu.Length) and float(result) == pytest.approx(3)


def test_an_amount_over_a_duration_is_a_rate_in_that_duration():
	result = Expression.parse(f'{TOTAL} / 3h').evaluate(FakeResolver(current={TOTAL: Millimeter(6)}), NOW)
	assert result.unit == 'mm/hr' and float(result) == pytest.approx(2)


def test_two_lengths_make_an_area_not_a_length():
	resolver = FakeResolver(current={'a.b.c': wu.Length.Meter(2), 'a.b.d': wu.Length.Meter(3)})
	result = Expression.parse('a.b.c * a.b.d').evaluate(resolver, NOW)
	assert result.unit == 'm²' and float(result) == pytest.approx(6)


def test_same_dimension_division_is_a_plain_ratio():
	resolver = FakeResolver(current={'a.b.c': wu.Length.Meter(6), 'a.b.d': wu.Length.Foot(3.28084)})
	result = Expression.parse('a.b.c / a.b.d').evaluate(resolver, NOW)
	assert type(result) is float and result == pytest.approx(6.0, rel=1e-3)


@pytest.mark.parametrize('text', [f'{RAIN} + 3h', '3h * 3h', '3h / 3h', 'today * 2'])
def test_a_duration_is_still_refused_where_it_means_nothing(text):
	with pytest.raises(ExpressionError):
		Expression.parse(text)


# -- unit literals that stand for themselves ------------------------------------------

def test_a_power_literal_times_a_duration_is_energy():
	result = Expression.parse('1.5kW * 3h').evaluate(FakeResolver(), NOW)
	assert isinstance(result, wu.Energy) and float(result['kWh']) == pytest.approx(4.5)


def test_irradiance_over_an_area_for_a_time_is_energy():
	resolver = FakeResolver(current={'a.b.sun': wu.Light.Irradiance(500)})
	result = Expression.parse('a.b.sun * 20m² * 3h').evaluate(resolver, NOW)
	assert isinstance(result, wu.Energy) and float(result['kWh']) == pytest.approx(30)


@pytest.mark.parametrize('text', ['a.b.sun * 20m^2', 'a.b.sun * 20 m²', '20m² * a.b.sun'])
def test_an_area_literal_is_written_with_a_superscript_or_a_caret(text):
	resolver = FakeResolver(current={'a.b.sun': wu.Light.Irradiance(500)})
	result = Expression.parse(text).evaluate(resolver, NOW)
	assert isinstance(result, wu.Power) and float(result['kW']) == pytest.approx(10)


def test_a_compound_unit_literal_compares_with_a_reading():
	resolver = FakeResolver(current={'a.b.sun': wu.Light.Irradiance(610)})
	assert Expression.parse('a.b.sun > 600 W/m²').evaluate(resolver, NOW) is True
	assert Expression.parse('a.b.sun > 700 W/m²').evaluate(resolver, NOW) is False


def test_an_energy_literal_over_a_duration_is_power():
	result = Expression.parse('6kWh / 3h').evaluate(FakeResolver(), NOW)
	assert isinstance(result, wu.Power) and float(result['kW']) == pytest.approx(2)


# -- to(): the unit of the answer ---------------------------------------------------

def test_to_gives_energy_in_the_unit_asked_for():
	resolver = FakeResolver(current={'a.b.sun': wu.Light.Irradiance(500)})
	result = Expression.parse('to(a.b.sun * 20m² * 3h, kWh)').evaluate(resolver, NOW)
	assert isinstance(result, wu.Energy.KilowattHour) and float(result) == pytest.approx(30)


def test_to_takes_a_unit_written_as_a_string():
	result = Expression.parse("to(12ft * 14ft, 'ft²')").evaluate(FakeResolver(), NOW)
	assert result.unit == 'ft²' and float(result) == pytest.approx(168)


def test_to_converts_a_change_in_its_own_units():
	resolver = FakeResolver(current={TEMP: Celsius(30), DEW: Celsius(20)})
	result = Expression.parse(f"to({TEMP} - {DEW}, '°F')").evaluate(resolver, NOW)
	assert float(result) == pytest.approx(18)


@pytest.mark.parametrize('text', ['to(a.b.c, kWh)', 'to(a.b.c, zzz)', 'to(a.b.c)', 'to(a.b.c, 3)'])
def test_to_refuses_a_unit_that_does_not_fit(text):
	resolver = FakeResolver(current={'a.b.c': wu.Power.Kilowatt(2)})
	with pytest.raises(ExpressionError):
		Expression.parse(text).evaluate(resolver, NOW)


# -- temperature readings and changes -----------------------------------------------

def test_the_difference_of_two_temperatures_is_a_change():
	resolver = FakeResolver(current={TEMP: Celsius(30), DEW: Celsius(20)})
	result = Expression.parse(f'{TEMP} - {DEW}').evaluate(resolver, NOW)
	assert isinstance(result, wu.temperature.CelsiusChange) and float(result) == 10


def test_a_unit_literal_taken_from_a_reading_is_a_change_in_its_own_scale():
	resolver = FakeResolver(current={TEMP: Fahrenheit(95)})
	result = Expression.parse(f'{TEMP} - 5°C').evaluate(resolver, NOW)
	assert isinstance(result, Fahrenheit) and float(result) == pytest.approx(86)


def test_the_mean_of_temperature_readings_still_works():
	resolver = FakeResolver(current={TEMP: Celsius(30), DEW: Celsius(20)})
	result = Expression.parse(f'avg({TEMP}, {DEW})').evaluate(resolver, NOW)
	assert isinstance(result, Celsius) and float(result) == 25


def test_two_temperature_readings_do_not_add():
	resolver = FakeResolver(current={TEMP: Celsius(30), DEW: Celsius(20)})
	with pytest.raises(ExpressionError, match='two temperature readings'):
		Expression.parse(f'{TEMP} + {DEW}').evaluate(resolver, NOW)


# -- places ---------------------------------------------------------------------

IN = 'indoor.temperature.temperature'
UP = (IN, 'home.upstairs')
HOUR = timedelta(hours=1)


def _at(*readings):
	"""Members at a place: (degrees F, minutes old) for each device."""
	return [(Fahrenheit(degrees), NOW - timedelta(minutes=age)) for degrees, age in readings]


def test_where_keyword_and_suffix_are_the_same_expression():
	keyword = Expression.parse(f'avg({IN}, where=home.upstairs)')
	suffix = Expression.parse(f'avg({IN}@home.upstairs)')
	assert keyword == suffix
	assert keyword.places == {PlacedKey(CategoryItem(IN), 'home.upstairs')}
	assert keyword.keys == frozenset()
	assert Expression.parse(f'mean({IN}@home.upstairs)') == suffix


def test_where_takes_a_one_word_place():
	assert Expression.parse(f'max({IN}, where=bedroom)').places == {PlacedKey(CategoryItem(IN), 'bedroom')}


@pytest.mark.parametrize('function, expected', [('avg', 21), ('min', 20), ('max', 22), ('count', 3)])
def test_a_place_aggregates_every_reading_there(function, expected):
	resolver = FakeResolver(members={UP: _at((20, 1), (22, 5), (21, 30))})
	result = Expression.parse(f'{function}({IN}@home.upstairs)').evaluate(resolver, NOW)
	assert result == (expected if function == 'count' else Fahrenheit(expected))


def test_a_reading_older_than_an_hour_is_left_out():
	resolver = FakeResolver(members={UP: _at((20, 1), (30, 61), (22, 59))})
	expression = Expression.parse(f'avg({IN}@home.upstairs)')
	assert expression.evaluate(resolver, NOW) == Fahrenheit(21)
	assert expression.evaluateCounted(resolver, NOW)[1] == 2


def test_stale_sets_the_bound_for_one_aggregate():
	resolver = FakeResolver(members={UP: _at((20, 1), (30, 61))})
	assert Expression.parse(f'count({IN}@home.upstairs)').evaluate(resolver, NOW) == 1
	assert Expression.parse(f'count({IN}@home.upstairs, stale=2h)').evaluate(resolver, NOW) == 2
	assert Expression.parse(f'avg({IN}, where=home.upstairs, stale=2h)').evaluate(resolver, NOW) == Fahrenheit(25)


def test_a_place_with_no_fresh_reading_has_no_average_and_a_count_of_zero():
	resolver = FakeResolver(members={UP: _at((30, 90))})
	assert Expression.parse(f'avg({IN}@home.upstairs)').evaluate(resolver, NOW) is Missing
	assert Expression.parse(f'count({IN}@home.upstairs)').evaluate(resolver, NOW) == 0
	assert Expression.parse(f'avg({IN}@home.garage)').evaluate(resolver, NOW) is Missing


def test_places_and_plain_keys_mix_in_one_aggregate():
	resolver = FakeResolver(current={TEMP: Fahrenheit(60)}, members={UP: _at((20, 1), (22, 1))})
	assert Expression.parse(f'avg({TEMP}, {IN}@home.upstairs)').evaluate(resolver, NOW) == Fahrenheit((60 + 20 + 22) / 3)
	# A plain key with no value still makes the result Missing, as before.
	assert Expression.parse(f'avg({DEW}, {IN}@home.upstairs)').evaluate(resolver, NOW) is Missing


def test_a_bare_place_is_the_one_device_there():
	one = FakeResolver(members={(IN, 'home.upstairs.bedroom'): _at((20, 1))})
	assert Expression.parse(f'{IN}@home.upstairs.bedroom').evaluate(one, NOW) == Fahrenheit(20)
	two = FakeResolver(members={UP: _at((20, 1), (22, 1))})
	assert Expression.parse(f'{IN}@home.upstairs').evaluate(two, NOW) is Missing


def test_a_resolver_without_places_is_an_error_where_it_is_asked():
	class Plain:
		def current(self, key):
			return None
	with pytest.raises(ExpressionError, match='cannot read places'):
		Expression.parse(f'avg({IN}@home)').evaluate(Plain(), NOW)


@pytest.mark.parametrize('text', [
	f'avg({IN}, {TEMP}, where=home)',           # which key does the place go with
	f'avg(where=home)',
	f'{IN}#bedroom@home',                       # a device and a place at once
	f'abs({IN}, where=home)',                   # where= only goes with min, max, avg, count
	f'avg({IN}@home, 3h)',                      # a window reads one device
	f'avg({IN}, where=home, stale=1)',          # stale= is a duration
	f'avg({IN}, where=home, window=3h)',
	f'count()',
	f'count(1, 2)',
	f'avg({IN}, where=1)',
])
def test_place_forms_that_are_rejected(text):
	with pytest.raises(ExpressionError):
		Expression.parse(text)


# -- at() of a calculation ------------------------------------------------------------

def _hourlyTemperatures(*values):
	return [(t, Fahrenheit(v)) for t, v in hourly(*values)]


def test_at_reads_a_whole_expression_as_it_was_then():
	resolver = FakeResolver(
		current={TEMP: Fahrenheit(59), DEW: Fahrenheit(40)},
		series={TEMP: _hourlyTemperatures(*[50 + i for i in range(10)]), DEW: _hourlyTemperatures(*[40] * 10)},
	)
	now = datetime(2026, 10, 4, 9, 0, tzinfo=timezone(timedelta(hours=-5)))
	assert float(Expression.parse(f'{TEMP} - {DEW}').evaluate(resolver, now)) == pytest.approx(19)
	assert float(Expression.parse(f'at({TEMP} - {DEW}, -3h)').evaluate(resolver, now)) == pytest.approx(16)


def test_at_of_an_expression_reports_each_key_as_a_point():
	expression = Expression.parse(f'at({TEMP} - {DEW}, -3h)')
	assert {(p.key, p.offset) for p in expression.points} == {(CategoryItem(TEMP), timedelta(hours=-3)), (CategoryItem(DEW), timedelta(hours=-3))}
	assert not expression.keys


def test_at_of_an_expression_still_needs_an_offset():
	with pytest.raises(ExpressionError):
		Expression.parse(f'at({TEMP} - {DEW})')
