#!/usr/bin/env python
"""Dev-only: render a whole `.levity` dashboard to a PNG, headless.

For one panel rather than the whole board, use `render_widget.py` — a 200px
cell buried in 1.8 megapixels is hard to judge.

Usage:
    poetry run python src/LevityDash/devtools/render_dashboard.py OUT.png
    poetry run python src/LevityDash/devtools/render_dashboard.py OUT.png --levity CAND.levity --seed DIR
    poetry run python src/LevityDash/devtools/render_dashboard.py OUT.png --size 1800x1090 --plugins
    poetry run python src/LevityDash/devtools/render_dashboard.py OUT.png --levity CAND.levity --scenario stormy-day
    poetry run python src/LevityDash/devtools/render_dashboard.py OUT.png --levity CAND.levity --theme dusk

`--scenario` feeds fixed values from `docs/design-references/scenarios/` through
the Fixture plugin instead of a live backend, so the render is repeatable. It
starts no other plugin. See `lib/plugins/builtin/Fixture.py`.

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

# --seed must reach the environment before the first LevityDash import, for the
# same reason QT_QPA_PLATFORM must - see _seed.py. Imported from this directory
# so it does not pull in the package it is configuring.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _seed import seedEnvironment

seedEnvironment()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from LevityDash.devtools._boot import DEFAULT_SIZE, FROZEN_TIME, boot, render_rect, shutdown


def _parse_size(text: str):
	width, _, height = text.lower().partition('x')
	return int(width), int(height)


def _parse_when(text: str):
	"""An ISO instant for --freeze-time, or _boot.FROZEN_TIME for 'default'."""
	from datetime import datetime

	if text in ('', 'default', None):
		return FROZEN_TIME
	when = datetime.fromisoformat(text)
	return when if when.tzinfo else when.astimezone()


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument('out', help='PNG path to write')
	parser.add_argument('--levity', help='candidate .levity to render (requires --seed)')
	parser.add_argument('--seed', help='config dir copy to render against; omit for the real config')
	parser.add_argument('--scenario', help='fixed values for every key: a docs/design-references/scenarios name or a YAML path (turns on the Fixture plugin; seeds from devtools/design-seed unless --seed)')
	parser.add_argument('--size', default='x'.join(map(str, DEFAULT_SIZE)), help='scene size driving layout (the window is sized to match)')
	parser.add_argument('--theme', help='force a colour theme (a name from resources/themes or <config>/themes) over the dashboard\'s own `theme:`')
	parser.add_argument('--settle', type=float, default=6.0)
	parser.add_argument('--scale', type=float, default=1.0)
	parser.add_argument('--plugins', action='store_true', help='start plugins for real values')
	parser.add_argument(
		'--freeze-time', nargs='?', const='default', metavar='ISO',
		help='pin the app clock (default: _boot.FROZEN_TIME) so two renders of the same file agree; '
			'the same patches as tests/conftest.py\'s frozen_time. Omit for a live clock',
	)
	args = parser.parse_args()

	if args.theme:
		from LevityDash.lib.ui.colors import theme

		try:
			theme.set_override(args.theme)
		except theme.ThemeError as e:
			parser.error(str(e))

	try:
		app, dashboard = boot(
			seed=args.seed, levity=args.levity, size=_parse_size(args.size),
			settle=args.settle, plugins=args.plugins,
			freeze=_parse_when(args.freeze_time) if args.freeze_time else None,
		)
	except ValueError as e:
		parser.error(str(e))

	try:
		scene = dashboard.scene
		rect = scene.sceneRect()
		if not render_rect(scene, rect, args.out, scale=args.scale):
			print(f'failed to write {args.out}', file=sys.stderr)
			return 1
		print(f'rendered {args.out}  ({rect.width():.0f}x{rect.height():.0f} @{args.scale:g}x)')
		return 0
	finally:
		shutdown(dashboard)


if __name__ == '__main__':
	raise SystemExit(main())
