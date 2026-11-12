#!/usr/bin/env python
"""Dev-only: draw a whole dashboard with QPainter and with Skia (CPU raster and GPU) and compare.

    xvfb-run -a python src/LevityDash/devtools/skia_dashboard.py OUT_DIR DASH.levity [DASH2.levity ...] \\
        [--scenario hot-clear-day] [--size 1800x1090] [--glow]

Boots the dashboard on the Fixture scenario, renders it with `QGraphicsScene.render()` and again with
`skia.shim.paintScene` into a Skia raster surface and an OpenGL Skia surface (needs a GL context: a
display, or `xvfb-run` with Mesa). Writes `<name>-qt.png`, `<name>-skia.png`, `<name>-side.png` and
prints the mean difference, the times and what the shim could only approximate. `--glow` turns on the
one-pass blurred glow (`skiaGlow`) instead of the stacked strokes, so the difference shows the new look.
Each dashboard is a fresh process (the app boots once per process).
"""
import argparse
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _seed import seedEnvironment

if __name__ == '__main__' and '--one' in sys.argv:
	os.environ.setdefault('QT_QPA_PLATFORM', 'xcb')
	seedEnvironment()
	sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def parseSize(text):
	w, _, h = text.lower().partition('x')
	return int(w), int(h)


def meanDiff(a, b):
	import numpy as np
	from PySide6.QtGui import QImage

	def arr(i):
		i = i.convertToFormat(QImage.Format.Format_RGB32)
		return np.frombuffer(i.constBits(), np.uint8).reshape(i.height(), i.bytesPerLine() // 4, 4)[..., :3].astype(int)
	x, y = arr(a), arr(b)
	h, w = min(x.shape[0], y.shape[0]), min(x.shape[1], y.shape[1])
	return float(np.abs(x[:h, :w] - y[:h, :w]).mean())


def toQImage(skImage):
	import numpy as np
	from PySide6.QtGui import QImage
	arr = np.ascontiguousarray(skImage.toarray(colorType=__import__('skia').kRGBA_8888_ColorType))
	h, w = arr.shape[:2]
	return QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()


class GL:
	"""An offscreen OpenGL context with a Skia GPU context on it."""

	def __init__(self):
		import skia
		from PySide6.QtGui import QOffscreenSurface, QOpenGLContext, QSurfaceFormat
		fmt = QSurfaceFormat()
		fmt.setStencilBufferSize(8)
		self.surface = QOffscreenSurface()
		self.surface.setFormat(fmt)
		self.surface.create()
		self.context = QOpenGLContext()
		self.context.setFormat(fmt)
		if not self.context.create() or not self.context.makeCurrent(self.surface):
			raise RuntimeError('no OpenGL context')
		self.gr = skia.GrDirectContext.MakeGL()
		if self.gr is None:
			raise RuntimeError('Skia could not make a GL context')

	def surfaceFor(self, w, h):
		import skia
		self.context.makeCurrent(self.surface)
		return skia.Surface.MakeRenderTarget(self.gr, skia.Budgeted.kNo, skia.ImageInfo.MakeN32Premul(w, h))

	def finish(self):
		import skia
		self.gr.flushAndSubmit(skia.GrSyncCpu.kYes)


def drawWith(surface, scene, rect, shim, background):
	from LevityDash.lib.ui.frontends.PySide.skia.shim import paintScene
	canvas = surface.getCanvas()
	shim.canvas = canvas
	canvas.save()
	canvas.scale(surface.width() / rect.width(), surface.height() / rect.height())
	canvas.translate(-rect.x(), -rect.y())
	n = paintScene(scene, shim, background, rect)
	canvas.restore()
	return n


def one(args):
	if args.glow:
		os.environ['LEVITY_SKIA_GLOW'] = '1'
	import skia
	from LevityDash.devtools._boot import boot, pump, render_image, shutdown
	from LevityDash.lib.ui.frontends.PySide.skia.shim import Report, SkiaPainterShim
	from PySide6.QtGui import QColor, QImage, QPainter

	name = Path(args.levity).stem
	app, dashboard = boot(seed=args.seed, levity=args.levity, size=parseSize(args.size), settle=args.settle, windowed=False, freeze=None)
	try:
		pump(app, 4.0)
		scene = dashboard.scene
		rect = scene.sceneRect()
		qt = render_image(scene, rect, 1.0)
		t = time.perf_counter()
		for _ in range(5):
			render_image(scene, rect, 1.0)
		qtMs = (time.perf_counter() - t) / 5 * 1000
		out = Path(args.out)
		out.mkdir(parents=True, exist_ok=True)
		qt.save(str(out / f'{name}-qt.png'))
		background = getattr(scene, 'backdrop', lambda: None)()
		w, h = qt.width(), qt.height()

		report = Report()
		shim = SkiaPainterShim(None, report)
		shim.cache = {}
		shim.blurGlow = args.glow

		raster = skia.Surface(w, h)
		cpu = []
		for _ in range(5):
			t = time.perf_counter()
			drawWith(raster, scene, rect, shim, background)
			cpu.append(time.perf_counter() - t)
		img = toQImage(raster.makeImageSnapshot())
		rec = []
		for _ in range(5):
			recorder = skia.PictureRecorder()
			t = time.perf_counter()
			canvas = recorder.beginRecording(skia.Rect.MakeWH(w, h))
			shim.canvas = canvas
			from LevityDash.lib.ui.frontends.PySide.skia.shim import paintScene
			paintScene(scene, shim, background, rect)
			picture = recorder.finishRecordingAsPicture()
			rec.append(time.perf_counter() - t)
		t = time.perf_counter()
		raster.getCanvas().drawPicture(picture)
		rasterOnly = (time.perf_counter() - t) * 1000

		gpuMs = float('nan')
		try:
			gl = GL()
			gsurf = gl.surfaceFor(w, h)
			gpu = []
			for _ in range(5):
				t = time.perf_counter()
				drawWith(gsurf, scene, rect, shim, background)
				gl.finish()
				gpu.append(time.perf_counter() - t)
			gpuMs = statistics.median(gpu) * 1000
			gimg = toQImage(gsurf.makeImageSnapshot())
			gimg.save(str(out / f'{name}-skia-gpu.png'))
			gpuDiff = meanDiff(qt, gimg)
		except Exception as e:  # noqa: BLE001
			print(f'{name}: GPU path failed: {e}')
			gpuDiff = float('nan')

		img.save(str(out / f'{name}-skia.png'))
		side = QImage(w * 2 + 8, h, QImage.Format.Format_RGB32)
		side.fill(QColor('#888'))
		p = QPainter(side)
		p.drawImage(0, 0, qt)
		p.drawImage(w + 8, 0, img)
		p.end()
		side.save(str(out / f'{name}-side.png'))
		print(f'{name}: items {len(scene.items())}  Qt {qtMs:.1f} ms  skia cpu {statistics.median(cpu) * 1000:.1f} ms (record {statistics.median(rec) * 1000:.1f} + raster {rasterOnly:.1f})  '
		      f'skia gpu {gpuMs:.1f} ms (draw+flush)  diff cpu {meanDiff(qt, img):.2f}/255 gpu {gpuDiff:.2f}/255')
		for k, n in report.lossy.most_common(8):
			print(f'   lossy   {n // 10:5d}/frame  {k}')
		for k, n in report.missing.most_common(8):
			print(f'   MISSING {n // 10:5d}/frame  {k}')
		print(f'   calls {dict(report.calls)}  paths converted {report.pathsConverted}  cache hits {report.pathCacheHits}')
		return 0
	finally:
		shutdown(dashboard)


def main():
	ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	ap.add_argument('out')
	ap.add_argument('levity', nargs='+')
	ap.add_argument('--scenario')
	ap.add_argument('--seed')
	ap.add_argument('--size', default='1800x1090')
	ap.add_argument('--settle', type=float, default=5.0)
	ap.add_argument('--glow', action='store_true')
	ap.add_argument('--one', action='store_true', help=argparse.SUPPRESS)
	a = ap.parse_args()
	if a.one:
		a.levity = a.levity[0]
		return one(a)
	rc = 0
	for path in a.levity:
		cmd = [sys.executable, str(Path(__file__).resolve()), a.out, path, '--one', '--size', a.size, '--settle', str(a.settle)]
		for flag in ('scenario', 'seed'):
			if getattr(a, flag):
				cmd += [f'--{flag}', getattr(a, flag)]
		if a.glow:
			cmd.append('--glow')
		rc |= subprocess.call(cmd)
	return rc


if __name__ == '__main__':
	sys.exit(main())
