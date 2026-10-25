"""`preset: table`: labels once, units once, one cell per row and column."""
import pytest

from LevityDash.lib import presets

COLUMNS = [
	{'head': 'Temp', 'unit': '°F', 'key': 'indoor.temperature.temperature#{row}', 'precision': 1},
	{'head': 'Humidity', 'unit': '%', 'key': 'indoor.humidity.humidity#{row}'},
]
ROWS = [{'label': 'Bedroom', 'row': 'bedroom'}, {'label': 'Office', 'row': 'office'}]


def table(**props):
	return {'preset': 'table', 'props': {'columns': COLUMNS, 'rows': ROWS, **props}}


def texts(item):
	return [i for i in item['items'] if i['type'] == 'text']


def cells(item):
	return [i for i in item['items'] if i['type'] == 'realtime.text']


def test_the_table_is_a_preset_and_expands_to_a_grid():
	assert 'table' in presets.available()
	item = presets.expand({'items': [table()]})['items'][0]
	assert item['type'] == 'grid'
	assert item['grid']['columns'] == ['1.2fr', '1fr', '1fr']
	assert item['grid']['rows'] == ['1fr', '1fr', '1fr']


def test_labels_and_units_are_written_once():
	item = presets.expand({'items': [table()]})['items'][0]
	assert [t['text'] for t in texts(item)] == ['Temp °F', 'Humidity %', 'Bedroom', 'Office']
	assert len(cells(item)) == 4
	assert all(c['display']['unitPosition'] == 'Hidden' and 'title' in c and c['title'] is False for c in cells(item))


def test_each_cell_has_its_own_key_and_place():
	item = presets.expand({'items': [table()]})['items'][0]
	got = {(c['grid']['row'], c['grid']['column']): c['key'] for c in cells(item)}
	assert got[(2, 2)] == 'indoor.temperature.temperature#bedroom'
	assert got[(3, 3)] == 'indoor.humidity.humidity#office'


def test_numbers_align_on_the_point_and_share_dashboard_wide_groups():
	item = presets.expand({'items': [table()]})['items'][0]
	label = cells(item)[0]['display']['valueLabel']
	assert label['number-align'] == 'decimal'
	assert label['matchingGroup'] == {'group': 'global.value', 'matchAll': True}
	assert all(t['matchingGroup'] == {'group': 'global.title', 'matchAll': True} for t in texts(item))


def test_text_height_sizes_heads_labels_and_numbers_alike():
	item = presets.expand({'items': [table(textHeight='4.5mm')]})['items'][0]
	assert all(t['text-height'] == '4.5mm' for t in texts(item))
	assert all(c['display']['valueLabel']['text-height'] == '4.5mm' for c in cells(item))
	plain = presets.expand({'items': [table()]})['items'][0]
	assert not any('text-height' in t for t in texts(plain))


def test_gutter_is_the_column_gap():
	item = presets.expand({'items': [table(gutter='10mm', rowGap='1mm')]})['items'][0]
	assert item['grid']['gap'] == ['1mm', '10mm']


def test_a_row_can_give_its_own_keys_and_skip_a_cell():
	rows = [{'label': 'Outside', 'keys': ['environment.temperature.temperature', None]}]
	item = presets.expand({'items': [table(rows=rows)]})['items'][0]
	assert [c['key'] for c in cells(item)] == ['environment.temperature.temperature']


@pytest.mark.parametrize('props, words', [
	({'columns': []}, 'columns'),
	({'rows': []}, 'rows'),
	({'columns': [{'head': 'x', 'nope': 1}]}, 'nope'),
	({'rows': [{'label': 'x'}]}, 'row'),  # a {row} key with no row name
	({'rows': [{'label': 'x', 'keys': ['a']}]}, 'keys'),
	({'alignment': 'Top'}, 'alignment'),
])
def test_a_wrong_table_is_an_error_tile_that_says_why(props, words):
	item = presets.expand({'items': [table(**props)]})['items'][0]
	assert item['type'] == presets.FAILED
	assert words in item['message']


def test_a_table_can_hold_a_preset_name_and_extra_fields():
	node = table()
	node['geometry'] = {'x': '0%', 'y': '0%', 'width': '50%', 'height': '50%'}
	item = presets.expand({'items': [node]})['items'][0]
	assert item['geometry']['width'] == '50%'
