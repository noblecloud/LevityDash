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
