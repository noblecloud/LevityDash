"""Gauge tick labels: each unit's compact convention, with the spacing as a floor.

A dial face is not a readout. inHg reads `29.92` but its ticks read `28 29 30`;
hPa reads `1013.2` but its ticks read `1000 1010 1020`. That difference belongs to
the unit, so the tick labels ask WeatherUnits for the unit's *compact* format
rather than spelling out a precision per gauge.

The exception is a scale too fine for the convention to carry: ticks at
29.90-30.10 by 0.05 would all label `30`, so the spacing sets a floor under the
compact precision and the digits come back only where the scale forces them.
"""
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Gauge import GaugeTickTextGroup
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime import Realtime


def _gauge(dashboard, key='environment.pressure.pressure', display=None):
	display = display or {}
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '30%', 'height': '30%'})
	sandbox.state = {'items': [{
		'type': 'realtime.gauge', 'name': 'g', 'key': key,
		'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'},
		'display': display,
	}]}
	dashboard.app.processEvents()
	gauge = next(c for c in sandbox.childPanels if isinstance(c, Realtime)).display
	return sandbox, gauge


def _labels(dashboard, gauge, ticks='major'):
	"""{tick value: rendered label} for one graduation group."""
	dashboard.app.processEvents()
	group = getattr(gauge, f'{ticks}Divisions').labels
	return {round(float(label.value), 6): label.text for label in group}


def test_whole_inch_ticks_drop_the_reading_precision(dashboard):
	"""The case in the brief: 28-32 inHg read as 28 29 30, not 28.00 29.00."""
	sandbox, gauge = _gauge(dashboard, display={'range': {'min': 28, 'max': 32}})
	labels = _labels(dashboard, gauge)
	assert labels, 'no major tick labels'
	for value, text in labels.items():
		assert text == f'{value:.0f}', f'{value} labelled {text!r} - a whole-inch dial shows whole inches'
	sandbox.scene().removeItem(sandbox)


def test_the_word_unit_is_not_repeated_on_every_tick(dashboard):
	"""Said once, by the unit label under the reading - not 5 times round the dial."""
	sandbox, gauge = _gauge(dashboard, display={'range': {'min': 28, 'max': 32}})
	for value, text in _labels(dashboard, gauge).items():
		assert 'inHg' not in text and 'mmHg' not in text, f'{value} labelled {text!r} - the word unit came back'
	sandbox.scene().removeItem(sandbox)


def test_a_fine_scale_gets_its_digits_back(dashboard):
	"""29.90-30.10 by 0.05: the spacing floor of 1c, which is its whole point.

	Compact alone would label these `30 30 30 30 30` - five identical labels.
	The floor puts back exactly the digits the scale needs, so the labels stay
	distinct.

	Driven through `format_value` on a stand-in group rather than a built
	29.9-30.1 gauge: that gauge raises `Gauge has no attribute '_needle'`
	on construction, which predates this work (it reproduces with these
	changes stashed) and belongs to the needle, not to tick formatting. What
	is under test here is the floor arithmetic.
	"""
	class _Ticks:
		tick_values = [29.9 + 0.05 * i for i in range(5)]

	class _Group(GaugeTickTextGroup):
		def __init__(self, ticks):
			self._ticks = ticks

	group = _Group(_Ticks())
	# Two, not one: at one decimal 29.90 and 29.95 both render `29.9`, so the
	# labels would still collide. Asserted against the property rather than a
	# literal, since the answer depends on the interval chosen here.
	assert group._spacingPrecision() == 2
	one_place = {round(v, 1) for v in _Ticks.tick_values}
	assert len(one_place) < len(_Ticks.tick_values), 'one decimal genuinely collides'

	from WeatherUnits.pressure import InchOfMercury
	labels = [group.format_value(InchOfMercury(v)) for v in _Ticks.tick_values]
	assert len(set(labels)) == len(labels), f'tick labels collided: {labels}'


def test_a_whole_number_dial_needs_no_floor(dashboard):
	"""The floor is a floor, not a rule: whole inches must stay whole."""
	sandbox, gauge = _gauge(dashboard, display={'range': {'min': 28, 'max': 32}})
	group = gauge.majorDivisions.labels
	assert group._spacingPrecision() is None, 'a 1-inch spacing needs no decimals'
	sandbox.scene().removeItem(sandbox)


def test_a_user_format_merges_over_the_default(dashboard):
	"""`format: {precision: 0}` must not bring the word unit back on every tick."""
	sandbox, gauge = _gauge(dashboard, display={
		'range': {'min': 28, 'max': 32},
		'major': {'labels': {'format': {'precision': 0}}},
	})
	for value, text in _labels(dashboard, gauge).items():
		assert 'inHg' not in text and 'mmHg' not in text, f'{value} labelled {text!r} - the word unit came back'
	sandbox.scene().removeItem(sandbox)


def test_temperature_ticks_keep_their_degree_symbol(dashboard):
	"""Symbols stay glued to the number; only the WORD unit is dropped."""
	sandbox, gauge = _gauge(dashboard, key='environment.temperature.temperature', display={
		'range': {'min': 60, 'max': 100},
	})
	labels = _labels(dashboard, gauge)
	texts = ' '.join(labels.values())
	assert labels, 'no temperature tick labels'
	assert '°' in texts, f'temperature ticks lost the degree symbol: {sorted(labels.values())}'
	assert 'F' not in texts, f'temperature ticks grew the word unit: {sorted(labels.values())}'
	sandbox.scene().removeItem(sandbox)


def test_the_reading_itself_is_untouched(dashboard):
	"""The dial changes; the readout does not. A reading keeps its precision."""
	sandbox, gauge = _gauge(dashboard, display={'range': {'min': 28, 'max': 32}})
	from WeatherUnits.pressure import InchOfMercury
	assert str(InchOfMercury(29.97)) == '29.97 inHg', 'the reading lost its precision'
	sandbox.scene().removeItem(sandbox)


def test_a_bad_format_still_cannot_blank_the_dial(dashboard):
	"""The existing guard, kept: a failing spec logs and falls back."""
	sandbox, gauge = _gauge(dashboard, display={
		'range': {'min': 28, 'max': 32},
		'major': {'labels': {'format': {'precision': 'nonsense'}}},
	})
	dashboard.app.processEvents()
	group = gauge.majorDivisions.labels
	from WeatherUnits.pressure import InchOfMercury
	assert group.format_value(InchOfMercury(28.0)), 'a bad spec returned nothing'
	sandbox.scene().removeItem(sandbox)