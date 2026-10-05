"""
Bend text outlines along a circular arc.

Everything here works in the label's *local* frame: origin at the label centre,
+x along the reading direction. The centre of the dial sits at ``(0, +R)`` when
the label is upright (``s = +1``, glyph tops point away from the dial centre) and
at ``(0, -R)`` when it is flipped (``s = -1``).
"""
from enum import Enum

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QFontMetricsF, QPainterPath, QPolygonF, QTransform

__all__ = ['CurveMode', 'warp_point', 'bend_text', 'glyph_ring_text']


class CurveMode(Enum):
	none = 'none'
	warp = 'warp'
	glyphs = 'glyphs'


def warp_point(x, y, y_mid, radius, side):
	"""
	Map a point of flat text onto the arc.

	`x` is measured from the label centre along the text, `y` from the baseline
	(y down), `y_mid` is the y of the middle of the ascent/descent band. `radius`
	is the distance from the dial centre to the label centre, `side` is +1 for
	upright labels and -1 for flipped ones. Works on numbers and numpy arrays.
	"""
	alpha = x / radius
	r = radius - side * (y - y_mid)
	return r * np.sin(alpha), side * (radius - r * np.cos(alpha))


def _subdivide(points: np.ndarray, max_len: float) -> np.ndarray:
	"""Split every edge of a polyline so that no edge is longer than `max_len`."""
	if len(points) < 2:
		return points
	start = points[:-1]
	delta = points[1:] - start
	counts = np.maximum(1, np.ceil(np.hypot(delta[:, 0], delta[:, 1]) / max_len)).astype(int)
	index = np.repeat(np.arange(len(delta)), counts)
	first = np.cumsum(counts) - counts
	frac = (np.arange(len(index)) - first[index]) / counts[index]
	out = start[index] + delta[index] * frac[:, None]
	return np.vstack([out, points[-1:]])


def bend_text(text: str, font, scale: float, radius: float, side: int, epsilon: float) -> QPainterPath:
	"""
	Outline of `text` bent along a circle, in the label's local units.

	`scale` is the item's scale: the outline is warped at final size, then divided
	by it. `radius` is the label-centre radius in scene units. `epsilon` is the
	flatness tolerance in scene units.
	"""
	fm = QFontMetricsF(font)
	width = fm.horizontalAdvance(text)
	ascent, descent = fm.ascent(), fm.descent()
	flat = QPainterPath()
	flat.addText(QPointF(0, 0), font, text)
	scale = scale or 1.0
	y_mid = (descent - ascent) / 2 * scale
	# Smallest radius the text spans, floored so the chord length stays positive.
	inner = max(radius - (ascent + descent) * scale, radius * 0.1, 1e-3)
	max_len = max((8 * inner * epsilon) ** 0.5, 1e-3)
	result = QPainterPath()
	result.setFillRule(Qt.WindingFill)
	for polygon in flat.toSubpathPolygons(QTransform().scale(scale, scale)):
		points = np.array([(p.x(), p.y()) for p in polygon])
		if len(points) < 2:
			continue
		points = _subdivide(points, max_len)
		x, y = warp_point(points[:, 0] - width * scale / 2, points[:, 1], y_mid, radius, side)
		result.addPolygon(QPolygonF([QPointF(a / scale, b / scale) for a, b in zip(x, y)]))
		result.closeSubpath()
	return result


def glyph_ring_text(text: str, font, scale: float, radius: float, side: int) -> QPainterPath:
	"""Each character stays straight, rotated and placed on the circle."""
	fm = QFontMetricsF(font)
	width = fm.horizontalAdvance(text)
	ascent, descent = fm.ascent(), fm.descent()
	scale = scale or 1.0
	y_mid = (descent - ascent) / 2
	radius = radius / scale
	result = QPainterPath()
	result.setFillRule(Qt.WindingFill)
	for i, char in enumerate(text):
		if char.isspace():
			continue
		advance = fm.horizontalAdvance(text[:i])
		glyph_width = fm.horizontalAdvance(char)
		alpha = (advance + glyph_width / 2 - width / 2) / radius
		glyph = QPainterPath()
		glyph.addText(QPointF(-glyph_width / 2, -y_mid), font, char)
		placement = QTransform()
		placement.translate(float(radius * np.sin(alpha)), float(side * radius * (1 - np.cos(alpha))))
		placement.rotate(float(side * np.degrees(alpha)))
		result.addPath(placement.map(glyph))
	return result
