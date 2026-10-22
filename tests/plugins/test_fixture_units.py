from LevityDash.lib.plugins.builtin.Fixture import buildSchema


def test_a_daily_total_keeps_its_time_unit():
	"""`unit: in` on a daily total must stay a rate-shaped unit, not a plain inch (a length)."""
	schema, _ = buildSchema({'keys': {'environment.precipitation.daily': {'value': 3.9, 'unit': 'in'}}})
	assert schema['environment.precipitation.daily']['sourceUnit'] == ['in', 'day']


def test_a_scenario_pair_is_used_as_written():
	schema, _ = buildSchema({'keys': {'environment.precipitation.precipitation': {'value': 1.4, 'unit': ['in', 'hr']}}})
	assert schema['environment.precipitation.precipitation']['sourceUnit'] == ['in', 'hr']


def test_there_is_one_unit_table():
	from LevityDash.lib.plugins.schema.units import unitDict as old
	from LevityDash.lib.plugins.utils import unitDict
	assert old is unitDict


def test_power_energy_and_area_units_are_in_the_unit_table():
	import pytest
	import unitcorn as wu
	from LevityDash.lib.plugins.utils import unitDict
	for text, cls in (('W', wu.Power), ('kW', wu.Power), ('hp', wu.Power), ('kWh', wu.Energy), ('J', wu.Energy), ('m²', wu.Area), ('ha', wu.Area), ('ft²', wu.Area)):
		value = unitDict[text](2)
		assert isinstance(value, cls), text
		assert float(value) == pytest.approx(2), text


def test_a_scenario_can_name_a_power_and_an_energy():
	schema, _ = buildSchema({'keys': {'house.power.net': {'value': 3.4, 'unit': 'kW'}, 'house.energy.today': {'value': 18, 'unit': 'kWh'}}})
	assert schema['house.power.net']['sourceUnit'] == 'kW'
	assert schema['house.energy.today']['sourceUnit'] == 'kWh'


def test_a_scenario_with_kw_loads_as_a_power_and_does_energy_sums(tmp_path, monkeypatch):
	"""`unit: kW` in a scenario goes through the real plugin schema, and the value takes part in expressions."""
	import unitcorn as wu
	from datetime import datetime, timedelta, timezone
	from LevityDash.lib.plugins.builtin.Fixture import ENV_VAR, Fixture
	from LevityDash.lib.plugins.expressions import Expression
	from LevityDash.lib.plugins.categories import CategoryItem

	scenario = tmp_path / 'power.yaml'
	scenario.write_text('name: power\nkeys:\n  house.power.net: {value: 5, unit: kW}\n  house.energy.today: {value: 18, unit: kWh}\n')
	monkeypatch.setenv(ENV_VAR, str(scenario))
	schema = Fixture().schema
	power = schema['house.power.net'].getConvertFunc()(5.0)
	energy = schema['house.energy.today'].getConvertFunc()(18.0)
	assert isinstance(power, wu.Power) and isinstance(energy, wu.Energy)

	class Resolver:
		def current(self, key):
			return {'house.power.net': power, 'house.energy.today': energy}.get(str(key))

	now = datetime(2026, 10, 4, 15, 0, tzinfo=timezone(timedelta(hours=-5)))
	assert isinstance(Expression.parse('house.power.net * 1h').evaluate(Resolver(), now), wu.Energy)
	assert Expression.parse('house.power.net > 4 kW').evaluate(Resolver(), now) is True
	assert Expression.parse('house.energy.today > 20 kWh').evaluate(Resolver(), now) is False
