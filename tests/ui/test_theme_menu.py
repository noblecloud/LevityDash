"""The theme menu forces a theme and reloads; the Studio picker forces one too."""
import pytest

from LevityDash.lib.ui.colors import theme
from LevityDash.lib.ui.frontends.PySide.Modules.ThemeMenu import ThemeMenu


@pytest.fixture(autouse=True)
def default_theme():
	theme.reset()
	yield
	theme.reset()


def test_picking_a_theme_forces_it_and_reloads():
	reloads = []
	menu = ThemeMenu(None, lambda: reloads.append(1))
	names = [a.text() for a in menu.actions() if a.text()]
	assert names[0] == "Dashboard's own" and {'default', 'dusk', 'paper'} <= set(names)
	menu.pick('paper')
	assert theme.active().name == 'paper' and reloads == [1]
	assert menu._actions['paper'].isChecked()
	menu.pick(None)
	assert theme.override() is None and reloads == [1, 1]
	assert menu._actions[None].isChecked()


def test_override_survives_a_dashboard_asking_for_another_theme():
	theme.set_override('paper')
	assert theme.activate('dusk').name == 'paper'
