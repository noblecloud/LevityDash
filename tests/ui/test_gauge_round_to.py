"""`round_to` must pick a usable step for any range, including sub-1 ones.

A gauge narrower than one unit could not be built at all. `round_to` tested
exact float divisibility (`span % 10 ** power > 0`) and kept decrementing the
power until the remainder was exactly 0.0 - which, for a span below 1, means
walking into *negative* powers and stopping at _power = -323, where the
remainder underflows. It returned 1e-323, `rounded_min` overflowed computing
`floor(min / round_to)`, and the gauge died in `__init__`. What the caller saw
was an unrelated-looking `AttributeError: 'Gauge' object has no attribute
'_needle'`, because construction stopped before `needle` was ever set.

The loop was always bounded - it terminates at -323 - so the cost was a garbage
`round_to`, not a hang. See docs/tasks/gauge-round-to-float.md.
"""
from math import isfinite

from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime import Realtime

# The ranges from the brief. The three that already worked are here as
# regression guards: the fix must not move them.
RANGES = (
	(29.9, 30.1, 'fine barograph, 0.05 ticks'),
	(0, 0.5, 'sub-1 from zero'),
	(0, 1, 'decade - already worked'),
	(950, 1050, 'the 99<span<=350 band - already worked'),
	(28, 32, 'whole inches - already worked'),
)


def _range(dashboard, lo, hi):
	"""A GaugeRange built directly, so the test does not need a full gauge."""
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '30%', 'height': '30%'})
	sandbox.state = {'items': [{
		'type': 'realtime.gauge', 'name': 'g', 'key': 'environment.pressure.pressure',
		'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'},
		'display': {'range': {'min': lo, 'max': hi}},
	}]}
	dashboard.app.processEvents()
	gauge = next(c for c in sandbox.childPanels if isinstance(c, Realtime)).display
	return sandbox, gauge.range


def test_sub_one_ranges_produce_a_usable_step(dashboard):
	"""The bug: these returned 1e-323 and overflowed rounded_min."""
	for lo, hi, label in RANGES:
		sandbox, rng = _range(dashboard, lo, hi)
		try:
			round_to = rng.round_to
			assert isfinite(round_to), f'{label}: round_to is not finite: {round_to!r}'
			assert round_to >= 1e-12, f'{label}: round_to {round_to!r} is below any usable scale'
			assert 0 < round_to <= abs(hi - lo), f'{label}: round_to {round_to!r} is wider than the span'
		finally:
			sandbox.scene().removeItem(sandbox)


def test_rounded_min_stays_finite(dashboard):
	"""The overflow itself: floor(lo / round_to) must not blow up."""
	for lo, hi, label in RANGES:
		sandbox, rng = _range(dashboard, lo, hi)
		try:
			assert isfinite(float(rng.rounded_min)), f'{label}: rounded_min is not finite'
			assert isfinite(float(rng.rounded_max)), f'{label}: rounded_max is not finite'
		finally:
			sandbox.scene().removeItem(sandbox)


def test_the_working_ranges_are_unchanged(dashboard):
	"""0-1, 950-1050 and 28-32 were already right; pin their exact values."""
	expected = {(0, 1): 0.1, (950, 1050): 10, (28, 32): 1}
	for (lo, hi), want in expected.items():
		sandbox, rng = _range(dashboard, lo, hi)
		try:
			assert rng.round_to == want, f'{lo}-{hi}: round_to is {rng.round_to!r}, was {want!r}'
		finally:
			sandbox.scene().removeItem(sandbox)


def test_a_sub_one_gauge_actually_builds(dashboard):
	"""The regression that matters: today this raises before it draws."""
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '30%', 'height': '30%'})
	sandbox.state = {'items': [{
		'type': 'realtime.gauge', 'name': 'g', 'key': 'environment.pressure.pressure',
		'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'},
		'display': {'range': {'min': 29.9, 'max': 30.1}, 'major': {'interval': 0.05}},
	}]}
	dashboard.app.processEvents()
	gauge = next(c for c in sandbox.childPanels if isinstance(c, Realtime)).display
	assert gauge.needle is not None, 'the needle was never built'
	sandbox.scene().removeItem(sandbox)


def test_the_half_steps_survive(dashboard):
	"""29.95 and 30.05 must still be graduations.

	`round_to` sets rounded_min/rounded_max, which position every tick. A step
	of 0.1 divides the 0.2 span exactly but would snap the range to 29.9/30.0/
	30.1 and drop both half-steps - arithmetically right for the span, wrong
	for the dial.
	"""
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '30%', 'height': '30%'})
	sandbox.state = {'items': [{
		'type': 'realtime.gauge', 'name': 'g', 'key': 'environment.pressure.pressure',
		'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'},
		'display': {'range': {'min': 29.9, 'max': 30.1}, 'major': {'interval': 0.05}},
	}]}
	dashboard.app.processEvents()
	gauge = next(c for c in sandbox.childPanels if isinstance(c, Realtime)).display
	assert gauge.range.round_to <= 0.05, (
		f'round_to {gauge.range.round_to!r} is coarser than the 0.05 interval, '
		'so the half-steps would be dropped'
	)
	ticks = sorted(round(float(v), 6) for v in gauge.majorDivisions.tick_values)
	assert 29.95 in ticks and 30.05 in ticks, f'half-steps missing: {ticks}'
	sandbox.scene().removeItem(sandbox)