"""Gauge Studio drags: Option gears the drag down, scrolling sets the ratio, Cmd/Ctrl moves freely."""
import dataclasses
import os

import pytest

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
from PySide6.QtCore import QPointF, Qt  # noqa: E402

from LevityDash.devtools._studio_handles import Gearing, GEAR_STEPS  # noqa: E402

_SEED = os.environ.get('LEVITYDASH_CONFIG_SEED')
from LevityDash.devtools import gauge_studio as gs  # noqa: E402

if _SEED is not None:
	os.environ['LEVITYDASH_CONFIG_SEED'] = _SEED

NONE, ALT, CMD = Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.AltModifier, Qt.KeyboardModifier.ControlModifier


def test_ungeared_follows_the_mouse_one_to_one():
	g = Gearing()
	g.begin(QPointF(10, 10))
	assert g.point(QPointF(110, 10), False) == QPointF(110, 10)


def test_geared_moves_a_quarter_as_far():
	g = Gearing(ratio=4)
	g.begin(QPointF(0, 0))
	assert g.point(QPointF(100, 0), True) == QPointF(25, 0)


def test_pressing_the_key_mid_drag_does_not_jump_the_handle():
	g = Gearing(ratio=4)
	g.begin(QPointF(0, 0))
	assert g.point(QPointF(100, 0), False) == QPointF(100, 0)
	assert g.point(QPointF(100, 0), True) == QPointF(100, 0)  # same mouse spot: the handle stays
	assert g.point(QPointF(140, 0), True) == QPointF(110, 0)  # then 40px of mouse is 10px of handle


def test_releasing_the_key_does_not_jump_either():
	g = Gearing(ratio=4)
	g.begin(QPointF(0, 0))
	g.point(QPointF(100, 0), True)  # handle at 25
	assert g.point(QPointF(100, 0), False) == QPointF(25, 0)
	assert g.point(QPointF(150, 0), False) == QPointF(75, 0)


def test_the_wheel_steps_the_ratio_and_anchors_where_it_is():
	g = Gearing(ratio=4)
	g.begin(QPointF(0, 0))
	g.point(QPointF(100, 0), True)  # handle at 25
	assert g.step(+1) == 6
	assert g.point(QPointF(100, 0), True) == QPointF(25, 0)
	assert g.point(QPointF(160, 0), True) == QPointF(35, 0)  # 60px / 6
	for _ in range(20):
		g.step(+1)
	assert g.ratio == GEAR_STEPS[-1]
	for _ in range(20):
		g.step(-1)
	assert g.ratio == GEAR_STEPS[0]


def _pump():
	from PySide6.QtWidgets import QApplication
	for _ in range(5):
		QApplication.processEvents()


@pytest.fixture
def studio():
	s = gs.Studio()
	s.loadDisplay({'arc': {'weight': '8%'}}, 'environment.temperature.temperature', 'gear-test')
	s.settle()
	_pump()
	s.layer.rebuildNow()
	return s


def test_a_real_handle_moves_a_quarter_as_far_when_geared_and_stays_whole_when_not(studio):
	layer = studio.layer
	item = next(i for i in layer.items if i.spec.kind == 'radius')
	seen = []
	item.spec = dataclasses.replace(item.spec, drag=lambda state, pos, fine: seen.append((QPointF(pos), fine)))
	start = QPointF(100, 100)
	layer.begin(item, start)
	layer.move(item, start + QPointF(100, 0), NONE)
	layer.move(item, start + QPointF(100, 0) + QPointF(100, 0), ALT)
	layer.move(item, start + QPointF(100, 0) + QPointF(100, 0) + QPointF(0, 0), ALT | CMD)
	assert seen[0][0] == start + QPointF(100, 0) and seen[0][1] is False
	assert seen[1][0] == start + QPointF(125, 0)  # the second 100px, geared 4:1
	assert seen[2][1] is True  # Cmd turns snapping off
	layer.end(item)


def test_one_geared_drag_is_one_undo_step(studio):
	layer = studio.layer
	item = next(i for i in layer.items if i.spec.kind == 'radius')
	before = len(studio.history)
	start = layer.gauge.sceneBoundingRect().center()
	layer.begin(item, start)
	for x in (10, 30, 60, 90):
		layer.move(item, start + QPointF(x, 0), ALT)
	layer.end(item)
	_pump()
	assert len(studio.history) - before <= 1
