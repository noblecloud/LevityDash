"""What the beam spends per frame: shared windows and a frame rate that follows the paint cost."""
import pytest

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainterPath

from LevityDash.lib.ui.frontends.PySide.Modules.beam import styles
from LevityDash.lib.ui.frontends.PySide.Modules.beam.pulse_driver import PulseDriver

STOPS = ((0.0, 0.0), (0.42, 0.0), (0.5, 1.0), (0.58, 0.0), (1.0, 0.0))


def _ctx(key=('cost-test', 400, 200)):
	path = QPainterPath()
	path.addRoundedRect(QRectF(5, 5, 390, 190), 20, 20)
	return styles.PaintCtx(
		size=None, rect=QRectF(0, 0, 400, 200), radius=0.0, dark=True, variant=None, fade=1.0,
		brightness=1.0, saturation=1.0, hue_deg=0.0, progress=0.0, path=path, path_key=key,
	)


def test_the_same_window_is_built_once_per_frame():
	ctx = _ctx()
	first = styles.path_travel_mask(ctx, 400, 200, 0.3, STOPS, 30.0)
	assert styles.path_travel_mask(ctx, 400, 200, 0.3, STOPS, 30.0) is first
	assert styles.path_travel_mask(ctx, 400, 200, 0.31, STOPS, 30.0) is not first


def test_the_window_is_lit_where_the_stops_say():
	ctx = _ctx()
	mask = styles.path_travel_mask(ctx, 400, 200, 0.0, STOPS, 30.0)
	along = [mask.pixelColor(x, y).alpha() for x in range(0, 400, 4) for y in (5, 195)]
	assert max(along) > 200, 'the window peaks on the path'
	assert min(along) == 0, 'and is dark elsewhere along it'


def test_slow_paints_stretch_the_frame_interval():
	driver = PulseDriver()
	assert driver._timer.interval() == 33
	for _ in range(20):
		driver.note_paint(0.08)
		driver._adapt()
	assert driver._timer.interval() > 100
	for _ in range(40):
		driver.note_paint(0.001)
		driver._adapt()
	assert driver._timer.interval() < 41, 'back to about 30 fps'
