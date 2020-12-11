import logging

from PySide2.QtGui import QMouseEvent
from PySide2.QtWidgets import QFrame


class LoudWidget(QFrame):
	def mousePressEvent(self, event: QMouseEvent) -> None:
		print(self)
		logging.info(self)
		super(LoudWidget, self).mousePressEvent(event)
