"""Dev-only: boot a headless dashboard and render parts of it to images.

Shared by `render_dashboard.py` and `render_widget.py`. Not imported by the
shipped app.

The ordering here is fiddly and easy to get wrong, which is why it lives in one
place:

- `QT_QPA_PLATFORM=offscreen` must be set *before* LevityDash is imported — the
  QApplication is constructed during the import chain and the platform can't
  change afterwards.
- `load_dashboard` has to be scheduled on the event loop, not called directly;
  skipping it yields a perfectly working app with an empty scene, which renders
  as a black rectangle and looks like a broken renderer.
- The window is resized but never shown. Sizing is what drives layout; showing
  is only needed for `view.grab()`, which we deliberately avoid.
- The resize has to happen *after* `load_dashboard`, which restores a saved
  geometry and will otherwise silently override it.
"""
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

DEFAULT_SIZE = (1800, 1090)

#: The instant `freeze_time()` pins the app clock to when given no argument: the
#: same local instant as the test suite's `FROZEN_TIME` fixture (tests/conftest.py),
#: so a design render and a test agree about "now".
FROZEN_TIME = datetime(2025, 6, 18, 14, 30, 0, tzinfo=timezone.utc).astimezone()


def freeze_time(when: Optional[datetime] = None) -> dict:
	"""Pin the clock so a one-shot render is repeatable. Returns what was pinned.

	Ports `tests/conftest.py`'s `frozen_time` fixture to the renderers, plus the
	readers a test never starts: the Fixture and Mock plugins (both stamp a
	`time` key from `datetime.now()`), and the Graph display's own `_time`
	partial. `now` on the `shared` module is the app-wide clock the widgets use.

	Call *after* the LevityDash import and *before* `boot()` builds any widget.

	⚠ Deliberately does NOT replace `sys.modules['datetime']`. A function-local
	`from datetime import datetime` (Gauge.py's `GaugeMarker._tickClock`) can
	therefore not be pinned - and replacing the module globally would make every
	`isinstance(x, datetime)` in the app answer False for real datetimes. A
	clock marker with no `at:` is the one construct that still moves with the
	wall clock; `render_diff.py` refuses to baseline such a file (see
	`unpinned_clock_markers`).
	"""
	import datetime as _dt
	from importlib import import_module

	when = when or FROZEN_TIME
	if when.tzinfo is None:
		when = when.astimezone()

	class _FrozenDatetime(_dt.datetime):
		@classmethod
		def now(cls, tz=None):
			return when.astimezone(tz) if tz else when

		@classmethod
		def today(cls):
			return when

	pinned = {}

	def pin(module_name: str, attr: str, value) -> None:
		try:
			module = import_module(module_name)
		except ImportError:  # a module this checkout lacks is not a failure
			return
		if not hasattr(module, attr):
			return
		setattr(module, attr, value)
		pinned[f'{module_name.split(".")[-1]}.{attr}'] = True

	# The app-wide clock.
	shared = import_module('LevityDash.lib.utils.shared')
	original_now = shared.now
	pin('LevityDash.lib.utils.shared', 'now', lambda: when)

	# `from ...shared import now` COPIES the function into a module's namespace at
	# import time, so patching `shared.now` alone leaves every one of those
	# reading the real clock. Derive the list by identity rather than naming
	# modules: whatever holds the original function gets the frozen one.
	for name, module in list(sys.modules.items()):
		if name.startswith('LevityDash') and getattr(module, 'now', None) is original_now:
			module.now = lambda: when
			pinned[f'{name.split(".")[-1]}.now'] = True

	try:
		shared.Now.now = classmethod(lambda cls, **kw: when)
		pinned['Now.now'] = True
	except Exception:  # noqa: BLE001
		pass

	# Modules that bound `datetime` (or a `strftime`) at import time, before this ran.
	for module_name in (
		'LevityDash.lib.ui.frontends.PySide.Modules.Displays.DateTime',
		'LevityDash.lib.ui.frontends.PySide.Modules.Displays.Moon',
		'LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph',
		'LevityDash.lib.plugins.builtin.Fixture',
		'LevityDash.lib.plugins.builtin.Mock',
	):
		pin(module_name, 'datetime', _FrozenDatetime)

	# DateTime renders via a module-level `strftime(fmt)` that reads the system clock.
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays import DateTime as _DateTime

	if hasattr(_DateTime, 'strftime'):
		_DateTime.strftime = lambda fmt: when.strftime(fmt)
		pinned['DateTime.strftime'] = True

	# Graph binds `partial(datetime.now, tz=LOCAL_TIMEZONE)` on the class that
	# draws the current-time line; it is a plain class attribute (a staticmethod
	# since 3.14), so replacing it is the same shape.
	_Graph = import_module('LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph')
	indicator = getattr(_Graph, 'CurrentTimeIndicator', None)
	if indicator is not None and hasattr(indicator, '_time'):
		indicator._time = staticmethod(lambda: when)
		pinned['CurrentTimeIndicator._time'] = True

	pinned['when'] = when.isoformat()
	return pinned


def boot(
	seed: Optional[str] = None,
	levity: Optional[str] = None,
	size: Tuple[int, int] = DEFAULT_SIZE,
	settle: float = 6.0,
	plugins: bool = False,
	windowed: bool = False,
	freeze: Optional[datetime] = None,
):
	"""Bring up a dashboard and return ``(app, LevityDashboard)``.

	``seed`` renders against a *copy* of a config dir (safe anywhere, but values
	with no source in that copy show as placeholders). Omit it to render the
	real config, which means real data — and on macOS a Bluetooth-capable host
	if the Govee plugin is enabled (see CLAUDE.md's Bluetooth gotcha).

	With ``LEVITYDASH_FIXTURE`` set (the devtools' ``--scenario``, see
	``_seed.py``), the Fixture plugin supplies every value. It is the only
	plugin started, with or without ``plugins=True``: a design render must not
	reach the network or Bluetooth. The seed is whatever ``_seed`` staged.

	``windowed=True`` shows a real window instead of forcing
	``QT_QPA_PLATFORM=offscreen`` — for `design_mode.py`, which needs an actual
	interactive Qt event loop (`app.exec()`) rather than a scene to hand to
	`render_image`. Every other caller renders offscreen and never shows a
	window, so this defaults to ``False`` and changes nothing for them.

	``freeze`` (a datetime, or ``FROZEN_TIME``) pins the app clock before the
	dashboard is built, so two renders of the same file agree; see
	`freeze_time`. Left ``None`` the clock is live, which is what an
	interactive design session wants.
	"""
	if not windowed:
		os.environ['QT_QPA_PLATFORM'] = 'offscreen'
	fixture = bool(os.environ.get('LEVITYDASH_FIXTURE', '').strip())
	if fixture and not seed:
		# `_seed.seedEnvironment` already pointed the environment at a seed and a
		# disposable config; take its word rather than demanding `--seed` twice.
		seed = os.environ.get('LEVITYDASH_CONFIG_SEED')
	if seed:
		os.environ['LEVITYDASH_CONFIG_DEBUG'] = '1'
		os.environ['LEVITYDASH_CONFIG_SEED'] = str(Path(seed))
	elif levity:
		raise ValueError('rendering a candidate .levity needs a seed; refusing to overwrite the real dashboard')

	from LevityDash import LevityDashboard

	# NOT before init(): `LevityDashboard.init()` is what imports
	# `LevityDash.lib`, whose own `__init__` sets `config` on the singleton. Any
	# earlier `LevityDash.lib.*` import runs that module against an already
	# immutable dashboard and dies with "LevityDashboard is immutable".
	LevityDashboard.init()

	if freeze is not None:
		pinned = freeze_time(freeze)
		print(f"frozen clock at {pinned['when']} ({len(pinned) - 1} sources)")

	if levity:
		# NOT `seed_path / 'saves' / 'dashboards' / 'default.levity'` - that
		# copies into `seed` itself, which is exactly the directory `seed` is
		# supposed to be read from, never written to. Whatever LevityDashboard
		# just resolved config to (a disposable temp dir, populated a moment
		# ago by copying FROM seed) is the only destination that is ever safe.
		# Writing into `seed` directly overwrote a real dashboard the one time
		# `seed` pointed at a real, live config directory rather than a
		# scratch copy - `seed` being a live directory is an explicitly
		# supported, documented use (CLAUDE.md, the design skill), not an edge
		# case, so this cannot be "usually fine."
		from LevityDash.lib.config import userConfig

		base = getattr(userConfig.userPath, 'path', userConfig.userPath)
		dashboards = Path(base) / 'saves' / 'dashboards'
		dashboards.mkdir(parents=True, exist_ok=True)
		shutil.copy(levity, dashboards / 'default.levity')

	LevityDashboard.plugins.load_all()
	app = LevityDashboard.app

	from PySide6.QtCore import QTimer

	app.init_app()
	QTimer.singleShot(10, LevityDashboard.load_dashboard)
	if fixture:
		# When the scenario's values arrive. Displays format a value once, on
		# arrival, and never re-format it - so a value that lands before a display
		# has resolved its configured unit (or its unit metadata) keeps whatever
		# it printed first. Deterministic renders therefore want the values to
		# arrive *last*: `LEVITYDASH_FIXTURE_DELAY_MS=end` injects them after the
		# dashboard has settled, which is what render_diff.py uses. A number is
		# milliseconds from here, and is what an interactive look wants.
		setting = (os.environ.get('LEVITYDASH_FIXTURE_DELAY_MS') or '50').strip().lower()
		if setting == 'end':
			fixture_pending = True
		else:
			fixture_pending = False
			QTimer.singleShot(int(setting or 50), lambda: startFixture(LevityDashboard))
	elif plugins:
		fixture_pending = False
		QTimer.singleShot(50, LevityDashboard.plugins.start)
	else:
		fixture_pending = False

	# Resize AFTER the dashboard has loaded. load_dashboard restores a saved
	# window geometry, so an earlier resize gets clobbered and the render comes
	# out at whatever size the config happened to remember - which looks like a
	# renderer bug and isn't. Racing it by chance is how this first appeared to
	# work.
	pump(app, min(1.5, settle))
	app.main_window.resize(*size)
	if windowed:
		app.main_window.show()
	pump(app, max(settle - 1.5, 1.5))
	if fixture_pending:
		# Every display now exists and has been laid out; publishing here means
		# no display can format a value before it knows its own units. The second
		# publish is what a display sees in the wild - the same value arriving
		# again - and gives any consumer that formatted the first callback a
		# settled second one.
		startFixture(LevityDashboard)
		pump(app, 1.0)
		plugin = LevityDashboard.plugins.get('Fixture', None)
		if plugin is not None:
			plugin.publish()
			pump(app, 0.5)
	return app, LevityDashboard


def startFixture(dashboard) -> None:
	"""Start the Fixture plugin alone. Raises if it did not load."""
	plugin = dashboard.plugins.get('Fixture', None)
	if plugin is None:
		raise RuntimeError('LEVITYDASH_FIXTURE is set but the Fixture plugin did not load; see LevityDash.log')
	plugin.thread.start()
	# The Mock plugin (made-up non-weather values) runs beside the scenario when
	# its config turns it on; the design seed does. It never touches the network.
	mock = dashboard.plugins.get('Mock', None)
	if mock is not None and mock.enabled:
		mock.thread.start()


def pump(app, seconds: float) -> None:
	"""Run the event loop for a while without blocking on exec()."""
	end = time.monotonic() + seconds
	while time.monotonic() < end:
		app.processEvents()
		time.sleep(0.005)


def render_image(scene, source_rect, scale: float = 1.0):
	"""Render a region of the scene and return the `QImage`.

	Uses `QGraphicsScene.render()` rather than `view.grab()`: it paints the
	items directly, so there is no viewport and no GL context to go wrong.
	`grab()` captures the viewport, needs the window shown, and under offscreen
	returns blank white unless `[QtOptions] openGL` is forced off first.

	⚠️ `QGraphicsEffect`s do not composite identically this way (the moon's glow
	renders flat). Layout, type, spacing and colour are faithful; effects are
	approximate.

	Must run on the Qt thread - it reads the scene graph.
	"""
	from PySide6.QtCore import QRectF, Qt
	from PySide6.QtGui import QImage, QPainter

	size = (source_rect.size() * scale).toSize()
	image = QImage(size, QImage.Format.Format_ARGB32)
	image.fill(Qt.black)  # the dashboard assumes a dark ground
	painter = QPainter(image)
	painter.setRenderHint(QPainter.Antialiasing)
	scene.render(painter, QRectF(image.rect()), source_rect)
	painter.end()
	return image


def render_png_bytes(scene, source_rect, scale: float = 1.0) -> bytes:
	"""`render_image`, encoded as PNG in memory - for serving over HTTP."""
	from PySide6.QtCore import QBuffer, QByteArray

	image = render_image(scene, source_rect, scale=scale)
	data = QByteArray()
	buffer = QBuffer(data)
	buffer.open(QBuffer.OpenModeFlag.WriteOnly)
	image.save(buffer, 'PNG')
	buffer.close()
	return bytes(data)


def render_rect(scene, source_rect, out: str, scale: float = 1.0) -> bool:
	"""Render a region of the scene to a PNG file."""
	return render_image(scene, source_rect, scale=scale).save(out)


def named_items(scene):
	"""Every scene item carrying a `name:` from the .levity, as {name: item}.

	Later items win on a name collision — the dashboard doesn't enforce
	uniqueness, so `--list` is the way to find out what you actually have.
	"""
	found = {}
	for item in scene.items():
		name = getattr(item, 'stateName', None)
		if isinstance(name, str) and name:
			found[name] = item
	return found
