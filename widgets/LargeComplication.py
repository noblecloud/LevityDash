from typing import Any, Dict, Optional, Union

from PyQt5.QtGui import QColor
from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import QBoxLayout, QWidget
from WeatherUnits import Measurement

from ui import fonts
from ui.Temperature_UI import Ui_ComplicationGroup
from utils import randomColor, Position
from widgets.Complication import Complication, ComplicationArray, ComplicationArrayGrid, ComplicationArrayHorizontal, ComplicationArrayVertical
from widgets.Proto import ComplicationPrototype


class LargeComplication(Ui_ComplicationGroup, ComplicationPrototype):
	widgetPositions: dict[Position:Union[QWidget, ComplicationArray]]
	center: Union[ComplicationPrototype, QWidget, ComplicationArrayGrid]

	topArray: ComplicationArrayHorizontal
	bottomArray: ComplicationArrayHorizontal
	leftArray: ComplicationArrayVertical
	rightArray: ComplicationArrayVertical

	topLeft: Union[ComplicationPrototype, QWidget]
	topRight: Union[ComplicationPrototype, QWidget]
	bottomLeft: Union[ComplicationPrototype, QWidget]
	bottomRight: Union[ComplicationPrototype, QWidget]

	widgets = [Position.TopLeft, Position.TopRight, Position.Center,
	           Position.BottomLeft, Position.BottomRight]

	arrays = [Position.Top, Position.Left,
	          Position.Bottom, Position.Right]

	_showTitle: bool = True
	_showCenterTitle: bool = False
	_isGrid: bool = False

	@property
	def complications(self):
		return [*[x for l in [self.widgetPositions[item]._complications for item in self.arrays] for x in l], *[self.widgetPositions[item] for item in self.widgets if self.widgetPositions[item].title]]

	def __init__(self, parent, isGrid: bool = False, showCenterTitle: bool = None, *args, **kwargs):
		super(LargeComplication, self).__init__(*args, **kwargs)
		self.setupUi(self)
		self.widgetPositions = {
				Position.Top:          self.topArray,
				Position.TopCenter:    self.topArray,
				Position.TopLeft:      self.topLeft,
				Position.TopRight:     self.topRight,
				Position.Center:       self.center,
				Position.CenterLeft:   self.leftArray,
				Position.Left:         self.leftArray,
				Position.CenterRight:  self.rightArray,
				Position.Right:        self.rightArray,
				Position.Bottom:       self.bottomArray,
				Position.BottomCenter: self.bottomArray,
				Position.BottomLeft:   self.bottomRight,
				Position.BottomRight:  self.bottomRight,
		}
		if isGrid:
			self.isGrid = isGrid
		else:
			self.center: ComplicationPrototype
			self.center.showTitle = self._showCenterTitle

		self._color = QColor(randomColor())
		self.fillEmptyCells()
		self.parseAfterInit()
		self.update()
		self.setAttribute(Qt.WA_StyledBackground, True)
		self.setStyleSheet(f"background: {randomColor()}")

	def parseAfterInit(self):
		self.value = self._value

	@property
	def isGrid(self) -> bool:
		return self._isGrid

	@isGrid.setter
	def isGrid(self, value):
		self._isGrid = value
		if value:
			oldWidget = self.center
			self.center = ComplicationArrayGrid(self)
			self.layout.replaceWidget(oldWidget, self.center)
		else:
			oldWidget = self.center
			self.center = Complication(self)
			self.layout.replaceWidget(oldWidget, self.center)

	@property
	def showTitle(self) -> bool:
		return self._showTitle

	@showTitle.setter
	def showTitle(self, value: bool):
		self._showTitle = value

	def update(self):
		title: Optional[str] = self.title if self.glyphTitle is None else self.glyphTitle
		if title is None and hasattr(self._value, 'title'):
			title = self._value.title

		if self._showTitle and title:
			self.titleLabel.setText(title)
			self.titleLabel.show()
		else:
			self.titleLabel.clear()
			self.titleLabel.hide()

		if isinstance(self.value, QWidget):
			self.valueWidget.show()
			self.valueLabel.hide()
			self.layout.removeWidget(self.valueWidget)
			self.valueWidget = self.value
			self.layout.addWidget(self.valueWidget)
		elif self.value is None:
			pass
		else:
			self.valueLabel.setText(self.value)
			self.valueLabel.show()
			self.valueWidget.hide()
		QWidget.update(self)

	def fillEmptyCells(self):
		startingRow = 1 if self._showTitle else 0 if self.topArray.isEmpty else 2
		endingRow = 3 if self.bottomArray.isEmpty else 2
		startingCol = 0 if self.leftArray.isEmpty else 1
		endingCol = 2 if self.rightArray.isEmpty else 1

		colSpan = endingCol - startingCol + 1
		rowSpan = endingRow - startingRow + 1

		self.grid.addWidget(self.center, startingRow, startingCol, rowSpan, colSpan)

	def addItems(self, *item: Union[Measurement, str, int, float, QWidget, type],
	             position: Position = Position.Bottom):

		destination = self.widgetPositions[position]
		if position in self.arrays:
			destination.insert(*item)
		elif position in self.widgets:
			if isinstance(item, tuple) and len(item) > 1:
				self._log.warn(f'Only one [{item[0]}] item can be added here, the rest will be ignored: [{item[1:]}]')
				item = item[0]
			else:
				item = item[0]
			oldWidget = destination
			if isinstance(item, (str, int, float)):
				item = Complication(parent=self, value=item)
				# item.setMinimumHeight(100)
				item.setMinimumWidth(100)
				item.show()
			elif isinstance(item, type):
				subscriptionKey = item.__name__.lower() if item.__name__.isupper() else item.__name__
				item = Complication(parent=self, title=item.__name__, subscriptionKey=subscriptionKey)
				item.setMinimumWidth(100)
			elif isinstance(item, QWidget):
				pass
			else:
				self._log.error(f'This item [{item}] can not be added as this [{type(item)}] class')
				return None
			self.layout.replaceWidget(oldWidget, item)

		self.fillEmptyCells()

	@property
	def title(self):
		if self.showTitle and not self._isGrid:
			if self._title:
				return self._title
			else:
				return self.center.title
		return

	@title.setter
	def title(self, value):
		pass

	@property
	def value(self):
		if self._isGrid:
			return None
		else:
			return self.center.value

	@value.setter
	def value(self, value):
		if self._isGrid:
			self._log.warn('setting a value does not work with ComplicationGrids')
		else:
			self.center.value = value
			if self.showTitle:
				self.titleLabel.show()
				self.center.titleLabel.hide()
			else:
				self.titleLabel.hide()
				if self._showCenterTitle:
					self.center.titleLabel.show()
				else:
					self.center.titleLabel.hide()

	@property
	def maxFontSize(self):
		return self.center.maxFontSize

	@property
	def valueLabel(self):
		return self.center.valueLabel
