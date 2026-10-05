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
	"""The drawn arc and the placed point agree to well under a pixel.

	They are not the same curve: `subPath` is Qt's arc, which quantises angles to
	a 16th of a degree, and `pointAt` is the polar arithmetic the marks have
	always used. The gap is bounded - this pins it, so growing it would be
	noticed - and closing it is a visible change, not a refactor.
	"""
	track = ArcTrack(QRectF(-200, -200, 400, 400), start, end)
	path = track.subPath(0, 1)
	for percent, point in ((0, track.pointAt(0)), (1, track.pointAt(1))):
		on_path = path.pointAtPercent(percent)
		gap = ((on_path.x() - point.x()) ** 2 + (on_path.y() - point.y()) ** 2) ** 0.5
		assert gap < 0.25, f'{percent}: drawn arc and placed point differ by {gap:.3f} px'


@pytest.mark.parametrize(('start', 'end'), ANGLE_RANGES)
def test_point_at_angle_is_the_mark_arithmetic(start, end):
	"""Bit for bit what `Tick.draw` computes: radius * cos/sin of the mark angle.

	The mark angle is the dial's less 90 degrees - `Tick.angle` is
	`gauge.startAngle - 90 + index * interval`, and that is what goes into
	`cos`/`sin`. Getting this wrong rotates every tick by 90 degrees, which is
	exactly what the first version of this did.
	"""
	from math import cos, radians, sin
	track = ArcTrack(QRectF(-200, -200, 400, 400), start, end)
	assert track.markAngle(0) == start - 90
	assert track.markAngle(1) == end - 90
	for angle in (start - 90, (start + end) / 2 - 90, end - 90):
		r = radians(angle)
		assert track.pointAtAngle(angle) == QPointF(200 * cos(r), 200 * sin(r))
		assert track.normalAtAngle(angle) == QPointF(cos(r), sin(r))


@pytest.mark.parametrize(('start', 'end'), ANGLE_RANGES)
def test_subpath_piece_matches_the_whole_path(start, end):
	"""A middle piece starts and ends where the track says those positions are."""
	rect = QRectF(-200, -200, 400, 400)
	track = ArcTrack(rect, start, end)
	piece = track.subPath(0.25, 0.75)
	for percent, t in ((0, 0.25), (1, 0.75)):
		on_piece = piece.pointAtPercent(percent)
		point = track.pointAt(t)
		gap = ((on_piece.x() - point.x()) ** 2 + (on_piece.y() - point.y()) ** 2) ** 0.5
		assert gap < 0.25, f't={t}: piece and track differ by {gap:.3f} px'


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
