from typing import Union

from PySide2.QtGui import QFont, QResizeEvent, QShowEvent
from PySide2.QtWidgets import QBoxLayout, QFrame, QGridLayout, QHBoxLayout, QSizePolicy, QSpacerItem, QVBoxLayout, QWidget
from WeatherUnits import Measurement

from ui.fonts import compact, rounded
from ui.Complication_UI import Ui_Frame
from PySide2.QtCore import QSize, Qt, Signal

from utils import Logger
from widgets.DynamicLabel import DynamicLabel
from widgets.Proto import ComplicationPrototype


class Complication(Ui_Frame, ComplicationPrototype):

	# def __init__(self, title: str = None, value: Union[Measurement, int, float, str] = None):
	def __init__(self, *args, **kwargs):
		super(Complication, self).__init__(*args, **kwargs)
		self.setupUi(self)
		self.setLayout(self.verticalLayout)
		self.update()
		self.titleLabel._scalar = 0.8

		self.value = self._value

		if self._glyphTitle:
			self.titleLabel.setGlyph(self._glyphTitle)
		if self._widget:
			self.setWidget(self._widget)
		else:
			self.valueWidget.hide()
		if self._value is None and self._widget is None:
			self.hide()
		if 'miniature' in kwargs.keys():
			if kwargs['miniature']:
				self.titleLabel.setMinimumHeight(5)
				self.titleLabel.setMaximumHeight(30)
		del self._widget

	def setWidget(self, widget: QWidget):
		oldWidget = self.valueWidget
		self.valueWidget = widget
		self.layout.replaceWidget(oldWidget, self.valueWidget)
		self.valueWidget.show()
		self.valueLabel.clear()
		self.show()

	def resizeEvent(self, event: QResizeEvent) -> None:
		super().resizeEvent(event)
		if self._direction is not None:
			self.layout.setDirection(self._direction)
			alignmentValue = Qt.AlignBottom if self._direction == QVBoxLayout.BottomToTop else Qt.AlignTop
			alignmentTitle = Qt.AlignTop if self._direction == QVBoxLayout.BottomToTop else Qt.AlignBottom
			self.valueLabel.setAlignment(Qt.AlignHCenter | alignmentValue)
			self.titleLabel.setAlignment(Qt.AlignHCenter | alignmentTitle)
		elif self.parent() is not None and self.parent().height() / 2 < self.pos().y() and self._direction is None:
			self.layout.setDirection(QVBoxLayout.BottomToTop)
			self.valueLabel.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)

	def __repr__(self):
		return f"{self.title} | {self.value}"

	@property
	def dynamicFont(self) -> QFont:
		if str(self.fontInfo().family()).startswith('SF'):
			if self.dynamicFontSize > 21:
				font = QFont(rounded)
			else:
				font = QFont(compact)
		else:
			font = QFont(self.font())
		font.setPointSizeF(self.dynamicFontSize)
		return font

	@property
	def dynamicFontSize(self):
		return max(self.height() * 0.15, 14)

	# def titleOnTop(self, value: bool = True):
	# 	self._direction = QVBoxLayout.TopToBottom if value else QVBoxLayout.BottomToTop
	# 	self.update()

	def showEvent(self, event):
		super(Complication, self).showEvent(event)

	'''customTitle = self._glyphTitle if self._glyphTitle is not None else self._title'''


class LockedAspectRatio(QFrame):
	def resizeEvent(self, event):
		new_size = self.size()
		new_size.scale(event.size(), Qt.KeepAspectRatio)
		self.resize(new_size)
	# super(LockedAspectRatio, self).resizeEvent(event)
