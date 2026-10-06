"""Dev-only: the colour-theme picker in Gauge Studio.

Not the Studio's own light/dark button, which styles the controls. This one picks the theme the gauge is drawn in,
so a `$token` in a template can be tried against `default`, `dusk`, `paper` and any file in `<config>/themes`.
"""
from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QComboBox

from LevityDash.lib.ui.colors import theme


class ThemePicker(QComboBox):
	"""One entry per theme. ``picked(name)`` fires after the theme is forced; ``stageColor`` is its ground."""

	picked = Signal(str)

	def __init__(self, parent=None):
		super().__init__(parent)
		self.setToolTip('The colour theme the gauge is drawn in')
		self.addItems(theme.available())
		self.setCurrentText(theme.DEFAULT_NAME)
		self.activated.connect(self._activated)

	def _activated(self, _=None):
		name = self.currentText()
		theme.set_override(name)
		self.picked.emit(name)

	def select(self, name: str):
		"""Force ``name`` (as if picked), without a signal."""
		with QSignalBlocker(self):
			self.setCurrentText(name)
		theme.set_override(name)

	@staticmethod
	def stageColor() -> QColor:
		return theme.color('background').QColor
