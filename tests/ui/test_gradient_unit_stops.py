"""Gradient stops pinned to unit values: the parse and convert maths, and the YAML forms."""
import pytest
import WeatherUnits as wu

from LevityDash.lib.ui.colors.stopunits import StopUnitError, formatStop, parseStop, toDataUnit
from LevityDash.lib.ui.colors.gradient import Gradient


def test_parse():
	assert parseStop('99°F') == (99.0, '°F')
	assert parseStop('30 mph') == (30.0, 'mph')
	assert parseStop('37') == (37.0, None)
	assert parseStop('°') in (None, (None, None))


@pytest.mark.parametrize('number, unit, expected', [
	(0, '°C', 32.0),
	(100, '°C', 212.0),
	(212, '°F', 212.0),
])
def test_convert_to_fahrenheit(number, unit, expected):
	assert float(toDataUnit(number, unit, wu.Temperature.Fahrenheit)) == pytest.approx(expected, abs=1e-3)


def test_celsius_data():
	assert float(toDataUnit(99, '°F', wu.Temperature.Celsius)) == pytest.approx(37.2222, abs=1e-3)


def test_wrong_dimension_raises():
	with pytest.raises(StopUnitError):
		toDataUnit(30, 'mph', wu.Temperature.Fahrenheit)


def test_format():
	assert formatStop(99, '°F') == '99°F'
	assert formatStop(30, 'mph') == '30 mph'


def test_map_and_list_forms_decode_the_same():
	a = Gradient.decode({'32°F': '#4aa3ff', '99°F': '#ff4a4a'})
	b = Gradient.decode([{'at': '32°F', 'color': '#4aa3ff'}, {'at': '99°F', 'color': '#ff4a4a'}])
	assert [s.key for s in a.values()] == [s.key for s in b.values()] == ['32°F', '99°F']


def test_pinned_stops_round_trip_in_their_unit():
	g = Gradient.decode({'32°F': '#4aa3ff', '37°C': '#ff4a4a'})
	assert [s.key for s in g.values()] == ['32°F', '37°C']


def test_resolve_converts_to_the_data_unit_and_skips_a_bad_stop():
	g = Gradient.decode({'32°F': '#4aa3ff', '30 mph': '#00ff00', '37°C': '#ff4a4a'})
	r = g.resolve(wu.Temperature.Fahrenheit)
	values = sorted(round(float(s.value), 1) for s in r.values())
	assert values == [32.0, 98.6]
