"""A Realtime item's connection: `key:` / `source:` flat, a bare `connection:`, or nested.

`Realtime.keyAndSource` is an `unwrap` property over `Connection`, the same
mechanism as `TitleValueSplitter.title`, so the item's own `key:` feeds the
connection. `Realtime.connection` loads the nested and bare forms. Save writes
the flat form, and a connection with only a key saves as the short `key:`.
"""
import pytest

from LevityDash.lib.plugins.computed import computedEngine
from LevityDash.lib.plugins.expressions import Expression
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime import Connection, Realtime

KEY = 'environment.temperature.temperature'
EXPR = 'max(environment.temperature.temperature, today)'
GEOMETRY = {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'}


def _panel(dashboard, **item):
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '10%', 'height': '10%'})
	sandbox.state = {'items': [{'type': 'realtime.text', 'name': 'connected', 'geometry': GEOMETRY, **item}]}
	dashboard.app.processEvents()
	return sandbox, next(c for c in sandbox.childPanels if isinstance(c, Realtime))


def _drop(sandbox):
	sandbox.scene().removeItem(sandbox)


@pytest.mark.parametrize('item', [
	{'key': KEY},
	{'connection': KEY},
	{'connection': {'key': KEY}},
], ids=['flat', 'bare', 'nested'])
def test_every_form_loads_the_same_key(dashboard, item):
	sandbox, panel = _panel(dashboard, **item)
	try:
		assert str(panel.key) == KEY
		assert isinstance(panel.connection, Connection)
		assert panel.connection.owner is panel
	finally:
		_drop(sandbox)


@pytest.mark.parametrize('item', [
	{'key': KEY},
	{'connection': KEY},
	{'connection': {'key': KEY}},
], ids=['flat', 'bare', 'nested'])
def test_a_key_only_connection_saves_as_the_short_key(dashboard, item):
	sandbox, panel = _panel(dashboard, **item)
	try:
		state = panel.state
		assert state['key'] == KEY
		assert 'connection' not in state
		assert 'source' not in state
	finally:
		_drop(sandbox)


def test_source_loads_flat_and_nested_and_saves_flat(dashboard):
	for item in ({'key': KEY, 'source': 'any'}, {'connection': {'key': KEY, 'source': 'any'}}):
		sandbox, panel = _panel(dashboard, **item)
		try:
			assert str(panel.key) == KEY
			assert panel._preferredSourceName == 'any'
			state = panel.state
			assert state['key'] == KEY
			assert 'connection' not in state
		finally:
			_drop(sandbox)


def test_an_expression_key_saves_as_its_text(dashboard):
	engine = computedEngine()
	computedKey = Expression.parse(EXPR).key
	before = engine.refcount(computedKey)
	sandbox, panel = _panel(dashboard, connection=EXPR)
	try:
		assert engine.refcount(computedKey) == before + 1
		assert panel.state['key'] == EXPR
	finally:
		_drop(sandbox)


def test_setting_key_on_the_item_goes_through_the_connection(dashboard):
	sandbox, panel = _panel(dashboard, key=KEY)
	try:
		panel.key = 'environment.humidity.humidity'
		assert str(panel.connection.key) == 'environment.humidity.humidity'
		assert panel.state['key'] == 'environment.humidity.humidity'
	finally:
		_drop(sandbox)
