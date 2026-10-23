from LevityDash.lib.variables import resolveVariables, substitute

VARS = {'hot': '90°F', 'temp': 'environment.temperature.temperature', 'gap': 3, 'room': 'bedroom'}


def test_a_whole_value_keeps_its_type():
	assert substitute('$gap', VARS) == 3
	assert substitute('${gap}', VARS) == 3
	assert substitute({'padding': '$gap'}, VARS) == {'padding': 3}


def test_inside_text_it_is_spliced():
	assert substitute('$temp > $hot', VARS) == 'environment.temperature.temperature > 90°F'
	assert substitute('indoor.temperature.temperature#${room}-1', VARS) == 'indoor.temperature.temperature#bedroom-1'


def test_unknown_names_are_left_for_the_theme():
	assert substitute('$accent', VARS) == '$accent'
	assert substitute({'color': '$series-1'}, VARS) == {'color': '$series-1'}


def test_a_variable_may_use_an_earlier_one():
	state = {'vars': {'a': 5, 'b': '$a + 1'}, 'items': [{'when': '$b'}]}
	assert resolveVariables(state)['items'] == [{'when': '5 + 1'}]


def test_vars_stay_and_the_rest_is_resolved():
	state = {'vars': {'gap': 3}, 'items': [{'type': 'stack', 'padding': '$gap', 'items': [{'spacing': '$gap'}]}]}
	out = resolveVariables(state)
	assert out['vars'] == {'gap': 3}
	assert out['items'][0]['items'][0]['spacing'] == 3
	assert state['items'][0]['padding'] == '$gap', 'the input is not changed'


def test_a_root_list_or_a_file_without_vars_is_untouched():
	assert resolveVariables([{'a': '$x'}]) == [{'a': '$x'}]
	state = {'items': [{'a': '$x'}]}
	assert resolveVariables(state) is state


def test_bad_vars_do_not_raise():
	state = {'vars': ['not', 'a', 'map'], 'items': [{'a': '$x'}]}
	assert resolveVariables(state) is state
	assert resolveVariables({'vars': {'1bad': 1, 'ok': 2}, 'items': ['$ok']})['items'] == [2]


# section saving

from LevityDash.lib.variables import retemplate

TEMPLATE = {
	'vars': {'gap': 3, 'hot': '90°F'},
	'items': [
		{'name': 'a', 'padding': '$gap', 'when': 'x > $hot', 'geometry': {'width': '50%'}},
		{'name': 'b', 'padding': '$gap'},
	],
}
RESOLVED = resolveVariables(TEMPLATE)


def live(**changes):
	"""What the app saves for the file above, with `changes` applied to item a."""
	import copy
	state = copy.deepcopy(RESOLVED)
	state['items'][0].update(changes)
	return state


def test_an_untouched_save_writes_the_names_back():
	assert retemplate(live(), RESOLVED, TEMPLATE) == TEMPLATE


def test_an_edited_field_is_written_as_the_new_value_and_the_rest_keeps_its_name():
	saved = retemplate(live(padding=5), RESOLVED, TEMPLATE)
	assert saved['items'][0]['padding'] == 5
	assert saved['items'][0]['when'] == 'x > $hot'
	assert saved['items'][1]['padding'] == '$gap'


def test_a_nested_edit_keeps_the_names_beside_it():
	saved = retemplate(live(geometry={'width': '60%'}), RESOLVED, TEMPLATE)
	assert saved['items'][0]['geometry'] == {'width': '60%'}
	assert saved['items'][0]['padding'] == '$gap'


def test_reordered_named_items_still_line_up():
	state = live()
	state['items'].reverse()
	saved = retemplate(state, RESOLVED, TEMPLATE)
	assert [item['name'] for item in saved['items']] == ['b', 'a']
	assert all(item['padding'] == '$gap' for item in saved['items'])


def test_a_new_item_is_written_as_it_is_and_the_others_keep_their_names():
	state = live()
	state['items'].append({'name': 'c', 'padding': 3})
	saved = retemplate(state, RESOLVED, TEMPLATE)
	assert saved['items'][2] == {'name': 'c', 'padding': 3}
	assert saved['items'][0]['padding'] == '$gap'


def test_a_degree_sign_added_by_the_app_is_not_an_edit():
	template = {'range': {'min': '$lo'}}
	assert retemplate({'range': {'min': '30°'}}, {'range': {'min': 30}}, template) == template
	assert retemplate({'range': {'min': '31°'}}, {'range': {'min': 30}}, template) == {'range': {'min': '31°'}}


def test_shared_variables_apply_to_a_file_with_no_vars():
	state = {'items': [{'key': '$upstairs', 'padding': '$gap'}]}
	out = resolveVariables(state, {'upstairs': 'avg(a, where=home.upstairs)', 'gap': 3})
	assert out['items'] == [{'key': 'avg(a, where=home.upstairs)', 'padding': 3}]


def test_the_files_own_vars_win_over_shared_ones():
	state = {'vars': {'gap': 5}, 'items': [{'padding': '$gap', 'spacing': '$other'}]}
	out = resolveVariables(state, {'gap': 3, 'other': 1})
	assert out['items'] == [{'padding': 5, 'spacing': 1}]


def test_a_file_variable_may_use_a_shared_one():
	state = {'vars': {'wide': '$gap * 2'}, 'items': [{'x': '$wide'}]}
	assert resolveVariables(state, {'gap': 3})['items'] == [{'x': '3 * 2'}]


def test_vars_yaml_beside_config(tmp_path):
	from LevityDash.lib.variables import loadSharedVariables
	assert loadSharedVariables(tmp_path) == {}
	(tmp_path / 'vars.yaml').write_text('upstairs: avg(a, where=home.upstairs)\nfloor: $upstairs\n')
	assert loadSharedVariables(tmp_path) == {'upstairs': 'avg(a, where=home.upstairs)', 'floor': 'avg(a, where=home.upstairs)'}
	(tmp_path / 'vars.yaml').write_text('vars:\n  gap: 3\n')
	assert loadSharedVariables(tmp_path / 'vars.yaml') == {'gap': 3}
	(tmp_path / 'vars.yaml').write_text(': : bad')
	assert loadSharedVariables(tmp_path) == {}


def test_a_variable_in_a_mapping_key_is_replaced():
	assert substitute({'$temp': {'plot': 1}, 'plain': 2}, {'temp': 'environment.temperature.temperature'}) == {
		'environment.temperature.temperature': {'plot': 1},
		'plain': 2,
	}


def test_a_key_that_is_not_a_variable_or_not_text_is_left_alone():
	assert substitute({'$accent': 1, '$n': 2}, {'n': 5}) == {'$accent': 1, '$n': 2}


def test_a_save_keeps_a_variable_used_as_a_mapping_key():
	template = {'vars': {'temp': 'environment.temperature.temperature', 'line': 'bar'}, 'items': [{'$temp': {'plot': '$line', 'size': 1}, 'plain': 2}]}
	resolved = resolveVariables(template)
	live = {'vars': template['vars'], 'items': [{'environment.temperature.temperature': {'plot': 'bar', 'size': 3}, 'plain': 2}]}
	assert retemplate(live, resolved, template)['items'] == [{'$temp': {'plot': '$line', 'size': 3}, 'plain': 2}]


def test_vars_yaml_through_the_config_path_type(tmp_path):
	# The loader hands over `userConfig.userPath`, an EasyPath, not a Path.
	from LevityDash.lib.EasyPath import EasyPath
	from LevityDash.lib.variables import loadSharedVariables
	(tmp_path / 'vars.yaml').write_text('gap: 3\n')
	assert loadSharedVariables(EasyPath(tmp_path)) == {'gap': 3}
	assert loadSharedVariables(EasyPath(tmp_path / 'vars.yaml')) == {'gap': 3}


def test_a_themes_sizes_are_variables_that_a_file_can_override():
	from LevityDash.lib.ui.colors import theme
	sizes = theme.load('default').sizes()
	state = {'vars': {'space_3': '9mm'}, 'items': [{'type': 'stack', 'spacing': '$space_3', 'padding': '$space_5', 'size': '$type_head'}]}
	item = resolveVariables(state, sizes)['items'][0]
	assert item == {'type': 'stack', 'spacing': '9mm', 'padding': '8mm', 'size': '160%'}
