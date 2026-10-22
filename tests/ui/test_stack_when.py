"""A stack item with `when:` takes no room while the condition is false, so the items after it close up."""
from LevityDash.lib.plugins.computed import computedEngine
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Containers.Stacks import Stack

RAINING = 'environment.precipitation.precipitation > 0'


def _stack(dashboard, items):
	box = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '50%', 'height': '10%'})
	box.state = {'items': [{'type': 'stack', 'direction': 'Horizontal', 'name': 'row', 'items': items}]}
	return box, next(c for c in box.childItems() if isinstance(c, Stack))


def _widths(stack):
	return [round(g.surface.geometry.relativeWidth, 3) for g in stack.geometries.values() if stack._shown(g)]


def test_a_hidden_item_gives_up_its_room(dashboard):
	box, stack = _stack(dashboard, [
		{'type': 'group', 'name': 'a'},
		{'type': 'group', 'name': 'b', 'when': False},
		{'type': 'group', 'name': 'c'},
	])
	try:
		widths = _widths(stack)
		assert len(widths) == 2
		assert widths[0] == widths[1] and widths[0] > 0.45
	finally:
		box.scene().removeItem(box)


def test_the_item_returns_when_its_condition_holds(dashboard):
	box, stack = _stack(dashboard, [
		{'type': 'group', 'name': 'a'},
		{'type': 'group', 'name': 'b', 'when': RAINING},
		{'type': 'group', 'name': 'c'},
	])
	try:
		assert len(_widths(stack)) == 2
		engine = computedEngine()
		b = next(g.surface for g in stack.geometries.values() if g.surface.stateName == 'b')
		engine._publish(engine._entries[b.condition._binding.source.key], True)
		dashboard.wait_until(lambda: len(_widths(stack)) == 3, message='b takes its place')
		assert all(abs(w - 1 / 3) < 0.02 for w in _widths(stack))

		engine._publish(engine._entries[b.condition._binding.source.key], False)
		dashboard.wait_until(lambda: len(_widths(stack)) == 2, message='b gives it back')
	finally:
		box.scene().removeItem(box)
