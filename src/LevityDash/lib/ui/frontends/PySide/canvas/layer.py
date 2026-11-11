"""The widget that draws the dashboard scene with Qt Canvas Painter, underneath a transparent view."""
import time

from PySide6.QtCanvasPainter import QCanvasOffscreenCanvas, QCanvasPainterWidget
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QTransform

from .shim import CanvasPainterShim, Report, paintScene

__all__ = ['CanvasSceneLayer']

#: Scene units added around each changed region: a shadow or glow reaches past an item's bounding rectangle.
_PAD = 24.0


class CanvasSceneLayer(QCanvasPainterWidget):
	"""Keeps the scene in a retained GPU texture and re-records only the regions that changed.

	Walking every item of a 6,000 to 12,000 item scene in Python each frame is far slower than QPainter,
	which repaints only dirty rectangles. This does the same: `scene.changed` collects dirty regions, and
	`prePaint` clears and redraws just those (clipped, items that touch them only) into an offscreen canvas
	that keeps its contents; `paint` then draws that texture. A new size or view transform repaints it all.

	It sits below the `QGraphicsView`, which keeps every event (mouse, keys, hover, selection) but paints
	nothing in this mode. The view's own transform (`fitInView`) is applied when recording.
	"""

	def __init__(self, view, parent=None):
		super().__init__(parent)
		self.view = view
		self.report = Report()
		#: Seconds the Python side spent recording each of the last frames.
		self.recordSeconds = []
		#: (dirty area in scene units squared or -1 for everything, items painted, seconds) per recorded frame.
		self.frames = []
		self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
		self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
		self._connected = None
		self._canvas = None
		self._image = None
		self._pixels = QSize()
		self._transform = None
		#: None: repaint everything. A rectangle in scene units: repaint that. An empty one: nothing to do.
		self._dirty = None
		#: Converted paths kept between frames (`CanvasPainterShim.cache`): most paths do not change.
		self.pathCache = {}

	def bind(self):
		scene = self.view.scene()
		if scene is None or scene is self._connected:
			return
		self._connected = scene
		scene.changed.connect(self._sceneChanged)

	def invalidate(self):
		"""Repaint the whole scene on the next frame."""
		self._dirty = None
		self.update()

	def _sceneChanged(self, regions=None):
		if self._dirty is None:
			self.update()
			return
		dirty = self._dirty
		for r in regions or ():
			dirty = dirty.united(r.adjusted(-_PAD, -_PAD, _PAD, _PAD)) if not dirty.isNull() else r.adjusted(-_PAD, -_PAD, _PAD, _PAD)
		self._dirty = dirty
		self.update()

	def resizeEvent(self, event):
		super().resizeEvent(event)
		self.invalidate()

	def _ensureCanvas(self, painter, ratio):
		pixels = QSize(max(1, round(self.width() * ratio)), max(1, round(self.height() * ratio)))
		if self._canvas is not None and pixels == self._pixels:
			return False
		if self._canvas is not None:
			painter.destroyCanvas(self._canvas)
		self._canvas = painter.createCanvas(pixels, 1, QCanvasOffscreenCanvas.Flag.PreserveContents)
		self._image = None
		self._pixels = pixels
		self._dirty = None
		return True

	def prePaint(self, painter):
		scene = self.view.scene()
		if scene is None:
			return
		ratio = self.devicePixelRatioF()
		self._ensureCanvas(painter, ratio)
		transform = QTransform(self.view.viewportTransform())
		if transform != self._transform:
			self._transform = transform
			self._dirty = None
		dirty = self._dirty
		if dirty is not None and dirty.isNull():
			return
		started = time.perf_counter()
		self._dirty = QRectF()
		view = transform * QTransform.fromScale(ratio, ratio)
		if dirty is None:
			region = None
		else:
			region = dirty.intersected(scene.sceneRect().adjusted(-_PAD, -_PAD, _PAD, _PAD))
			if region.isEmpty():
				return
		self.beginCanvasPainting(self._canvas)
		painter.resetClipping()
		painter.resetTransform()
		painter.setTransform(view)
		if region is not None:
			device = view.mapRect(region)
			painter.setClipRect(device.adjusted(-1, -1, 1, 1))
			painter.save()
			painter.resetTransform()
			painter.clearRect(device.adjusted(-1, -1, 1, 1))
			painter.restore()
		else:
			painter.clearRect(QRectF(0, 0, self._pixels.width(), self._pixels.height()))
		shim = CanvasPainterShim(painter, self.report, ratio)
		shim.cache = self.pathCache
		painted = paintScene(scene, shim, scene.backdrop(), scene.sceneRect(), region if region is not None else None)
		self.frames.append((region.width() * region.height() if region is not None else -1.0, painted, time.perf_counter() - started))
		del self.frames[:-120]
		painter.resetClipping()
		self.endCanvasPainting()
		self.recordSeconds.append(time.perf_counter() - started)
		del self.recordSeconds[:-120]

	def paint(self, painter):
		if self._canvas is None:
			return
		if self._image is None:
			self._image = painter.addImage(self._canvas)
		painter.drawImage(self._image, QRectF(0, 0, self.width(), self.height()))
