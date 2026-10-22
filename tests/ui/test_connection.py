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
		panel.delete()
		_drop(sandbox)
	assert engine.refcount(computedKey) == before, 'deleting the panel gives its lease back'


def test_setting_key_on_the_item_goes_through_the_connection(dashboard):
	sandbox, panel = _panel(dashboard, key=KEY)
	try:
		panel.key = 'environment.humidity.humidity'
		assert str(panel.connection.key) == 'environment.humidity.humidity'
		assert panel.state['key'] == 'environment.humidity.humidity'
	finally:
		_drop(sandbox)


# -- where ------------------------------------------------------------------------

class _Placed:
	def __init__(self, **places):
		self.places = places


@pytest.fixture
def house(monkeypatch):
	from LevityDash import LevityDashboard
	placed = [_Placed(bedroom='home.upstairs.bedroom'), _Placed(office='home.upstairs.office', kitchen='home.downstairs.kitchen')]
	# The loader is the one place a display finds its plugins; iterating it is all `where` needs.
	monkeypatch.setattr(type(LevityDashboard.plugins), '__iter__', lambda self: iter(placed))


@pytest.mark.parametrize('item', [
	{'key': 'indoor.temperature.temperature', 'where': 'home.upstairs.bedroom'},
	{'connection': {'key': 'indoor.temperature.temperature', 'where': 'Home.Upstairs.Bedroom'}},
	{'where': 'home.upstairs.bedroom', 'key': 'indoor.temperature.temperature'},
], ids=['flat', 'nested', 'where-first'])
def test_where_scopes_the_key_to_the_one_device_there(dashboard, house, item):
	sandbox, panel = _panel(dashboard, **item)
	try:
		assert str(panel.key) == 'indoor.temperature.temperature#bedroom'
	finally:
		_drop(sandbox)


def test_where_saves_back_with_the_unscoped_key(dashboard, house):
	sandbox, panel = _panel(dashboard, key='indoor.temperature.temperature', where='home.upstairs.bedroom')
	try:
		state = panel.state
		assert state['key'] == 'indoor.temperature.temperature'
		assert state['where'] == 'home.upstairs.bedroom'
	finally:
		_drop(sandbox)


@pytest.mark.parametrize('where, why', [
	('home.upstairs', 'several'),     # bedroom and office
	('home.garage', 'none'),
	('home..up', 'invalid'),
], ids=['several', 'none', 'invalid'])
def test_where_that_does_not_name_one_device_leaves_the_key_alone(dashboard, house, where, why):
	sandbox, panel = _panel(dashboard, key='indoor.temperature.temperature', where=where)
	try:
		assert str(panel.key) == 'indoor.temperature.temperature'
	finally:
		_drop(sandbox)


def test_where_does_not_override_a_key_that_names_a_device(dashboard, house):
	sandbox, panel = _panel(dashboard, key='indoor.temperature.temperature#office', where='home.upstairs.bedroom')
	try:
		assert str(panel.key) == 'indoor.temperature.temperature#office'
	finally:
		_drop(sandbox)


# -- period -----------------------------------------------------------------------

TEMP = 'environment.temperature.temperature'


def test_period_opens_the_matching_expression(dashboard):
	sandbox, panel = _panel(dashboard, key=TEMP, period='yesterday', using='high')
	try:
		assert panel._keySource.text == f'max({TEMP}, yesterday)'
	finally:
		panel.delete()
		_drop(sandbox)


def test_period_saves_back_with_the_key_as_written(dashboard):
	sandbox, panel = _panel(dashboard, key=TEMP, period='3h', using='avg')
	try:
		state = panel.state
		assert state['key'] == TEMP
		assert (state['period'], state['using']) == ('3h', 'avg')
	finally:
		panel.delete()
		_drop(sandbox)


def test_period_and_where_together(dashboard, house):
	sandbox, panel = _panel(dashboard, key='indoor.temperature.temperature', where='home.upstairs.bedroom', period='today', using='min')
	try:
		assert panel._keySource.text == 'min(indoor.temperature.temperature#bedroom, today)'
		state = panel.state
		assert state['key'] == 'indoor.temperature.temperature'
		assert state['where'] == 'home.upstairs.bedroom'
	finally:
		panel.delete()
		_drop(sandbox)
