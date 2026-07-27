#!/usr/bin/env python
"""Dev-only: render a single panel/widget from a dashboard to a PNG.

Iterating on one gauge or one panel is much easier when you're looking at just
that panel — a full-dashboard render buries a 200px cell in 1.8 megapixels, and
you end up cropping by hand every time.

Items are addressed by the `name:` in the `.levity`. Use `--list` to see what's
available; not every item has a name, and names aren't enforced unique.

Usage:
    # what can I render?
    poetry run python src/LevityDash/devtools/render_widget.py --list --seed DIR

    # one panel, at 2x so small text is legible
    poetry run python src/LevityDash/devtools/render_widget.py \\
        --name terrarium --out terrarium.png --scale 2 --seed DIR

    # every named item at once, into a directory
    poetry run python src/LevityDash/devtools/render_widget.py \\
        --all --out-dir widgets/ --seed DIR

`--pad` adds context around the item, which matters for judging *placement* —
a label's binding depends on its distance to neighbours, so a pixel-tight crop
can make bad spacing look fine. Render with padding when reviewing proximity,
without when reviewing the item itself.
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

from LevityDash.devtools._boot import DEFAULT_SIZE, boot, named_items, render_rect


def _parse_size(text: str):
	width, _, height = text.lower().partition('x')
	return int(width), int(height)


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument('--name', help='name: of the item to render')
	parser.add_argument('--all', action='store_true', help='render every named item')
	parser.add_argument('--list', action='store_true', help='list renderable item names and exit')
	parser.add_argument('--out', help='PNG path (single item)')
	parser.add_argument('--out-dir', help='directory for --all')
	parser.add_argument('--scale', type=float, default=1.0, help='upscale factor; 2 makes small text legible')
	parser.add_argument('--pad', type=float, default=0.0, help='pixels of surrounding context to include')
	parser.add_argument('--levity', help='candidate .levity to render (requires --seed)')
	parser.add_argument('--seed', help='config dir copy to render against; omit for the real config')
	parser.add_argument('--size', default='x'.join(map(str, DEFAULT_SIZE)), help='window size driving layout')
	parser.add_argument('--settle', type=float, default=6.0)
	parser.add_argument('--plugins', action='store_true', help='start plugins for real values')
	args = parser.parse_args()

	if not (args.list or args.all or args.name):
		parser.error('need one of --list, --name, or --all')
	if args.name and not args.out:
		parser.error('--name needs --out')
	if args.all and not args.out_dir:
		parser.error('--all needs --out-dir')

	try:
		app, dashboard = boot(
			seed=args.seed, levity=args.levity, size=_parse_size(args.size),
			settle=args.settle, plugins=args.plugins,
		)
	except ValueError as e:
		parser.error(str(e))

	scene = dashboard.scene
	items = named_items(scene)

	if args.list:
		print(f'{len(items)} named item(s):')
		for name, item in sorted(items.items()):
			rect = item.sceneBoundingRect()
			print(f'  {name:<24} {rect.width():>6.0f} x {rect.height():<6.0f}  ({type(item).__name__})')
		return 0

	targets = items if args.all else {args.name: items.get(args.name)}
	if not args.all and targets[args.name] is None:
		print(f'no item named {args.name!r}. Available: {", ".join(sorted(items)) or "(none)"}', file=sys.stderr)
		return 1

	if args.all:
		out_dir = Path(args.out_dir)
		out_dir.mkdir(parents=True, exist_ok=True)

	for name, item in targets.items():
		rect = item.sceneBoundingRect()
		if args.pad:
			rect = rect.adjusted(-args.pad, -args.pad, args.pad, args.pad)
		out = str(Path(args.out_dir) / f'{name}.png') if args.all else args.out
		if render_rect(scene, rect, out, scale=args.scale):
			print(f'rendered {name} -> {out}  ({rect.width():.0f}x{rect.height():.0f} @{args.scale:g}x)')
		else:
			print(f'failed to write {out}', file=sys.stderr)
			return 1
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
