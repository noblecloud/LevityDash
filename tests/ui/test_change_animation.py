"""`change-animation` on a label: the text moves when the value it shows changes."""
import pytest
from PySide6.QtTest import QTest

from LevityDash.lib.ui import value_change
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Label import Label
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import Text
from LevityDash.lib.ui.value_change import ChangeSpec


# -- parsing (Qt-free) --

@pytest.mark.parametrize('written, style, seconds', [
	('fade', 'fade', value_change.DEFAULT_DURATION),
	('Slide', 'slide', value_change.DEFAULT_DURATION),
	('slide 500ms', 'slide', 0.5),
	('flash 0.2s', 'flash', 0.2),
	({'style': 'fade', 'duration': '0.6s'}, 'fade', 0.6),
	({'style': 'slide', 'duration': 1}, 'slide', 1.0),
	(True, 'fade', value_change.DEFAULT_DURATION),
])
def test_parse(written, style, seconds):
	spec = value_change.parse(written)
	assert spec == ChangeSpec(style, seconds)


@pytest.mark.parametrize('written', [None, False, 'none', 'NONE'])
def test_parse_off(written):
	assert value_change.parse(written) is None


@pytest.mark.parametrize('written', ['wobble', 'slide 3s', 'fade 0ms', {'style': 'fade', 'speed': 2}, 12])
def test_parse_rejects(written):
	with pytest.raises(ValueError):
		value_change.parse(written)


def test_encode_round_trips():
	for written in ('fade', 'slide 500ms', {'style': 'flash', 'duration': '1.2s'}):
		spec = value_change.parse(written)
		assert value_change.parse(spec.encode()) == spec
	assert ChangeSpec('fade').encode() == 'fade'


@pytest.mark.parametrize('old, new, expected', [
	('71°', '72°', 1), ('72°', '71.5°', -1), ('1,013.2 hPa', '1,009 hPa', -1), ('-3°', '2°', 1),
	('−5°', '−6°', -1), ('NW', 'N', 0), ('4 mph', '4 mph', 0), (None, '3', 0),
])
def test_direction(old, new, expected):
	assert value_change.direction(old, new) == expected


# -- on a dashboard --

@pytest.fixture
def sandbox(dashboard):
	box = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '50%', 'height': '30%'})
	yield box
	if box.scene() is not None:
		box.scene().removeItem(box)


def settle(dashboard, rounds=8):
	for _ in range(rounds):
		QTest.qWait(20)
		dashboard.app.processEvents()


def labelIn(box, text, **extra):
	box.state = {'items': [{'type': 'text', 'text': text, 'margins': '0px', 'alignment': 'Center',
	                        'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'}, **extra}]}
	label = next(item for item in box.childItems() if isinstance(item, Label))
	# a sandbox outside a dashboard load leaves the first build to the next action; build it now, as a loaded
	# dashboard has by the time a value changes
	Text.updateTransform.__wrapped__(label.textBox, updatePath=True, reason='test')
	return label


def change(dashboard, label, text):
	label.textBox.value = text
	settle(dashboard, 2)


@pytest.mark.parametrize('style', ['fade', 'slide', 'flash', 'tint', 'roll', 'slot', 'count', 'pop', 'flip'])
def test_change_runs_and_ends_clean(dashboard, sandbox, style):
	label = labelIn(sandbox, '71°', **{'change-animation': f'{style} 200ms'})
	settle(dashboard)
	box = label.textBox
	assert box._changeSpec == ChangeSpec(style, 0.2)
	opacity, before = box.opacity(), len(box.childItems())
	change(dashboard, label, '72°')
	animator = box._changeAnimator
	assert animator is not None and animator.running
	assert len(box.childItems()) == before + 1
	if style == 'slide':
		assert box.transformations()
	QTest.qWait(350)
	dashboard.app.processEvents()
	assert not animator.running
	assert len(box.childItems()) == before
	assert box.transformations() == []
	assert box.opacity() == pytest.approx(opacity)
	assert box.text == '72°'
	assert not box.path().isEmpty()


def test_glyphs_split_one_per_character(dashboard, sandbox):
	from LevityDash.lib.ui.frontends.PySide.valuechange import glyphs
	label = labelIn(sandbox, '18.4% 0°')
	settle(dashboard)
	assert len(glyphs(label.textBox.path())) == len('18.4%0°')


def test_roll_moves_only_the_changed_characters(dashboard, sandbox):
	from LevityDash.lib.ui.frontends.PySide.valuechange import glyphs
	label = labelIn(sandbox, '1,071°', **{'change-animation': 'roll 2s'})
	settle(dashboard)
	box = label.textBox
	change(dashboard, label, '1,082°')
	effect = box._changeAnimator.effect
	assert len(effect.columns) == 2  # the 7 and the 1
	assert len(glyphs(box.path())) == 4  # 1 , 0 ° stay in the outline
	assert effect.travel > 0
	box._changeAnimator.stop()
	assert len(glyphs(box.path())) == 6


def test_roll_handles_a_longer_number(dashboard, sandbox):
	label = labelIn(sandbox, '99', **{'change-animation': 'roll 2s'})
	settle(dashboard)
	change(dashboard, label, '100')
	effect = label.textBox._changeAnimator.effect
	assert len(effect.columns) == 3
	assert effect.columns[0][1] is None  # the new leading 1 rolls in from nothing
	label.textBox._changeAnimator.stop()


def test_tint_follows_direction(dashboard, sandbox):
	from LevityDash.lib.ui import Color
	label = labelIn(sandbox, '50', **{'change-animation': 'tint 2s'})
	settle(dashboard)
	change(dashboard, label, '40')
	assert label.textBox._changeAnimator.effect.glow.brush().color() == Color.role('bad').QColor
	change(dashboard, label, '45')
	assert label.textBox._changeAnimator.effect.glow.brush().color() == Color.role('good').QColor
	label.textBox._changeAnimator.stop()


def test_slide_direction_follows_the_number(dashboard, sandbox):
	label = labelIn(sandbox, '50', **{'change-animation': 'slide 2s'})
	settle(dashboard)
	change(dashboard, label, '60')
	rising = label.textBox._changeAnimator.effect.travel
	change(dashboard, label, '40')
	falling = label.textBox._changeAnimator.effect.travel
	assert rising > 0 > falling
	label.textBox._changeAnimator.stop()


def test_off_by_default(dashboard, sandbox):
	label = labelIn(sandbox, '71°')
	settle(dashboard)
	children = len(label.textBox.childItems())
	change(dashboard, label, '72°')
	assert label.textBox._changeAnimator is None
	assert len(label.textBox.childItems()) == children


def test_environment_switch_turns_it_off(dashboard, sandbox, monkeypatch):
	monkeypatch.setenv('LEVITY_CHANGE_ANIMATION', '0')
	label = labelIn(sandbox, '71°', **{'change-animation': 'fade'})
	settle(dashboard)
	change(dashboard, label, '72°')
	assert label.textBox._changeAnimator is None


def test_same_text_or_layout_change_does_not_animate(dashboard, sandbox):
	label = labelIn(sandbox, '71°', **{'change-animation': 'fade'})
	settle(dashboard)
	box: Text = label.textBox
	box.updateTransform(reason='test', updatePath=True)
	settle(dashboard, 2)
	assert box._changeAnimator is None


def test_a_new_change_replaces_a_running_one(dashboard, sandbox):
	label = labelIn(sandbox, '1', **{'change-animation': 'fade 2s'})
	settle(dashboard)
	before = len(label.textBox.childItems())
	change(dashboard, label, '2')
	change(dashboard, label, '3')
	assert len(label.textBox.childItems()) == before + 1
	label.textBox._changeAnimator.stop()
	assert len(label.textBox.childItems()) == before


def test_saves_what_was_written(dashboard, sandbox):
	label = labelIn(sandbox, '71°', **{'change-animation': 'slide 500ms'})
	settle(dashboard)
	assert label.state.get('change-animation') == {'style': 'slide', 'duration': '500ms'}
	label = labelIn(sandbox, '71°', **{'change-animation': 'flash'})
	settle(dashboard)
	assert label.state.get('change-animation') == 'flash'


def test_slot_strip_passes_through_the_numerals_between(dashboard, sandbox):
	label = labelIn(sandbox, '5', **{'change-animation': 'slot 2s'})
	settle(dashboard)
	change(dashboard, label, '9')
	effect = label.textBox._changeAnimator.effect
	assert len(effect.strips) == 1
	_, strip, steps = effect.strips[0]
	# 5 6 7 8 9: five numerals stacked one column pitch apart
	assert steps == 4 and strip.path().boundingRect().height() > 4 * abs(effect.travel)
	label.textBox._changeAnimator.stop()


def test_slot_wraps_and_counts_down(dashboard, sandbox):
	label = labelIn(sandbox, '19', **{'change-animation': 'slot 2s'})
	settle(dashboard)
	change(dashboard, label, '22')  # rose: the ones column wraps 9 0 1 2
	effect = label.textBox._changeAnimator.effect
	assert sorted(strip[2] for strip in effect.strips) == [1, 3]
	change(dashboard, label, '20')  # fell: 2 1 0
	effect = label.textBox._changeAnimator.effect
	assert effect.sign == -1 and [strip[2] for strip in effect.strips] == [2]
	label.textBox._changeAnimator.stop()


def test_slot_non_digit_rolls(dashboard, sandbox):
	label = labelIn(sandbox, 'N', **{'change-animation': 'slot 2s'})
	settle(dashboard)
	change(dashboard, label, 'S')
	effect = label.textBox._changeAnimator.effect
	assert effect.strips == [] and len(effect.columns) == 1
	label.textBox._changeAnimator.stop()


def test_count_shows_an_intermediate_number_and_restores(dashboard, sandbox):
	label = labelIn(sandbox, '71.0°', **{'change-animation': 'count 2s'})
	settle(dashboard)
	box = label.textBox
	full = box.path()
	change(dashboard, label, '72.0°')
	anim = box._changeAnimator
	anim.animation.pause()
	effect = anim.effect
	assert effect.counting and box.path().isEmpty()
	anim._frame(0.3)
	assert effect.shown not in (None, '71.0°', '72.0°') and effect.shown.endswith('°')
	assert 71.0 < value_change.number(effect.shown) < 72.0
	assert not effect.child.path().isEmpty()
	anim.stop()
	assert not box.path().isEmpty()
	assert box.path().boundingRect().size() == full.boundingRect().size()


def test_count_falls_back_without_a_number(dashboard, sandbox):
	label = labelIn(sandbox, 'N', **{'change-animation': 'count 2s'})
	settle(dashboard)
	change(dashboard, label, 'S')
	effect = label.textBox._changeAnimator.effect
	assert not effect.counting and not label.textBox.path().isEmpty()
	label.textBox._changeAnimator.stop()
