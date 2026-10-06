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
