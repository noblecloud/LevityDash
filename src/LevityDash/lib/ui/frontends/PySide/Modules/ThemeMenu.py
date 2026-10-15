"""A menu that switches the colour theme of the running dashboard."""
from typing import Any, Optional

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu

from LevityDash.lib.ui import UILogger
from LevityDash.lib.ui.colors import theme

log = UILogger.getChild('ThemeMenu')

__all__ = ('ThemeMenu',)


class ThemeMenu(QMenu):
	"""``Theme``: every theme found in ``resources/themes`` and ``<config>/themes``, the dashboard's own marked.

	A pick is written into the dashboard file as its root ``theme:`` (``CentralPanel.setTheme``, the normal save) and the
	dashboard is built again from the file, because an item reads its ``$tokens`` once, when it is built. If the file cannot be written the
	pick still shows, as an override for this run (``theme.set_override``), and the log says so.
	"""

	def __init__(self, parent=None, dashboard: Any = None):
		super().__init__('Theme', parent)
		self._dashboard = dashboard
		self._group = QActionGroup(self)
		self._group.setExclusive(True)
		self._actions: dict[str, QAction] = {}
		self.aboutToShow.connect(self.rebuild)
		self.rebuild()
		theme.on_change(self._follow, call_now=False)

	def rebuild(self):
		"""List the themes again (a theme file may have been added) and mark the one in force."""
		self.clear()
		self._actions.clear()
		for action in list(self._group.actions()):
			self._group.removeAction(action)
		for name in theme.available():
			self._add(name, name)
		self._follow()

	def _add(self, name: str, text: str):
		action = self.addAction(text)
		action.setCheckable(True)
		action.triggered.connect(lambda _=False, name=name: self.pick(name))
		self._group.addAction(action)
		self._actions[name] = action

	def _current(self) -> Optional[str]:
		"""The name of the theme in force: a forced one, else the dashboard's, else the default."""
		active = theme.override() or theme.active()
		if active.name == 'inline':
			active = theme.load(active.extends or theme.DEFAULT_NAME)
		return next((n for n in theme.available() if _same(n, active)), None)

	def _follow(self, active=None):
		if (action := self._actions.get(self._current())) is not None:
			action.setChecked(True)

	def pick(self, name: str):
		try:
			theme.load(name)
		except theme.ThemeError as error:
			log.error(str(error))
			return
		dashboard = self._dashboard
		if dashboard is None or not dashboard.setTheme(name):
			log.error(f'The {name} theme was not saved to the dashboard file; it is in force for this run only.')
			try:
				theme.set_override(name)
			except theme.ThemeError as error:
				log.error(str(error))
				return
		if dashboard is not None:
			# A reload of the same file reconciles the items in place, and a display keeps the colour it first resolved.
			dashboard.clear()
			dashboard.reload()


def _same(name: str, other) -> bool:
	try:
		return theme.load(name) is other
	except theme.ThemeError:
		return False
