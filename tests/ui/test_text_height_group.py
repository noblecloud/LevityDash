"""`text-height` pins the height of a label's text, and a size group keeps its members equal.

Until this the group read the whole box height, both for the tier and for the fit, so a label in a
group ignored its `text-height` and grew to fill its box.
"""
import pytest
from PySide6.QtTest import QTest

from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import Text


@pytest.fixture
def sandbox(dashboard):
	box = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '60%', 'height': '60%'})
	yield box
	if box.scene() is not None:
		box.scene().removeItem(box)


def settle(dashboard):
	for _ in range(8):
		QTest.qWait(20)
		dashboard.app.processEvents()


def label(text, geometry, **extra):
	x, y, w, h = geometry
	return {'type': 'text', 'text': text, 'margins': '0px', 'geometry': {'x': x, 'y': y, 'width': w, 'height': h}, **extra}


def sizes(box) -> dict[str, float]:
	"""Each label's drawn text size in scene pixels: the font size times the fitted scale."""
	out = {}
	for item in box.scene().items():
		if isinstance(item, Text) and box.isAncestorOf(item):
			out[item.text] = item.font().pointSizeF() * item.transform().m22()
	return out


def test_text_height_holds_inside_a_group(dashboard, sandbox):
	group = {'matchingGroup': {'group': 'global.text-height-test', 'matchAll': True}}
	sandbox.state = {'items': [
		label('Short', ('0%', '0%', '45%', '20%'), **{'text-height': '24px'}, **group),
		label('Tall', ('50%', '0%', '45%', '70%'), **{'text-height': '24px'}, **group),
		label('Alone', ('0%', '50%', '45%', '40%'), **{'text-height': '24px'}),
	]}
	settle(dashboard)
	got = sizes(sandbox)
	# Boxes of very different heights, one pinned height: one tier, one size.
	assert got['Short'] == pytest.approx(got['Tall'], rel=0.02)
	# The group gives the same size as a lone label with the same text-height, not the box height.
	assert got['Tall'] == pytest.approx(got['Alone'], rel=0.1)
	assert got['Tall'] < 40


def test_a_wider_member_shrinks_the_whole_group(dashboard, sandbox):
	group = {'matchingGroup': {'group': 'global.text-height-narrow', 'matchAll': True}}
	sandbox.state = {'items': [
		label('A much longer label', ('0%', '0%', '15%', '30%'), **{'text-height': '30px'}, **group),
		label('B', ('50%', '0%', '45%', '60%'), **{'text-height': '30px'}, **group),
	]}
	settle(dashboard)
	got = sizes(sandbox)
	# The narrow box sets the size for every member; none breaks out to its own pinned height.
	assert got['B'] == pytest.approx(got['A much longer label'], rel=0.02)


def test_text_height_in_physical_units_loads(dashboard, sandbox):
	sandbox.state = {'items': [label('Millimetres', ('0%', '0%', '90%', '50%'), **{'text-height': '5mm'})]}
	settle(dashboard)
	assert 'Millimetres' in sizes(sandbox)
