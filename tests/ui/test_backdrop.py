"""The dashboard's ground: a flat colour or a gradient, from `background:` or the theme."""
import pytest
from PySide6.QtCore import QPointF, QRectF, Qt

from LevityDash.lib.ui.colors import backdrop, theme


@pytest.fixture(autouse=True)
def default_theme():
	theme.reset()
	yield
	theme.reset()


def test_no_spec_is_the_theme_background():
	assert backdrop.decode(None).color.name() == '#000000'
	theme.activate('paper')
	assert backdrop.decode(None).color.name() == '#f4efe6'


def test_a_scale_token_is_a_gradient_and_a_colour_token_is_flat():
	theme.activate('dusk')
	ground = backdrop.decode('$sky')
	assert not ground.flat and ground.stops[0][0] == 0 and ground.stops[-1][0] == 1
	assert backdrop.decode('$surface').flat


def test_stops_are_stretched_over_the_board():
	a = backdrop.decode({0: '#000000', 100: '#ffffff'})
	b = backdrop.decode({0: '#000000', 1: '#ffffff'})
	assert [p for p, _ in a.stops] == [p for p, _ in b.stops] == [0, 1]


def test_angle_sets_the_direction():
	rect = QRectF(0, 0, 200, 100)
	down = backdrop.linearGradient(rect, backdrop.decode({'gradient': {0: '#000', 1: '#fff'}}).angle, [(0, Qt.black), (1, Qt.white)])
	right = backdrop.linearGradient(rect, backdrop.decode({'gradient': {0: '#000', 1: '#fff'}, 'angle': 90}).angle, [(0, Qt.black), (1, Qt.white)])
	assert down.start().x() == pytest.approx(down.finalStop().x()) and down.start().y() < down.finalStop().y()
	assert right.start().y() == pytest.approx(right.finalStop().y()) and right.start().x() < right.finalStop().x()


def test_a_font_token_is_refused():
	with pytest.raises(theme.ThemeError):
		backdrop.decode('$mono')


SUN = {'by': 'astronomy.sun.elevation', 'top': '$sky-top', 'bottom': '$sky-horizon'}


def test_a_ground_that_follows_a_key_names_it():
	assert backdrop.follows(SUN) == 'astronomy.sun.elevation'
	assert backdrop.follows('$sky') is None and backdrop.follows({'gradient': {0: '#000', 1: '#fff'}}) is None


def test_a_following_ground_is_the_theme_background_until_it_has_a_reading():
	assert backdrop.decode(SUN).flat


def test_a_following_ground_moves_with_the_reading():
	night, dawn, day = (backdrop.decode(SUN, value=v) for v in (-20, 0, 40))
	assert not night.flat and not dawn.flat and not day.flat
	assert night.stops[0][1].lightness() < day.stops[0][1].lightness()
	assert dawn.stops[-1][1].red() > dawn.stops[-1][1].blue()  # a warm horizon at sunrise
	assert day.stops[-1][1].blue() > day.stops[-1][1].red()


def test_a_reading_past_the_ends_is_clamped():
	assert backdrop.decode(SUN, value=-90) == backdrop.decode(SUN, value=-60)
	assert backdrop.decode(SUN, value=90) == backdrop.decode(SUN, value=70)


def test_a_following_ground_needs_both_ends_and_knows_its_keys():
	with pytest.raises(theme.ThemeError, match='bottom'):
		backdrop.decode({'by': 'x', 'top': '$sky-top'}, value=1)
	with pytest.raises(theme.ThemeError, match='unknown keys'):
		backdrop.decode({**SUN, 'colour': 'red'}, value=1)


def test_haze_names_its_key_and_takes_colour_out_of_the_sky():
	spec = {**SUN, 'haze': 'environment.clouds.cover.cover'}
	assert backdrop.hazeKey(spec) == 'environment.clouds.cover.cover' and backdrop.hazeKey(SUN) is None
	clear = backdrop.decode(spec, value=40)
	cloudy = backdrop.decode(spec, value=40, haze=1.0)
	assert backdrop.decode(spec, value=40, haze=0) == clear
	assert cloudy.stops[-1][1].saturationF() < clear.stops[-1][1].saturationF()
	assert cloudy != clear


def test_sky_shorthand_is_the_following_ground():
	assert backdrop.normalize('sky') == backdrop.SKY
	assert backdrop.follows('sky') == 'astronomy.sun.elevation'
	assert backdrop.hazeKey('sky') == 'environment.clouds.cover.cover'
	assert backdrop.decode('sky').flat  # no reading yet
	assert backdrop.decode('sky', value=40) == backdrop.decode(backdrop.SKY, value=40)


def test_sky_shorthand_takes_overrides_and_can_drop_cloud():
	spec = {'sky': True, 'angle': 160, 'haze': False}
	assert backdrop.hazeKey(spec) is None and backdrop.decode(spec, value=0).angle == 160
	assert backdrop.hazeKey({'sky': {'haze': 'x.y'}}) == 'x.y'
	assert backdrop.normalize({'sky': False, 'angle': 90}) == {'angle': 90}


def test_stars_are_an_option_of_the_sky():
	assert backdrop.starLimit('sky') is None
	assert backdrop.starLimit({'sky': True, 'stars': True}) == backdrop.STAR_LIMIT
	assert backdrop.starLimit({'sky': True, 'stars': 4.5}) == 4.5
	assert backdrop.starLimit({'gradient': {0: '#000', 1: '#fff'}, 'stars': True}) is None
	assert backdrop.starOptions({'sky': True, 'stars': True, 'star-time': '2026-12-21T02:00:00Z'}) == {'star-time': '2026-12-21T02:00:00Z'}
	backdrop.decode({'sky': True, 'stars': True}, value=-20)  # known keys


def test_stars_fade_in_with_the_dark_and_out_with_cloud():
	assert backdrop.starAlpha(20) == 0 and backdrop.starAlpha(None) == 0
	assert 0 < backdrop.starAlpha(-6) < 1 and backdrop.starAlpha(-30) == 1
	assert backdrop.starAlpha(-30, 1.0) < backdrop.starAlpha(-30, 0.3) < 1


def test_a_moon_blocks_stars_by_default_and_any_item_can_ask(dashboard):
	from tests.conftest import pump
	from LevityDash.lib.ui.frontends.PySide.Modules import Panel
	scene = dashboard.scene
	slot = Panel(parent=scene.base, geometry={'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'})
	try:
		slot.state = {'items': [
			{'type': 'moon', 'geometry': {'x': '0%', 'y': '0%', 'width': '20%', 'height': '30%'}},
			{'type': 'group', 'occludes-stars': True, 'geometry': {'x': '50%', 'y': '50%', 'width': '20%', 'height': '20%'}, 'items': []},
			{'type': 'group', 'geometry': {'x': '80%', 'y': '80%', 'width': '10%', 'height': '10%'}, 'items': []},
		]}
		pump(dashboard.app, 0.3)
		scene.refreshBackdrop()
		holes = scene._starOcclusion()
		rect = scene.sceneRect()
		assert holes.contains(QPointF(rect.width() * 0.6, rect.height() * 0.6))  # the group that asked
		assert not holes.contains(QPointF(rect.width() * 0.85, rect.height() * 0.85))  # the one that did not
		moon = next(i for i in scene.items() if getattr(i, 'tag', None) == 'moon' or type(i).__name__ == 'Moon')
		assert holes.contains(moon.sceneBoundingRect().center())  # the moon by default
	finally:
		if slot.scene() is not None:
			slot.scene().removeItem(slot)


def test_the_star_layer_builds_at_the_device_density_and_cuts_holes(dashboard):
	from PySide6.QtCore import QRectF
	from PySide6.QtGui import QPainterPath
	from LevityDash.lib.ui.colors.starsky import StarLayer
	spec = {'sky': True, 'stars': True, 'star-time': '2026-12-12T04:00:00Z', 'star-place': [40.7, -74.0]}
	hole = QPainterPath()
	hole.addRect(QRectF(0, 0, 100, 100))
	layer = StarLayer()
	size = QRectF(0, 0, 400, 300)
	whole = layer.pixmap(size, 2.0, spec, -30, 0.0)
	assert whole is not None and whole.width() == 800 and whole.height() == 600 and whole.devicePixelRatio() == 2.0
	cut = layer.pixmap(size, 2.0, spec, -30, 0.0, hole).toImage()
	assert all(cut.pixelColor(x, y).alpha() == 0 for x in range(0, 200, 7) for y in range(0, 200, 7))
	assert backdrop.starOptions({'sky': True, 'stars': True, 'milky-way': False}) == {'milky-way': False}


def test_chromatic_aberration_parts_the_colours_towards_the_edge():
	import numpy as np
	from LevityDash.lib.ui.colors import starsky
	acc = np.zeros((3, 40, 400), dtype=np.float32)
	starsky._fringe(acc, 380.0, 20.0, 1.0, np.array([1.0, 1.0, 1.0], dtype=np.float32), 0.01, (200.0, 20.0))
	xs = [(acc[c] * np.arange(400)[None, :]).sum() / acc[c].sum() for c in range(3)]
	assert xs[0] > xs[1] > xs[2]  # red further out than green, blue further in
	flat = np.zeros_like(acc)
	starsky._fringe(flat, 380.0, 20.0, 1.0, np.array([1.0, 1.0, 1.0], dtype=np.float32), 0.0, (200.0, 20.0))
	assert np.allclose(flat[0], flat[2])


def test_the_milky_way_comes_from_the_photograph_in_galactic_coordinates():
	import numpy as np
	from LevityDash.lib.ui.colors import starsky
	light = starsky._sampleMilkyWay(np.array([5.0, 180.0, 90.0]), np.array([-5.0, 0.0, 45.0])).sum(axis=0)
	assert light[0] > 2 * light[1] > 2 * light[2]  # the Sagittarius star clouds, the anticentre, high above the plane
	clouds = starsky._sampleMilkyWay(np.array([280.5, 302.8]), np.array([-32.9, -44.3])).sum(axis=0)
	assert (clouds > light[2]).all()  # both Magellanic Clouds are there


def test_faint_stars_are_splatted_where_they_are():
	import numpy as np
	from LevityDash.lib.ui.colors import starsky
	acc = np.zeros((3, 20, 30), dtype=np.float32)
	starsky._dust(acc, np.array([5.5, 20.5, -9.0]), np.array([4.5, 12.5, 3.0]), np.ones((3, 3), dtype=np.float32), 0.6)
	assert acc[0, 4, 5] == pytest.approx(1.0) and acc[1, 12, 20] == pytest.approx(1.0)
	assert acc.sum() == pytest.approx(2 * acc[:, :10, :10].sum(), rel=0.01)  # two equal stars; the one off the picture adds nothing
