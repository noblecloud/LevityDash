#!/usr/bin/env python
"""Dev-only: render every gauge preset and the showcase, then compare two captures
pixel by pixel. The safety net for the meter refactor (`docs/tasks/meter-and-bar.md`):
that work may move code, it may not move pixels.

    render_diff.py capture BEFORE/           # 22 presets + the showcase -> PNGs
    render_diff.py capture AFTER/
    render_diff.py compare BEFORE/ AFTER/    # exit 1 on any real difference
    render_diff.py selfcheck WORK/           # capture twice, compare: is the harness stable?

What makes two captures comparable
----------------------------------
- **Fixed values.** Every capture writes `_scenario.yaml` into its own directory:
  the weather keys of `stormy-day` and `gauge-cards`, merged with every key of
  the Mock plugin's own table (`Mock.MOCK_KEYS`, parsed from source, not copied)
  at its `base` value. Nothing then depends on Mock's sine waves, its per-run
  `random` phases or the wall clock.
- **Mock is switched off.** The design seed enables it (`Mock.ini`), and
  `_boot.startFixture` starts it beside the scenario, which is how two showcase
  renders of unchanged code came to differ by ~48k pixels. Each capture stages
  its own copy of the seed (`_seed/`) with `enabled = False`.
- **A frozen clock** (`--freeze-time`, see `_boot.freeze_time`; pass
  `--no-freeze-time` to leave it live).
- **A settle long enough for `animate:`** (`wrap-compass.levity` sets 800ms).
- **Clock markers pinned with `at:`.** One that is not pinned keeps its hands on
  the wall clock (the freeze cannot reach `GaugeMarker._tickClock`'s
  function-local import), so `selfcheck` names any file that differs between two
  captures of the same code - fix the file, do not loosen the comparison.

Sizes: the showcase at its documented 2560x1440, every preset at 1600x900 (the
size the presets' own header comments document). `--size WxH` overrides both.

A capture directory holds `<stem>.png` per target plus `_manifest.json` (inputs,
hashes, per-file ink) and the `_scenario.yaml` / `_seed/` it ran with. Nothing
outside the directory is written, and no produced file is deleted.
"""
import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import yaml

#: `QT_QPA_PLATFORM` must be set before the first PySide6 import, and comparing
#: images wants QImage - set it here rather than relying on the child renders.
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

HERE = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[3]

PRESET_DIR = REPO / 'docs' / 'design-references' / 'presets'
SHOWCASE = REPO / 'docs' / 'design-references' / 'gauge-showcase.levity'
SCENARIO_DIR = REPO / 'docs' / 'design-references' / 'scenarios'
DESIGN_SEED = HERE / 'design-seed'
RENDERER = HERE / 'render_dashboard.py'
MOCK_SOURCE = REPO / 'src' / 'LevityDash' / 'lib' / 'plugins' / 'builtin' / 'Mock.py'

#: The scenarios the presets' own headers name, merged in this order to build
#: `_scenario.yaml`. `stormy-day` first: it is the fuller weather set (24-point
#: series, which the `at(key, -3h)` markers on several presets want).
BASE_SCENARIOS = ('stormy-day', 'gauge-cards')

SHOWCASE_SIZE = (2560, 1440)
PRESET_SIZE = (1600, 900)
DEFAULT_SETTLE = 14.0

#: A pixel counts as different when a channel differs by more than this many
#: levels. 30 is the figure the meter brief measured the Mock drift with.
DEFAULT_LEVEL = 30
DEFAULT_TOLERANCE = 0

#: When a render's scenario values arrive: `_boot.boot` injects them *after* the
#: dashboard has settled (`LEVITYDASH_FIXTURE_DELAY_MS=end`).
#:
#: Not a settle tweak. A display formats a value once, when it arrives, and never
#: re-formats it, so a value that lands before the display has resolved its
#: configured unit - or its unit metadata - keeps whatever it printed first:
#: `ev.charge.range` read `313` (km) in some runs and `194` (mi, the unit
#: `[Units] length = mi` asks for) in others, and its caption read `313` against
#: `313 km`. Both flipped ~50/50 at the default 50ms publish, and were still
#: flipping under a several-second delay once six renders shared the machine.
#: Injecting the values last removes the race by construction rather than by
#: guessing a margin.
FIXTURE_DELAY_MS = 'end'


# --------------------------------------------------------------------------- #
# the scenario a capture runs with


def mock_keys() -> Dict[str, dict]:
	"""The Mock plugin's key table, read out of its source.

	Read rather than imported on purpose: importing that module pulls the
	LevityDash package (and with it a QApplication) into this process, which
	would then have to be offscreen and is never used for anything else.

	`MOCK_KEYS` is a dict of `dict(unit=..., base=..., ...)` calls, so
	`ast.literal_eval` cannot read it. The assignment's right-hand side is
	compiled and run instead, with an empty `__builtins__` bar `dict`: anything
	other than plain literals and `dict(...)` in that table raises NameError
	here and now, which is the loud failure wanted when its shape changes.
	"""
	source = MOCK_SOURCE.read_text()
	tree = ast.parse(source)
	node = None
	for statement in tree.body:
		if isinstance(statement, ast.AnnAssign) and getattr(statement.target, 'id', None) == 'MOCK_KEYS':
			node = statement.value
		elif isinstance(statement, ast.Assign) and any(getattr(t, 'id', None) == 'MOCK_KEYS' for t in statement.targets):
			node = statement.value
		if node is not None:
			break
	if node is None:
		raise RuntimeError(f'no MOCK_KEYS assignment found in {MOCK_SOURCE}')
	segment = ast.get_source_segment(source, node)
	namespace: dict = {}
	exec(f'MOCK_KEYS = {segment}', {'__builtins__': {}, 'dict': dict}, namespace)  # noqa: S102 - our own source, literal table
	return namespace['MOCK_KEYS']


def build_scenario() -> dict:
	"""`_scenario.yaml`'s contents: base scenarios + every Mock key at its base.

	A key already named by a base scenario wins: those entries carry a series and
	a title, and matching them keeps the diff.scenario and the design renders
	reading the same values.
	"""
	keys: Dict[str, dict] = {}
	for name in BASE_SCENARIOS:
		with open(SCENARIO_DIR / f'{name}.yaml') as file:
			keys.update(yaml.safe_load(file)['keys'])
	added = []
	for key, spec in mock_keys().items():
		if key in keys:
			continue
		# Only the fields the schema builder reads (`Fixture.buildSchema`).
		keys[key] = {'value': spec['base'], 'unit': spec['unit'], 'title': spec.get('title', key)}
		added.append(key)
	return {
		'name': 'diff-stable',
		'description': (
			'Fixed values for render_diff.py: the stormy-day and gauge-cards weather keys, plus '
			f'every Mock key at its base value ({len(added)} added). Nothing here changes with the clock.'
		),
		'keys': dict(sorted(keys.items())),
	}


#: `[Units] length = mi` in the design seed is the only preferred unit a scenario
#: value disagrees with (`ev.charge.range`, km, straight from Mock's own table),
#: and a display that resolves its configured unit before the value arrives
#: converts while one that does not keeps the source unit - the text is never
#: recomputed either way. `stage_seed` therefore pins the staged seed's `length`
#: to whatever unit the scenario itself supplies, so both outcomes print the same
#: text. Same class of fix would be needed per dimension if another one turns up.
LENGTH_UNITS = ('mi', 'km', 'm', 'mm', 'in', 'ft')


def length_unit_in(scenario: dict) -> Optional[str]:
	"""The single length unit a scenario supplies values in, or None if unclear."""
	found = {
		entry['unit'] for entry in scenario['keys'].values()
		if isinstance(entry, dict) and entry.get('unit') in LENGTH_UNITS
	}
	return found.pop() if len(found) == 1 else None


def stage_seed(directory: Path, scenario: Optional[dict] = None) -> Path:
	"""A copy of `design-seed`, with Mock off and `[Units]` pinned. Returns its path."""
	if directory.exists():
		shutil.rmtree(directory)
	shutil.copytree(DESIGN_SEED, directory)
	mock_ini = directory / 'plugins' / 'Mock.ini'
	mock_ini.parent.mkdir(parents=True, exist_ok=True)
	mock_ini.write_text('[plugin]\nenabled = False\n')
	if scenario is not None and (unit := length_unit_in(scenario)):
		config_ini = directory / 'config.ini'
		text = config_ini.read_text()
		if re.search(r'^length\s*=', text, re.M):
			config_ini.write_text(re.sub(r'^length\s*=.*$', f'length = {unit}', text, flags=re.M))
	return directory


def digest_tree(directory: Path) -> str:
	"""A stable hash of every file under `directory` (paths and contents)."""
	accumulator = hashlib.sha256()
	for path in sorted(p for p in directory.rglob('*') if p.is_file()):
		accumulator.update(str(path.relative_to(directory)).encode())
		accumulator.update(hashlib.sha256(path.read_bytes()).digest())
	return accumulator.hexdigest()


# --------------------------------------------------------------------------- #
# image IO (Qt loads the PNG, numpy does the arithmetic)


def load_rgb(path: Path) -> np.ndarray:
	from PySide6.QtGui import QImage

	image = QImage(str(path))
	if image.isNull():
		raise RuntimeError(f'{path}: not a readable image')
	image = image.convertToFormat(QImage.Format.Format_RGBA8888)
	height, width = image.height(), image.width()
	row = image.bytesPerLine()
	buffer = np.frombuffer(image.constBits().tobytes(), dtype=np.uint8).reshape(height, row // 4, 4)
	return buffer[:, :width, :3].copy()


def save_rgb(array: np.ndarray, path: Path) -> None:
	from PySide6.QtGui import QImage

	height, width, _ = array.shape
	rgba = np.empty((height, width, 4), dtype=np.uint8)
	rgba[:, :, :3] = array
	rgba[:, :, 3] = 255
	image = QImage(rgba.tobytes(), width, height, width * 4, QImage.Format.Format_RGBA8888)
	if not image.save(str(path)):
		raise RuntimeError(f'failed to write {path}')


def ink_of(array: np.ndarray) -> float:
	"""Share of pixels that are not (near) black - a blank render reads ~0."""
	return float((array.max(axis=2) > 8).mean())


# --------------------------------------------------------------------------- #
# capture


def targets(only: Optional[Sequence[str]] = None) -> List[Path]:
	found = sorted(PRESET_DIR.glob('*.levity')) + [SHOWCASE]
	if only:
		wanted = {name.lower() for name in only}
		found = [p for p in found if p.stem.lower() in wanted]
		if not found:
			raise SystemExit(f'--only matched nothing; presets are:\n  ' + '\n  '.join(p.stem for p in sorted(PRESET_DIR.glob('*.levity'))))
	return found


def size_for(target: Path, override: Optional[Tuple[int, int]]) -> Tuple[int, int]:
	if override:
		return override
	return SHOWCASE_SIZE if target.stem == 'gauge-showcase' else PRESET_SIZE


def render_command(
	target: Path, out: Path, seed: Path, scenario: Path, size: Tuple[int, int],
	settle: float, scale: float, freeze: Optional[str], python: str,
) -> List[str]:
	command = [
		python, str(RENDERER), str(out),
		'--levity', str(target),
		'--seed', str(seed),
		'--scenario', str(scenario),
		'--size', f'{size[0]}x{size[1]}',
		'--settle', str(settle),
	]
	if scale != 1.0:
		command += ['--scale', str(scale)]
	if freeze:
		command += ['--freeze-time', freeze]
	return command


def capture(args) -> int:
	out_dir = Path(args.directory).expanduser().resolve()
	out_dir.mkdir(parents=True, exist_ok=True)
	size_override = None
	if args.size:
		width, _, height = args.size.lower().partition('x')
		size_override = (int(width), int(height))

	scenario = build_scenario()
	scenario_path = out_dir / '_scenario.yaml'
	scenario_path.write_text(yaml.safe_dump(scenario, sort_keys=False, width=120))
	seed_dir = stage_seed(out_dir / '_seed', scenario)

	selected = targets(args.only)
	freeze = None if args.no_freeze_time else (args.freeze_time or 'default')
	manifest = {
		'created': time.strftime('%Y-%m-%dT%H:%M:%S'),
		'commit': subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip(),
		'inputs': {
			'scenario': hashlib.sha256(scenario_path.read_bytes()).hexdigest(),
			'seed': digest_tree(seed_dir),
			'settle': args.settle,
			'scale': args.scale,
			'freeze_time': freeze or 'live',
			'fixture_delay_ms': FIXTURE_DELAY_MS,
			'size': args.size or 'per-target',
			'python': sys.version.split()[0],
		},
		'files': {},
	}
	manifest_path = out_dir / '_manifest.json'

	def run(target: Path) -> Tuple[str, dict]:
		size = size_for(target, size_override)
		out = out_dir / f'{target.stem}.png'
		command = render_command(target, out, seed_dir, scenario_path, size, args.settle, args.scale, freeze, args.python)
		started = time.monotonic()
		completed = subprocess.run(command, capture_output=True, text=True, env={**os.environ, 'LEVITYDASH_FIXTURE_DELAY_MS': FIXTURE_DELAY_MS})
		seconds = time.monotonic() - started
		entry = {'seconds': round(seconds, 1), 'size': list(size), 'exit': completed.returncode}
		output = (completed.stdout or '') + (completed.stderr or '')
		# A render can log a traceback and still write a PNG (a plugin thread that
		# dies mid-publish, a layout that warns and carries on). Those must not
		# become a silent baseline: record and report them.
		entry['tracebacks'] = output.count('Traceback (most recent call last)')
		if entry['tracebacks']:
			lines = [line.strip() for line in output.splitlines() if line.strip()]
			entry['last_error'] = lines[-1][:200] if lines else ''
		if completed.returncode != 0 or not out.is_file():
			entry['error'] = output.strip()[-400:]
			return target.stem, entry
		try:
			image = load_rgb(out)
			entry['ink'] = round(ink_of(image), 5)
			entry['pixels'] = [image.shape[1], image.shape[0]]
			entry['sha256'] = hashlib.sha256(out.read_bytes()).hexdigest()
		except Exception as e:  # noqa: BLE001 - report, do not abort the sweep
			entry['error'] = f'{type(e).__name__}: {e}'
		return target.stem, entry

	print(f'capture -> {out_dir}  ({len(selected)} files, jobs={args.jobs}, settle={args.settle:g}, freeze={freeze})')
	failures: List[str] = []
	blank: List[str] = []
	noisy: List[str] = []
	with ThreadPoolExecutor(max_workers=args.jobs) as pool:
		for name, entry in pool.map(run, selected):
			manifest['files'][name] = entry
			if 'error' in entry:
				failures.append(name)
				print(f'  {name:<24} FAILED  {entry["error"].splitlines()[-1][:110] if entry["error"] else ""}')
			else:
				if entry.get('ink', 1) < 0.005:
					blank.append(name)
				if entry.get('tracebacks'):
					noisy.append(name)
				print(f'  {name:<24} {entry["pixels"][0]}x{entry["pixels"][1]}  ink={entry["ink"]:.3f}  {entry["seconds"]:>5.1f}s')

	manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
	print(f'wrote {manifest_path.name}')

	if noisy:
		print(f'\n⚠ {len(noisy)} render(s) logged a traceback but still produced a PNG: {", ".join(noisy)}')
		for name in noisy:
			print(f'    {name}: {manifest["files"][name].get("last_error", "")}')
		print('  A file whose render raised may still differ between two captures - fix this before baselining.')
	if blank:
		print(f'\n⚠ {len(blank)} file(s) rendered almost blank (ink < 0.005): {", ".join(blank)}')
		print('  A key they read is probably missing from _scenario.yaml - fix that before baselining.')
	if failures:
		print(f'\n✗ {len(failures)} render(s) failed: {", ".join(failures)}', file=sys.stderr)
		return 1
	return 0


# --------------------------------------------------------------------------- #
# compare


def manifests_differ(a_dir: Path, b_dir: Path) -> List[str]:
	"""Input fields the two captures disagree on. `commit` is expected to differ."""
	try:
		a = json.loads((a_dir / '_manifest.json').read_text())
		b = json.loads((b_dir / '_manifest.json').read_text())
	except (OSError, json.JSONDecodeError):
		return ['(no manifest on one side)']
	return [f'{k}: {a["inputs"].get(k)} != {b["inputs"].get(k)}' for k in sorted(set(a['inputs']) | set(b['inputs'])) if a['inputs'].get(k) != b['inputs'].get(k)]


def regions(mask, block: int = 24, gap: int = 1) -> list:
	"""Bounding boxes of the differing clusters in `mask`, as (x0, y0, x1, y1).

	Coarse blocks first, so the cost does not scale with the pixel count, then
	each cluster is tightened to exact pixel bounds. Ordered largest first.
	"""
	ys, xs = np.nonzero(mask)
	if not len(ys):
		return []
	cells = {(int(y) // block, int(x) // block) for y, x in zip(ys, xs)}
	grid = set()
	for by, bx in cells:
		for dy in range(-gap, gap + 1):
			for dx in range(-gap, gap + 1):
				grid.add((by + dy, bx + dx))
	seen, clusters = set(), []
	for cell in grid:
		if cell in seen:
			continue
		stack, cluster = [cell], []
		seen.add(cell)
		while stack:
			cy, cx = stack.pop()
			cluster.append((cy, cx))
			for dy in (-1, 0, 1):
				for dx in (-1, 0, 1):
					neighbour = (cy + dy, cx + dx)
					if neighbour in grid and neighbour not in seen:
						seen.add(neighbour)
						stack.append(neighbour)
		clusters.append(set(cluster))
	boxes = []
	for cluster in clusters:
		ys_here, xs_here = [], []
		for y, x in zip(ys, xs):
			if (int(y) // block, int(x) // block) in cluster:
				ys_here.append(int(y))
				xs_here.append(int(x))
		boxes.append((min(xs_here), min(ys_here), max(xs_here), max(ys_here)))
	return sorted(boxes, key=lambda b: -((b[2] - b[0] + 1) * (b[3] - b[1] + 1)))


def explain_regions(boxes) -> str:
	"""`x172-238 y767-782, …` for a diff row — where to look, in one line."""
	if not boxes:
		return ''
	shown = ', '.join(f'x{x0}-{x1} y{y0}-{y1}' for x0, y0, x1, y1 in boxes[:3])
	return f'  regions: {shown}' + (f' (+{len(boxes) - 3} more)' if len(boxes) > 3 else '')


def compare(args) -> int:
	a_dir, b_dir = Path(args.a).expanduser().resolve(), Path(args.b).expanduser().resolve()
	for directory in (a_dir, b_dir):
		if not directory.is_dir():
			raise SystemExit(f'{directory} is not a directory')
	diff_dir = Path(args.diff_dir).expanduser().resolve() if args.diff_dir else b_dir / '_diff'

	names_a = {p.stem for p in a_dir.glob('*.png') if not p.name.endswith('.diff.png')}
	names_b = {p.stem for p in b_dir.glob('*.png') if not p.name.endswith('.diff.png')}
	common = sorted(names_a & names_b)
	if not common:
		raise SystemExit(f'no PNGs in common between {a_dir} and {b_dir}')
	for side, names in (('only in A', names_a - names_b), ('only in B', names_b - names_a)):
		if names:
			print(f'note: {len(names)} file(s) {side}: {", ".join(sorted(names))}')

	differing_inputs = manifests_differ(a_dir, b_dir)
	if differing_inputs:
		print('⚠ the two captures were made with different inputs:')
		for line in differing_inputs:
			print(f'    {line}')
		print('  (only `commit` is expected to differ; anything else makes this comparison meaningless)\n')

	level, tolerance = args.level, args.tolerance
	rows = []
	worst = 0.0
	total_diff = 0
	with ThreadPoolExecutor(max_workers=args.jobs) as pool:
		def diff(name: str):
			a = load_rgb(a_dir / f'{name}.png')
			b = load_rgb(b_dir / f'{name}.png')
			if a.shape != b.shape:
				return name, {'shape': True, 'a': a.shape, 'b': b.shape}
			delta = np.abs(a.astype(np.int16) - b.astype(np.int16))
			mask = delta.max(axis=2) > level
			count = int(mask.sum())
			boxes = regions(mask) if count else []
			if count:
				diff_dir.mkdir(parents=True, exist_ok=True)
				save_rgb(np.clip(delta * 8, 0, 255).astype(np.uint8), diff_dir / f'{name}.diff.png')
			return name, {
				'max_level': int(delta.max()), 'count': count, 'pixels': int(mask.size),
				'share': count / mask.size, 'ink_a': ink_of(a), 'ink_b': ink_of(b),
				'regions': boxes,
			}

		for name, row in pool.map(diff, common):
			rows.append((name, row))
			if row.get('shape'):
				print(f'  {name:<24} SIZE {row["a"]} != {row["b"]}')
				continue
			total_diff += row['count']
			worst = max(worst, row['share'])
			flag = '' if row['count'] <= tolerance else '  ← differs'
			if row['count'] or args.verbose:
				print(f'  {name:<24} {row["count"]:>8} px >{level}  ({row["share"] * 100:5.2f}% of {row["pixels"]})  max Δ{row["max_level"]:<4}{flag}{explain_regions(row["regions"])}')

	shape_errors = [name for name, row in rows if row.get('shape')]
	over = [name for name, row in rows if not row.get('shape') and row['count'] > tolerance]
	print(
		f'\n{len(common)} files compared: {len(common) - len(over) - len(shape_errors)} clean, '
		f'{len(over)} over tolerance, {len(shape_errors)} with a size change'
	)
	print(f'total differing pixels (>{level} levels): {total_diff}   worst file: {worst * 100:.2f}%')
	if over or shape_errors:
		if not shape_errors:
			print(f'diff images: {diff_dir}/')
		return 1
	return 0


def selfcheck(args) -> int:
	"""Capture twice into one directory and compare: is the harness stable?"""
	work = Path(args.directory).expanduser().resolve()
	work.mkdir(parents=True, exist_ok=True)
	for half in ('a', 'b'):
		rc = capture(argparse.Namespace(**{**vars(args), 'directory': str(work / half), 'func': None}))
		if rc:
			print(f'capture {half} failed', file=sys.stderr)
			return rc
	rc = compare(argparse.Namespace(a=str(work / 'a'), b=str(work / 'b'), diff_dir=None, level=args.level, tolerance=args.tolerance, jobs=args.jobs, verbose=False))
	if rc:
		print('\n✗ two captures of the SAME code differ - the harness is not stable yet.')
		print('  The files named above are the unstable ones. Fix the cause (a clock marker')
		print('  without `at:`, an un-settled animation, a value that is not in _scenario.yaml)')
		print('  rather than raising --tolerance.')
		return rc
	print('\n✓ two captures of unchanged code match exactly - safe to baseline.')
	return 0


# --------------------------------------------------------------------------- #
# cli


def main(argv: Optional[Sequence[str]] = None) -> int:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	subparsers = parser.add_subparsers(dest='command', required=True)

	def add_capture_arguments(sub):
		sub.add_argument('directory', help='directory to write the capture into (created if missing)')
		sub.add_argument('--only', action='append', metavar='STEM', help='render only these files (repeatable)')
		sub.add_argument('--size', help=f'override every size, e.g. 1600x900 (default: showcase {SHOWCASE_SIZE[0]}x{SHOWCASE_SIZE[1]}, presets {PRESET_SIZE[0]}x{PRESET_SIZE[1]})')
		sub.add_argument('--settle', type=float, default=DEFAULT_SETTLE, help=f'seconds each render settles for (default {DEFAULT_SETTLE:g})')
		sub.add_argument('--scale', type=float, default=1.0)
		sub.add_argument('--jobs', type=int, default=min(4, (os.cpu_count() or 2)), help='renders to run at once')
		sub.add_argument('--python', default=sys.executable, help='interpreter that can import LevityDash (default: this one)')
		sub.add_argument('--no-freeze-time', action='store_true', help='leave the app clock live (renders will not be repeatable)')
		sub.add_argument('--freeze-time', metavar='ISO', help='the instant to pin the clock to (default: _boot.FROZEN_TIME)')

	capture_parser = subparsers.add_parser('capture', help='render every target into a directory')
	add_capture_arguments(capture_parser)

	compare_parser = subparsers.add_parser('compare', help='compare two capture directories')
	compare_parser.add_argument('a')
	compare_parser.add_argument('b')
	compare_parser.add_argument('--level', type=int, default=DEFAULT_LEVEL, help=f'channel delta that counts as different (default {DEFAULT_LEVEL})')
	compare_parser.add_argument('--tolerance', type=int, default=DEFAULT_TOLERANCE, help=f'differing pixels allowed per file (default {DEFAULT_TOLERANCE})')
	compare_parser.add_argument('--diff-dir', help='where to write <name>.diff.png (default: <B>/_diff)')
	compare_parser.add_argument('--jobs', type=int, default=min(4, (os.cpu_count() or 2)))
	compare_parser.add_argument('--verbose', action='store_true', help='list clean files too')

	selfcheck_parser = subparsers.add_parser('selfcheck', help='capture twice and compare - the stability test')
	add_capture_arguments(selfcheck_parser)
	selfcheck_parser.add_argument('--level', type=int, default=DEFAULT_LEVEL)
	selfcheck_parser.add_argument('--tolerance', type=int, default=DEFAULT_TOLERANCE)

	args = parser.parse_args(argv)
	if args.command == 'capture':
		return capture(args)
	if args.command == 'compare':
		return compare(args)
	if args.command == 'selfcheck':
		return selfcheck(args)
	parser.error(f'unknown command {args.command!r}')


if __name__ == '__main__':
	raise SystemExit(main())
