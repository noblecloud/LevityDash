from typing import Union

from PySide2.QtWidgets import QPushButton

from widgets.Status import StatusObject
from widgets.loudWidget import LoudWidget
from ui.Complication_UI import Ui_Frame
from PySide2.QtCore import QObject, Signal, Slot


class Complication(Ui_Frame, LoudWidget, StatusObject):

	clicked: Signal

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.clicked = Signal()
		self.setupUi(self)

	def mousePressEvent(self, event):
		self.clicked.emit()
		print('test')

	def setLive(self, value):
		self.value.live = value
	# @property
	# def title(self):
	# 	return self.title.text()
	#
	# @title.setter
	# def title(self, value):
	# 	self.title.setText(value)
	#
	# @property
	# def value(self):
	# 	return self.value.text()
	#
	# @value.setter
	# def value(self, value):
	# 	self.value.setText(value)
