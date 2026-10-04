"""Two Realtime panels sharing one expression key.

Both panels acquire the same computed key, so the engine refcounts it. Deleting
one must release exactly one reference and stop that panel listening, and a
reload over live panels must match them by computed key rather than by the
expression text (the panel's `key` is the computed `CategoryItem`).
"""
from LevityDash.lib.plugins.computed import computedEngine
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime import Realtime

EXPR = 'max(environment.temperature.temperature, today)'


def _items(first='0%', second='50%'):
	return [
		{'type': 'realtime.text', 'name': name, 'key': EXPR,
		 'geometry': {'x': x, 'y': '0%', 'width': '50%', 'height': '100%'}}
		for name, x in (('high-a', first), ('high-b', second))
	]


def _panels(sandbox):
	return {c.stateName: c for c in sandbox.childPanels if isinstance(c, Realtime)}


def test_shared_expression_refcount_and_delete(dashboard):
	engine = computedEngine()
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '10%', 'height': '10%'})
	sandbox.state = {'items': _items()}
	dashboard.app.processEvents()
	panels = _panels(sandbox)
	a, b = panels['high-a'], panels['high-b']
	key = a.key
	assert key == b.key
	assert engine.refcount(key) == 2

	# Nothing computes without a running plugin, so publish a value by hand;
	# that creates the container both panels subscribe to.
	engine._publish(engine._entries[key], 42.0)
	dashboard.app.processEvents()
	assert a._Realtime__connectedContainer is not None
	assert b._Realtime__connectedContainer is not None

	# Reloading the same file over the live panels must not move or double-count them.
	sandbox.state = {'items': _items()}
	dashboard.app.processEvents()
	assert _panels(sandbox) == panels
	assert engine.refcount(key) == 2

	a.delete()
	dashboard.app.processEvents()
	assert engine.refcount(key) == 1
	assert a._Realtime__connectedContainer is None, 'a deleted panel is still subscribed to the shared key'
	assert b.state['key'] == EXPR

	# The survivor still follows the shared key.
	engine._publish(engine._entries[key], 43.0)
	dashboard.app.processEvents()
	assert '43' in b.display.text

	sandbox.scene().removeItem(sandbox)
