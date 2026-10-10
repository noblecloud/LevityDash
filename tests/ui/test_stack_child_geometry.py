"""A stack sizes its children along its direction; a child's `geometry:` there stands in for `size:`."""
import pytest

from tests.conftest import pump
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Containers.Stacks import Stack


@pytest.fixture
def slot(dashboard):
	box = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '50%', 'height': '50%'})
	yield box
	if box.scene() is not None:
		box.scene().removeItem(box)


def build(slot, direction, items) -> Stack:
	slot.state = {'items': [{'type': 'stack', 'direction': direction, 'spacing': '0px', 'items': items}]}
	return next(c for c in slot.childItems() if isinstance(c, Stack))


def spans(stack, attr):
	"""Child extents in layout order (`childPanels` is in z-order, not stack order)."""
	rects = sorted((c.sceneBoundingRect() for c in stack.childPanels), key=lambda r: (r.y(), r.x()))
	return [getattr(r, attr)() for r in rects]


def test_geometry_height_sizes_a_vertical_child(dashboard, slot):
	stack = build(slot, 'Vertical', [
		{'type': 'group', 'geometry': {'height': '50%'}},
		{'type': 'group', 'size': '20%'},
		{'type': 'group'},
	])
	pump(dashboard.app, 0.3)
	heights = spans(stack, 'height')
	whole = stack.sceneBoundingRect().height()
	assert heights[0] == pytest.approx(whole * 0.5, abs=1)
	assert heights[1] == pytest.approx(whole * 0.2, abs=1)
	assert heights[2] == pytest.approx(whole * 0.3, abs=1)


def test_geometry_width_sizes_a_horizontal_child(dashboard, slot):
	stack = build(slot, 'Horizontal', [
		{'type': 'group', 'geometry': {'width': '60%'}},
		{'type': 'group'},
	])
	pump(dashboard.app, 0.3)
	widths = spans(stack, 'width')
	whole = stack.sceneBoundingRect().width()
	assert widths[0] == pytest.approx(whole * 0.6, abs=1)
	assert widths[1] == pytest.approx(whole * 0.4, abs=1)


def test_explicit_size_beats_geometry(dashboard, slot):
	stack = build(slot, 'Vertical', [
		{'type': 'group', 'size': '25%', 'geometry': {'height': '75%'}},
		{'type': 'group'},
	])
	pump(dashboard.app, 0.3)
	assert spans(stack, 'height')[0] == pytest.approx(stack.sceneBoundingRect().height() * 0.25, abs=1)


def test_item_size_max_caps_each_child(dashboard, slot):
	"""`item-size-max` used to crash the stack on a typo (`meaxCellSize`)."""
	slot.state = {'items': [{
		'type': 'stack', 'direction': 'Vertical', 'spacing': '0px',
		'item-size-max': '20%',
		'items': [{'type': 'group'}, {'type': 'group'}],
	}]}
	stack = next(c for c in slot.childItems() if isinstance(c, Stack))
	pump(dashboard.app, 0.3)
	whole = stack.sceneBoundingRect().height()
	assert all(h <= whole * 0.2 + 1 for h in spans(stack, 'height'))
