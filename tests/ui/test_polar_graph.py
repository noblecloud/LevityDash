"""The `polar-graph` item: its scale and binning maths, and that it paints."""
from datetime import timedelta

import numpy as np
import pytest
from PySide6.QtGui import QColor, QImage, QPainter

from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar import PolarGraph, binned, niceRange, niceStep, parseWindow, smoothed


def test_nice_step_is_round():
	assert niceStep(40, 4) == 10
	assert niceStep(20, 4) == 5
	assert niceStep(23, 4) == 10
	assert niceStep(0.9, 4) == 0.25
	assert niceStep(0, 4) == 1


def test_nice_range_widens_to_whole_steps():
	assert niceRange(59, 74) == (55, 75)
	assert niceRange(0, 31) == (0, 40)
	assert niceRange(5, 5) == (5, 6)


def test_window_words():
	assert parseWindow('today') is None
	assert parseWindow('6h') == timedelta(hours=6)
	assert parseWindow('90m') == timedelta(minutes=90)
	assert parseWindow(12) == timedelta(hours=12)
	with pytest.raises(ValueError):
		parseWindow('soonish')


def test_petal_zero_is_centred_on_north():
	angles = np.array([358.0, 2.0, 90.0])
	speeds = np.array([4.0, 6.0, 10.0])
	by_value = binned(angles, speeds, 8, frequency=False)
	assert by_value[0] == 5.0 and by_value[2] == 10.0 and by_value[1] == 0.0
	by_count = binned(angles, speeds, 8, frequency=True)
	assert by_count[0] == pytest.approx(2 / 3) and by_count.sum() == pytest.approx(1)


def test_smoothing_never_overshoots():
	x = np.arange(0.0, 360.0, 15.0)
	y = np.where(x == 180, 90.0, 60.0)
	gx, gy = smoothed(x, y, per=2.0)
	assert gy.max() <= 90.0 + 1e-9 and gy.min() >= 60.0 - 1e-9 and len(gx) > len(x)


@pytest.fixture
def slot(dashboard):
	box = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '20%', 'height': '30%'})
	yield box
	if box.scene() is not None:
		box.scene().removeItem(box)


def make(slot, **settings) -> PolarGraph:
	state = {'type': 'polar-graph', 'name': 'polar', 'key': 'environment.temperature.temperature', **settings}
	slot.state = {'items': [state]}
	return next(c for c in slot.childItems() if isinstance(c, PolarGraph))


def paint(graph: PolarGraph) -> QImage:
	image = QImage(400, 400, QImage.Format.Format_ARGB32)
	image.fill(QColor('black'))
	painter = QPainter(image)
	graph.setRect(graph.rect().__class__(0, 0, 400, 400))
	graph.paintPolar(painter)
	painter.end()
	return image


def inked(image: QImage) -> int:
	black = QColor('black').rgb()
	return sum(1 for y in range(0, 400, 4) for x in range(0, 400, 4) if image.pixel(x, y) != black)


def test_loads_with_defaults(dashboard, slot):
	graph = make(slot)
	assert graph.isTime and graph.style == 'area' and graph.window is None and graph.turnStart == 180.0
	other = make(slot, angle='environment.wind.direction.direction')
	assert not other.isTime and other.style == 'trail' and other.window == timedelta(hours=6)


def test_state_round_trips(dashboard, slot):
	graph = make(slot, angle='environment.wind.direction.direction', style='rose', window='12h', range={'min': 0, 'max': 40}, labels='compass', hole=0.3)
	state = graph.state
	assert state['angle'] == 'environment.wind.direction.direction'
	assert state['style'] == 'rose' and state['window'] == '12h'
	assert state['range'] == {'min': 0.0, 'max': 40.0} and state['hole'] == 0.3


def test_bad_style_does_not_abort_the_load(dashboard, slot):
	graph = make(slot, style='donut', window='soonish')
	assert graph.style == 'area' and graph.window is None


def test_empty_face_paints(dashboard, slot):
	graph = make(slot)
	assert inked(paint(graph)) > 0  # rings, spokes and labels, with no data at all


@pytest.mark.parametrize('style, angle', [('area', 'time'), ('line', 'time'), ('trail', 'dir'), ('rose', 'dir')])
def test_every_style_paints_data(dashboard, slot, monkeypatch, style, angle):
	graph = make(slot, style=style, **({} if angle == 'time' else {'angle': 'environment.wind.direction.direction'}))
	empty = inked(paint(graph))
	turn = np.linspace(0, 0.95, 24)
	monkeypatch.setattr(graph, 'points', lambda: (turn, turn * 360.0 if angle == 'time' else (turn * 700) % 360, 60 + 10 * np.sin(turn * 6)))
	assert inked(paint(graph)) > empty
