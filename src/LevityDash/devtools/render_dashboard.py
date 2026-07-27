#!/usr/bin/env python
"""Dev-only: render a whole `.levity` dashboard to a PNG, headless.

For one panel rather than the whole board, use `render_widget.py` — a 200px
cell buried in 1.8 megapixels is hard to judge.

Usage:
    poetry run python src/LevityDash/devtools/render_dashboard.py OUT.png
    poetry run python src/LevityDash/devtools/render_dashboard.py OUT.png --levity CAND.levity --seed DIR
    poetry run python src/LevityDash/devtools/render_dashboard.py OUT.png --size 1800x1090 --plugins

Rendering notes (why this doesn't use `view.grab()`), and the caveat about
`QGraphicsEffect`s, are in `_boot.render_rect`.
"""
import argparse
import os
import sys
from pathlib import Path

# Before ANY LevityDash import: the QApplication is constructed during the
# package import chain and the platform cannot change afterwards. Importing
# _boot pulls in the LevityDash package to get at devtools, so setting this
# inside boot() would already be too late - it silently opened a real cocoa
# window and rendered at the wrong size.
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from LevityDash.devtools._boot import DEFAULT_SIZE, boot, render_rect


def _parse_size(text: str):
	width, _, height = text.lower().partition('x')
	return int(width), int(height)


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument('out', help='PNG path to write')
	parser.add_argument('--levity', help='candidate .levity to render (requires --seed)')
	parser.add_argument('--seed', help='config dir copy to render against; omit for the real config')
	parser.add_argument('--size', default='x'.join(map(str, DEFAULT_SIZE)), help='window size driving layout')
	parser.add_argument('--settle', type=float, default=6.0)
	parser.add_argument('--scale', type=float, default=1.0)
	parser.add_argument('--plugins', action='store_true', help='start plugins for real values')
	args = parser.parse_args()

	try:
		app, dashboard = boot(
			seed=args.seed, levity=args.levity, size=_parse_size(args.size),
			settle=args.settle, plugins=args.plugins,
		)
	except ValueError as e:
		parser.error(str(e))

	scene = dashboard.scene
	rect = scene.sceneRect()
	if not render_rect(scene, rect, args.out, scale=args.scale):
		print(f'failed to write {args.out}', file=sys.stderr)
		return 1
	print(f'rendered {args.out}  ({rect.width():.0f}x{rect.height():.0f} @{args.scale:g}x)')
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
