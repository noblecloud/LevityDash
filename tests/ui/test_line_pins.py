"""Glyphs pinned along a line."""
import pytest

def test_pin_steps_pick_the_last_row_reached():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import PIN_DEFAULTS, pinText

	config = {**PIN_DEFAULTS, 'steps': [[0.0, 'dry'], [0.1, 'wet']]}
	assert pinText(0.0, config)[0] == 'dry'
	assert pinText(0.5, config)[0] == 'wet'
	assert pinText(-1, config)[0] == ''
	assert pinText(3, {**PIN_DEFAULTS, 'map': {'3': 'storm'}})[0] == 'storm'
	assert pinText('plain', PIN_DEFAULTS) == ('plain', None)


def test_pin_icon_names_become_glyphs():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import PIN_DEFAULTS, pinText

	text, font = pinText('wi:rain', PIN_DEFAULTS)
	assert font is not None and text != 'wi:rain'


def test_pin_map_takes_comparisons_and_drops_unnamed_values():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import PIN_DEFAULTS, pinText

	config = {**PIN_DEFAULTS, 'map': {'true': 'storm'}}
	assert pinText(True, config)[0] == 'storm'
	assert pinText(False, config)[0] == ''
