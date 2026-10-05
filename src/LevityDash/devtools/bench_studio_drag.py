#!/usr/bin/env python
"""Dev-only: drag a Gauge Studio slider offscreen and count what the studio does.

    QT_QPA_PLATFORM=offscreen PYTHONPATH=src python src/LevityDash/devtools/bench_studio_drag.py [--cell N] [--pause-ms 700]

Presses the mouse on a control slider, moves it in small steps with a pause in the
middle, releases, and reports how often the gauge was rebuilt and when. The rebuild
(`Studio.settle`) must not run while the button is down, even through a long pause,
and must run once after the release.
"""
import argparse
import copy
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _studio_env

_studio_env.prepare()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from LevityDash.devtools import gauge_studio as gs


def main() -> int:
	p = argparse.ArgumentParser()
	p.add_argument('--cell', type=int, default=0)
	p.add_argument('--pause-ms', type=int, default=700)
	a = p.parse_args()
	app = QApplication.instance() or QApplication(sys.argv)
	cells = gs.showcaseCells()
	studio = gs.Studio()
	studio.show()
	label, entry = cells[a.cell]
	studio.loadDisplay(copy.deepcopy(entry.get('display') or {}), entry.get('key'), label)
	QTest.qWait(50)

	events = []
	t0 = time.monotonic()
	original = studio.settle

	def timed():
		started = time.monotonic()
		original()
		events.append(('settle', round((started - t0) * 1000), round((time.monotonic() - started) * 1000)))

	studio.settleTimer.timeout.disconnect()
	studio.settleTimer.timeout.connect(timed)

	flushed = studio._flush

	def timedFlush():
		started = time.monotonic()
		flushed()
		events.append(('flush', round((started - t0) * 1000), round((time.monotonic() - started) * 1000)))

	studio.flushTimer.timeout.disconnect()
	studio.flushTimer.timeout.connect(timedFlush)

	row = studio.rows[('arc', 'weight')]
	slider = row.slider
	slider.setFocus()
	QTest.qWait(20)
	span = slider.width() - 20
	y = slider.height() // 2
	QTest.mousePress(slider, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(10, y))
	steps = 40
	for i in range(steps):
		QTest.mouseMove(slider, QPoint(10 + span * i // steps, y))
		QTest.qWait(25)
		if i == steps // 2:
			events.append(('pause', round((time.monotonic() - t0) * 1000), a.pause_ms))
			QTest.qWait(a.pause_ms)
	released = round((time.monotonic() - t0) * 1000)
	QTest.mouseRelease(slider, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(10 + span, y))
	QTest.qWait(gs.SETTLE_MS + 400)
	settles = [e for e in events if e[0] == 'settle']
	flushes = [e for e in events if e[0] == 'flush']
	during = [e for e in settles if e[1] < released]
	after = [e for e in settles if e[1] >= released]
	print(f'cell {a.cell}: {label}')
	print(f'flushes (in-place edits): {len(flushes)}, median {sorted(f[2] for f in flushes)[len(flushes) // 2] if flushes else 0} ms, max {max((f[2] for f in flushes), default=0)} ms')
	print(f'settles before release: {len(during)} {during}')
	print(f'settles after release: {len(after)} {after}')
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
