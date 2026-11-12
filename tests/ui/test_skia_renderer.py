"""The Skia tier is opt-in and optional; its shim draws like QPainter (raster, so no GL is needed here)."""
import pytest

from LevityDash.lib.ui.frontends.PySide import skia as skiaTier


def test_default_renderer_is_not_skia():
	assert not skiaTier.wanted('qpainter')
	assert not skiaTier.wanted('canvas')


def test_skia_needs_the_package(monkeypatch):
	monkeypatch.setattr(skiaTier, 'available', lambda: False)
	assert not skiaTier.wanted('skia')


def test_skia_when_available(monkeypatch):
	monkeypatch.setattr(skiaTier, 'available', lambda: True)
	assert skiaTier.wanted(' Skia ')


def _scene():
	from PySide6.QtCore import QRectF, Qt
	from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
	from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsRectItem, QGraphicsScene

	scene = QGraphicsScene(0, 0, 120, 80)
	rect = QGraphicsRectItem(10, 10, 50, 30)
	rect.setBrush(QBrush(QColor('#3080ff')))
	rect.setPen(QPen(Qt.PenStyle.NoPen))
	scene.addItem(rect)
	ring = QPainterPath()
	ring.addEllipse(QRectF(70, 20, 40, 40))
	ring.addEllipse(QRectF(80, 30, 20, 20))  # same winding: Qt's winding fill keeps it solid
	path = QGraphicsPathItem(ring)
	path.setBrush(QBrush(QColor('#ffaa00')))
	path.setPen(QPen(QColor('white'), 2, Qt.PenStyle.DashLine))
	scene.addItem(path)
	return scene


def _pixels(image):
	import numpy as np
	from PySide6.QtGui import QImage
	image = image.convertToFormat(QImage.Format.Format_RGBA8888)
	return np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)[..., :3].astype(int)


def test_shim_matches_qpainter():
	skia = pytest.importorskip('skia')
	import numpy as np
	from PySide6.QtGui import QColor, QImage, QPainter
	from LevityDash.lib.ui.frontends.PySide.skia.shim import SkiaPainterShim, paintScene

	scene = _scene()
	qt = QImage(120, 80, QImage.Format.Format_RGBA8888)
	qt.fill(QColor('black'))
	p = QPainter(qt)
	p.setRenderHint(QPainter.RenderHint.Antialiasing)
	scene.render(p)
	p.end()

	surface = skia.Surface(120, 80)
	shim = SkiaPainterShim(surface.getCanvas())
	paintScene(scene, shim, QColor('black'))
	arr = np.ascontiguousarray(surface.makeImageSnapshot().toarray(colorType=skia.kRGBA_8888_ColorType))[..., :3].astype(int)

	assert not shim.report.missing
	assert np.abs(_pixels(qt) - arr).mean() < 2.0


def test_glow_uses_one_blurred_pass():
	skia = pytest.importorskip('skia')
	from PySide6.QtCore import QRectF
	from PySide6.QtGui import QBrush, QColor, QPainterPath
	from LevityDash.lib.ui.glow import Glow, paintGlow
	from LevityDash.lib.ui.frontends.PySide.skia.shim import SkiaPainterShim

	path = QPainterPath()
	path.addEllipse(QRectF(10, 10, 40, 40))
	shim = SkiaPainterShim(skia.Surface(64, 64).getCanvas())
	paintGlow(shim, path, QBrush(QColor('#ff00ff')), 4.0, Glow())
	assert shim.report.calls['glow passes'] == 2  # the halo and the capped additive bloom
	shim.blurGlow = False
	shim.report.clear()
	paintGlow(shim, path, QBrush(QColor('#ff00ff')), 4.0, Glow())
	assert shim.report.calls['glow passes'] == 0
