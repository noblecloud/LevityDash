"""The Canvas Painter tier is opt-in and optional; the default stays QPainter."""
import pytest

from LevityDash.lib.ui.frontends.PySide import canvas


def test_default_renderer_is_qpainter():
	assert not canvas.wanted('qpainter')
	assert not canvas.wanted('')


def test_canvas_needs_the_module(monkeypatch):
	monkeypatch.setattr(canvas, 'available', lambda: False)
	assert not canvas.wanted('canvas')


def test_canvas_when_available(monkeypatch):
	monkeypatch.setattr(canvas, 'available', lambda: True)
	assert canvas.wanted(' Canvas ')


def test_shim_clip_survives_restore():
	pytest.importorskip('PySide6.QtCanvasPainter')
	from PySide6.QtCore import QRectF
	from PySide6.QtGui import QTransform
	from LevityDash.lib.ui.frontends.PySide.canvas.shim import CanvasPainterShim

	class FakeCanvas:
		def __init__(self):
			self.rects = []
			self.resets = 0

		def __getattr__(self, name):
			if name == 'resetClipping':
				return self._reset
			if name == 'setClipRect':
				return self.rects.append
			if name == 'getTransform':
				return QTransform
			return lambda *a, **k: None

		def _reset(self):
			self.resets += 1
			self.rects.append(None)

	canvas_ = FakeCanvas()
	shim = CanvasPainterShim(canvas_)
	shim.setClipRect(QRectF(0, 0, 10, 10))
	shim.save()
	shim.setClipRect(QRectF(2, 2, 3, 3))
	shim.restore()
	assert canvas_.rects[-1] == QRectF(0, 0, 10, 10)
