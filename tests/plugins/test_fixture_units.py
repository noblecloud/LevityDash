from LevityDash.lib.plugins.builtin.Fixture import buildSchema


def test_a_daily_total_keeps_its_time_unit():
	"""`unit: in` on a daily total must stay a rate-shaped unit, not a plain inch (a length)."""
	schema, _ = buildSchema({'keys': {'environment.precipitation.daily': {'value': 3.9, 'unit': 'in'}}})
	assert schema['environment.precipitation.daily']['sourceUnit'] == ['in', 'day']


def test_a_scenario_pair_is_used_as_written():
	schema, _ = buildSchema({'keys': {'environment.precipitation.precipitation': {'value': 1.4, 'unit': ['in', 'hr']}}})
	assert schema['environment.precipitation.precipitation']['sourceUnit'] == ['in', 'hr']


def test_power_energy_and_area_units_are_in_the_unit_table():
	import pytest
	import WeatherUnits as wu
	from LevityDash.lib.plugins.schema.units import unitDict
	for text, cls in (('W', wu.Power), ('kW', wu.Power), ('hp', wu.Power), ('kWh', wu.Energy), ('J', wu.Energy), ('m²', wu.Area), ('ha', wu.Area), ('ft²', wu.Area)):
		value = unitDict[text](2)
		assert isinstance(value, cls), text
		assert float(value) == pytest.approx(2), text


def test_a_scenario_can_name_a_power_and_an_energy():
	schema, _ = buildSchema({'keys': {'house.power.net': {'value': 3.4, 'unit': 'kW'}, 'house.energy.today': {'value': 18, 'unit': 'kWh'}}})
	assert schema['house.power.net']['sourceUnit'] == 'kW'
	assert schema['house.energy.today']['sourceUnit'] == 'kWh'
