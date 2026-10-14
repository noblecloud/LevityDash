"""Gauge Studio's wireframe and guideline layers read the gauge and write nothing."""
import os

import pytest

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QPainterPath  # noqa: E402

from LevityDash.devtools import _studio_geometry as geometry  # noqa: E402

_SEED = os.environ.get('LEVITYDASH_CONFIG_SEED')
from LevityDash.devtools import gauge_studio as gs  # noqa: E402

if _SEED is not None:
	os.environ['LEVITYDASH_CONFIG_SEED'] = _SEED


def _pump():
	from PySide6.QtWidgets import QApplication
	for _ in range(5):
		QApplication.processEvents()


def _load(display):
	s = gs.Studio()
	s.settings.clear()
	s.loadDisplay(display, 'environment.temperature.temperature', 'wire-test')
	s.settle()
	_pump()
	s.layer.rebuildNow()
	return s


def _box(x, y, w, h, role='label', kind='value'):
	p = QPainterPath()
	p.addRect(QRectF(x, y, w, h))
	return geometry.Shape(kind, kind, p, role=role)


def test_overlapping_label_boxes_are_found_and_touching_ones_are_not():
	shapes = [_box(0, 0, 10, 10), _box(5, 5, 10, 10, kind='unit'), _box(15, 0, 10, 4, kind='caption'), _box(40, 40, 5, 5, kind='sub-label')]
	assert geometry.overlapping(shapes) == {0, 1}  # the caption only touches the unit's corner column


def test_wireframe_draws_the_elements_and_changes_nothing():
	s = _load({'arc': {'weight': '8%'}, 'radius': '40%'})
	before, history = s.exportDisplay(), len(s.history)
	s.wireAction.setChecked(True)
	_pump()
	kinds = {sh.kind for sh in s.layer.wire.shapes}
	assert {'card', 'dial', 'track', 'tick', 'tick-label', 'value', 'needle', 'pivot'} <= kinds
	assert s.layer.wire.veil is not None
	for action in s.layerActions.values():
		action.setChecked(True)
	assert s.layer.wire.guides
	assert s.exportDisplay() == before and len(s.history) == history
	s.wireAction.setChecked(False)
	for action in s.layerActions.values():
		action.setChecked(False)
	assert not s.layer.wire.isVisible()


def test_a_below_value_label_on_a_full_ring_is_drawn_red():
	s = _load({'arc': {'weight': '10%', 'start-angle': -180, 'end-angle': 180}, 'value-label': {'position': 'below'}})
	s.wireAction.setChecked(True)
	_pump()
	wire = s.layer.wire
	assert {wire.shapes[i].name for i in wire.red} >= {'value ink', 'track band'}
