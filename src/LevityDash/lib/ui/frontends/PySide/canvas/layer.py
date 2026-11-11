"""The widget that draws the dashboard scene with Qt Canvas Painter, underneath a transparent view."""
from PySide6.QtCanvasPainter import QCanvasPainterWidget
from PySide6.QtCore import QRectF, Qt

from .shim import CanvasPainterShim, Report, paintScene

__all__ = ['CanvasSceneLayer']


class CanvasSceneLayer(QCanvasPainterWidget):
	"""Walks `view.scene()` through `CanvasPainterShim` each frame and redraws only when the scene changes.

	It sits below the `QGraphicsView`, which keeps every event (mouse, keys, hover, selection) but
	paints nothing in this mode. The view's own transform (`fitInView`) is applied on top of the walk.
	"""

	def __init__(self, view, parent=None):
		super().__init__(parent)
		self.view = view
		self.report = Report()
		self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
		self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
		self._connected = None

	def bind(self):
		scene = self.view.scene()
		if scene is None or scene is self._connected:
			return
		self._connected = scene
		scene.changed.connect(self._sceneChanged)

	def _sceneChanged(self, _regions=None):
		self.update()

	def paint(self, canvas):
		scene = self.view.scene()
		if scene is None:
			return
		shim = CanvasPainterShim(canvas, self.report, self.devicePixelRatioF())
		canvas.setTransform(self.view.viewportTransform())
		paintScene(scene, shim, scene.backdrop(), scene.sceneRect())
