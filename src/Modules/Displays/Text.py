import logging

from datetime import datetime, timedelta

from functools import cached_property
from PySide2.QtCore import QObject, QPoint, QPointF, QRectF, Signal, Slot
from PySide2.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, Qt, QTransform
from PySide2.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsTextItem, QStyleOptionGraphicsItem
from typing import Any, Callable, Optional, Union
from WeatherUnits.length import Centimeter, Millimeter

from src.plugins.plugin import Container
from src.plugins.dispatcher import MultiSourceContainer
from src import app, colorPalette, rounded
from src.utils import _Panel, addCrosshair, Alignment, AlignmentFlag, cachedUnless, clearCacheAttr, connectSignal, Size, strToOrdinal, toOrdinal


class TextItemSignals(QObject):
	changed = Signal()


class Text(QGraphicsPathItem):
	log = logging.getLogger(__name__)
	_value: Container
	_parent: _Panel
	figure: 'Figure'
	__alignment: Alignment
	_scaleSelection = min
	minimumDisplayHeight = Millimeter(10)
	baseLabelRelativeHeight = 0.3

	__filters: dict[str, Callable] = {'0Ordinal': toOrdinal, '0Add Ordinal': strToOrdinal, '1Lower': str.lower, '1Upper': str.upper, '2Title': str.title}
	enabledFilters: set[str]

	def __init__(self, parent: _Panel,
	             value: Optional[Any] = None,
	             alignment: Union[Alignment, AlignmentFlag] = None,
	             scalar: float = 1.0,
	             font: Union[QFont, str] = None,
	             filters: Optional[set[str]] = None,
	             color: QColor = None):
		self.__customFilterFunction = None
		self.__enabledFilters = set()

		super(Text, self).__init__(parent=None)
		self.setPen(QPen(Qt.NoPen))
		self.signals = TextItemSignals()

		if filters is None:
			filters = list()

		if alignment is None:
			alignment = Alignment(AlignmentFlag.Center)
		elif isinstance(alignment, AlignmentFlag):
			alignment = Alignment(alignment)
		self.__alignment = alignment
		self._value = None
		self._parent = parent
		self.scalar = scalar
		self.setColor(color)
		self.setFont(font)
		self.value = value
		self.updateItem()
		if isinstance(parent, _Panel):
			self.setParentItem(parent)
		self.setAlignment(alignment)
		self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, False)
		self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsToShape, False)
		# self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption, True)
		# self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
		# self.document().setDocumentMargin(0)
		font = self.font()
		# font.setPointSizeF(self.limitRect.height())
		self.setFont(font)
		self.screenWidth = 0
		self.updateTransform()

		for filter in filters:
			self.setFilter(filter, True)

		if hasattr(self.parent, 'signals') and hasattr(self.parent.signals, 'resized'):
			self.parent.signals.resized.connect(self.updateTransform)

	def setCustomFilterFunction(self, filterFunc: Callable):
		self.__customFilterFunction = filterFunc

	def updateItem(self):
		pass

	@property
	def minimumFontSize(self) -> float:
		if app.activeWindow() is None:
			return None
		dpi = app.activeWindow().screen().logicalDotsPerInch()
		return max(float(self.minimumDisplayHeight.inch*dpi), 5.0)

	@property
	def suggestedFontSize(self) -> float:
		return max(self.limitRect.height(), 5)

	@property
	def align(self):
		return self.__alignment

	@property
	def parent(self):
		return self._parent

	def setAlignment(self, alignment: Alignment):
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
				if isinstance(value, str):
					value = Alignment(value)
				elif isinstance(value, dict):
					value = Alignment(**value)
				else:
					raise TypeError('Alignment must be of type Alignment or AlignmentFlag')
			self.__alignment = value
		self.__updatePath()
		self.updateTransform()

	@property
	def enabledFilters(self):
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
		if font == None:
			font = QFont(rounded)
		elif isinstance(font, str):
			font = QFont(font)
		elif isinstance(font, QFont):
			font = font
		else:
			font = QFont(font)
		if self.minimumFontSize and font.pointSizeF() < self.minimumFontSize:
			font.setPointSizeF(self.minimumFontSize)
		self._font = font
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
			return self.font().pointSizeF() <= self.minimumFontSize
		return False

	def updateTransform(self, *args):
		transform = QTransform()
		rect = self.boundingRect()
		pRect = self.limitRect
		m = QPointF(*self.align.multipliersAlt)

		if rect.isValid() and pRect.isValid():
			wScale = pRect.width() / rect.width()
			hScale = pRect.height() / rect.height()
			x, y = pRect.topLeft().toTuple()
			origin = rect.center()
			self.setTransformOriginPoint(origin)
			x += m.x() * pRect.width()
			# x += m.x() * rect.width()
			y += m.y() * pRect.height()
			# y -= m.y() * rect.height()
			transform.translate(x, y)
			scale = self._scaleSelection(wScale, hScale)
			# if abs(scale - 1) > 0.1 and not self.atFontMinimum:
			# 	font = self.font()
			# 	font.setPointSizeF(font.pointSizeF() * scale)
			# 	self._font = font
			# 	clearCacheAttr(self, 'textRect')
			# 	self.updateTransform()
			transform.scale(scale, scale)
			self.setTransform(transform)

	def sceneBoundingRect(self) -> QRectF:
		return self.mapRectToScene(self.transform().mapRect(self.boundingRect()))

	def refresh(self):
		self._font.setPointSizeF(self.suggestedFontSize)
		self.__updatePath()
		self.updateTransform()

	def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Any) -> None:
		# t = self.t
		w = painter.worldTransform()
		scale = min(w.m11(), w.m22())
		w.scale(1 / w.m11(), 1 / w.m22())
		# if self.font().pointSizeF() > self.minimumFontSize * scale:
		# 	scale = self.minimumFontSize / self.font().pointSizeF()
		w.scale(scale, scale)

		painter.setTransform(w)
		super().paint(painter, option, widget)
		# iT = t.inverted()[0]

	def worldTransform(self) -> QTransform:
		if self.scene():
			return self.deviceTransform(self.scene().views()[0].transform())
		else:
			return self.transform()

	@property
	def physicalDisplaySize(self) -> tuple[Centimeter, Centimeter]:
		window = self.scene().views()[0]
		t = self.worldTransform()
		rect = t.map(self.path()).boundingRect()
		physicalHeight = rect.height()/window.physicalDpiY()*2.54
		physicalWidth = rect.width()/window.physicalDpiX()*2.54
		return Centimeter(physicalWidth), Centimeter(physicalHeight)

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
		print(f'Setting filter: {filter}')
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
			return self._value
		return self._value.value

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
		path = QPainterPath()
		path.addText(QPoint(0, 0), self.font(), self.text)
		r = path.boundingRect()
		c = r.center()
		r.moveCenter(QPointF(0, 0))
		c = c - r.center()
		path.translate(-c)
		path.translate(self.alignment.translationFromCenter(r).asQPointF())

		self._path = path.simplified()
		self.setPath(path)

	def updateText(self):
		self.__updatePath()
		self.updateTransform()

	def withoutUnit(self):
		return getattr(self.value, '@withoutUnit', None) or f'WithOutUnit{self.value}'


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
