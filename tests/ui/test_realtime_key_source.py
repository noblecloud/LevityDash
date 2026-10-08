"""A Realtime panel's key is opened through ``openValueSource``.

The Studio draws a gauge without booting the dashboard: it registers a stand-in
in ``lib/valuesource`` that replaces ``openValueSource`` (devtools/_studio_stage.py).
The panel's key setter used to build its ``KeySource`` from
``acquireValueSource``/``KeySource`` directly, so it was outside that path - a
Studio-built Realtime panel would register its expression with the *real*
computed engine instead of asking the stand-in. Latent today (the Studio never
builds a Realtime panel); this pins the setter to ``openValueSource`` and fails
if the direct acquire comes back.
"""
from LevityDash.lib.plugins.computed import computedEngine
from LevityDash.lib.plugins.expressions import Expression
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime import Realtime
from LevityDash.lib import valuesource
from LevityDash.lib.valuesource import installStandIn
from statekit.binding import Constant

EXPR = 'max(environment.temperature.temperature, today)'


def _panel(dashboard, key):
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '10%', 'height': '10%'})
	sandbox.state = {'items': [{
		'type': 'realtime.text', 'name': 'keyed', 'key': key,
		'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'},
	}]}
	dashboard.app.processEvents()
	return sandbox, next(c for c in sandbox.childPanels if isinstance(c, Realtime))


def test_realtime_key_is_opened_through_open_value_source(dashboard):
	engine = computedEngine()
	computedKey = Expression.parse(EXPR).key
	seen = []

	def standIn(value, label='', effect=''):
		seen.append(value)
		return Constant(0)

	saved = valuesource._standIn
	installStandIn(standIn)
	try:
		before = engine.refcount(computedKey)
		sandbox, panel = _panel(dashboard, EXPR)
		try:
			dashboard.app.processEvents()
			assert EXPR in seen, 'the key setter never asked openValueSource'
			assert engine.refcount(computedKey) == before, (
				'the key setter registered the expression with the real computed engine '
				'instead of the stand-in'
			)
		finally:
			sandbox.scene().removeItem(sandbox)
	finally:
		installStandIn(saved)
