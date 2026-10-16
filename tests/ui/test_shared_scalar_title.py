"""A bare `title: X` on an item must keep the `shared: title:` mapping that the same key carries.

The item's string replaces the whole mapping, so the shared `matchingGroup` was dropped and the title sized
to its own box. `_scalarsOverShared` decodes the string the way the key's own decoder does, so the shared
mapping merges with it, the same as `title: {text: X}`.
"""
from LevityDash.lib.ui.frontends.PySide.Modules.Containers.Stacks import _scalarsOverShared
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime import Realtime


def test_bare_title_decodes_to_text_so_shared_group_merges():
	shared = {'title': {'matchingGroup': {'group': 'stripTitle@strip', 'matchAll': True}}}
	state = _scalarsOverShared({'key': 'environment.temperature.dewpoint', 'title': 'Dewpoint'}, shared, Realtime)
	assert state['title'] == {'text': 'Dewpoint'}


def test_a_scalar_with_no_shared_mapping_is_left_alone():
	state = _scalarsOverShared({'title': 'Dewpoint'}, {}, Realtime)
	assert state['title'] == 'Dewpoint'


def test_a_mapping_item_value_is_left_alone():
	item_title = {'text': 'Dewpoint'}
	shared = {'title': {'matchingGroup': 'g'}}
	assert _scalarsOverShared({'title': item_title}, shared, Realtime)['title'] is item_title
