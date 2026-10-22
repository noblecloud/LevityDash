"""The dashboard's ground: a flat colour or a gradient, from `background:` or the theme."""
import pytest
from PySide6.QtCore import QRectF, Qt

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
