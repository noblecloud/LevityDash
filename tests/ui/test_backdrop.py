"""The board's ground: a flat colour or a gradient, from `background:` or the theme."""
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
