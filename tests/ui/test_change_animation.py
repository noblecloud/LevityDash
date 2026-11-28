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


@pytest.mark.parametrize('style', ['fade', 'slide', 'flash', 'tint', 'roll', 'pop', 'flip', 'wipe', 'typewriter', 'scramble'])
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


@pytest.mark.parametrize('style', ['wipe', 'typewriter', 'scramble'])
def test_reveal_styles_hide_then_restore_the_outline(dashboard, sandbox, style):
	label = labelIn(sandbox, '1,071°', **{'change-animation': f'{style} 2s'})
	settle(dashboard)
	box = label.textBox
	change(dashboard, label, '1,082°')
	animator = box._changeAnimator
	effect = animator.effect
	assert effect.inner is None
	assert len(box.childItems()) == 1
	animator.animation.pause()
	for t in (0.0, 0.3, 0.7, 1.0):
		animator._frame(t)
	animator.stop()
	assert box.path().elementCount() == effect.full.elementCount() > 0
	assert box.childItems() == []


def test_wipe_edge_moves_left_to_right(dashboard, sandbox):
	label = labelIn(sandbox, '71°', **{'change-animation': 'wipe 2s'})
	settle(dashboard)
	change(dashboard, label, '72°')
	animator = label.textBox._changeAnimator
	effect = animator.effect
	animator.animation.pause()
	animator._frame(0.2)
	early = effect.fresh.rect().right()
	animator._frame(0.8)
	assert effect.fresh.rect().right() > early
	assert effect.stale.rect().left() == pytest.approx(effect.fresh.rect().right())
	animator.stop()


def test_typewriter_shows_characters_in_order(dashboard, sandbox):
	label = labelIn(sandbox, '1,071°', **{'change-animation': 'typewriter 2s'})
	settle(dashboard)
	change(dashboard, label, '1,082°')
	animator = label.textBox._changeAnimator
	effect = animator.effect
	animator.animation.pause()
	animator._frame(0.2)
	shown =[letter.opacity() for letter in effect.letters]
	assert shown == sorted(shown, reverse=True)
	assert shown[0] == 1.0 and shown[-1] < 1.0
	animator._frame(1.0)
	assert all(letter.opacity() == 1.0 for letter in effect.letters)
	assert effect.old.opacity() == 0.0
	animator.stop()


def test_typewriter_falls_back_to_a_wipe_without_glyphs(dashboard, sandbox, monkeypatch):
	from LevityDash.lib.ui.frontends.PySide import valuechange
	monkeypatch.setattr(valuechange, 'glyphs', lambda path: [])
	label = labelIn(sandbox, '71°', **{'change-animation': 'typewriter 2s'})
	settle(dashboard)
	change(dashboard, label, '72°')
	animator = label.textBox._changeAnimator
	assert isinstance(animator.effect.inner, valuechange._Wipe)
	animator.stop()
	assert not label.textBox.path().isEmpty()
	assert label.textBox.childItems() == []


def test_scramble_changes_only_the_changed_characters(dashboard, sandbox):
	from LevityDash.lib.ui.frontends.PySide.valuechange import glyphs
	label = labelIn(sandbox, '1,071°', **{'change-animation': 'scramble 2s'})
	settle(dashboard)
	box = label.textBox
	change(dashboard, label, '1,082°')
	animator = box._changeAnimator
	effect = animator.effect
	assert len(effect.columns) == 2
	animator.animation.pause()
	animator._frame(0.1)
	assert all(sum(f.isVisible() for f in faces) == 1 for _, _, faces, _ in effect.columns)
	assert not any(final.isVisible() for _, final, _, _ in effect.columns)
	animator._frame(1.0)
	assert all(final.isVisible() for _, final, _, _ in effect.columns)
	assert all(not f.isVisible() for _, _, faces, _ in effect.columns for f in faces)
	animator.stop()
	assert len(glyphs(box.path())) == 6


def test_scramble_falls_back_to_fade(dashboard, sandbox, monkeypatch):
	from LevityDash.lib.ui.frontends.PySide import valuechange
	monkeypatch.setattr(valuechange, 'glyphs', lambda path: [])
	label = labelIn(sandbox, '71°', **{'change-animation': 'scramble 2s'})
	settle(dashboard)
	change(dashboard, label, '72°')
	animator = label.textBox._changeAnimator
	assert isinstance(animator.effect.inner, valuechange._Fade)
	animator.stop()
	assert label.textBox.childItems() == []
