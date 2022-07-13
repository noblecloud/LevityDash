from asyncio import get_running_loop

from datetime import datetime, timedelta

from dateutil.parser import parser
from PySide2.QtCore import QObject, QPoint, QPointF, QRectF, Signal, Slot
from PySide2.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, Qt, QTransform
from PySide2.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsTextItem, QStyleOptionGraphicsItem
from typing import Any, Callable, Optional, Union, TYPE_CHECKING

import WeatherUnits as wu
from LevityDash.lib.config import userConfig

from LevityDash.lib.plugins import Container
from LevityDash.lib.plugins.dispatcher import MultiSourceContainer
from LevityDash.lib.ui.fonts import defaultFont, compactFont, weatherGlyph
from LevityDash.lib.utils.shared import clearCacheAttr, now, Now, strToOrdinal, toOrdinal, _Panel, TextFilter
from LevityDash.lib.utils.geometry import Alignment, AlignmentFlag
from LevityDash.lib.ui.frontends.PySide.utils import colorPalette, addCrosshair, DebugSwitch, DebugPaint
from LevityDash.lib.plugins.observation import TimeHash

loop = get_running_loop()


class TextItemSignals(QObject):
	changed = Signal()


@DebugPaint
class Text(QGraphicsPathItem):
	_value: Container
	_parent: _Panel
	__alignment: Alignment
	__modifier: Optional[dict]
	scaleSelection = min
	minimumDisplayHeight = wu.Length.Millimeter(10)
	baseLabelRelativeHeight = 0.3

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
		self.__modifier = modifier

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
	def suggestedFontPointSize(self):
		return self.suggestedFontPixelSize/self.scene().view.physicalDpiY()

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
		self.prepareGeometryChange()
		clearCacheAttr(self, 'textRect')
		if font is None:
			font = QFont(defaultFont)
		elif isinstance(font, str):
			font = QFont(font)
		elif isinstance(font, QFont):
			font = QFont(font)
		else:
			font = QFont(font)
		if self.minimumFontSize and font.pointSizeF() < self.minimumFontSize:
			font.setPointSizeF(self.minimumFontSize)
		self._font = font
		if self._value is not None:
			self.__updatePath()
			self.updateTransform()

	def font(self):
		return self._font

	@property
	def limitRect(self) -> QRectF:
		return self.parent.marginRect

	@property
	def atFontMinimum(self):
		if self.minimumFontSize:
			return self.suggestedFontPointSize <= self.minimumFontSize
		return False

	def updateTransform(self, rect: QRectF = None, *args):
		transform = QTransform()
		rect = self.boundingRect()

		# For consistency across other text boxes, the a '|' character is added when
		# getting the text height
		fm = QFontMetricsF(self.font())
		fmRect = fm.tightBoundingRect(f'|{self.text}')

		rect.setHeight(fmRect.height())
		pRect = self.limitRect
		m = QPointF(*self.align.multipliersAlt)

		if rect.isValid() and pRect.isValid():
			wScale = pRect.width()/rect.width()
			hScale = pRect.height()/rect.height()
			x, y = pRect.topLeft().toTuple()
			origin = rect.center()
			self.setTransformOriginPoint(origin)
			x += m.x()*pRect.width()
			y += m.y()*pRect.height()
			transform.translate(x, y)
			scale = self.scaleSelection(wScale, hScale)
			transform.scale(scale, scale)
			transform.mapRect(pRect)
			self.setTransform(transform)

	def sceneBoundingRect(self) -> QRectF:
		return self.mapRectToScene(self.transform().mapRect(self.boundingRect()))

	def autoFont(self, size: float):
		if self.atFontMinimum:
			return

	def refresh(self):
		self._font.setPointSizeF(self.suggestedFontPixelSize)
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

	# Section .paint
	def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Any) -> None:
		painter.setRenderHint(QPainter.Antialiasing)
		w = painter.worldTransform()
		scale = min(w.m11(), w.m22())
		w.scale(1/w.m11(), 1/w.m22())
		w.scale(scale, scale)
		painter.setTransform(w)
		super().paint(painter, option, widget)

	def _debug_paint(self, painter, option, widget):
		self._normal_paint(painter, option, widget)
		painter.setOpacity(1)
		addCrosshair(painter, pos=QPoint(0, 0), color=self._debug_paint_color)

	def worldTransform(self) -> QTransform:
		if self.scene():
			return self.deviceTransform(self.scene().views()[0].transform())
		else:
			return self.transform()

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

	def estimateTextSize(self, font: QFont) -> tuple[float, float]:
		"""
		Estimates the height and width of a string provided a font
		:rtype: float, float
		:param font:
		:return: height and width of text
		"""
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
		self.__modifier = value

	@property
	def text(self):
		if self.__customFilterFunction:
			text = self.withoutUnit()
		else:
			text = str(self.value)
		for filter in self.enabledFilters:
			text = self.__filters[filter](text)
		return text

	@text.setter
	def text(self, value):
		self.value = value

	@property
	def value(self):
		if self._value is None:
			return 'NA'
		if isinstance(self._value, (str, int, float, datetime, timedelta)):
			value = self._value
		else:
			value = self._value.value
			if self.__modifier:
				# if self.__modifier['type'] == 'attribute' and hasattr(value, f'@{self.__modifier["key"]}'):
				# 	value = getattr(value, f'@{self.__modifier["key"]}')
				if time := self.__modifier['atTime']:
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

	def __updatePath(self):
		clearCacheAttr(self, 'textRect')

		fm = QFontMetricsF(self.font())
		fontPath = QPainterPath()
		fontPath.addText(0, 0, self.font(), f'|')

		fm.fontPath = fontPath

		path = QPainterPath()
		path.setFillRule(Qt.WindingFill)
		text = self.text
		r = fm.tightBoundingRect(text)
		r.setHeight(fm.fontPath.boundingRect().height())
		path.addText(QPointF(0, 0), self.font(), text)

		textCenter = path.boundingRect().center()

		if self.font().family() != 'Weather Icons':
			textCenter.setY(-fm.strikeOutPos())

		path.translate(-textCenter)

		pRect = path.boundingRect()
		pRect.setBottom(fm.descent())

		translation = self.alignment.translationFromCenter(r).asQPointF()
		path.translate(translation)
		pRect.translate(translation)

		self._textRect = pRect

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
