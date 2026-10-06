"""A menu that switches the colour theme of the running dashboard."""
from typing import Callable, Optional

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu

from LevityDash.lib.ui import UILogger
from LevityDash.lib.ui.colors import theme

log = UILogger.getChild('ThemeMenu')

__all__ = ('ThemeMenu',)


class ThemeMenu(QMenu):
	"""``Theme``: the dashboard's own theme, then every theme found in ``resources/themes`` and ``<config>/themes``.

	A pick is an override for this run (``theme.set_override``), so it does not touch the dashboard file; "Dashboard's
	own" lifts it. The board is reloaded after a pick, because an item reads its ``$tokens`` once, when it is built.
	"""

	def __init__(self, parent=None, reload: Optional[Callable[[], None]] = None):
		super().__init__('Theme', parent)
		self._reload = reload
		self._group = QActionGroup(self)
		self._group.setExclusive(True)
		self._actions: dict[Optional[str], QAction] = {}
		self.aboutToShow.connect(self.rebuild)
		self.rebuild()
		theme.on_change(self._follow, call_now=False)

	def rebuild(self):
		"""List the themes again (a theme file may have been added) and mark the one in force."""
		self.clear()
		self._actions.clear()
		for action in list(self._group.actions()):
			self._group.removeAction(action)
		self._add(None, "Dashboard's own")
		self.addSeparator()
		for name in theme.available():
			self._add(name, name)
		self._follow()

	def _add(self, name: Optional[str], text: str):
		action = self.addAction(text)
		action.setCheckable(True)
		action.triggered.connect(lambda _=False, name=name: self.pick(name))
		self._group.addAction(action)
		self._actions[name] = action

	def _current(self) -> Optional[str]:
		"""The name of the forced theme, or ``None`` when the dashboard chooses."""
		override = theme.override()
		if override is None:
			return None
		return next((n for n in theme.available() if _same(n, override)), None)

	def _follow(self, active=None):
		current = self._current()
		if (action := self._actions.get(current)) is not None:
			action.setChecked(True)

	def pick(self, name: Optional[str]):
		try:
			theme.set_override(name)
		except theme.ThemeError as error:
			log.error(str(error))
			return
		if self._reload is not None:
			self._reload()


def _same(name: str, other) -> bool:
	try:
		return theme.load(name) is other
	except theme.ThemeError:
		return False
