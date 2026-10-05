"""Gauge fill ends fed by value sources: live update, release and YAML round-trip."""
from PySide6.QtTest import QTest

from LevityDash.lib.plugins.computed import computedEngine
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime import Realtime

EXPR = 'max(environment.temperature.temperature, today)'


def _settle(dashboard):
	dashboard.app.processEvents()


def _engine_idle(dashboard, engine, key):
	# The engine computes in the background and publishes Missing (no data in this
	# test) which would clear a hand-published value; let that land first.
	for _ in range(100):
		QTest.qWait(20)
		dashboard.app.processEvents()
		if engine._entries[key].state == 'idle':
			return


def _gauge(dashboard, fill):
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '30%', 'height': '30%'})
	sandbox.state = {'items': [{
		'type': 'realtime.gauge', 'name': 'g', 'key': 'environment.temperature.temperature',
		'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'},
		'display': {'range': {'min': -20, 'max': 20}, 'fill': fill},
	}]}
	dashboard.app.processEvents()
	gauge = next(c for c in sandbox.childPanels if isinstance(c, Realtime)).display
	return sandbox, gauge


def test_fill_follows_source_and_releases(dashboard):
	engine = computedEngine()
	sandbox, gauge = _gauge(dashboard, {'from': 0, 'to': EXPR})
	item = gauge._fillItem
	assert item is not None
	key = item._bindings[0].source.key
	assert engine.refcount(key) >= 1
	assert item._pending == {'to'}, 'no value yet: the fill is hidden'
	_engine_idle(dashboard, engine, key)
	assert not item.isVisibleTo(None)

	engine._publish(engine._entries[key], 10.0)
	# The fill attaches to the new container on a short timer.
	dashboard.wait_until(lambda: not item._pending, message='the fill receives the first value')
	a, b = item._angles()
	assert not item._pending and not item.path().isEmpty() and item.isVisibleTo(None) and b > a, 'a positive value grows the fill clockwise from 0'

	engine._publish(engine._entries[key], -10.0)
	dashboard.wait_until(lambda: item._angles()[1] < item._angles()[0], message='the fill follows the negative value')
	a2, b2 = item._angles()
	assert b2 < a2 and b2 < b, 'a negative value grows the fill the other way from 0'
	assert abs(a2 - a) < 1e-6, 'the from end stays at 0'

	before = engine.refcount(key)
	gauge.fill = None
	assert engine.refcount(key) == before - 1
	sandbox.scene().removeItem(sandbox)


def test_fill_round_trip(dashboard):
	fill = {'from': 0, 'to': EXPR, 'weight': '5%', 'color': '#ff8a3d'}
	sandbox, gauge = _gauge(dashboard, fill)
	saved = gauge.state['fill']
	assert saved == fill
	assert type(saved) is dict and isinstance(saved['to'], str)
	gauge.fill = None
	sandbox.scene().removeItem(sandbox)


def test_bad_fill_source_never_raises(dashboard):
	sandbox, gauge = _gauge(dashboard, {'to': 'max((('})
	assert gauge._fillItem is None or not gauge._fillItem.isVisible()
	gauge.fill = None
	sandbox.scene().removeItem(sandbox)


def test_deleting_the_panel_releases_fill_and_marker_sources(dashboard):
	engine = computedEngine()
	sandbox, gauge = _gauge(dashboard, {'from': 0, 'to': EXPR})
	gauge.markers = [{'value': EXPR}]
	key = gauge._fillItem._bindings[0].source.key
	before = engine.refcount(key)
	assert before >= 2, 'the fill and the marker each hold the expression'
	panel = next(c for c in sandbox.childPanels if isinstance(c, Realtime))
	panel.delete()
	_settle(dashboard)
	assert engine.refcount(key) == before - 2
	sandbox.scene().removeItem(sandbox)
