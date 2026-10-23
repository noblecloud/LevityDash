"""A number that follows a value: `opacity: {of, from, to}` (lib/ui/bound_number.py)."""
import pytest
import unitcorn as wu

from LevityDash.lib import valuesource
from LevityDash.lib.ui.bound_number import BoundNumber, decodeNumber, isBound
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.valuesource import installStandIn
from statekit.binding import Constant

F = wu.Temperature.Fahrenheit
C = wu.Temperature.Celsius
SPEC = {'of': 'environment.humidity.humidity', 'from': [0, 100], 'to': [0.2, 1]}


def test_a_mapping_with_of_from_and_to_is_a_bound_number():
	assert isBound(SPEC) and not isBound({'of': 'a.b', 'to': [0, 1]}) and not isBound(0.5)
	assert isinstance(decodeNumber(SPEC, float), BoundNumber)
	assert decodeNumber(0.5, float) == 0.5


@pytest.mark.parametrize('value, expected', [(0, 0.2), (50, 0.6), (100, 1.0), (-20, 0.2), (400, 1.0)])
def test_the_reading_is_placed_on_the_range_in_a_straight_line(value, expected):
	assert BoundNumber(SPEC).numberFor(value) == pytest.approx(expected)


def test_clamp_false_runs_past_the_ends_and_a_reversed_range_runs_backwards():
	assert BoundNumber({**SPEC, 'clamp': False}).numberFor(150) == pytest.approx(1.4)
	assert BoundNumber({'of': 'a.b', 'from': [0, 10], 'to': [1, 0]}).numberFor(2.5) == pytest.approx(0.75)


def test_the_ends_of_from_may_carry_units_and_the_reading_may_arrive_in_any():
	bound = BoundNumber({'of': 'a.b', 'from': ['32°F', '212°F'], 'to': [0, 1]})
	assert bound.numberFor(F(122)) == pytest.approx(0.5)
	assert bound.numberFor(C(50)) == pytest.approx(0.5)


@pytest.mark.parametrize('value', [None, True])
def test_a_value_with_no_number_gives_none(value):
	assert BoundNumber(SPEC).numberFor(value) is None


@pytest.mark.parametrize('spec', [
	{**SPEC, 'speed': 3},
	{**SPEC, 'of': True},
	{**SPEC, 'from': [5, 5]},
	{**SPEC, 'from': [0, 'wet']},
	{**SPEC, 'to': [0, 1, 2]},
	{**SPEC, 'clamp': 'yes'},
	{**SPEC, 'fallback': 'x'},
])
def test_a_bad_bound_number_is_refused(spec):
	with pytest.raises((ValueError, TypeError)):
		BoundNumber(spec)


def _item(dashboard, opacity):
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '10%', 'height': '10%'})
	sandbox.state = {'items': [{
		'type': 'group', 'opacity': opacity, 'items': [],
		'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'},
	}]}
	dashboard.app.processEvents()
	return sandbox, sandbox.childPanels[0]


def test_an_items_opacity_follows_its_value_and_saves_the_spec(dashboard):
	saved = valuesource._standIn
	installStandIn(lambda value, label='', effect='': Constant(50))
	try:
		sandbox, item = _item(dashboard, SPEC)
		try:
			assert item.opacity() == pytest.approx(0.6)
			assert item.encodedState()['opacity'] == SPEC
		finally:
			sandbox.scene().removeItem(sandbox)
	finally:
		installStandIn(saved)


def test_a_plain_opacity_is_unchanged_and_saved_as_a_number(dashboard):
	sandbox, item = _item(dashboard, 0.4)
	try:
		assert item.opacity() == pytest.approx(0.4)
		assert item.encodedState()['opacity'] == pytest.approx(0.4)
	finally:
		sandbox.scene().removeItem(sandbox)


def test_changing_a_bound_opacity_to_a_plain_one_lets_go_of_the_source(dashboard):
	saved = valuesource._standIn
	installStandIn(lambda value, label='', effect='': Constant(100))
	try:
		sandbox, item = _item(dashboard, SPEC)
		try:
			assert item.opacity() == pytest.approx(1.0)
			item.state = {'opacity': 0.3}
			assert item.opacity() == pytest.approx(0.3)
			assert not item.numbers._followers.get(item)
		finally:
			sandbox.scene().removeItem(sandbox)
	finally:
		installStandIn(saved)
