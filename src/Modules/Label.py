from src.Modules.Displays.Text import Text
from src import logging
from functools import cached_property
from typing import Any, Callable, Optional, Union

from PySide2.QtCore import QRectF, Qt, QTimer, Signal, Slot
from PySide2.QtGui import QColor, QFont, QFontMetrics, QPainter, QPalette, QPen, QTransform
from PySide2.QtWidgets import QApplication, QGraphicsItem, QGraphicsProxyWidget, QGraphicsTextItem, QLineEdit

from src.Modules.Handles.Figure import MarginHandles
from src.Grid import Geometry
from src.fonts import compact, rounded
from src import colorPalette
from src.utils import Alignment, AlignmentFlag, clearCacheAttr, Margins, Position, Size, SizeWatchDog, strToOrdinal, toOrdinal
from src.Modules.Panel import Panel
from src.Modules.Menus import EditableLabelContextMenu, LabelContextMenu

__all__ = ['Label', 'EditableLabel']

log = logging.getLogger(__name__)


# class Text(QGraphicsTextItem):
#
# 	def __init__(self, parent: Panel,
# 	             value: Optional[Any] = None,
# 	             alignment: Alignment = Alignment.Center,
# 	             scalar: float = 1.0,
# 	             font: Union[QFont, str] = None,
# 	             color: QColor = None):
# 		super(Text, self).__init__(parent=parent)
# 		self._value = None
# 		self.__alignment = None
# 		self.setParentItem(parent)
# 		self.setFlag(QGraphicsItem.ItemIsMovable, False)
# 		self.setFlag(QGraphicsItem.ItemIsSelectable, False)
# 		self.setFlag(QGraphicsItem.ItemIsFocusable, False)
# 		self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
# 		self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
# 		self.setAlignment(alignment)
# 		self.scalar = scalar
# 		self.setFont(font)
# 		self.setColor(color)
# 		self.value = value
# 		# print(self.text)
#
# 	@cached_property
# 	def fontMetrics(self) -> QFontMetrics:
# 		font = QFont(self.dynamicFont)
# 		self.__ratioFontSize = round(self.parentItem().marginRect.height())
# 		font.setPixelSize(self.__ratioFontSize)
# 		return QFontMetrics(font)
#
# 	@cached_property
# 	def ratio(self):
# 		textRect = self.fontMetrics.boundingRect(self.text())
# 		return self.__ratioFontSize / max(textRect.width(), 1)
#
# 	@property
# 	def dynamicFont(self) -> QFont:
# 		if self.font() is None:
# 			height = self. height()
# 			if height > 120:
# 				return QFont(rounded)
# 			return QFont(compact)
# 		return self.font()
#
# 	def setAlignment(self, alignment: Alignment):
# 		if not isinstance(alignment, Alignment):
# 			alignment = Alignment(alignment)
# 		self.__alignment = alignment
# 		# self.updateTransform()
#
# 	def alignment(self):
# 		return self.__alignment
#
# 	def setFont(self, font: Union[QFont, str]):
# 		if font == None:
# 			font = QFont(rounded.family(), 100)
# 		elif isinstance(font, str):
# 			font = QFont(font, self.height() * .1)
# 		elif isinstance(font, QFont):
# 			font = font
# 		else:
# 			font = QFont(font)
# 		super(Text, self).setFont(font)
# 		# self.updateTransform()
#
# 	# def updateTransform(self):
# 	# 	transform = QTransform()
# 	# 	parentRect = self.parentItem().rect()
# 	# #
# 	# # 	# transform.translate(self.boundingRect().width() * self.alignment().multipliers[0], self.boundingRect().height() * self.alignment().multipliers[1])
# 	# 	selfRect = self.fontMetrics.boundingRect(self.text())
# 	# # 	# selfRect.moveCenter(self.boundingRect().center().toPoint())
# 	# 	widthScalar = parentRect.width() / max(selfRect.width(), 1)
# 	# 	heightScalar = parentRect.height() / max(selfRect.height(), 1)
# 	# 	scale = min(widthScalar, heightScalar)
# 	# 	xMul, yMul = self.alignment().multipliers
# 	#
# 	# 	rect = self.boundingRect()
# 	# 	xOffset = parentRect.width() * xMul - rect.width() * xMul * scale
# 	# 	yOffset = parentRect.height() * -yMul - rect.height() * -yMul * scale
# 	#
# 	# 	transform.translate(*(rect.topLeft().toPoint() - selfRect.topLeft()).toTuple())
# 	# 	transform.scale(scale, scale)
# 	# 	self.setTransform(transform)
#
# 	def setColor(self, value):
# 		if value is None:
# 			color = colorPalette.windowText().color()
# 		elif isinstance(value, str) and value.startswith('#'):
# 			value = QColor(value)
# 		elif isinstance(value, QColor):
# 			color = value
# 		else:
# 			color = colorPalette.windowText().color()
# 		self.setDefaultTextColor(color)
#
# 	def updateFontSize(self):
# 		self.setFont(QFont(self.font().family(), self.parentItem().fontSize * self.scalar))
#
# 	def setPlainText(self, text: str) -> None:
# 		# self.setHtml('<p style="text-align:center;">' + text + '</p>')
# 		super(Text, self).setPlainText(text)
# 		# self.setTextWidth(len(str(text)) * 2)
# 		# self.updateTransform()
#
# 	def setRect(self, rect: QRectF) -> None:
# 		transform = QTransform()
# 		r = self.boundingRect()
# 		hS = self.boundingRect().height() / self.fontMetrics.height()
# 		widthScalar = rect.width() / max(r.width(), 1)
# 		heightScalar = rect.height() / (max(r.height(), 1))
# 		scale = min(widthScalar, heightScalar)
# 		if self.alignment().horizontal.isLeft:
# 			pass
# 		elif self.alignment().horizontal.isRight:
# 			transform.translate(rect.width() - r.width() * scale, 0)
# 		else:
# 			transform.translate((rect.width() - r.width() * scale) / 2, 0)
# 		if self.alignment().vertical.isTop:
# 			pass
# 		elif self.alignment().vertical.isBottom:
# 			transform.translate(0, rect.height() - r.height() * scale)
# 		else:
# 			transform.translate(0, (rect.height() - r.height() * scale) / 2)
# 		xMul, yMul = self.alignment().multipliers
# 		transform.scale(scale, scale)
# 		transform.translate(*(rect.topLeft() - r.topLeft()).toTuple())
# 		# transform.translate(rect.width() * self.alignment().multipliers[0], rect.height() * self.alignment().multipliers[1])
# 		self.setTransform(transform)
#
# 	def paint(self, painter: QPainter, option, widget):
# 		# # painter.translate()
# 		# parentRect = self.parentItem().rect()
# 		# #
# 		# # 	# transform.translate(self.boundingRect().width() * self.alignment().multipliers[0], self.boundingRect().height() * self.alignment().multipliers[1])
# 		#
# 		# # 	# selfRect.moveCenter(self.boundingRect().center().toPoint())
# 		# # r = self.fontMetrics.boundingRect(self.text())
# 		# # r = self.fontMetrics.boundingRect(parentRect.toRect(), self.alignment().asQtAlignment, self.text(), 0)
# 		# # selfRect = self.boundingRect()
# 		# r = self.boundingRect()
# 		#
# 		# widthScalar = parentRect.width() / max(r.width(), 1)
# 		# heightScalar = parentRect.height() / max(r.height(), 1)
# 		# xMul, yMul = self.alignment().multipliers
# 		# scale = min(widthScalar, heightScalar)
# 		# xOffset = r.width() * xMul
# 		# yOffset = parentRect.height() * -yMul - r.height() * -yMul
# 		# transform = QTransform()
# 		#
# 		# # painter.translate(xOffset, yOffset)
# 		# # painter.scale(scale, scale)
# 		#
# 		#
# 		#
# 		#
# 		# # painter.setRenderHint(QPainter.Antialiasing, False)
# 		# # painter.setRenderHint(QPainter.TextAntialiasing, False)
# 		# # painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
# 		# # painter.setRenderHint(QPainter.HighQualityAntialiasing, False)
# 		# # # Falsepainter.setRenderHint(QPainter.NonCosmeticDefaultPen, False)
# 		# painter.setRenderHint(QPainter.Qt4CompatiblePainting, False)
# 		super(Text, self).paint(painter, option, widget)
#
# 		painter.setPen(QPen(Qt.red, 1))
# 		painter.drawRect(self.boundingRect())
#
# 	@property
# 	def value(self):
# 		return self._value
#
# 	@value.setter
# 	def value(self, value):
# 		if str(value) != self.text():
# 			self._value = value
# 			self.setPlainText(self.text())
#
# 	def text(self):
# 		if self.value is None:
# 			return ''
# 		return str(self.value)


class Label(Panel):
	_text = ''
	__filters: dict[str, Callable] = {'0Ordinal': toOrdinal, '0Add Ordinal': strToOrdinal, '1Lower': str.lower, '1Upper': str.upper, '2Title': str.title}
	enabledFilters: set[str]
	_acceptsChildren = False

	__ratioFontSize = 100
	_lineBreaking: bool

	def __init__(self, parent: Union['Panel', 'GridScene'],
	             text: str = "",
	             alignment: Alignment = None,
	             filters: list[str] = None,
	             font: QFont = None,
	             lineBreaking: bool = False,
	             *args, **kwargs):
		if filters is None:
			filters = list()
		self.lineBreaking = lineBreaking
		self.enabledFilters: set = set()
		super().__init__(parent=parent, *args, **kwargs)
		if alignment is None:
			alignment = Alignment.Center
		self.alignment: Alignment = alignment
		self.font = QFont(rounded)
		self.marginHandles = MarginHandles(self)
		self.marginHandles.signals.action.connect(self.textBox.updateTransform)
		self.textBox.setParentItem(self)
		self.text = text
		# self.showGrid = False
		for filter in filters:
			self.setFilter(filter, True)
		self.font = font
		# self.grid = None

		self.update()
		self.setAcceptDrops(False)

	@cached_property
	def textBox(self):
		a = Text(self, value=str(self.text))
		a.setParentItem(self)
		return a

	def editMargins(self):
		self.marginHandles.show()

	def dragEnterEvent(self, event):
		if event.mimeData().hasFormat('text/plain'):
			event.accept()

	def shouldShowGrid(self) -> bool:
		return False

	def __repr__(self):
		return f'<{self.__class__.__name__}(text={self.text}, position={Position(self.pos())}, size={Size(self.rect().size())} {f", {self.gridItem}," if self.snapping else ""} zPosition={self.zValue()}>'

	@property
	def filters(self):
		return list(self.__filters.keys())

	@property
	def lineBreaking(self):
		return self._lineBreaking

	@lineBreaking.setter
	def lineBreaking(self, value):
		self._lineBreaking = value
		clearCacheAttr(self, 'ratio', 'fontMetrics', 'fontSize')

	@property
	def state(self):
		state = super(Label, self).state
		state['alignment'] = self.alignment.asDict()
		state['filters'] = list(self.enabledFilters)
		state['text'] = self.text
		if self.lineBreaking:
			state['lineBreaking'] = True
		return state

	@cached_property
	def contextMenu(self):
		return LabelContextMenu(self)

	@property
	def alignment(self):
		return self.textBox.align

	@alignment.setter
	def alignment(self, value):
		self.textBox.setAlignment(value)

	def setAlignment(self, alignment: AlignmentFlag):
		if isinstance(alignment, Alignment):
			self.alignment = alignment
		elif isinstance(alignment, AlignmentFlag):
			if alignment.isVertical:
				self.alignment.vertical = alignment.asVertical
			if alignment.isHorizontal:
				self.alignment.horizontal = alignment.asHorizontal
		elif isinstance(alignment, int, str):
			self.alignment = AlignmentFlag[alignment]
		self.update()

	def setFilter(self, filter: str, value: bool = None):
		rawString = str(self.text)
		print(f'Setting filter: {filter}')
		if value is None:
			value = not filter in self.enabledFilters
		if value:
			self.enabledFilters.add(filter)
		else:
			self.enabledFilters.discard(filter)
		if rawString == self.text:
			self.enabledFilters.discard(filter)
			log.warning(f'Filter {filter[1:]} is not applicable to "{rawString}"')

		self.update()

	@cached_property
	def fontMetrics(self):
		font = QFont(self.dynamicFont)
		self.__ratioFontSize = self.marginRect.height() or 10
		font.setPixelSize(self.__ratioFontSize)
		return QFontMetrics(font)

	def refresh(self):
		clearCacheAttr(self, 'ratio', 'fontMetrics', 'fontSize')
		self.update()

	@property
	def text(self):
		text = str(self._text)
		for filter in self.enabledFilters:
			text = self.__filters[filter](text)
		if self.lineBreaking:
			text = text.replace(' ', '\n')
		return text

	@text.setter
	def text(self, value):
		# clearCacheAttr(self, 'ratio', 'fontMetrics', 'fontSize')
		self._text = value
		self.textBox.text = value

		self.update()

	def setText(self, text: str):
		self._text = text

	@cached_property
	def ratio(self):
		textRect = self.fontMetrics.boundingRect(self.text)
		return self.__ratioFontSize / max(textRect.width(), 1)

	def height(self):
		return self.rect().height()

	def width(self):
		return self.rect().width()

	@property
	def isEmpty(self):
		return self.text == ''

	@property
	def dynamicFont(self) -> QFont:
		if self.font is None:
			height = self.height()
			if height > 120:
				return QFont(rounded)
			return QFont(compact)
		return self.font

	def updateRatio(self):
		clearCacheAttr(self, 'ratio', 'fontMetrics', 'fontSize')
		self.update()

	@cached_property
	def fontSize(self):
		rect = self.marginRect
		return round(max(10, min(self.ratio * rect.width(), rect.height())))

	def setRect(self, rect: QRectF):
		super(Label, self).setRect(rect)
		self.textBox.setPos(self.rect().topLeft())
		self.textBox.updateTransform()


class HiddenLineEdit(QLineEdit):
	parent: 'EditableLabel'

	def __init__(self, parent, *args, **kwargs):
		self.parent = parent
		super(HiddenLineEdit, self).__init__(*args, **kwargs)
		self.setVisible(False)

	def paintEvent(self, event) -> None:
		pass

	def focusOutEvent(self, event):
		print('focus out')
		self.parent.setFocus()
		self.parent.doneEditing()
		super(HiddenLineEdit, self).focusOutEvent(event)

	def focusInEvent(self, event):
		print('focus in')
		super(HiddenLineEdit, self).focusInEvent(event)


class EditableLabel(Label):

	def __init__(self, *args, **kwargs):
		self.lineEdit = HiddenLineEdit(self)
		self._manualValue = None
		super().__init__(*args, **kwargs)
		proxy = QGraphicsProxyWidget(self)
		proxy.setWidget(self.lineEdit)
		self.lineEdit.textChanged.connect(self.textChanged)
		self.lineEdit.cursorPositionChanged.connect(self.cursorPositionChanged)
		self.lineEdit.returnPressed.connect(self.doneEditing)
		self.editTimer = QTimer(interval=3000, timeout=self.doneEditing, singleShot=True)
		self.setFlag(QGraphicsItem.ItemIsSelectable, True)

		self.setAcceptDrops(True)
		self.setAcceptHoverEvents(True)

	def focusInEvent(self, event):
		super(EditableLabel, self).focusInEvent(event)

	def focusOutEvent(self, event):
		super(EditableLabel, self).focusOutEvent(event)

	def dragEnterEvent(self, event):
		if event.mimeData().hasText():
			event.accept()
			self.__text = self._text
			self.text = event.mimeData().text()
		else:
			event.ignore()

	def dragLeaveEvent(self, event):
		self.text = self.__text
		event.accept()

	def dropEvent(self, event):
		self.text = event.mimeData().text()
		event.accept()

	def hoverLeaveEvent(self, event):
		if self.lineEdit.keyboardGrabber() is self.lineEdit:
			self.doneEditing()

	def cursorPositionChanged(self):
		self.editTimer.start()
		self.update()

	def textChanged(self, text: str):
		self.editTimer.start()
		self.setText(text)

	def mouseDoubleClickEvent(self, event):
		self.edit()

	def doneEditing(self):
		print('done editing')
		self.editTimer.stop()
		self.lineEdit.releaseKeyboard()
		self.lineEdit.releaseMouse()
		self.lineEdit.clearFocus()
		self.clearFocus()
		self._text = self._text.strip()
		if len(self._text) == 0:
			self._manualValue = False
		else:
			self._manualValue = True

	@property
	def text(self):
		text = str(self._text)
		if self.lineEdit.keyboardGrabber() is self.lineEdit:
			cursorPos = self.lineEdit.cursorPosition()
			text = list(text)
			text.insert(cursorPos, '_')
			text = ''.join(text)
		return text

	@text.setter
	def text(self, value):
		self._text = value
		self.lineEdit.setText(value)
		if hasattr(self, 'ratio'):
			delattr(self, 'ratio')

	@cached_property
	def contextMenu(self):
		return EditableLabelContextMenu(self)

	def edit(self):
		self.lineEdit.grabKeyboard()
		self.update()
		self.setFocus(Qt.MouseFocusReason)

	def delete(self):
		self.editTimer.stop()
		super(EditableLabel, self).delete()


class TitleLabel(EditableLabel):

	def __init__(self, *args, **kwargs):
		kwargs['geometry'] = Geometry(surface=self, size=(1, 0.2), position=Position(0, 0), absolute=False, snapping=False)
		super().__init__(*args, **kwargs)
		self.setMovable(False)
		self._manualValue = kwargs.get('manualValue', False)

	def allowDynamicUpdate(self) -> bool:
		return not self._manualValue

	@property
	def state(self):
		state = super().state
		if self._manualValue:
			state['manualValue'] = self._manualValue
		return state
