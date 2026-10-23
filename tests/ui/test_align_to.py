"""`align-to:` puts a point of an item on a point of a named sibling."""
import pytest

from tests.conftest import pump
from LevityDash.lib.ui.frontends.PySide.Modules import Panel


@pytest.fixture
def slot(dashboard):
	box = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'})
	yield box
	if box.scene() is not None:
		box.scene().removeItem(box)


def build(dashboard, slot, items):
	slot.state = {'items': [{'type': 'group', 'items': items}]}
	pump(dashboard.app, 0.3)
	group = next(c for c in slot.childItems() if hasattr(c, 'childPanels'))
	return group, {c.stateName: c for c in group.childPanels if c.stateName}


def box(item):
	r = item.parentItem().mapRectFromItem(item, item.rect())
	return r.x(), r.y(), r.width(), r.height()


def test_centre_on_a_sibling_and_below_it(dashboard, slot):
	group, kids = build(dashboard, slot, [
		{'type': 'group', 'name': 'a', 'geometry': {'x': '10%', 'y': '10%', 'width': '40%', 'height': '30%'}},
		{'type': 'group', 'name': 'b', 'geometry': {'width': '20%', 'height': '10%'}, 'align-to': {'to': 'a', 'x': 'center', 'y': 'bottom', 'self-y': 'top'}},
	])
	a, b = box(kids['a']), box(kids['b'])
	assert b[0] + b[2] / 2 == pytest.approx(a[0] + a[2] / 2, abs=1)
	assert b[1] == pytest.approx(a[1] + a[3], abs=1)


def test_a_string_centres_both_ways_and_an_unnamed_axis_keeps_its_place(dashboard, slot):
	group, kids = build(dashboard, slot, [
		{'type': 'group', 'name': 'a', 'geometry': {'x': '10%', 'y': '10%', 'width': '40%', 'height': '30%'}},
		{'type': 'group', 'name': 'b', 'geometry': {'width': '10%', 'height': '10%'}, 'align-to': 'a'},
		{'type': 'group', 'name': 'c', 'geometry': {'x': '70%', 'y': '70%', 'width': '10%', 'height': '10%'}, 'align-to': {'to': 'a', 'x': 'right'}},
	])
	a, b, c = (box(kids[n]) for n in 'abc')
	assert (b[0] + b[2] / 2, b[1] + b[3] / 2) == pytest.approx((a[0] + a[2] / 2, a[1] + a[3] / 2), abs=1)
	assert c[0] == pytest.approx(a[0] + a[2], abs=1) and c[1] == pytest.approx(group.rect().height() * 0.7, abs=1)


def test_it_follows_the_sibling_when_the_dashboard_is_resized(dashboard, slot):
	group, kids = build(dashboard, slot, [
		{'type': 'group', 'name': 'a', 'geometry': {'x': '10%', 'y': '10%', 'width': '40%', 'height': '30%'}},
		{'type': 'group', 'name': 'b', 'geometry': {'width': '10%', 'height': '10%'}, 'align-to': {'to': 'a', 'x': 'right', 'self-x': 'left'}},
	])
	slot.setRect(0, 0, slot.rect().width() / 2, slot.rect().height())
	slot.signals.resized.emit(slot.rect())
	pump(dashboard.app, 0.2)
	a, b = box(kids['a']), box(kids['b'])
	assert b[0] == pytest.approx(a[0] + a[2], abs=1)


def test_a_missing_sibling_is_quiet_and_round_trips():
	from LevityDash.lib.layout.anchor import Anchor
	assert Anchor.decode({'to': 'a', 'x': 'left', 'self-x': 'right', 'offset': {'x': '2mm'}}).encode() == {'to': 'a', 'x': 'left', 'self-x': 'right', 'offset': {'x': '2mm'}}
