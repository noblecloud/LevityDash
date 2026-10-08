from LevityDash.lib.plugins.builtin.Fixture import buildSchema


def test_a_daily_total_keeps_its_time_unit():
	"""`unit: in` on a daily total must stay a rate-shaped unit, not a plain inch (a length)."""
	schema, _ = buildSchema({'keys': {'environment.precipitation.daily': {'value': 3.9, 'unit': 'in'}}})
	assert schema['environment.precipitation.daily']['sourceUnit'] == ['in', 'day']


def test_a_scenario_pair_is_used_as_written():
	schema, _ = buildSchema({'keys': {'environment.precipitation.precipitation': {'value': 1.4, 'unit': ['in', 'hr']}}})
	assert schema['environment.precipitation.precipitation']['sourceUnit'] == ['in', 'hr']
