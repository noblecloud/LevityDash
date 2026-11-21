#!/usr/bin/env python
"""Dev-only: measure how smooth the GUI thread is, on a booted dashboard.

    python src/LevityDash/devtools/perf_probe.py --levity docs/tasks/lambda-cross-section.levity --scenario hot-clear-day
    python src/LevityDash/devtools/perf_probe.py ... --idle 20 --scroll 200 --profile 10 --json out.json

It boots the dashboard like `render_dashboard.py`, shows the window, and runs three
measurements, each reported as numbers a person can compare between two checkouts:

* ``idle``: how the main thread's time divides while nothing is touched. Every
  viewport paint is timed (count, mean, p95, max) and every event-loop turn that
  took over 8 ms is counted (a 60 Hz frame is 16.7 ms, so a turn over that is a
  dropped frame). Also the share of wall time the loop spent busy.
* ``scroll``: drags the first graph back and forth by wheel steps and by moving
  its proxy, forcing a repaint after each step, and reports the time per step.
* ``profile``: cProfile of the idle loop, top functions by own time, so the
  hotspot has a name.

Needs a display or ``QT_QPA_PLATFORM=offscreen`` (the default here). Nothing is
written to the real config: it seeds from ``devtools/design-seed``.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _seed import seedEnvironment

seedEnvironment()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from LevityDash.devtools._boot import boot, shutdown  # noqa: E402


def stats(values):
	if not values:
		return {'n': 0}
	v = sorted(values)
	return {
		'n': len(v), 'mean_ms': round(sum(v) / len(v) * 1000, 2),
		'p95_ms': round(v[int(len(v) * 0.95) - 1 if len(v) > 1 else 0] * 1000, 2), 'max_ms': round(v[-1] * 1000, 2),
	}


class PaintTimer:
	"""Event filter on the viewport that times every paint event."""

	def __init__(self, viewport):
		from PySide6.QtCore import QEvent, QObject
		self.durations = []
		self.rects = []
		outer = self

		class Filter(QObject):
			def eventFilter(self, obj, event):
				# A paint event is handled after the filter returns; timing the whole
				# turn is done by the loop below, so here only count and size them.
				if event.type() == QEvent.Type.Paint:
					r = event.region().boundingRect()
					outer.rects.append(r.width() * r.height())
				return False

		self.filter = Filter()
		viewport.installEventFilter(self.filter)


def runLoop(app, seconds, timer=None, profile=None):
	"""Pump events for `seconds`, returning per-turn durations and the busy share."""
	turns = []
	busy = 0.0
	end = time.monotonic() + seconds
	if profile is not None:
		profile.enable()
	while time.monotonic() < end:
		t0 = time.perf_counter()
		app.processEvents()
		dt = time.perf_counter() - t0
		turns.append(dt)
		busy += dt
		time.sleep(0.001)
	if profile is not None:
		profile.disable()
	return turns, busy / seconds


def census(dashboard, view):
	"""Item counts by class, and the time of one forced full frame."""
	from collections import Counter
	counts = Counter(type(i).__name__ for i in dashboard.scene.items())
	view.viewport().repaint()
	t0 = time.perf_counter()
	view.viewport().repaint()
	return {'frame_ms': round((time.perf_counter() - t0) * 1000, 1), 'items_by_class': dict(counts.most_common(30))}


def pointer(app, view, g, steps, profile, top, out):
	"""Hover across the graph, then press and drag it: the time of each mouse event including the
	repaint it causes, and a cProfile of the drag."""
	import cProfile, io, pstats
	from PySide6.QtCore import QPoint, Qt
	from PySide6.QtTest import QTest
	vp = view.viewport()
	rect = g.sceneBoundingRect()
	y = rect.center().y()
	x0 = rect.left() + rect.width() * 0.3

	def at(x):
		return view.mapFromScene(x, y)

	QTest.mouseMove(vp, at(x0))
	runLoop(app, 0.2)
	hover = []
	for i in range(steps):
		t0 = time.perf_counter()
		QTest.mouseMove(vp, at(x0 + i * 2))
		app.processEvents()
		time.sleep(0.004)
		app.processEvents()
		hover.append(time.perf_counter() - t0 - 0.004)
	drag = []
	g.proxy.contentsWidth = lambda: 100000.0
	QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(x0))
	app.processEvents()
	prof = cProfile.Profile() if profile else None
	if prof:
		prof.enable()
	for i in range(steps):
		t0 = time.perf_counter()
		QTest.mouseMove(vp, at(x0 - (i + 1) * 3))
		app.processEvents()
		time.sleep(0.004)
		app.processEvents()
		drag.append(time.perf_counter() - t0 - 0.004)
	if prof:
		prof.disable()
	QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(x0 - steps * 3))
	app.processEvents()
	if prof:
		s = io.StringIO()
		pstats.Stats(prof, stream=s).sort_stats('tottime').print_stats(top)
		pstats.Stats(prof, stream=s).sort_stats('cumulative').print_stats(top)
		out['drag_profile'] = s.getvalue()
	# wheel: a trackpad sends many small events, a mouse few big ones
	from PySide6.QtCore import QPointF
	from PySide6.QtGui import QWheelEvent
	from PySide6.QtWidgets import QApplication
	wheel = []
	wprof = cProfile.Profile() if profile else None
	center = QPointF(at(rect.center().x()))
	if wprof:
		wprof.enable()
	for i in range(steps):
		t0 = time.perf_counter()
		ev = QWheelEvent(center, vp.mapToGlobal(center), QPoint(0, 0), QPoint(0, -6), Qt.MouseButton.NoButton,
			Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.ScrollUpdate, False)
		QApplication.sendEvent(vp, ev)
		app.processEvents()
		time.sleep(0.004)
		app.processEvents()
		wheel.append(time.perf_counter() - t0 - 0.004)
	if wprof:
		wprof.disable()
		s = io.StringIO()
		pstats.Stats(wprof, stream=s).sort_stats('tottime').print_stats(top)
		out['wheel_profile'] = s.getvalue()
	return {'hover_step': stats(hover), 'drag_step': stats(drag), 'wheel_step': stats(wheel), 'wheel_moved_px': round(g.proxy.pos().x(), 1)}


def animate(app, dashboard, pt, seconds):
	"""Start every gauge's needle animation and report the loop's turns and the paints they caused."""
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.gauge import Gauge
	gauges = [i for i in dashboard.scene.items() if isinstance(i, Gauge)]
	for gauge in gauges:
		lo, hi = float(gauge._range.rounded_min), float(gauge._range.rounded_max)
		try:
			gauge.value = lo
			gauge.value = hi
		except Exception:  # a gauge with no value feed in this dashboard
			pass
	pt.rects.clear()
	paintTimes = []
	turns = []
	end = time.monotonic() + seconds
	last = time.perf_counter()
	gaps = []
	while time.monotonic() < end:
		t0 = time.perf_counter()
		app.processEvents()
		now = time.perf_counter()
		turns.append(now - t0)
		time.sleep(0.002)
	frames = len(pt.rects)
	return {
		'gauges': len(gauges), 'turns': stats(turns), 'paints': frames, 'fps': round(frames / seconds, 1),
		'turns_over_16ms': len([t for t in turns if t > 0.0167]),
	}


def graphs(dashboard):
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import GraphPanel
	return [i for i in dashboard.scene.items() if isinstance(i, GraphPanel)]


def main() -> int:
	p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	p.add_argument('--levity')
	p.add_argument('--scenario')
	p.add_argument('--seed')
	p.add_argument('--size', default='1680x1050')
	p.add_argument('--idle', type=float, default=15.0, help='seconds of idle measurement')
	p.add_argument('--scroll', type=int, default=120, help='scroll steps (0 to skip)')
	p.add_argument('--profile', type=float, default=10.0, help='seconds of cProfile (0 to skip)')
	p.add_argument('--top', type=int, default=25)
	p.add_argument('--cache', default='', help='experiment: comma list of class names to give DeviceCoordinateCache before measuring')
	p.add_argument('--census', action='store_true', help='print item counts by class and paint cost per class for one full frame')
	p.add_argument('--animate', type=float, default=0.0, help='seconds to sweep every gauge needle and report frame timing')
	p.add_argument('--json')
	args = p.parse_args()

	w, _, h = args.size.partition('x')
	app, dashboard = boot(seed=args.seed, levity=args.levity, size=(int(w), int(h)), settle=4.0)
	out = {'size': args.size, 'items': len(dashboard.scene.items())}
	try:
		window = app.main_window
		view = window.view
		window.show()
		runLoop(app, 2.0)
		pt = PaintTimer(view.viewport())
		if args.cache:
			from PySide6.QtWidgets import QGraphicsItem
			names = {n.strip() for n in args.cache.split(',')}
			n = 0
			for item in dashboard.scene.items():
				if type(item).__name__ in names or any(c.__name__ in names for c in type(item).__mro__):
					item.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
					n += 1
			out['cached_items'] = n
			runLoop(app, 0.5)
		if args.census:
			out['census'] = census(dashboard, view)

		# idle
		turns, busy = runLoop(app, args.idle)
		slow = [t for t in turns if t > 0.008]
		out['idle'] = {
			'busy_share': round(busy, 3), 'turns': stats(turns), 'turns_over_8ms': len(slow),
			'turns_over_16ms': len([t for t in turns if t > 0.0167]), 'paints': len(pt.rects),
			'paints_per_s': round(len(pt.rects) / args.idle, 1),
			'mean_paint_px': round(sum(pt.rects) / len(pt.rects)) if pt.rects else 0,
		}

		# animation: sweep every needle at once and see how the event loop copes
		if args.animate:
			out['animate'] = animate(app, dashboard, pt, args.animate)

		# scroll
		gs = graphs(dashboard)
		out['graphs'] = len(gs)
		if gs and args.scroll:
			from PySide6.QtCore import QPointF
			g = gs[0]
			g.setSelected(False)
			# The fixture's history is shorter than the graph, so the proxy's own clamp leaves no room
			# to scroll; lift it (the cost of a repaint does not depend on how far the data goes).
			g.proxy.contentsWidth = lambda: 100000.0
			view.viewport().update()
			runLoop(app, 0.3)
			step = max(1.0, g.pixelsPerMinute * 15)
			times = []
			paint_times = []
			pos0 = g.proxy.pos().x()
			direction = 1
			last_x = None
			# What a real scroll costs: the item moves and the view repaints what Qt marks dirty
			# (the whole viewport under a QOpenGLWidget, the changed regions otherwise).
			pt.rects.clear()
			real = []
			# Walk away from whichever end the graph starts at; bounce when a move changes nothing.
			for i in range(args.scroll):
				before = g.proxy.pos().x()
				if i == 0 or (i > 1 and last_x == before):
					direction = -direction
				last_x = before
				t0 = time.perf_counter()
				g.proxy.moveBy(direction * step, 0)
				app.processEvents()
				time.sleep(0.004)
				app.processEvents()
				real.append(time.perf_counter() - t0 - 0.004)
			vp = view.viewport()
			out['scroll_real'] = {
				'per_step': stats(real), 'paints': len(pt.rects),
				'mean_painted_share': round(sum(pt.rects) / max(1, len(pt.rects)) / (vp.width() * vp.height()), 3),
				'opengl': type(vp).__name__,
			}
			for i in range(args.scroll):
				if i % 40 == 0:
					direction = -direction
				t0 = time.perf_counter()
				g.proxy.moveBy(direction * step, 0)
				t1 = time.perf_counter()
				view.viewport().repaint()
				t2 = time.perf_counter()
				app.processEvents()
				t3 = time.perf_counter()
				times.append(t3 - t0)
				paint_times.append(t2 - t1)
			out['scroll'] = {
				'step_px': round(step, 1), 'moved_px': round(g.proxy.pos().x() - pos0, 1),
				'per_step': stats(times), 'repaint': stats(paint_times),
			}
			if args.profile:
				import cProfile, io, pstats
				prof = cProfile.Profile()
				prof.enable()
				for i in range(args.scroll):
					if i % 40 == 0:
						direction = -direction
					g.proxy.moveBy(direction * step, 0)
					view.viewport().repaint()
					app.processEvents()
				prof.disable()
				s = io.StringIO()
				pstats.Stats(prof, stream=s).sort_stats('tottime').print_stats(args.top)
				pstats.Stats(prof, stream=s).sort_stats('cumulative').print_stats(args.top + 20)
				out['scroll_profile'] = s.getvalue()

		# pointer: hover and drag over the first graph, through real mouse events
		if gs and args.scroll:
			out['pointer'] = pointer(app, view, gs[0], args.scroll, args.profile, args.top, out)

		# idle profile
		if args.profile:
			import cProfile, io, pstats
			prof = cProfile.Profile()
			runLoop(app, args.profile, profile=prof)
			s = io.StringIO()
			pstats.Stats(prof, stream=s).sort_stats('tottime').print_stats(args.top)
			out['idle_profile'] = s.getvalue()
	finally:
		shutdown(dashboard)

	text = {k: v for k, v in out.items() if not k.endswith('_profile')}
	print(json.dumps(text, indent=1))
	for k in ('idle_profile', 'scroll_profile', 'drag_profile', 'wheel_profile'):
		if k in out:
			print(f'\n== {k} ==\n{out[k]}')
	if args.json:
		Path(args.json).write_text(json.dumps(out, indent=1))
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
