"""Opt-in frame timing for the live display.

    LEVITY_FRAME_LOG=/tmp/frames.jsonl LevityDash        # or LevityDash-run

Writes one JSON line every `LEVITY_FRAME_LOG_EVERY` seconds (default 10) about the window's own
event loop, so a slow or juddery display can be measured without a profiler:

* ``paint_ms``: how long `QGraphicsView.paintEvent` took (the scene walk and the drawing into the
  viewport; with a ``QOpenGLWidget`` the GPU flush after it is not included), ``mean``/``p95``/``max``;
* ``painted_share``: the share of the viewport each paint covered (1.0 = the whole window: every
  update repainted everything, which is what a GL viewport may do);
* ``fps``: paints per second, and ``gap_ms`` the time between the starts of successive paints while
  the display was animating (a gap over 33 ms is a dropped frame at 30 fps);
* ``lag_ms``: how late an 8 ms timer fired, a direct reading of how long the GUI thread was busy
  with something else (a data update, a layout, Python work) when it should have been free.

Off unless the variable is set; costs two ``perf_counter`` calls per paint when on.
"""
import json
import os
import time
from collections import deque
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QTimer


def _summary(values) -> dict:
	if not values:
		return {'n': 0}
	v = sorted(values)
	return {
		'n': len(v), 'mean': round(sum(v) / len(v) * 1000, 2),
		'p95': round(v[max(int(len(v) * 0.95) - 1, 0)] * 1000, 2), 'max': round(v[-1] * 1000, 2),
	}


class FrameLog(QObject):
	"""Collects paint and loop-lag samples for a view and appends a summary line to a file."""

	def __init__(self, view, path: str, every: float = 10.0):
		super().__init__(view)
		self.view = view
		self.path = Path(path).expanduser()
		self.every = every
		self._paints: list = []
		self._share: list = []
		self._gaps: list = []
		self._lag: list = []
		self._lastStart: Optional[float] = None
		self._since = time.monotonic()
		self._tickAt = time.perf_counter()
		self._tick = QTimer(self, interval=8)
		self._tick.timeout.connect(self._onTick)
		self._tick.start()
		self._flush = QTimer(self, interval=int(every * 1000))
		self._flush.timeout.connect(self.write)
		self._flush.start()

	def _onTick(self):
		now = time.perf_counter()
		self._lag.append(max(now - self._tickAt - 0.008, 0.0))
		self._tickAt = now

	def paint(self, started: float, duration: float, share: float):
		if self._lastStart is not None and started - self._lastStart < 1.0:
			self._gaps.append(started - self._lastStart)
		self._lastStart = started
		self._paints.append(duration)
		self._share.append(share)

	def write(self):
		elapsed = max(time.monotonic() - self._since, 1e-6)
		share = round(sum(self._share) / len(self._share), 3) if self._share else 0
		line = {
			'time': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'seconds': round(elapsed, 1),
			'viewport': type(self.view.viewport()).__name__, 'fps': round(len(self._paints) / elapsed, 1),
			'paint_ms': _summary(self._paints), 'painted_share': share, 'gap_ms': _summary(self._gaps),
			'lag_ms': _summary(self._lag), 'lag_over_16ms': len([x for x in self._lag if x > 0.016]),
		}
		try:
			self.path.parent.mkdir(parents=True, exist_ok=True)
			with self.path.open('a') as f:
				f.write(json.dumps(line) + '\n')
		except OSError:
			pass
		self._paints, self._share, self._gaps, self._lag = [], [], [], []
		self._since = time.monotonic()


def install(view) -> Optional[FrameLog]:
	"""A `FrameLog` for `view` when `LEVITY_FRAME_LOG` names a file, else None."""
	path = os.environ.get('LEVITY_FRAME_LOG', '').strip()
	if not path:
		return None
	try:
		every = float(os.environ.get('LEVITY_FRAME_LOG_EVERY', '10'))
	except ValueError:
		every = 10.0
	return FrameLog(view, path, every)
