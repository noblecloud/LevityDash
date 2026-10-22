"""The closed set of value shapes (lib/plugins/shapes.py)."""
import logging

import pytest

from LevityDash.lib.plugins import shapes
from LevityDash.lib.plugins.shapes import SHAPES, choicesOf, shapeOf


def test_the_set_is_closed_and_ordered_numbers_first():
	assert SHAPES == ('number', 'enum', 'text', 'time', 'list', 'point')


@pytest.mark.parametrize('entry, expected', [
	({'type': 'temperature', 'sourceUnit': 'f'}, 'number'),
	({'type': 'wind', 'sourceUnit': ['mi', 'hr']}, 'number'),
	({'type': 'summary', 'sourceUnit': 'str'}, 'text'),
	({'sourceUnit': 'timezone'}, 'text'),
	({'type': 'datetime', 'sourceUnit': 'ISO8601'}, 'time'),
	({'type': 'datetime', 'sourceUnit': 'datetime'}, 'time'),
	({'type': 'date', 'sourceUnit': 'epoch'}, 'time'),
	({'sourceUnit': 'bool'}, 'enum'),
	({'sourceUnit': 'AQIHC'}, 'enum'),
	({'type': 'icon', 'sourceUnit': 'int'}, 'enum'),
	({'sourceUnit': 'WeatherCode'}, 'enum'),
	({}, 'number'),
])
def test_the_shape_comes_from_the_unit_and_type(entry, expected):
	assert shapeOf(entry) == expected


def test_an_explicit_shape_wins():
	assert shapeOf({'sourceUnit': 'str', 'shape': 'enum'}) == 'enum'
	assert shapeOf({'sourceUnit': 'f', 'shape': 'time'}) == 'time'


def test_a_name_outside_the_set_is_logged_once_and_ignored(caplog):
	shapes._warned.clear()
	with caplog.at_level(logging.WARNING, logger='LevityDash.shapes'):
		assert shapeOf({'sourceUnit': 'f', 'shape': 'blob'}) == 'number'
		assert shapeOf({'sourceUnit': 'f', 'shape': 'blob'}) == 'number'
	assert len([r for r in caplog.records if 'blob' in r.getMessage()]) == 1


def test_a_reserved_shape_is_kept_and_logged_once(caplog):
	shapes._warned.clear()
	with caplog.at_level(logging.WARNING, logger='LevityDash.shapes'):
		assert shapeOf({'shape': 'list'}) == 'list'
		assert shapeOf({'shape': 'point'}) == 'point'
	assert len([r for r in caplog.records if 'reserved' in r.getMessage()]) == 2


def test_an_enum_names_its_choices():
	assert choicesOf({'sourceUnit': 'bool'}) == (False, True)
	assert choicesOf({'shape': 'enum', 'choices': ['ok', 'warn', 'down']}) == ('ok', 'warn', 'down')
	assert choicesOf({'shape': 'enum'}) is None
	assert choicesOf({'sourceUnit': 'f', 'choices': [1]}) is None  # only an enum has choices


def test_every_builtin_schema_entry_has_a_shape_in_the_set():
	"""Walk the schema of each builtin plugin that writes one as a dict; none may land outside the set."""
	import importlib
	found = 0
	for name in ('OpenMeteo', 'PirateWeather', 'OpenWeatherMap'):
		module = importlib.import_module(f'LevityDash.lib.plugins.builtin.{name}')
		stack = [getattr(module, 'schema', {})]
		while stack:
			node = stack.pop()
			if not isinstance(node, dict):
				continue
			if 'sourceUnit' in node or 'type' in node and isinstance(node['type'], str) and 'sourceKey' in node:
				assert shapeOf(node) in SHAPES
				found += 1
			stack.extend(v for v in node.values() if isinstance(v, dict))
	assert found > 20
