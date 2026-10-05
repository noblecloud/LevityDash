"""A value label set to `float-under` draws in a strip below the dial."""
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime import Realtime


def test_float_under_value_sits_below_the_dial(dashboard):
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '30%', 'height': '30%'})
	sandbox.state = {'items': [{
		'type': 'realtime.gauge', 'name': 'g', 'key': 'environment.temperature.temperature',
		'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'},
		'display': {'range': {'min': -50, 'max': 50}, 'value-label': {'position': 'float-under', 'size': '14%'}},
	}]}
	dashboard.app.processEvents()
	gauge = next(c for c in sandbox.childPanels if isinstance(c, Realtime)).display
	strip = gauge._sideValueRect()
	dial = gauge._dialRect()
	assert strip.top() >= dial.bottom() - 1e-6, 'the dial leaves the strip free'
	assert gauge.center.y() < dial.bottom()
	assert gauge.valueLabel.textBox.getTextPosition().y() > gauge.center.y(), 'the value sits below the dial centre'
