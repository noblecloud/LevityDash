#!/usr/bin/env python
"""Dev-only spike: draw the Studio's gauge showcase through Qt Canvas Painter and compare with Qt.

    QT_QPA_PLATFORM=xcb xvfb-run -a python src/LevityDash/devtools/canvas_spike.py OUT_DIR [--cells 0,1,2] [--scale 3]

Needs a GL (or other RHI) context: a real display, or `xvfb-run` with Mesa on Linux. For each
cell it loads the gauge into the Studio stage (the real `Gauge` class), renders it with
`QGraphicsScene.render()` (QPainter, CPU) and again with `canvas_shim.paintScene` on a
`QCanvasPainterWidget`, then writes `NN-qt.png`, `NN-canvas.png`, `NN-side.png` and prints the
mean pixel difference, timings, and what the shim could only approximate (`Report`).
"""
import argparse
import copy
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _studio_env

_studio_env.prepare()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PySide6.QtCanvasPainter import QCanvasPainterWidget
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from LevityDash.devtools import studio as gs
from LevityDash.devtools.canvas_shim import CanvasPainterShim, Report, paintScene

app = QApplication.instance() or QApplication(sys.argv)


class SceneWidget(QCanvasPainterWidget):
	"""Draws `scene` through the shim; keeps the time the Python side spent recording."""

	def __init__(self, scene, background, scale, cache=False):
		super().__init__()
		self.pathCache = {} if cache else None
		self.scene = scene
		self.background = background
		self.scale = scale
		self.report = Report()
		self.recordMs = []
		self.painted = 0

	def paint(self, canvas):
		t = time.perf_counter()
		shim = CanvasPainterShim(canvas, self.report)
		shim.cache = self.pathCache
		canvas.scale(self.scale, self.scale)
		self.painted = paintScene(self.scene, shim, self.background, self.scene.sceneRect())
		self.recordMs.append((time.perf_counter() - t) * 1000)


def pump(n=3):
	for _ in range(n):
		app.processEvents()


def qtRender(scene, size, background, scale):
	img = QImage(int(size.width() * scale), int(size.height() * scale), QImage.Format.Format_ARGB32_Premultiplied)
	img.fill(background)
	p = QPainter(img)
	p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing | QPainter.RenderHint.SmoothPixmapTransform)
	scene.render(p, QRectF(img.rect()), scene.sceneRect())
	p.end()
	return img


def meanDiff(a: QImage, b: QImage) -> float:
	import numpy as np
	a = a.convertToFormat(QImage.Format.Format_RGB32)
	b = b.convertToFormat(QImage.Format.Format_RGB32)
	w, h = min(a.width(), b.width()), min(a.height(), b.height())

	def arr(i):
		return np.frombuffer(i.constBits(), np.uint8).reshape(i.height(), i.bytesPerLine() // 4, 4)[:h, :w, :3].astype(int)
	return float(np.abs(arr(a) - arr(b)).mean())


def sideBySide(a: QImage, b: QImage) -> QImage:
	out = QImage(a.width() + b.width() + 8, max(a.height(), b.height()), QImage.Format.Format_RGB32)
	out.fill(QColor('#888'))
	p = QPainter(out)
	p.drawImage(0, 0, a)
	p.drawImage(a.width() + 8, 0, b)
	p.end()
	return out


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument('out')
	ap.add_argument('--cells', default='0,1,2,3', help='showcase cell indexes, or "all"')
	ap.add_argument('--scale', type=float, default=2.0)
	ap.add_argument('--frames', type=int, default=30)
	ap.add_argument('--cache', action='store_true', help='cache converted paths by a cheap fingerprint (experimental)')
	a = ap.parse_args()
	out = Path(a.out)
	out.mkdir(parents=True, exist_ok=True)
	cells = gs.showcaseExamples()
	indexes = range(len(cells)) if a.cells == 'all' else [int(x) for x in a.cells.split(',')]
	studio = gs.Studio()
	studio.show()
	pump()
	rows = []
	for i in indexes:
		label, entry = cells[i]
		studio.loadDisplay(copy.deepcopy(entry.get('display') or {}), entry.get('key'), label)
		pump()
		studio.settle()
		scene = studio.studio.scene
		size = scene.sceneRect().size()
		background = QColor('#1b1e24')  # the Studio stage is transparent; both renders need the same opaque ground
		qt = qtRender(scene, size, background, a.scale)
		t = time.perf_counter()
		for _ in range(a.frames):
			qtRender(scene, size, background, a.scale)
		qtMs = (time.perf_counter() - t) / a.frames * 1000

		w = SceneWidget(scene, background, a.scale, a.cache)
		w.resize(int(size.width() * a.scale), int(size.height() * a.scale))
		w.show()
		pump(5)
		w.report.clear()
		w.recordMs.clear()
		for _ in range(a.frames):
			w.update()
			pump(2)
		img = w.grabFramebuffer()
		rec = statistics.median(w.recordMs[2:]) if len(w.recordMs) > 3 else float('nan')
		w.close()
		d = meanDiff(qt, img)
		qt.save(str(out / f'{i:02d}-qt.png'))
		img.save(str(out / f'{i:02d}-canvas.png'))
		sideBySide(qt, img).save(str(out / f'{i:02d}-side.png'))
		r = w.report
		frames = max(1, len(w.recordMs))
		print(f'cell {i:2d} {label[:34]:34s} items drawn {w.painted:3d}  Qt {qtMs:6.1f} ms  canvas record {rec:6.1f} ms  '
			f'mean diff {d:5.1f}/255  paths/frame {r.pathsConverted // frames:3d} ({r.pathElements // frames} elems, {r.convertSeconds / frames * 1000:.1f} ms converting)')
		for k, n in r.lossy.most_common(6):
			print(f'      lossy  {n // frames:4d}/frame  {k}')
		for k, n in r.missing.most_common(6):
			print(f'      MISSING {n // frames:4d}/frame  {k}')
		rows.append((i, label, qtMs, rec, d))
	if rows:
		print(f'\nmedian over {len(rows)} cells: Qt {statistics.median(r[2] for r in rows):.1f} ms, canvas record {statistics.median(r[3] for r in rows):.1f} ms, '
			f'mean diff {statistics.median(r[4] for r in rows):.1f}/255')
	studio.close()


if __name__ == '__main__':
	main()
