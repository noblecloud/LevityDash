"""A saved item loads back as the same item: a gauge keeps its `type` and saves nothing derived, a text keeps its font."""
from PySide6.QtTest import QTest

from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime import Realtime


def _item(dashboard, kind):
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '30%', 'height': '30%'})
	sandbox.state = {'items': [{
		'type': kind, 'name': 'g', 'key': 'environment.temperature.temperature',
		'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'},
	}]}
	for _ in range(5):
		QTest.qWait(20)
		dashboard.app.processEvents()
	return next(c for c in sandbox.childPanels if isinstance(c, Realtime))


def test_each_display_saves_its_own_type(dashboard):
	for kind, saved in (('realtime.gauge', 'realtime.gauge'), ('realtime.bar', 'realtime.bar'), ('realtime.text', 'realtime')):
		assert _item(dashboard, kind).state['type'] == saved


def test_the_derived_centre_is_not_saved(dashboard):
	gauge = _item(dashboard, 'realtime.gauge')
	assert 'center_offset' not in gauge.display.state


def _label(dashboard, **fields):
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '30%', 'height': '30%'})
	sandbox.state = {'items': [{'type': 'text', 'name': 't', 'text': 'x', 'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'}, **fields}]}
	for _ in range(5):
		QTest.qWait(20)
		dashboard.app.processEvents()
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Label import Label
	return next(c for c in sandbox.childPanels if isinstance(c, Label))


def test_a_text_font_is_saved_and_a_theme_font_keeps_its_token(dashboard):
	assert _label(dashboard, font='$display').state['font'] == '$display'
	assert _label(dashboard, font='Roboto').state['font'] == 'Roboto'
