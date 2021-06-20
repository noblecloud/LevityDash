from math import ceil, sqrt
from typing import Union

from PySide2.QtCore import QSize, Qt, Signal
from PySide2.QtGui import QResizeEvent, QShowEvent
from PySide2.QtWidgets import QBoxLayout, QFrame, QGridLayout, QHBoxLayout, QSizePolicy, QSpacerItem, QVBoxLayout, QWidget
from WeatherUnits import Measurement

from utils import Logger
from widgets.Complication import Complication
from widgets.DynamicLabel import DynamicLabel
from widgets.Proto import ComplicationPrototype


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
				maxValueSize = list(item.maxFontSize for item in complicationsOnly)
				heights = list(item.valueLabel.localY for item in complicationsOnly if item.valueLabel.localY is not None and item.valueLabel.isVisible())
				maxTitleSize = list(item.maxFontSizeTitle for item in complicationsOnly if isinstance(item.titleLabel, DynamicLabel) and item.titleLabel.isVisible())
				for comp in complicationsOnly:
					if maxValueSize:
						comp.valueLabel.setSharedFontSize(min(maxValueSize))
					if maxTitleSize:
						comp.titleLabel.setSharedFontSize(min(maxTitleSize))
					if heights:
						comp.valueLabel.sharedHeight = (min(heights))
			else:
				pass
			# self._log.warning('nothing to balance')

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

	def makeComplication(self, item, **kwargs):
		localArgs = {'parent': self, 'direction': self.layoutDirection}
		if kwargs is not None:
			localArgs.update(kwargs)

		if isinstance(item, ComplicationPrototype):
			comp = item
			comp.setParent(self)
			comp.direction = self.layoutDirection

		elif isinstance(item, Measurement):
			localArgs.update({'title': item.title, 'value': item, 'subscriptionKey': item.subscriptionKey})

		elif issubclass(item, Measurement):
			localArgs.update({'title': item.title, 'subscriptionKey': item.subscriptionKey})

		elif isinstance(item, QWidget):
			localArgs.update({'value': None, 'widget': item})

		comp = Complication(**localArgs)
		self._complications.append(comp)
		if comp.title:
			self.__setattr__(comp.subscriptionKey, comp)
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
		self.layout.setDirection(QVBoxLayout.LeftToRight)
		self.balanceFontSizes()

	def addSpacer(self):
		self.layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))


class ComplicationArrayGrid(ComplicationArray):
	_layoutDirection = QVBoxLayout.TopToBottom
	layout: QGridLayout
	_titlesOnTop = True

	# _square: bool = True

	def __init__(self, *args, **kwargs):
		super(ComplicationArrayGrid, self).__init__(*args, **kwargs)
		self.setLayout(QGridLayout())
		self.setMargins()

	def insert(self, *item: Union[Measurement, str, int, float, QWidget], **kwargs):
		if isinstance(item[0], list):
			item = tuple(item[0])
		if isinstance(item, tuple):
			for i in item:
				self.makeComplication(i, **kwargs)
		else:
			self.makeComplication(item, **kwargs)

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
