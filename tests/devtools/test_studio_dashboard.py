"""The Studio builder editing a real dashboard file: open, change, save back only what changed."""
import shutil
from pathlib import Path

import pytest

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
import yaml  # noqa: E402
from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402

from LevityDash.devtools import _studio_builder as sb  # noqa: E402
from LevityDash.devtools import _studio_preset as m  # noqa: E402

# Copies of the design dashboards as they were written without presets: stack shorthand and size groups in plain
# sight, which the Studio must keep. The design dashboards themselves use presets and may change; this one does not.
BOARDS = Path(__file__).parent / 'dashboards'


class StubEngine:
	size = (1440, 900)

	def __init__(self):
		self.drawn = []

	def resize(self, size):
		self.size = size

	def render(self, items, names, root=None):
		self.drawn.append((items, root))
		image = QImage(64, 40, QImage.Format.Format_ARGB32)
		image.fill(0)
		return image, {path: QRectF(10, 10, 100, 50) for path in names.values()}


@pytest.fixture
def board(tmp_path, monkeypatch):
	monkeypatch.setenv('LEVITYDASH_STUDIO_DIR', str(tmp_path / 'studio'))

	def make(name):
		target = tmp_path / f'{name}.levity'
		shutil.copy(BOARDS / f'{name}.levity', target)
		win = sb.Builder(target, engine=StubEngine(), dashboard=True)
		win.timer.stop()
		boards.append(win)
		return win, target

	boards = []
	yield make
	for win in boards:
		win.close()


@pytest.mark.parametrize('name', ['station', 'storm', 'sky', 'week'])
def test_save_without_a_change_leaves_the_file_as_it_was(board, name):
	win, path = board(name)
	before = path.read_text()
	win.save()
	assert path.read_text() == before


def test_a_geometry_edit_changes_only_that_line(board):
	win, path = board('station')
	before = path.read_text().splitlines()
	target = next(p for p, n in win.piece.walk() if p and 'geometry' in n and isinstance(n['geometry'], dict) and 'width' in n['geometry'])
	win.select(target)
	win.editField('geometry.width', '33%')
	assert win.isDirty()
	win.save()
	after = path.read_text().splitlines()
	changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
	assert len(before) == len(after) and 1 <= len(changed) <= 2
	assert not win.isDirty()
	assert win.status.text().endswith('as it was')
	assert yaml.safe_load(path.read_text()) == win.piece.dashboard()


def test_the_root_keys_reach_the_preview(board):
	win, _ = board('station')
	win.redraw()
	items, root = win.engine.drawn[-1]
	assert root and root['vars'] and 'theme' in root


def test_shorthand_items_stay_as_written(board):
	win, path = board('station')
	shorts = [p for p in _paths(win.piece.template) if m.opaque(win.piece.raw(p))]
	assert shorts, 'station.levity has stack shorthand'
	win.select(shorts[0])
	assert win.selection == shorts[0]
	text = path.read_text()
	win.duplicateItem()
	win.save()
	assert path.read_text() != text
	assert yaml.safe_load(path.read_text()) == win.piece.dashboard()


def _paths(node, path=()):
	out = []
	for i, kid in enumerate(node.get('items') or []):
		out.append(path + (i,))
		if isinstance(kid, dict) and not m.opaque(kid):
			out += _paths(kid, path + (i,))
	return out


def test_edit_root_keys_keeps_their_order(board):
	win, path = board('storm')
	win.select(())
	extras = {k: v for k, v in win.piece.root.items() if k != 'items'}
	extras['vars'] = dict(extras['vars'], zz_new='#123456')
	win.editField('#root', extras)
	win.save()
	data = yaml.safe_load(path.read_text())
	assert list(data) == list(win.piece.root)
	assert data['vars']['zz_new'] == '#123456'


def test_save_refuses_the_real_config_folder(board, tmp_path, monkeypatch):
	win, path = board('storm')
	monkeypatch.setattr(sb, 'inRealConfig', lambda p: True)
	asked = []
	monkeypatch.setattr(win, 'saveAs', lambda: asked.append(1))
	win.editField('name', 'x') if False else None
	before = path.read_text()
	win.save()
	assert asked and path.read_text() == before


def test_undo_restores_the_dashboard(board):
	win, _ = board('storm')
	saved = win.piece.dashboard()
	win.select((0,))
	win.deleteItem()
	assert win.isDirty()
	win.undo()
	assert win.piece.dashboard() == saved and not win.isDirty()


def test_a_bare_key_can_be_selected_and_changed(board):
	win, path = board('station')
	bare = [p for p in _paths(win.piece.template) if isinstance(win.piece.raw(p), str)]
	if not bare:
		win.select(())
		win.addItem('spacer')
		win.piece.template['items'].append('environment.wind.speed')
		bare = [len(win.piece.template['items']) - 1]
		bare = [tuple(bare)]
	win.select(bare[0])
	assert win.selection == bare[0]
	win.editField('=', 'environment.wind.gust')
	assert win.piece.raw(bare[0]) == 'environment.wind.gust'


def test_theme_and_vars_have_controls(board):
	win, path = board('storm')
	win.select(())
	assert {'#theme.extends', '#theme.colors', '#vars', '#root'} <= set(win.itemTab.rows)
	before = dict(win.piece.root['vars'])
	win.editField('#vars', dict(before, zz='#112233'))
	win.editField('#theme.extends', 'dusk')
	win.save()
	data = yaml.safe_load(path.read_text())
	assert data['vars']['zz'] == '#112233' and data['theme']['extends'] == 'dusk'
	assert {k: v for k, v in data['vars'].items() if k != 'zz'} == before
	assert list(data) == list(win.piece.root)


def test_the_theme_picker_writes_the_pick_to_the_file(board):
	from LevityDash.lib.ui.colors import theme
	win, path = board('station')
	win.select(())
	win.themePicker.setCurrentText('paper')
	win.themePicker._activated()
	assert win.isDirty() and theme.override() is None
	win.save()
	saved = yaml.safe_load(path.read_text())['theme']
	assert saved['extends'] == 'paper' and saved['colors']  # an inline theme keeps its colours
	# a reopened dashboard shows the theme its file names, without forcing it
	win.openDashboard(path)
	assert win.themePicker.currentText() == 'paper' and theme.override() is None
	# a named theme is replaced by the pick, and an undo takes the pick back
	win.editField('#theme', 'paper')
	win.themePicker.setCurrentText('dusk')
	win.themePicker._activated()
	assert win.piece.root['theme'] == 'dusk'
	win.undo()
	assert win.piece.root['theme'] == 'paper'
	win.themePicker.setCurrentText('default')
	win.themePicker._activated()
	assert 'theme' not in win.piece.root
	theme.reset()


def test_a_row_left_alone_keeps_its_type(board):
	win, _ = board('storm')
	win.select(())
	edit = win.itemTab.rows['#vars'].editor
	before = dict(win.piece.root['vars'])
	seen = []
	edit.changed.connect(seen.append)
	key, val, *_ = edit._rows[0]
	key.setText(key.text())
	edit._done()
	assert not seen, 'nothing changed'
	assert edit.value() == before


def test_group_memberships_survive_an_edit(board):
	win, path = board('station')
	count = path.read_text().count('matchingGroup')
	target = next(p for p, n in win.piece.walk() if p and isinstance(n.get('geometry'), dict) and 'width' in n['geometry'])
	win.select(target)
	win.editField('geometry.width', '33%')
	win.save()
	assert path.read_text().count('matchingGroup') == count > 0


def test_group_scopes_are_found():
	node = {'type': 'stack', 'shared': {'title': {'matchingGroup': {'group': 'rowTitle@temperature', 'matchAll': True}}}, 'items': [{'matchingGroup': 'plain'}, {'matchingGroup': {'group': '$g@x'}}]}
	assert list(sb._groupScopes(node)) == ['rowTitle@temperature']


def test_to_preset_warns_only_about_inherited_scopes(board):
	win, _ = board('station')
	inner = next(p for p, n in win.piece.walk() if len(p) > 1 and n.get('type') == 'realtime.text')
	parent_has = any('rowTitle@' in str(win.piece.node(inner[:i]).get('shared')) for i in range(len(inner)))
	win.select(inner)
	win.extractPreset('zz-leaf')
	assert ('inherits size groups' in win.status.text()) == parent_has


def test_the_command_line_parser_builds(capsys):
	"""`studio.py --help` runs: no flag is declared twice."""
	from LevityDash.devtools import studio
	with pytest.raises(SystemExit) as stop:
		studio.main(['--help'])
	assert stop.value.code == 0
	out = capsys.readouterr().out
	assert '--polar' in out and '--gauge' in out and '--scenario' in out


def test_the_old_state_folder_moves_once(tmp_path):
	from LevityDash.devtools import _studio_state as st
	old = tmp_path / st.OLD_NAME
	old.mkdir()
	(old / 'studio.ini').write_text('[pins]\nkept=1\n')
	new = tmp_path / st.NAME
	assert st._moveOldFolder(new) == new
	assert (new / 'studio.ini').read_text().endswith('kept=1\n') and not old.exists()
	old.mkdir()
	st._moveOldFolder(new)
	assert old.exists(), 'a folder that is already there is left alone'


def test_a_file_with_a_template_is_a_preset_and_the_rest_are_dashboards(tmp_path):
	from LevityDash.devtools import _studio_library as library
	preset = tmp_path / 'p.levity'
	preset.write_text('props: {}\ntemplate: {type: group}\n')
	board = tmp_path / 'd.levity'
	board.write_text('items: []\n')
	assert library.classify(preset) == library.PRESET and library.classify(board) == library.DASHBOARD


def test_only_the_builder_stages_a_dashboard():
	import _studio_env
	assert _studio_env._runsBuilder(['/x/studio.py'])
	assert not _studio_env._runsBuilder(['pytest'])


def test_the_studio_names_its_process_and_has_an_icon_of_its_own():
	import sys
	from LevityDash.devtools import _studio_identity as ident
	art = Path(__file__).parents[2] / 'src' / 'LevityDash' / 'resources' / 'ui-elements'
	assert (art / 'icon-studio.png').exists()
	assert (art / 'icon-studio.png').read_bytes() != (art / 'icon512.png').read_bytes()
	if sys.platform.startswith('linux'):
		before = Path('/proc/self/comm').read_text()
		try:
			assert ident.apply(art / 'icon-studio.png')
			assert Path('/proc/self/comm').read_text().strip() == 'LevityDashStudi'
		finally:
			Path('/proc/self/comm').write_text(before.strip())


def test_arrow_keys_nudge_the_selected_item_and_undo(board):
	from PySide6.QtCore import Qt
	from PySide6.QtTest import QTest
	win, path = board('station')
	target = next(p for p, n in win.piece.walk() if len(p) >= 2 and n.get('geometry'))
	win.select(target)
	win.refresh() if hasattr(win, 'refresh') else None
	win.timer.stop()
	if target not in win.stage.rects:
		pytest.skip('item not on the stage')
	before = yaml.safe_dump(win.piece.template, sort_keys=False)
	x0 = float(str(win.piece.node(target)['geometry']['x']).rstrip('%'))
	QTest.keyClick(win.stage, Qt.Key.Key_Right)
	assert float(win.piece.node(target)['geometry']['x'].rstrip('%')) == pytest.approx(x0 + 1, abs=0.15)
	QTest.keyClick(win.stage, Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
	assert float(win.piece.node(target)['geometry']['x'].rstrip('%')) == pytest.approx(x0 - 4, abs=0.3)
	win.undo(); win.undo()
	assert yaml.safe_dump(win.piece.template, sort_keys=False) == before


def test_copy_and_paste_an_item_and_undo(board):
	from PySide6.QtWidgets import QApplication
	win, path = board('station')
	before = yaml.safe_dump(win.piece.template, sort_keys=False)
	source = next(p for p, n in win.piece.walk() if len(p) >= 2 and not n.get('items') and str(n.get('type')) not in sb.CONTAINERS)
	win.select(source)
	win.copyItem()
	assert yaml.safe_load(QApplication.clipboard().text())[0] == win.piece.node(source)
	count = len(win.piece.node(source[:-1])['items'])
	win.pasteItem()  # a leaf is selected: the copy goes right after it
	assert len(win.piece.node(source[:-1])['items']) == count + 1 and win.selection == source[:-1] + (source[-1] + 1,)
	win.undo()
	assert yaml.safe_dump(win.piece.template, sort_keys=False) == before
	QApplication.clipboard().setText('not: [valid')
	win.pasteItem()
	assert yaml.safe_dump(win.piece.template, sort_keys=False) == before and 'clipboard' in win.status.text()


def test_a_dropped_row_moves_the_item_and_undo_puts_it_back(board):
	win, path = board('station')
	before = yaml.safe_dump(win.piece.template, sort_keys=False)
	target = next(p for p, n in win.piece.walk() if p and n.get('type') == 'group' and p != (0,))
	moving = next(p for p, n in win.piece.walk() if len(p) >= 2 and not n.get('items') and not m.holds(n) and p[:-1] != target)
	count = len(win.piece.node(target).get('items') or [])
	win.relocateItem(moving, target, -1)
	assert yaml.safe_dump(win.piece.template, sort_keys=False) != before
	win.undo()
	assert yaml.safe_dump(win.piece.template, sort_keys=False) == before
	win.relocateItem((0,), (0, 0), -1)  # into itself: refused, nothing changes or is recorded
	assert yaml.safe_dump(win.piece.template, sort_keys=False) == before


def test_dropping_a_tree_row_onto_a_container_moves_it_in(board):
	"""A drag cannot be run offscreen, so the drop event is built by hand with the position Qt would report."""
	from PySide6.QtCore import QMimeData, QPointF, Qt
	from PySide6.QtGui import QDropEvent
	from PySide6.QtWidgets import QAbstractItemView
	win, path = board('storm')
	win.resize(1200, 800)
	win.show()
	rows, stack = [], [win.tree.topLevelItem(0)]
	while stack:
		row = stack.pop(0)
		rows.append(row)
		stack += [row.child(i) for i in range(row.childCount())]
	data = Qt.ItemDataRole.UserRole
	source = next(r for r in rows if r.childCount() == 0 and len(r.data(0, data)) >= 2 and not m.holds(win.piece.node(r.data(0, data))))
	target = next(r for r in rows if r.childCount() and r.data(0, data) and r.data(0, data) != source.data(0, data)[:-1] and r.data(0, data) != source.data(0, data)[:len(r.data(0, data))])
	win.tree.setCurrentItem(source)
	win.tree.dropIndicatorPosition = lambda: QAbstractItemView.DropIndicatorPosition.OnItem
	before = yaml.safe_dump(win.piece.template, sort_keys=False)
	at = QPointF(win.tree.visualItemRect(target).center())
	win.tree.dropEvent(QDropEvent(at, Qt.DropAction.MoveAction, QMimeData(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
	assert yaml.safe_dump(win.piece.template, sort_keys=False) != before
	win.undo()
	assert yaml.safe_dump(win.piece.template, sort_keys=False) == before


def test_tree_shortcuts_copy_paste_delete_duplicate_and_move(board):
	from PySide6.QtCore import Qt
	from PySide6.QtGui import QShortcut
	from PySide6.QtWidgets import QApplication
	win, path = board('station')
	target = next(p for p, n in win.piece.walk() if len(p) >= 2 and not n.get('items') and str(n.get('type')) not in sb.CONTAINERS)
	win.select(target)
	win.tree.setFocus()
	keys = {s.key().toString(): s for s in win.tree.findChildren(QShortcut)}
	for name in ('Ctrl+C', 'Ctrl+V', 'Del', 'Ctrl+D', 'Alt+Up', 'Alt+Down'):
		assert any(name.lower() in k.lower() for k in keys), name
	count = len(win.piece.node(target[:-1])['items'])
	[s for k, s in keys.items() if 'ctrl+d' in k.lower()][0].activated.emit()
	assert len(win.piece.node(target[:-1])['items']) == count + 1
	[s for k, s in keys.items() if 'del' in k.lower()][0].activated.emit()
	assert len(win.piece.node(target[:-1])['items']) == count
	assert win.tree.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu


def test_wrap_and_unwrap_keep_placement_and_undo(board):
	win, path = board('station')
	target = next(p for p, n in win.piece.walk() if len(p) >= 2 and 'geometry' in n and not m.opaque(n))
	before = yaml.safe_dump(win.piece.template)
	geometry = win.piece.node(target)['geometry']
	win.select(target)
	win.wrapItem()
	box = win.piece.node(target)
	assert box['type'] == 'group' and box['geometry'] == geometry
	assert 'geometry' not in box['items'][0]
	win.unwrapItem()
	assert yaml.safe_dump(win.piece.template) == before  # unwrap is the exact inverse
	win.undo()
	win.undo()
	assert yaml.safe_dump(win.piece.template) == before
	# the dashboard itself is left alone
	win.select(())
	win.wrapItem()
	assert win.piece.template is not None and len(win.history) == 0


def test_tree_filter_keeps_matches_and_their_containers(board):
	win, path = board('station')

	def shown():
		rows, stack = [], [win.tree.topLevelItem(0)]
		while stack:
			row = stack.pop()
			if not row.isHidden():
				rows.append(row.text(0))
				stack += [row.child(i) for i in range(row.childCount())]
		return rows

	everything = shown()
	win.filterBox.setText('wind')
	some = shown()
	assert 0 < len(some) < len(everything)
	assert any('wind' in r.lower() for r in some[1:])
	win.rebuildTree()
	assert shown() == some  # a rebuild after an edit keeps the filter
	win.filterBox.setText('')
	assert len(shown()) == len(everything)
	win.filterBox.setText('zzzz-no-such-item')
	assert win.tree.topLevelItem(0).isHidden()
