"""Dev-only: the hairline guides drawn over the preview while a handle is dragged.

A guide is a line, a polyline (an arc or a circle) or a tag. Lines are one device pixel wide whatever the
zoom, and a tag is drawn at a fixed size, so the guides read the same at any zoom. A guide the drag has
snapped to is *hot*: pink and a little heavier, and its tag says which target it landed on.
"""
from dataclasses import dataclass
from typing import List, Optional, Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem

COLD = '#8fb4ff'
HOT = '#ff4fa3'


@dataclass
class Line:
	points: Sequence[QPointF]
	hot: bool = False
	dashed: bool = False


@dataclass
class Tag:
	text: str
	at: QPointF
	hot: bool = False


class Guides(QGraphicsItem):
	"""Holds the guides of the drag in progress; empty between drags."""

	def __init__(self, parent: QGraphicsItem, z: float):
		super().__init__(parent)
		self.setZValue(z)
		self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
		self.lines: List[Line] = []
		self.tags: List[Tag] = []
		self._bounds = QRectF()
		font = QFont()
		font.setPixelSize(11)
		self._font = font

	def boundingRect(self) -> QRectF:
		return self._bounds

	def show(self, lines: Sequence[Line], tags: Sequence[Tag], bounds: QRectF):
		self.prepareGeometryChange()
		self.lines, self.tags = list(lines), list(tags)
		self._bounds = bounds.adjusted(-400, -400, 400, 400)
		self.setVisible(bool(self.lines or self.tags))
		self.update()

	def clear(self):
		self.prepareGeometryChange()
		self.lines, self.tags = [], []
		self._bounds = QRectF()
		self.setVisible(False)

	def paint(self, painter: QPainter, *args):
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		for line in sorted(self.lines, key=lambda l: l.hot):
			pen = QPen(QColor(HOT if line.hot else COLD), 1.6 if line.hot else 1.0)
			pen.setCosmetic(True)
			if line.dashed:
				pen.setStyle(Qt.PenStyle.DashLine)
			painter.setPen(pen)
			painter.drawPolyline(QPolygonF(list(line.points)))
		world = painter.worldTransform()
		painter.save()
		painter.resetTransform()
		painter.setFont(self._font)
		metrics = QFontMetricsF(self._font)
		for tag in sorted(self.tags, key=lambda t: t.hot):
			colour = QColor(HOT if tag.hot else COLD)
			at = world.map(tag.at)
			box = QRectF(0, 0, metrics.horizontalAdvance(tag.text) + 10, metrics.height() + 4)
			box.moveCenter(at)
			painter.setPen(QPen(colour, 1))
			painter.setBrush(QColor(20, 24, 30, 235))
			painter.drawRoundedRect(box, 4, 4)
			painter.setPen(QColor('#ffffff') if tag.hot else colour)
			painter.drawText(box, Qt.AlignmentFlag.AlignCenter, tag.text)
		painter.restore()


class Wire(QGraphicsItem):
	"""The wireframe and the guideline layers: the gauge's geometry (`_studio_geometry`) drawn over the preview.

	In wireframe mode a veil in the stage colour dims the painted gauge and every element shows as a one pixel
	outline in its own colour; elements that collide draw red. Guideline layers draw with or without the wireframe.
	"""

	def __init__(self, z: float):
		super().__init__()
		self.setZValue(z)
		self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
		self.veil: Optional[QColor] = None
		self.shapes: list = []
		self.guides: list = []
		self.red: set = set()
		self._bounds = QRectF()

	def boundingRect(self) -> QRectF:
		return self._bounds

	def show(self, shapes, red, guides, veil: Optional[QColor], bounds: QRectF):
		self.prepareGeometryChange()
		self.shapes, self.red, self.guides, self.veil = list(shapes), set(red), list(guides), veil
		self._bounds = bounds.adjusted(-40, -40, 40, 40)
		self.setVisible(True)
		self.update()

	def clear(self):
		self.prepareGeometryChange()
		self.shapes, self.guides, self.red, self.veil = [], [], set(), None
		self._bounds = QRectF()
		self.setVisible(False)

	def _pen(self, colour: str, dashed: bool, width: float = 1.0, alpha: int = 255) -> QPen:
		c = QColor(colour)
		c.setAlpha(alpha)
		pen = QPen(c, width)
		pen.setCosmetic(True)
		if dashed:
			pen.setStyle(Qt.PenStyle.DashLine)
		return pen

	def paint(self, painter: QPainter, *args):
		from LevityDash.devtools import _studio_geometry as geometry
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		if self.veil is not None:
			painter.fillRect(self._bounds, self.veil)
		painter.setBrush(Qt.BrushStyle.NoBrush)
		for g in self.guides:
			painter.setPen(self._pen(HOT if g.hot else '#9db4d6', g.dashed and not g.hot, 1.6 if g.hot else 1.0, 255 if g.hot else 120))
			painter.drawPath(g.path)
		for i, s in enumerate(self.shapes):
			red = i in self.red
			painter.setPen(self._pen(geometry.OVERLAP if red else geometry.COLORS.get(s.kind, '#ffffff'), s.dashed, 1.5 if red else 1.0))
			painter.drawPath(s.path)
