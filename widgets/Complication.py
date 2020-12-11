from PySide2.QtCore import QFile
from PySide2.QtUiTools import QUiLoader

from classes.loudWidget import LoudWidget
from ui.Complication_UI import Ui_Frame


class Complication(LoudWidget, Ui_Frame):

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.setupUi(self)

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
