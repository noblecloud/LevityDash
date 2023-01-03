from functools import cached_property
from typing import List

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QGraphicsItem, QLineEdit

from LevityDash.lib.stateful import DefaultFalse, DefaultTrue, StateProperty
from LevityDash.lib.ui import Color
from LevityDash.lib.ui.fonts import fontDict as fonts, FontWeight, getFontFamily
from LevityDash.lib.ui.frontends.PySide import qtLogger as guiLog
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays import Text
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import ScaleType, TextFilter
from LevityDash.lib.ui.frontends.PySide.Modules.Handles.MarginHandles import MarginHandles
from LevityDash.lib.ui.frontends.PySide.Modules.Menus import EditableLabelContextMenu, LabelContextMenu
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import MatchAllSizeGroup, SizeGroup
from LevityDash.lib.ui.frontends.PySide.utils import addRect, DebugPaint
from LevityDash.lib.ui.Geometry import Alignment, AlignmentFlag, Geometry, parseSize, Position, Size, Margins
from LevityDash.lib.ui.icons import getIcon, Icon
from LevityDash.lib.utils import clearCacheAttr
from WeatherUnits.length import Length

log = guiLog.getChild(__name__)

__all__ = ['Label', 'EditableLabel', 'TitleLabel']

defaultFont = fonts['default']
compactFont = fonts['compact']
titleFont = fonts['title']


@DebugPaint
class Label(Panel, tag='label'):
	_acceptsChildren = False
	_fontWeight = FontWeight.Normal

	__ratioFontSize = 100
	_lineBreaking: bool
	marginHandles: MarginHandles

	__exclude__ = {..., 'items'}

	_defaultText: str | None = None
	_defaultIcon: Icon | None = None

	def __init_subclass__(cls, **kwargs):
		super().__init_subclass__(**kwargs)
		cls._defaultIcon = kwargs.get('defaultIcon', None)
		cls._defaultText = kwargs.get('defaultText', None)

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.marginHandles: MarginHandles = MarginHandles(self)
		self.marginHandles.signals.action.connect(self.textBox.updateText)
		self.marginHandles.setEnabled(True)
		self.setAcceptDrops(False)
		self.geometry.updateSurface()

	def __rich_repr__(self):
		yield 'textBox', self.textBox
		yield from super().__rich_repr__()

	@cached_property
	def textBox(self) -> Text:
		box = Text(self)
		box.setParentItem(self)
		return box

	@StateProperty(default=[], allowNone=False, dependencies={'geometry', 'text', 'margins'})
	def filters(self) -> List[TextFilter]:
		return self.textBox.enabledFilters

	@filters.setter
	def filters(self, value: List[TextFilter]):
		self.textBox.enabledFilters = value

	@filters.decode
	def filters(self, value: List[str]) -> List[TextFilter]:
		return [TextFilter[f] for f in value]

	@filters.encode
	def filters(value: List[TextFilter]) -> List[str]:
		return [f.name for f in value]

	def editMargins(self, toggle: bool = True):
		if toggle:
			self.parent.clearFocus()
			self.parent.parent.clearFocus()
			self.marginHandles.scene().clearFocus()
			self.marginHandles.setEnabled(True)
			self.marginHandles.setVisible(True)
			self.marginHandles.forceDisplay = True
			self.marginHandles.updatePosition(self.marginRect)
			self.marginHandles.setFocus()
		else:
			self.marginHandles.forceDisplay = False
			self.marginHandles.setEnabled(False)
			self.marginHandles.setVisible(False)

	@StateProperty
	def margins(self) -> Margins:
		pass

	@margins.after
	def margins(self):
		clearCacheAttr(self, 'marginRect')
		if hasattr(self, 'marginHandles'):
			self.textBox.updateTransform(updatePath=False)

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
		type(self).alignment.default(type(self))
		self.update()

	def setFilter(self, filter: str, enabled: bool = True):
		self.textBox.setFilter(filter, enabled)

	@StateProperty(default=..., sortOrder=0, dependencies={'geometry', 'margins'}, repr=True)
	def text(self) -> str:
		return self.textBox.text if not self.hasIcon else ...

	@text.setter
	def text(self, value: str):
		self.textBox.value = value

	@text.condition
	def text(value):
		return bool(value) and value is not ...

	@property
	def defaultText(self) -> str | None:
		return self._defaultText

	@StateProperty(default=None, sortOrder=1, dependencies={'geometry', 'margins'}, repr=True)
	def icon(self) -> Icon | None:
		return self.textBox.icon

	@icon.setter
	def icon(self, value: Icon):
		self.textBox.value = value

	@icon.encode
	def icon(self, value: Icon) -> str:
		return f'{value.iconPack.prefix}:{value.name}' if value is not None else None

	@icon.decode
	def icon(self, value: str) -> Icon:
		return getIcon(value)

	@icon.condition
	def icon(self):
		return not self.textBox.hasDynamicValue

	@property
	def defaultIcon(self) -> Icon | None:
		return self._defaultIcon

	@property
	def hasIcon(self) -> bool:
		return isinstance(self.textBox.value, Icon)

	@StateProperty(allowNone=False, default=Color.text)
	def color(self) -> Color:
		return self.textBox.color

	@color.setter
	def color(self, value: Color):
		self.textBox.setColor(value)

	@color.decode
	def color(self, value: str | dict | QColor) -> Color:
		try:
			return Color(value)
		except ValueError as e:
			raise e

	@StateProperty(key='font', default=defaultFont.family(), repr=True, allowNone=False)
	def fontFamily(self) -> str:
		return self.textBox.font().family()

	@fontFamily.setter
	def fontFamily(self, value: str):
		self.textBox.setFontFamily(value)

	@fontFamily.decode
	def fontFamily(self, value: str) -> str:
		return getFontFamily(value)

	@fontFamily.condition
	def fontFamily(self) -> bool:
		return not self.textBox.isIcon and not self.textBox.hasDynamicFontFamily

	@fontFamily.condition
	def fontFamily(self) -> bool:
		return self.textBox.icon is not None and self.textBox.font().family() != self.textBox.icon.font.family()

	@StateProperty(key='weight', default=FontWeight.Normal, repr=True, allowNone=False)
	def fontWeight(self) -> FontWeight:
		return FontWeight.fromQt(self.textBox.font().weight())

	@fontWeight.setter
	def fontWeight(self, value: FontWeight):
		self.textBox.setFont(
			FontWeight.macOSWeight(
				self.textBox.font(noIconFont=True).family(),
				value
			)
		)

	@fontWeight.decode
	def fontWeight(self, value: str | int | float) -> FontWeight:
		if isinstance(value, float):
			value = int(value)
		return FontWeight[value]

	@fontWeight.encode
	def fontWeight(value: FontWeight) -> str:
		return value.name

	@fontWeight.condition
	def fontWeight(self) -> bool:
		return not self.textBox.isIcon

	def allowDynamicUpdate(self) -> bool:
		return not self.textBox.isIcon

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
		currentRect = self.rect()
		if currentRect != rect:
			super(Label, self).setRect(rect)
			self.textBox.setPos(self.rect().topLeft())
			self.textBox.updateText()

	@StateProperty(key='text-scale-type', default=ScaleType.auto)
	def textScaleType(self) -> ScaleType:
		return self.textBox.textScaleType

	@textScaleType.setter
	def textScaleType(self, value: ScaleType):
		self.textBox.textScaleType = value

	@textScaleType.encode
	def textScaleType(self, value: ScaleType) -> str:
		return value.name

	@textScaleType.decode
	def textScaleType(self, value: str) -> ScaleType:
		return ScaleType[value]

	@StateProperty(default={}, dependencies={'geometry', 'text', 'alignment'})
	def modifiers(self) -> dict:
		return self.textBox.modifiers

	@modifiers.setter
	def modifiers(self, value: dict):
		self.textBox.modifiers = value

	@StateProperty(key='format-hint', default = None)
	def formatHint(self) -> str:
		return getattr(self.textBox, '_formatHint', None)

	@formatHint.setter
	def formatHint(self, value: str):
		self.textBox._formatHint = value

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

	@StateProperty(default=None, dependencies={'geometry', 'text', 'alignment'})
	def matchingGroup(self) -> SizeGroup:
		return getattr(self, '_matchingGroup', None)

	@matchingGroup.setter
	def matchingGroup(self, value: SizeGroup):
		if (g := getattr(self, '_matchingGroup', None)) is not None and g is not value:
			g.removeItem(self.textBox)
		self._matchingGroup = value
		value.addItem(self.textBox)

	@matchingGroup.decode
	def matchingGroup(self, value: str | dict) -> SizeGroup:
		if isinstance(value, str):
			value = {'group': value}
		return self.getAttrGroup(**value)

	@matchingGroup.encode
	def matchingGroup(self, value: SizeGroup) -> str | dict | None:
		if value is None:
			return None
		if (g := self._rawItemState.get('matchingGroup')) is not None:
			return g
		parent = value.parent
		if parent is self.localGroup:
			prefix = 'local'
		elif parent is self.scene().base:
			prefix = 'global'
		elif parent is self.parentLocalGroup:
			prefix = 'parent'
		elif parent is self.getTaggedGroup('group').getAttrGroup(value.key, True if isinstance(value, MatchAllSizeGroup) else False):
			prefix = 'group'
		elif parent in self.getTaggedGroups(value):
			prefix = parent.name
		elif parent in self.getNamedGroups():
			prefix = f'{parent.name}@{parent.parent.name}'
		else:
			raise ValueError(f'invalid group {value}')
		return {'group': f'{prefix}.{value.name}', 'matchAll': value.matchAll}


	# Section .paint
	def _debug_paint(self, painter: QPainter, option, widget):
		# addCrosshair(painter, pos=QPoint(0, 0), color=self._debug_paint_color)
		c = QColor(self._debug_paint_color)
		c.setAlphaF(0.1)
		addRect(painter, self.rect(), fill=c, offset=2)
		addRect(painter, self.marginRect)
		self._normal_paint(painter, option, widget)


class NonInteractiveLabel(Label, tag=...):
	deletable = False
	_movable = False
	_resizable = False
	_locked = True

	__exclude__ = {..., 'geometry', 'locked', 'frozen', 'movable', 'resizable', 'text'}

	__defaults__ = {
		'margins':   ('11%', '11%', '11%', '11%'),
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


class TitleLabel(NonInteractiveLabel, defaultText='-'):
	deletable = False

	__exclude__ = {'geometry', 'locked', 'frozen', 'movable', 'resizable'}
	_manualValue: str | None = None

	__defaults__ = {
		'weight': FontWeight.Light,
		'color': '#eeeeee',
		'font': 'Roboto',
	}

	def __init__(self, *args, **kwargs):
		kwargs['geometry'] = Geometry(surface=self, size=(1, 0.2), position=Position(0, 0), absolute=False, snapping=False)
		super().__init__(*args, **kwargs)
		self.textBox._scaleType = ScaleType.auto

	@StateProperty(default=..., sortOrder=0, dependencies={'geometry', 'margins'}, repr=True)
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
