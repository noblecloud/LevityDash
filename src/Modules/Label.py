from src import logging
from functools import cached_property
from typing import Callable, Union

from PySide2.QtCore import QRectF, Qt, QTimer, Signal, Slot
from PySide2.QtGui import QFont, QFontMetrics, QPalette, QPen
from PySide2.QtWidgets import QApplication, QGraphicsItem, QGraphicsProxyWidget, QLineEdit

from src.Modules.Handles.Figure import MarginHandles
from src.Grid import Geometry
from src.fonts import compact, rounded
from src import colorPalette
from src.utils import Alignment, AlignmentFlag, clearCacheAttr, Margins, Position, Size, StepSignal, strToOrdinal, toOrdinal
from src.Modules.Panel import Panel
from src.Modules.Menus import EditableLabelContextMenu, LabelContextMenu

__all__ = ['Label', 'EditableLabel']

log = logging.getLogger(__name__)


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
		self.changeWatcher = StepSignal(signal=self.updateRatio, step=10)
		self.enabledFilters: set = set()
		super().__init__(parent=parent, *args, **kwargs)
		if alignment is None:
			alignment = Alignment.Center
		self.alignment: Alignment = alignment
		self.text = text
		self.font = QFont(rounded)
		self.marginHandles = MarginHandles(self)
		# self.showGrid = False
		for filter in filters:
			self.setFilter(filter, True)
		self.font = font
		# self.grid = None

		self.update()
		self.setAcceptDrops(False)

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
		self.__ratioFontSize = round(self.marginRect.height())
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
		clearCacheAttr(self, 'ratio', 'fontMetrics', 'fontSize')
		self._text = value

		self.update()

	def setText(self, text: str):
		if str(self._text) != str(text):
			clearCacheAttr(self, 'ratio', 'fontMetrics', 'fontSize')
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
		return max(10, min(self.ratio * rect.width(), rect.height()))

	def setRect(self, rect: QRectF):
		super(Label, self).setRect(rect)
		clearCacheAttr(self, 'ratio', 'fontMetrics', 'fontSize', 'marginRect')

	def paint(self, painter, option, widget):
		super(Label, self).paint(painter, option, widget)
		painter.setPen(QPen(colorPalette.windowText().color()))
		painter.setBrush(Qt.NoBrush)
		font = self.dynamicFont
		font.setPixelSize(self.fontSize)

		painter.setFont(font)
		rect = self.marginRect

		painter.drawText(rect, self.alignment.asQtAlignment | Qt.TextDontClip, self.text)
	# super(DynamicLabel, self).paint(painter, option, widget)


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
