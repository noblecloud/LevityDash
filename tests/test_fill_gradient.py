"""`fill-gradient`: a text fill that is a scale's gradient around a followed value."""
import pytest
from PySide6.QtGui import QGradient
from unitcorn.temperature import Temperature

from LevityDash.lib.ui.fill_gradient import FillGradient, decodeFillGradient

SPEC = {'scale': 'TemperatureGradient', 'of': 'environment.temperature.temperature', 'spread': '8°F'}


def stops(brush):
	g = brush.gradient()
	return [s[1] for s in g.stops()]


def test_top_is_warmer_than_foot():
	brush = FillGradient(SPEC).brushFor(Temperature.Fahrenheit(70))
	g = brush.gradient()
	assert g.coordinateMode() == QGradient.CoordinateMode.ObjectBoundingMode
	assert (g.start().x(), g.start().y()) == pytest.approx((0.5, 0.0))
	assert (g.finalStop().x(), g.finalStop().y()) == pytest.approx((0.5, 1.0))
	top, foot = stops(brush)[0], stops(brush)[-1]
	assert top != foot
	assert top.red() > foot.red()  # the warm end of the scale is above


def test_spread_is_a_distance_in_any_unit():
	f = FillGradient(SPEC)
	assert f._delta(Temperature.Celsius(20)) == pytest.approx(8 * 5 / 9)
	assert f._delta(Temperature.Fahrenheit(70)) == pytest.approx(8)
	assert FillGradient({**SPEC, 'spread': 3})._delta(Temperature.Celsius(20)) == 3


def test_zero_spread_is_one_colour():
	brush = FillGradient({**SPEC, 'spread': 0}).brushFor(Temperature.Fahrenheit(70))
	assert len({c.name() for c in stops(brush)}) == 1


def test_angle():
	g = FillGradient({**SPEC, 'angle': 90}).brushFor(Temperature.Fahrenheit(70)).gradient()
	assert (g.start().x(), g.start().y()) == pytest.approx((0.0, 0.5))


def test_no_number_no_brush():
	assert FillGradient(SPEC).brushFor('n/a') is None
	assert FillGradient(SPEC).brushFor(None) is None


@pytest.mark.parametrize('spec', [{'scale': 'x'}, {**SPEC, 'bogus': 1}, {**SPEC, 'spread': 'wide'}, {**SPEC, 'angle': 'up'}, {**SPEC, 'stops': 1}, 'red'])
def test_bad_specs(spec):
	with pytest.raises((ValueError, TypeError)):
		decodeFillGradient(spec)
