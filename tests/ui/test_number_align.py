"""Numbers in a size group line up on the number, not on the whole string.

`number-align: decimal` puts every decimal point of a column on one line (a value with no point acts as if it
ended in one); `end` right-aligns the digits. The unit hangs to the right. The printed text is never changed.
"""
import pytest
from PySide6.QtGui import QFontMetricsF

from LevityDash.lib.ui import numberalign
from LevityDash.lib.ui.Groups import MatchAllSizeGroup
from LevityDash.lib.ui.Geometry import AlignmentFlag
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import Text

VALUES = ['72.4°', '44%', '50°', '0', '19.4 mi', '.02']


def _column(dashboard, mode, alignment):
	panel = dashboard.scene.base
	group = MatchAllSizeGroup(panel, f'number-align-{mode}-{alignment.name}')
	texts = []
	for value in VALUES:
		text = Text(panel, value=value, alignment=alignment)
		text.setNumberAlign(mode)
		group.addItem(text)
		texts.append(text)
	for text in texts:
		text.updateTransform(reason='test')
	return texts


def _edge(text, mode) -> float:
	"""Where this text puts the alignment edge, in the item's own coordinates, as drawn."""
	head = numberalign.split(text.text, mode)[0]
	return text._text_pos.x() + QFontMetricsF(text.font()).horizontalAdvance(head)


@pytest.mark.parametrize('mode', numberalign.MODES)
@pytest.mark.parametrize('alignment', [AlignmentFlag.Right, AlignmentFlag.Left, AlignmentFlag.HorizontalCenter])
def test_cuts_land_on_one_line(dashboard, mode, alignment):
	texts = _column(dashboard, mode, alignment)
	try:
		edges = [_edge(t, mode) for t in texts]
		assert max(edges) - min(edges) < 0.01, dict(zip(VALUES, edges))
		assert [t.text for t in texts] == VALUES, 'alignment must not change what is printed'
	finally:
		for t in texts:
			t.scene() and t.scene().removeItem(t)


def test_off_by_default(dashboard):
	text = Text(dashboard.scene.base, value='72.4°')
	assert text._numberAlign is None
	assert text._numberColumn() is None


def test_a_word_is_not_a_number(dashboard):
	"""A compass point keeps its plain placement and adds nothing to the column."""
	panel = dashboard.scene.base
	group = MatchAllSizeGroup(panel, 'number-align-word')
	number, word = Text(panel, value='7.5'), Text(panel, value='WSW')
	for t in (number, word):
		t.setNumberAlign('decimal')
		group.addItem(t)
	try:
		assert word._numberColumn() is None
		assert number._numberColumn() == number._numberExtents()
	finally:
		for t in (number, word):
			t.scene() and t.scene().removeItem(t)


def test_a_column_is_shared_only_by_items_on_one_edge(dashboard, monkeypatch):
	"""A dashboard-wide group holds values in many columns. Only the items whose boxes end on the same edge share
	the column, so a short value in one cell does not make room for the widest number elsewhere."""
	panel = dashboard.scene.base
	group = MatchAllSizeGroup(panel, 'number-align-columns')
	short, wide, beside = Text(panel, value='7'), Text(panel, value='30.09'), Text(panel, value='12.5')
	for t in (short, wide, beside):
		t.setNumberAlign('decimal')
		t.alignment = AlignmentFlag.Right
		group.addItem(t)
	try:
		assert short._columnEdge() == wide._columnEdge(), 'one box, one edge'
		assert short._numberColumn()[0] == wide._numberExtents()[0], 'same edge: the column is shared'
		monkeypatch.setattr(wide, '_columnEdge', lambda: short._columnEdge() - 200)
		assert short._numberColumn()[1] == max(short._numberExtents()[1], beside._numberExtents()[1])
		assert short._numberColumn()[0] == max(short._numberExtents()[0], beside._numberExtents()[0]), \
			'another column does not widen this one'
	finally:
		for t in (short, wide, beside):
			t.scene() and t.scene().removeItem(t)
