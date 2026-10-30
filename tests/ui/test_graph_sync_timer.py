"""The graph's redraw timer must survive a steady stream of data updates.

Every data update calls ``GraphPanel.onAxisChange`` -> ``updateSyncTimer``. That used to
``start()`` the timer each time, and ``QTimer.start`` on a running timer restarts its countdown.
A display fed a push every minute (mode=remote, any realtime key) therefore never reached the
end of a several-minute interval: ``refresh`` / ``syncDisplay`` never ran again, the proxy sat
where the first sync left it while the clock moved on, and the plot slid off the left edge
about a pixel per ``msPerPixel`` until the graph was gone (a couple of days on a 66 h window).
"""
import time

from PySide6.QtCore import QTimer

from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import GraphPanel


class _Panel:
	"""Just what ``updateSyncTimer`` reads: a timer and ``msPerPixel``."""
	msPerPixel = 1000

	def __init__(self, fired: list):
		self.syncTimer = QTimer(interval=2000)
		self.syncTimer.timeout.connect(lambda: fired.append(time.monotonic()))


def test_sync_timer_fires_while_updates_keep_arriving(dashboard):
	from PySide6.QtWidgets import QApplication
	qapp = QApplication.instance()
	fired = []
	panel = _Panel(fired)
	end = time.monotonic() + 2.6
	while time.monotonic() < end:
		GraphPanel.updateSyncTimer(panel)  # a data push, well inside the interval
		qapp.processEvents()
		time.sleep(0.05)
	panel.syncTimer.stop()
	assert len(fired) >= 2, 'the sync timer was restarted by every update and never fired'
