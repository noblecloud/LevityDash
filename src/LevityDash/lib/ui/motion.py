"""How things settle after a value changes, read from the active theme's ``motion`` token.

``smooth`` is the original ease in and out. ``spring`` is the same cubic-bezier that Paddock's UI uses for state
changes, ``cubic-bezier(.34, 1.56, .64, 1)``: it leaves quickly, overshoots a little and settles on the value. A
hand that moves 100 degrees passes its mark by about 9. The animation still ends exactly on the target.
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF

__all__ = ('STYLES', 'curve', 'style')

STYLES = ('smooth', 'spring')

_SPRING = ((0.34, 1.56), (0.64, 1.0))


def style() -> str:
	"""The active theme's motion style, ``smooth`` when it names none or one this version does not know."""
	from LevityDash.lib.ui.colors import theme
	try:
		name = str(theme.active().size('motion')).strip().lower()
	except Exception:
		return 'smooth'
	return name if name in STYLES else 'smooth'


def curve(name: str | None = None) -> QEasingCurve:
	"""An easing curve for ``name`` (the active theme's style when ``None``)."""
	name = name or style()
	if name == 'spring':
		easing = QEasingCurve(QEasingCurve.Type.BezierSpline)
		easing.addCubicBezierSegment(QPointF(*_SPRING[0]), QPointF(*_SPRING[1]), QPointF(1.0, 1.0))
		return easing
	return QEasingCurve(QEasingCurve.Type.InOutCubic)
