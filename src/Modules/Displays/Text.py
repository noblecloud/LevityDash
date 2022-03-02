from functools import cached_property
from PySide2.QtCore import QPoint, QPointF, QRectF
from PySide2.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, Qt, QTransform
from PySide2.QtWidgets import QGraphicsItem, QGraphicsTextItem, QStyleOptionGraphicsItem
from typing import Any, Optional, Union

from src.catagories import ValueWrapper
from src import colorPalette, rounded
from src.utils import _Panel, Alignment, clearCacheAttr


class Text(QGraphicsTextItem):
	_value: ValueWrapper
	_parent: _Panel
	figure: 'FigureRect'
	__alignment: Alignment = Alignment.Center
	_scaleSelection = min

	def __init__(self, parent: _Panel,
	             value: Optional[Any] = None,
	             alignment: Alignment = Alignment.Center,
	             scalar: float = 1.0,
	             font: Union[QFont, str] = None,
	             color: QColor = None):
		super(Text, self).__init__(parent=None)
		self._parent = parent
		self._value = value
		self.scalar = scalar
		self.setColor(color)
		self.setFont(font)
		self.updateItem()
		if isinstance(parent, _Panel):
			self.setParentItem(parent)
		self.setPlainText('')
		self.setAlignment(alignment)
		self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, False)
		self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsToShape, False)
		self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption, True)
		# self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
		self.document().setDocumentMargin(0)

	@property
	def align(self):
		return self.__alignment

	def setFontSize(self, size: float) -> None:
		font = self.font()
		font.setPixelSize(size)

	# self.setFont(font)

	@property
	def parent(self):
		return self._parent

	def setAlignment(self, alignment: Alignment):
		if not isinstance(alignment, Alignment):
			alignment = Alignment(alignment)
		self.__alignment = alignment
		self.updateTransform()

	def alignment(self):
		return self.__alignment

	@cached_property
	def textRect(self) -> QRectF:
		self.prepareGeometryChange()
		fm = QFontMetricsF(self.font())
		rect = fm.boundingRect(self.toPlainText())

		bounding_rect = QGraphicsTextItem.boundingRect(self)
		m = QPointF(*self.align.multipliersAlt)
		rect.moveTopLeft(QPointF(0, 0))
		t = QTransform()
		# t.translate(*((rect.size() - bounding_rect.size()) / 2).toTuple())
		t.translate(-rect.width() * m.x(), -rect.height() * m.y())
		rect.translate(-rect.width() * m.x(), -rect.height() * m.y())
		self.t = t
		return rect

	@cached_property
	def tightTextRect(self) -> QRectF:
		self.prepareGeometryChange()
		fm = QFontMetricsF(self.font())
		rect = fm.tightBoundingRect(self.toPlainText())
		# tRect = fm.tightBoundingRect(self.toPlainText())
		bounding_rect = QGraphicsTextItem.boundingRect(self)
		rect.moveCenter(bounding_rect.topLeft())
		# rect.moveTo(QGraphicsTextItem.boundingRect(self).topLeft())
		return rect

	def boundingRect(self) -> QRectF:
		return self.textRect

	def setFont(self, font: Union[QFont, str]):
		self.prepareGeometryChange()
		clearCacheAttr(self, 'textRect')
		if font == None:
			font = QFont(rounded)
		elif isinstance(font, str):
			font = QFont(font, self.height() * .1)
		elif isinstance(font, QFont):
			font = font
		else:
			font = QFont(font)
		super(Text, self).setFont(font)
		self.updateTransform()

	def updateTransform(self):
		transform = QTransform()
		rect = self.textRect
		pRect = self.parent.marginRect
		m = QPointF(*self.align.multipliersAlt)

		if rect.isValid():
			wScale = pRect.width() / rect.width()
			hScale = pRect.height() / rect.height()
			x, y = pRect.topLeft().toTuple()
			origin = rect.center()
			self.setTransformOriginPoint(origin)
			x += m.x() * pRect.width()
			y += m.y() * pRect.height()
			transform.translate(x, y)
			# transform.scale(wScale, hScale)
			self.setTransform(transform)

	def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Any) -> None:
		t = self.t
		w = painter.worldTransform()
		scale = min(w.m11(), w.m22())
		w.scale(1 / w.m11(), 1 / w.m22())
		w.scale(scale, scale)

		painter.setWorldTransform(t * w)
		iT = t.inverted()[0]
		option.rect = iT.mapRect(option.rect)
		option.exposedRect = iT.mapRect(option.exposedRect)
		painter.setPen(Qt.red)
		painter.drawRect(self.boundingRect())

		super(Text, self).paint(painter, option, widget)

	def setColor(self, value):
		if value is None:
			color = colorPalette.windowText().color()
		elif isinstance(value, str) and value.startswith('#'):
			value = QColor(value)
		elif isinstance(value, QColor):
			color = value
		else:
			color = colorPalette.windowText().color()
		self.setDefaultTextColor(color)

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

	def updateFontSize(self):
		pass

	def setPlainText(self, text: str) -> None:
		super(Text, self).setPlainText(text)
		clearCacheAttr(self, 'textRect')
		self.updateTransform()

	def setPos(self, *args, **kwargs):
		super(Text, self).setPos(*args, **kwargs)

	def updateItem(self) -> None:
		self.updateFontSize()

	def text(self) -> str:
		return str(self._value)

	@property
	def value(self):
		return self._value

	@value.setter
	def value(self, value):
		if str(value) != self.text():
			self._value = value
			self.setPlainText(self.text())
			self.updateItem()

	def fixExposedRect(self, rect, t, painter):
		return t.inverted()[0].mapRect(t.mapRect(rect).intersected(t.mapRect(painter.window())))


m = (0.0, 0.0)
