import pytest

from LevityDash.lib import presets
from LevityDash.lib.variables import _definitions, resolveVariables, retemplate

DIAL = '''
doc: A dial
props:
  key: {default: environment.temperature.temperature, type: key}
  hi: {default: 100, type: number, min: 0, max: 200}
  accent: $orange
  label: Temp
  top: $hi
template:
  type: group
  items:
    - {type: realtime.gauge, key: $key, display: {range: {max: $hi}, color: $accent}}
    - {type: text, text: $label, when: $key > $top}
'''
OUTER = '''
props: {key: x}
template:
  type: group
  items:
    - {preset: dial, props: {key: $key, hi: 50}}
'''
LOOP = 'template: {type: group, items: [{preset: loop}]}'
SPARK = '''
props:
  key: environment.pressure.pressure
  key2: {default: null, type: key}
  color: {default: null, type: color}
  min: {default: null, type: number}
template:
  type: mini-graph
  min: $min
  style: {color: $color, weight: 1}
  figures:
    - figure: p
      $key: {plot: one}
      $key2: {plot: two}
'''


@pytest.fixture(autouse=True)
def library(tmp_path):
	for name, text in {'dial': DIAL, 'outer': OUTER, 'loop': LOOP, 'spark': SPARK}.items():
		(tmp_path / f'{name}.yaml').write_text(text)
	presets.add_search_path(lambda: [tmp_path])
	yield tmp_path
	presets._search.clear()
	presets.clear_cache()


def test_defaults_fill_every_property_and_a_default_may_use_an_earlier_one():
	item = presets.expand([{'preset': 'dial', 'name': 'a'}])[0]
	assert item['name'] == 'a' and item['type'] == 'group'
	gauge, label = item['items']
	assert gauge['key'] == 'environment.temperature.temperature'
	assert gauge['display'] == {'range': {'max': 100}, 'color': '$orange'}, 'a whole $prop keeps its type; an unknown $name is left for the theme'
	assert label == {'type': 'text', 'text': 'Temp', 'when': 'environment.temperature.temperature > 100'}


def test_props_override_and_fields_merge_over_the_template():
	use = {'preset': 'dial', 'props': {'hi': 80, 'accent': '$blue'}, 'geometry': {'x': 0}, 'items': [{'type': 'text'}]}
	item = presets.expand([use])[0]
	assert item['items'] == [{'type': 'text'}], 'lists replace'
	assert item['geometry'] == {'x': 0}
	use = {'preset': 'dial', 'props': {'hi': 80, 'accent': '$blue'}, 'type': 'titled-group'}
	item = presets.expand([use])[0]
	assert item['type'] == 'titled-group'
	assert item['items'][0]['display'] == {'range': {'max': 80}, 'color': '$blue'}


def test_the_input_is_not_changed_and_vars_stay_untouched():
	state = {'vars': {'a': 1}, 'items': [{'preset': 'dial', 'props': {'hi': '$a'}}]}
	out = presets.expand(state)
	assert state['items'][0]['preset'] == 'dial'
	assert out['vars'] == {'a': 1}
	assert resolveVariables(out)['items'][0]['items'][0]['display']['range']['max'] == 1, 'vars still resolve after expansion'


@pytest.mark.parametrize('use, words', [
	({'preset': 'dial', 'props': {'nope': 1}}, 'no property nope'),
	({'preset': 'dial', 'props': {'hi': 'high'}}, 'is number'),
	({'preset': 'dial', 'props': {'hi': 500}}, 'outside'),
	({'preset': 'dial', 'props': 3}, 'mapping'),
	({'preset': 'loop'}, 'loop'),
])
def test_a_bad_use_becomes_a_failed_node_and_the_rest_loads(use, words):
	out = presets.expand([{'preset': 'dial', 'name': 'fine'}, {**use, 'name': 'bad', 'geometry': {'x': 1}}])
	assert out[0]['type'] == 'group'
	assert out[1]['type'] == presets.FAILED
	assert words in out[1]['message']
	assert out[1]['name'] == 'bad' and out[1]['geometry'] == {'x': 1}


def test_a_name_that_is_not_a_preset_file_is_left_alone():
	state = [{'type': 'stack', 'preset': 'value-stack'}, {'type': 'stack', 'preset': {'title': {'height': 1}}}]
	assert presets.expand(state) == state


def test_a_preset_may_use_another_with_its_own_props():
	item = presets.expand([{'preset': 'outer', 'props': {'key': 'wind'}}])[0]
	inner = item['items'][0]
	assert inner['items'][0]['key'] == 'wind'
	assert inner['items'][0]['display']['range']['max'] == 50


def test_a_preset_file_that_is_wrong_is_an_error(library):
	(library / 'broken.yaml').write_text('props: {a: {default: 1, speed: 2}}\ntemplate: {type: group}')
	out = presets.expand([{'preset': 'broken'}])[0]
	assert out['type'] == presets.FAILED and 'unknown settings' in out['message']


# Saving: the live tree is what the app dumps. `loaded` is the same dump taken right after loading.

def _roundtrip(written, live_edit=None, variables=None):
	state = [written]
	resolved = resolveVariables({'vars': variables or {}, 'items': presets.expand(state)})['items'] if variables else presets.expand(state)
	loaded = [dict(resolved[0], normalised=1)]  # the app adds keys on a dump
	live = [dict(loaded[0])]
	if live_edit:
		live_edit(live[0])
	vars_ = _definitions(variables) if variables else {}
	return retemplate(live, loaded, state, lambda item, wrote, base: presets.collapse(item, wrote, base, vars_))[0]


def test_an_unchanged_use_saves_as_written():
	written = {'preset': 'dial', 'name': 'a', 'props': {'hi': 80}, 'geometry': {'x': 1}}
	assert _roundtrip(written) == written


def test_a_changed_field_saves_alone_beside_preset_and_props():
	written = {'preset': 'dial', 'name': 'a', 'props': {'hi': 80}}

	def edit(item):
		item['name'] = 'renamed'
		item['geometry'] = {'x': 5}
		item['items'] = [dict(item['items'][0], key='other'), item['items'][1]]

	out = _roundtrip(written, edit)
	assert out['preset'] == 'dial' and out['props'] == {'hi': 80}
	assert out['name'] == 'renamed' and out['geometry'] == {'x': 5}
	assert len(out['items']) == 2 and out['items'][0]['key'] == 'other', 'a changed list is written whole'
	assert set(out) == {'preset', 'props', 'name', 'geometry', 'items'}


def test_a_field_the_file_wrote_keeps_its_text_while_it_holds():
	written = {'preset': 'dial', 'name': 'a', 'display': {'color': '$mine'}, 'geometry': {'x': '$gap'}}
	out = _roundtrip(written, lambda item: item.update(name='b'), variables={'gap': 3})
	assert out == {'preset': 'dial', 'name': 'b', 'display': {'color': '$mine'}, 'geometry': {'x': '$gap'}}


def test_a_property_left_null_leaves_its_entry_out_and_a_set_one_puts_it_back():
	bare = presets.expand([{'preset': 'spark'}])[0]
	assert bare == {'type': 'mini-graph', 'style': {'weight': 1}, 'figures': [{'figure': 'p', 'environment.pressure.pressure': {'plot': 'one'}}]}, \
		'a null property drops its key, and a mapping it empties'
	set_ = presets.expand([{'preset': 'spark', 'props': {'min': 29.5, 'color': '$red', 'key2': 'a.b'}}])[0]
	assert set_['min'] == 29.5 and set_['style'] == {'color': '$red', 'weight': 1}
	assert set_['figures'][0]['a.b'] == {'plot': 'two'}, 'a property used as a key names the series'


def test_a_property_used_as_a_key_must_be_text(library):
	use = {'preset': 'spark', 'props': {'key': 5}}
	assert presets.expand([use])[0]['type'] == presets.FAILED


def test_an_item_keeps_its_children_for_last(library):
	use = {'preset': 'dial', 'name': 'a', 'geometry': {'x': 0}}
	assert list(presets.expand([use])[0])[-1] == 'items', 'an item takes its own geometry and settings before its children are built'
