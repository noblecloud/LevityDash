"""`tracking`, `italic` and `outline` on a text item."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetricsF
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


def label(text, y, **extra):
	return {'type': 'text', 'text': text, 'margins': '0px', 'text-height': '30px', 'alignment': 'CenterLeft',
	        'geometry': {'x': '0%', 'y': y, 'width': '100%', 'height': '20%'}, **extra}


def texts(box) -> dict[str, Text]:
	return {item.text: item for item in box.scene().items() if isinstance(item, Text) and box.isAncestorOf(item)}


def width(item: Text) -> float:
	return QFontMetricsF(item.font()).horizontalAdvance('PLAIN')


def test_tracking_opens_and_closes_the_letters(dashboard, sandbox):
	sandbox.state = {'items': [
		label('PLAIN', '0%'),
		label('PLAIN ', '25%', tracking=0.3),
		label(' PLAIN', '50%', tracking='-5%'),
	]}
	settle(dashboard)
	got = texts(sandbox)
	assert width(got['PLAIN ']) > width(got['PLAIN']) * 1.3
	assert width(got[' PLAIN']) < width(got['PLAIN'])


def test_italic_sets_the_font(dashboard, sandbox):
	sandbox.state = {'items': [label('Upright', '0%'), label('Slanted', '25%', italic=True)]}
	settle(dashboard)
	got = texts(sandbox)
	assert got['Slanted'].font().italic()
	assert not got['Upright'].font().italic()


def test_outline_draws_a_line_and_no_fill(dashboard, sandbox):
	sandbox.state = {'items': [
		label('Solid', '0%'),
		label('Hollow', '25%', outline=2),
		label('Both', '50%', outline={'weight': 3, 'color': '#ff0000', 'fill': True}),
	]}
	settle(dashboard)
	got = texts(sandbox)
	assert got['Solid'].pen().style() == Qt.NoPen
	assert got['Hollow'].pen().style() != Qt.NoPen and got['Hollow'].pen().widthF() == 2
	assert got['Hollow'].brush().style() == Qt.NoBrush
	assert got['Both'].brush().style() != Qt.NoBrush
	assert got['Both'].pen().color().name() == '#ff0000'


def test_outline_refuses_a_key_it_does_not_know(dashboard, sandbox):
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Label import Label
	with pytest.raises(ValueError, match='outline takes'):
		Label.outline.decodeValue({'width': 2}, None)
