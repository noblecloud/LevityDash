"""Qt Canvas Painter (GPU) backend for the dashboard scene.

`CanvasPainterShim` quacks like the `QPainter` every item's `paint()` receives and forwards the
calls to a `QCanvasPainter` (`PySide6.QtCanvasPainter`, Qt 6.11+). `paintScene` walks a scene in
stacking order and calls each item's own `paint()` with the shim, so display code needs no rewrite.

Everything the shim cannot do exactly is counted in `Report` (`lossy`: approximated, `missing`:
a `QPainter` method the shim lacks).

Import this module only after `available()` (see `__init__`): it needs `PySide6.QtCanvasPainter`.
"""
import time
from collections import Counter
from contextlib import contextmanager
from math import degrees

from shiboken6 import getCppPointer
from PySide6.QtCanvasPainter import (
	QCanvasConicalGradient, QCanvasLinearGradient, QCanvasPainter, QCanvasPath, QCanvasRadialGradient,
)
from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import (
	QBrush, QColor, QFont, QPainterPathStroker, QFontMetricsF, QGradient, QImage, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QTransform,
)
from PySide6.QtWidgets import (
	QAbstractGraphicsShapeItem, QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem, QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsPolygonItem,
	QGraphicsRectItem, QGraphicsSimpleTextItem, QStyleOptionGraphicsItem,
)

__all__ = ['CanvasPainterShim', 'Report', 'paintScene']

_CAP = {
	Qt.PenCapStyle.FlatCap: QCanvasPainter.LineCap.Butt,
	Qt.PenCapStyle.SquareCap: QCanvasPainter.LineCap.Square,
	Qt.PenCapStyle.RoundCap: QCanvasPainter.LineCap.Round,
}
_JOIN = {
	Qt.PenJoinStyle.MiterJoin: QCanvasPainter.LineJoin.Miter,
	Qt.PenJoinStyle.BevelJoin: QCanvasPainter.LineJoin.Bevel,
	Qt.PenJoinStyle.RoundJoin: QCanvasPainter.LineJoin.Round,
	Qt.PenJoinStyle.SvgMiterJoin: QCanvasPainter.LineJoin.Miter,
}
_COMPOSE = {
	QPainter.CompositionMode.CompositionMode_SourceOver: QCanvasPainter.CompositeOperation.SourceOver,
	QPainter.CompositionMode.CompositionMode_SourceAtop: QCanvasPainter.CompositeOperation.SourceAtop,
	QPainter.CompositionMode.CompositionMode_DestinationOut: QCanvasPainter.CompositeOperation.DestinationOut,
}


class Report:
	"""What the shim could not do exactly, and how often."""

	def __init__(self):
		self.lossy = Counter()
		self.missing = Counter()
		self.calls = Counter()
		self.pathElements = 0
		self.pathsConverted = 0
		self.imagesUploaded = 0
		self.convertSeconds = 0.0
		self.pathCacheHits = 0

	def clear(self):
		self.__init__()


class _Device:
	def __init__(self, ratio: float = 1.0):
		self._ratio = ratio

	def devicePixelRatio(self):
		return self._ratio

	devicePixelRatioF = devicePixelRatio

	def width(self):
		return 0

	height = width


class CanvasPainterShim:
	"""The subset of `QPainter` that LevityDash's `paint()` methods use, on a `QCanvasPainter`."""

	def __init__(self, canvas: QCanvasPainter, report: Report = None, ratio: float = 1.0):
		self.canvas = canvas
		self.report = report or Report()
		self._device = _Device(ratio)
		self._pen = QPen(Qt.PenStyle.NoPen)
		self._brush = QBrush(Qt.BrushStyle.NoBrush)
		self._font = QFont()
		self._opacity = 1.0
		self._mode = QPainter.CompositionMode.CompositionMode_SourceOver
		self._stack = []
		#: Device-space clip rectangle (or None) currently in force.
		self._clip = None
		self._world = QTransform()
		#: What the canvas already carried (the view's scale) when the walk began; `setTransform` goes on top of it.
		self.base = QTransform()
		#: Optional dict: converted paths by a cheap fingerprint (experimental; a hit assumes equal fingerprint means equal path).
		self.cache = None
		self._images = {}
		self._seen = set()

	# Section: state

	def save(self):
		self._stack.append((self._pen, self._brush, self._font, self._opacity, self._mode, QTransform(self._world), self._clip))
		self.canvas.save()

	def restore(self):
		if self._stack:
			self._pen, self._brush, self._font, self._opacity, self._mode, self._world, self._clip = self._stack.pop()
		self.canvas.restore()
		self._applyClip()  # the canvas keeps the clip across restore(); put back the one this level had
		self.canvas.setGlobalAlpha(self._opacity)
		self.canvas.setGlobalCompositeOperation(_COMPOSE.get(self._mode, QCanvasPainter.CompositeOperation.SourceOver))

	def begin(self, *_):
		return True

	def end(self):
		return True

	def isActive(self):
		return True

	def device(self):
		return self._device

	def setPen(self, pen):
		if isinstance(pen, QColor):
			pen = QPen(pen)
		elif isinstance(pen, Qt.PenStyle):
			pen = QPen(pen)
		elif isinstance(pen, (Qt.GlobalColor, int)):
			pen = QPen(QColor(pen))
		self._pen = pen

	def pen(self):
		return self._pen

	def setBrush(self, brush):
		if isinstance(brush, (QColor,)):
			brush = QBrush(brush)
		elif isinstance(brush, Qt.BrushStyle):
			brush = QBrush(brush)
		elif isinstance(brush, Qt.GlobalColor):
			brush = QBrush(QColor(brush))
		elif isinstance(brush, QGradient):
			brush = QBrush(brush)
		self._brush = brush

	def brush(self):
		return self._brush

	def setFont(self, font):
		self._font = font
		self.canvas.setFont(font)

	def font(self):
		return self._font

	def fontMetrics(self):
		return QFontMetricsF(self._font)

	def setOpacity(self, value):
		self._opacity = float(value)
		self.canvas.setGlobalAlpha(self._opacity)

	def opacity(self):
		return self._opacity

	def setCompositionMode(self, mode):
		self._mode = mode
		if mode not in _COMPOSE:
			self.report.lossy[f'compositionMode {mode.name}'] += 1
		self.canvas.setGlobalCompositeOperation(_COMPOSE.get(mode, QCanvasPainter.CompositeOperation.SourceOver))

	def compositionMode(self):
		return self._mode

	def setRenderHint(self, *_):
		pass

	def setRenderHints(self, *_):
		pass

	def renderHints(self):
		return QPainter.RenderHint.Antialiasing

	def setBackground(self, *_):
		pass

	def setBackgroundMode(self, *_):
		pass

	def setLayoutDirection(self, *_):
		pass

	# Section: transforms

	def setTransform(self, transform, combine=False):
		self._world = QTransform(self._world) * transform if combine else QTransform(transform) * self.base
		self.canvas.setTransform(self._world)

	setWorldTransform = setTransform

	def transform(self):
		return QTransform(self._world)

	worldTransform = transform

	def resetTransform(self):
		self._world = QTransform()
		self.canvas.resetTransform()

	def translate(self, *args):
		if len(args) == 1:
			dx, dy = args[0].x(), args[0].y()
		else:
			dx, dy = args
		self._world = QTransform().translate(dx, dy) * self._world
		self.canvas.translate(dx, dy)

	def scale(self, sx, sy):
		self._world = QTransform().scale(sx, sy) * self._world
		self.canvas.scale(sx, sy)

	def rotate(self, degrees_):
		from math import radians
		self._world = QTransform().rotate(degrees_) * self._world
		self.canvas.rotate(radians(degrees_))

	def _applyClip(self):
		"""Canvas Painter's clip is a device-space rectangle that `restore()` does not undo, so the shim owns it."""
		c = self.canvas
		c.resetClipping()
		if self._clip is not None:
			t = c.getTransform()
			c.resetTransform()
			c.setClipRect(self._clip)
			c.setTransform(t)

	def _clipTo(self, rect: QRectF, op=Qt.ClipOperation.ReplaceClip):
		mapped = self._world.mapRect(QRectF(rect))
		if op == Qt.ClipOperation.IntersectClip and self._clip is not None:
			mapped = mapped.intersected(self._clip)
		self._clip = mapped
		self._applyClip()

	def setClipPath(self, path, op=Qt.ClipOperation.ReplaceClip):
		self.report.lossy['setClipPath -> clip to bounding rect'] += 1
		self._clipTo(path.boundingRect(), op)

	def setClipRect(self, *args, op=Qt.ClipOperation.ReplaceClip, **_):
		if len(args) > 1 and isinstance(args[-1], Qt.ClipOperation):
			*args, op = args
		self._clipTo(args[0] if len(args) == 1 else QRectF(*args), op)

	def setClipping(self, on):
		if not on:
			self._clip = None
			self._applyClip()

	# Section: paint sources

	def _paintBrush(self, brush: QBrush):
		"""A `QCanvasPainter` fill/stroke style for a `QBrush`, or None when nothing is drawn."""
		style = brush.style()
		if style == Qt.BrushStyle.NoBrush:
			return None
		if style == Qt.BrushStyle.SolidPattern:
			return QColor(brush.color())
		if style in (Qt.BrushStyle.LinearGradientPattern, Qt.BrushStyle.RadialGradientPattern, Qt.BrushStyle.ConicalGradientPattern):
			g = brush.gradient()
			if style == Qt.BrushStyle.LinearGradientPattern:
				cg = QCanvasLinearGradient(g.start(), g.finalStop())
			elif style == Qt.BrushStyle.RadialGradientPattern:
				cg = QCanvasRadialGradient(g.center(), 0.0, g.radius())
				if g.focalPoint() != g.center():
					self.report.lossy['radial gradient focal point ignored'] += 1
			else:
				cg = QCanvasConicalGradient(g.center(), g.angle())
			for stop in g.stops():
				cg.setColorAt(stop[0], stop[1])
			return cg
		self.report.lossy[f'brush style {style.name} (texture or pattern) drawn solid'] += 1
		return QColor(brush.color())

	def _applyStroke(self):
		pen = self._pen
		if pen.style() == Qt.PenStyle.NoPen:
			return False
		stroke = self._paintBrush(pen.brush())
		if stroke is None:
			return False
		c = self.canvas
		c.setStrokeStyle(stroke)
		width = pen.widthF()
		c.setLineWidth(width if width > 0 else 1.0)
		c.setLineCap(_CAP.get(pen.capStyle(), QCanvasPainter.LineCap.Butt))
		c.setLineJoin(_JOIN.get(pen.joinStyle(), QCanvasPainter.LineJoin.Miter))
		c.setMiterLimit(pen.miterLimit())
		if pen.style() not in (Qt.PenStyle.SolidLine, Qt.PenStyle.NoPen):
			self.report.lossy[f'pen style {pen.style().name} on a shape drawn solid'] += 1
		return True

	def _applyFill(self, brush=None):
		fill = self._paintBrush(brush if brush is not None else self._brush)
		if fill is None:
			return False
		self.canvas.setFillStyle(fill)
		return True

	# Section: paths

	def _toCanvasPath(self, path: QPainterPath) -> QCanvasPath:
		"""A `QCanvasPath` with the same outline.

		Qt fills with the non-zero winding rule, so a hole (the inside of a 0 or an 8, a ring) is just
		a contour wound the other way. Canvas Painter instead forces every sub-path to one winding unless
		it is marked as a hole, so the sub-paths are sorted into solid and hole by the sign of their area
		against the largest one.
		"""
		t0 = time.perf_counter()
		key = None
		if self.cache is not None:
			n = path.elementCount()
			b = path.boundingRect()
			step = max(1, n // 12)
			key = (n, b.x(), b.y(), b.width(), b.height(), path.fillRule(),
				tuple((e.x, e.y) for e in map(path.elementAt, range(0, n, step))))
			hit = self.cache.get(key)
			if hit is not None:
				self.report.pathCacheHits += 1
				self.report.convertSeconds += time.perf_counter() - t0
				return hit
		c = QCanvasPath()
		n = path.elementCount()
		self.report.pathsConverted += 1
		self.report.pathElements += n
		E = QPainterPath.ElementType
		elements = [path.elementAt(i) for i in range(n)]
		contours = []  # [first element index, signed area]
		for i, e in enumerate(elements):
			if e.type == E.MoveToElement:
				contours.append([i, 0.0, e.x, e.y, e.x, e.y])  # start index, area, first x/y, previous x/y
			else:
				cur = contours[-1]
				cur[1] += cur[4] * e.y - e.x * cur[5]
				cur[4], cur[5] = e.x, e.y
		for cur in contours:  # close each contour for the area
			cur[1] += cur[4] * cur[3] - cur[2] * cur[5]
		solidSign = 1.0
		if len(contours) > 1:
			biggest = max(contours, key=lambda k: abs(k[1]))
			solidSign = 1.0 if biggest[1] >= 0 else -1.0
		starts = {k[0]: (k[1] * solidSign) < 0 for k in contours}
		i = 0
		while i < n:
			e = elements[i]
			t = e.type
			if t == E.MoveToElement:
				if len(contours) > 1:
					c.beginHoleSubPath() if starts[i] else c.beginSolidSubPath()
				c.moveTo(e.x, e.y)
				i += 1
			elif t == E.LineToElement:
				c.lineTo(e.x, e.y)
				i += 1
			else:  # CurveToElement is followed by two CurveToDataElements
				a = elements[i + 1]
				b = elements[i + 2]
				c.bezierCurveTo(e.x, e.y, a.x, a.y, b.x, b.y)
				i += 3
		self.report.convertSeconds += time.perf_counter() - t0
		if key is not None:
			self.cache[key] = c
		return c

	def _drawCanvasPath(self, cpath: QCanvasPath, fill: bool, stroke: bool, brush=None, evenOdd=False):
		c = self.canvas
		self.report.calls['paths drawn'] += 1
		c.beginPath()
		c.addPath(cpath)
		if fill and self._applyFill(brush):
			c.setFillRule(QCanvasPainter.FillRule.EvenOdd if evenOdd else QCanvasPainter.FillRule.NonZero)
			c.fill()
		if stroke and self._applyStroke():
			c.stroke()

	def _dashed(self) -> bool:
		return self._pen.style() not in (Qt.PenStyle.SolidLine, Qt.PenStyle.NoPen) and self._pen.brush().style() != Qt.BrushStyle.NoBrush

	def _strokeOutline(self, path: QPainterPath) -> QPainterPath:
		"""The dashed stroke of `path` as a filled outline; Canvas Painter has no line dash."""
		stroker = QPainterPathStroker(self._pen)
		if self._pen.widthF() <= 0:
			stroker.setWidth(1.0)
		return stroker.createStroke(path)

	def drawPath(self, path):
		if self._dashed():
			self._drawCanvasPath(self._toCanvasPath(path), True, False, evenOdd=path.fillRule() == Qt.FillRule.OddEvenFill)
			self._drawCanvasPath(self._toCanvasPath(self._strokeOutline(path)), True, False, self._pen.brush())
			self.report.lossy['dashed stroke drawn as filled outline'] += 1
			return
		self._drawCanvasPath(self._toCanvasPath(path), True, True, evenOdd=path.fillRule() == Qt.FillRule.OddEvenFill)

	def fillPath(self, path, brush):
		if not isinstance(brush, QBrush):
			brush = QBrush(brush)
		self._drawCanvasPath(self._toCanvasPath(path), True, False, brush, path.fillRule() == Qt.FillRule.OddEvenFill)

	def strokePath(self, path, pen):
		old = self._pen
		self._pen = pen if isinstance(pen, QPen) else QPen(pen)
		if self._dashed():
			self._drawCanvasPath(self._toCanvasPath(self._strokeOutline(path)), True, False, self._pen.brush())
			self.report.lossy['dashed stroke drawn as filled outline'] += 1
		else:
			self._drawCanvasPath(self._toCanvasPath(path), False, True)
		self._pen = old

	def _shape(self, build, qpath=None):
		if qpath is not None and self._dashed():
			path = QPainterPath()
			qpath(path)
			return self.drawPath(path)
		c = self.canvas
		c.beginPath()
		build(c)
		if self._applyFill():
			c.fill()
		if self._applyStroke():
			c.stroke()

	def drawRect(self, *args):
		r = args[0] if len(args) == 1 else QRectF(*args)
		self._shape(lambda c: c.rect(QRectF(r)), lambda q: q.addRect(QRectF(r)))

	def drawRoundedRect(self, rect, rx, ry=None, mode=None):
		if not isinstance(rect, (QRectF,)):
			rect = QRectF(rect)
		self._shape(lambda c: c.roundRect(rect, rx), lambda q: q.addRoundedRect(rect, rx, rx if ry is None else ry))

	def drawEllipse(self, *args):
		if len(args) == 1:
			r = QRectF(args[0])
		elif len(args) == 2:  # center, rx / ry as numbers
			ctr, rx = args
			r = QRectF(ctr.x() - rx, ctr.y() - rx, 2 * rx, 2 * rx)
		elif len(args) == 3:
			ctr, rx, ry = args
			r = QRectF(ctr.x() - rx, ctr.y() - ry, 2 * rx, 2 * ry)
		else:
			r = QRectF(*args)
		self._shape(lambda c: c.ellipse(r), lambda q: q.addEllipse(r))

	def drawLine(self, *args):
		if len(args) == 1:
			ln = args[0]
			p1, p2 = ln.p1(), ln.p2()
		elif len(args) == 2:
			p1, p2 = args
		else:
			p1, p2 = QPointF(args[0], args[1]), QPointF(args[2], args[3])

		if self._dashed():
			path = QPainterPath(QPointF(p1))
			path.lineTo(QPointF(p2))
			return self.drawPath(path)

		def build(c):
			c.moveTo(p1)
			c.lineTo(p2)
		c = self.canvas
		c.beginPath()
		build(c)
		if self._applyStroke():
			c.stroke()

	def drawPolygon(self, poly, *_):
		pts = list(poly) if not isinstance(poly, QPolygonF) else poly.toList()

		def build(c):
			c.moveTo(QPointF(pts[0]))
			for p in pts[1:]:
				c.lineTo(QPointF(p))
			c.closePath()

		def qbuild(q):
			q.addPolygon(QPolygonF([QPointF(p) for p in pts]))
			q.closeSubpath()
		self._shape(build, qbuild)

	def drawPolyline(self, poly):
		pts = list(poly) if not isinstance(poly, QPolygonF) else poly.toList()
		if self._dashed():
			path = QPainterPath(QPointF(pts[0]))
			for p in pts[1:]:
				path.lineTo(QPointF(p))
			return self.drawPath(path)
		c = self.canvas
		c.beginPath()
		c.moveTo(QPointF(pts[0]))
		for p in pts[1:]:
			c.lineTo(QPointF(p))
		if self._applyStroke():
			c.stroke()

	def fillRect(self, *args):
		*geometry, brush = args if len(args) in (2, 5) else (*args, None)
		rect = geometry[0] if len(geometry) == 1 else QRectF(*geometry)
		if isinstance(brush, (QColor, Qt.GlobalColor)):
			brush = QBrush(QColor(brush))
		elif brush is not None and not isinstance(brush, QBrush):
			brush = QBrush(brush)
		c = self.canvas
		if self._applyFill(brush):
			c.fillRect(QRectF(rect))

	def eraseRect(self, *args):
		self.report.lossy['eraseRect ignored'] += 1

	# Section: text

	def drawText(self, *args):
		c = self.canvas
		self.report.calls['text drawn'] += 1
		if not self._applyFill(QBrush(self._pen.color())):
			return
		c.setFont(self._font)
		if len(args) == 2 and isinstance(args[0], (QPointF,)):
			c.setTextAlign(QCanvasPainter.TextAlign.Left)
			c.setTextBaseline(QCanvasPainter.TextBaseline.Alphabetic)
			c.fillText(args[1], args[0])
		elif len(args) == 3 and isinstance(args[0], (int, float)):
			c.setTextAlign(QCanvasPainter.TextAlign.Left)
			c.setTextBaseline(QCanvasPainter.TextBaseline.Alphabetic)
			c.fillText(args[2], float(args[0]), float(args[1]))
		elif len(args) >= 3:  # rect, flags, text
			rect, flags, text = QRectF(args[0]), args[1], args[2]
			flags = int(getattr(flags, 'value', flags))
			A = Qt.AlignmentFlag
			if flags & A.AlignRight.value:
				c.setTextAlign(QCanvasPainter.TextAlign.Right)
				x = rect.right()
			elif flags & A.AlignHCenter.value:
				c.setTextAlign(QCanvasPainter.TextAlign.Center)
				x = rect.center().x()
			else:
				c.setTextAlign(QCanvasPainter.TextAlign.Left)
				x = rect.left()
			c.setTextBaseline(QCanvasPainter.TextBaseline.Middle)
			c.fillText(text, x, rect.center().y())
		else:
			self.report.missing['drawText' + repr(tuple(type(a).__name__ for a in args))] += 1

	# Section: images

	def _canvasImage(self, image):
		if isinstance(image, QPixmap):
			image = image.toImage()
		key = image.cacheKey()
		self._seen.add(key)
		ci = self._images.get(key)
		if ci is None:
			ci = self.canvas.addImage(image)
			self._images[key] = ci
			self.report.imagesUploaded += 1
		return ci

	def drawImage(self, target, image, *rest):
		ci = self._canvasImage(image)
		if isinstance(target, QPointF) or hasattr(target, 'x') and not hasattr(target, 'width'):
			self.canvas.drawImage(ci, QPointF(target).x(), QPointF(target).y())
		else:
			target = QRectF(target)
			if rest:
				self.canvas.drawImage(ci, QRectF(rest[0]), target)
			else:
				self.canvas.drawImage(ci, target)

	def drawPixmap(self, target, pixmap, *rest):
		self.drawImage(target, pixmap, *rest)

	def dropUnseenImages(self):
		for key in [k for k in self._images if k not in self._seen]:
			self.canvas.removeImage(self._images.pop(key))
		self._seen.clear()

	def __getattr__(self, name):
		# A `QPainter` method the shim does not have: count it, and do nothing.
		if name.startswith('__'):
			raise AttributeError(name)
		self.report.missing[name] += 1
		return lambda *a, **k: None


# Section: the scene walk

_NATIVE_PAINTERS = (
	QGraphicsPathItem, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPolygonItem,
	QGraphicsSimpleTextItem, QGraphicsPixmapItem,
)


def _pythonPaint(item) -> bool:
	"""True when some Python class in the item's MRO defines `paint` itself."""
	for cls in type(item).__mro__:
		if 'paint' in cls.__dict__:
			return not cls.__module__.startswith('PySide6')
	return False


def _attr(item, name):
	"""The item's real Qt pen or brush: what `QGraphicsRectItem.paint` would use, not a Python property of the same name."""
	if name in ('pen', 'brush') and isinstance(item, QAbstractGraphicsShapeItem):
		return getattr(QAbstractGraphicsShapeItem, name)(item)
	value = getattr(item, name)
	return value() if callable(value) else value


def _nativePaint(item, shim: CanvasPainterShim):
	"""Draw a stock Qt item (path, rect, text, ...) that has no Python `paint`."""
	if isinstance(item, QGraphicsPathItem):
		shim.setPen(_attr(item, "pen"))
		shim.setBrush(_attr(item, "brush"))
		shim.drawPath(item.path())
	elif isinstance(item, QGraphicsRectItem):
		shim.setPen(_attr(item, "pen"))
		shim.setBrush(_attr(item, "brush"))
		shim.drawRect(item.rect())
	elif isinstance(item, QGraphicsEllipseItem):
		shim.setPen(_attr(item, "pen"))
		shim.setBrush(_attr(item, "brush"))
		shim.drawEllipse(item.rect())
	elif isinstance(item, QGraphicsLineItem):
		shim.setPen(_attr(item, "pen"))
		shim.drawLine(item.line())
	elif isinstance(item, QGraphicsPolygonItem):
		shim.setPen(_attr(item, "pen"))
		shim.setBrush(_attr(item, "brush"))
		shim.drawPolygon(item.polygon())
	elif isinstance(item, QGraphicsSimpleTextItem):
		shim.setFont(item.font())
		shim.setPen(QPen(_attr(item, "brush").color()))
		shim.drawText(QPointF(0, QFontMetricsF(item.font()).ascent()), item.text())
	elif isinstance(item, QGraphicsPixmapItem):
		shim.drawPixmap(item.offset(), item.pixmap())


@contextmanager
def nativePaintRedirected():
	"""Make `super().paint(...)` on a stock Qt item class work when the painter is a shim.

	LevityDash's items often subclass `QGraphicsPathItem`/`QGraphicsRectItem` and call the C++
	`paint` through `super()`, which only accepts a real `QPainter`. For the length of the block
	those base methods are replaced by Python ones that draw the item through the shim and hand
	a real `QPainter` on to the original, so normal rendering is unaffected.
	"""
	saved = {}

	def make(cls, original):
		def paint(self, painter, option=None, widget=None):
			if isinstance(painter, CanvasPainterShim):
				_nativePaint(self, painter)
			else:
				original(self, painter, option, widget)
		return paint

	for cls in _NATIVE_PAINTERS:
		saved[cls] = cls.paint
		cls.paint = make(cls, cls.paint)
	try:
		yield
	finally:
		for cls, original in saved.items():
			cls.paint = original


def paintScene(scene, shim: CanvasPainterShim, background: QColor = None, rect: QRectF = None):
	"""Draw every visible item of `scene` through `shim`, in stacking order."""
	with nativePaintRedirected():
		return _paintScene(scene, shim, background, rect)


_CLIPS_CHILDREN = QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape
_CLIPS_SELF = QGraphicsItem.GraphicsItemFlag.ItemClipsToShape


def _clipRect(item, cache: dict):
	"""The scene rectangle `item` is clipped to by itself and its ancestors, or None. Rectangles only: a
	clipping shape is reduced to its bounds (Canvas Painter has no clip path)."""
	key = getCppPointer(item)[0]  # id() would be reused: parentItem() hands back short-lived wrappers
	if key in cache:
		return cache[key]
	parent = item.parentItem()
	rect = _clipRect(parent, cache) if parent is not None else None
	if parent is not None and parent.flags() & _CLIPS_CHILDREN:
		mine = parent.mapRectToScene(parent.shape().boundingRect())
		rect = mine if rect is None else rect.intersected(mine)
	cache[key] = rect
	return rect


def _paintScene(scene, shim: CanvasPainterShim, background: QColor = None, rect: QRectF = None):
	canvas = shim.canvas
	rect = rect or scene.sceneRect()
	if background is not None:
		shim.fillRect(rect, QBrush(background))
	option = QStyleOptionGraphicsItem()
	shim.base = canvas.getTransform()
	painted = 0
	clips = {}
	for item in scene.items(Qt.SortOrder.AscendingOrder):
		if not item.isVisible() or item.flags() & QGraphicsItem.GraphicsItemFlag.ItemHasNoContents:
			continue
		opacity = item.effectiveOpacity()
		if opacity <= 0:
			continue
		canvas.save()
		shim._stack.clear()
		shim._pen = QPen(Qt.PenStyle.NoPen)
		shim._brush = QBrush(Qt.BrushStyle.NoBrush)
		shim._opacity = opacity
		shim._mode = QPainter.CompositionMode.CompositionMode_SourceOver
		shim._world = QTransform(shim.base)
		canvas.setGlobalAlpha(opacity)
		canvas.setGlobalCompositeOperation(QCanvasPainter.CompositeOperation.SourceOver)
		clip = _clipRect(item, clips)
		if item.flags() & _CLIPS_SELF:
			own = item.mapRectToScene(item.shape().boundingRect())
			clip = own if clip is None else clip.intersected(own)
		shim._clip = shim.base.mapRect(clip) if clip is not None else None
		shim._applyClip()
		shim.setTransform(item.sceneTransform())
		if item.graphicsEffect() is not None:
			shim.report.lossy['QGraphicsEffect skipped'] += 1
		try:
			if _pythonPaint(item):
				option.rect = item.boundingRect().toRect()
				item.paint(shim, option, None)
			elif isinstance(item, _NATIVE_PAINTERS):
				_nativePaint(item, shim)
			else:
				continue
			painted += 1
		except Exception as e:  # noqa: BLE001 - the spike reports what breaks instead of stopping
			shim.report.missing[f'{type(item).__name__}.paint raised {type(e).__name__}: {str(e)[:60]}'] += 1
		finally:
			canvas.restore()
	shim._clip = None
	shim._applyClip()
	shim.dropUnseenImages()
	return painted
