"""`text: [Temperature, Temp, T]` shows the longest text that fits its box without shrinking much."""
import pytest
from PySide6.QtCore import QRectF

from LevityDash.lib.ui.Groups import MatchAllSizeGroup
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import Text

WORDS = ['Temperature', 'Temp', 'T']


class _Boxed(Text):
	box = QRectF(0, 0, 400, 60)

	@property
	def limitRect(self) -> QRectF:
		return QRectF(self.box)


def _text(dashboard, width, **kw):
	cls = type('Boxed', (_Boxed,), {'box': QRectF(0, 0, width, 60)})
	item = cls(dashboard.scene.base, value=WORDS, **kw)
	item.updateTransform(reason='test')
	return item


@pytest.mark.parametrize('width, shown', [(900, 'Temperature'), (190, 'Temp'), (20, 'T')])
def test_the_longest_text_that_fits_shows(dashboard, width, shown):
	item = _text(dashboard, width)
	try:
		assert item.text == shown
		assert item.alternates == tuple(WORDS)
	finally:
		item.scene() and item.scene().removeItem(item)


def test_zero_condense_always_shows_the_first(dashboard):
	item = _text(dashboard, 20)
	try:
		item.setAlternates(WORDS, condense=0)
		item.updateTransform(reason='test')
		assert item.text == 'Temperature'
	finally:
		item.scene() and item.scene().removeItem(item)


def test_the_choice_does_not_follow_the_group_size(dashboard):
	"""A size group sets the font size; the choice is made on ratios, so it cannot move with it."""
	item = _text(dashboard, 190)
	group = MatchAllSizeGroup(dashboard.scene.base, 'condense-group')
	try:
		group.addItem(item)
		for _ in range(3):
			item.updateTransform(reason='test')
			group.mark_dirty()
		assert item.text == 'Temp'
	finally:
		item.scene() and item.scene().removeItem(item)


def test_a_plain_string_clears_the_list(dashboard):
	item = _text(dashboard, 900)
	try:
		item.value = 'Wind'
		assert item.alternates == () and item.text == 'Wind'
	finally:
		item.scene() and item.scene().removeItem(item)


def test_a_label_saves_the_list_and_not_the_text_it_shows(dashboard):
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Label import Label

	assert Label.statefulItems['condense'].decodeValue(0.5, None) == 0.5
	with pytest.raises(ValueError):
		Label.statefulItems['condense'].decodeValue(2, None)


def test_a_loaded_label_round_trips_the_list(dashboard):
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Label import Label

	label = Label(parent=dashboard.scene.base, text=WORDS, condense=0.7)
	try:
		saved = label.state
		assert saved['text'] == WORDS
		assert saved['condense'] == 0.7
	finally:
		label.scene() and label.scene().removeItem(label)
