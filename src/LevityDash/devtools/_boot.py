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
import time
from pathlib import Path
from typing import Optional, Tuple

DEFAULT_SIZE = (1800, 1090)


def boot(
	seed: Optional[str] = None,
	levity: Optional[str] = None,
	size: Tuple[int, int] = DEFAULT_SIZE,
	settle: float = 6.0,
	plugins: bool = False,
):
	"""Bring up an offscreen dashboard and return ``(app, LevityDashboard)``.

	``seed`` renders against a *copy* of a config dir (safe anywhere, but values
	with no source in that copy show as placeholders). Omit it to render the
	real config, which means real data — and on macOS a Bluetooth-capable host
	if the Govee plugin is enabled (see CLAUDE.md's Bluetooth gotcha).
	"""
	os.environ['QT_QPA_PLATFORM'] = 'offscreen'
	if seed:
		seed_path = Path(seed)
		os.environ['LEVITYDASH_CONFIG_DEBUG'] = '1'
		os.environ['LEVITYDASH_CONFIG_SEED'] = str(seed_path)
		if levity:
			shutil.copy(levity, seed_path / 'saves' / 'dashboards' / 'default.levity')
	elif levity:
		raise ValueError('rendering a candidate .levity needs a seed; refusing to overwrite the real dashboard')

	from LevityDash import LevityDashboard

	LevityDashboard.init()
	LevityDashboard.plugins.load_all()
	app = LevityDashboard.app

	from PySide6.QtCore import QTimer

	app.init_app()
	QTimer.singleShot(10, LevityDashboard.load_dashboard)
	if plugins:
		QTimer.singleShot(50, LevityDashboard.plugins.start)

	# Resize AFTER the dashboard has loaded. load_dashboard restores a saved
	# window geometry, so an earlier resize gets clobbered and the render comes
	# out at whatever size the config happened to remember - which looks like a
	# renderer bug and isn't. Racing it by chance is how this first appeared to
	# work.
	pump(app, min(1.5, settle))
	app.main_window.resize(*size)
	pump(app, max(settle - 1.5, 1.5))
	return app, LevityDashboard


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
