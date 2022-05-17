from functools import cached_property
from PySide2.QtCore import QRectF, Qt, QTimer
from PySide2.QtGui import QFont
from PySide2.QtWidgets import QGraphicsItem, QGraphicsProxyWidget, QLineEdit
from typing import Union

from LevityDash.lib.Geometry import Geometry
from LevityDash.lib.ui.fonts import compactFont, defaultFont
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import Text
from LevityDash.lib.ui.frontends.PySide.Modules.Handles.MarginHandles import MarginHandles
from LevityDash.lib.ui.frontends.PySide.Modules.Menus import EditableLabelContextMenu, LabelContextMenu
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
from LevityDash.lib.utils.geometry import Alignment, AlignmentFlag, Position, Size
from LevityDash.lib.log import LevityGUILog as guiLog

log = guiLog.getChild(__name__)

__all__ = ['Label', 'EditableLabel']


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
# 				return QFont(defaultFont)
# 			return QFont(compactFont)
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
# 			font = QFont(defaultFont.family(), 100)
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
	_acceptsChildren = False

	__ratioFontSize = 100
	_lineBreaking: bool
	marginHandles: MarginHandles

	def __init__(self, parent: Union['Panel', 'LevityScene'],
		text: str = "",
		alignment: Alignment = None,
		filters: list[str] = None,
		font: QFont = None,
		lineBreaking: bool = False,
		modifiers: dict = None,
		*args, **kwargs):
		self.lineBreaking = lineBreaking

		if filters is None:
			filters = []

		super().__init__(parent=parent, *args, **kwargs)
		if alignment is None:
			alignment = Alignment(AlignmentFlag.Center)
		self.alignment: Alignment = alignment
		self.marginHandles: MarginHandles = MarginHandles(self)
		self.marginHandles.signals.action.connect(self.textBox.updateTransform)
		self.textBox.setParentItem(self)
		self.text = text
		for f in filters:
			self.textBox.setFilter(f, True)
		self.textBox.modifiers = modifiers
		self.setAcceptDrops(False)

	@cached_property
	def textBox(self):
		box = Text(self)
		box.setParentItem(self)
		return box

	@property
	def filters(self):
		return self.textBox.enabledFilters

	@filters.setter
	def filters(self, value):
		if isinstance(value, str):
			value = {value}
		if not isinstance(value, set):
			value = set(value)
		self.textBox.enabledFilters = value

	def editMargins(self):
		self.marginHandles.setEnabled(True)
		self.marginHandles.show()
		self.marginHandles.updatePosition(self.rect())

	def dragEnterEvent(self, event):
		if event.mimeData().hasFormat('text/plain'):
			event.accept()

	def shouldShowGrid(self) -> bool:
		return False

	def __repr__(self):
		return f'<{self.__class__.__name__}(text={self.text}, position={Position(self.pos())}, size={Size(self.rect().size())} {f", {self.gridItem}," if self.snapping else ""} zPosition={self.zValue()}>'

	@property
	def state(self):
		state = super(Label, self).state
		if not self.alignment.isDefault():
			state['alignment'] = self.alignment
		if self.filters:
			state['filters'] = list(self.textBox.enabledFilters)
		state['text'] = self.text
		return state

	@state.setter
	def state(self, state):
		self.alignment = state.get('alignment', Alignment.default())
		self.filters = state.get('filters', [])
		self.text = state.get('text', '')

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
		self.textBox.setAlignment(alignment)
		self.update()

	def setFilter(self, filter: str, enabled: bool = True):
		self.textBox.setFilter(filter, enabled)

	@property
	def text(self):
		return self.textBox.text

	@text.setter
	def text(self, value):
		self.textBox.value = value

	def setText(self, text: str):
		self.text = text

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
				return QFont(defaultFont)
			return QFont(compactFont)
		return self.font

	def setRect(self, rect: QRectF):
		super(Label, self).setRect(rect)
		self.textBox.setPos(self.rect().topLeft())
		self.textBox.updateTransform()

	@property
	def modifiers(self):
		return self.textBox.modifiers

	@modifiers.setter
	def modifiers(self, value):
		self.textBox.modifiers = value


class NonInteractiveLabel(Label):
	_movable = False
	_resizable = False
	_locked = True

	def __init__(self, parent: Union['Panel', 'LevityScene'],
		*args, **kwargs):
		super().__init__(parent=parent, *args, **kwargs)
		self.setFlag(QGraphicsItem.ItemIsMovable, False)
		self.setFlag(QGraphicsItem.ItemIsSelectable, False)
		self.setFlag(QGraphicsItem.ItemIsFocusable, False)

	def contextMenuEvent(self, event):
		event.ignore()
		return

	def unlock(self):
		self.setFlag(QGraphicsItem.ItemIsMovable, True)
		self.setFlag(QGraphicsItem.ItemIsSelectable, True)
		self.setFlag(QGraphicsItem.ItemIsFocusable, True)
		self.resizeHandles.setEnabled(True)
		self.resizeHandles.updatePosition(self.rect())

	def lock(self):
		self.setFlag(QGraphicsItem.ItemIsMovable, False)
		self.setFlag(QGraphicsItem.ItemIsSelectable, False)
		self.setFlag(QGraphicsItem.ItemIsFocusable, False)
		self.resizeHandles.setEnabled(False)


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
		self._manualValue = None
		super().__init__(*args, **kwargs)
		self.setFlag(QGraphicsItem.ItemIsSelectable, True)

		self.setAcceptDrops(True)
		self.setAcceptHoverEvents(True)

	@classmethod
	def validate(cls, item: dict) -> bool:
		panelValidation = super(EditableLabel, cls).validate(item)
		return panelValidation and 'text' in item

	def focusInEvent(self, event):
		super(EditableLabel, self).focusInEvent(event)

	def focusOutEvent(self, event):
		super(EditableLabel, self).focusOutEvent(event)

	def dragEnterEvent(self, event):
		if event.mimeData().hasText():
			event.accept()
			self.__text = self.text
			self.text = event.mimeData().text()
		else:
			event.ignore()

	def dragLeaveEvent(self, event):
		self.text = self.__text
		event.accept()

	def dropEvent(self, event):
		self.text = event.mimeData().text()
		event.accept()

	# def hoverLeaveEvent(self, event):
	# 	if self.lineEdit.keyboardGrabber() is self.lineEdit:
	# 		self.doneEditing()

	def cursorPositionChanged(self):
		self.textBox.refresh()

	def textChanged(self, text: str):
		# self.editTimer.start()
		self.textBox.value = text

	def mouseDoubleClickEvent(self, event):
		self.edit()

	def doneEditing(self):
		self.clearFocus()
		self.text = self.text.strip()
		if len(self.text) == 0:
			self._manualValue = False
		else:
			self._manualValue = True

	@property
	def text(self):
		return self.textBox.text

	@text.setter
	def text(self, value):
		self.textBox.value = value

	@cached_property
	def contextMenu(self):
		return EditableLabelContextMenu(self)

	def edit(self):
		self.update()
		self.setFocus(Qt.MouseFocusReason)

	def delete(self):
		super(EditableLabel, self).delete()

	@property
	def state(self):
		state = super(EditableLabel, self).state
		state['type'] = 'text'
		return state


class TitleLabel(Label):

	def __init__(self, *args, **kwargs):
		kwargs['geometry'] = Geometry(surface=self, size=(1, 0.2), position=Position(0, 0), absolute=False, snapping=False)
		super().__init__(*args, **kwargs)
		self.setMovable(False)
		self._manualValue = kwargs.get('text', None)

	def allowDynamicUpdate(self) -> bool:
		return not self._manualValue

	def setManualValue(self, value: str):
		self._manualValue = value
		self.text = value

	@property
	def isEmpty(self) -> bool:
		return False

	@property
	def state(self):
		state = super().state
		if self._manualValue:
			state['manualValue'] = self._manualValue
		return state
