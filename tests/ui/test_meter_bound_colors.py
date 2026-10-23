"""Gauge and bar colours go through one door (`ColorSlots`), so a `{scale, of}` colour follows its value anywhere."""
import pytest
import WeatherUnits as wu

from LevityDash.lib import valuesource
from LevityDash.lib.ui.colors.bound import ColorSlots, LiveColor
from LevityDash.lib.ui.colors import Color
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime import Realtime
from LevityDash.lib.valuesource import installStandIn
from statekit.binding import Constant

F = wu.Temperature.Fahrenheit
BOUND = {'scale': 'TemperatureGradient', 'of': 'environment.temperature.feelsLike'}


def _display(dashboard, type_, display):
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '30%', 'height': '30%'})
	sandbox.state = {'items': [{
		'type': type_, 'name': 'm', 'key': 'environment.temperature.temperature',
		'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'},
		'display': display,
	}]}
	dashboard.app.processEvents()
	return sandbox, next(c for c in sandbox.childPanels if isinstance(c, Realtime)).display


@pytest.fixture
def hot():
	saved = valuesource._standIn
	installStandIn(lambda value, label='', effect='': Constant(F(100)))
	yield
	installStandIn(saved)


def test_slots_give_a_colour_for_a_plain_spec_and_a_live_one_for_a_bound_spec():
	slots = ColorSlots(lambda: None)
	assert isinstance(slots.slot('#ff0000'), Color)
	live = slots.slot(BOUND, owner='a')
	assert isinstance(live, LiveColor) and live.spec == BOUND
	slots.releaseAll()


def test_a_gauge_arc_and_fill_follow_their_value_and_save_the_spec(dashboard, hot):
	sandbox, gauge = _display(dashboard, 'realtime.gauge', {'arc': {'color': BOUND}, 'fill': {'from': 0, 'to': 50, 'color': BOUND}})
	try:
		expected = Color.decode('#000000').QColor
		assert isinstance(gauge.arc.color, LiveColor)
		assert gauge.arc.color.QColor != expected
		assert gauge._fillItem._color.QColor == gauge.arc.color.QColor
		assert gauge.arc.encodedState()['color'] == BOUND
	finally:
		sandbox.scene().removeItem(sandbox)


def test_a_bar_follows_a_bound_fill_colour_when_it_paints(dashboard, hot):
	sandbox, bar = _display(dashboard, 'realtime.bar', {'range': {'min': 0, 'max': 100}, 'fill': {'color': BOUND}})
	try:
		assert bar._qc(BOUND) != bar._qc('#00ff00')
		assert bar._qc(BOUND) == bar._qc(dict(BOUND)), 'one source for equal specs'
	finally:
		sandbox.scene().removeItem(sandbox)
