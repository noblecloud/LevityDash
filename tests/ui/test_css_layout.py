"""`flex:` and `type: grid` on a stack hand its layout to `lib/layout`; a stack without them is untouched."""
import pytest

from tests.conftest import pump
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Containers.Stacks import GridStack, Stack, _checkedKeys


@pytest.fixture
def slot(dashboard):
	box = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '50%', 'height': '50%'})
	yield box
	if box.scene() is not None:
		box.scene().removeItem(box)


def build(dashboard, slot, kind, **state):
	slot.state = {'items': [{'type': kind, 'spacing': '0px', **state}]}
	stack = next(c for c in slot.childItems() if isinstance(c, Stack))
	pump(dashboard.app, 0.3)
	return stack


def rects(stack):
	"""Child scene rects in layout order, as shares of the stack's own rect."""
	whole = stack.sceneBoundingRect()
	return [
		((r.x() - whole.x()) / whole.width(), (r.y() - whole.y()) / whole.height(), r.width() / whole.width(), r.height() / whole.height())
		for r in sorted((c.sceneBoundingRect() for c in stack.childPanels), key=lambda r: (round(r.y()), r.x()))
	]


def test_grow_shares_what_the_fixed_item_leaves(dashboard, slot):
	stack = build(dashboard, slot, 'stack', direction='Horizontal', flex={}, items=[
		{'type': 'group', 'size': '20%'},
		{'type': 'group', 'flex': {'grow': 1}},
		{'type': 'group', 'flex': {'grow': 3}},
	])
	assert [r[2] for r in rects(stack)] == pytest.approx([0.2, 0.2, 0.6], abs=0.01)


def test_shrink_takes_back_in_proportion_to_shrink_times_basis(dashboard, slot):
	stack = build(dashboard, slot, 'stack', direction='Horizontal', items=[
		{'type': 'group', 'flex': {'basis': '80%', 'shrink': 1}},
		{'type': 'group', 'flex': {'basis': '80%', 'shrink': 3}},
	])
	assert [r[2] for r in rects(stack)] == pytest.approx([0.65, 0.35], abs=0.01)


def test_justify_space_between_spreads_fixed_items(dashboard, slot):
	stack = build(dashboard, slot, 'stack', direction='Horizontal', flex={'justify': 'space-between'}, items=[
		{'type': 'group', 'size': '20%'}, {'type': 'group', 'size': '20%'}, {'type': 'group', 'size': '20%'},
	])
	assert [r[0] for r in rects(stack)] == pytest.approx([0.0, 0.4, 0.8], abs=0.01)


def test_order_and_align_items(dashboard, slot):
	stack = build(dashboard, slot, 'stack', direction='Horizontal', flex={'align-items': 'center'}, items=[
		{'type': 'group', 'size': '30%', 'flex': {'cross': '50%'}},
		{'type': 'group', 'size': '30%', 'flex': {'cross': '50%', 'order': -1}},
	])
	found = rects(stack)
	assert [r[0] for r in found] == pytest.approx([0.0, 0.3], abs=0.01)
	assert all(r[1] == pytest.approx(0.25, abs=0.01) and r[3] == pytest.approx(0.5, abs=0.01) for r in found)


def test_a_plain_stack_still_shares_equally(dashboard, slot):
	stack = build(dashboard, slot, 'stack', direction='Horizontal', items=[
		{'type': 'group', 'size': '25%'}, {'type': 'group'}, {'type': 'group'},
	])
	assert [r[2] for r in rects(stack)] == pytest.approx([0.25, 0.375, 0.375], abs=0.01)


def test_grid_places_by_line_and_span(dashboard, slot):
	stack = build(dashboard, slot, 'grid', grid={'columns': ['1fr', '3fr'], 'rows': ['1fr', '1fr']}, items=[
		{'type': 'group', 'grid': {'column': 1, 'row': 1, 'row-span': 2}},
		{'type': 'group', 'grid': {'column': 2, 'row': 1}},
		{'type': 'group', 'grid': {'column': 2, 'row': 2}},
	])
	assert isinstance(stack, GridStack)
	found = rects(stack)
	assert found[0] == pytest.approx((0.0, 0.0, 0.25, 1.0), abs=0.01)
	assert found[1] == pytest.approx((0.25, 0.0, 0.75, 0.5), abs=0.01)
	assert found[2] == pytest.approx((0.25, 0.5, 0.75, 0.5), abs=0.01)


def test_unknown_keys_are_an_error_not_silence():
	assert _checkedKeys({'Grow': 1}, {'grow'}, 'flex') == {'grow': 1}
	with pytest.raises(ValueError, match='nope'):
		_checkedKeys({'grow': 1, 'nope': 2}, {'grow'}, 'flex')
