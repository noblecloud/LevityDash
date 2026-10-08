"""The EV caption's unit is stable from the first paint.

The showcase's EV gauge caption reads ``ev.charge.range`` and printed ``313 km``
in some renders and ``194 mi`` in others. The value is a Length, and WeatherUnits'
``Measurement.localize`` resolved the preferred unit through ``Generic`` - a
*set* of generic bases iterated in class-hash order - so ``[Units] length = mi``
was applied or not from one process to the next (length is the one dimension
whose ``type`` is a system class, ``Metric Length``, so the config lookup misses
and lands on that fallback). ``localizeValue`` resolves the dimension class from
the MRO instead; this pins the caption text for a fixed config.
"""
from datetime import datetime

import pytest

from LevityDash import LevityDashboard
from LevityDash.lib import valuesource
from LevityDash.lib.plugins.builtin.Mock import _TIME_FORMAT
from LevityDash.lib.plugins.schema import LevityDatagram
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime import Realtime
from LevityDash.lib.valuesource import installStandIn

KEY = 'ev.charge.range'
GAUGE_KEY = 'ev.charge.level'
#: The seeded config asks for ``length = mi``; a kilometre reading must print in
#: miles, always - not whichever unit the process happened to pick.
PREFERRED = 'mi'


@pytest.fixture
def pinned_length_unit(monkeypatch):
	"""Pin the preferred length unit the caption resolves against.

	The suite's WeatherUnits config is whatever ``WU_CONFIG_PATH`` pointed at when
	WeatherUnits was first imported. The app sets that at ``lib.config`` import,
	but a devtools test can import WeatherUnits first, leaving the process on
	WeatherUnits' own ``si.ini`` - which has no ``[Units]``. Pin the one dimension
	this test asserts, so it does not depend on the import order.
	"""
	import WeatherUnits as wu
	monkeypatch.setattr(type(wu.config), 'localUnits', property(lambda self: {'length': PREFERRED}))


@pytest.fixture
def real_value_sources():
	"""The Studio's value-source stand-in is process-global and its tests leave it
	installed. Restore the real dispatcher lookup here, and put back whatever was
	there so the Studio's own tests are unaffected by the order they run in."""
	saved = valuesource._standIn
	installStandIn(None)
	try:
		yield
	finally:
		installStandIn(saved)


def _publish(mock, km: float = 313.0) -> None:
	"""Push a fixed reading through the plugin's real schema, like its own publish()."""
	realtime = {'time': datetime.now().replace(microsecond=0).strftime(_TIME_FORMAT)}
	realtime[mock._sourceKeys[KEY]] = km
	realtime[mock._sourceKeys[GAUGE_KEY]] = 65.0
	datagram = LevityDatagram(realtime, schema=mock.schema, dataMap=mock.schema.dataMaps['realtime'], static=False)
	mock.realtime.update(datagram)


def _gauge(dashboard):
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '30%', 'height': '30%'})
	sandbox.state = {'items': [{
		'type': 'realtime.gauge', 'name': 'ev', 'key': GAUGE_KEY,
		'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'},
		'display': {'range': {'min': 0, 'max': 100}, 'sub-label': {'value': KEY, 'format': {'precision': 0}}},
	}]}
	dashboard.app.processEvents()
	panel = next(c for c in sandbox.childPanels if isinstance(c, Realtime))
	return sandbox, panel.display


def _caption_text(dashboard, gauge) -> str:
	dashboard.wait_until(lambda: gauge._subItem is not None and gauge._subItem._hasValue,
	                     message='the caption receives the range value')
	return gauge._subItem._text


def test_ev_caption_prints_the_preferred_length_unit(dashboard, real_value_sources, pinned_length_unit):
	mock = LevityDashboard.plugins.get('Mock')
	assert mock is not None, 'the Mock plugin supplies the showcase keys'
	_publish(mock)
	sandbox, gauge = _gauge(dashboard)
	try:
		text = _caption_text(dashboard, gauge)
		assert text.endswith(f' {PREFERRED}'), f'the caption must print the preferred unit, got {text!r}'
		assert text == '194 mi', f'a 313 km reading in miles at precision 0 is 194 mi, got {text!r}'
	finally:
		sandbox.scene().removeItem(sandbox)


def test_ev_caption_does_not_change_unit_between_paints(dashboard, real_value_sources, pinned_length_unit):
	"""Two reads of the same key must agree - the flip was per-read, not per-value."""
	mock = LevityDashboard.plugins.get('Mock')
	_publish(mock, km=313.0)
	sandbox, gauge = _gauge(dashboard)
	try:
		first = _caption_text(dashboard, gauge)
		# A second publish of the same value must not move the unit word.
		_publish(mock, km=313.0)
		dashboard.wait_until(lambda: gauge._subItem._hasValue, message='the caption keeps its value')
		dashboard.app.processEvents()
		assert gauge._subItem._text == first, f'the unit word flipped: {first!r} then {gauge._subItem._text!r}'
	finally:
		sandbox.scene().removeItem(sandbox)
