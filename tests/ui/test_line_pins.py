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


def test_a_row_of_pins_sits_at_one_height():
	import numpy as np
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import PIN_DEFAULTS, pinPath

	times = np.array([0.0, 100.0])
	xs = np.array([0.0, 400.0])
	ys = np.array([10.0, 300.0])
	pins = (np.array([20.0, 80.0]), ['sun', 'sun'])
	config = {**PIN_DEFAULTS, 'size': 14, 'spacing': 1.0}
	onLine = pinPath(times, xs, ys, *pins, config, 96.0)
	row = pinPath(times, xs, ys, *pins, config, 96.0, 200.0)
	assert onLine.boundingRect().height() > 100          # the two marks follow a rising line
	assert row.boundingRect().height() < 20               # both sit on one row
	assert row.boundingRect().center().y() == pytest.approx(200.0, abs=8)


def test_pins_take_an_at_height_and_strip_is_a_plot_kind():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import LinePlot, StripPlot, plotClassFor

	decode = LinePlot.statefulItems['pins'].decodeValue
	assert decode({'key': 'a.b', 'at': 0.25}, None)['at'] == 0.25
	assert decode({'key': 'a.b', 'at': 7}, None)['at'] == 1.0
	assert 'at' not in decode({'key': 'a.b'}, None)
	for name in ('strip', 'Strip', 'row', 'timeline'):
		assert plotClassFor({'type': name}) is StripPlot
	assert StripPlot._rowAt == 0.5 and StripPlot._drawsLine is False
	assert LinePlot._rowAt is None and LinePlot._drawsLine is True
