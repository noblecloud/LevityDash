"""A colour that follows a value: `color: {scale: ..., of: ...}` (lib/ui/colors/bound.py)."""
import pytest
import WeatherUnits as wu

from LevityDash.lib.ui.colors.bound import BoundColor, decodeColor, isBound
from LevityDash.lib.ui.colors import Color
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Label import Label
from LevityDash.lib import valuesource
from LevityDash.lib.valuesource import installStandIn
from statekit.binding import Constant

F = wu.Temperature.Fahrenheit
C = wu.Temperature.Celsius


def test_a_scale_and_a_value_make_a_bound_colour():
	assert isBound({'scale': 'TemperatureGradient', 'of': 'a.b.c'})
	assert not isBound({'color': '#fff', 'alpha': 0.4})
	assert isinstance(decodeColor({'scale': 'TemperatureGradient', 'of': 'a.b.c'}), BoundColor)
	assert isinstance(decodeColor('#ff0000'), Color)


def test_the_same_temperature_in_two_units_is_the_same_colour():
	bound = BoundColor({'scale': 'TemperatureGradient', 'of': 'a.b.c'})
	assert bound.colorFor(F(70)) == bound.colorFor(C(21.111111))
	assert bound.colorFor(F(20)) != bound.colorFor(F(100))


def test_unit_stops_are_placed_by_reading_in_any_unit():
	bound = BoundColor({'scale': {'32°F': '#0000ff', '212°F': '#ff0000'}, 'of': 'a.b.c'})
	cold, hot = bound.colorFor(C(0)), bound.colorFor(C(100))
	assert cold.blue > cold.red and hot.red > hot.blue


@pytest.mark.parametrize('value', [None, True])
def test_a_value_with_no_number_has_no_colour(value):
	assert BoundColor({'scale': 'TemperatureGradient', 'of': 'a.b.c'}).colorFor(value) is None


@pytest.mark.parametrize('spec', [
	{'scale': 'TemperatureGradient', 'of': 'a.b.c', 'speed': 3},
	{'scale': 'TemperatureGradient', 'of': True},
	{'scale': 'NoSuchGradient', 'of': 'a.b.c'},
])
def test_a_bad_bound_colour_is_refused(spec):
	with pytest.raises((ValueError, TypeError, KeyError)):
		BoundColor(spec)


def _label(dashboard, color):
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '10%', 'height': '10%'})
	sandbox.state = {'items': [{
		'type': 'text', 'text': 'hi', 'color': color,
		'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'},
	}]}
	dashboard.app.processEvents()
	return sandbox, next(c for c in sandbox.childPanels if isinstance(c, Label))


def test_a_label_takes_the_colour_of_its_value_and_saves_the_spec(dashboard):
	spec = {'scale': 'TemperatureGradient', 'of': 'environment.temperature.temperature'}
	saved = valuesource._standIn
	installStandIn(lambda value, label='', effect='': Constant(F(100)))
	try:
		sandbox, label = _label(dashboard, spec)
		try:
			expected = BoundColor(spec).colorFor(F(100))
			assert label.color == expected
			assert label.color != Color.default
			assert label.encodedState['color'] == spec
		finally:
			sandbox.scene().removeItem(sandbox)
	finally:
		installStandIn(saved)


def test_a_label_keeps_its_fallback_until_the_source_has_a_value(dashboard):
	spec = {'scale': 'TemperatureGradient', 'of': 'a.b.c', 'fallback': '#336699'}
	saved = valuesource._standIn
	installStandIn(lambda value, label='', effect='': None)
	try:
		sandbox, label = _label(dashboard, spec)
		try:
			assert label.color == Color.decode('#336699')
		finally:
			sandbox.scene().removeItem(sandbox)
	finally:
		installStandIn(saved)
