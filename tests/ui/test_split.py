"""`type: split`: two items either side of a divider, loaded from a dashboard, saved as only what differs."""
import copy

import pytest
import yaml
from PySide6.QtTest import QTest

from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.CentralPanel import StatefulDumper
from LevityDash.lib.ui.frontends.PySide.Modules.Containers.SplitPanel import SplitPanel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import Text

GROUPS = {
	'title': {'matchingGroup': {'group': 'global.title', 'matchAll': True}},
	'display': {'valueLabel': {'matchingGroup': {'group': 'global.value', 'matchAll': True}}},
}


def pane(name, *keys):
	return {
		'type': 'stack', 'name': name, 'direction': 'vertical', 'shared': copy.deepcopy(GROUPS),
		'items': [{'type': 'realtime.text', 'key': key, 'title': key.split('.')[-1]} for key in keys],
	}


@pytest.fixture
def sandbox(dashboard):
	box = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '50%', 'height': '50%'})
	yield box
	if box.scene() is not None:
		box.scene().removeItem(box)


def settle(dashboard):
	for _ in range(5):
		QTest.qWait(20)
		dashboard.app.processEvents()


def clear(dashboard, box):
	for child in box.childItems():
		if isinstance(child, Panel):
			box.scene().removeItem(child)
	settle(dashboard)


def load(dashboard, box, **split):
	clear(dashboard, box)
	box.state = {'items': [{'type': 'split', 'name': 'outer', **split}]}
	settle(dashboard)
	return next(c for c in box.childItems() if isinstance(c, SplitPanel))


def dump(box) -> dict:
	"""What a save writes for the sandbox, as plain data."""
	return yaml.safe_load(yaml.dump(box.state, Dumper=StatefulDumper, default_flow_style=False))['items'][0]


def two(**split):
	return {'items': [
		pane('left', 'environment.temperature.temperature', 'environment.humidity.humidity'),
		pane('right', 'environment.pressure.pressure', 'environment.wind.speed.speed'),
	], **split}


def test_a_split_loads_with_its_two_items_either_side(dashboard, sandbox):
	split = load(dashboard, sandbox, orientation='vertical', ratio=0.4, **two())
	first, second = split.primary, split.secondary
	assert first.stateName == 'left' and second.stateName == 'right'
	width = split.rect().width()
	assert first.rect().width() == pytest.approx(width * 0.4, abs=2)
	assert second.rect().width() == pytest.approx(width * 0.6, abs=2)
	assert second.pos().x() == pytest.approx(width * 0.4, abs=2)
	assert first.rect().height() == pytest.approx(split.rect().height(), abs=2)


def test_the_default_divider_is_horizontal_with_the_first_item_on_top(dashboard, sandbox):
	split = load(dashboard, sandbox, **two())
	assert split.primary.pos().y() == pytest.approx(0, abs=2)
	assert split.secondary.pos().y() == pytest.approx(split.rect().height() / 2, abs=2)
	assert split.secondary.rect().width() == pytest.approx(split.rect().width(), abs=2)


def test_a_save_writes_only_what_differs(dashboard, sandbox):
	load(dashboard, sandbox, **two())
	saved = dump(sandbox)
	assert saved['type'] == 'split'
	assert 'orientation' not in saved and 'ratio' not in saved
	assert [item['name'] for item in saved['items']] == ['left', 'right']
	assert all('geometry' not in item and 'locked' not in item and 'movable' not in item for item in saved['items'])

	load(dashboard, sandbox, orientation='vertical', ratio=0.4, **two())
	custom = dump(sandbox)
	assert custom['orientation'] == 'vertical' and custom['ratio'] == 0.4


def test_a_saved_split_loads_back_the_same(dashboard, sandbox):
	load(dashboard, sandbox, orientation='vertical', ratio=0.35, **two())
	saved = dump(sandbox)
	again = load(dashboard, sandbox, **{k: copy.deepcopy(v) for k, v in saved.items() if k not in ('type', 'name')})
	assert again.ratio == 0.35 and again.orientation.name == 'Vertical'
	assert dump(sandbox) == saved


def test_dragging_the_divider_is_saved_and_double_click_swaps_the_sides(dashboard, sandbox):
	split = load(dashboard, sandbox, orientation='vertical', **two())
	split.splitter.ratio = 0.25
	assert dump(sandbox)['ratio'] == 0.25
	assert split.primary.rect().width() == pytest.approx(split.rect().width() * 0.25, abs=2)
	split.splitter.swapSurfaces()
	assert [item['name'] for item in dump(sandbox)['items']] == ['right', 'left']


def test_one_item_fills_the_split(dashboard, sandbox):
	split = load(dashboard, sandbox, items=[pane('only', 'environment.wind.speed.speed')])
	assert split.primary.rect().size() == split.rect().size()
	assert split.secondary is None


def test_three_items_become_an_error_tile(dashboard, sandbox):
	clear(dashboard, sandbox)
	sandbox.state = {'items': [{'type': 'split', 'name': 'bad', 'items': [pane(n, 'environment.wind.speed.speed') for n in 'abc']}]}
	settle(dashboard)
	from LevityDash.lib.ui.frontends.PySide.Modules.ErrorTile import ErrorTile
	assert any(isinstance(c, ErrorTile) for c in sandbox.childItems())
	assert not any(isinstance(c, SplitPanel) for c in sandbox.childItems())


def values(dashboard, split):
	"""The value labels under the split: one per reading, four in all."""
	return [
		t for t in dashboard.scene.items()
		if isinstance(t, Text) and split.isAncestorOf(t) and t.isVisible() and t.size_group is not None
		and t.size_group.key == 'value'
	]


def test_size_groups_reach_across_the_two_items(dashboard, sandbox):
	"""The split lays out; it groups nothing, and it must not cut a group in two."""
	split = load(dashboard, sandbox, orientation='vertical', ratio=0.3, **two())
	settle(dashboard)
	members = values(dashboard, split)
	assert len(members) == 4
	assert len({id(t.size_group) for t in members}) == 1, 'one global.value group for all four'
	assert {split.primary.isAncestorOf(t) for t in members} == {True, False}, 'with members in both items'
	assert len({round(t.font().pointSizeF(), 2) for t in members}) == 1


def test_a_split_sizes_text_as_a_plain_stack_does(dashboard, sandbox):
	"""The split is not a size scope of its own: the same panes in a stack get the same sizes."""
	split = load(dashboard, sandbox, orientation='vertical', ratio=0.3, **two())
	settle(dashboard)
	inSplit = {round(t.font().pointSizeF(), 2) for t in values(dashboard, split)}
	clear(dashboard, sandbox)
	sandbox.state = {'items': [{'type': 'stack', 'name': 'outer', 'direction': 'horizontal', **two()}]}
	settle(dashboard)
	stack = next(c for c in sandbox.childItems() if isinstance(c, Panel))
	assert {round(t.font().pointSizeF(), 2) for t in values(dashboard, stack)} == inSplit


def test_a_group_stays_whole_after_the_divider_moves(dashboard, sandbox):
	split = load(dashboard, sandbox, orientation='vertical', ratio=0.3, **two())
	split.splitter.ratio = 0.7
	settle(dashboard)
	dashboard.refresh_all()
	after = values(dashboard, split)
	assert len(after) == 4
	assert len({id(t.size_group) for t in after}) == 1
	assert len({round(t.font().pointSizeF(), 2) for t in after}) == 1
