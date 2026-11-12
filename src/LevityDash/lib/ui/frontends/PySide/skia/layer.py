"""The widget that draws the dashboard scene with Skia on OpenGL, underneath a transparent view."""
import time

import skia
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QSurfaceFormat, QTransform
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from .shim import Report, SkiaPainterShim, paintScene, toSkMatrix

__all__ = ['SkiaSceneLayer']

#: Scene units added around each changed region: a shadow or glow reaches past an item's bounding rectangle.
_PAD = 24.0
_GL_RGBA8 = 0x8058


class SkiaSceneLayer(QOpenGLWidget):
	"""Keeps the scene in a retained Skia GPU surface and re-records only the regions that changed.

	The same arrangement as the Canvas Painter layer: `scene.changed` collects dirty regions, `paintGL`
	redraws just those (clipped, items that touch them only) into an offscreen GPU surface that keeps its
	contents, then copies that surface to the widget. A new size or view transform repaints it all.

	It sits below the `QGraphicsView`, which keeps every event but paints nothing in this mode.
	"""

	def __init__(self, view, parent=None):
		super().__init__(parent)
		fmt = QSurfaceFormat(self.format())
		fmt.setStencilBufferSize(8)
		self.setFormat(fmt)
		self.view = view
		self.report = Report()
		self.recordSeconds = []
		#: (dirty area in scene units squared or -1 for everything, items painted, seconds) per recorded frame.
		self.frames = []
		self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
		self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
		self._connected = None
		self._gr = None
		self._retained = None
		self._pixels = QSize()
		self._transform = None
		self._dirty = None
		self.pathCache = {}
		self.shim = SkiaPainterShim(None, self.report)
		self.shim.cache = self.pathCache

	def bind(self):
		scene = self.view.scene()
		if scene is None or scene is self._connected:
			return
		self._connected = scene
		scene.changed.connect(self._sceneChanged)

	def invalidate(self):
		self._dirty = None
		self.update()

	def _sceneChanged(self, regions=None):
		if self._dirty is None:
			self.update()
			return
		dirty = self._dirty
		for r in regions or ():
			grown = r.adjusted(-_PAD, -_PAD, _PAD, _PAD)
			dirty = dirty.united(grown) if not dirty.isNull() else grown
		self._dirty = dirty
		self.update()

	def initializeGL(self):
		self._gr = skia.GrDirectContext.MakeGL()
		self._retained = None

	def resizeGL(self, w, h):
		self._dirty = None

	def _ensureRetained(self, pixels: QSize):
		if self._retained is not None and pixels == self._pixels:
			return
		self._retained = skia.Surface.MakeRenderTarget(self._gr, skia.Budgeted.kYes, skia.ImageInfo.MakeN32Premul(pixels.width(), pixels.height()))
		self._pixels = pixels
		self._dirty = None

	def paintGL(self):
		scene = self.view.scene()
		if scene is None or self._gr is None:
			return
		self._gr.resetContext()  # Qt touched GL state since Skia last drew
		ratio = self.devicePixelRatioF()
		pixels = QSize(max(1, round(self.width() * ratio)), max(1, round(self.height() * ratio)))
		self._ensureRetained(pixels)
		transform = QTransform(self.view.viewportTransform())
		if transform != self._transform:
			self._transform = transform
			self._dirty = None
		dirty = self._dirty
		if dirty is None or not dirty.isNull():
			self._record(scene, transform, ratio, dirty)
		target = skia.GrBackendRenderTarget(pixels.width(), pixels.height(), 0, 8, skia.GrGLFramebufferInfo(self.defaultFramebufferObject(), _GL_RGBA8))
		surface = skia.Surface.MakeFromBackendRenderTarget(self._gr, target, skia.kBottomLeft_GrSurfaceOrigin, skia.kRGBA_8888_ColorType, None, None)
		if surface is None:
			self.report.missing['no Skia surface for the widget framebuffer'] += 1
			return
		surface.getCanvas().drawImage(self._retained.makeImageSnapshot(), 0, 0)
		surface.flushAndSubmit()
		del surface

	def _record(self, scene, transform, ratio, dirty):
		started = time.perf_counter()
		self._dirty = QRectF()
		region = None
		if dirty is not None:
			region = dirty.intersected(scene.sceneRect().adjusted(-_PAD, -_PAD, _PAD, _PAD))
			if region.isEmpty():
				return
		canvas = self._retained.getCanvas()
		view = transform * QTransform.fromScale(ratio, ratio)
		canvas.save()
		canvas.resetMatrix()
		if region is not None:
			device = view.mapRect(region).adjusted(-1, -1, 1, 1)
			canvas.clipRect(skia.Rect.MakeXYWH(device.x(), device.y(), device.width(), device.height()))
		canvas.clear(skia.ColorTRANSPARENT)
		canvas.setMatrix(toSkMatrix(view))
		self.shim.canvas = canvas
		self.shim._device._ratio = ratio
		painted = paintScene(scene, self.shim, scene.backdrop(), scene.sceneRect(), region)
		canvas.restore()
		seconds = time.perf_counter() - started
		self.frames.append((region.width() * region.height() if region is not None else -1.0, painted, seconds))
		del self.frames[:-120]
		self.recordSeconds.append(seconds)
		del self.recordSeconds[:-120]
