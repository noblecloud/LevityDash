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


def wait_until(app, condition, timeout: float = 5.0, message: str = '') -> None:
	"""Pump Qt events until ``condition()`` is true, or fail after ``timeout`` seconds.

	Use this instead of one ``processEvents()`` or a fixed sleep when the
	thing under test arrives through a timer or a queued signal.
	"""
	end = time.monotonic() + timeout
	while True:
		app.processEvents()
		if condition():
			return
		if time.monotonic() >= end:
			raise AssertionError(message or f'timed out after {timeout}s waiting for {condition!r}')
		time.sleep(0.005)


@pytest.fixture(autouse=True)
def _restore_process_globals():
	"""Undo what a test leaves in process-wide state, whatever order the tests run in.

	- ``valuesource._standIn``: ``StudioGauge`` installs one that answers every key from made-up data. Left
	  installed, a later test's key becomes a ``Constant`` and never reaches the dispatcher.
	- ``polar.feed._standIn``: the polar Studio's equivalent.
	- Computed values nobody holds any more: the engine keeps the last value of a released expression, so the next
	  test using the same expression would start from the previous test's reading.
	"""
	import sys
	valuesource = sys.modules.get('LevityDash.lib.valuesource')
	feed = sys.modules.get('LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.feed')
	saved = valuesource._standIn if valuesource else None
	savedFeed = feed._standIn if feed else None
	leasesBefore = _computed_leases()
	yield
	valuesource = sys.modules.get('LevityDash.lib.valuesource')
	if valuesource is not None:
		valuesource.installStandIn(saved)
	feed = sys.modules.get('LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.feed')
	if feed is not None:
		feed.installStandIn(savedFeed)
	computed = sys.modules.get('LevityDash.lib.plugins.computed')
	if computed is not None and computed._engine is not None:
		_clear_unused_computed(computed, computed._engine)
	leaked = {key: n for key, n in _computed_leases().items() if n > leasesBefore.get(key, 0)}
	# A lease left behind keeps its value alive for every later test that reads the same expression. Panels give
	# theirs back in ``delete()``; taking one out of the scene does not.
	assert not leaked, f'this test left computed-value leases held: {leaked}; call .delete() on the panel'


def _computed_leases() -> dict:
	"""``{computed key: users}`` of the process's engine, empty when none was created."""
	import sys
	computed = sys.modules.get('LevityDash.lib.plugins.computed')
	engine = computed._engine if computed is not None else None
	return {str(key): entry.count for key, entry in engine._entries.items()} if engine is not None else {}


def _clear_unused_computed(computed, engine) -> None:
	"""Empty the value of every computed key no panel holds a lease on."""
	for key in list(engine.source.keys()):
		if key in engine:
			continue
		container = engine.source.getOrCreate(key)
		if container.value is None or container.value.rawValue is None:
			continue
		container._update(None, timestamp=container.value.timestamp, metadata=dict(computed._METADATA), flags=computed._FLAGS)
		engine.source.publisher.publish({key})


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

		def wait_until(self, condition, timeout: float = 5.0, message: str = ''):
			"""Pump Qt events until ``condition()`` holds; fail after ``timeout`` seconds."""
			return wait_until(self.app, condition, timeout, message)

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
