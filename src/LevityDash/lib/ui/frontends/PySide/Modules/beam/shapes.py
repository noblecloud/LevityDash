"""Beam outlines: SVG path data and a few named shapes, fitted to a panel's rectangle.

A beam without a path follows the panel's rounded rectangle. With `path:` it follows the
outline instead. The path is scaled to fill the panel, so only its proportions matter.
"""
from __future__ import annotations

import math
import re
from typing import Optional

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath, QTransform

#: Named outlines, as path data in any units.
PRESETS = {
	'circle': 'M 50 0 A 50 50 0 1 1 49.99 0 Z',
	'diamond': 'M 50 0 L 100 50 L 50 100 L 0 50 Z',
	'triangle': 'M 50 0 L 100 100 L 0 100 Z',
	'arc': 'M 0 100 A 50 50 0 0 1 100 100',
	'wave': 'M 0 50 C 15 0 35 0 50 50 S 85 100 100 50',
	'heart': 'M 50 90 C 10 60 0 30 25 12 C 40 2 50 15 50 25 C 50 15 60 2 75 12 C 100 30 90 60 50 90 Z',
}

_TOKEN = re.compile(r'[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?')
_ARGS = {'M': 2, 'L': 2, 'H': 1, 'V': 1, 'C': 6, 'S': 4, 'Q': 4, 'T': 2, 'A': 7, 'Z': 0}


def _arc(path: QPainterPath, x0: float, y0: float, rx: float, ry: float, rot: float, large: bool, sweep: bool, x: float, y: float) -> None:
	"""SVG endpoint arc as Qt arcs (the W3C endpoint-to-centre conversion)."""
	if rx == 0 or ry == 0 or (x0 == x and y0 == y):
		path.lineTo(x, y)
		return
	rx, ry = abs(rx), abs(ry)
	phi = math.radians(rot)
	cp, sp = math.cos(phi), math.sin(phi)
	dx, dy = (x0 - x) / 2, (y0 - y) / 2
	x1, y1 = cp * dx + sp * dy, -sp * dx + cp * dy
	lam = x1 ** 2 / rx ** 2 + y1 ** 2 / ry ** 2
	if lam > 1:
		rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
	num = rx ** 2 * ry ** 2 - rx ** 2 * y1 ** 2 - ry ** 2 * x1 ** 2
	den = rx ** 2 * y1 ** 2 + ry ** 2 * x1 ** 2
	coef = math.sqrt(max(0.0, num / den)) * (-1 if large == sweep else 1)
	cx1, cy1 = coef * rx * y1 / ry, -coef * ry * x1 / rx
	cx, cy = cp * cx1 - sp * cy1 + (x0 + x) / 2, sp * cx1 + cp * cy1 + (y0 + y) / 2
	a1 = math.degrees(math.atan2((y1 - cy1) / ry, (x1 - cx1) / rx))
	a2 = math.degrees(math.atan2((-y1 - cy1) / ry, (-x1 - cx1) / rx))
	delta = a2 - a1
	if sweep and delta < 0:
		delta += 360
	elif not sweep and delta > 0:
		delta -= 360
	arc = QPainterPath()
	# Qt angles run counter-clockwise on a y-up grid, SVG's clockwise on y-down: negate.
	arc.arcMoveTo(QRectF(-rx, -ry, 2 * rx, 2 * ry), -a1)
	arc.arcTo(QRectF(-rx, -ry, 2 * rx, 2 * ry), -a1, -delta)
	transform = QTransform().translate(cx, cy).rotate(rot)
	arc = transform.map(arc)
	path.connectPath(arc) if path.elementCount() else path.addPath(arc)
	path.lineTo(x, y)


def parseSvgPath(data: str) -> QPainterPath:
	"""Path data (M L H V C S Q T A Z, absolute and relative) as a QPainterPath. Raises ValueError on bad data."""
	tokens = _TOKEN.findall(data or '')
	if not tokens or tokens[0] not in 'Mm':
		raise ValueError('path data must start with M')
	path = QPainterPath()
	cur = QPointF(0, 0)
	start = QPointF(0, 0)
	lastC: Optional[QPointF] = None
	lastQ: Optional[QPointF] = None
	i = 0
	cmd = ''
	while i < len(tokens):
		if tokens[i].isalpha():
			cmd = tokens[i]
			i += 1
			if cmd in 'Zz':
				path.closeSubpath()
				cur = QPointF(start)
				lastC = lastQ = None
				continue
		elif cmd == '':
			raise ValueError('path data must start with M')
		up = cmd.upper()
		n = _ARGS[up]
		args = [float(t) for t in tokens[i:i + n]]
		if len(args) < n or any(t.isalpha() for t in tokens[i:i + n]):
			raise ValueError(f'{cmd} needs {n} numbers')
		i += n
		rel = cmd.islower()
		ox, oy = (cur.x(), cur.y()) if rel else (0.0, 0.0)
		if up == 'M':
			cur = QPointF(args[0] + ox, args[1] + oy)
			start = QPointF(cur)
			path.moveTo(cur)
			cmd = 'l' if rel else 'L'  # extra pairs after M are lines
			lastC = lastQ = None
		elif up == 'L':
			cur = QPointF(args[0] + ox, args[1] + oy)
			path.lineTo(cur)
			lastC = lastQ = None
		elif up == 'H':
			cur = QPointF(args[0] + ox, cur.y())
			path.lineTo(cur)
			lastC = lastQ = None
		elif up == 'V':
			cur = QPointF(cur.x(), args[0] + oy)
			path.lineTo(cur)
			lastC = lastQ = None
		elif up == 'C':
			c1, c2, end = QPointF(args[0] + ox, args[1] + oy), QPointF(args[2] + ox, args[3] + oy), QPointF(args[4] + ox, args[5] + oy)
			path.cubicTo(c1, c2, end)
			cur, lastC, lastQ = end, c2, None
		elif up == 'S':
			c1 = QPointF(2 * cur.x() - lastC.x(), 2 * cur.y() - lastC.y()) if lastC is not None else QPointF(cur)
			c2, end = QPointF(args[0] + ox, args[1] + oy), QPointF(args[2] + ox, args[3] + oy)
			path.cubicTo(c1, c2, end)
			cur, lastC, lastQ = end, c2, None
		elif up == 'Q':
			c1, end = QPointF(args[0] + ox, args[1] + oy), QPointF(args[2] + ox, args[3] + oy)
			path.quadTo(c1, end)
			cur, lastQ, lastC = end, c1, None
		elif up == 'T':
			c1 = QPointF(2 * cur.x() - lastQ.x(), 2 * cur.y() - lastQ.y()) if lastQ is not None else QPointF(cur)
			end = QPointF(args[0] + ox, args[1] + oy)
			path.quadTo(c1, end)
			cur, lastQ, lastC = end, c1, None
		elif up == 'A':
			end = QPointF(args[5] + ox, args[6] + oy)
			_arc(path, cur.x(), cur.y(), args[0], args[1], args[2], bool(args[3]), bool(args[4]), end.x(), end.y())
			cur = end
			lastC = lastQ = None
	return path


def fitPath(path: QPainterPath, width: float, height: float, margin: float = 1.0) -> QPainterPath:
	"""`path` scaled to fill a width x height panel, `margin` px in from each edge."""
	box = path.boundingRect()
	if box.width() <= 0 and box.height() <= 0:
		return QPainterPath()
	sx = (width - 2 * margin) / box.width() if box.width() > 0 else 1.0
	sy = (height - 2 * margin) / box.height() if box.height() > 0 else 1.0
	transform = QTransform().translate(margin, margin).scale(sx, sy).translate(-box.left(), -box.top())
	return transform.map(path)


def resolve(spec: Optional[str]) -> Optional[QPainterPath]:
	"""A named shape or path data to a path in its own units; None for no spec. Raises ValueError on bad data."""
	if spec in (None, ''):
		return None
	spec = str(spec).strip()
	return parseSvgPath(PRESETS.get(spec.lower(), spec))
