from PySide2.QtCore import QObject
from PySide2.QtWidgets import QLabel


class StatusObject(QObject):

	def __init__(self, *args, **kwargs):
		self.setProperty('live', True)
		super().__init__(*args, **kwargs)

	def setLive(self, value):
		pass

	@property
	def live(self):
		return self.property('live')

	@live.setter
	def live(self, value: bool):
		self.setLive(value)
		self.setProperty('live', value)


class StatusLabel(QLabel, StatusObject):

	def setText(self, value):
		self.live = True
		super().setText(value)
