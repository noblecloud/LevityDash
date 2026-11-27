"""Where a save writes: the file that is open, and only inside the config's `saves/dashboards/`.

Ctrl+S used to write `<config>/saves/dashboards/default.levity` whatever was open, so opening a reference
dashboard and saving it replaced the configured default. `CentralPanel.save` now writes the open file when
it lives in the saves folder, and offers Save As otherwise. The theme picker writes the open file too, so it
follows the same rule.
"""
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from LevityDash import LevityDashboard
from LevityDash.lib.config import userConfig


@pytest.fixture
def panel(dashboard):
	central = LevityDashboard.CENTRAL_PANEL
	saved = central.filePath
	yield central
	central.filePath = saved


@pytest.fixture
def savesDir():
	path = userConfig.userPath['saves']['dashboards'].path
	path.mkdir(parents=True, exist_ok=True)
	return path


def test_the_saves_folder_is_the_only_writable_place(panel, savesDir, tmp_path):
	assert panel.isConfigFile(savesDir / 'anything.levity')
	assert panel.isConfigFile(savesDir / 'nested' / 'still.levity')
	assert not panel.isConfigFile(tmp_path / 'scratch.levity')
	assert not panel.isConfigFile(Path('docs/design-references/grid-packing.levity').absolute())


def test_save_writes_the_open_config_file(panel, savesDir, monkeypatch):
	path = savesDir / 'open-dashboard.levity'
	calls = []
	monkeypatch.setattr(panel, '_save', lambda directory=None, name=None: calls.append(('save', directory, name)) or True)
	monkeypatch.setattr(panel, 'saveAs', lambda *a, **k: calls.append(('saveAs', a, k)))
	panel.filePath = path

	panel.save()

	assert calls == [('save', path.parent, path.name)]


def test_save_outside_the_config_is_save_as(panel, tmp_path, monkeypatch):
	path = tmp_path / 'reference.levity'
	path.write_text('- type: group\n  name: main\n  items: []\n')
	calls = []
	monkeypatch.setattr(panel, '_save', lambda directory=None, name=None: calls.append(('save', directory, name)) or True)
	monkeypatch.setattr(panel, 'saveAs', lambda *a, **k: calls.append(('saveAs', a, k)))
	panel.filePath = path

	panel.save()

	assert calls == [('saveAs', (), {'prefill': path})], 'a file outside saves/dashboards must not be rewritten in place'


def test_a_theme_change_does_not_write_a_file_outside_the_config(panel, tmp_path, monkeypatch):
	from LevityDash.lib.ui.colors import theme

	path = tmp_path / 'reference.levity'
	path.write_text('- type: group\n  name: main\n  items: []\n')
	panel.filePath = path
	def boom(*a, **k):
		raise AssertionError('a theme change wrote a file outside saves/dashboards')
	monkeypatch.setattr(panel, '_save', boom)

	written = panel.setTheme(next(name for name in theme.available() if name != theme.DEFAULT_NAME))

	assert written is False


def test_a_missing_file_reports_without_a_dialog(panel, tmp_path, monkeypatch):
	def boom(*a, **k):
		raise AssertionError('a control-socket load opened a modal dialog')
	monkeypatch.setattr(QMessageBox, 'critical', boom)

	with pytest.raises(FileNotFoundError):
		panel._load(tmp_path / 'not-there.levity', interactive=False)

