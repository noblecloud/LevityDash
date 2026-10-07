"""pulse-outside blobs on a custom path move onto the outline."""
import pytest

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath

from LevityDash.lib.ui.frontends.PySide.Modules.beam.styles import PathSnap


def test_corner_blob_lands_on_the_circle():
	path = QPainterPath()
	path.addEllipse(QRectF(0, 0, 200, 200))
	snap = PathSnap(path, ('circle',), 200, 200, QPointF(0, 0))
	x, y = snap.move(0, 0)
	assert (x - 100) ** 2 + (y - 100) ** 2 == pytest.approx(100 ** 2, rel=0.02)
	assert x < 100 and y < 100, 'the top-left corner stays top-left'


def test_origin_offsets_the_result():
	path = QPainterPath()
	path.addEllipse(QRectF(0, 0, 200, 200))
	plain = PathSnap(path, None, 200, 200, QPointF(0, 0)).move(100, 0)
	shifted = PathSnap(path, None, 200, 200, QPointF(30, 30)).move(130, 30)
	assert shifted == pytest.approx((plain[0] + 30, plain[1] + 30))
