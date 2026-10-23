"""`when:` as a size condition: the window or the parent's size, read in the frontend, alone or with `and:`."""
import pytest
from PySide6.QtCore import QRectF

from tests.conftest import pump
from LevityDash.lib.plugins.computed import computedEngine
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Containers.Switch import Switch

RAINING = 'environment.precipitation.precipitation > 0'


@pytest.fixture
def window(dashboard):
	"""The scene's rect, put back after the test."""
	scene = dashboard.scene
	saved = QRectF(scene.sceneRect())

	def resize(width, height):
		scene.setSceneRect(QRectF(0, 0, width, height))
		pump(dashboard.app, 0.1)

	yield resize
	scene.setSceneRect(saved)
	pump(dashboard.app, 0.2)


@pytest.fixture
def slot(dashboard):
	box = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '40%', 'height': '30%'})
	yield box
	if box.scene() is not None:
		box.scene().removeItem(box)


def make(slot, when, **extra):
	slot.state = {'items': [{'type': 'group', 'name': 'sized', 'when': when, **extra}]}
	return next(c for c in slot.childItems() if getattr(c, 'stateName', None) == 'sized')


def test_the_item_follows_the_window_width(dashboard, slot, window):
	window(1000, 600)
	item = make(slot, {'min-width': '900px'})
	assert item.isVisible()
	window(800, 600)
	assert not item.isVisible()
	window(1600, 600)
	assert item.isVisible()


def test_orientation_follows_the_window_shape(dashboard, slot, window):
	window(600, 1000)
	portrait = make(slot, {'orientation': 'portrait'})
	assert portrait.isVisible()
	window(1000, 600)
	assert not portrait.isVisible()


def test_the_parent_is_the_scope_when_asked(dashboard, slot, window):
	window(1000, 600)
	wide = slot.rect().width()
	item = make(slot, {'of': 'parent', 'min-width': wide + 50})
	assert not item.isVisible()
	narrow = make(slot, {'of': 'parent', 'max-width': wide + 50})
	assert narrow.isVisible()


def test_a_size_condition_does_not_touch_the_plugin_layer(dashboard, slot, window):
	window(1000, 600)
	before = set(computedEngine()._entries)
	make(slot, {'min-width': 900})
	assert set(computedEngine()._entries) == before


def test_and_needs_the_data_too(dashboard, slot, window):
	window(1000, 600)
	item = make(slot, {'min-width': 900, 'and': RAINING})
	assert not item.isVisible()  # wide enough, but no rain value yet
	engine = computedEngine()
	key = item.condition._binding.source.key
	engine._publish(engine._entries[key], True)
	dashboard.wait_until(lambda: item.isVisible(), message='size and rain both hold')
	window(700, 600)
	assert not item.isVisible()
	window(1000, 600)
	engine._publish(engine._entries[key], False)
	dashboard.wait_until(lambda: not item.isVisible(), message='the rain stops')


def test_a_bad_condition_hides_the_item_and_loads_the_rest(dashboard, slot, window):
	window(1000, 600)
	item = make(slot, {'min-width': '50%'})
	assert not item.isVisible()


def test_a_switch_picks_the_first_size_that_fits(dashboard, slot, window):
	window(1000, 600)
	slot.state = {'items': [{'type': 'switch', 'hold': 0, 'fade': 0, 'name': 'slot', 'items': [
		{'type': 'group', 'name': 'big', 'when': {'min-width': 900}},
		{'type': 'group', 'name': 'small'},
	]}]}
	switch = next(c for c in slot.childItems() if isinstance(c, Switch))
	name = lambda: switch.active.stateName if switch.active is not None else None  # noqa: E731
	dashboard.wait_until(lambda: name() == 'big', message='the wide layout')
	window(700, 600)
	dashboard.wait_until(lambda: name() == 'small', message='the narrow layout')


def test_the_condition_saves_back_as_written(dashboard, slot, window):
	window(1000, 600)
	item = make(slot, {'min-width': '900px', 'orientation': 'landscape'})
	assert item.when == {'min-width': '900px', 'orientation': 'landscape'}
