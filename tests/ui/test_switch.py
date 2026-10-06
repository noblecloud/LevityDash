"""The `switch` slot: choose among children by `when:`, with a hold time and optional cycling."""
import pytest

from tests.conftest import pump
from LevityDash.lib.plugins.computed import computedEngine
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Containers.Switch import Switch
from LevityDash.lib.ui.frontends.PySide.Modules.condition import parseSeconds

RAINING = 'environment.precipitation.precipitation > 0'
WINDY = 'environment.wind.speed.speed > 20'


@pytest.fixture
def slot(dashboard):
	box = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '10%', 'height': '10%'})
	yield box
	if box.scene() is not None:
		box.scene().removeItem(box)


def make(slot, **settings) -> Switch:
	state = {'type': 'switch', 'hold': 0, 'fade': 0, 'name': 'slot', **settings}
	state.setdefault('items', [
		{'type': 'group', 'name': 'rain', 'when': RAINING},
		{'type': 'group', 'name': 'uv'},
	])
	slot.state = {'items': [state]}
	return next(c for c in slot.childItems() if isinstance(c, Switch))


def child(switch, name):
	return next(c for c in switch.choices if c.stateName == name)


def feed(switch, name, value):
	engine = computedEngine()
	key = child(switch, name).condition._binding.source.key
	engine._publish(engine._entries[key], value)


def test_parse_seconds():
	assert parseSeconds('30s') == 30
	assert parseSeconds('500ms') == pytest.approx(0.5)
	assert parseSeconds('2m') == 120
	assert parseSeconds(5) == 5
	assert parseSeconds('soon', 7) == 7
	assert parseSeconds(None, 3) == 3


def test_default_shows_until_the_condition_holds(dashboard, slot):
	switch = make(slot)
	rain, uv = child(switch, 'rain'), child(switch, 'uv')
	assert switch.active is uv and uv.isVisible() and not rain.isVisible()

	feed(switch, 'rain', True)
	dashboard.wait_until(lambda: switch.active is rain, message='rain takes the slot')
	assert rain.isVisible() and not uv.isVisible()

	feed(switch, 'rain', False)
	dashboard.wait_until(lambda: switch.active is uv, message='uv comes back')
	assert uv.isVisible() and not rain.isVisible()


def test_children_fill_the_slot(dashboard, slot):
	switch = make(slot)
	for c in switch.choices:
		assert c.rect().size() == switch.rect().size()


def test_a_missing_value_is_false(dashboard, slot):
	switch = make(slot)
	assert switch.active is child(switch, 'uv')


def test_bad_when_counts_as_false_and_does_not_raise(dashboard, slot):
	switch = make(slot, items=[
		{'type': 'group', 'name': 'bad', 'when': 'import os'},
		{'type': 'group', 'name': 'bad2', 'when': '((('},
		{'type': 'group', 'name': 'uv'},
	])
	assert switch.active is child(switch, 'uv')


def test_no_match_and_no_default_shows_nothing(dashboard, slot):
	switch = make(slot, items=[{'type': 'group', 'name': 'rain', 'when': RAINING}])
	assert switch.active is None
	assert not child(switch, 'rain').isVisible()


def test_hold_stops_flapping(dashboard, slot):
	switch = make(slot, hold='0.4s')
	rain, uv = child(switch, 'rain'), child(switch, 'uv')
	feed(switch, 'rain', True)
	dashboard.app.processEvents()
	assert switch.active is uv, 'the change is held, not applied at once'
	feed(switch, 'rain', False)  # back before the hold ends
	pump(dashboard.app, 0.7)
	assert switch.active is uv
	feed(switch, 'rain', True)
	dashboard.wait_until(lambda: switch.active is rain, timeout=3, message='a change that lasts goes through')


def test_cycle_takes_turns_among_matches(dashboard, slot):
	switch = make(slot, cycle='0.15s', items=[
		{'type': 'group', 'name': 'a', 'when': True},
		{'type': 'group', 'name': 'b', 'when': True},
		{'type': 'group', 'name': 'c', 'when': False},
	])
	seen = []
	a, b = child(switch, 'a'), child(switch, 'b')
	dashboard.wait_until(lambda: (seen.append(switch.active) or True) and {a, b} <= set(seen), timeout=3, message='both matching children get a turn')
	assert child(switch, 'c') not in seen
	assert sum(c.isVisible() for c in switch.choices) == 1


def test_cycle_stops_with_one_match(dashboard, slot):
	switch = make(slot, cycle='0.1s', items=[
		{'type': 'group', 'name': 'a', 'when': True},
		{'type': 'group', 'name': 'b', 'when': False},
	])
	assert not switch._cycleTimer.isActive()


def test_reload_keeps_the_children_and_leases(dashboard, slot):
	engine = computedEngine()
	switch = make(slot)
	rain = child(switch, 'rain')
	key = rain.condition._binding.source.key
	assert engine.refcount(key) == 1
	make(slot)
	assert child(switch, 'rain') is rain
	assert engine.refcount(key) == 1


def test_removing_the_slot_releases_the_source(dashboard, slot):
	engine = computedEngine()
	switch = make(slot)
	key = child(switch, 'rain').condition._binding.source.key
	slot.scene().removeItem(slot)
	assert engine.refcount(key) == 0


def test_when_on_a_plain_panel_hides_it(dashboard, slot):
	slot.state = {'items': [{'type': 'group', 'name': 'solo', 'when': WINDY}]}
	solo = next(c for c in slot.childItems() if isinstance(c, Panel) and c.stateName == 'solo')
	assert not solo.isVisible()
	engine = computedEngine()
	key = solo.condition._binding.source.key
	engine._publish(engine._entries[key], True)
	dashboard.wait_until(lambda: solo.isVisible(), message='shows while the condition holds')
