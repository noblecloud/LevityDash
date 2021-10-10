from PySide2.QtGui import QFont

from ui.conditions_UI import Ui_conditions
from widgets.loudWidget import LoudWidget
from widgets.Status import StatusObject


class Submodule(LoudWidget, StatusObject):

	def __init__(self, *args, **kwargs):
		super().__init__()
		self.setProperty('live', False)

	# @property
	# def live(self):
	# 	return self.property('live')
	#
	# @live.setter
	# def live(self, value: bool):
	# 	self.setProperty('live', value)


class currentConditions(Ui_conditions, Submodule):

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.glyphs = QFont()
		self.glyphs.setPointSize(30)
		self.glyphs.setFamily(u"Weather Icons")
		self.setupUi(self)
		self.glyphLabel.fontFamily = u"Weather Icons"
		self.forecastString = False
		sshFile = "styles/conditions.qss"
		with open(sshFile, "r") as fh:
			self.setStyleSheet(fh.read())

	# self.forecastString.setFont('test')

	def resizeEvent(self, event):
		super().resizeEvent(event)
		if self.height() > 100:
			font = self.glyphLabel._font()
			font.setPointSizeF(self.height() * .9)
			self.glyphLabel.setFont(font)
			self.topSpacer.setDisabled(True)
			self.forecastStringLabel.setDisabled(True)
			self.currentConditionLabel.setDisabled(True)
			self.bottomSpacer.setDisabled(True)

	@property
	def glyph(self):
		return None

	@glyph.setter
	def glyph(self, value):
		self.live = True
		self.glyphLabel.glyph = value

	@property
	def forecastString(self):
		return self.forecastStringLabel.text()

	@forecastString.setter
	def forecastString(self, value):
		self.live = True
		if value:
			self.forecastStringLabel.setText(value)
			self.forecastStringLabel.show()
		else:
			self.forecastStringLabel.hide()

	@property
	def currentCondition(self):
		return self.currentConditionLabel.text()

	@currentCondition.setter
	def currentCondition(self, value):
		if value:
			self.currentConditionLabel.setText(value)
			self.currentConditionLabel.show()
		else:
			self.currentConditionLabel.hide()
