import logging

from PySide2.QtCore import Signal
from PySide2.QtGui import QMouseEvent
from PySide2.QtWidgets import QFrame


class LoudWidget(QFrame):
	clicked = Signal(QFrame)

	def mousePressEvent(self, event: QMouseEvent) -> None:
		super(LoudWidget, self).mousePressEvent(event)

	def mouseReleaseEvent(self, event: QMouseEvent) -> None:
		super(LoudWidget, self).mouseReleaseEvent(event)
