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



def test_an_expression_key_and_a_precision_survive_the_save(dashboard):
	"""`max(a, b): {...}` shorthand reloads as a literal key, and `precision` was never written."""
	text = _dump(dashboard, [{
		'type': 'value-stack', 'name': 'row', 'geometry': BOX,
		'items': [{
			'type': 'realtime.text', 'key': 'max(environment.temperature.temperature, today)',
			'title': {'text': 'Peak'}, 'display': {'precision': 0},
		}],
	}])
	item = yaml.safe_load(text)['items'][0]['items'][0]
	assert item['key'] == 'max(environment.temperature.temperature, today)'
	assert item['display']['precision'] == 0


def test_a_clock_keeps_its_format_hint(dashboard):
	"""The gauge's hint override once replaced the getter every Label shares, so no clock ever reported its hint."""
	text = _dump(dashboard, [{
		'type': 'clock', 'name': 'c', 'geometry': BOX,
		'items': [{'format': '%-I:%M', 'format-hint': '10:00', 'geometry': BOX}],
	}])
	assert yaml.safe_load(text)['items'][0]['items'][0]['format-hint'] == '10:00'


def test_a_type_first_shorthand_item_loads_as_its_type(dashboard):
	"""A stack writes `{titled-group: {...}}`; the loader fell back to the stack's default item type and dropped the title."""
	from LevityDash.lib.ui.frontends.PySide.Modules.Containers.TitleContainer import TitledPanel
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '40%', 'height': '40%'})
	sandbox.state = {'items': [{
		'type': 'value-stack', 'name': 'row', 'geometry': BOX,
		'items': [{'titled-group': {'name': 'g', 'title': {'text': 'Aloft'}, 'items': []}}],
	}]}
	for _ in range(5):
		QTest.qWait(20)
		dashboard.app.processEvents()
	def below(item):
		for child in item.childItems():
			yield child
			yield from below(child)
	found = [i for i in below(sandbox) if isinstance(i, TitledPanel)]
	assert found, 'the shorthand item did not load as a titled-group'


def test_a_gauge_range_is_saved_at_full_precision(dashboard):
	"""7.07 was written as '7.1', which moved the sun arc's ends on reload."""
	text = _dump(dashboard, [{
		'type': 'realtime.gauge', 'key': 'astronomy.sun.remaining', 'geometry': BOX,
		'display': {'range': {'min': 7.07, 'max': 18.68}},
	}])
	saved = yaml.safe_load(text)['items'][0]['display']['range']
	assert (saved['min'], saved['max']) == (7.07, 18.68)


def test_a_group_saves_its_items_in_stacking_order(dashboard):
	"""Sorted by position, a later item that overlaps an earlier one changed layers on reload."""
	text = _dump(dashboard, [{
		'type': 'group', 'name': 'layers', 'geometry': BOX,
		'items': [
			{'type': 'group', 'name': 'under', 'geometry': {'x': '40%', 'y': '40%', 'width': '50%', 'height': '50%'}},
			{'type': 'group', 'name': 'over', 'geometry': {'x': '0%', 'y': '0%', 'width': '60%', 'height': '60%'}},
		],
	}])
	names = [i['name'] for i in yaml.safe_load(text)['items'][0]['items']]
	assert names == ['under', 'over']


GRAPH = {
	'type': 'graph', 'name': 'g', 'timeframe': {'days': 1}, 'geometry': BOX,
	'annotations': {'hourLabels': {'alignment': 'BottomCenter'}, 'dayLabels': {'enabled': False}},
	'figures': [{'figure': 'temperature', 'environment.temperature.temperature': {'plot': {'type': 'plot', 'color': '#ff0000'}}}],
}


def test_a_graph_does_not_save_what_its_own_layout_derived(dashboard):
	"""The hour labels move the margins to fit and the graph hands the indicator a colour; neither was written."""
	text = _dump(dashboard, [GRAPH])
	saved = yaml.safe_load(text)['items'][0]
	assert 'indicator' not in saved
	assert 'margins' not in saved


def test_a_graph_keeps_the_margins_the_config_wrote(dashboard):
	text = _dump(dashboard, [{**GRAPH, 'margins': {'top': '8%', 'bottom': '20%'}}])
	saved = yaml.safe_load(text)['items'][0]
	assert saved['margins'] == {'top': '8%', 'bottom': '20%'}


def test_a_gauge_saves_a_plain_interval_and_no_derived_unit_text(dashboard):
	"""`interval: 1` came back as '1', and the unit label's text, which follows the data, was written too."""
	text = _dump(dashboard, [{
		'type': 'realtime.gauge', 'key': 'astronomy.sun.remaining', 'geometry': BOX,
		'display': {'range': {'min': 7, 'max': 19}, 'major': {'interval': 1, 'length': '2%'}},
	}])
	saved = yaml.safe_load(text)['items'][0]
	assert saved['display']['major']['interval'] == 1
	assert 'text' not in saved.get('unit-label', {})
