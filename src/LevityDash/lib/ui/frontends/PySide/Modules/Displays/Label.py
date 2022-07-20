from functools import cached_property

from PySide2.QtCore import QRectF, Qt
from PySide2.QtGui import QFont
from PySide2.QtWidgets import QGraphicsItem, QLineEdit

from ... import qtLogger as guiLog
from .....Geometry import Geometry
from .....fonts import compactFont, defaultFont
from . import Text
from LevityDash.lib.ui.frontends.PySide.Modules.Handles.MarginHandles import MarginHandles
from LevityDash.lib.ui.frontends.PySide.Modules.Menus import EditableLabelContextMenu, LabelContextMenu
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.utils.geometry import Alignment, AlignmentFlag, Position, Size
from LevityDash.lib.utils import clearCacheAttr
from LevityDash.lib.stateful import DefaultTrue, DefaultFalse, DefaultGroup, StateProperty

log = guiLog.getChild(__name__)

__all__ = ['Label', 'EditableLabel']


class Label(Panel, tag='label'):
	_acceptsChildren = False

	__ratioFontSize = 100
	_lineBreaking: bool
	marginHandles: MarginHandles

	__exclude__ = {..., 'items'}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.marginHandles: MarginHandles = MarginHandles(self)
		self.marginHandles.signals.action.connect(self.textBox.updateText)
		self.setAcceptDrops(False)
		self.geometry.updateSurface()

	@cached_property
	def textBox(self):
		box = Text(self)
		box.setParentItem(self)
		return box

	@StateProperty(default=set(), allowNone=False, dependencies={'geometry', 'text', 'margins'})
	def filters(self) -> set[str]:
		return self.textBox.enabledFilters

	@filters.setter
	def filters(self, value):
		self.textBox.enabledFilters = value

	@filters.encode
	def filters(value) -> list:
		match value:
			case str(value):
				value = [value]
			case None:
				value = list
			case set(value) | tuple(value):
				value = list(value)
			case list(value):
				pass
			case _:
				raise TypeError(f'filters must be a string, list, tuple or set, not {type(value)}')
		return value

	def editMargins(self):
		self.parent.clearFocus()
		self.parent.parent.clearFocus()

		self.marginHandles.scene().clearFocus()
		self.marginHandles.setEnabled(True)
		self.marginHandles.show()
		self.marginHandles.updatePosition(self.rect())
		self.marginHandles.setFocus()

	@StateProperty
	def margins(self):
		pass

	@margins.after
	def margins(self):
		clearCacheAttr(self, 'marginRect')
		if hasattr(self, 'marginHandles'):
			self.textBox.updateTransform()

	def dragEnterEvent(self, event):
		if event.mimeData().hasFormat('text/plain'):
			event.accept()

	@cached_property
	def contextMenu(self):
		return LabelContextMenu(self)

	@StateProperty(default=Alignment.default(), dependencies={'geometry', 'text', 'margins'}, allowNone=False)
	def alignment(self) -> Alignment:
		return self.textBox.align

	@alignment.setter
	def alignment(self, value):
		self.textBox.setAlignment(value)

	def setAlignment(self, alignment: AlignmentFlag):
		self.textBox.setAlignment(alignment)
		type(self).alignment.default(self)
		self.update()

	def setFilter(self, filter: str, enabled: bool = True):
		self.textBox.setFilter(filter, enabled)

	@StateProperty(default=DefaultGroup('⋯', '', None), sortOrder=0, dependencies={'geometry', 'margins'}, repr=True)
	def text(self) -> str:
		return self.textBox.text

	@text.setter
	def text(self, value):
		self.textBox.value = value

	@text.condition
	def text(value):
		return bool(value)

	def setText(self, text: str):
		self.text = text

	def height(self):
		return self.rect().height()

	def width(self):
		return self.rect().width()

	@property
	def isEmpty(self):
		return False

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

	@StateProperty(default=None, dependencies={'geometry', 'text', 'alignment'})
	def modifiers(self) -> dict:
		return self.textBox.modifiers

	@modifiers.setter
	def modifiers(self, value: dict):
		self.textBox.modifiers = value


class NonInteractiveLabel(Label, tag=...):
	deletable = False
	_movable = False
	_resizable = False
	_locked = True

	__exclude__ = {..., 'geometry', 'locked', 'frozen', 'movable', 'resizable', 'text'}

	__defaults__ = {
		'margins':   ('10%', '10%', '10%', '10%'),
		'movable':   False,
		'resizable': False,
		'locked':    True
	}

	def __init__(self, parent: 'Panel', *args, **kwargs):
		Label.__init__(self, parent=parent, *args, **kwargs)
		self.locked = DefaultTrue
		self.movable = DefaultFalse
		self.resizable = DefaultFalse
		self.setFlag(QGraphicsItem.ItemIsSelectable, False)
		self.setFlag(QGraphicsItem.ItemIsFocusable, False)
		self.setAcceptedMouseButtons(Qt.NoButton)

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
		self.parent.setFocus()
		self.parent.doneEditing()
		super(HiddenLineEdit, self).focusOutEvent(event)

	def focusInEvent(self, event):
		super(HiddenLineEdit, self).focusInEvent(event)


class EditableLabel(Label, tag='text'):

	def __init__(self, *args, **kwargs):
		self._manualValue = None
		super().__init__(*args, **kwargs)
		self.setFlag(QGraphicsItem.ItemIsSelectable, True)

		self.setAcceptDrops(True)
		self.setAcceptHoverEvents(not True)

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

	def cursorPositionChanged(self):
		self.textBox.refresh()

	def textChanged(self, text: str):
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


class TitleLabel(Label):
	deletable = False

	__exclude__ = {..., 'geometry', 'locked', 'frozen', 'movable', 'resizable', 'text'}

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
