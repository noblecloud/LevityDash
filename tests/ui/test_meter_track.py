"""The track's geometry, and that `ArcTrack` draws the same arc the gauge always did.

`ArcTrack.subPath` replaces the four lines `GaugeArc.draw` used to build its path
by hand, so the test that matters is the one comparing the two:
`same_as_hand_built_path`. If that passes for a spread of angle ranges, the
refactor cannot have moved a pixel.
"""
import pytest
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath

from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.track import ArcTrack, LineTrack

#: Angle ranges to check: the defaults, a full circle, one running the other way,
#: a quarter, and a pair of odd ones (a non-square rect, and a negative sweep).
ANGLE_RANGES = [(-120, 120), (0, 360), (120, -120), (0, 90), (-35.5, 200.25), (90, 0)]


def path_signature(path: QPainterPath):
	"""A path as comparable tuples - element type and each coordinate, verbatim."""
	# `.type` is a Qt enum, not an int, and `int()` refuses it; it compares fine as is.
	return [(path.elementAt(i).type, path.elementAt(i).x, path.elementAt(i).y) for i in range(path.elementCount())]


def hand_built(rect: QRectF, start: float, end: float) -> QPainterPath:
	"""Exactly what `GaugeArc.draw` did before this module existed."""
	full = end - start
	path = QPainterPath()
	path.arcMoveTo(rect, -start + 90)
	path.arcTo(rect, -start + 90, -full)
	return path


@pytest.mark.parametrize(('start', 'end'), ANGLE_RANGES)
def test_same_as_hand_built_path(start, end):
	rect = QRectF(-200, -200, 400, 400)
	track = ArcTrack(rect, start, end)
	assert path_signature(track.subPath(0, 1)) == path_signature(hand_built(rect, start, end))


@pytest.mark.parametrize(('start', 'end'), ANGLE_RANGES)
def test_subpath_ends_where_pointat_says(start, end):
	track = ArcTrack(QRectF(-200, -200, 400, 400), start, end)
	path = track.subPath(0, 1)
	first, last = track.pointAt(0), track.pointAt(1)
	assert path.pointAtPercent(0) == first
	assert path.pointAtPercent(1) == last


@pytest.mark.parametrize(('start', 'end'), ANGLE_RANGES)
def test_subpath_piece_matches_the_whole_path(start, end):
	"""A middle piece starts and ends on the full arc's points."""
	rect = QRectF(-200, -200, 400, 400)
	track = ArcTrack(rect, start, end)
	piece = track.subPath(0.25, 0.75)
	assert piece.pointAtPercent(0) == track.pointAt(0.25)
	assert piece.pointAtPercent(1) == track.pointAt(0.75)


def test_quarter_circle_length():
	track = ArcTrack(QRectF(-100, -100, 200, 200), 0, 90)
	assert track.lengthPx == pytest.approx(100 * 90 / 180 * 3.141592653589793, rel=1e-9)


def test_angle_convention_is_the_dials():
	"""0 is up, positive is clockwise: t=0 on a 0..360 dial is the top of the circle."""
	track = ArcTrack(QRectF(-100, -100, 200, 200), 0, 360)
	top = track.pointAt(0)
	assert top.x() == pytest.approx(0, abs=1e-9)
	assert top.y() == pytest.approx(-100, abs=1e-9)


def test_line_track_basics():
	track = LineTrack(QPointF(0, 0), QPointF(100, 0))
	assert track.pointAt(0.5) == QPointF(50, 0)
	assert track.lengthPx == pytest.approx(100)
	assert track.tangentAt(0.5) == QPointF(1, 0)
	assert track.normalAt(0.5) == QPointF(0, 1)
	assert track.angleAt(0.5) == pytest.approx(0)
	piece = track.subPath(0.25, 0.75)
	assert piece.pointAtPercent(0) == QPointF(25, 0)
	assert piece.pointAtPercent(1) == QPointF(75, 0)
