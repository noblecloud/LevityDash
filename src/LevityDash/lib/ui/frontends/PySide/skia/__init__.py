"""Optional GPU render tier: Skia (`skia-python`, BSD) on OpenGL under a transparent `QGraphicsView`.

Selected with `[QtOptions] renderer = skia` (or `LEVITY_RENDERER=skia`; default `qpainter`). Imported
lazily so a machine without `skia-python`, or one that keeps QPainter, never loads it.
"""
from functools import cache

__all__ = ['available', 'wanted']


@cache
def available() -> bool:
	try:
		import skia  # noqa: F401
		from PySide6.QtOpenGLWidgets import QOpenGLWidget  # noqa: F401
	except ImportError:
		return False
	return True


def wanted(name: str) -> bool:
	"""True when the configured renderer is `skia` and it can be used; warns and says no otherwise."""
	if str(name).strip().lower() != 'skia':
		return False
	if not available():
		from LevityDash.lib.ui.frontends.PySide import qtLogger
		qtLogger.warning('renderer = skia needs the skia-python package (pip install skia-python); using QPainter')
		return False
	return True
