"""Shared pytest fixtures for LevityDash.

Boots the real Qt application headlessly (offscreen platform, pristine
temporary config) and drives the event loop by hand so tests can inspect the
populated QGraphicsScene without ever entering the blocking ``exec_()`` loop.

This formalizes the throwaway harnesses used during the size-group debugging
(inspect_bad / inspect_rel / inspect_windowfit / inspect_unit).
"""
import os
import time
from pathlib import Path

# Must be set before any PySide6/Qt import happens anywhere in the import graph.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LEVITYDASH_CONFIG_DEBUG", "1")
# Seed the throwaway config dir with an *established* user config (onboarding
# answered, real dashboard) rather than a fresh-install one - see
# tests/resources/config-seed/. Unset LEVITYDASH_CONFIG_SEED for tests that
# specifically want the onboarding/fresh-install path.
os.environ.setdefault("LEVITYDASH_CONFIG_SEED", str(Path(__file__).parent / "resources" / "config-seed"))

import pytest


def pump(app, seconds: float) -> None:
	"""Process Qt events for ``seconds`` of wall time so timers can fire."""
	end = time.monotonic() + seconds
	while time.monotonic() < end:
		app.processEvents()
		time.sleep(0.005)


# A fixed, unremarkable instant used to make time-dependent widgets (clock,
# date) deterministic across runs. 2025-06-18 is a Wednesday at 14:30.
import datetime as _dt

FROZEN_TIME = _dt.datetime(2025, 6, 18, 14, 30, 0, tzinfo=_dt.timezone.utc).astimezone()


@pytest.fixture
def frozen_time(monkeypatch):
	"""Freeze the app clock at FROZEN_TIME for time-sensitive tests.

	Freezes every current-time source the visible widgets actually use:
	- ``shared.now`` / ``shared.Now.now`` (used by app logic),
	- the ``strftime`` the DateTime clock renders with (it reads the system
	  clock directly, not ``Now``),
	- ``datetime.now`` in the Moon module.
	Opt-in (not autouse): request it, then trigger a refresh to observe a
	stable clock/date/moon. Value injection (fixed measurements) is deferred
	to the TestData plugin - see plan Phase 1.5.
	"""
	from LevityDash.lib.utils import shared

	monkeypatch.setattr(shared, "now", lambda: FROZEN_TIME)
	monkeypatch.setattr(shared.Now, "now", classmethod(lambda cls, **kw: FROZEN_TIME))

	# DateTime renders via `strftime(fmt)` (system clock); freeze it.
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays import DateTime as _DateTime
	monkeypatch.setattr(_DateTime, "strftime", lambda fmt: FROZEN_TIME.strftime(fmt), raising=False)

	# Moon reads `datetime.now(tz)` directly; freeze via a stub datetime.
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays import Moon as _Moon

	class _FrozenDatetime(_dt.datetime):
		@classmethod
		def now(cls, tz=None):
			return FROZEN_TIME.astimezone(tz) if tz else FROZEN_TIME

	monkeypatch.setattr(_Moon, "datetime", _FrozenDatetime, raising=False)

	return FROZEN_TIME


@pytest.fixture(scope="session")
def dashboard():
	"""A booted, settled dashboard.

	Returns a small namespace with the app, view, scene and driver helpers.
	Plugins are loaded (so containers/labels exist) but never *started* - no
	network, no worker threads - which keeps the session deterministic and
	teardown clean.
	"""
	from LevityDash import LevityDashboard

	LevityDashboard.init()
	LevityDashboard.plugins.load_all()

	app = LevityDashboard.app
	# Replicate LevityDashApp.start() up to (but not including) exec_(), and
	# skip wiring plugin auto-start.
	from PySide6.QtCore import QTimer

	app.init_app()
	QTimer.singleShot(10, LevityDashboard.load_dashboard)
	app.main_window.show()

	# Dashboard loads at ~10ms; loadingFinished arms the first-fit which runs
	# after the 300ms resizeDone debounce. Pump well past that.
	pump(app, 3.0)

	view = LevityDashboard.view
	scene = LevityDashboard.scene

	class Driver:
		app = None
		view = None
		scene = None

		def texts(self):
			from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import Text
			return [i for i in self.scene.items() if isinstance(i, Text)]

		def visible_texts(self):
			return [t for t in self.texts() if t.isVisible() and (t.text or "").strip()]

		def settled_resize(self, dw: int, dh: int):
			win = self.view.window()
			sz = win.size()
			win.resize(max(200, sz.width() + dw), max(150, sz.height() + dh))
			pump(self.app, 1.2)  # past the 300ms resizeDone debounce

		def refresh_all(self):
			self.view.refresh()
			pump(self.app, 0.8)

	d = Driver()
	d.app, d.view, d.scene = app, view, scene

	yield d

	try:
		LevityDashboard.plugins.stop()
	except Exception:
		pass
	app.processEvents()
