#!/usr/bin/env python
"""Dev-only: write the laid-out rectangle of every panel in a dashboard to a text file.

A pixel diff of two renders is noisy where graphs and glows animate. Layout is not, so this is
the exact check that a layout change moved nothing:

    dump_layout.py OUT.txt --levity BOARD.levity --scenario stormy-day --size 2560x1440
    diff BEFORE.txt AFTER.txt

One line per panel: its path in the scene, its class, and its scene rectangle rounded to 0.01.
"""
import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _seed import seedEnvironment

seedEnvironment()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from LevityDash.devtools._boot import FROZEN_TIME, boot, shutdown


def walk(item, path, lines):
	rect = item.sceneBoundingRect()
	name = getattr(item, 'stateName', None) or ''
	lines.append(f'{path} {type(item).__name__} {name} {rect.x():.2f} {rect.y():.2f} {rect.width():.2f} {rect.height():.2f}')
	for index, child in enumerate(item.childItems()):
		if hasattr(child, 'sceneBoundingRect'):
			walk(child, f'{path}/{index}', lines)


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument('out')
	parser.add_argument('--levity')
	parser.add_argument('--seed')
	parser.add_argument('--scenario')
	parser.add_argument('--size', default='2560x1440')
	parser.add_argument('--settle', type=float, default=6.0)
	args = parser.parse_args()
	width, _, height = args.size.lower().partition('x')
	app, dashboard = boot(seed=args.seed, levity=args.levity, size=(int(width), int(height)), settle=args.settle, plugins=False, freeze=FROZEN_TIME)
	try:
		lines: list[str] = []
		for index, item in enumerate(dashboard.scene.items()):
			if item.parentItem() is None:
				walk(item, str(index), lines)
		Path(args.out).write_text('\n'.join(lines) + '\n')
		print(f'wrote {args.out} ({len(lines)} panels)')
		return 0
	finally:
		shutdown(dashboard)


if __name__ == '__main__':
	raise SystemExit(main())
