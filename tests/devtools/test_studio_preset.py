"""The Studio builder's preset model: expand a template, store only the diff, keep the tree and the properties in step."""
import pytest
import yaml

from LevityDash.devtools import _studio_preset as m
from LevityDash.lib import presets as lib

DIAL = {
	'props': {
		'key': 'environment.temperature.temperature',
		'accent': '$orange',
		'lo': {'default': 30, 'type': 'number', 'min': 0, 'max': 200},
		'hi': {'default': 110, 'type': 'number'},
	},
	'template': {
		'type': 'group',
		'items': [
			{'type': 'realtime.gauge', 'key': '$key', 'display': {'arc': {'gradient': '$accent'}, 'range': {'min': '$lo', 'max': '$hi'}}},
			{'type': 'text', 'text': 'High ${hi}'},
		],
	},
}


@pytest.fixture
def dial():
	return m.Piece.fromText('temp-dial', yaml.safe_dump(DIAL))


def test_expand_substitutes_typed_values_and_text(dial):
	out = dial.expanded({'hi': 100})
	gauge, label = out['items']
	assert gauge['key'] == 'environment.temperature.temperature'
	assert gauge['display']['range'] == {'min': 30, 'max': 100}, 'a whole $name keeps the value\'s type'
	assert label['text'] == 'High 100', '${name} inside text is interpolated'
	assert gauge['display']['arc']['gradient'] == '$orange', 'a default that is a theme token passes through for the theme to resolve'
	assert out == lib.parse('temp-dial', yaml.safe_dump(DIAL)).instance({'hi': 100}), 'the builder expands with the library, not its own copy'


def test_undeclared_tokens_are_left_alone(dial):
	dial.template['items'][1]['text'] = '$muted'
	assert dial.expanded()['items'][1]['text'] == '$muted'


def test_instance_stores_only_the_difference(dial):
	assert dial.instance() == {'preset': 'temp-dial'}
	assert dial.instance({'hi': 100, 'lo': 30}) == {'preset': 'temp-dial', 'props': {'hi': 100}}
	got = dial.instance({'hi': 100}, {'geometry': {'x': '10%'}})
	assert got == {'preset': 'temp-dial', 'props': {'hi': 100}, 'geometry': {'x': '10%'}}


def test_instance_drops_fields_the_preset_already_has(dial):
	same = dial.expanded()
	assert dial.instance({}, {'type': 'group', 'items': same['items']}) == {'preset': 'temp-dial'}


def test_an_instance_expands_the_same_through_the_library(dial):
	instance = dial.instance({'hi': 90}, {'geometry': {'x': '10%'}})
	out = lib.Preset.instance(dial.toPreset(), instance.get('props'), {k: v for k, v in instance.items() if k not in ('preset', 'props')})
	assert out['geometry'] == {'x': '10%'}
	assert out['items'][0]['display']['range']['max'] == 90


def test_untyped_and_listed_properties_keep_their_shape():
	piece = m.Piece.fromText('zones', yaml.safe_dump({'props': {'zones': {'default': [], 'doc': 'bands'}}, 'template': {'type': 'realtime.gauge'}}))
	assert piece.props['zones'].type == 'any' and piece.props['zones'].kind() == 'any'
	assert piece.asData()['props']['zones'] == {'default': [], 'doc': 'bands'}
	assert m.inferType(5) == 'number' and m.inferType('#fff') == 'color' and m.inferType('4mm') == 'size' and m.inferType([1]) == 'any'


def test_a_file_the_library_refuses_is_refused():
	with pytest.raises(lib.PresetError):
		m.Piece.fromText('bad', 'props: {a: 1}\n')


def test_problems_name_unknown_and_failed_values(dial):
	assert dial.problems({'hi': 100}) == []
	[unknown] = dial.problems({'nope': 1})
	assert 'no property nope' in unknown
	[high] = dial.problems({'lo': 500})
	assert "'lo'" in high and 'outside 0 to 200' in high
	[wrong] = dial.problems({'lo': 'x'})
	assert "'lo' is number" in wrong


def test_props_round_trip_in_their_shortest_form(dial):
	data = dial.asData()
	assert data['props']['key'] == 'environment.temperature.temperature'
	assert data['props']['accent'] == '$orange', 'an untyped property with nothing else writes bare'
	assert data['props']['hi'] == {'default': 110, 'type': 'number'}
	assert data['props']['lo'] == {'default': 30, 'type': 'number', 'min': 0, 'max': 200}
	again = m.Piece.fromText('temp-dial', yaml.safe_dump(data))
	assert again.asData() == data
	assert lib.parse('temp-dial', yaml.safe_dump(data)).props.keys() == dial.toPreset().props.keys(), 'the library reads what the builder writes'


def test_rename_updates_every_reference(dial):
	dial.rename('hi', 'ceiling')
	assert 'hi' not in dial.props and 'ceiling' in dial.props
	assert dial.template['items'][0]['display']['range']['max'] == '$ceiling'
	assert dial.template['items'][1]['text'] == 'High ${ceiling}'


def test_drop_bakes_the_default_into_the_template(dial):
	dial.drop('lo')
	assert dial.template['items'][0]['display']['range']['min'] == 30


def test_tree_edits(dial):
	path = dial.add((), {'type': 'clock'})
	assert path == (2,)
	assert dial.duplicate(path) == (3,)
	assert dial.move((3,), -2) == (1,)
	assert [n['type'] for n in dial.template['items']] == ['realtime.gauge', 'clock', 'text', 'clock']
	dial.remove((1,))
	assert [n['type'] for n in dial.template['items']] == ['realtime.gauge', 'text', 'clock']
	assert dial.node((0,))['type'] == 'realtime.gauge' and dial.node((9,)) is None


def test_set_field_makes_and_clears_nested_mappings():
	node = {}
	m.setField(node, 'geometry.x', '5%')
	m.setField(node, 'display.range.min', 0)
	assert node == {'geometry': {'x': '5%'}, 'display': {'range': {'min': 0}}}
	m.setField(node, 'display.range.min', None)
	assert node == {'geometry': {'x': '5%'}}, 'a mapping a removal empties goes with it'
	assert m.getField(node, 'geometry.x') == '5%' and m.getField(node, 'geometry.y', 'none') == 'none'


def test_unique_name():
	piece = m.Piece(props={'size': m.PropSpec('size')})
	assert piece.uniqueName('size') == 'size-2'
	assert piece.uniqueName('a b') == 'a-b'
