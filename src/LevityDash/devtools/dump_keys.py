#!/usr/bin/env python
"""Dev-only: list every key the configured plugins publish, with its source, unit and current value.

Boots the dashboard offscreen with the real plugins (against a copy of the config, so nothing is written to it),
waits for them to report, and prints one line per key: what a `.levity` can actually read on this machine.

Usage:
    poetry run python src/LevityDash/devtools/dump_keys.py --seed "~/Library/Application Support/LevityDash" \\
        --wait 90 --out keys.tsv

Columns: key, state (live/waiting/off), sources, unit, shape, value, forecast points, history points.
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _seed import seedEnvironment

seedEnvironment()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from LevityDash.devtools._boot import boot, pump, shutdown
from LevityDash.devtools._studio_keys import collectKeys


def _points(dispatcher, key: str, attr: str) -> str:
	try:
		multi = dispatcher.get(key)
		best = 0
		for _, container in multi.items():
			series = getattr(container, attr, None)
			if series is not None:
				best = max(best, len(series))
		return str(best)
	except Exception:  # noqa: BLE001 - not every key keeps a series
		return ''


def main():
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument('--seed', required=True, help='config dir to copy from (never written to)')
	parser.add_argument('--wait', type=float, default=90.0, help='seconds to let the plugins report')
	parser.add_argument('--out', help='write the table here instead of stdout')
	args = parser.parse_args()

	# An empty dashboard: the keys come from the plugins, not from what a dashboard happens to show.
	empty = Path(tempfile.mkdtemp()) / 'keys.levity'
	empty.write_text('- type: text\n  text: keys\n')
	app, dashboard = boot(seed=os.path.expanduser(args.seed), levity=str(empty), plugins=True, settle=2.0)
	try:
		pump(app, args.wait)
		rows = collectKeys(dashboard.dispatcher, dashboard.plugins)
		lines = ['key\tstate\tsources\tunit\tshape\tvalue\tforecast\thistory']
		for info in rows:
			lines.append('\t'.join([
				info.key, info.state, ','.join(info.sourceNames), info.unit, info.shape,
				info.value.replace('\t', ' ').replace('\n', ' '),
				_points(dashboard.dispatcher, info.key, 'forecast'),
				_points(dashboard.dispatcher, info.key, 'historical'),
			]))
		text = '\n'.join(lines) + '\n'
		if args.out:
			Path(args.out).write_text(text)
			print(f'{len(rows)} keys written to {args.out}')
		else:
			sys.stdout.write(text)
	finally:
		shutdown(dashboard)


if __name__ == '__main__':
	main()
