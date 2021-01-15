import logging

from PySide2 import QtCore, QtGui, QtWidgets

from widgets.loudWidget import LoudWidget
from widgets.DynamicLabel import DynamicGlyph, DynamicLabel
from widgets.Status import StatusObject


class GlyphBox(LoudWidget, StatusObject):
	_glyph: DynamicLabel
	_font: QtGui.QFont

	def __init__(self, glyph):
		super().__init__()

		# self.installEventFilter(self)
		self._glyph = DynamicGlyph(glyph)
		self._glyph.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

		layout = QtWidgets.QVBoxLayout()
		layout.addWidget(self._glyph, QtCore.Qt.AlignCenter)
		layout.setAlignment(QtCore.Qt.AlignCenter)

		self.setLayout(layout)
		self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

	# def eventFilter(self, obj, event):
	# 	# if event.type() == QtCore.QEvent.Resize:
	# 	# 	self._glyph.setText(str(self._glyph.font().pointSizeF()))
	# 	return super().eventFilter(obj, event)

	@property
	def glyph(self):
		return self._glyph

	@glyph.setter
	def glyph(self, value):
		self.live = True
		self._glyph = value
