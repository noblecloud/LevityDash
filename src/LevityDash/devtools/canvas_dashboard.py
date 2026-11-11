#!/usr/bin/env python
"""Dev-only: draw a whole dashboard with the QPainter and the Qt Canvas Painter renderers and compare.

    xvfb-run -a python src/LevityDash/devtools/canvas_dashboard.py OUT_DIR DASH.levity [DASH2.levity ...] \\
        [--scenario hot-clear-day] [--size 1800x1090]

Boots the real windowed app on the Fixture scenario with `LEVITY_RENDERER=canvas`, so the
`CanvasSceneLayer` is the thing that paints. Writes `<name>-qt.png`, `<name>-canvas.png` and
`<name>-side.png` and prints the mean difference, the Qt render time, the Canvas record time and
what the shim could only approximate. Needs a GL context (a display, or `xvfb-run` with Mesa).
Each dashboard is a fresh process run because the app boots once per process: pass one file, or
several and this script re-runs itself for each.
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
	os.environ['LEVITY_RENDERER'] = 'canvas'
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


def one(args):
	from LevityDash.devtools._boot import boot, pump, render_image, shutdown
	from PySide6.QtCore import QRectF
	from PySide6.QtGui import QColor, QImage, QPainter

	name = Path(args.levity).stem
	app, dashboard = boot(
		seed=args.seed, levity=args.levity, size=parseSize(args.size), settle=args.settle,
		windowed=True, freeze=None,
	)
	try:
		window = app.main_window
		view = window.view
		pump(app, 4.0)  # let the fixture data arrive before either render
		layer = getattr(view, 'canvasLayer', None)
		print(f'{name}: canvasMode={view.canvasMode} layer={layer is not None}')
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
		if layer is None:
			return 1
		layer.report.clear()
		layer.recordSeconds.clear()
		layer.frames.clear()
		for _ in range(5):
			layer.update()
			pump(app, 0.15)
		img = layer.grabFramebuffer()
		img.save(str(out / f'{name}-canvas.png'))
		side = QImage(qt.width() + img.width() + 8, max(qt.height(), img.height()), QImage.Format.Format_RGB32)
		side.fill(QColor('#888'))
		p = QPainter(side)
		p.drawImage(0, 0, qt)
		p.drawImage(qt.width() + 8, 0, img)
		p.end()
		side.save(str(out / f'{name}-side.png'))
		r = layer.report
		for area, n, sec in layer.frames[:12]:
			print(f'   frame: area {area:10.0f}  items {n:5d}  {sec * 1000:6.1f} ms')
		print(f'{name}: items {len(scene.items())}  Qt {qtMs:.1f} ms  canvas record {statistics.median(layer.recordSeconds or [float("nan")]) * 1000:.1f} ms  mean diff {meanDiff(qt, img):.1f}/255  canvas {img.width()}x{img.height()}')
		for k, n in r.lossy.most_common(8):
			print(f'   lossy   {n // 5:5d}/frame  {k}')
		for k, n in r.missing.most_common(8):
			print(f'   MISSING {n // 5:5d}/frame  {k}')
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
		rc |= subprocess.call(cmd)
	return rc


if __name__ == '__main__':
	raise SystemExit(main())
