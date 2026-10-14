"""Fitting the board's text reaches a fixed point, so it does not depend on update order."""
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import Text


def test_refit_all_text_is_idempotent(dashboard):
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '40%', 'height': '30%'})
	sandbox.state = {'items': [{
		'type': 'realtime.gauge', 'name': 'g', 'key': 'environment.temperature.temperature',
		'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'},
		'display': {'range': {'min': -50, 'max': 50}, 'value-label': {'position': 'float-under', 'size': '14%'}},
	}]}
	dashboard.app.processEvents()
	view = dashboard.view
	view._refitAllText()
	first = view._textSnapshot()
	assert first, 'the board has text to fit'
	view._refitAllText()
	assert view._textSnapshot() == first


def test_current_text_rect_rebuilds_a_stale_rect(dashboard):
	"""A cached rect whose inputs moved since it was built is rebuilt before it is fitted against."""
	item = next(i for i in dashboard.scene.items() if isinstance(i, Text) and i.text)
	fresh = item.currentTextRect()
	assert item.currentTextRect() is fresh, 'an up-to-date rect is reused'
	item._builtSignature = None
	rebuilt = item.currentTextRect()
	assert rebuilt is not fresh
	assert item._layoutSignature() == item._builtSignature
