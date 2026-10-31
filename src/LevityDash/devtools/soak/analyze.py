"""Turn a soak run's files into pass/fail checks and ``report.md``.

Pure functions over the JSON lines the probes wrote (``backend-probe.jsonl``, ``frontend-probe.jsonl``,
``procs.jsonl``) and the two ``*.out`` logs, so it can be re-run on an old output directory:

    python analyze.py <out>

Each check returns ``(status, detail)`` with status ``PASS``, ``WARN`` or ``FAIL``. Only ``FAIL`` fails the run.
Trend checks ignore the warm-up (the first virtual hour or tenth of the run, whichever is longer), when the
dashboard is still loading, caches fill and the first fetches land.
"""
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

PASS, WARN, FAIL = 'PASS', 'WARN', 'FAIL'
ANSI = re.compile(r'\x1b\[[0-9;]*m')
LEVEL = re.compile(r'^\d\d/\d\d/\d\d \d\d:\d\d:\d\d\s+(DEBUG|VERBOSE|INFO|WARNING|ERROR|CRITICAL)\s+(.*)$')

#: Warnings that are known and unrelated to what a soak watches. Matched against the normalised message.
KNOWN_NOISE = [
	r'Font family .* not found',
	r"No usable weights for font family",
	r'does not support propagateSizeHints',
	r'libpyside: Failed to disconnect',
]


def load(path: Path) -> list:
	if not path.exists():
		return []
	rows = []
	for line in path.read_text().splitlines():
		try:
			rows.append(json.loads(line))
		except ValueError:
			pass  # a line cut short by the kill
	return rows


def warmup(rows: list) -> list:
	"""``rows`` after the warm-up."""
	if not rows:
		return rows
	total = rows[-1]['elapsed']
	cut = max(3600.0, total * 0.1)
	return [r for r in rows if r['elapsed'] >= cut] if total > cut * 1.5 else rows[len(rows) // 2:]


def slopePerHour(rows: list, field: str) -> float:
	"""Least squares slope of ``field`` against virtual hours."""
	xs = [r['elapsed'] / 3600 for r in rows]
	ys = [r[field] for r in rows]
	if len(xs) < 3:
		return 0.0
	mx, my = statistics.fmean(xs), statistics.fmean(ys)
	var = sum((x - mx) ** 2 for x in xs)
	return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var if var else 0.0


def edges(values: list, fraction: float = 0.2) -> tuple:
	"""Mean of the first and of the last ``fraction`` of ``values``."""
	k = max(1, int(len(values) * fraction))
	return statistics.fmean(values[:k]), statistics.fmean(values[-k:])


# --- logs ----------------------------------------------------------------------------------------------------------

def normalise(message: str) -> str:
	message = re.sub(r'0x[0-9a-fA-F]+', '0x#', message)
	message = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '<uuid>', message)
	return re.sub(r'\d+(\.\d+)?', '#', message).strip()[:200]


def scanLog(path: Path) -> dict:
	"""``{'errors': Counter, 'warnings': Counter, 'tracebacks': Counter, 'noise': int}`` for one log file."""
	result = {'errors': Counter(), 'warnings': Counter(), 'tracebacks': Counter(), 'noise': 0}
	if not path.exists():
		return result
	lines = [ANSI.sub('', line.rstrip()) for line in path.read_text(errors='replace').splitlines()]
	i = 0
	while i < len(lines):
		line = lines[i]
		if line.startswith('Traceback (most recent call last)'):
			j = i + 1
			while j < len(lines) and (lines[j].startswith(' ') or lines[j].startswith('\t') or not lines[j]):
				j += 1
			frames = [l.strip() for l in lines[i + 1:j] if l.strip().startswith('File ')]
			final = lines[j] if j < len(lines) else ''
			where = frames[-1] if frames else ''
			result['tracebacks'][f'{normalise(final)}  [{where.split(", in ")[0].replace(str(Path.home()), "~")}]'] += 1
			i = j
			continue
		if (m := LEVEL.match(line)):
			level, message = m.groups()
			key = normalise(message)
			if any(re.search(p, key) for p in KNOWN_NOISE):
				result['noise'] += 1
			elif level in ('ERROR', 'CRITICAL'):
				result['errors'][key] += 1
			elif level == 'WARNING':
				result['warnings'][key] += 1
		elif any(re.search(p, line) for p in KNOWN_NOISE):
			result['noise'] += 1
		i += 1
	return result


def checkLogs(logs: dict) -> list:
	checks = []
	for role, scan in logs.items():
		bad = {**scan['errors'], **scan['tracebacks']}
		total = sum(bad.values())
		checks.append((
			f'{role} log: no errors or tracebacks', FAIL if total else PASS,
			'none' if not total else f'{total} in {len(bad)} kinds: ' + '; '.join(f'{n}x {k}' for k, n in sorted(bad.items(), key=lambda kv: -kv[1])[:6]),
		))
		warnings = scan['warnings']
		checks.append((
			f'{role} log: no unexpected warnings', WARN if warnings else PASS,
			'none' if not warnings else f'{sum(warnings.values())} in {len(warnings)} kinds: ' + '; '.join(f'{n}x {k}' for k, n in warnings.most_common(6)),
		))
	return checks


# --- process health ------------------------------------------------------------------------------------------------

def checkProcesses(procs: list, died) -> list:
	checks = [('both processes stayed up', FAIL if died else PASS, f'{died[0]} exited with {died[1]}' if died else 'yes')]
	return checks


def checkFlat(rows: list, role: str, field: str, label: str, maxGrowth: float, maxSlope: float, floor: float = 0.0) -> tuple:
	"""FAIL when ``field`` grew by more than ``maxGrowth`` (a fraction, end window against start window) *and* trends
	up faster than ``maxSlope`` per virtual hour."""
	rows = warmup(rows)
	if len(rows) < 6:
		return f'{role} {label} flat', WARN, f'only {len(rows)} samples after warm-up'
	values = [r[field] for r in rows]
	start, end = edges(values)
	growth = (end - start) / start if start else 0.0
	slope = slopePerHour(rows, field)
	failing = growth > maxGrowth and slope > maxSlope and end - start > floor
	return f'{role} {label} flat', FAIL if failing else PASS, f'{start:.1f} -> {end:.1f} ({growth:+.1%}), {slope:+.2f}/h'


def checkResources(role: str, rows: list) -> list:
	if not rows:
		return [(f'{role} probe wrote samples', FAIL, 'none')]
	checks = [
		checkFlat(rows, role, 'rssMB', 'memory (MB)', 0.15, 0.5, floor=20),
		checkFlat(rows, role, 'gcObjects', 'Python objects', 0.10, 200, floor=20000),
	]
	body = warmup(rows)
	for field, label, limit in (('threads', 'threads', 4), ('fds', 'file descriptors', 10)):
		values = [r[field] for r in body]
		checks.append((f'{role} {label} flat', FAIL if max(values) - min(values) > limit else PASS, f'{min(values)}..{max(values)}'))
	return checks


def checkCpu(procs: list) -> list:
	checks = []
	for role in ('backend', 'frontend'):
		values = [p[role]['cpu'] for p in procs if isinstance(p.get(role), dict) and 'cpu' in p[role]]
		values = values[len(values) // 10:]
		if len(values) < 9:
			checks.append((f'{role} CPU flat', WARN, f'only {len(values)} samples'))
			continue
		start, end = edges(values, 0.33)
		checks.append((f'{role} CPU flat', FAIL if end > start * 1.3 + 3 else PASS, f'{start:.0f}% -> {end:.0f}% of a core (mean {statistics.fmean(values):.0f}%)'))
	return checks


# --- frontend ------------------------------------------------------------------------------------------------------

def frontendRows(rows: list) -> list:
	return [r for r in rows if r.get('frontend', {}).get('loaded')]


def checkConnection(rows: list) -> list:
	"""The socket stays connected; separately, heartbeats keep arriving (a long GUI stall flaps this one on a slow box)."""
	rows = frontendRows(warmup(rows))
	if not rows:
		return [('frontend stayed connected to the backend', FAIL, 'no loaded samples')]
	connected = sum(1 for r in rows if r['frontend']['connection']['state'] == 'connected')
	alive = sum(1 for r in rows if r['frontend']['connection']['alive'])
	return [
		('frontend stayed connected to the backend', PASS if connected / len(rows) >= 0.98 else FAIL, f'{connected}/{len(rows)} samples'),
		('backend heartbeats kept arriving', PASS if alive / len(rows) >= 0.98 else WARN, f'{alive}/{len(rows)} samples'),
	]


def checkGraphDrift(rows: list) -> tuple:
	"""Every graph with data sits where ``syncDisplay`` would put it now, to within two sync intervals and two minutes.

	Bug #249 was a graph whose redraw timer was restarted by every data push, so it never ran and the plot slid off
	the screen at one second per second.
	"""
	worst = {}
	late = Counter()
	for r in frontendRows(warmup(rows)):
		for g in r['frontend']['graphs']:
			if not isinstance(g, dict) or 'driftSeconds' not in g or g['driftSeconds'] is None:
				continue
			if not any(p.get('has') for p in g['plots']):
				continue
			tolerance = 2 * g['syncSeconds'] + 120
			drift = abs(g['driftSeconds'])
			key = f"{g['name']} {','.join(p['key'] for p in g['plots'][:1])}"
			if drift > tolerance:
				late[key] += 1
			if drift > worst.get(key, (0, 0))[0]:
				worst[key] = (drift, r['virtual'])
	bad = {k: n for k, n in late.items() if n >= 2}
	if bad:
		detail = '; '.join(f'{k}: {n} samples late, worst {worst[k][0]:.0f}s at {worst[k][1]}' for k, n in list(bad.items())[:6])
		return 'graphs track now', FAIL, detail
	top = max(worst.values(), default=(0, ''))
	return 'graphs track now', PASS, f'{len(worst)} graphs, worst drift {top[0]:.0f}s'


def checkGraphData(rows: list) -> tuple:
	"""Each plotted series still reaches at least two hours short of now (a forecast reaches days ahead)."""
	stale = {}
	for r in frontendRows(warmup(rows)):
		for g in r['frontend']['graphs']:
			if not isinstance(g, dict):
				continue
			for p in g.get('plots', []):
				series = p.get('series')
				if p.get('has') and series and series.get('n') and series['last'] < r['epoch'] - 7200:
					stale.setdefault(p['key'], (r['virtual'], (r['epoch'] - series['last']) / 3600))
	return 'plotted series reach now', FAIL if stale else PASS, '; '.join(f'{k} {v[1]:.1f}h behind at {v[0]}' for k, v in list(stale.items())[:6]) or 'all current'


def checkRemoteWindows(rows: list) -> list:
	"""RemoteContainer windows only grow (#250) and the fetched series keep their size."""
	checks = []
	periods, sizes, shrunk, windows = {}, {}, {}, {}
	for r in frontendRows(rows):
		for c in r['frontend']['remote']:
			ident = (c['key'], c['source'])
			low, high = c['period']
			if ident in periods and (low > periods[ident][0] + 1e-6 or high < periods[ident][1] - 1e-6):
				shrunk.setdefault(ident, f"{periods[ident]} -> {(low, high)} at {r['virtual']}")
			periods[ident] = (min(low, periods.get(ident, (low, high))[0]), max(high, periods.get(ident, (low, high))[1]))
			series = c.get('series')
			if series and series.get('n'):
				windows.setdefault(ident, []).append((r['elapsed'], series['n']))
	checks.append(('remote containers: fetch windows never shrink', FAIL if shrunk else PASS, '; '.join(f'{k}: {v}' for k, v in list(shrunk.items())[:5]) or f'{len(periods)} containers'))
	bad = []
	for ident, points in windows.items():
		seen = 0
		for _, n in points[len(points) // 5:]:
			if seen and n < seen * 0.9 and seen - n > 30:
				bad.append(f'{ident[1]}:{ident[0]} fell from {seen} to {n} points')
				break
			seen = max(seen, n)
	checks.append(('remote series keep their size', FAIL if bad else PASS, '; '.join(bad[:5]) or f'{len(windows)} series'))
	old = {}
	for r in frontendRows(warmup(rows)):
		for c in r['frontend']['remote']:
			if c['source'] in ('Astronomy', 'Host') or c['source'].startswith('Govee'):
				age = c.get('valueAge')
				if age is not None and age > 900:
					old.setdefault((c['source'], c['key']), (r['virtual'], age))
	checks.append(('realtime values keep arriving', FAIL if old else PASS, '; '.join(f'{k[0]}:{k[1]} {v[1]:.0f}s old at {v[0]}' for k, v in list(old.items())[:5]) or 'all fresh'))
	return checks


def checkScene(rows: list) -> tuple:
	rows = frontendRows(warmup(rows))
	if len(rows) < 6:
		return 'scene item count flat', WARN, 'too few samples'
	values = [r['frontend']['sceneItems'] for r in rows]
	start, end = edges(values)
	return 'scene item count flat', FAIL if end > start * 1.05 + 20 else PASS, f'{start:.0f} -> {end:.0f}'


# --- backend -------------------------------------------------------------------------------------------------------

#: Plugin group -> how far past now its last point must reach, in days.
HORIZON_DAYS = {('OpenMeteo', 'hourly'): 10, ('PirateWeather', 'hourly'): 5}


def checkBackendWindows(rows: list) -> list:
	checks = []
	horizon, sizes, down, duplicate = {}, {}, {}, {}
	for r in warmup(rows):
		plugins = r.get('backend', {}).get('plugins')
		if not isinstance(plugins, dict):
			continue
		for name, plugin in plugins.items():
			if name in ('OpenMeteo', 'PirateWeather', 'Astronomy', 'Host') or name.startswith('Govee'):
				if not plugin['running']:
					down.setdefault(name, r['virtual'])
			for group, span in plugin.get('groups', {}).items():
				if not span.get('n'):
					continue
				sizes.setdefault((name, group), []).append(span['n'])
				if not span.get('unique', True):
					duplicate.setdefault((name, group), r['virtual'])
				days = HORIZON_DAYS.get((name, group))
				if days and (span['last'] - r['epoch']) / 86400 < days:
					horizon.setdefault((name, group), (r['virtual'], (span['last'] - r['epoch']) / 86400))
	checks.append(('plugins stayed running', FAIL if down else PASS, '; '.join(f'{k} stopped by {v}' for k, v in down.items()) or 'yes'))
	checks.append(('forecast horizons keep advancing', FAIL if horizon else PASS, '; '.join(f'{k[0]} {k[1]} only {v[1]:.1f}d ahead at {v[0]}' for k, v in horizon.items()) or 'yes (new fetches land)'))
	bad = []
	longRun = bool(rows) and rows[-1]['elapsed'] > 12 * 3600
	for ident, counts in sizes.items():
		seen = counts[0]
		for n in counts:
			if n < seen * 0.9 and seen - n > 30:
				bad.append(f'{ident[0]} {ident[1]} fell from {seen} to {n}')
				break
			seen = max(seen, n)
		else:
			start, end = edges(counts, 0.25)
			if longRun and end > start * 1.25 + 30:
				bad.append(f'{ident[0]} {ident[1]} grew {start:.0f} -> {end:.0f}')
	checks.append(('plugin history windows hold steady', FAIL if bad else PASS, '; '.join(bad[:5]) or f'{len(sizes)} groups neither shrink nor grow'))
	checks.append(('no duplicate timestamps', FAIL if duplicate else PASS, '; '.join(f'{k[0]} {k[1]} at {v}' for k, v in duplicate.items()) or 'none'))
	stale = {}
	for r in warmup(rows):
		for name, plugin in (r.get('backend', {}).get('plugins') or {}).items():
			if name in ('Astronomy', 'Host') or name.startswith('Govee'):
				ages = list(plugin.get('realtimeAges', {}).values())
				if ages and max(ages) > 900:
					stale.setdefault(name, (r['virtual'], max(ages)))
	checks.append(('backend realtime values stay fresh', FAIL if stale else PASS, '; '.join(f'{k} {v[1]:.0f}s old at {v[0]}' for k, v in stale.items()) or 'yes'))
	return checks


# --- report --------------------------------------------------------------------------------------------------------

def run(out: Path, args=None, died=None) -> int:
	out = Path(out)
	backend, frontend, procs = load(out / 'backend-probe.jsonl'), load(out / 'frontend-probe.jsonl'), load(out / 'procs.jsonl')
	logs = {'backend': scanLog(out / 'backend.out'), 'frontend': scanLog(out / 'frontend.out')}

	checks = checkProcesses(procs, died)
	checks += checkLogs(logs)
	checks += checkResources('backend', backend) + checkResources('frontend', frontend)
	checks += checkCpu(procs)
	if frontend:
		checks += checkConnection(frontend)
		checks += [checkGraphDrift(frontend), checkGraphData(frontend), checkScene(frontend)]
		checks += checkRemoteWindows(frontend)
	checks += checkBackendWindows(backend)

	failed = [c for c in checks if c[1] == FAIL]
	span = ''
	if frontend:
		span = f"{frontend[0]['virtual']} to {frontend[-1]['virtual']} ({frontend[-1]['elapsed'] / 3600:.1f} virtual hours, {frontend[-1]['real'] / 60:.0f} real minutes)"
	lines = ['# Soak report', '', f'Run: {span or "no samples"}', f'Result: **{"FAIL" if failed else "PASS"}** ({len(failed)} failing, {sum(1 for c in checks if c[1] == WARN)} warnings)', '']
	lines += ['| check | result | detail |', '|---|---|---|']
	for name, status, detail in checks:
		lines.append(f'| {name} | {status} | {detail.replace("|", "/")} |')
	for role, scan in logs.items():
		lines += ['', f'## {role} log', f'Known noise lines: {scan["noise"]}']
		for title, counter in (('Errors', scan['errors']), ('Tracebacks', scan['tracebacks']), ('Warnings', scan['warnings'])):
			if counter:
				lines += ['', f'### {title}'] + [f'- {n}x `{k}`' for k, n in counter.most_common(15)]
	(out / 'report.md').write_text('\n'.join(lines) + '\n')
	print('\n'.join(lines[:3] + [''] + [f'{s:4} {n}: {d}' for n, s, d in checks]))
	return 1 if failed else 0


if __name__ == '__main__':
	raise SystemExit(run(Path(sys.argv[1])))
