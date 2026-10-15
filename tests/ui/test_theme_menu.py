"""The theme menu writes the pick into the dashboard file and reloads; the Studio picker forces one too."""
import pytest
import yaml
from PySide6.QtTest import QTest

from LevityDash.lib.EasyPath import EasyPathFile
from LevityDash.lib.ui.colors import theme
from LevityDash.lib.ui.frontends.PySide.Modules.ThemeMenu import ThemeMenu


@pytest.fixture(autouse=True)
def default_theme():
	theme.reset()
	yield
	theme.reset()


class FakeDashboard:
	"""Stands in for the CentralPanel: records what the menu asks of it."""

	def __init__(self, saves=True):
		self.saves, self.set, self.reloads, self.cleared = saves, [], 0, 0

	def setTheme(self, name):
		self.set.append(name)
		return self.saves

	def clear(self):
		self.cleared += 1

	def reload(self):
		self.reloads += 1


def test_picking_a_theme_saves_it_and_reloads():
	dashboard = FakeDashboard()
	menu = ThemeMenu(None, dashboard)
	names = [a.text() for a in menu.actions() if a.text()]
	assert {'default', 'dusk', 'paper'} <= set(names)
	menu.pick('paper')
	assert dashboard.set == ['paper'] and dashboard.cleared == dashboard.reloads == 1
	assert theme.override() is None


def test_an_unsaved_pick_is_forced_for_this_run():
	dashboard = FakeDashboard(saves=False)
	menu = ThemeMenu(None, dashboard)
	menu.pick('paper')
	assert theme.active().name == 'paper' and dashboard.reloads == 1
	assert menu._actions['paper'].isChecked()


def test_override_survives_a_dashboard_asking_for_another_theme():
	theme.set_override('paper')
	assert theme.activate('dusk').name == 'paper'


def _settle(dashboard):
	for _ in range(5):
		QTest.qWait(20)
		dashboard.app.processEvents()


def test_a_picked_theme_is_written_to_the_file_and_comes_back_on_reload(dashboard, tmp_path):
	base = dashboard.scene.base
	path = tmp_path / 'themed.levity'
	path.write_text('items:\n  - type: group\n    name: only\n    geometry: {x: 0%, y: 0%, width: 100%, height: 100%}\n')
	was = base.filePath
	try:
		base.filePath = EasyPathFile(path)
		base._load(base.filePath)
		_settle(dashboard)
		assert base.setTheme('dusk') is True
		assert yaml.safe_load(path.read_text())['theme'] == 'dusk'
		theme.reset()
		base.reload()
		_settle(dashboard)
		assert theme.active().name == 'dusk' and base.theme == 'dusk'
		# an inline theme keeps its colours and takes the pick as its parent
		base.theme = {'extends': 'dusk', 'colors': {'solar': '#ffd400'}}
		assert base.setTheme('paper') is True
		assert yaml.safe_load(path.read_text())['theme'] == {'extends': 'paper', 'colors': {'solar': '#ffd400'}}
		# the default theme is the absence of the key
		base.theme = 'dusk'
		assert base.setTheme('default') is True
		assert 'theme' not in yaml.safe_load(path.read_text())
	finally:
		if was is not None:
			base.filePath = was
			base._load(was)
			_settle(dashboard)
