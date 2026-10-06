"""A filled shape's glow starts flush with its outline: nothing shows outside it at `reach: 0`."""
from PySide6.QtCore import QRectF
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath

from LevityDash.lib.ui.glow import Glow, paintGlow


def _render(reach: float) -> QImage:
	image = QImage(100, 100, QImage.Format.Format_ARGB32_Premultiplied)
	image.fill(0)
	path = QPainterPath()
	path.addEllipse(QRectF(40, 40, 20, 20))
	painter = QPainter(image)
	paintGlow(painter, path, QBrush(QColor('#ffffff')), 20.0, Glow(strength=1.0, reach=reach), filled=True)
	painter.end()
	return image


def test_no_halo_at_zero_reach():
	image = _render(0.0)
	assert image.pixelColor(30, 50).alpha() == 0
	assert image.pixelColor(38, 50).alpha() == 0


def test_halo_outside_the_outline():
	image = _render(0.5)
	assert image.pixelColor(35, 50).alpha() > 0
	assert image.pixelColor(10, 50).alpha() == 0


def test_reach_px_matches_painted_extent():
	glow = Glow(strength=1.0, reach=0.5)
	assert glow.reach_px(20.0, filled=True) == 20.0 * 0.5 + 1
