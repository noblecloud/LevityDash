from typing import Optional, Union

from PySide2.QtWidgets import QFrame, QWidget
import logging

from src.grid.Cell import Cell

log = logging.getLogger(__name__)


class DummyWidget(QFrame):
	isEmpty = True
	value = None
	widget = None
	title = None
	glyph = None
	measurement = None
	cell: Cell = None

	def __init__(self, parent, assume: Union[bool, QWidget] = None, *args, **kwargs):
		super(DummyWidget, self).__init__(parent, *args, **kwargs)
		if parent and assume is None:
			assume = parent
		if assume:
			self.setSizePolicy(assume.sizePolicy())
			self.setMaximumSize(assume.geometry().size())
			self.setMinimumSize(parent.blockSize)
			self.assume = assume
			self.cell = assume.cell
		if self.cell is None:
			self.cell = Cell(self)
			self.cell.h = 1
			self.cell.w = 1
		self.setStyleSheet('background: white')

	# self.hide()

	def kill(self):
		self.parent().layout.removeWidget(self)
		self.hide()

	# def show(self):
	# 	self.hide()

	def autoShow(self):
		self.hide()

	def mousePressEvent(self, event):
		self.kill()
		super().mousePressEvent(event)
