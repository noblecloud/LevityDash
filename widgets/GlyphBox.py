import logging

from PySide2 import QtCore, QtGui, QtWidgets

from classes.loudWidget import LoudWidget
from widgets.DynamicLabel import DynamicLabel


class GlyphBox(LoudWidget):
	_label: DynamicLabel
	_font: QtGui.QFont

	def __init__(self, glyph):
		super().__init__()

		# self.installEventFilter(self)
		self._label = DynamicLabel(glyph)
		self._label.maxSize = 200
		self._font = QtGui.QFont('Weather Icons')
		self._label.setFont(self._font)
		self._label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

		layout = QtWidgets.QVBoxLayout()
		layout.addWidget(self._label, QtCore.Qt.AlignCenter)
		layout.setAlignment(QtCore.Qt.AlignCenter)

		self.setLayout(layout)
		self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

	def _setGlyph(self, glyph):
		if isinstance(glyph, str):
			try:
				self._label.setText(chr(int(glyph, 16)))
			except ValueError:
				logging.error('Glyph must be valid hex code: received: {}'.format(glyph))
		elif isinstance(glyph, int):
			self._label.setText(chr(glyph))
		else:
			self._label.setText(chr(0))

	def update(self):
		super().update()
		self._font = QtGui.QFont('Weather Icons')

	def eventFilter(self, obj, event):
		if event.type() == QtCore.QEvent.Resize:
			self._label.setText(str(self._label.font().pointSizeF()))
		return super().eventFilter(obj, event)

	@property
	def glyph(self):
		return self._glyph

	@glyph.setter
	def glyph(self, value):
		self._setGlyph(value)
