"""Colour maths for the Oklch and emissive colour forms. Expected bytes come from running
color_sphere/demo.html's `oklchColor` and `displayColor` in node (emission 3.18, saturation 1)."""
import pytest

from LevityDash.lib.ui.colors import Color
from LevityDash.lib.ui.colors import oklch


DEMO = {0: (255, 94, 154), 30: (255, 101, 82), 145: (70, 255, 95), 200: (1, 245, 255), 266: (112, 152, 255), 320: (229, 119, 255)}


@pytest.mark.parametrize('hue,expected', DEMO.items())
def test_display_color_matches_demo(hue, expected):
	got = oklch.display_color(oklch.oklch_color(hue))
	assert tuple(round(c * 255) for c in got) == expected
	assert Color.decode({'hue': hue, 'emission': 3.18}).rgb == expected


def test_gamut_clamp_keeps_colour_in_range():
	# hue 200 at L .70 C .20 is outside sRGB; the search lowers chroma
	assert all(0.0 <= c <= 1.0 for c in oklch.oklch_color(200))


def test_oklch_string_and_hue_agree():
	assert Color.decode('oklch(0.70 0.20 145)') == Color.decode({'hue': 145})
	assert Color.decode('oklch(70% 0.2 145)') == Color.decode('oklch(0.7, 0.2, 145deg)')


def test_oklch_alpha():
	assert Color.decode('oklch(0.7 0.2 145 / 50%)').alpha == 128


def test_plain_colours_keep_their_meaning():
	assert Color.decode('#ff8800').rgb == (255, 136, 0)
	assert Color.decode([1, 2, 3]).rgb == (1, 2, 3)


def test_emission_off_changes_nothing_but_encoding():
	# srgb round trip of a plain colour is stable
	assert Color.decode({'color': '#336699', 'emission': None}).rgb == (0x33, 0x66, 0x99)


def test_srgb_round_trip():
	for c in ((0.0, 0.2, 1.0), (0.5, 0.5, 0.5)):
		back = oklch.srgb_to_linear(oklch.linear_to_srgb(c))
		assert all(abs(a - b) < 1e-9 for a, b in zip(c, back))


def test_palette_schemes():
	assert oklch.scheme_hues(145, 'triadic') == [145, 265, 25]
	assert oklch.scheme_hues(10, 'analogous') == [10, 40, 340]
	with pytest.raises(ValueError):
		oklch.scheme_hues(0, 'nonsense')
	a = Color.decode({'palette': {'hue': 145, 'scheme': 'triadic'}, 'index': 1})
	assert a == Color.decode({'hue': 265})


def test_bad_forms_raise():
	for bad in ('oklch(banana)', {'hue': 10, 'bogus': 1}, {'hue': 10, 'emission': -1}):
		with pytest.raises(ValueError):
			Color.decode(dict(bad) if isinstance(bad, dict) else bad)
