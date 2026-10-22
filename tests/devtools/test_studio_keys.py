"""The Studio's key browser: what it lists, how it searches, what it says about an expression, and that it sets a key."""
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
from PySide6.QtCore import QMimeData, Qt  # noqa: E402

from LevityDash.devtools import _studio_builder as sb  # noqa: E402
from LevityDash.devtools import _studio_keys as keys  # noqa: E402
from LevityDash.devtools import _studio_keys_tab as tab  # noqa: E402
from LevityDash.lib.plugins.categories import CategoryItem  # noqa: E402
from tests.devtools.test_studio_dashboard import BOARDS, StubEngine  # noqa: E402


class FakeValue:
	unit_symbol = '°F'

	def __str__(self):
		return '68°'


def container(value=None, **metadata):
	return SimpleNamespace(now=SimpleNamespace(value=value), metadata=metadata)


def plugin(name, enabled, schema=None, places=None):
	return SimpleNamespace(name=name, enabled=enabled, schema=SimpleNamespace(flatDict=schema or {}), places=places or {})


def test_a_key_is_listed_once_with_every_source_and_computed_keys_are_left_out():
	bedroom = CategoryItem('indoor.temperature.temperature#bedroom')
	outdoor = CategoryItem('environment.temperature.temperature')
	table = {
		bedroom: {'Fixture': container(FakeValue(), title='Bedroom', sourceUnit='f')},
		outdoor: {'Fixture': container(FakeValue(), title='Outdoor'), 'OpenMeteo': container(None, title='Outdoor')},
		CategoryItem('computed.x1234'): {'Computed': container(FakeValue())},
	}
	found = {i.key: i for i in keys.collectKeys(SimpleNamespace(items=table.items), [plugin('Fixture', True, places={'bedroom': 'home.upstairs.bedroom'})])}
	assert set(found) == {'indoor.temperature.temperature#bedroom', 'environment.temperature.temperature'}
	assert found['environment.temperature.temperature'].sourceNames == ['Fixture', 'OpenMeteo']
	assert found['environment.temperature.temperature'].state == keys.LIVE
	room = found['indoor.temperature.temperature#bedroom']
	assert (room.place, room.identity, room.unit, room.value) == ('home.upstairs.bedroom', 'bedroom', '°F', '68°')


def test_schema_keys_of_a_plugin_that_is_off_are_listed_without_a_value():
	found = {i.key: i for i in keys.collectKeys(SimpleNamespace(items=dict().items), [plugin('WeatherFlow', False, {
		'environment.wind.speed.speed': {'title': 'Wind', 'sourceUnit': 'mi/hr'},
		'environment.condition.icon': {'title': 'Icon', 'type': 'icon', 'sourceUnit': 'str', 'shape': 'enum'},
		'timestamp': {'title': 'Time', 'sourceUnit': 'ISO8601'},
		'environment': {'timeseriesOnly': True},
	})])}
	assert set(found) == {'environment.wind.speed.speed', 'environment.condition.icon'}
	assert found['environment.wind.speed.speed'].state == keys.OFF
	assert found['environment.wind.speed.speed'].unit == 'mi/hr'
	assert found['environment.condition.icon'].shape == 'enum'


def _sample():
	table = {
		CategoryItem('indoor.temperature.temperature#bedroom'): {'Fixture': container(FakeValue(), title='Bedroom')},
		CategoryItem('indoor.humidity.humidity#office'): {'Fixture': container(None, title='Humidity')},
	}
	return keys.collectKeys(SimpleNamespace(items=table.items), [plugin('Fixture', True, places={'bedroom': 'home.upstairs.bedroom', 'office': 'home.upstairs.office'})])


def test_search_words_and_filters():
	rows = _sample()
	find = lambda text: [i.key for i in rows if keys.matches(i, text)]
	assert len(find('')) == 2
	assert find('humid') == ['indoor.humidity.humidity#office']
	assert len(find('place:home.upstairs')) == 2
	assert find('place:home.upstairs.bedroom') == ['indoor.temperature.temperature#bedroom']
	assert find('state:live') == ['indoor.temperature.temperature#bedroom']
	assert find('source:fix unit:°f') == ['indoor.temperature.temperature#bedroom']
	assert find('shape:enum') == []
	assert find('bedroom shape:number') == ['indoor.temperature.temperature#bedroom']


def test_an_expression_is_checked_against_the_keys_that_exist():
	rows = _sample()
	good = keys.checkExpression('indoor.temperature.temperature#bedroom - indoor.humidity.humidity#office', rows)
	assert good.ok and good.kind == 'an expression' and good.unknown == [] and good.waiting == ['indoor.humidity.humidity#office']
	missing = keys.checkExpression('avg(nothing.here.at_all, indoor.temperature.temperature#bedroom)', rows)
	assert missing.unknown == ['nothing.here.at_all']
	assert 'No loaded plugin has nothing.here.at_all' in keys.describe(missing)
	assert not keys.checkExpression('indoor.temperature.temperature#bedroom +', rows).ok
	assert keys.checkExpression('', rows).problem
	placed = keys.checkExpression('avg(indoor.temperature.temperature, where=home.upstairs)', rows)
	assert placed.ok and placed.places == ['home.upstairs']
	assert keys.checkExpression('at(indoor.temperature.temperature#bedroom, -3h)', rows).ok


@pytest.fixture
def builder(tmp_path, monkeypatch):
	monkeypatch.setenv('LEVITYDASH_STUDIO_DIR', str(tmp_path / 'studio'))
	target = tmp_path / 'station.levity'
	shutil.copy(BOARDS / 'station.levity', target)
	win = sb.Builder(target, engine=StubEngine(), dashboard=True)
	win.timer.stop()
	win.keysTab.timer.stop()
	win.keysTab.setInfos(_sample())
	yield win
	win.close()


def _firstKeyed(win):
	def walk(node, path):
		if isinstance(node, dict):
			if str(node.get('type')) in tab.KEYED and 'preset' not in node and isinstance(node.get('key'), str):
				return path
			for i, kid in enumerate(node.get('items') or []):
				if (found := walk(kid, path + (i,))) is not None:
					return found
	return walk(win.piece.node(()), ())


def test_the_tab_lists_filters_and_sets_the_key_of_the_selected_item(builder):
	win = builder
	box = win.keysTab
	assert box.tree.topLevelItemCount() == 2
	box.search.setText('humid')
	assert box.tree.topLevelItemCount() == 1
	box.search.setText('')
	path = _firstKeyed(win)
	assert path is not None
	win.select(path)
	assert box.keyed
	assert box.selectKey('indoor.temperature.temperature#bedroom')
	box.useRow(box.tree.currentItem())
	assert win.piece.node(path)['key'] == 'indoor.temperature.temperature#bedroom'
	win.undo()
	assert win.piece.node(path)['key'] != 'indoor.temperature.temperature#bedroom'


def test_a_key_dropped_on_an_item_sets_it_and_a_container_refuses(builder):
	win = builder
	path = _firstKeyed(win)
	win._keyDropped(path, 'indoor.humidity.humidity#office')
	assert win.piece.node(path)['key'] == 'indoor.humidity.humidity#office'
	win._keyDropped((), 'indoor.humidity.humidity#office')
	assert 'takes no key' in win.status.text()


def test_the_expression_box_reports_and_sets(builder):
	win = builder
	box = win.keysTab
	path = _firstKeyed(win)
	win.select(path)
	box.setValue('indoor.temperature.temperature#bedroom - nothing.here.at_all')
	assert 'No loaded plugin has nothing.here.at_all' in box.report.text()
	box.setValue('indoor.temperature.temperature#bedroom -')
	assert not box.result.text()
	box.setValue('avg(indoor.temperature.temperature#bedroom, indoor.humidity.humidity#office)')
	assert box.useExpression.isEnabled()
	assert box.useText(box.value())
	assert win.piece.node(path)['key'].startswith('avg(')


def test_a_row_drags_out_as_its_key(builder):
	box = builder.keysTab
	row = box.tree.topLevelItem(0)
	mime = box.tree.mimeData([row])
	assert mime.text() == row.data(0, Qt.ItemDataRole.UserRole)
	assert bytes(mime.data(tab.KEY_MIME)).decode() == mime.text()


def test_peek_works_out_an_expression_without_publishing_it():
	from LevityDash.lib.plugins.computed import computedEngine
	from LevityDash.lib.plugins.expressions import Expression
	engine = computedEngine()
	before = set(engine._entries)
	result, used = engine.peek(Expression.parse('1 + 2'))
	assert result == 3 and used == 0
	assert set(engine._entries) == before
	assert keys.preview('1 + 2') == '= 3'
	assert 'cannot parse' in keys.preview('1 +')
