#!/usr/bin/env python
"""Dev-only: render a `.levity` dashboard to a PNG, headless.

Renders the scene graph straight into a `QImage` via `QGraphicsScene.render()`.
Nothing is shown, so there is no viewport and no GL context — which is what
makes this preferable to `view.grab()`:

- `view.grab()` captures the *viewport*, so it needs the window shown, and with
  the default `QOpenGLWidget` viewport under `QT_QPA_PLATFORM=offscreen` there
  is no real GL context and the grab comes back **blank white**. Working around
  that means forcing `[QtOptions] openGL = False` on the config first.
- `scene.render()` paints the items directly. No window, no GL, no config
  poking, and the output is the dashboard itself rather than the window
  (which would include the status bar).

⚠️ `QGraphicsEffect`s do not composite identically this way — the moon's glow,
for instance, renders flat. Layout, type, spacing and colour are faithful;
treat effects as approximate.

Usage:
    poetry run python src/LevityDash/devtools/render_dashboard.py OUT.png
    poetry run python src/LevityDash/devtools/render_dashboard.py OUT.png --levity CANDIDATE.levity --seed DIR
    poetry run python src/LevityDash/devtools/render_dashboard.py OUT.png --size 1800x1090

With no `--seed`, this renders the **real** config — which means real plugin
data, and on macOS the Govee plugin needs a Bluetooth-capable host (see
CLAUDE.md's Bluetooth gotcha). With `--seed`, it renders against a copy, which
is safe anywhere but may show `•••` for anything that copy has no source for.

Designing against `•••` placeholders is guesswork: long values overflow and
short ones look lost once real numbers arrive. Prefer a render with data.
"""
import argparse
import os
import shutil
import sys
import time
from pathlib import Path


def _parse_size(text: str) -> tuple[int, int]:
	width, _, height = text.lower().partition('x')
	return int(width), int(height)


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument('out', help='PNG path to write')
	parser.add_argument('--levity', help='Candidate .levity to render (copied into the seed/config first)')
	parser.add_argument('--seed', help='Config dir to render against; omit to use the real config')
	parser.add_argument('--size', default='1800x1090', help='Window size driving layout (default: 1800x1090)')
	parser.add_argument('--settle', type=float, default=6.0, help='Seconds to pump events before rendering')
	parser.add_argument('--plugins', action='store_true', help='Start plugins, for real values rather than placeholders')
	args = parser.parse_args()

	width, height = _parse_size(args.size)

	os.environ['QT_QPA_PLATFORM'] = 'offscreen'
	if args.seed:
		seed = Path(args.seed)
		os.environ['LEVITYDASH_CONFIG_DEBUG'] = '1'
		os.environ['LEVITYDASH_CONFIG_SEED'] = str(seed)
		if args.levity:
			shutil.copy(args.levity, seed / 'saves' / 'dashboards' / 'default.levity')
	elif args.levity:
		parser.error('--levity needs --seed; refusing to overwrite the real dashboard')

	from LevityDash import LevityDashboard

	LevityDashboard.init()
	LevityDashboard.plugins.load_all()
	app = LevityDashboard.app

	from PySide6.QtCore import QRectF, Qt, QTimer
	from PySide6.QtGui import QImage, QPainter

	app.init_app()
	QTimer.singleShot(10, LevityDashboard.load_dashboard)
	if args.plugins:
		QTimer.singleShot(50, LevityDashboard.plugins.start)
	# Sizing the window is what drives layout, even though it is never shown.
	app.main_window.resize(width, height)

	end = time.monotonic() + args.settle
	while time.monotonic() < end:
		app.processEvents()
		time.sleep(0.005)

	scene = LevityDashboard.scene
	rect = scene.sceneRect()
	image = QImage(rect.size().toSize(), QImage.Format.Format_ARGB32)
	image.fill(Qt.black)  # the dashboard assumes a dark ground; transparent would misread
	painter = QPainter(image)
	painter.setRenderHint(QPainter.Antialiasing)
	scene.render(painter, QRectF(image.rect()), rect)
	painter.end()

	if not image.save(args.out):
		print(f'failed to write {args.out}', file=sys.stderr)
		return 1
	print(f'rendered {args.out}  ({rect.width():.0f}x{rect.height():.0f})')
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
