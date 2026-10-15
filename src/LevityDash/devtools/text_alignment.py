#!/usr/bin/env python
"""Dev-only: measure where real text lands against its box, headless, and draw it.

Boots an empty dashboard on the Fixture scenario, builds each case of `_textalign_cases.py` (labels, relative
geometry, margins, flex and grid cells, value displays, size groups), lets the text fit settle the way a render
does, then measures every text item by painting it and finding the ink (`_textalign.py`). Prints the probes
that are not where their alignment says (`_textalign_rules.py`) and writes JSON for the tests.

Usage:
    poetry run python src/LevityDash/devtools/text_alignment.py                      # every case, print the misses
    poetry run python src/LevityDash/devtools/text_alignment.py --only align/wide    # cases whose id starts with this
    poetry run python src/LevityDash/devtools/text_alignment.py --out DIR            # also write one overlay PNG per case
    poetry run python src/LevityDash/devtools/text_alignment.py --json FILE          # the probes, for tests/devtools

Overlay colours: box blue, limit rect green, fit rect (format hint) amber dashed, painted ink red, baseline
pink, ascent/descent/strikeout grey dotted. The tests run this and assert on the JSON:
`tests/devtools/test_text_alignment.py`.
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _seed import seedEnvironment, parseFlag

if parseFlag(sys.argv, '--scenario') is None:
	sys.argv += ['--scenario', 'hot-clear-day']
seedEnvironment()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from LevityDash.devtools._boot import boot, pump, shutdown
from LevityDash.devtools._textalign import asTuple, measure, overlay, slug
from LevityDash.devtools._textalign_cases import SCENE, select
from LevityDash.devtools._textalign_rules import Probe, deviations, isEmpty, misplaced, overflow


def collectTexts(panels):
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import Text

	found = []

	def walk(item):
		for child in item.childItems():
			if isinstance(child, Text):
				if (child.text or '').strip() and child.isVisible() and not child.path().isEmpty():
					found.append(child)
			walk(child)

	for panel in panels:
		walk(panel)
	return found


def namedRects(panels) -> dict:
	"""Scene rect of every item the case named, for layout checks."""
	from LevityDash.lib.ui.frontends.PySide.Modules import Panel

	rects = {}

	def walk(item):
		for child in item.childItems():
			name = getattr(child, 'name', None)
			if isinstance(child, Panel) and isinstance(name, str) and name:
				r = child.mapRectToScene(child.rect())
				rects[name] = [round(r.x(), 3), round(r.y(), 3), round(r.width(), 3), round(r.height(), 3)]
			walk(child)

	for panel in panels:
		walk(panel)
	return rects


def runCase(app, dashboard, case, out: Path | None) -> dict:
	from LevityDash.lib.ui.frontends.PySide.Modules import Panel

	base = dashboard.scene.base
	panels = []
	try:
		from LevityDash.lib import presets

		for spec in case.panels:
			panel = Panel(parent=base, geometry=spec.geometry)
			panel.state = {'items': presets.expand(spec.items)}
			panels.append(panel)
		pump(app, 0.25)
		dashboard.view._refitAllText()
		pump(app, 0.15)
		dashboard.view._refitAllText()
		pump(app, 0.05)
		texts = collectTexts(panels)
		probes = [measure(text, case.id) for text in texts]
		image = None
		if out is not None and probes:
			image = overlay(probes, texts, out / f'{slug(case.id)}.png', title=case.id)
			for probe in probes:
				probe.overlay = str(image)
		return {'id': case.id, 'probes': [p.asDict() for p in probes], 'facts': case.facts, 'rects': namedRects(panels), 'panels': [asTuple(p.mapRectToScene(p.rect())) for p in panels]}
	finally:
		for panel in panels:
			if panel.scene() is not None:
				panel.scene().removeItem(panel)


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument('--only', default='', help='run the cases whose id starts with this')
	parser.add_argument('--out', help='write one overlay PNG per case into this folder')
	parser.add_argument('--json', help='write the probes here')
	parser.add_argument('--scenario', default='hot-clear-day')
	args = parser.parse_args()

	cases = select(args.only)
	if not cases:
		parser.error(f'no case starts with {args.only!r}')
	out = Path(args.out) if args.out else None

	with tempfile.TemporaryDirectory() as tmp:
		dashboardFile = Path(tmp) / 'empty.levity'
		dashboardFile.write_text('items: []\n')
		app, dashboard = boot(levity=str(dashboardFile), size=SCENE, settle=3.0)
		try:
			results = [runCase(app, dashboard, case, out) for case in cases]
		finally:
			shutdown(dashboard)

	if args.json:
		Path(args.json).write_text(json.dumps(results))

	bad = 0
	for result in results:
		for data in result['probes']:
			probe = Probe.fromDict(data)
			if isEmpty(probe.ink):
				print(f'EMPTY    {probe}')
				bad += 1
				continue
			missed, outside = misplaced(probe), overflow(probe)
			if missed or outside:
				bad += 1
				print(f'MISS     {probe}\n         off={ {k: round(v, 2) for k, v in missed.items()} } overflow={ {k: round(v, 2) for k, v in outside.items()} }')
	total = sum(len(r['probes']) for r in results)
	print(f'{total} probes in {len(results)} cases, {bad} off')
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
