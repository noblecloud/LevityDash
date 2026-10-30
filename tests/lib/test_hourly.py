"""`hourly-row`: columns of readings placed under the matching time of a graph."""
import pytest

from LevityDash.lib import hourly, presets

FRAME = {'days': 1, 'hours': 12}
ROW = {'key': 'at(environment.temperature.temperature, {offset})', 'precision': 0}


def _props(**kwargs):
	return {name: default for name, (default, _) in hourly.PROPS.items()} | {'rows': [ROW]} | kwargs


def test_columns_are_equal_and_centred_on_their_time():
	columns = hourly.columnTimes(FRAME, 3)
	assert [t for t, _, _ in columns] == [0, 3, 6, 9, 12, 15, 18, 21, 24, 27]
	assert all(w == pytest.approx(3 / 36 * 100, abs=1e-3) for _, _, w in columns)
	for t, left, width in columns:
		assert left + width / 2 == pytest.approx((t + 6) / 36 * 100, abs=1e-3)   # the default offset is -6h


def test_past_adds_the_columns_before_now_that_fit():
	times = [t for t, _, _ in hourly.columnTimes(FRAME, 3, past=True)]
	assert times[0] == -3 and 0 in times


def test_a_step_that_fits_nothing_is_refused():
	with pytest.raises(ValueError, match='no column fits'):
		hourly.build(_props(step=40))
	with pytest.raises(ValueError, match='step'):
		hourly.build(_props(step='soon'))


@pytest.mark.parametrize('change, message', [
	({'rows': []}, 'needs rows'),
	({'rows': [{'key': 'a.b', 'colour': 'red'}]}, 'no setting colour'),
	({'rows': [{'precision': 0}]}, 'no key'),
	({'head': 'bold'}, 'clock, relative or none'),
	({'numberAlign': 'left'}, 'decimal, end or none'),
])
def test_a_bad_row_says_what_is_wrong(change, message):
	with pytest.raises(ValueError, match=message):
		hourly.build(_props(**change))


def test_each_column_reads_its_own_moment():
	group = hourly.build(_props(step=6, graph='temps'))
	assert group['type'] == 'group'
	columns = group['items']
	keys = [[i['key'] for i in c['items'] if i['type'] == 'realtime.text'][0] for c in columns[:3]]
	assert keys == [f'at(environment.temperature.temperature, {h}h)' for h in ('0', '6', '12')]
	assert columns[1]['time-axis'] == {'graph': 'temps', 'at': '6h'}
	assert columns[0]['items'][0]['text'] == 'Now'
	assert columns[1]['items'][0]['items'][0]['offset'] == '6h'
	# every number and every head is in a dashboard-wide size group
	assert columns[1]['items'][1]['display']['valueLabel']['matchingGroup'] == {'group': 'global.value', 'matchAll': True}


def test_no_graph_means_no_time_axis():
	assert all('time-axis' not in c for c in hourly.build(_props())['items'])


def test_the_preset_is_registered_and_expands():
	item = presets.expand([{'preset': 'hourly-row', 'props': {'rows': [ROW], 'graph': 'g'}}])[0]
	assert item['type'] == 'group' and item['items']
	assert presets.expand([{'preset': 'hourly-row', 'props': {'rows': []}}])[0]['type'] == presets.FAILED


@pytest.mark.parametrize('text, hours', [(3, 3.0), ('3h', 3.0), ('-90min', -1.5), ('1d', 24.0), ({'days': 1, 'hours': 12}, 36.0)])
def test_spans_read_several_ways(text, hours):
	assert hourly.spanHours(text, 'x') == hours
