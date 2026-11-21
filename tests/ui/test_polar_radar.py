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


def test_a_glyph_is_chosen_by_type_then_family_then_category():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.glyphs import classify
	assert classify('B738', 'A3').shape == 'narrow'
	assert classify('A388').shape == 'quad' and classify('B77W').shape == 'wide'
	assert classify('GLF4').shape == 'bizjet' and classify('E75L').shape == 'regional'
	assert classify('AT72').shape == 'twinprop' and classify('C172').shape == 'light'
	assert classify('EC35').shape == 'heli' and classify('F16').shape == 'fighter'
	assert classify('B39M').shape == 'narrow'  # listed
	assert classify('A21X', 'A3').shape == 'narrow'  # not listed: the A32x/A31x family prefix would miss it, so category answers
	assert classify('QQQQ', 'A5').shape == 'wide' and classify(None, 'A7').shape == 'heli'
	assert classify('', None).shape == 'unknown'
	assert classify('b738').shape == 'narrow'  # case does not matter


def test_every_shape_has_a_path_inside_the_unit_box():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar import glyphs
	for shape in glyphs.SHAPES:
		bounds = glyphs.path(shape).boundingRect()
		assert 0.2 < bounds.height() <= 1.1 and bounds.width() <= 1.3, shape
		assert abs(bounds.center().x()) < 0.01, f'{shape} is not centred side to side'


def test_the_radar_paints_a_glyph_turned_to_its_heading():
	north = _grab([Blip('A', 90, 25, heading=0, speed=200, kind='B738')], legend=False)
	east = _grab([Blip('A', 90, 25, heading=90, speed=200, kind='B738')], legend=False)
	dots = _grab([Blip('A', 90, 25, heading=0, speed=200, kind='B738')], legend=False, glyphs=False)
	assert north != east and north != dots


def _hit(blips, pos, top=50):
	from PySide6.QtCore import QPointF, QRectF
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.radar import hitBlip
	return hitBlip(QRectF(0, 0, 400, 400), blips, top, QPointF(*pos))


def test_a_click_finds_the_blip_it_lands_on():
	plane = Blip('UAL123', 90, 25, speed=0, slot=3)
	# Due east at half the range: the disc's radius is 200 less the text padding, so the mark is near x = 284.
	assert _hit([plane], (284, 200)) is plane
	assert _hit([plane], (200, 200)) is None            # the middle, where nothing is
	assert _hit([plane], (330, 200)) is None            # well clear of it
	assert _hit([Blip('far', 90, 80)], (284, 200)) is None  # past the rim: not drawn, so not clickable
	assert _hit([], (284, 200)) is None


def test_two_blips_on_one_point_hand_back_the_nearer_to_the_pointer():
	near = Blip('near', 90, 25, slot=1)
	far = Blip('far', 90, 25.4, slot=2)
	hit = _hit([far, near], (286, 200))
	assert hit is not None and hit.slot in (1, 2)


def test_the_popover_paints_a_panel_inside_the_plot():
	from PySide6.QtCore import QRectF
	from PySide6.QtGui import QColor, QImage, QPainter
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar import draw, radar

	image = QImage(400, 400, QImage.Format.Format_ARGB32)
	image.fill(QColor('black'))
	look = draw.Look(*(QColor('white') for _ in range(5)))
	painter = QPainter(image)
	plane = Blip('UAL123', 90, 25, altitude=12000, speed=250, slot=1)
	panel = radar.drawPopover(painter, look, QRectF(0, 0, 400, 400), plane, [('Altitude', '12,000 ft'), ('Speed', '250 kt')], 50)
	painter.end()
	assert panel.width() > 40 and panel.height() > 20
	assert QRectF(0, 0, 400, 400).contains(panel), 'the panel is kept inside the plot'
	inside = image.pixelColor(int(panel.center().x()), int(panel.center().y()))
	assert inside != QColor('black'), 'the panel is painted, not left as empty sky'


class _FakeRadar:
	"""Just enough of a Polar panel for the popover: it paints the disc and answers clicks."""

	def __init__(self, blips=()):
		self._overlay = None
		self._scene = None
		self.blips = list(blips)
		self.painted: list = []
		self.selected = None

	def scene(self):
		return self._scene

	def rect(self):
		from PySide6.QtCore import QRectF
		return QRectF(0, 0, 400, 400)

	def drawRadarInto(self, painter, rect):
		self.painted.append((rect.width(), rect.height()))

	def radarBlips(self):
		return self.blips

	def radarTop(self):
		return 50.0

	def selectRadarSlot(self, slot):
		self.selected = slot


def _click(item, point):
	from PySide6.QtCore import QEvent, Qt
	from PySide6.QtWidgets import QGraphicsSceneMouseEvent
	event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
	event.setButton(Qt.MouseButton.LeftButton)
	event.setPos(point)
	item.mousePressEvent(event)


def test_the_radar_opens_larger_as_a_square_inside_the_scene():
	from PySide6.QtCore import QPointF, QRectF
	from PySide6.QtWidgets import QGraphicsScene
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.popover import RadarPopover

	scene = QGraphicsScene()
	scene.setSceneRect(QRectF(0, 0, 1000, 600))
	panel = _FakeRadar()
	panel._scene = scene
	popover = RadarPopover(panel)
	scene.addItem(popover)
	assert panel._overlay is None  # the panel sets it when it opens one, as openRadarPopover does
	area = popover.radarArea()
	assert area.width() == area.height(), 'the disc gets a square, not a stretched one'
	assert scene.sceneRect().contains(area)
	assert area.width() > min(scene.sceneRect().width(), scene.sceneRect().height()) * 0.8, 'most of the scene'
	from PySide6.QtGui import QColor, QImage, QPainter
	image = QImage(1000, 600, QImage.Format.Format_ARGB32)
	image.fill(QColor('white'))
	painter = QPainter(image)
	popover.paint(painter, None)
	painter.end()
	assert panel.painted, 'it draws the panel radar, not a second copy of it'
	assert panel.painted[-1][0] == area.width(), 'and draws it into the square, so it scales up'
	assert image.pixelColor(2, 2) != QColor('white'), 'the backdrop dims the dashboard behind it'
	assert image.pixelColor(500, 300) != QColor(0, 0, 0, 205), 'the disc itself is drawn in the middle'


def test_a_click_on_a_blip_in_the_popover_selects_it_and_a_click_elsewhere_closes_it():
	from PySide6.QtCore import QRectF
	from PySide6.QtWidgets import QGraphicsScene
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.popover import RadarPopover

	scene = QGraphicsScene()
	scene.setSceneRect(QRectF(0, 0, 800, 800))
	panel = _FakeRadar([Blip('OVERHEAD', 0, 0, slot=4)])  # at the middle of the disc
	popover = RadarPopover(panel)
	panel._overlay = popover
	scene.addItem(popover)
	centre = popover.radarArea().center()
	_click(popover, centre)
	assert panel.selected == 4 and popover.scene() is scene, 'a blip click names it and keeps the popover'
	_click(popover, popover.boundingRect().topLeft())  # the backdrop, outside the disc
	assert popover.scene() is None and panel._overlay is None, 'a click away closes it'


def test_a_trail_is_painted_and_fades_with_age():
	from PySide6.QtCore import QRectF
	from PySide6.QtGui import QColor, QImage, QPainter
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar import draw, radar
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.geometry import polarPoint

	def paint(paths):
		image = QImage(400, 400, QImage.Format.Format_ARGB32)
		image.fill(QColor('black'))
		look = draw.Look(*(QColor('white') for _ in range(5)))
		painter = QPainter(image)
		radar.drawRadar(painter, look, QRectF(0, 0, 400, 400), [Blip('A', 0, 5, kind='B738')], 50, 4, 8,
		                lambda alt: QColor('white'), 0, legend=False, glyphs=False, paths=paths)
		painter.end()
		return image

	# Oldest point at 20 nmi due south, newest at 5 nmi due north, ten minutes apart.
	path = [(600.0, 180, 20.0), (300.0, 180, 12.0), (0.0, 0, 5.0)]
	bare, inked = paint(None), paint([path])
	fontPx = max(8.0, 400 / 28)
	radius = 200 - fontPx * 2.2

	def added(point):
		x, y = int(point[0]), int(point[1])
		return sum(abs(inked.pixelColor(x + dx, y + dy).lightness() - bare.pixelColor(x + dx, y + dy).lightness())
		           for dx in range(-2, 3) for dy in range(-2, 3))

	# The trail runs from 20 nmi due south to 5 nmi due north, so sample the first leg and the last leg on their own
	# headings: 16 nmi south is early in the trail, 3.5 nmi south is the middle of its final, newest leg.
	oldest = polarPoint(200, 200, radius * 16 / 50, 180)
	newest = polarPoint(200, 200, radius * 3.5 / 50, 180)
	assert added(oldest) > 0, 'the whole trail is drawn, not just its newest end'
	assert added(newest) > added(oldest), 'the newest end of a trail is brighter than its oldest'



class _FakePanel:
	"""The bits of Polar that the field handling and the trail reader touch."""

	def __init__(self, slots=3):
		self._radarValues = {}
		self._slots = slots
		self._overlay = None
		self.updates = 0

	def update(self):
		self.updates += 1


def test_every_text_field_the_table_names_is_kept_as_text():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.item import Polar, _RADAR_FIELDS
	panel = _FakePanel()
	for field, isText in _RADAR_FIELDS.items():
		panel._radarValues.clear()
		Polar._radarChanged(panel, field, 1, '12.5' if isText else 12.5)
		stored = panel._radarValues.get((field, 1))
		if isText:
			assert stored == '12.5', f'{field} is text in the table but was not kept: {stored!r}'
		else:
			assert stored == 12.5, f'{field} is numeric in the table but was not kept: {stored!r}'
	# The trail is the case that was dropped: a string handed to the numeric branch becomes None and vanishes.
	panel._radarValues.clear()
	Polar._radarChanged(panel, 'path', 1, '30:10.0:4.0;0:20.0:3.0')
	assert panel._radarValues[('path', 1)] == '30:10.0:4.0;0:20.0:3.0'


def test_the_radar_reads_its_trails_out_of_the_published_paths():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.item import Polar
	panel = _FakePanel(slots=3)
	panel._radarValues.update({
		('path', 1): '30:10.0:4.0;0:20.0:3.0',
		('path', 2): '',            # a slot with no history
		('path', 3): 'nonsense',    # a trail that cannot be read
	})
	assert Polar.radarPaths(panel) == [[(30.0, 10.0, 4.0), (0.0, 20.0, 3.0)]]
	panel._radarValues.clear()
	assert Polar.radarPaths(panel) == []
