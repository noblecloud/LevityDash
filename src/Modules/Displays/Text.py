from functools import cached_property
from PySide2.QtCore import QPoint, QPointF, QRectF
from PySide2.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, Qt, QTransform
from PySide2.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsTextItem, QStyleOptionGraphicsItem
from typing import Any, Optional, Union
from WeatherUnits.length import Centimeter, Millimeter

from src.catagories import ValueWrapper
from src import app, colorPalette, rounded
from src.utils import _Panel, addCrosshair, Alignment, AlignmentFlag, cachedUnless, clearCacheAttr


class Text(QGraphicsPathItem):
	_value: ValueWrapper
	_parent: _Panel
	figure: 'FigureRect'
	__alignment: Alignment
	_scaleSelection = min
	minimumDisplayHeight = Millimeter(10)
	baseLabelRelativeHeight = 0.3

	def __init__(self, parent: _Panel,
	             value: Optional[Any] = None,
	             alignment: Alignment = AlignmentFlag.Center,
	             scalar: float = 1.0,
	             font: Union[QFont, str] = None,
	             color: QColor = None):
		super(Text, self).__init__(parent=None)
		self.__alignment = Alignment(AlignmentFlag.Center)
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
		self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption, True)
		# self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
		# self.document().setDocumentMargin(0)
		font = self.font()
		# font.setPointSizeF(self.limitRect.height())
		self.setFont(font)
		self.screenWidth = 0
		self.updateTransform()
		if hasattr(self.parent, 'signals'):
			self.parent.signals.resized.connect(self.updateTransform)

	# self.setCache

	def updateItem(self):
		pass

	@property
	def minimumFontSize(self) -> float:
		if app.activeWindow() is None:
			return None
		dpi = app.activeWindow().screen().logicalDotsPerInch()
		return float(self.minimumDisplayHeight.inch * dpi)

	@property
	def suggestedFontSize(self) -> float:
		return self.limitRect.height()

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
				value = Alignment(value)
			self.__alignment = value
		self.__updatePath()
		self.updateTransform()

	# @cached_property
	# def textRect(self) -> QRectF:
	# 	self.prepareGeometryChange()
	# 	fm = QFontMetricsF(self.font())
	# 	rect = fm.tightBoundingRect(self.text)
	#
	# 	bounding_rect = QGraphicsPathItem.boundingRect(self)
	# 	m = QPointF(*self.align.multipliersAlt)
	# 	rect.moveTopLeft(QPointF(0, 0))
	# 	t = QTransform()
	# 	t.translate(*((rect.size() - bounding_rect.size()) / 2).toTuple())
	# 	t.translate(-rect.width() * m.x(), -rect.height() * m.y())
	# 	rect.translate(-rect.width() * m.x(), -rect.height() * m.y())
	# 	self.t = t
	# 	return rect

	@cached_property
	def tightTextRect(self) -> QRectF:
		self.prepareGeometryChange()
		fm = QFontMetricsF(self.font())
		rect = fm.tightBoundingRect(self.toPlainText())
		rect.adjust(-1, -1, 1, 1)
		# tRect = fm.tightBoundingRect(self.toPlainText())
		bounding_rect = QGraphicsTextItem.boundingRect(self)
		rect.moveCenter(bounding_rect.topLeft())
		# rect.moveTo(QGraphicsTextItem.boundingRect(self).topLeft())
		return rect

	# def boundingRect(self) -> QRectF:
	# 	return self.textRect

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

	def refresh(self):
		self._font.setPointSizeF(self.suggestedFontSize)
		self.__updatePath()
		self.updateTransform()

	def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Any) -> None:
		# t = self.t
		w = painter.worldTransform()
		scale = min(w.m11(), w.m22())
		w.scale(1 / w.m11(), 1 / w.m22())
		painter.setPen(Qt.NoPen)
		painter.setBrush(self.brush())
		# if self.font().pointSizeF() > self.minimumFontSize * scale:
		# 	scale = self.minimumFontSize / self.font().pointSizeF()
		w.scale(scale, scale)

		painter.setTransform(w)
		# iT = t.inverted()[0]
		self.screenWidth = option.rect.width() * scale
		self.screenHeight = option.rect.height() * scale
		# option.rect = iT.mapRect(option.rect).adjusted(-1, -1, 1, 1)
		# option.exposedRect = iT.mapRect(option.exposedRect).adjusted(-1, -1, 1, 1)
		# pen = QPen(Qt.white)
		# painter.setPen(pen)
		painter.drawPath(self._path)

	# painter.setBrush(Qt.NoBrush)
	# pen = QPen(Qt.red)
	# pen.setCosmetic(True)
	# pen.setWidth(1)
	# painter.setPen(pen)
	# painter.drawRect(option.rect)
	# pen.setColor(Qt.blue)
	# painter.setPen(pen)
	# painter.drawRect(self.boundingRect())
	# painter.drawRect(self.limitRect.adjusted(1, 1, -1, -1))
	# if self.text:
	# 	addCrosshair(painter, color=Qt.green)

	# super(Text, self).paint(painter, option, widget)

	def worldTransform(self) -> QTransform:
		if self.scene():
			return app.activeWindow().transform()
		else:
			return QTransform()

	@property
	def physicalDisplaySize(self) -> tuple[Centimeter, Centimeter]:
		window = self.scene().views()[0]
		physicalHeight = Centimeter(window.physicalDpiY() / 25.4 * window.height())
		physicalWidth = Centimeter(window.physicalDpiX() / 25.4 * window.width())
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
		self.setPen(pen)
		self.setBrush(brush)

	# self.setDefaultTextColor(color)

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

	@property
	def text(self):
		return str(self.value)

	@text.setter
	def text(self, value):
		self.value = value

	@property
	def value(self):
		return self._value

	@value.setter
	def value(self, value):
		if str(value) != self.text:
			self._value = value
			self.__updatePath()
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

		self._path = path
		self.setPath(path)

	def fixExposedRect(self, rect, t, painter):
		return t.inverted()[0].mapRect(t.mapRect(rect).intersected(t.mapRect(painter.window())))


m = (0.0, 0.0)
