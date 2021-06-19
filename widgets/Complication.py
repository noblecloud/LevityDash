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


@Logger
class ComplicationArray(QFrame):
	_complications: list[Complication]
	_layoutDirection = None
	layout: QBoxLayout
	_square: bool = False
	valueChangedSignal = Signal(Complication)
	_balance = True

	def __init__(self, *args, **kwargs):
		self._complications = []
		super(ComplicationArray, self).__init__(*args, **kwargs)
		self.valueChangedSignal.connect(self.balanceFontSizes)
		if not self._complications:
			self.hide()

	def setMargins(self):
		self.layout.setContentsMargins(0, 0, 0, 0)
		self.layout.setSpacing(5)

	@property
	def isVertical(self) -> bool:
		return self.layout.direction() < 1

	@property
	def isEmpty(self):
		return not bool(self._complications)

	def resizeEvent(self, event) -> None:
		if self._square:
			new_size = QSize(10, 10)
			new_size.scale(event.size(), Qt.KeepAspectRatio)
			self.resize(new_size)
		self.balanceFontSizes()
		super().resizeEvent(event)

	def balanceFontSizes(self):
		if self.balance:
			complicationsOnly = list(item for item in self._complications if isinstance(item, ComplicationPrototype) and item.canBalance)
			if complicationsOnly:
				maxFontSize = min(item.maxFontSize for item in complicationsOnly) if complicationsOnly else 0
				maxFontSizeTitles = min(item.maxFontSizeTitle for item in complicationsOnly if isinstance(item.titleLabel, DynamicLabel) and item.titleLabel.isVisible()) if complicationsOnly else 0
				for comp in complicationsOnly:
					comp.valueLabel.setSharedFontSize(maxFontSize)
					comp.titleLabel.setSharedFontSize(maxFontSizeTitles)
			else:
				self._log.warning('nothing to balance')

	def insert(self, *item: Union[Measurement, str, int, float, QWidget, type]):
		if isinstance(item[0], list):
			item = tuple(item[0])
		if isinstance(item, tuple):
			for i in item:
				self.layout.addWidget(self.makeComplication(i))
		else:
			self.layout.addWidget(self.makeComplication(item))
		self.show()
		self.update()

	def makeComplication(self, item):
		if isinstance(item, ComplicationPrototype):
			comp = item
			comp.setParent(self)
			comp.direction = self.layoutDirection
		elif isinstance(item, Measurement):
			comp = Complication(parent=self, value=item, direction=self.layoutDirection)
		elif isinstance(item, type):
			subscriptionKey = item.__name__.lower() if item.__name__.isupper() or item.__name__.istitle() else item.__name__
			comp = Complication(parent=self, title=item.__name__, subscriptionKey=subscriptionKey, direction=self.layoutDirection)
		elif isinstance(item, QWidget):
			print('testardad')
			comp = Complication(parent=self, widget=item, direction=self.layoutDirection)
		self._complications.append(comp)
		if comp.title:
			self.__setattr__(comp.title.lower(), comp)
		return comp

	def replace(self, items: Union[list[Measurement], Measurement]):
		self.clear()
		self.insert(items)

	def clear(self):
		while self.layout.count():
			child = self.layout.takeAt(0)
			if child.widget():
				child.widget().deleteLater()

	@property
	def layout(self):
		return super().layout()

	@property
	def layoutDirection(self):
		return self._layoutDirection

	@property
	def complications(self):
		return [*[x for x in self._complications if not hasattr(x, 'complications')], *[l for y in [x.complications for x in self._complications if hasattr(x, 'complications')] for l in y]]

	@property
	def balance(self):
		return self._balance

	@balance.setter
	def balance(self, value):
		self._balance = value

	@property
	def layoutDirection(self):
		return QVBoxLayout.TopToBottom if self.parent().height() / 2 < self.pos().y() else QVBoxLayout.BottomToTop


class ComplicationArrayVertical(ComplicationArray):
	layout: QVBoxLayout
	_layoutDirection = QVBoxLayout.TopToBottom

	def __init__(self, *args, **kwargs):
		super(ComplicationArrayVertical, self).__init__(*args, **kwargs)
		self.setLayout(QVBoxLayout())
		# self.layout.addItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))
		self.setMargins()


class ComplicationArrayHorizontal(ComplicationArray):
	_layoutDirection = None
	layout: QHBoxLayout
	_balance = True

	def __init__(self, *args, **kwargs):
		super(ComplicationArrayHorizontal, self).__init__(*args, **kwargs)
		self.setLayout(QHBoxLayout())
		self.setMargins()

	def showEvent(self, event: QShowEvent) -> None:
		super().showEvent(event)
		self.balanceFontSizes()

	def resizeEvent(self, event: QResizeEvent) -> None:
		super().resizeEvent(event)
		self.balanceFontSizes()

	def addSpacer(self):
		self.layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))


from math import sqrt, ceil


class ComplicationArrayGrid(ComplicationArray):
	_layoutDirection = QVBoxLayout.TopToBottom
	layout: QGridLayout
	_titlesOnTop = True
	_square: bool = True

	def __init__(self, *args, **kwargs):
		super(ComplicationArrayGrid, self).__init__(*args, **kwargs)
		self.setLayout(QGridLayout())
		self.setMargins()

	def insert(self, *item: Union[Measurement, str, int, float, QWidget]):
		if isinstance(item[0], list):
			item = tuple(item[0])
		if isinstance(item, tuple):
			for i in item:
				self.makeComplication(i)
		else:
			self.makeComplication(item)

		self.setWidgets()

	def setWidgets(self):
		s = ceil(sqrt(len(self._complications)))
		for i, widget in enumerate(self._complications):
			row = i // s
			col = i % s
			self.layout.addWidget(widget, row, col)
		self.show()

	def showEvent(self, event: QShowEvent) -> None:
		self.balanceFontSizes()
		super().showEvent(event)

	def resizeEvent(self, event: QResizeEvent) -> None:
		self.balanceFontSizes()
		super().resizeEvent(event)


class LockedAspectRatio(QFrame):
	def resizeEvent(self, event):
		new_size = self.size()
		new_size.scale(event.size(), Qt.KeepAspectRatio)
		self.resize(new_size)
	# super(LockedAspectRatio, self).resizeEvent(event)
