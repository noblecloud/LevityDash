"""The palette check run when a theme loads: text contrast and data colours that share a hue."""
import logging

from LevityDash.lib.ui.colors import contrast as palette, theme


def inline(**colors):
	return theme.Theme.decode({'extends': 'default', 'colors': colors})


def test_every_shipped_theme_passes():
	for name in theme.available():
		assert palette.audit(theme.load(name)) == [], name


def test_contrast_of_black_and_white_is_21():
	assert round(palette.contrast((0, 0, 0), (1, 1, 1))) == 21


def test_faint_text_under_4_5_to_1_is_named():
	found = palette.audit(inline(faint='#303038'))
	assert len(found) == 1 and '$faint' in found[0] and '4.5:1' in found[0]


def test_text_with_alpha_is_measured_over_the_background():
	found = palette.audit(inline(muted={'color': '$text', 'alpha': 0.2}))
	assert any('$muted' in f for f in found)


def test_two_data_colours_of_one_hue_are_named_but_grey_ones_are_not():
	found = palette.audit(inline(**{'series-1': '#e53935', 'series-2': '#ff5a50'}))
	assert any('$series-1 and $series-2' in f for f in found)
	assert palette.audit(inline(**{'series-1': '#808080', 'series-2': '#858585'})) == []


def test_loading_warns_once(caplog):
	t = inline(faint='#303038')
	log = logging.getLogger('palette-test')
	with caplog.at_level(logging.WARNING, logger='palette-test'):
		palette.check_theme(t, log)
		palette.check_theme(t, log)
	assert [r for r in caplog.records if r.levelno == logging.WARNING] and len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1 and 'faint' in caplog.text
