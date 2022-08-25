from asyncio import get_running_loop
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional, Union, TYPE_CHECKING

from dateutil.parser import parser
from PySide2.QtCore import QObject, QPoint, QPointF, QRectF, Signal
from PySide2.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, Qt, QTransform
from PySide2.QtWidgets import QGraphicsItem, QGraphicsPathItem

import WeatherUnits as wu
from LevityDash.lib.config import userConfig
from LevityDash.lib.plugins import Container
from LevityDash.lib.plugins.dispatcher import MultiSourceContainer
from LevityDash.lib.ui.fonts import defaultFont
from LevityDash.lib.ui.Geometry import Geometry, Size, AlignmentFlag, Alignment
from LevityDash.lib.ui.icons import IconPack
from LevityDash.lib.utils.shared import now, strToOrdinal, toOrdinal, _Panel, ClosestMatchEnumMeta
from LevityDash.lib.ui.frontends.PySide.utils import colorPalette, addCrosshair, addRect, DebugPaint
from LevityDash.lib.plugins.observation import TimeHash

loop = get_running_loop()


class TextItemSignals(QObject):
	changed = Signal()


class ScaleType(str, Enum, metaclass=ClosestMatchEnumMeta):
	fill = 'fill'
	auto = 'auto'
	font = 'font'


@DebugPaint
class Text(QGraphicsPathItem):
	_value: Container
	_parent: _Panel
	__alignment: Alignment
	__modifier: Optional[dict]
	scaleSelection = min
	minimumDisplayHeight = wu.Length.Millimeter(10)
	baseLabelRelativeHeight = 0.3
	_fixedFontSize: int | float = 0
	_scaleType: ScaleType = ScaleType.auto
	_height: Size.Height | None = None
	_relativeTo: Geometry | None = None
	_height_px_cache: Optional[int] = None

	_valueAccessor: Callable[[], Any] | None = None
	_textAccessor: Callable[[], Any] | None = None

	__filters: dict[str, Callable] = {'0Ordinal': toOrdinal, '0Add Ordinal': strToOrdinal, '1Lower': str.lower, '1Upper': str.upper, '2Title': str.title}
	enabledFilters: set[str]

	if TYPE_CHECKING:
		from LevityDash.lib.ui.frontends.PySide.app import LevityScene
		def scene(self) -> LevityScene: ...

	# Section init
	def __init__(self, parent: _Panel,
		value: Optional[Any] = None,
		alignment: Union[Alignment, AlignmentFlag] = None,
		font: Union[QFont, str] = None,
		filters: Optional[set[str]] = None,
		modifier: Optional[dict] = None,
		color: QColor = None,
		**kwargs
	):
		self._font = None
		self.__customFilterFunction = None
		self.__enabledFilters = set()
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
		self._value = None

		self.setFont(font)
		self.setColor(color)
		self.value = value
		self.setAlignment(alignment)
		self.updateTransform()

		for _filter in filters:
			self.setFilter(_filter, True)

		if hasattr(self.parent, 'signals') and hasattr(self.parent.signals, 'resized'):
			self.parent.signals.resized.connect(self.updateTransform)

	def __rich_repr__(self):
		if (textRect := getattr(self, '_textRect', None)) is not None:
			textRect = self.mapRectToScene(textRect)
			yield 'textRect', textRect
		yield 'limitRect', self.limitRect
		yield 'fontSize', self._font.pointSizeF(), 16.0
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
				dpi = self.surface.scene().view.screen().physicalDotsPerInchY()
				value = float(height.inch)*dpi
				self._height_px_cache = value
				return value
			case _:
				return None

	def setCustomFilterFunction(self, filterFunc: Callable):
		self.__customFilterFunction = filterFunc

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
					value = Alignment(value)
				elif isinstance(value, dict):
					value = Alignment(**value)
				else:
					raise TypeError('Alignment must be of type Alignment or AlignmentFlag')
			self.__alignment = value
		self.__updatePath()
		self.updateTransform()

	@property
	def enabledFilters(self) -> set[str]:
		return self.__enabledFilters

	@enabledFilters.setter
	def enabledFilters(self, value):
		if isinstance(value, str):
			value = {value}
		if not isinstance(value, set):
			value = set(value)
		self.__enabledFilters = value

	def setFont(self, font: Union[QFont, str]):
		if font is None:
			font = QFont(defaultFont)
		elif isinstance(font, str):
			font = QFont(font)
		elif isinstance(font, QFont):
			font = QFont(font)
		else:
			font = QFont(font)
		self._font = font
		if self._value is not None:
			self.__updatePath()
			self.updateTransform()

	def setFixedFontSize(self, size: float | int):
		self.fixedFontSize = size

	def font(self):
		font = QFont(self._font)
		if g := getattr(self, '_sized', False):
			font.setPointSizeF(g.sharedFontSize(self))
		else:
			font.setPointSize(self.fontSize)
		return font

	@property
	def limitRect(self) -> QRectF:
		return self.parent.marginRect

	# Section Transform
	def updateTransform(self, rect: QRectF = None, updateShared: bool = True, *args):
		transform = QTransform()
		self.resetTransform()

		limitRect = self.limitRect

		if (height := self.height_px) is not None:
			center = limitRect.center()
			limitRect.setHeight(height)
			limitRect.moveCenter(center)

		rect = self._textRect
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
		textRect = textRect or self._textRect
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
		return self.scaleSelection(wScale, hScale)

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
		self.__updatePath()
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
		if (tr := getattr(self, '_textRect', None)) is not None:
			addRect(painter, tr)
		self._normal_paint(painter, option, widget)

	@property
	def physicalDisplaySize(self) -> tuple[wu.Length.Centimeter, wu.Length.Centimeter]:
		window = self.scene().views()[0]
		# t = self.worldTransform()
		rect = self.path().boundingRect()
		physicalHeight = wu.Length.Inch(rect.height()/window.physicalDpiY()).cm
		physicalWidth = wu.Length.Inch(rect.width()/window.physicalDpiX()).cm
		return physicalWidth, physicalHeight

	def setColor(self, value):
		if value is None:
			color = colorPalette.windowText().color()
		elif isinstance(value, str) and value.startswith('#'):
			value = QColor(value)
		elif isinstance(value, QColor):
			color = value
		else:
			color = colorPalette.windowText().color()
		pen = QPen(color)
		brush = QBrush(color)
		self.setPen(Qt.NoPen)
		self.setBrush(brush)

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
	def text(self) -> str:
		if self._textAccessor is not None:
			return self._textAccessor()
		if self.__customFilterFunction:
			text = self.withoutUnit()
		else:
			text = str(self.value)
		for filter in self.enabledFilters:
			text = self.__filters[filter](text)
		if text is None:
			return '⋯'
		return text

	@text.setter
	def text(self, value):
		self.value = value

	@property
	def value(self):
		if self._valueAccessor is not None:
			return self._valueAccessor()
		if self._value is None:
			return '⋯'
		if isinstance(self._value, (str, int, float, datetime, timedelta)):
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
			if isinstance(value, MultiSourceContainer):
				self.__customFilterFunction = True
			self._value = value
			self.__updatePath()
			self.updateTransform()
		else:
			self.updateTransform()

	def setValueAccessor(self, accessor: Callable[[], Any] | None):
		self._valueAccessor = accessor
		self.__updatePath()

	def setScaleType(self, value: ScaleType):
		self._scaleType = value
		self.__updatePath()
		self.updateTransform()

	def __updatePath(self):
		self.resetTransform()
		fm = QFontMetricsF(self.font())

		path = QPainterPath()
		path.setFillRule(Qt.WindingFill)
		text = self.text
		path.addText(QPointF(0, 0), self.font(), text)
		pathSizeHint = QPainterPath(path)
		pathSizeHint.addText(QPointF(0, 0), self.font(), text)
		match self._scaleType:
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
		textCenter = r.center()

		if self.font().family() != 'Weather Icons' and self._scaleType is not ScaleType.fill:
			textCenter.setY(-fm.strikeOutPos())

		path.translate(-textCenter)

		translation = self.alignment.translationFromCenter(r).asQPointF()
		path.translate(translation)

		r.moveCenter(path.boundingRect().center())
		rotation = self.rotation() or self.parent.rotation()
		self._textRect = r if not abs(rotation) else QTransform().rotate(rotation).map(pathSizeHint).boundingRect()
		self._sizeHintRect = r

		self._path = path
		self.setPath(path)

	def updateText(self):
		self.__updatePath()
		self.updateTransform()

	def withoutUnit(self, value=None):
		value = value or self.value
		# if self.__modifier:
		# 	if hasattr(value, 'value'):
		# 		value = value.value
		# 	if self.__modifier['type'] == 'attribute' and hasattr(value, self.__modifier['key']):
		# 		value = getattr(value, self.__modifier['key'])
		# 	return str(value.withoutUnit)
		return getattr(value, '@withoutUnit', None) or f'WithOutUnit{value}'


class Icon(Text):
	iconPack: IconPack
	icon: str
	style: Optional[str]

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	@property
	def iconPack(self) -> IconPack | None:
		if self.icon is None:
			return None
		prefix = self.icon.split('-')[0]
		return IconPack[prefix]


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
