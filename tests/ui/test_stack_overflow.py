"""`overflow:` on a stack: clip, scroll with the wheel, and keep fixed-size items at their size."""
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QGraphicsItem

from tests.conftest import pump
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Containers.Stacks import Stack


@pytest.fixture
def slot(dashboard):
	box = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '50%', 'height': '50%'})
	yield box
	if box.scene() is not None:
		box.scene().removeItem(box)


def build(dashboard, slot, **state):
	items = [{'type': 'group', 'size': '30%'} for _ in range(5)]
	slot.state = {'items': [{'type': 'stack', 'direction': 'Vertical', 'spacing': '0px', 'items': items, **state}]}
	stack = next(c for c in slot.childItems() if isinstance(c, Stack))
	pump(dashboard.app, 0.3)
	return stack


def tops(stack):
	return sorted(round(c.pos().y()) for c in stack.childPanels)


def bottom(stack):
	return max(c.pos().y() + c.rect().height() for c in stack.childPanels)


def test_a_plain_stack_squeezes_and_does_not_clip(dashboard, slot):
	stack = build(dashboard, slot)
	assert not stack.flags() & QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape
	assert stack.overflow == 'visible'


def test_scroll_keeps_the_size_and_clips(dashboard, slot):
	stack = build(dashboard, slot, overflow='scroll')
	assert stack.flags() & QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape
	heights = [round(c.rect().height()) for c in stack.childPanels]
	assert heights == [round(stack.rect().height() * 0.3)] * 5  # 5 x 30% overflows 150%, and nothing shrank
	assert stack._scrollLimit == pytest.approx(stack.rect().height() * 0.5, abs=2)


def test_the_wheel_moves_the_content_and_stops_at_the_end(dashboard, slot):
	stack = build(dashboard, slot, overflow='auto')
	first = tops(stack)
	stack.scrollTo(30)
	assert tops(stack)[0] == first[0] - 30
	stack.scrollTo(10 ** 6)
	assert stack._scroll == pytest.approx(stack._scrollLimit)
	assert bottom(stack) == pytest.approx(stack.rect().height(), abs=1)
	stack.scrollTo(-5)
	assert tops(stack) == first


def test_hidden_and_clip_do_not_scroll_by_wheel(dashboard, slot):
	for mode in ('hidden', 'clip'):
		stack = build(dashboard, slot, overflow=mode)
		assert stack.flags() & QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape and not stack.scrolls


def test_auto_shows_a_bar_only_while_it_overflows(dashboard, slot):
	stack = build(dashboard, slot, overflow='auto')
	assert stack._scrollBar.isVisible() or stack._scrollBar.isVisibleTo(stack)
	fits = build(dashboard, slot, overflow='auto', items=[{'type': 'group', 'size': '30%'}])
	assert fits._scrollLimit == 0
	assert getattr(fits, '_scrollBar', None) is None or not fits._scrollBar.isVisibleTo(fits)


def test_a_wheel_event_scrolls_and_one_past_the_end_is_left_alone(dashboard, slot):
	from PySide6.QtWidgets import QGraphicsSceneWheelEvent
	stack = build(dashboard, slot, overflow='auto')

	def wheel(delta):
		event = QGraphicsSceneWheelEvent()
		event.setDelta(delta)
		event.accept()
		stack.wheelEvent(event)
		return event.isAccepted()

	assert wheel(-120) and stack._scroll == pytest.approx(stack.rect().height() / 5)
	stack.scrollTo(10 ** 6)
	assert not wheel(-120)  # at the end: the wheel is not taken, so something behind it may use it
	assert wheel(120) and stack._scroll < stack._scrollLimit
