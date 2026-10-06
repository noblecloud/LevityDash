from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPen

from .Panel import Panel


class ErrorTile(Panel, tag='error-tile'):
	"""Stands in for an item that raised while loading, in that item's geometry.

	Never saved: a save would write the tile out as nothing and delete the
	item's text from the file. `CentralPanel._save` refuses while one exists.
	"""
	savable = False

	def __init__(self, parent, label: str, message: str, geometry=None):
		self.label = label
		self.message = message
		super().__init__(parent=parent, geometry=geometry) if geometry is not None else super().__init__(parent=parent)
		self.setToolTip(f"{label}\n{message}")

	def paint(self, painter, option, widget):
		rect = self.rect()
		painter.setPen(QPen(QColor(220, 70, 70), 2))
		painter.setBrush(QColor(220, 70, 70, 40))
		painter.drawRect(rect.adjusted(1, 1, -1, -1))
		painter.setPen(QColor(235, 120, 120))
		font = QFont()
		font.setPixelSize(max(9, min(14, int(rect.height() / 6))))
		painter.setFont(font)
		painter.drawText(rect.adjusted(6, 4, -6, -4), int(Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap), f"{self.label}\n{self.message}")


__all__ = ['ErrorTile']
