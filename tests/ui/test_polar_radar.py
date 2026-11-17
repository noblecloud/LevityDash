"""The radar plot: ring maths, labels, and that it paints each aircraft where it belongs."""
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.radar import Blip, label, ringValues


def test_rings_are_round_numbers_inside_the_rim():
	assert ringValues(50, 5) == [10, 20, 30, 40, 50]
	assert ringValues(100, 4) == [25, 50, 75, 100]
	assert ringValues(7, 3)[-1] <= 7


def test_label_shows_the_flight_level_when_there_is_an_altitude():
	plane = Blip('UAL123', 90, 10, altitude=12000)
	assert label(plane, True) == 'UAL123 120'
	assert label(plane, False) == 'UAL123'
	assert label(Blip('N1', 0, 1, altitude=0), True) == 'N1'


def _grab(blips, top=50, **kw):
	from PySide6.QtCore import QRectF
	from PySide6.QtGui import QColor, QImage, QPainter
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar import draw, radar

	image = QImage(400, 400, QImage.Format.Format_ARGB32)
	image.fill(QColor('black'))
	look = draw.Look(*(QColor('white') for _ in range(5)))
	painter = QPainter(image)
	radar.drawRadar(painter, look, QRectF(0, 0, 400, 400), blips, top, 4, 8, lambda alt: QColor('#ff00ff'), 0, **kw)
	painter.end()
	return image


def test_a_blip_lands_at_its_bearing_and_distance():
	empty = _grab([], legend=False)
	east = _grab([Blip('E', 90, 25, speed=0)], legend=False)  # half the range, due east: right of centre, level with it
	# The disc is 400 wide less padding; half way out due east is about 3/4 of the way across.
	changed = [(x, y) for x in range(0, 400) for y in range(0, 400) if east.pixel(x, y) != empty.pixel(x, y)]
	assert changed
	xs, ys = [x for x, _ in changed], [y for _, y in changed]
	assert 270 < sum(xs) / len(xs) < 330 and abs(sum(ys) / len(ys) - 200) < 6


def test_a_blip_past_the_rim_is_not_drawn():
	assert _grab([Blip('far', 90, 80)], legend=False) == _grab([], legend=False)
