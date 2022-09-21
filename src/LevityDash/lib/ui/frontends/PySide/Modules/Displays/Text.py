from asyncio import get_running_loop
from datetime import datetime, timedelta
from enum import Enum
from functools import cached_property
from typing import Any, Callable, List, Optional, TYPE_CHECKING, Union

from dateutil.parser import parser
from PySide2.QtCore import QObject, QPoint, QPointF, QRectF, Signal
from PySide2.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, Qt, QTransform
from PySide2.QtWidgets import QGraphicsItem, QGraphicsPathItem
from qasync import asyncSlot
from rich.repr import rich_repr

import WeatherUnits as wu
from LevityDash.lib.config import userConfig
from LevityDash.lib.plugins import Container
from LevityDash.lib.plugins.observation import TimeHash
from LevityDash.lib.ui import Color
from LevityDash.lib.ui.fonts import defaultFont, FontWeight
from LevityDash.lib.ui.frontends.PySide.utils import addCrosshair, addRect, colorPalette, DebugPaint
from LevityDash.lib.ui.Geometry import Alignment, AlignmentFlag, Geometry, getDPI, Size
from LevityDash.lib.ui.icons import fa as FontAwesome, Icon
from LevityDash.lib.utils.shared import _Panel, ActionPool, ClosestMatchEnumMeta, defer, now, TextFilter

loop = get_running_loop()


class TextItemSignals(QObject):
	changed = Signal()


class ScaleType(str, Enum, metaclass=ClosestMatchEnumMeta):
	fill = 'fill'
	auto = 'auto'
	font = 'font'



@DebugPaint
@rich_repr
class Text(QGraphicsPathItem):

	_actionPool: ActionPool = cached_property(lambda self: ActionPool(self, trace='TextItem'))

	_value: Container
	_parent: _Panel
	_textRect: QRectF = None

	__alignment: Alignment
	__modifier: Optional[dict]
	__defaultIcon = FontAwesome.getIcon('ellipsis', 'solid')
	__defaultText = '-'

	_defaultIconFromParent: Icon | None
	_defaultTextFromParent: str | None

	scaleSelection = min
	minimumDisplayHeight = wu.Length.Millimeter(10)
	baseLabelRelativeHeight = 0.3

	_fixedFontSize: int | float = 0
	_scaleType: ScaleType = ScaleType.auto
	_height: Size.Height | None = None
	_relativeTo: Geometry | None = None
	_height_px_cache: Optional[int] = None
	_color: Color = Color(colorPalette.windowText().color())
	_value: Container | str | int | float | datetime | timedelta | Icon | None = None

	_valueAccessor: Callable[[], Any] | None = None
	_textAccessor: Callable[[], Any] | None = None
	_fontAccessor: Callable[[], QFont] | None = None

	_defaultIcon: Optional[Icon] = None
	_defaultText: Optional[str] = None

	enabledFilters: List[TextFilter]
	__enabledFilters: List[TextFilter]

	if TYPE_CHECKING:
		from LevityDash.lib.ui.frontends.PySide.app import LevityScene
		def scene(self) -> LevityScene: ...

	# Section init
	def __init__(self, parent: _Panel,
		value: Optional[Any] = None,
		alignment: Union[Alignment, AlignmentFlag] = None,
		font: Union[QFont, str] = None,
		filters: Optional[List[str]] = None,
		modifier: Optional[dict] = None,
		color: QColor = None,
		**kwargs
	):
		self._font = None
		self.__enabledFilters = []
		self.__modifier = modifier or {}

		super(Text, self).__init__(parent=None)
		self.setPen(QPen(Qt.NoPen))
		self.signals = TextItemSignals()

		self._parent = parent
		if isinstance(parent, QGraphicsItem):
			self.setParentItem(parent)
		if filters is None:
			filters = list()

		if alignment is None:
			alignment = Alignment(AlignmentFlag.Center)
		elif isinstance(alignment, AlignmentFlag):
			alignment = Alignment(alignment)
		self.__alignment = alignment

		self.setFont(font)
		self.setColor(color)
		self.value = value
		self.setAlignment(alignment)
		self.updateTransform()

		for _filter in filters:
			self.setFilter(_filter, True)

		if hasattr(self.parent, 'signals') and hasattr(self.parent.signals, 'resized'):
			self.parent.signals.resized.connect(self.asyncUpdateTransform)

	def setParentItem(self, parent: QGraphicsItem) -> None:
		if (currentParent := self.parentItem()) is not parent:
			try:
				currentParent._actionPool.discard(self._actionPool)
			except AttributeError:
				pass
		super(Text, self).setParentItem(parent)
		if parent is not None:
			try:
				parent._actionPool.add(self._actionPool)
			except AttributeError:
				pass

	@property
	def is_loading(self) -> bool:
		try:
			return self.parent.is_loading
		except AttributeError:
			return self.topLevelItem().is_loading

	@property
	def state_is_loading(self) -> bool:
		if self.parent is None:
			return self.is_loading or False
		return self.is_loading or self.parent.state_is_loading

	def __rich_repr__(self):
		yield 'text', self.text
		if (textRect := getattr(self, '_textRect', None)) is not None:
			textRect = self.mapRectToScene(textRect)
			yield 'textRect', textRect
		yield 'limitRect', self.limitRect
		yield 'fontSize', self.font().pointSizeF(), 16.0
		yield 'fontWeight', FontWeight.fromQt5(self._font.weight()), FontWeight.Normal
		yield 'font', self.font()
		yield 'transform', (self.transform().m11(), self.transform().m22())

	def setRelativeHeight(self, height: Size.Height, relativeTo: Geometry):
		self._height = height
		self._height_px_cache = None
		self._relativeTo = relativeTo

	def setAbsoluteHeight(self, height: Size.Height):
		self._height = height
		self._relativeTo = None

	@property
	def height(self) -> Size.Height | wu.Length | None:
		return self._height

	@property
	def height_px(self) -> float | None:
		if self._height_px_cache is not None:
			return self._height_px_cache
		height: Size.Height = self._height
		match height:
			case Size.Height(absolute=True):
				self._height_px_cache = height.value
				return height.value
			case Size.Height(relative=True):
				if self._relativeTo is None:
					raise ValueError('RelativeTo is not set')
				return height.toAbsolute(self._relativeTo.absoluteHeight)
			case wu.Length(), _:
				dpi = getDPI(self.surface.scene().view.screen())
				value = float(height.inch)*dpi
				self._height_px_cache = value
				return value
			case _:
				return None

	@property
	def minimumFontSize(self) -> float:
		dpi = self.scene().view.physicalDpiX()
		return max(float(self.minimumDisplayHeight.inch*dpi), 5.0)

	@property
	def suggestedFontPixelSize(self) -> float:
		return max(self.limitRect.height(), 5)

	@property
	def fixedFontSize(self) -> float | int:
		return self._fixedFontSize

	@fixedFontSize.setter
	def fixedFontSize(self, size: float | int):
		self._fixedFontSize = size or 0.0
		if self._fixedFontSize:
			self._font.setPointSizeF(size)
		else:
			self._font.setPointSizeF(self.suggestedFontPixelSize)

	@property
	def fontSize(self) -> float | int:
		return self.fixedFontSize or self.suggestedFontPixelSize

	@property
	def align(self) -> Alignment:
		return self.__alignment

	@property
	def parent(self):
		return self._parent

	def setAlignment(self, alignment: Alignment | AlignmentFlag):
		self.alignment = alignment

	@property
	def alignment(self) -> Alignment:
		return self.__alignment

	@alignment.setter
	def alignment(self, value):
		if isinstance(value, AlignmentFlag):
			if value.isVertical:
				self.__alignment.vertical = value.asVertical
			if value.isHorizontal:
				self.__alignment.horizontal = value.asHorizontal
		else:
			if not isinstance(value, Alignment):
				if isinstance(value, AlignmentFlag):
					value = Alignment(value)
				elif isinstance(value, str):
					value = AlignmentFlag[value]
					value = Alignment(value)
				elif isinstance(value, dict):
					value = Alignment(**value)
				else:
					raise TypeError('Alignment must be of type Alignment or AlignmentFlag')
			self.__alignment = value
		self.updateTransform()

	@property
	def enabledFilters(self) -> List[TextFilter]:
		return self.__enabledFilters

	@enabledFilters.setter
	def enabledFilters(self, value: List[TextFilter]):
		self.__enabledFilters = value

	def setFont(self, font: Union[QFont, str], update: bool = True):
		if font is None:
			font = QFont(defaultFont)
		elif isinstance(font, str):
			font = QFont(font)
		elif isinstance(font, QFont):
			font = QFont(font)
		else:
			font = QFont(font)
		self._font = font
		if self._value is not None and update:
			self.updateTransform()

	def setFixedFontSize(self, size: float | int):
		self.fixedFontSize = size

	@property
	def _font(self):
		return self.__font

	@_font.setter
	def _font(self, value):
		self.__font = value

	def font(self, noIconFont: bool = False) -> QFont:
		font = QFont(self._font)
		font = QFont(icon.font) if (icon := self.icon) is not None and not noIconFont else font
		if g := getattr(self, '_sized', False):
			font.setPointSizeF(g.sharedFontSize(self))
		else:
			font.setPointSize(self.fontSize)
		return font

	def setFontFamily(self, family: str, update: bool=True):
		self._font.setFamily(family)
		if update: self.updateTransform()

	def setFontWeight(self, weight: int, update: bool=True):
		self._font.setWeight(weight)
		if weight != 50:
			self._font: QFont
		if update: self.updateTransform()

	def setFontAccessor(self, accessor: Callable):
		self._fontAccessor = accessor

	@property
	def hasDynamicFontFamily(self) -> bool:
		return self._fontAccessor is not type(self)._fontAccessor

	@property
	def limitRect(self) -> QRectF:
		return self.parent.marginRect

	@asyncSlot()
	async def asyncUpdateTransform(self, *args, **kwargs):
		self.updateTransform(*args, **kwargs)

	# Section Transform
	@defer
	def updateTransform(self, rect: QRectF = None, updateShared: bool = True, updatePath: bool = True, *args):
		transform = QTransform()
		self.resetTransform()
		if updatePath:
			self.__updatePath()

		limitRect = self.limitRect

		if (height := self.height_px) is not None:
			center = limitRect.center()
			limitRect.setHeight(height)
			limitRect.moveCenter(center)

		rect = self._textRect or self.__updatePath()
		# if rect.isValid() and limitRect.isValid():
		self.setTransformOriginPoint(rect.center())
		x, y = self.getTextPosition(limitRect).toTuple()
		if align := getattr(self, '_sized', None):
			sceneY = align.sharedY(self)
			y = self.mapFromScene(QPointF(0, sceneY)).y()
		transform.translate(x, y)
		if not self._fixedFontSize:
			if group := getattr(self, '_sized', None):
				scale = group.sharedSize(self)
			else:
				scale = self.getTextScale(rect, limitRect)
			transform.scale(scale, scale)
		self.setTransform(transform)

	def setScenePosition(self, position: QPointF):
		self.setPos(self.mapFromScene(position))

	def getTextScale(self, textRect: QRectF = None, limitRect: QRectF = None) -> float:
		textRect = textRect or self._textRect or self.__updatePath()
		limitRect = limitRect or self.limitRect

		width = (textRect.width()) or 1
		height = (textRect.height()) or 1

		rotation = abs(self.rotation() or self.parent.rotation())
		if rotation < 45:
			wScale = limitRect.width()/width
			hScale = limitRect.height()/height
		else:
			wScale = limitRect.width()/height
			hScale = limitRect.height()/width
		return round(self.scaleSelection(wScale, hScale), 4)

	def getTextPosition(self, limitRect: QRectF = None) -> QPointF:
		limitRect = limitRect or self.limitRect
		m = QPointF(*self.align.multipliersAlt)
		x, y = limitRect.topLeft().toTuple()
		x += m.x()*limitRect.width()
		y += m.y()*limitRect.height()
		return QPointF(x, y)

	def getTextScenePosition(self, limitRect: QRectF = None) -> QPointF:
		limitRect = self.parent.mapRectToScene(limitRect or self.limitRect)
		m = QPointF(*self.align.multipliersAlt)
		x, y = limitRect.topLeft().toTuple()
		x += m.x()*limitRect.width()
		y += m.y()*limitRect.height()
		return QPointF(x, y)

	def getRelativeTextPosition(self, item: QGraphicsItem, limitRect: QRectF = None) -> QPointF:
		pos = self.getTextPosition(limitRect)
		return self.mapToItem(item, pos)

	def refresh(self):
		self.updateTransform()
		value = getattr(self.value, 'value', self.value)
		if isinstance(value, wu.Time) and userConfig.getOrSet('Display', 'liveUpdateTimedeltas', True, userConfig.getboolean):
			refreshTask = getattr(self, 'refreshTask', None)
			if refreshTask is not None:
				refreshTask.cancel()
			# TODO: change this to properly use abs once WeatherUnits has it implemented
			if wu.Time.Minute(abs(value.minute)) < wu.Time.Minute(1):
				self.refreshTask = loop.call_later(1, self.refresh)
			elif wu.Time.Hour(abs(value.hour)) < wu.Time.Hour(1):
				self.refreshTask = loop.call_later(60, self.refresh)

	def _debug_paint(self, painter: QPainter, option, widget):
		size = 2.5
		addCrosshair(painter, size=size, pos=QPoint(0, 0), color=self._debug_paint_color)
		# if (tr := getattr(self, '_textRect', None)) is not None:
		# 	addRect(painter, tr)
		if (fmt_rect := getattr(self, 'fmt_rect_hint', None)) is not None:
			addRect(painter, fmt_rect)
		self._normal_paint(painter, option, widget)

	@property
	def physicalDisplaySize(self) -> tuple[wu.Length.Centimeter, wu.Length.Centimeter]:
		window = self.scene().views()[0]
		# t = self.worldTransform()
		rect = self.path().boundingRect()
		physicalHeight = wu.Length.Inch(rect.height()/window.physicalDpiY()).cm
		physicalWidth = wu.Length.Inch(rect.width()/window.physicalDpiX()).cm
		return physicalWidth, physicalHeight

	def setColor(self, value: Color):
		if value is None:
			value = Color(colorPalette.windowText().color())
		self._color = value
		brush = QBrush(value.QColor)
		self.setBrush(brush)

	@property
	def color(self) -> Color:
		return self._color

	@color.setter
	def color(self, value):
		self.setColor(value)

	def estimateTextSize(self, font: QFont | float | int) -> tuple[float, float]:
		"""
		Estimates the height and width of a string provided a font
		:rtype: float, float
		:param font:
		:return: height and width of text
		"""
		if isinstance(font, (float, int)):
			font = QFont(self.font())
			font.setPointSizeF(font)
		p = QPainterPath()
		p.addText(QPoint(0, 0), font, self.text)
		rect = p.boundingRect()
		return rect.width(), rect.height()

	def setFilter(self, filter: str, value: bool = None):
		rawString = str(self.text)
		if value is None:
			value = not filter in self.enabledFilters
		if value:
			self.enabledFilters.add(filter)
		else:
			self.enabledFilters.discard(filter)
		# if rawString == self.text:
		# 	self.enabledFilters.discard(filter)
		# 	self.log.warning(f'Filter {filter[1:]} is not applicable to "{rawString}"')
		self.__updatePath()

	@property
	def modifiers(self):
		return self.__modifier

	@modifiers.setter
	def modifiers(self, value):
		if value is None:
			self.__modifier.clear()
			return
		self.__modifier = value

	def setTextAccessor(self, accessor: Callable[[], Any] | None):
		self._textAccessor = accessor
		self.updateText()

	@property
	def hasDynamicText(self) -> bool:
		return self._textAccessor is not None

	@cached_property
	def _defaultIconFromParent(self) -> Icon | None:
		return getattr(self.parentItem(), 'defaultIcon', None)

	@cached_property
	def _defaultTextFromParent(self) -> str | None:
		return getattr(self.parentItem(), 'defaultText', None)

	@property
	def default(self) -> str | Icon:
		return (self._defaultTextFromParent or
		        self._defaultIconFromParent or
		        self._defaultText or
		        self._defaultIcon or
		        self.__defaultText or
		        self.__defaultIcon)

	def advance(self, phase:int) -> None:
		super().advance(phase)
		print('advance', phase)

	@property
	def text(self) -> str | None:
		text = str(self.value) if (func := self._textAccessor) is None else func()
		if text is None:
			return None
		for filterFunc in self.enabledFilters:
			text = filterFunc(text)
		return text

	@text.setter
	def text(self, value):
		self.value = value

	@property
	def value(self) -> Container | str | int | float | datetime | timedelta | Icon | None:
		if self._valueAccessor is not None:
			return self._valueAccessor()
		if self._value is None:
			return self.default
		if isinstance(self._value, (str, int, float, datetime, timedelta, Icon)):
			value = self._value
		else:
			value = self._value.value
			if self.__modifier:
				# if self.__modifier['type'] == 'attribute' and hasattr(value, f'@{self.__modifier["key"]}'):
				# 	value = getattr(value, f'@{self.__modifier["key"]}')
				if time := self.__modifier.get('atTime', None):
					value = value.source.source[value.key]
					if time == 'today':
						time = now()
						time = time.replace(hour=0, minute=0, second=0, microsecond=0)
					elif time == 'tomorrow':
						time = now()
						time = time.replace(hour=0, minute=0, second=0, microsecond=0)
						time += timedelta(days=1)
					elif time == 'yesterday':
						time = now()
						time = time.replace(hour=0, minute=0, second=0, microsecond=0)
						time -= timedelta(days=1)
					else:
						time = parser.parse(time)
					value = value.getFromTime(time, timehash=TimeHash.Minutely)

		return value

	@value.setter
	def value(self, value):
		if str(value) != self.text:
			self._value = value
			self.updateTransform()

	@property
	def icon(self) -> None | Icon:
		value = self.value
		value = subValue if (subValue := getattr(value, 'value', None)) is not None else value
		if value is None and self.text is None and self._defaultText is None:
			return self._defaultIcon or self.__defaultIcon
		return icon if isinstance(icon := value, Icon) and self._textAccessor is None else None

	@property
	def isIcon(self) -> bool:
		value = self.icon
		return value is not self.__defaultIcon and isinstance(value, Icon)

	def setValueAccessor(self, accessor: Callable[[], Any] | None):
		self._valueAccessor = accessor
		self.updateTransform()

	@property
	def hasDynamicValue(self) -> bool:
		return self._valueAccessor is not None

	@property
	def textScaleType(self) -> ScaleType:
		return self._scaleType

	@textScaleType.setter
	def textScaleType(self, value: ScaleType):
		if value != self._scaleType:
			self._scaleType = value
			self.updateTransform()

	def setScaleType(self, value: ScaleType):
		self._scaleType = value
		self.updateTransform()

	def __updatePath(self) -> QRectF:
		self.resetTransform()
		font = self.font()
		fm = QFontMetricsF(font)

		if (fmt_hint := getattr(self, '_formatHint', None)) is not None:
			fmt_hint_rect = fm.tightBoundingRect(fmt_hint)
		else:
			fmt_hint_rect = QRectF()

		path = QPainterPath()
		path.setFillRule(Qt.WindingFill)
		text = self.text if self.icon is None else str(self.icon)
		path.addText(QPointF(0, 0), font, text)
		pathSizeHint = QPainterPath(path)

		scaleType = ScaleType.fill if self.isIcon else self._scaleType
		if fm.tightBoundingRect('|').isEmpty():
			scaleType = ScaleType.font

		match scaleType:
			case ScaleType.fill:
				pass
			case ScaleType.auto:
				pathSizeHint.addText(0, 0, self.font(), f'|')
			case ScaleType.font:
				pathSizeHint.moveTo(0, fm.ascent())
				pathSizeHint.lineTo(0, fm.descent())
			case _:
				pass
		r = pathSizeHint.boundingRect()
		if fmt_hint_rect.isValid():
			align = self.alignment
			if AlignmentFlag.Left & align.horizontal:
				fmt_left = fmt_hint_rect.left()
				r_left = r.left()
				if fmt_left > r_left:
					r.setLeft(fmt_left)
				else:
					fmt_hint_rect.setLeft(r_left)
			elif AlignmentFlag.Right & align.horizontal:
				fmt_right = fmt_hint_rect.right()
				r_right = r.right()
				if fmt_right < r_right:
					r.setRight(fmt_right)
				else:
					fmt_hint_rect.setRight(r_right)
			else:
				fmt_hint_rect.moveCenter(r.center())

			if AlignmentFlag.Top & align.vertical:
				fmt_top = fmt_hint_rect.top()
				r_top = r.top()
				if fmt_top < r_top:
					r.setTop(fmt_top)
				else:
					fmt_hint_rect.setTop(r_top)
			elif AlignmentFlag.Bottom & align.vertical:
				fmt_bottom = fmt_hint_rect.bottom()
				r_bottom = r.bottom()
				if fmt_bottom > r_bottom:
					r.setBottom(fmt_bottom)
				else:
					fmt_hint_rect.setBottom(r_bottom)
			else:
				fmt_hint_rect.moveCenter(r.center())
			r = r.united(fmt_hint_rect)
		textCenter = r.center()

		if scaleType is not ScaleType.fill:
			textCenter.setY(-fm.strikeOutPos())

		path.translate(-textCenter)

		translation = self.alignment.translationFromCenter(r).asQPointF()
		path.translate(translation)

		r.moveCenter(path.boundingRect().center())
		rotation = self.rotation() or self.parent.rotation()
		newTextRect = r if not abs(rotation) else QTransform().rotate(rotation).map(pathSizeHint).boundingRect()
		lastTextRect = self._textRect or newTextRect
		if lastTextRect != newTextRect and (sizeGroup := getattr(self, '_sized', None)) is not None:
			sizeGroup.clearSizes()
		self._textRect = newTextRect
		self._sizeHintRect = r
		self._fmt_rect = fmt_hint_rect

		self._path = path
		self.setPath(path)
		return r

	@defer
	def updateText(self):
		self.__updatePath()
		self.updateTransform(updatePath=False)

	def __del__(self):
		if self._actionPool.up is not self._actionPool:
			self._actionPool.up.remove(self._actionPool)


class TextHelper(Text):
	"""
	This class does not have its own stored value, instead it is provided a value by the parent Text item.
	Example: Displaying the parent text item's unit
	"""

	def __init__(self, parent, reference: Text, font: QFont = None, alignment: Alignment = None, enabledFilters: set = None, *args, **kwargs):
		self.reference = reference
		super().__init__(parent, '', font, alignment, enabledFilters, *args, **kwargs)

	# connectSignal(reference.signals.changed, self.refresh)

	@property
	def value(self):
		return getattr(self.reference.value, '@unit', '')

	@value.setter
	def value(self, value):
		pass

	def __dir__(self):
		return set(super().__dir__()) - set(dir(QGraphicsItem))
