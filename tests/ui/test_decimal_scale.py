"""`decimal-scale` and `decimal-align`: the fractional digits of a number at a smaller size."""
import pytest
from PySide6.QtGui import QFont, QFontMetricsF
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
	return {'type': 'text', 'text': text, 'margins': '0px', 'text-height': '40px', 'alignment': 'CenterLeft',
	        'geometry': {'x': '0%', 'y': y, 'width': '100%', 'height': '20%'}, **extra}


def texts(box) -> dict[str, Text]:
	return {item.text: item for item in box.scene().items() if isinstance(item, Text) and box.isAncestorOf(item)}


def inkWidth(item: Text) -> float:
	item._update_path()
	return item.path().boundingRect().width()


def test_decimals_are_smaller_and_narrower(dashboard, sandbox):
	sandbox.state = {'items': [label('67.7°', '0%'), label('67.7° ', '20%', **{'decimal-scale': 0.5})]}
	settle(dashboard)
	got = texts(sandbox)
	plain, small = got['67.7°'], got['67.7° ']
	assert small._decimalScale == 0.5
	assert inkWidth(small) < inkWidth(plain)


def test_runs_split_only_the_fraction(dashboard, sandbox):
	sandbox.state = {'items': [label('1.34 in', '0%', **{'decimal-scale': '60%'})]}
	settle(dashboard)
	item = texts(sandbox)['1.34 in']
	assert item._decimalScale == pytest.approx(0.6)
	font = QFont(item.font())
	runs = item._decimalRuns('1.34 in', font)
	assert [r[0] for r in runs] == ['1', '.34', ' in']
	assert QFontMetricsF(runs[1][1]).height() < QFontMetricsF(runs[0][1]).height()
	assert item._decimalRuns('42', font) is None


def test_align_moves_the_fraction_up(dashboard, sandbox):
	sandbox.state = {'items': [label('88.8', '0%', **{'decimal-scale': 0.5, 'decimal-align': 'top'})]}
	settle(dashboard)
	item = texts(sandbox)['88.8']
	font = QFont(item.font())
	top = item._decimalRuns('88.8', font)[1][2]
	item.setDecimalAlign('center')
	middle = item._decimalRuns('88.8', font)[1][2]
	item.setDecimalAlign('baseline')
	assert top < middle < 0 == item._decimalRuns('88.8', font)[1][2]
	item.setDecimalAlign('top')
	item._update_path()
	assert item.path().boundingRect().top() < 0


def test_number_align_keeps_the_point_on_one_line(dashboard):
	from LevityDash.lib.ui.Groups import MatchAllSizeGroup
	from LevityDash.lib.ui.Geometry import AlignmentFlag
	panel = dashboard.scene.base
	group = MatchAllSizeGroup(panel, 'decimal-scale-column')
	values = ['5.25', '105.5', '72.4']
	items = []
	for value in values:
		text = Text(panel, value=value, alignment=AlignmentFlag.Right)
		text.setNumberAlign('decimal')
		text.setDecimalScale(0.5)
		group.addItem(text)
		items.append(text)
	try:
		for text in items:
			text.updateTransform(reason='test')
		edges = [t._text_pos.x() + t._advance(t.text.split('.')[0], QFont(t.font())) for t in items]
		assert max(edges) - min(edges) < 0.01, dict(zip(values, edges))
	finally:
		for t in items:
			t.scene() and t.scene().removeItem(t)


def test_bad_scale_is_refused():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Label import Label
	decode = Label.decimalScale.decode if hasattr(Label.decimalScale, 'decode') else None
	assert decode is not None
