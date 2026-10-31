"""In-process sampling for the soak children. Each sample is one JSON line in ``<out>/<role>-probe.jsonl``.

The backend samples from a plain thread (no Qt needed, and it starts before ``LevityDash`` is imported); the
frontend from a ``QTimer`` on the GUI thread, because the scene may only be read there. Both sample every
``LEVITYDASH_SOAK_PROBE_EVERY`` *virtual* seconds (default 300).

``<out>/eval-<role>.py``, when present, is executed in that probe on its next tick and its ``result`` goes to ``eval-<role>.json``:
a debugging door for looking at live objects without restarting a multi-hour run.
"""
import gc
from collections import Counter
from weakref import ReferenceType
import json
import os
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

import psutil
import timewarp

_PROBE_EVERY = float(os.environ.get('LEVITYDASH_SOAK_PROBE_EVERY', '300'))
_SHOT_EVERY = float(os.environ.get('LEVITYDASH_SOAK_SHOT_EVERY', '21600'))
_WINDOW = tuple(int(n) for n in os.environ.get('LEVITYDASH_SOAK_WINDOW', '1680x1050').split('x'))
_process = psutil.Process()
_lock = threading.Lock()
_handles = {}


def processStats() -> dict:
	cpu = _process.cpu_times()
	objects = gc.get_objects()
	census = Counter(type(o).__name__ for o in objects)
	weak = Counter(type(o()).__name__ for o in objects if type(o) is ReferenceType)
	del objects
	with _process.oneshot():
		return {
			'rssMB': round(_process.memory_info().rss / 2 ** 20, 2), 'threads': _process.num_threads(),
			'fds': _process.num_fds(), 'cpuUser': round(cpu.user, 2), 'cpuSystem': round(cpu.system, 2),
			'gcObjects': sum(census.values()), 'gcCounts': list(gc.get_count()),
			'gcTop': census.most_common(12), 'weakTop': weak.most_common(8),
		}


def base(role: str) -> dict:
	return {
		'role': role, 'virtual': datetime.now().astimezone().isoformat(timespec='seconds'), 'epoch': round(time.time(), 1),
		'elapsed': round(timewarp.elapsed(), 1), 'real': round(timewarp.realElapsed(), 1),
		**processStats(),
	}


def write(out: Path, role: str, row: dict) -> None:
	with _lock:
		with open(out / f'{role}-probe.jsonl', 'a') as f:
			f.write(json.dumps(row, default=str) + '\n')


def debugEval(out: Path, role: str, namespace: dict) -> None:
	path = out / f'eval-{role}.py'
	if not path.exists():
		return
	try:
		scope = dict(namespace)
		exec(compile(path.read_text(), str(path), 'exec'), scope)
		(out / f'eval-{role}.json').write_text(json.dumps(scope.get('result'), default=str, indent=1))
	except BaseException:
		(out / f'eval-{role}.json').write_text(json.dumps({'error': traceback.format_exc()}))
	path.rename(out / f'eval-{role}.done.py')


def _safe(fn, *args):
	try:
		return fn(*args)
	except Exception:
		return {'error': traceback.format_exc(limit=3)}


def startBackendProbe(out: Path) -> None:
	def run():
		while True:
			time.sleep(_PROBE_EVERY)
			row = base('backend')
			if 'LevityDash.lib.plugins.dispatcher' in sys.modules:
				row['backend'] = _safe(backendSample)
			write(out, 'backend', row)
			debugEval(out, 'backend', {'sys': sys, 'out': out})

	threading.Thread(target=run, name='soak-probe', daemon=True).start()


def _epoch(value, depth: int = 0):
	"""Epoch seconds of a datetime, or of whatever wraps one in ``.value`` or ``.timestamp`` (an ObservationTimestamp, a
	timeseries item); None if there is none."""
	if isinstance(value, datetime):
		return round(value.timestamp(), 1)
	if value is None or depth > 2:
		return None
	for name in ('timestamp', 'value'):
		inner = getattr(value, name, None)
		if inner is not None and inner is not value:
			found = _epoch(inner() if callable(inner) and not isinstance(inner, type) else inner, depth + 1)
			if found is not None:
				return found
	return None


def _span(timestamps) -> dict:
	"""``{n, first, last, sorted}`` of an iterable of timestamps, copying it first (a plugin thread may be writing)."""
	for _ in range(5):
		try:
			items = [_epoch(t) for t in list(timestamps)]
			break
		except RuntimeError:  # changed size during iteration; try again
			time.sleep(0.01)
	else:
		return {'n': None}
	items = [t for t in items if t is not None]
	if not items:
		return {'n': 0}
	return {'n': len(items), 'first': min(items), 'last': max(items), 'unique': len(set(items)) == len(items)}


def backendSample() -> dict:
	"""Per plugin: whether it runs, the span of each observation group, and how old its realtime values are."""
	from LevityDash import LevityDashboard
	now_ = time.time()
	plugins = {}
	for plugin in list(LevityDashboard.plugins):
		row = {'running': bool(plugin.running), 'groups': {}}
		for group in ('hourly', 'daily', 'minutely'):
			observation = getattr(plugin, group, None)
			if observation is not None:
				row['groups'][group] = _safe(_span, list(observation.keys()))
		realtime = getattr(plugin, 'realtime', None)
		if realtime is not None:
			ages = {}
			for key, value in list(realtime.items()):
				stamp = _epoch(value)
				if stamp is not None:
					ages[str(key)] = round(now_ - stamp, 1)
			row['realtimeAges'] = ages
		plugins[plugin.name] = row
	return {'plugins': plugins}


def startFrontendProbe(out: Path) -> None:
	from PySide6.QtCore import QTimer
	from LevityDash import LevityDashboard
	timer = QTimer(LevityDashboard.app)

	shots = out / 'shots'
	shots.mkdir(exist_ok=True)
	state = {'sized': False, 'shot': -1}

	def tick():
		if not state['sized'] and LevityDashboard.scene is not None:
			LevityDashboard.app.main_window.resize(*_WINDOW)
			state['sized'] = True
		row = base('frontend')
		row['frontend'] = _safe(frontendSample)
		write(out, 'frontend', row)
		hour = int(timewarp.elapsed() // _SHOT_EVERY)
		if state['sized'] and hour != state['shot']:
			state['shot'] = hour
			_safe(lambda: LevityDashboard.view.grab().save(str(shots / f'v{int(timewarp.elapsed() / 3600):04d}h.png')))
		debugEval(out, 'frontend', {'sys': sys, 'out': out, 'LevityDashboard': LevityDashboard})

	timer.timeout.connect(tick)
	timer.start(int(_PROBE_EVERY * 1000))
	_handles['timer'] = timer


def frontendSample() -> dict:
	"""The window, the connection, every graph's position against where it should be, and the remote containers."""
	from LevityDash import LevityDashboard
	from LevityDash.lib.plugins.dispatcher import MultiSourceContainer
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import GraphPanel
	from LevityDash.lib.wire.containers import RemoteContainer

	scene = LevityDashboard.scene
	if scene is None:
		return {'loaded': False}
	connection = LevityDashboard.dispatcher.remote
	window = LevityDashboard.app.main_window
	items = scene.items()
	sample = {
		'loaded': True, 'window': [window.width(), window.height()], 'sceneItems': len(items),
		'connection': {'state': connection.state, 'alive': connection.backendAlive, 'sinceBeat': connection.secondsSinceHeartbeat},
	}

	graphs = []
	for graph in (i for i in items if isinstance(i, GraphPanel)):
		graphs.append(_safe(graphSample, graph))
	sample['graphs'] = graphs

	remote = []
	for key, container in list(LevityDashboard.dispatcher.items()):
		if not isinstance(container, MultiSourceContainer):
			continue
		for source, inner in list(container.items()):
			if not isinstance(inner, RemoteContainer):
				continue
			series = inner.timeseries
			row = {'key': str(key), 'source': getattr(source, 'name', str(source)), 'period': [round(p.total_seconds() / 3600, 2) for p in inner._tsPeriod]}
			stamp = _epoch(inner.value)
			row['valueAge'] = None if stamp is None else round(time.time() - stamp, 1)
			if series is not None:
				row['series'] = _span([i.timestamp for i in series.list])
			remote.append(row)
	sample['remote'] = remote
	return sample


def graphSample(graph) -> dict:
	"""Where the graph's proxy sits against where ``syncDisplay`` would put it at this very moment."""
	timeframe = graph.timeframe
	pps = graph.pixelsPerSecond
	anchor = min(
		timeframe.displayPosition,
		min((figure.figureMinStart for figure in graph.figures), default=timeframe.displayPosition),
	)
	expected = (timeframe.start - anchor).total_seconds() * pps
	maxX = -timeframe.lookback.total_seconds() * pps
	minX = -graph.proxy.contentsWidth() + graph.rect().right() + maxX
	proxyX = graph.proxy.pos().x()
	clamped = sorted((expected, minX, maxX))[1]
	row = {
		'name': graph.name, 'type': type(graph).__name__, 'pps': pps, 'proxyX': round(proxyX, 3), 'expectedX': round(expected, 3), 'minX': round(minX, 3), 'maxX': round(maxX, 3),
		'clampedX': round(clamped, 3), 'driftSeconds': round((proxyX - clamped) / pps, 1) if pps else None,
		'syncActive': graph.syncTimer.isActive(), 'syncSeconds': round(graph.syncTimer.interval() / 1000, 2),
		'range': timeframe.range.total_seconds(), 'visible': graph.isVisible(), 'plots': [],
	}
	for figure in graph.figures:
		for plot in figure.plotData:
			series = plot.timeseries
			entry = {'key': str(plot.key), 'has': bool(plot.hasData)}
			if series is not None:
				entry['series'] = _span([i.timestamp for i in series.list]) if hasattr(series, 'list') else {'n': len(series)}
			row['plots'].append(entry)
	return row


def finish() -> None:
	pass
