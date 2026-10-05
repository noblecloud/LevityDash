#!/usr/bin/env python
"""Dev-only: time Gauge Studio's build, in-place edit and settle paths, offscreen.

    QT_QPA_PLATFORM=offscreen PYTHONPATH=src python src/LevityDash/devtools/bench_gauge_studio.py [--cell N] [--runs 5] [--profile build|edit|settle] [--all]
"""
import argparse
import cProfile
import copy
import pstats
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _studio_env

_studio_env.prepare()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PySide6.QtWidgets import QApplication

from LevityDash.devtools import gauge_studio as gs

app = QApplication.instance() or QApplication(sys.argv)


def pump(n=3):
	for _ in range(n):
		app.processEvents()


def median(fn, runs):
	times = []
	for _ in range(runs):
		t = time.perf_counter()
		fn()
		times.append((time.perf_counter() - t) * 1000)
	return statistics.median(times), min(times), max(times)


def main():
	p = argparse.ArgumentParser()
	p.add_argument('--cell', type=int, default=0)
	p.add_argument('--runs', type=int, default=5)
	p.add_argument('--profile', choices=['build', 'edit', 'settle'])
	p.add_argument('--render', metavar='DIR', help='render every showcase cell on the studio stage to DIR/NN.png (for before/after diffs) and exit')
	p.add_argument('--render-edits', metavar='DIR', help='apply a fixed series of in-place edits to a few cells, render after each step into DIR, and exit')
	p.add_argument('--roundtrip', action='store_true', help='for every showcase cell: edit, settle, export, load the export, export again, and compare')
	p.add_argument('--only', type=int, help='with --roundtrip: one cell index; each cell in its own process avoids one failure spoiling the next')
	p.add_argument('--all', action='store_true', help='benchmark every showcase cell (build only)')
	a = p.parse_args()
	cells = gs.showcaseCells()
	studio = gs.Studio()
	studio.show()
	pump()
	if a.roundtrip:
		bad = 0
		for i, (label, entry) in enumerate(cells):
			if a.only is not None and i != a.only:
				continue
			try:
				studio.loadDisplay(copy.deepcopy(entry.get('display') or {}), entry.get('key'), label)
				pump()
				if ('arc', 'weight') in studio.rows:
					studio._edited(('arc', 'weight'), '7%')
					studio._flush()
				studio.settle()
				first = studio.exportDisplay()
				shot = studio.studio.render()
				studio.loadDisplay(copy.deepcopy(first), entry.get('key'), label)
				pump()
				second = studio.exportDisplay()
				same = first == second and studio.studio.render() == shot
				import hashlib, json
				digest = hashlib.md5(json.dumps(first, sort_keys=True, default=str).encode() + bytes(shot.constBits())).hexdigest()[:10]
				print(f'{i:2d} {label[:30]:30s} {"round-trips" if same else "DIFFERS"} {digest}')
				bad += not same
			except Exception as e:  # noqa: BLE001
				print(f'{i:2d} {label[:30]:30s} FAILED {type(e).__name__}: {str(e)[:60]}')
				bad += 1
		print(f'{bad} of {len(cells)} cells did not round-trip')
		return
	if a.render_edits:
		out = Path(a.render_edits)
		out.mkdir(parents=True, exist_ok=True)
		steps = [
			(('arc', 'weight'), '9%'), (('arc', 'weight'), '4%'), (('arc', 'start'), 120), (('arc', 'start'), 150),
			(('value-label', 'position'), 'center'), (('value-label', 'position'), 'below'),
			(('major', 'labels', 'position'), 'inside'), (('major', 'labels', 'position'), 'outside'),
		]
		for i in (0, 3, 20, 27):
			label, entry = cells[i]
			studio.loadDisplay(copy.deepcopy(entry.get('display') or {}), entry.get('key'), label)
			pump()
			for n, (path, value) in enumerate(steps):
				if path not in studio.rows:
					continue
				studio._edited(path, value)
				studio._flush()
				studio.studio.render().save(str(out / f'{i:02d}-{n}.png'))
		return
	if a.render:
		out = Path(a.render)
		out.mkdir(parents=True, exist_ok=True)
		for i, (label, entry) in enumerate(cells):
			studio.loadDisplay(copy.deepcopy(entry.get('display') or {}), entry.get('key'), label)
			pump()
			studio.studio.render().save(str(out / f'{i:02d}.png'))
		return
	if a.all:
		for i, (label, entry) in enumerate(cells):
			d = entry.get('display') or {}
			m = median(lambda: studio.loadDisplay(copy.deepcopy(d), entry.get('key'), label), 3)
			print(f'{i:2d} {label[:40]:40s} load {m[0]:7.1f} ms')
		return
	label, entry = cells[a.cell]
	display = copy.deepcopy(entry.get('display') or {})
	key = entry.get('key')
	print(f'cell {a.cell}: {label}')
	studio.loadDisplay(copy.deepcopy(display), key, label)
	pump()
	preset = studio.studio.preset

	def build():
		studio.studio.build(copy.deepcopy(display), preset)

	def mk(path, gen):
		def run():
			studio._edited(path, gen())
			studio._flush()
		return run

	def setval():
		lo, hi = studio.studio.range
		studio.setValue(lo + (hi - lo) * (0.3 + 0.4 * (time.perf_counter() % 1)))

	tests = {
		'build (gauge from display)': build,
		'value change': setval,
		'exportDisplay': studio.exportDisplay,
		'settle (export+rebuild+sync)': studio.settle,
		'_afterBuild (panel rebuild)': studio._afterBuild,
		'syncRows': studio.syncRows,
	}
	edits = {
		('arc', 'weight'): lambda: f'{random.randint(3, 12)}%',
		('arc', 'start'): lambda: random.randint(100, 140),
		('value-label', 'position'): lambda: random.choice(['below', 'center', 'above']),
		('major', 'labels', 'position'): lambda: random.choice(['outside', 'inside']),
	}
	for path, gen in edits.items():
		if path in studio.rows:
			tests['edit ' + '.'.join(path)] = mk(path, gen)
	if a.profile:
		fn = {'build': build, 'settle': studio.settle, 'edit': tests.get('edit arc.weight')}[a.profile]
		fn()
		pr = cProfile.Profile()
		pr.enable()
		for _ in range(a.runs):
			fn()
		pr.disable()
		for sort in ('cumtime', 'tottime'):
			pstats.Stats(pr).sort_stats(sort).print_stats(40)
		return
	for name, fn in tests.items():
		try:
			fn()
			pump()
			m = median(fn, a.runs)
		except Exception as e:  # noqa: BLE001 - a gauge whose export does not round-trip fails settle; say so and go on
			print(f'{name:36s} FAILED {type(e).__name__}: {e}')
			continue
		print(f'{name:36s} median {m[0]:8.1f} ms  (min {m[1]:.1f}, max {m[2]:.1f})')


main()
