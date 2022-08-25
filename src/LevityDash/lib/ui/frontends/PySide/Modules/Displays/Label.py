from functools import cached_property

from PySide2.QtCore import QRectF, Qt
from PySide2.QtGui import QFont, QPainter, QColor
from PySide2.QtWidgets import QGraphicsItem, QLineEdit

from LevityDash.lib.ui.frontends.PySide.utils import addRect, DebugPaint
from WeatherUnits.length import Length
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import SizeGroup
from LevityDash.lib.ui.frontends.PySide import qtLogger as guiLog
from LevityDash.lib.ui.Geometry import Geometry, Size, Position, parseSize, AlignmentFlag, Alignment
from LevityDash.lib.ui.fonts import compactFont, defaultFont
from LevityDash.lib.ui.frontends.PySide.Modules.Displays import Text
from LevityDash.lib.ui.frontends.PySide.Modules.Handles.MarginHandles import MarginHandles
from LevityDash.lib.ui.frontends.PySide.Modules.Menus import EditableLabelContextMenu, LabelContextMenu
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import ScaleType
from LevityDash.lib.utils import clearCacheAttr
from LevityDash.lib.stateful import DefaultTrue, DefaultFalse, DefaultGroup, StateProperty
from LevityDash.lib.ui.icons import IconPack

log = guiLog.getChild(__name__)

__all__ = ['Label', 'EditableLabel', 'TitleLabel']


@DebugPaint(color='#00ffaa')
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
		self.marginHandles.setEnabled(False)
		self.setAcceptDrops(False)
		self.geometry.updateSurface()

	def __rich_repr__(self):
		yield 'textBox', self.textBox
		yield from super().__rich_repr__()

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
		self.marginHandles.setVisible(True)
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
		return self.textBox.text if not self.hasIcon else None

	@text.setter
	def text(self, value):
		self.textBox.value = value

	@text.condition
	def text(value):
		return bool(value)

	@StateProperty(default=None, sortOrder=1, dependencies={'geometry', 'margins'}, repr=True)
	def icon(self) -> str | None:
		return getattr(self, '_icon', None)

	@icon.setter
	def icon(self, value):
		self._icon = value
		if value.startswith('icon:'):
			value = value[5:]
		iconPack, name = value.split('-', 1)
		iconPack = IconPack[iconPack]
		font = iconPack.getFont()
		self.textBox.setFont(font)
		value = iconPack.getIconChar(name, '')
		self.textBox.value = value

	@property
	def hasIcon(self) -> bool:
		return self.icon is not None

	def allowDynamicUpdate(self) -> bool:
		return self.icon is None

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
		self.textBox.updateText()

	@StateProperty(default={}, dependencies={'geometry', 'text', 'alignment'})
	def modifiers(self) -> dict:
		return self.textBox.modifiers

	@modifiers.setter
	def modifiers(self, value: dict):
		self.textBox.modifiers = value

	@StateProperty(default=None, dependencies={'geometry', 'text', 'alignment'})
	def textHeight(self) -> Size.Height | Length | None:
		return self.textBox.height

	@textHeight.setter
	def textHeight(self, value: Size.Height):
		if value.relative:
			self.textBox.setRelativeHeight(value, self.localGroup.geometry)
		else:
			self.textBox.setAbsoluteHeight(value)
		self.textBox.updateTransform()

	@textHeight.decode
	def textHeight(self, value: str | int | float) -> Size.Height | Length | None:
		return parseSize(value, None)

	@textHeight.encode
	def textHeight(self, value: Size.Height) -> str:
		if value is not None:
			return str(value)

	@StateProperty(default={}, dependencies={'geometry', 'text', 'alignment'})
	def matchingGroup(self) -> dict:
		return getattr(self, '_matchingGroup', {})

	@matchingGroup.setter
	def matchingGroup(self, value: dict):
		self._matchingGroup = value

	@matchingGroup.decode
	def matchingGroup(value: str | dict) -> dict:
		if isinstance(value, str):
			return {'group': value}
		return value

	@matchingGroup.encode
	def matchingGroup(value: SizeGroup | dict) -> str | dict:
		match value:
			case {'group': group} | str(group):
				return group
		return value

	@matchingGroup.after
	def matchingGroup(self):
		v = self._matchingGroup or {}
		group = v.get('group', None) if isinstance(v, dict) else v
		matchAll = v.get('matchAll', False)
		match group.split('.') if isinstance(group, str) else group:
			case 'local', str(key):
				group = self.localGroup.getAttrGroup(key, matchAll)
			case 'global', str(key):
				group = self.scene().base.getAttrGroup(key, matchAll)
			case 'parent', str(key):
				group = (self.parentLocalGroup or self.localGroup).getAttrGroup(key, matchAll)
			case 'group', str(key):
				group = self.getTaggedGroup('group').getAttrGroup(key, matchAll)
			case str(tag), str(key):
				group = self.getTaggedGroup(tag).getAttrGroup(key, matchAll)
			case [str(named)] if '@' in named:
				key, group = named.split('@')
				group = self.getNamedGroup(group).getAttrGroup(key, matchAll)
			case SizeGroup():
				pass
			case _:
				raise ValueError(f'invalid group {group}')
		if (g := getattr(self, '_matchingGroupGroup', None)) is group:
			g.removeItem(self.textBox)
		group.addItem(self.textBox)
		self._matchingGroupGroup = group

	# def paint(self, painter: QPainter, option, widget):

	# Section .paint
	def _debug_paint(self, painter: QPainter, option, widget):
		# addCrosshair(painter, pos=QPoint(0, 0), color=self._debug_paint_color)
		c = QColor(self._debug_paint_color)
		c.setAlphaF(0.1)
		addRect(painter, self.rect(), fill=c, offset=2)
		self._normal_paint(painter, option, widget)


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
	def validate(cls, item: dict, context=None) -> bool:
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


class TitleLabel(NonInteractiveLabel):
	deletable = False

	__exclude__ = {'geometry', 'locked', 'frozen', 'movable', 'resizable'}
	_manualValue: str | None = None

	def __init__(self, *args, **kwargs):
		kwargs['geometry'] = Geometry(surface=self, size=(1, 0.2), position=Position(0, 0), absolute=False, snapping=False)
		super().__init__(*args, **kwargs)
		self.textBox._scaleType = ScaleType.auto

	@StateProperty(default=DefaultGroup('⋯', '', None), sortOrder=0, dependencies={'geometry', 'margins'}, repr=True)
	def text(self) -> str:
		pass

	@text.setter
	def text(self, value: str):
		self._manualValue = value
		Label.text.fset(self, value)

	@text.condition
	def text(self):
		return not self.allowDynamicUpdate()

	def allowDynamicUpdate(self) -> bool:
		return super().allowDynamicUpdate() and not self._manualValue

	@property
	def isEmpty(self) -> bool:
		return False
