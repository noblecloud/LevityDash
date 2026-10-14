"""Dragging in the Studio builder's preview snaps to the edges and centres of the parent and the siblings."""
import pytest

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QImage, QMouseEvent  # noqa: E402

from LevityDash.devtools import _studio_builder as sb  # noqa: E402

PARENT = QRectF(0, 0, 400, 200)


def test_a_move_snaps_its_edge_to_a_sibling_edge():
	sibling = QRectF(100, 100, 100, 50)
	rect, gx, gy = sb.snapDrag(QRectF(203, 20, 60, 40), 'move', None, PARENT, [sibling], 6)
	assert rect.left() == 200 and gx == [200]
	assert rect.top() == 20 and gy == []  # nothing within reach vertically


def test_a_move_snaps_its_centre_to_the_parent_centre():
	rect, gx, gy = sb.snapDrag(QRectF(168, 10, 60, 40), 'move', None, PARENT, [], 6)
	assert rect.center().x() == 200 and gx == [200]


def test_a_resize_snaps_only_the_edge_it_drags():
	sibling = QRectF(0, 0, 150, 50)
	rect, gx, gy = sb.snapDrag(QRectF(20, 20, 133, 70), 'resize', 'br', PARENT, [sibling], 6)
	assert (rect.left(), rect.right()) == (20, 150)
	assert rect.top() == 20 and rect.bottom() == 90 and gy == []


def test_nothing_snaps_beyond_reach():
	rect, gx, gy = sb.snapDrag(QRectF(40, 40, 60, 40), 'move', None, PARENT, [], 6)
	assert rect == QRectF(40, 40, 60, 40) and not gx and not gy


def drag(stage, start, end, modifiers=Qt.KeyboardModifier.NoModifier):
	def event(kind, p):
		return QMouseEvent(kind, QPointF(*p), QPointF(*p), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, modifiers)
	stage.mousePressEvent(event(QMouseEvent.Type.MouseButtonPress, start))
	stage.mouseMoveEvent(event(QMouseEvent.Type.MouseMove, end))
	moved = stage.rects[stage.path]
	stage.mouseReleaseEvent(event(QMouseEvent.Type.MouseButtonRelease, end))
	return moved


@pytest.fixture
def stage():
	st = sb.Stage()
	st.resize(400, 200)
	image = QImage(400, 200, QImage.Format.Format_ARGB32)
	st.show_(image, {(): QRectF(0, 0, 400, 200), (0,): QRectF(10, 10, 100, 50), (1,): QRectF(200, 100, 100, 50)})
	st.select((0,), True)
	return st


def test_the_stage_snaps_a_drag_and_clears_its_guides(stage):
	moved = drag(stage, (50, 30), (50 + 188, 30 + 1))  # the item's left edge lands 2px from the sibling's
	assert moved.left() == pytest.approx(200, abs=0.01)
	assert stage.guides == ([], [])


def test_alt_drags_free(stage):
	moved = drag(stage, (50, 30), (50 + 188, 30), Qt.KeyboardModifier.AltModifier)
	assert moved.left() == pytest.approx(198, abs=0.01)


def test_the_snap_box_turns_snapping_off(stage):
	stage.snap = False
	assert drag(stage, (50, 30), (50 + 188, 30)).left() == pytest.approx(198, abs=0.01)
