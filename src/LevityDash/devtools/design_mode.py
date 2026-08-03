#!/usr/bin/env python
"""Dev-only: a real, interactive window over one `.levity` fragment that
reloads itself whenever the file changes on disk.

For prototyping a single panel/section rather than a whole dashboard - point
this at a fragment (same shape as anything under `docs/design-references/`)
and get a live window: edit the file in your own editor, save, watch it
update in place. No PNGs, no HTTP - just the real frontend, reloading itself.

    poetry run python src/LevityDash/devtools/design_mode.py \\
        docs/design-references/temperature-column.levity --seed <config-copy>

This calls the exact same `CentralPanel.reload()` that `Ctrl+R` and the file
watcher use - which is why it's safe to fire on every save now and wasn't
before today: reload() used to strand orphaned panels and drop a fallback
match's state on anything but a trivial change (see
docs/tasks/dashboard-wont-load.md history). A design session that reloads
dozens of times is exactly the case that used to break.

`--seed` is required, same reasoning as the render devtools: this boots a
*real* dashboard, and without a seed it would read and write your live config.
"""
import argparse
import os
import sys
from pathlib import Path

# Same ordering rule as every other devtools entry point: --seed must reach the
# environment before the first LevityDash import. See _seed.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _seed import seedEnvironment

seedEnvironment()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from LevityDash.devtools._boot import DEFAULT_SIZE, boot


def _parseSize(text: str):
	width, _, height = text.lower().partition('x')
	return int(width), int(height)


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument('levity', help='the .levity fragment to watch and display')
	parser.add_argument('--seed', required=True, help='config dir copy to run against (never the real config)')
	parser.add_argument('--size', default='x'.join(map(str, DEFAULT_SIZE)), help='window size')
	parser.add_argument('--settle', type=float, default=6.0, help='seconds to let the initial load settle')
	parser.add_argument('--plugins', action='store_true', help='start plugins for live values')
	parser.add_argument('--interval', type=float, default=500, help='file-change poll interval, in ms')
	parser.add_argument(
		'--full-reload', action='store_true',
		help='wipe and rebuild from scratch on every change instead of reconciling. '
		     'Slower and drops any in-place UI state, but skips panel-matching entirely - '
		     'the right choice while restructuring a fragment (adding/removing/retyping '
		     'items) rather than tweaking values on an unchanged structure.',
	)
	args = parser.parse_args()

	source = Path(args.levity)
	if not source.exists():
		parser.error(f'no such file: {source}')

	app, dashboard = boot(
		seed=args.seed, size=_parseSize(args.size),
		settle=args.settle, plugins=args.plugins, windowed=True,
	)

	# NOT boot(levity=source): that copies the fragment into the seed's
	# default.levity once at startup, and every later reload() would just
	# re-read that one stale copy - edits to `source` would never show up.
	# Loading `source` directly here makes it CentralPanel.filePath from this
	# point on, so reload() (which re-reads self.filePath fresh every call)
	# always sees the file's current, live content.
	dashboard.CENTRAL_PANEL._load(source)

	from PySide6.QtCore import QTimer

	state = {'mtime': source.stat().st_mtime}

	def checkForChanges():
		try:
			mtime = source.stat().st_mtime
		except FileNotFoundError:
			return
		if mtime != state['mtime']:
			state['mtime'] = mtime
			panel = dashboard.CENTRAL_PANEL
			if args.full_reload:
				print(f'{source.name} changed, wiping and rebuilding...')
				# _load only clears when the path differs from what's already
				# loaded (see its own docstring/history); the path here never
				# changes between calls, so that check alone would just
				# reconcile. Calling clear() first forces a full rebuild
				# regardless, bypassing the panel-matcher entirely.
				panel.clear()
				panel._load(source)
			else:
				print(f'{source.name} changed, reloading...')
				panel.reload()

	timer = QTimer()
	timer.timeout.connect(checkForChanges)
	timer.start(int(args.interval))

	print(f'watching {source} - edit and save to see it update. Close the window or ctrl-c to stop.')
	return app.exec()


if __name__ == '__main__':
	raise SystemExit(main())
