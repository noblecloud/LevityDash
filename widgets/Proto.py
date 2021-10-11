from typing import Optional, Union

from PySide2 import QtCore
from PySide2.QtGui import QBrush, QColor, QDrag, QDragEnterEvent, QDragMoveEvent, QDropEvent, QFont, QMouseEvent, QPainter, QPainterPath, QPaintEvent, QPen, QPixmap
from PySide2.QtCore import QEvent, QMimeData, QPoint, QPointF, QRect, QSize, Qt, Signal, Slot
from PySide2.QtWidgets import QBoxLayout, QSizeGrip, QSizePolicy, QWidget
from WeatherUnits.base import Measurement

from src.grid.Cell import Cell
from src.fonts import rounded, weatherGlyph
from src.utils import Logger
from colors import randomColor
from widgets.DynamicLabel import DynamicLabel
from widgets.grip import Gripper


class MimeDataOffset(QMimeData):
	offset: QPointF = QPointF(0, 0)


@Logger
class ComplicationPrototype(QWidget):
	sizeGripBR: QSizeGrip
	_classColor = randomColor()
	_direction: QBoxLayout.Direction = None
	_title: Optional[str] = None
	_widget: QWidget = None
	_glyphTitle: Optional[str] = None
	_value: Union[Measurement, float, int, QWidget, None] = None
	_titleOnTop: Optional[bool] = None
	_showTitle: bool
	_showUnit: bool
	_text: str
	_font: QFont
	_isGrid: bool = False
	_square: bool = False
	_subscriptionKey: str = None
	valueWidget: Optional[QWidget]
	valueLabel: Optional[DynamicLabel]
	titleLabel: Optional[DynamicLabel]
	_debug: bool = False

	@property
	def subTitleUnit(self) -> bool:
		return self._subTitleUnit

	@subTitleUnit.setter
	def subTitleUnit(self, value: bool):
		self._subTitleUnit = value

	def __init__(self, *args, title: str = None,
	             value: Union[Measurement, float, int] = None,
	             glyph: bool = False,
	             widget: QWidget = None,
	             direction: QBoxLayout.Direction = None,
	             showTitle: bool = True,
	             glyphTitle: str = None,
	             showUnit: bool = False,
	             miniature: bool = False,
	             square: bool = False,
	             subscriptionKey: str = None,
	             subTitleUnit: bool = None,
	             cell: Cell = None,
	             debug: bool = False,
	             placeholder: bool = False,
	             **kwargs):

		self._title = title
		self._value = value
		self._glyph = glyph
		self._widget = widget
		self._glyphTitle = glyphTitle
		self._showTitle = showTitle
		self._showUnit = showUnit
		self._direction = direction
		self._square = square
		self._subscriptionKey = subscriptionKey
		self._subTitleUnit = subTitleUnit
		self._color = randomColor()
		self._cell = cell
		self._showDelete = False

		local = [item[1:] for item in ComplicationPrototype.__dict__.keys() if item[0:2] != '__' and item[0] == '_']
		# super(ComplicationPrototype, self).__init__(*args, **{key: item for key, item in kwargs.items() if key not in local})
		super(ComplicationPrototype, self).__init__(parent=kwargs.get('parent', None))
		# self.setAttribute(Qt.WA_TranslucentBackground)
		self.setAttribute(Qt.WA_Hover)
		if not cell:
			self._cell = Cell(self, h=1, w=1)
		elif isinstance(cell, dict):
			self._cell = Cell(self, **cell)
		self.setWindowFlag(Qt.SubWindow)
		self.setMouseTracking(True)

	# self._debug = True
	# if debug:
	# self.setAttribute(Qt.WA_StyledBackground, True)
	# x = f'''
	# background: {self._color};
	# '''
	# self.setStyleSheet(x)

	def paintEvent(self, event):
		p = QPainter(self)
		if self._showDelete:
			p.setBrush(QBrush(QColor(0.7, 0, 0, 0)))
			# p.setPen(QColor(0, 0, 0, a=0.7))
			p.drawRect(self.rect())
		# pen.setWidth(self._lineWeight)
		# pen.setColor(QColor(self._classColor))
		# p.drawRect(self.rect())
		super(ComplicationPrototype, self).paintEvent(event)

	@property
	def pix(self) -> QPixmap:
		return self.grab(self.rect())

	def resizeEvent(self, event):
		self.setGripper()
		# if self._square:
		# 	new_size = QSize(10, 10)
		# 	new_size.scale(self.size(), Qt.KeepAspectRatio)
		# 	# self.setMinimumSize(new_size)
		# 	self.resize(new_size)
		super(ComplicationPrototype, self).resizeEvent(event)

	# def event(self, event):
	# 	if event.type() == QEvent.HoverMove:
	# 		if (event.pos() - self.rect().topRight()).manhattanLength() < 20:
	# 			if not self._showDelete:
	# 				print('delete area')
	# 				self._showDelete = True
	# 				self.repaint()
	# 		else:
	# 			if self._showDelete:
	# 				print('leave delete area')
	# 				self._showDelete = False
	# 				self.repaint()
	# 	return super().event(event)

	# def eventFilter(self, obj, event):
	# 	if event.type() == QtCore.QEvent.Enter:
	#
	# 		print('tset', obj)
	# 	return super(ComplicationPrototype, self).eventFilter(obj, event)

	@property
	def subscriptionKey(self):
		return self._subscriptionKey if self._subscriptionKey is not None else self.title.lower()

	@subscriptionKey.setter
	def subscriptionKey(self, value):
		self._subscriptionKey = value

	@property
	def canBalance(self):
		return hasattr(self, 'valueLabel') and self.valueLabel.isVisible() and not self._isGrid

	def setValue(self, value):
		self.value = value

	@property
	def shouldBeShown(self):
		t = [self.value is not None]
		return any(t)

	def autoShow(self):
		self.show() if self.shouldBeShown else self.hide()

	@property
	def glyphTitle(self):
		return self._glyphTitle

	@glyphTitle.setter
	def glyphTitle(self, glyph):
		self._title = None
		self._glyphTitle = glyph
		self.titleLabel.setGlyph(glyph)
		self.update()

	@property
	def showTitle(self) -> bool:
		return self._showTitle

	@showTitle.setter
	def showTitle(self, value: bool):
		self._showTitle = value
		if value:
			self.titleLabel.show()
		else:
			self.titleLabel.hide()

	@property
	def showUnit(self) -> bool:
		return self._showUnit

	@showUnit.setter
	def showUnit(self, value: bool):
		self._showUnit = value

	@property
	def square(self):
		return self._square

	@square.setter
	def square(self, value):
		self._square = value

	@property
	def title(self):
		title: Optional[str] = self._title if self._glyphTitle is None else self._glyphTitle
		if isinstance(self._value, str):
			return title
		elif title is None and hasattr(self._value, 'title'):
			title = self._value.title
		return title

	@title.setter
	def title(self, title: str):
		self._title = title
		self._glyphTitle = None
		self.titleLabel.setFont(rounded)
		self.update()

	@property
	def value(self) -> Union[str, QWidget, None, Measurement]:
		if isinstance(self._value, Measurement):
			return self._value
		elif isinstance(self._value, QWidget):
			return self._value
		elif self._value is None:
			return None
		else:
			return str(self._value)

	@value.setter
	def value(self, value):
		self.valueLabel.value = value
		self._value = value
		self.update()

	def hit(self, sender, position):
		p = self.mapFrom(sender, position)
		return self.valueLabel.hit(sender, position), self.rect().contains(p)

	def inHitBox(self, sender, position):
		return self.geometry().contains(self.mapTo(sender, position))

	@property
	def widget(self):
		return self._widget

	@widget.setter
	def widget(self, value):
		oldWidget = self._widget
		self._widget = value
		self.layout.replaceWidget(oldWidget, value)
		self._widget.show()

	# del oldWidget

	@property
	def showUnit(self) -> bool:
		return self._showUnit

	@showUnit.setter
	def showUnit(self, value: bool):
		self._showUnit = value
		self.update()

	@property
	def showTitle(self) -> bool:
		return self._showTitle

	@showTitle.setter
	def showTitle(self, value: bool):
		self._showTitle = value

	@property
	def layout(self) -> QBoxLayout:
		return super().layout()

	@property
	def direction(self):
		return self._direction

	@direction.setter
	def direction(self, value):
		self._direction = None

	@property
	def maxFontSize(self):
		return self.valueLabel.maxSize if self.valueLabel.maxSize is not None else 30

	@property
	def maxFontSizeTitle(self):
		return self.titleLabel.maxSize if self.valueLabel.maxSize is not None else 10

	# print(value)
	# if not self._customTitle:
	# 	self_title(f"{value.title} ({value.unit})" if self.showUnit else value.title)
	# self.valueLabel.setText(str(value))

	@property
	def subscriptionKey(self):
		if isinstance(self._value, Measurement):
			return self._value.subscriptionKey
		elif self._subscriptionKey is not None:
			return self._subscriptionKey
		elif self.title:
			t = self.title
			t = t.lower() if t.isupper() else t
			t = t.replace(' ', '')
			key = f"{t[0].lower()}{t[1:]}"
			self._log.warning(f'A subscription key was not provided by this complications measurement; using {key} generated from the title')
			return key
		else:
			return None

	@subscriptionKey.setter
	def subscriptionKey(self, value):
		pass

	def actionForPosition(self, position):
		print(self, position)

	@property
	def cell(self):
		return self._cell

	@cell.setter
	def cell(self, value):
		self._cell = value

	def autoSetCell(self):
		self.cell.w = max(1, round(self.width() / self.parent().columnWidth))
		self.cell.h = max(1, round(self.height() / self.parent().rowHeight))

	def setGripper(self):
		x = self.sizeGripBR.geometry()
		x.moveBottom(self.rect().bottom())
		x.moveRight(self.rect().right())
		self.sizeGripBR.setGeometry(x)
		x.moveLeft(self.rect().left())
		self.sizeGripBL.setGeometry(x)

	def mouseDoubleClickEvent(self, event):
		if self._showDelete:
			self.parent().yank(self)

	def mouseMoveEvent(self, event: QMouseEvent):
		print(event.pos())
		super(ComplicationPrototype, self).mouseMoveEvent(event)

	def startPickup(self):
		self.mouseHoldTimer.stop()
		i, child = self.parent().pluck(self)
		if child is self:
			self.hide()

		info = MimeDataOffset()
		info.setText(str(child))
		drag = QDrag(child)
		drag.setPixmap(child.pix)
		drag.setHotSpot(child.rect().center())
		drag.setParent(child)
		drag.setMimeData(info)

		status = drag.exec_()
		# self.dragCancel(i, child, status, drag)

		self.clickStart = None

	def dragCancel(self, index, child, status, drag):
		pass
