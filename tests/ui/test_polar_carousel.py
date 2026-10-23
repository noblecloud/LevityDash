"""The carousel plot: where its marks land, and that it paints."""
import pytest

from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.geometry import carouselMarks


def test_the_centre_mark_is_under_the_pointer():
	marks = carouselMarks(180, 120, 16)
	middle = [m for m in marks if abs(m.offset) < 1e-9]
	assert [(m.label, m.kind) for m in middle] == [('S', 'cardinal')]


def test_marks_stay_inside_the_strip_and_cover_the_view():
	marks = carouselMarks(200, 120, 16)
	assert all(-0.5 <= m.offset <= 0.5 for m in marks)
	labels = [m.label for m in marks if m.label]
	assert labels == ['SSE', 'S', 'SSW', 'SW', 'WSW']  # 140 to 260 degrees, left to right


def test_letters_wrap_through_north():
	marks = carouselMarks(350, 120, 16)
	north = next(m for m in marks if m.label == 'N')
	assert north.offset == pytest.approx(10 / 120)
	assert north.degrees == 0


def test_a_tick_sits_between_two_letters():
	marks = carouselMarks(0, 90, 8)
	kinds = [m.kind for m in marks]
	assert kinds == ['point', 'minor', 'cardinal', 'minor', 'point']  # NW, tick, N, tick, NE


def test_a_bad_compass_or_view_is_refused():
	with pytest.raises(ValueError):
		carouselMarks(0, 120, 12)
	with pytest.raises(ValueError):
		carouselMarks(0, 0, 8)


def test_it_paints_ink():
	from PySide6.QtCore import QRectF
	from PySide6.QtGui import QColor, QImage, QPainter
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar import draw

	image = QImage(400, 120, QImage.Format.Format_ARGB32)
	image.fill(QColor('black'))
	look = draw.Look(*(QColor('white') for _ in range(5)))
	painter = QPainter(image)
	draw.drawCarousel(painter, look, QRectF(0, 0, 400, 120), 215.0, 120, 16, True)
	painter.end()
	assert any(image.pixelColor(x, y) != QColor('black') for x in range(0, 400, 7) for y in range(0, 120, 3))
	empty = QImage(400, 120, QImage.Format.Format_ARGB32)
	empty.fill(QColor('black'))
	painter = QPainter(empty)
	draw.drawCarousel(painter, look, QRectF(0, 0, 400, 120), None, 120, 16)  # no value yet: nothing drawn
	painter.end()
	assert empty == QImage(400, 120, QImage.Format.Format_ARGB32).convertedTo(empty.format()) or all(
		empty.pixelColor(x, y) == QColor('black') for x in range(0, 400, 9) for y in range(0, 120, 9))
