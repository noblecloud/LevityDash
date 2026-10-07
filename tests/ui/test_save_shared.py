"""A board with a `shared:` default or a graph's time indicator can be saved: neither aborts the dump."""
import yaml
from PySide6.QtTest import QTest

from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.CentralPanel import StatefulDumper

BOX = {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'}


def _dump(dashboard, items):
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '40%', 'height': '40%'})
	sandbox.state = {'items': items}
	for _ in range(5):
		QTest.qWait(20)
		dashboard.app.processEvents()
	return yaml.dump(sandbox.state, Dumper=StatefulDumper, default_flow_style=False)


def test_a_shared_enum_written_as_text_does_not_abort_the_save(dashboard):
	"""`shared: display: unitPosition: Hidden` is text; the live value is an enum, so the two could not be compared."""
	text = _dump(dashboard, [{
		'type': 'value-stack', 'name': 'row', 'geometry': BOX,
		'shared': {'display': {'unitPosition': 'Hidden'}},
		'items': [{'type': 'realtime.text', 'key': 'environment.temperature.temperature', 'title': {'text': 'T'}}],
	}])
	saved = yaml.safe_load(text)['items'][0]
	assert saved['shared'] == {'display': {'unitPosition': 'Hidden'}}


def test_a_graph_with_a_theme_coloured_indicator_saves(dashboard):
	"""The time indicator's state is one colour; the dumper had no way to write it."""
	text = _dump(dashboard, [{
		'type': 'graph', 'name': 'g', 'timeframe': {'days': 1}, 'geometry': BOX, 'indicator': {'color': '$text'},
		'figures': [{'figure': 'temperature', 'environment.temperature.temperature': {'plot': {'type': 'plot', 'color': '#ff0000'}}}],
	}])
	assert 'indicator' in text and '$text' in text

