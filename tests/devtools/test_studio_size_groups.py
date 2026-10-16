"""The Studio's Size groups tab reads the real engine's groups, flags a `@name` that no panel has, and writes the keys by hand."""
from pathlib import Path

import pytest
import yaml

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402

from LevityDash.devtools import _studio_builder as sb  # noqa: E402
from LevityDash.devtools import _studio_groups as sg  # noqa: E402
from tests.conftest import pump  # noqa: E402

BOARD = '''
- type: group
  name: left
  geometry: {x: 0%, y: 0%, width: 50%, height: 100%}
  items:
    - {type: text, text: "alpha", name: a, matchingGroup: {group: global.size, matchAll: true}, geometry: {x: 0%, y: 0%, width: 100%, height: 20%}}
    - {type: text, text: "beta", name: b, matchingGroup: {group: global.size, matchAll: true}, geometry: {x: 0%, y: 40%, width: 100%, height: 20%}}
- type: group
  name: right
  geometry: {x: 50%, y: 0%, width: 50%, height: 100%}
  items:
    - {type: text, text: "gamma", name: c, matchingGroup: {group: global.size, matchAll: true}, geometry: {x: 0%, y: 0%, width: 100%, height: 20%}}
    - {type: text, text: "delta", name: d, matchingGroup: "title@right", geometry: {x: 0%, y: 40%, width: 100%, height: 20%}}
    - {type: text, text: "lost", name: e, matchingGroup: "title@zzz", geometry: {x: 0%, y: 70%, width: 100%, height: 20%}}
'''


@pytest.fixture
def groups(dashboard, tmp_path):
	panel = LevityDash.LevityDashboard.CENTRAL_PANEL
	target = tmp_path / 'groups.levity'
	target.write_text(BOARD)
	was = panel.filePath
	panel._load(target)
	pump(dashboard.app, 1.5)
	names = {'left': (0,), 'right': (1,), 'a': (0, 0), 'b': (0, 1), 'c': (1, 0), 'd': (1, 1), 'e': (1, 2)}
	yield sg.collect(dashboard.scene, names)
	# the dashboard fixture is shared by the whole session: put its own file back
	if was is not None:
		panel._load(was)
		pump(dashboard.app, 1.5)


def test_every_text_is_listed_under_the_group_it_joined(groups):
	by = {g.label: g for g in groups}
	shared = by['global.size']
	assert shared.matchAll and len(shared.members) == 3
	assert {m.path for m in shared.members} == {(0, 0), (0, 1), (1, 0)}, 'one group across both panels, not one per panel'


def test_a_name_no_panel_has_is_flagged_and_a_real_one_is_not(groups):
	bad = [g for g in groups if g.unresolved]
	assert [g.unresolved for g in bad] == ['zzz'] and bad[0].members[0].path == (1, 2)
	ok = [g for g in groups if g.key == 'title' and not g.unresolved]
	assert ok and ok[0].members[0].path == (1, 1)


def test_the_spec_round_trips_what_the_file_holds():
	assert sg.spec('global.value') == ('global.value', False)
	assert sg.spec({'group': 'global.value', 'matchAll': True}) == ('global.value', True)
	assert sg.written('global.value', True) == {'group': 'global.value', 'matchAll': True}
	assert sg.written(' x ', False) == 'x' and sg.written('', True) is None


class Stub:
	"""An engine that answers with the groups it is given, so the tab can be tested without a second Qt boot."""
	size = (1440, 900)

	def __init__(self, found):
		self.groups = found

	def resize(self, size):
		self.size = size

	def render(self, items, names, root=None):
		image = QImage(64, 40, QImage.Format.Format_ARGB32)
		image.fill(0)
		return image, {path: QRectF(10, 10, 100, 50) for path in names.values()}


def test_the_tab_lists_groups_flags_the_missing_scope_and_writes_shared_keys(groups, tmp_path, monkeypatch):
	monkeypatch.setenv('LEVITYDASH_STUDIO_DIR', str(tmp_path / 'studio'))
	target = tmp_path / 'board.levity'
	target.write_text('- {type: group, name: left, items: [{type: text, text: x}]}\n')
	win = sb.Builder(target, engine=Stub(groups), dashboard=True)
	try:
		win.timer.stop()
		win.redraw()
		tab = win.groupsTab
		rows = [tab.tree.topLevelItem(i) for i in range(tab.tree.topLevelItemCount())]
		assert len(rows) == len(groups)
		flagged = [r for r in rows if r.text(0).startswith('⚠')]
		assert len(flagged) == 1 and 'zzz' in flagged[0].text(0)
		assert '1 matching no panel' in tab.summary.text()
		tab.tree.setCurrentItem(flagged[0])
		assert len(win.stage.marks) == 1, 'picking a group outlines its text on the stage'
		win.select((0,))
		tab.role.setCurrentIndex(0)
		tab.name.setText('global.title')
		tab.matchAll.setChecked(True)
		tab._apply()
		assert win.piece.node((0,))['shared']['title']['matchingGroup'] == {'group': 'global.title', 'matchAll': True}
		tab.role.setCurrentIndex(1)
		tab.name.setText('global.value')
		tab.matchAll.setChecked(False)
		tab._apply()
		assert win.piece.node((0,))['shared']['display']['valueLabel']['matchingGroup'] == 'global.value'
		tab.role.setCurrentIndex(0)
		tab._remove()
		assert 'title' not in win.piece.node((0,))['shared']
	finally:
		win.close()
