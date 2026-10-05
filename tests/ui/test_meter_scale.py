"""`Scale` against the degrees arithmetic it replaces.

`Gauge.value_to_angle` used to turn a value into a dial angle inline; the scale
now turns it into a fraction and the arc turns that into an angle. The test that
matters compares the two end to end, over ranges that are plain, inverted, offset
and cyclic - including values outside the range, which is where a needle sits
when its value runs off the end of the scale.
"""
import pytest

from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.scale import Scale


def old_value_to_angle(value, start, end, min_, range_, wrap):
	"""`Gauge.value_to_angle`, verbatim from before the split."""
	s, e = start, end
	if wrap:
		span = float(range_)
		return s + (float(value - min_) % span) / span * (e - s)
	angle = float(value - min_) / range_ * (e - s) + s
	return sorted((s, angle, e))[1]


def new_value_to_angle(value, start, end, min_, range_, wrap):
	t = Scale.from_span(min_, range_, wrap).toT(value)
	return start + t * (end - start)


#: start, end, min, range, wrap
CASES = [
	(-120, 120, 0, 100, False),
	(0, 360, 0, 100, False),
	(120, -120, 0, 100, False),
	(-90, 90, -20, 50, False),
	(0, 240, 32, 180, False),
	(0, 360, 0, 360, True),
	(-120, 120, 0, 12, True),
	(0, 360, 0, 1, True),
	(0, 360, -180, 360, True),
]

INSIDE = ['0.1', '12', '25', '50', '99.9', '-19.5', '0.0001']
OUTSIDE = ['-1000', '-20', '100', '150', '360', '1e6']


@pytest.mark.parametrize(('start', 'end', 'min_', 'range_', 'wrap'), CASES)
def test_matches_the_old_degrees_arithmetic(start, end, min_, range_, wrap):
	for text in INSIDE + OUTSIDE:
		value = float(text)
		old = old_value_to_angle(value, start, end, min_, range_, wrap)
		new = new_value_to_angle(value, start, end, min_, range_, wrap)
		assert new == pytest.approx(old, rel=1e-12, abs=1e-12), f'{value} on {start}..{end}'


@pytest.mark.parametrize(('start', 'end', 'min_', 'range_', 'wrap'), CASES)
def test_in_range_values_are_bit_for_bit_the_same(start, end, min_, range_, wrap):
	"""Inside the range the two are the same operations in the same order - no tolerance."""
	for text in INSIDE:
		value = float(text)
		assert new_value_to_angle(value, start, end, min_, range_, wrap) == old_value_to_angle(
			value, start, end, min_, range_, wrap), f'{value} on {start}..{end}'


def test_to_t_clamps_without_wrap():
	scale = Scale(0, 100)
	assert scale.toT(-5) == 0.0
	assert scale.toT(50) == 0.5
	assert scale.toT(500) == 1.0


def test_to_t_wraps_when_asked():
	scale = Scale(0, 360, wrap=True)
	assert scale.toT(0) == pytest.approx(0.0)
	assert scale.toT(90) == pytest.approx(0.25)
	assert scale.toT(450) == pytest.approx(0.25)
	assert scale.toT(-90) == pytest.approx(0.75)


def test_from_t_is_the_inverse():
	scale = Scale(-20, 50)
	for t in (0.0, 0.25, 0.5, 0.75, 1.0):
		assert scale.toT(scale.fromT(t)) == pytest.approx(t)


def test_span_keeps_what_it_was_given():
	"""`from_span` exists because ``rounded_min``/``rounded_range`` are a min and a
	span, and ``min + span - min`` is not always ``span`` in binary floating point."""
	scale = Scale.from_span(0.1, 0.3)
	assert scale.span == 0.3
	assert scale.max == pytest.approx(0.4)


def test_zero_span_does_not_divide_by_zero():
	assert Scale(5, 5).toT(7) == 0.0


def test_span_of_between_positions():
	scale = Scale(0, 100)
	assert scale.spanOf(0.25, 0.75) == pytest.approx(50)
