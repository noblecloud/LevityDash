"""An item in the Studio builder can become a preset of its own, and the template still expands to the same thing."""
import pytest
import yaml

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
from LevityDash.devtools import _studio_builder as sb  # noqa: E402
from LevityDash.devtools import _studio_preset as m  # noqa: E402
from tests.devtools.test_studio_builder import StubEngine  # noqa: E402


@pytest.fixture
def builder(tmp_path, monkeypatch):
	monkeypatch.setenv('LEVITYDASH_STUDIO_DIR', str(tmp_path))
	win = sb.Builder(engine=StubEngine())
	win.timer.stop()
	yield win
	win.close()


def card(builder):
	builder.piece.props['unit_title'] = m.PropSpec('unit_title', 'text', 'Temp')
	builder.piece.template['items'] = [
		{'type': 'group', 'geometry': {'x': '10%', 'y': '10%', 'width': '40%', 'height': '40%'}, 'items': [
			{'type': 'text', 'text': '$unit_title'},
			{'type': 'realtime.text', 'key': 'environment.temperature.temperature'},
		]},
	]
	builder.rebuildAll()


def test_extract_leaves_a_use_and_writes_the_preset(builder, tmp_path):
	card(builder)
	before = builder.piece.expanded({'unit_title': 'Wind'})
	builder.select((0,))
	builder.extractPreset('temp-card')
	use = builder.piece.node((0,))
	assert use['preset'] == 'temp-card' and use['geometry']['width'] == '40%'
	assert use['props'] == {'unit_title': '$unit_title'}
	saved = yaml.safe_load((tmp_path / 'presets' / 'temp-card.yaml').read_text())
	assert 'geometry' not in saved['template'] and saved['props']['unit_title']['default'] == 'Temp'
	assert builder.piece.expanded({'unit_title': 'Wind'}) == before


def test_extract_keeps_placement_fields_on_the_use(builder):
	card(builder)
	builder.piece.node((0,))['flex'] = {'grow': 2}
	builder.select((0,))
	builder.extractPreset('placed')
	assert builder.piece.node((0,))['flex'] == {'grow': 2}


def test_extract_refuses_the_root_and_a_taken_name(builder):
	card(builder)
	builder.select(())
	builder.extractPreset('x')
	assert 'Pick an item' in builder.status.text()
	builder.select((0,))
	builder.extractPreset('hero-readings')  # shipped
	assert 'already a preset' in builder.status.text()
	assert builder.piece.node((0,)).get('type') == 'group'


def test_extract_is_undoable(builder):
	card(builder)
	builder.select((0,))
	builder.extractPreset('undo-me')
	builder.undo()
	assert builder.piece.node((0,)).get('type') == 'group'


def stack_with_groups(builder):
	builder.piece.template['items'] = [
		{'type': 'value-stack', 'name': 'row', 'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '30%'},
		 'shared': {'title': {'matchingGroup': {'group': 'rowTitle@temperature', 'matchAll': True}},
		            'display': {'valueLabel': {'matchingGroup': {'group': 'rowValue@temperature', 'matchAll': True}}}},
		 'items': [{'type': 'realtime.text', 'key': 'environment.temperature.temperature'}]},
	]
	builder.rebuildAll()


def test_a_size_group_scope_becomes_a_property(builder, tmp_path):
	stack_with_groups(builder)
	before = builder.piece.expanded()
	builder.select((0,))
	builder.extractPreset('row-preset')
	piece = m.Piece.fromText('row-preset', (tmp_path / 'presets' / 'row-preset.yaml').read_text())
	assert list(piece.props) == ['group'] and piece.props['group'].default == 'temperature'
	shared = piece.template['shared']
	assert shared['title']['matchingGroup']['group'] == 'rowTitle@$group'
	assert shared['display']['valueLabel']['matchingGroup']['group'] == 'rowValue@$group'
	assert builder.piece.node((0,)).get('props') is None, 'the default keeps the use as it was'
	assert builder.piece.expanded() == before


def test_a_second_scope_gets_its_own_property(builder):
	stack_with_groups(builder)
	builder.piece.template['items'][0]['shared']['display']['valueLabel']['matchingGroup']['group'] = 'rowValue@wind'
	piece = builder.piece.extract((0,), 'row-preset')
	assert {n: s.default for n, s in piece.props.items()} == {'group': 'temperature', 'group-2': 'wind'}
	assert 'rowValue@${group-2}' in str(piece.template)


def test_a_use_can_name_another_panel(builder):
	stack_with_groups(builder)
	piece = builder.piece.extract((0,), 'row-preset')
	other = piece.toPreset().instance({'group': 'wind'})
	assert other['shared']['title']['matchingGroup']['group'] == 'rowTitle@wind'
