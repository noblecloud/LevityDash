"""Skia backend for the dashboard scene.

`SkiaPainterShim` quacks like the `QPainter` every item's `paint()` receives and forwards the calls to a
`skia.Canvas` (`skia-python`, BSD). `paintScene` walks a scene in stacking order and calls each item's
own `paint()` with the shim, so display code needs no rewrite. Unlike Qt Canvas Painter, Skia has
everything QPainter has and more: clip paths, dashes, every composition mode, and real Gaussian blur,
which is what drop shadows (`QGraphicsDropShadowEffect`), `QGraphicsBlurEffect` and glows use here.

The canvas can be a GPU surface (`layer.SkiaSceneLayer`, OpenGL) or a CPU raster one
(`devtools/skia_dashboard.py` uses both).

Everything the shim cannot do exactly is counted in `Report`.
"""
import time
from collections import Counter
from contextlib import contextmanager

import numpy as np
import skia
from shiboken6 import getCppPointer
from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import (
	QBrush, QColor, QFont, QFontMetricsF, QGradient, QImage, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QTransform,
)
from PySide6.QtWidgets import (
	QAbstractGraphicsShapeItem, QGraphicsBlurEffect, QGraphicsDropShadowEffect, QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem,
	QGraphicsOpacityEffect, QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsPolygonItem, QGraphicsRectItem, QGraphicsSimpleTextItem,
	QStyleOptionGraphicsItem,
)

__all__ = ['SkiaPainterShim', 'Report', 'paintScene', 'toSkMatrix']

_CAP = {
	Qt.PenCapStyle.FlatCap: skia.Paint.kButt_Cap,
	Qt.PenCapStyle.SquareCap: skia.Paint.kSquare_Cap,
	Qt.PenCapStyle.RoundCap: skia.Paint.kRound_Cap,
}
_JOIN = {
	Qt.PenJoinStyle.MiterJoin: skia.Paint.kMiter_Join,
	Qt.PenJoinStyle.BevelJoin: skia.Paint.kBevel_Join,
	Qt.PenJoinStyle.RoundJoin: skia.Paint.kRound_Join,
	Qt.PenJoinStyle.SvgMiterJoin: skia.Paint.kMiter_Join,
}
_M = QPainter.CompositionMode
_BLEND = {
	_M.CompositionMode_SourceOver: skia.BlendMode.kSrcOver,
	_M.CompositionMode_DestinationOver: skia.BlendMode.kDstOver,
	_M.CompositionMode_Clear: skia.BlendMode.kClear,
	_M.CompositionMode_Source: skia.BlendMode.kSrc,
	_M.CompositionMode_Destination: skia.BlendMode.kDst,
	_M.CompositionMode_SourceIn: skia.BlendMode.kSrcIn,
	_M.CompositionMode_DestinationIn: skia.BlendMode.kDstIn,
	_M.CompositionMode_SourceOut: skia.BlendMode.kSrcOut,
	_M.CompositionMode_DestinationOut: skia.BlendMode.kDstOut,
	_M.CompositionMode_SourceAtop: skia.BlendMode.kSrcATop,
	_M.CompositionMode_DestinationAtop: skia.BlendMode.kDstATop,
	_M.CompositionMode_Xor: skia.BlendMode.kXor,
	_M.CompositionMode_Plus: skia.BlendMode.kPlus,
	_M.CompositionMode_Multiply: skia.BlendMode.kMultiply,
	_M.CompositionMode_Screen: skia.BlendMode.kScreen,
	_M.CompositionMode_Overlay: skia.BlendMode.kOverlay,
	_M.CompositionMode_Darken: skia.BlendMode.kDarken,
	_M.CompositionMode_Lighten: skia.BlendMode.kLighten,
	_M.CompositionMode_ColorDodge: skia.BlendMode.kColorDodge,
	_M.CompositionMode_ColorBurn: skia.BlendMode.kColorBurn,
	_M.CompositionMode_HardLight: skia.BlendMode.kHardLight,
	_M.CompositionMode_SoftLight: skia.BlendMode.kSoftLight,
	_M.CompositionMode_Difference: skia.BlendMode.kDifference,
	_M.CompositionMode_Exclusion: skia.BlendMode.kExclusion,
}


class Report:
	"""What the shim could not do exactly, and how often."""

	def __init__(self):
		self.lossy = Counter()
		self.missing = Counter()
		self.calls = Counter()
		self.pathsConverted = 0
		self.pathCacheHits = 0
		self.imagesUploaded = 0
		self.convertSeconds = 0.0

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


def toSkMatrix(t: QTransform) -> skia.Matrix:
	"""Qt maps x' = m11 x + m21 y + dx; Skia's MakeAll takes (scaleX, skewX, transX, skewY, scaleY, transY, persp...)."""
	return skia.Matrix.MakeAll(t.m11(), t.m21(), t.dx(), t.m12(), t.m22(), t.dy(), t.m13(), t.m23(), t.m33())


def _color4f(c: QColor, alpha: float = 1.0) -> skia.Color4f:
	return skia.Color4f(c.redF(), c.greenF(), c.blueF(), c.alphaF() * alpha)


def _rect(r) -> skia.Rect:
	r = QRectF(r)
	return skia.Rect.MakeXYWH(r.x(), r.y(), r.width(), r.height())


class SkiaPainterShim:
	"""The subset of `QPainter` that LevityDash's `paint()` methods use, on a `skia.Canvas`."""

	def __init__(self, canvas: skia.Canvas, report: Report = None, ratio: float = 1.0):
		self.canvas = canvas
		self.report = report or Report()
		self._device = _Device(ratio)
		self._pen = QPen(Qt.PenStyle.NoPen)
		self._brush = QBrush(Qt.BrushStyle.NoBrush)
		self._font = QFont()
		self._opacity = 1.0
		self._mode = _M.CompositionMode_SourceOver
		self._stack = []
		self._world = QTransform()
		#: The transform the canvas carried when the walk began (view scale); `setTransform` goes on top of it.
		self.base = QTransform()
		#: Optional dict shared across frames: converted paths, keyed by a fingerprint and confirmed by `==`.
		self.cache = None
		self._images = {}
		#: Draw `glow:` halos as one blurred stroke (`glowPath`) instead of the stacked strokes.
		self.blurGlow = True

	# Section: state

	def save(self):
		self._stack.append((self._pen, self._brush, self._font, self._opacity, self._mode, QTransform(self._world)))
		self.canvas.save()

	def restore(self):
		if self._stack:
			self._pen, self._brush, self._font, self._opacity, self._mode, self._world = self._stack.pop()
		self.canvas.restore()

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
		if isinstance(brush, (QColor, Qt.BrushStyle, QGradient)):
			brush = QBrush(brush)
		elif isinstance(brush, Qt.GlobalColor):
			brush = QBrush(QColor(brush))
		self._brush = brush

	def brush(self):
		return self._brush

	def setFont(self, font):
		self._font = QFont(font)

	def font(self):
		return self._font

	def fontMetrics(self):
		return QFontMetricsF(self._font)

	def setOpacity(self, value):
		self._opacity = float(value)

	def opacity(self):
		return self._opacity

	def setCompositionMode(self, mode):
		self._mode = mode
		if mode not in _BLEND:
			self.report.lossy[f'compositionMode {mode.name}'] += 1

	def compositionMode(self):
		return self._mode

	def setRenderHint(self, *_):
		pass

	setRenderHints = setRenderHint

	def renderHints(self):
		return QPainter.RenderHint.Antialiasing

	def setBackground(self, *_):
		pass

	setBackgroundMode = setLayoutDirection = setBackground

	# Section: transforms

	def _syncMatrix(self):
		self.canvas.setMatrix(toSkMatrix(self._world))

	def setTransform(self, transform, combine=False):
		self._world = QTransform(transform) * self._world if combine else QTransform(transform) * self.base
		self._syncMatrix()

	setWorldTransform = setTransform

	def transform(self):
		return QTransform(self._world)

	worldTransform = transform

	def resetTransform(self):
		self._world = QTransform(self.base)
		self._syncMatrix()

	def translate(self, *args):
		dx, dy = (args[0].x(), args[0].y()) if len(args) == 1 else args
		self._world = QTransform().translate(dx, dy) * self._world
		self._syncMatrix()

	def scale(self, sx, sy):
		self._world = QTransform().scale(sx, sy) * self._world
		self._syncMatrix()

	def rotate(self, degrees_):
		self._world = QTransform().rotate(degrees_) * self._world
		self._syncMatrix()

	# Section: clipping (Skia clips are part of save/restore, as in QPainter; they can only narrow)

	def _clipOp(self, op):
		if op == Qt.ClipOperation.ReplaceClip and self._stack:
			# QPainter can replace a clip set at an outer level; Skia can only intersect with it.
			self.report.lossy['ReplaceClip intersected with the outer clip'] += 1
		if op == Qt.ClipOperation.NoClip:
			self.report.lossy['NoClip ignored'] += 1
			return None
		return skia.ClipOp.kIntersect

	def setClipRect(self, *args, op=Qt.ClipOperation.ReplaceClip, **_):
		if len(args) > 1 and isinstance(args[-1], Qt.ClipOperation):
			*args, op = args
		if self._clipOp(op) is None:
			return
		self.canvas.clipRect(_rect(args[0] if len(args) == 1 else QRectF(*args)), skia.ClipOp.kIntersect, True)

	def setClipPath(self, path, op=Qt.ClipOperation.ReplaceClip):
		if self._clipOp(op) is None:
			return
		self.canvas.clipPath(self._toSkPath(path), skia.ClipOp.kIntersect, True)

	def setClipRegion(self, region, op=Qt.ClipOperation.ReplaceClip):
		self.setClipRect(QRectF(region.boundingRect()), op)
		if region.rectCount() > 1:
			self.report.lossy['clip region reduced to its bounds'] += 1

	def setClipping(self, on):
		if not on:
			self.report.lossy['setClipping(False) ignored'] += 1

	# Section: paints

	def _shader(self, brush: QBrush):
		style = brush.style()
		g = brush.gradient()
		stops = g.stops()
		colors = [_color4f(c).toColor() for _, c in stops]
		positions = [float(p) for p, _ in stops]
		mode = {QGradient.Spread.PadSpread: skia.TileMode.kClamp, QGradient.Spread.ReflectSpread: skia.TileMode.kMirror,
		        QGradient.Spread.RepeatSpread: skia.TileMode.kRepeat}.get(g.spread(), skia.TileMode.kClamp)
		local = None
		if g.coordinateMode() != QGradient.CoordinateMode.LogicalMode:
			self.report.lossy[f'gradient coordinate mode {g.coordinateMode().name} drawn as logical'] += 1
		if style == Qt.BrushStyle.LinearGradientPattern:
			s, e = g.start(), g.finalStop()
			return skia.GradientShader.MakeLinear([skia.Point(s.x(), s.y()), skia.Point(e.x(), e.y())], colors, positions, mode)
		if style == Qt.BrushStyle.RadialGradientPattern:
			c, f = g.center(), g.focalPoint()
			if f != c or g.focalRadius() > 0:
				return skia.GradientShader.MakeTwoPointConical(
					skia.Point(f.x(), f.y()), g.focalRadius(), skia.Point(c.x(), c.y()), g.radius(), colors, positions, mode)
			return skia.GradientShader.MakeRadial(skia.Point(c.x(), c.y()), g.radius(), colors, positions, mode)
		# Conical: Qt sweeps counter-clockwise from `angle` (degrees, 0 = east); Skia sweeps clockwise from east.
		c = g.center()
		m = skia.Matrix()
		m.setRotate(-g.angle(), c.x(), c.y())
		m.preScale(1, -1, c.x(), c.y())
		return skia.GradientShader.MakeSweep(c.x(), c.y(), colors, positions, localMatrix=m)

	def _paint(self, brush: QBrush, stroke: bool):
		"""A `skia.Paint` for a brush, or None when nothing is drawn."""
		style = brush.style()
		if style == Qt.BrushStyle.NoBrush:
			return None
		p = skia.Paint(AntiAlias=True)
		if style in (Qt.BrushStyle.LinearGradientPattern, Qt.BrushStyle.RadialGradientPattern, Qt.BrushStyle.ConicalGradientPattern):
			p.setShader(self._shader(brush))
			p.setAlphaf(self._opacity)
		else:
			if style != Qt.BrushStyle.SolidPattern:
				self.report.lossy[f'brush style {style.name} drawn solid'] += 1
			p.setColor4f(_color4f(brush.color(), self._opacity))
		blend = _BLEND.get(self._mode)
		if blend is not None and blend != skia.BlendMode.kSrcOver:
			p.setBlendMode(blend)
		if stroke:
			pen = self._pen
			width = pen.widthF()
			p.setStyle(skia.Paint.kStroke_Style)
			p.setStrokeWidth(width)  # 0 is a hairline in both
			p.setStrokeCap(_CAP.get(pen.capStyle(), skia.Paint.kButt_Cap))
			p.setStrokeJoin(_JOIN.get(pen.joinStyle(), skia.Paint.kMiter_Join))
			p.setStrokeMiter(pen.miterLimit())
			if pen.style() not in (Qt.PenStyle.SolidLine, Qt.PenStyle.NoPen):
				unit = width if width > 0 else 1.0
				pattern = [max(v * unit, 0.01) for v in pen.dashPattern()]
				if len(pattern) % 2:
					pattern = pattern * 2
				if pattern:
					p.setPathEffect(skia.DashPathEffect.Make(pattern, pen.dashOffset() * unit))
		return p

	def _strokePaint(self):
		if self._pen.style() == Qt.PenStyle.NoPen:
			return None
		return self._paint(self._pen.brush(), True)

	def _fillPaint(self, brush=None):
		return self._paint(brush if brush is not None else self._brush, False)

	# Section: paths

	def _toSkPath(self, path: QPainterPath) -> skia.Path:
		t0 = time.perf_counter()
		key = None
		if self.cache is not None:
			b = path.boundingRect()
			key = (path.elementCount(), b.x(), b.y(), b.width(), b.height(), path.fillRule())
			for other, hit in self.cache.get(key, ()):
				if other == path:
					self.report.pathCacheHits += 1
					return hit
		sp = skia.Path()
		sp.setFillType(skia.PathFillType.kEvenOdd if path.fillRule() == Qt.FillRule.OddEvenFill else skia.PathFillType.kWinding)
		n = path.elementCount()
		i = 0
		while i < n:
			e = path.elementAt(i)
			if e.isMoveTo():
				sp.moveTo(e.x, e.y)
				i += 1
			elif e.isLineTo():
				sp.lineTo(e.x, e.y)
				i += 1
			else:  # CurveToElement, then two CurveToDataElements
				a = path.elementAt(i + 1)
				b = path.elementAt(i + 2)
				sp.cubicTo(e.x, e.y, a.x, a.y, b.x, b.y)
				i += 3
		self.report.pathsConverted += 1
		self.report.convertSeconds += time.perf_counter() - t0
		if key is not None:
			if len(self.cache) > 4000:
				self.cache.clear()
			self.cache.setdefault(key, []).append((QPainterPath(path), sp))
		return sp

	def _drawSk(self, draw):
		"""Fill with the brush, then stroke with the pen: QPainter's order."""
		self.report.calls['shapes drawn'] += 1
		fill = self._fillPaint()
		if fill is not None:
			draw(fill)
		stroke = self._strokePaint()
		if stroke is not None:
			draw(stroke)

	def drawPath(self, path):
		sp = self._toSkPath(path)
		self._drawSk(lambda p: self.canvas.drawPath(sp, p))

	def fillPath(self, path, brush):
		paint = self._fillPaint(brush if isinstance(brush, QBrush) else QBrush(brush))
		if paint is not None:
			self.canvas.drawPath(self._toSkPath(path), paint)

	def strokePath(self, path, pen):
		old = self._pen
		self._pen = pen if isinstance(pen, QPen) else QPen(pen)
		paint = self._strokePaint()
		if paint is not None:
			self.canvas.drawPath(self._toSkPath(path), paint)
		self._pen = old

	def drawRect(self, *args):
		r = _rect(args[0] if len(args) == 1 else QRectF(*args))
		self._drawSk(lambda p: self.canvas.drawRect(r, p))

	def drawRects(self, rects):
		for r in rects:
			self.drawRect(r)

	def drawRoundedRect(self, rect, rx, ry=None, mode=Qt.SizeMode.AbsoluteSize):
		rect = QRectF(rect)
		ry = rx if ry is None else ry
		if mode == Qt.SizeMode.RelativeSize:
			rx, ry = rect.width() * rx / 200.0, rect.height() * ry / 200.0
		r = _rect(rect)
		self._drawSk(lambda p: self.canvas.drawRoundRect(r, rx, ry, p))

	def drawEllipse(self, *args):
		if len(args) == 1:
			r = QRectF(args[0])
		elif len(args) == 3:
			ctr, rx, ry = args
			r = QRectF(ctr.x() - rx, ctr.y() - ry, 2 * rx, 2 * ry)
		else:
			r = QRectF(*args)
		sr = _rect(r)
		self._drawSk(lambda p: self.canvas.drawOval(sr, p))

	def drawLine(self, *args):
		if len(args) == 1:
			ln = QLineF(args[0])
			p1, p2 = ln.p1(), ln.p2()
		elif len(args) == 2:
			p1, p2 = QPointF(args[0]), QPointF(args[1])
		else:
			p1, p2 = QPointF(args[0], args[1]), QPointF(args[2], args[3])
		paint = self._strokePaint()
		if paint is not None:
			self.canvas.drawLine(p1.x(), p1.y(), p2.x(), p2.y(), paint)

	def drawLines(self, lines):
		for ln in lines:
			self.drawLine(ln)

	def _poly(self, poly, close):
		pts = poly.toList() if isinstance(poly, QPolygonF) else list(poly)
		sp = skia.Path()
		if pts:
			sp.moveTo(pts[0].x(), pts[0].y())
			for pt in pts[1:]:
				sp.lineTo(pt.x(), pt.y())
			if close:
				sp.close()
		return sp

	def drawPolygon(self, poly, *rest):
		sp = self._poly(poly, True)
		if rest and rest[-1] == Qt.FillRule.OddEvenFill:
			sp.setFillType(skia.PathFillType.kEvenOdd)
		self._drawSk(lambda p: self.canvas.drawPath(sp, p))

	def drawPolyline(self, poly):
		paint = self._strokePaint()
		if paint is not None:
			self.canvas.drawPath(self._poly(poly, False), paint)

	def drawPoint(self, *args):
		pt = QPointF(*args) if len(args) == 2 else QPointF(args[0])
		paint = self._strokePaint()
		if paint is not None:
			self.canvas.drawPoint(pt.x(), pt.y(), paint)

	def fillRect(self, *args):
		*geometry, brush = args if len(args) in (2, 5) else (*args, None)
		rect = geometry[0] if len(geometry) == 1 else QRectF(*geometry)
		if brush is None:
			brush = self._brush
		elif isinstance(brush, (QColor, Qt.GlobalColor)):
			brush = QBrush(QColor(brush))
		elif not isinstance(brush, QBrush):
			brush = QBrush(brush)
		paint = self._fillPaint(brush)
		if paint is not None:
			self.canvas.drawRect(_rect(rect), paint)

	def eraseRect(self, *args):
		self.report.lossy['eraseRect ignored'] += 1

	# Section: glow (optional fast path for `lib/ui/glow.py`)

	def glowPath(self, path: QPainterPath, brush: QBrush, width: float, sigma: float, alpha: float, additive: bool):
		"""Stroke `path` at `width` with a Gaussian blur of `sigma` - the halo in one GPU pass instead of stacked strokes."""
		old = (self._pen, self._opacity, self._mode)
		pen = QPen(brush, width)
		pen.setCapStyle(Qt.PenCapStyle.RoundCap)
		pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
		self._pen = pen
		self._opacity = old[1] * alpha
		if additive:
			self._mode = _M.CompositionMode_Plus
		paint = self._strokePaint()
		self._pen, self._opacity, self._mode = old
		if paint is None:
			return
		paint.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, max(sigma, 0.1)))
		self.canvas.drawPath(self._toSkPath(path), paint)
		self.report.calls['glow passes'] += 1

	# Section: text (drawn as glyph outlines: the same shapes QPainter would fill)

	def drawText(self, *args):
		self.report.calls['text drawn'] += 1
		fm = QFontMetricsF(self._font)
		if len(args) == 2 and isinstance(args[0], QPointF):
			origin, text = args
		elif len(args) == 3 and isinstance(args[0], (int, float)):
			origin, text = QPointF(float(args[0]), float(args[1])), args[2]
		elif len(args) >= 3:
			rect, flags, text = QRectF(args[0]), int(getattr(args[1], 'value', args[1])), str(args[2])
			A = Qt.AlignmentFlag
			w = fm.horizontalAdvance(text)
			if flags & A.AlignRight.value:
				x = rect.right() - w
			elif flags & A.AlignHCenter.value:
				x = rect.center().x() - w / 2
			else:
				x = rect.left()
			if flags & A.AlignBottom.value:
				y = rect.bottom() - fm.descent()
			elif flags & A.AlignTop.value:
				y = rect.top() + fm.ascent()
			else:
				y = rect.center().y() + (fm.ascent() - fm.descent()) / 2
			origin = QPointF(x, y)
		else:
			self.report.missing['drawText' + repr(tuple(type(a).__name__ for a in args))] += 1
			return
		path = QPainterPath()
		path.addText(origin, self._font, str(text))
		paint = self._fillPaint(QBrush(self._pen.color()))
		if paint is not None:
			self.canvas.drawPath(self._toSkPath(path), paint)

	# Section: images

	def _skImage(self, image):
		if isinstance(image, QPixmap):
			image = image.toImage()
		key = image.cacheKey()
		si = self._images.get(key)
		if si is None:
			img = image.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
			arr = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)[:, :img.width()].copy()
			si = skia.Image.fromarray(arr, colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kPremul_AlphaType)
			self._images[key] = si
			self.report.imagesUploaded += 1
		return si

	def drawImage(self, target, image, *rest):
		if isinstance(target, (int, float)):  # drawImage(x, y, image[, sx, sy, sw, sh])
			x, y, image, *rest = (target, image, *rest)
			target = QPointF(float(x), float(y))
			if len(rest) >= 4 and rest[2] > 0 and rest[3] > 0:
				target, rest = QRectF(target.x(), target.y(), rest[2], rest[3]), [QRectF(*rest[:4])]
			else:
				rest = []
		if image is None or image.isNull():
			return
		si = self._skImage(image)
		paint = skia.Paint(AntiAlias=True)
		paint.setAlphaf(self._opacity)
		blend = _BLEND.get(self._mode)
		if blend is not None:
			paint.setBlendMode(blend)
		sampling = skia.SamplingOptions(skia.FilterMode.kLinear)
		if isinstance(target, (QPointF,)) or (hasattr(target, 'x') and not hasattr(target, 'width')):
			pt = QPointF(target)
			self.canvas.drawImage(si, pt.x(), pt.y(), sampling, paint)
		else:
			src = _rect(rest[0]) if rest and isinstance(rest[0], (QRectF,)) or rest and hasattr(rest[0], 'width') else skia.Rect.MakeWH(si.width(), si.height())
			self.canvas.drawImageRect(si, src, _rect(target), sampling, paint)

	def drawPixmap(self, target, pixmap, *rest):
		self.drawImage(target, pixmap, *rest)

	def __getattr__(self, name):
		if name.startswith('__'):
			raise AttributeError(name)
		self.report.missing[name] += 1
		return lambda *a, **k: None


# Section: the scene walk

_NATIVE_PAINTERS = (
	QGraphicsPathItem, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPolygonItem,
	QGraphicsSimpleTextItem, QGraphicsPixmapItem,
)
_CLIPS_CHILDREN = QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape
_CLIPS_SELF = QGraphicsItem.GraphicsItemFlag.ItemClipsToShape
_NO_CONTENTS = QGraphicsItem.GraphicsItemFlag.ItemHasNoContents


def _pythonPaint(item) -> bool:
	for cls in type(item).__mro__:
		if 'paint' in cls.__dict__:
			return not cls.__module__.startswith('PySide6')
	return False


def _attr(item, name):
	if name in ('pen', 'brush') and isinstance(item, QAbstractGraphicsShapeItem):
		return getattr(QAbstractGraphicsShapeItem, name)(item)
	value = getattr(item, name)
	return value() if callable(value) else value


def _nativePaint(item, shim: SkiaPainterShim):
	if isinstance(item, QGraphicsPathItem):
		shim.setPen(_attr(item, 'pen'))
		shim.setBrush(_attr(item, 'brush'))
		shim.drawPath(item.path())
	elif isinstance(item, QGraphicsRectItem):
		shim.setPen(_attr(item, 'pen'))
		shim.setBrush(_attr(item, 'brush'))
		shim.drawRect(item.rect())
	elif isinstance(item, QGraphicsEllipseItem):
		shim.setPen(_attr(item, 'pen'))
		shim.setBrush(_attr(item, 'brush'))
		shim.drawEllipse(item.rect())
	elif isinstance(item, QGraphicsLineItem):
		shim.setPen(_attr(item, 'pen'))
		shim.drawLine(item.line())
	elif isinstance(item, QGraphicsPolygonItem):
		shim.setPen(_attr(item, 'pen'))
		shim.setBrush(_attr(item, 'brush'))
		shim.drawPolygon(item.polygon(), item.fillRule())
	elif isinstance(item, QGraphicsSimpleTextItem):
		shim.setFont(item.font())
		shim.setPen(QPen(_attr(item, 'brush').color()))
		shim.drawText(QPointF(0, QFontMetricsF(item.font()).ascent()), item.text())
	elif isinstance(item, QGraphicsPixmapItem):
		shim.drawPixmap(item.offset(), item.pixmap())


@contextmanager
def nativePaintRedirected():
	"""Let `super().paint(...)` on a stock Qt item class draw through the shim (the C++ method wants a real QPainter)."""
	saved = {}

	def make(original):
		def paint(self, painter, option=None, widget=None):
			if isinstance(painter, SkiaPainterShim):
				_nativePaint(self, painter)
			else:
				original(self, painter, option, widget)
		return paint

	for cls in _NATIVE_PAINTERS:
		saved[cls] = cls.paint
		cls.paint = make(cls.paint)
	try:
		yield
	finally:
		for cls, original in saved.items():
			cls.paint = original


def _clipChain(item):
	"""Ancestors (outermost first) whose shape clips `item`."""
	chain = []
	parent = item.parentItem()
	while parent is not None:
		if parent.flags() & _CLIPS_CHILDREN:
			chain.append(parent)
		parent = parent.parentItem()
	chain.reverse()
	return chain


def _effectLayer(item, effect, shim: SkiaPainterShim):
	"""Open a layer whose image filter applies `effect` to what the item paints. Returns True if a layer was opened."""
	if isinstance(effect, QGraphicsDropShadowEffect):
		off = effect.offset()
		sigma = max(effect.blurRadius() / 2.0, 0.1)
		c = effect.color()
		f = skia.ImageFilters.DropShadow(off.x(), off.y(), sigma, sigma, _color4f(c).toColor())
	elif isinstance(effect, QGraphicsBlurEffect):
		sigma = max(effect.blurRadius() / 2.0, 0.1)
		f = skia.ImageFilters.Blur(sigma, sigma)
	elif isinstance(effect, QGraphicsOpacityEffect):
		paint = skia.Paint()
		paint.setAlphaf(effect.opacity())
		shim.canvas.saveLayer(None, paint)
		return True
	else:
		shim.report.lossy[f'{type(effect).__name__} skipped'] += 1
		return False
	paint = skia.Paint()
	paint.setImageFilter(f)
	shim.canvas.saveLayer(None, paint)
	return True


def paintScene(scene, shim: SkiaPainterShim, background: QColor = None, rect: QRectF = None, region: QRectF = None):
	"""Draw every visible item of `scene` through `shim`, in stacking order; `region` (scene coordinates) limits the walk."""
	with nativePaintRedirected():
		return _paintScene(scene, shim, background, rect, region)


def _paintScene(scene, shim: SkiaPainterShim, background=None, rect=None, region=None):
	canvas = shim.canvas
	rect = rect or scene.sceneRect()
	m = canvas.getTotalMatrix()
	shim.base = QTransform(m.getScaleX(), m.getSkewY(), m.getPerspX(), m.getSkewX(), m.getScaleY(), m.getPerspY(), m.getTranslateX(), m.getTranslateY(), 1.0)
	canvas.save()
	if region is not None:
		canvas.clipRect(_rect(region), skia.ClipOp.kIntersect, False)
		items = scene.items(region, Qt.ItemSelectionMode.IntersectsItemBoundingRect, Qt.SortOrder.AscendingOrder)
	else:
		items = scene.items(Qt.SortOrder.AscendingOrder)
	if background is not None:
		shim._opacity = 1.0
		shim._mode = _M.CompositionMode_Source
		shim.fillRect(region if region is not None else rect, QBrush(background))
	option = QStyleOptionGraphicsItem()
	painted = 0
	for item in items:
		if not item.isVisible() or item.flags() & _NO_CONTENTS:
			continue
		opacity = item.effectiveOpacity()
		if opacity <= 0:
			continue
		canvas.save()
		shim._stack.clear()
		shim._pen = QPen(Qt.PenStyle.NoPen)
		shim._brush = QBrush(Qt.BrushStyle.NoBrush)
		shim._opacity = opacity
		shim._mode = _M.CompositionMode_SourceOver
		for clipper in _clipChain(item):
			canvas.setMatrix(toSkMatrix(clipper.sceneTransform() * shim.base))
			canvas.clipPath(shim._toSkPath(clipper.shape()), skia.ClipOp.kIntersect, True)
		shim._world = QTransform(shim.base)
		shim.setTransform(item.sceneTransform())
		if item.flags() & _CLIPS_SELF:
			canvas.clipPath(shim._toSkPath(item.shape()), skia.ClipOp.kIntersect, True)
		effect = item.graphicsEffect()
		layered = effect is not None and effect.isEnabled() and _effectLayer(item, effect, shim)
		try:
			if _pythonPaint(item):
				option.rect = item.boundingRect().toRect()
				item.paint(shim, option, None)
			elif isinstance(item, _NATIVE_PAINTERS):
				_nativePaint(item, shim)
			else:
				continue
			painted += 1
		except Exception as e:  # noqa: BLE001 - report what breaks instead of stopping the frame
			shim.report.missing[f'{type(item).__name__}.paint raised {type(e).__name__}: {str(e)[:60]}'] += 1
		finally:
			if layered:
				canvas.restore()
			canvas.restore()
	canvas.restore()
	return painted
