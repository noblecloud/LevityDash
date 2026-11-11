"""Optional GPU render tier: Qt Canvas Painter under a transparent `QGraphicsView`.

Selected with `[QtOptions] renderer = canvas` (default `qpainter`). Everything here is imported
lazily so a machine without `PySide6.QtCanvasPainter` (Qt < 6.11), or one that keeps QPainter,
never loads it. Canvas Painter is GPLv3/commercial; keep it an optional import.
"""
from functools import cache

__all__ = ['available', 'wanted']


@cache
def available() -> bool:
	try:
		import PySide6.QtCanvasPainter  # noqa: F401
	except ImportError:
		return False
	return True


def wanted(name: str) -> bool:
	"""True when the configured renderer is `canvas` and it can be used; warns and says no otherwise."""
	if str(name).strip().lower() != 'canvas':
		return False
	if not available():
		from LevityDash.lib.ui.frontends.PySide import qtLogger
		qtLogger.warning('renderer = canvas needs PySide6 6.11+ (QtCanvasPainter); using QPainter')
		return False
	return True
