"""SVG path data to `QPainterPath`.

Only what a glyph needs: the whole `d` grammar — `M L H V C S Q T A Z`, absolute
and relative, implicit repeats after a move — with no transforms and no styles.
An elliptical `A` is turned into cubic curves by the SVG spec's
endpoint-to-centre conversion, so nothing is approximated away.

Paths come back in the source's own coordinate space (the map's `viewBox`); the
caller scales them.
"""
import math
import re
from math import acos, cos, hypot, pi, radians, sin, sqrt
from typing import Iterable, List, Tuple

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath, QTransform

__all__ = ['parse', 'viewBox', 'path_data', 'parse_transform']

_TOKEN = re.compile(r'[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?')
_COMMANDS = set('MmLlHhVvCcSsQqTtAaZz')
_TRANSFORM = re.compile(r'(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)')


def parse_transform(value: str | None) -> QTransform:
	"""An SVG `transform` attribute as a `QTransform`.

	Handles what icon sets actually use — `translate`, `scale`, `rotate` (with and
	without a centre) and `matrix` — applied left to right, which is the order SVG
	specifies. `skewX`/`skewY` are applied as shears; anything unrecognised is
	ignored rather than guessed at.
	"""
	transform = QTransform()
	if not value:
		return transform
	for name, arguments in _TRANSFORM.findall(value):
		numbers = [float(x) for x in re.split(r'[\s,]+', arguments.strip()) if x]
		if name == 'matrix' and len(numbers) == 6:
			a, b, c, d, e, f = numbers
			step = QTransform(a, b, c, d, e, f)
		elif name == 'translate' and numbers:
			step = QTransform.fromTranslate(numbers[0], numbers[1] if len(numbers) > 1 else 0.0)
		elif name == 'scale' and numbers:
			step = QTransform.fromScale(numbers[0], numbers[1] if len(numbers) > 1 else numbers[0])
		elif name == 'rotate' and numbers:
			angle = numbers[0]
			# PySide6 exposes fromRotate on neither 6.6 nor 6.11, so rotate explicitly.
			cosine, sine = cos(radians(angle)), sin(radians(angle))
			rotation = QTransform(cosine, sine, -sine, cosine, 0.0, 0.0)
			if len(numbers) >= 3:
				cx, cy = numbers[1], numbers[2]
				step = QTransform.fromTranslate(-cx, -cy) * rotation * QTransform.fromTranslate(cx, cy)
			else:
				step = rotation
		elif name in ('skewX', 'skewY') and numbers:
			step = QTransform()
			if name == 'skewX':
				step.shear(math.tan(math.radians(numbers[0])), 0.0)
			else:
				step.shear(0.0, math.tan(math.radians(numbers[0])))
		else:
			continue
		transform = step * transform
	return transform



def path_data(markup: str) -> List[str]:
	"""Every `d` attribute in an SVG fragment, in document order."""
	if '<' in markup:
		return re.findall(r'\sd\s*=\s*"([^"]+)"', markup)
	return [markup]


def viewBox(value: str | Iterable[float] | None, default: Tuple[float, float] = (24.0, 24.0)) -> Tuple[float, float]:
	"""The `viewBox` size as `(width, height)`; `None` and junk answer `default`."""
	if value is None:
		return default
	if isinstance(value, str):
		parts = [x for x in re.split(r'[\s,]+', value.strip()) if x]
		if len(parts) != 4:
			return default
		try:
			_, _, width, height = (float(x) for x in parts)
		except ValueError:
			return default
	elif isinstance(value, (list, tuple)) and len(value) == 4:
		_, _, width, height = (float(x) for x in value)
	else:
		return default
	return (width if width > 0 else default[0], height if height > 0 else default[1])


def _tokens(d: str) -> List[str]:
	return _TOKEN.findall(d)


def parse(d: str) -> QPainterPath:
	"""`QPainterPath` for one `d` string. A malformed string yields what parsed before the fault."""
	path = QPainterPath()
	tokens = _tokens(d or '')
	if not tokens:
		return path

	position = QPointF(0.0, 0.0)
	start = QPointF(0.0, 0.0)
	last_control = None  # for S/T reflection
	last_command = ''
	i = 0

	def number() -> float:
		nonlocal i
		value = float(tokens[i])
		i += 1
		return value

	def point(relative: bool) -> QPointF:
		x, y = number(), number()
		return QPointF(position.x() + x, position.y() + y) if relative else QPointF(x, y)

	command = ''
	while i < len(tokens):
		token = tokens[i]
		if token in _COMMANDS:
			command = token
			i += 1
		elif not command:
			break
		# Implicit repeat: M continues as L, m as l; every other command repeats itself.

		relative = command.islower()
		kind = command.upper()

		if kind == 'Z':
			path.closeSubpath()
			position = QPointF(start)
			last_control = None
			last_command = command
			command = ''
			continue

		if kind == 'M':
			position = point(relative)
			start = QPointF(position)
			path.moveTo(position)
			last_control = None
			last_command = command
			# A second pair after a move is a line, and so on.
			command = 'l' if relative else 'L'
			continue

		if kind == 'L':
			position = point(relative)
			path.lineTo(position)
			last_control = None
		elif kind == 'H':
			x = number()
			position = QPointF(position.x() + x if relative else x, position.y())
			path.lineTo(position)
			last_control = None
		elif kind == 'V':
			y = number()
			position = QPointF(position.x(), position.y() + y if relative else y)
			path.lineTo(position)
			last_control = None
		elif kind in 'CS':
			if kind == 'C':
				c1 = point(relative)
			else:
				# Reflect the previous curve's second control point through the current point.
				c1 = _reflect(position, last_control if last_command.upper() in 'CS' else None)
			c2 = point(relative)
			end = point(relative)
			path.cubicTo(c1, c2, end)
			last_control = c2
			position = end
		elif kind in 'QT':
			if kind == 'Q':
				q = point(relative)
			else:
				q = _reflect(position, last_control if last_command.upper() in 'QT' else None)
			end = point(relative)
			# Qt has no quadratic segment: the exact conversion keeps the curve identical.
			c1 = QPointF(position.x() + 2.0 / 3.0 * (q.x() - position.x()), position.y() + 2.0 / 3.0 * (q.y() - position.y()))
			c2 = QPointF(end.x() + 2.0 / 3.0 * (q.x() - end.x()), end.y() + 2.0 / 3.0 * (q.y() - end.y()))
			path.cubicTo(c1, c2, end)
			last_control = q
			position = end
		elif kind == 'A':
			rx, ry, rotation, large, sweep = number(), number(), number(), number(), number()
			end = point(relative)
			_arc(path, position, end, rx, ry, rotation, bool(large), bool(sweep))
			position = end
			last_control = None
		else:
			break
		last_command = command
	return path


def _reflect(about: QPointF, control: QPointF | None) -> QPointF:
	if control is None:
		return QPointF(about)
	return QPointF(2 * about.x() - control.x(), 2 * about.y() - control.y())


def _arc(path: QPainterPath, start: QPointF, end: QPointF, rx: float, ry: float, rotation: float, large: bool, sweep: bool):
	"""Append an elliptical arc as cubic segments (SVG spec F.6.5 / F.6.6)."""
	rx, ry = abs(rx), abs(ry)
	if rx == 0 or ry == 0 or start == end:
		path.lineTo(end)
		return
	phi = radians(rotation % 360.0)
	cos_phi, sin_phi = cos(phi), sin(phi)
	dx2, dy2 = (start.x() - end.x()) / 2.0, (start.y() - end.y()) / 2.0
	x1 = cos_phi * dx2 + sin_phi * dy2
	y1 = -sin_phi * dx2 + cos_phi * dy2

	# Radii too small to reach: scale them up until the ellipse touches both points.
	scale = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
	if scale > 1.0:
		factor = sqrt(scale)
		rx, ry = rx * factor, ry * factor

	rx2, ry2 = rx * rx, ry * ry
	denominator = rx2 * y1 * y1 + ry2 * x1 * x1
	numerator = rx2 * ry2 - denominator
	coefficient = 0.0 if denominator == 0 else sqrt(max(0.0, numerator / denominator))
	if large == sweep:
		coefficient = -coefficient
	cx1 = coefficient * rx * y1 / ry
	cy1 = -coefficient * ry * x1 / rx
	cx = cos_phi * cx1 - sin_phi * cy1 + (start.x() + end.x()) / 2.0
	cy = sin_phi * cx1 + cos_phi * cy1 + (start.y() + end.y()) / 2.0

	def angle(ux: float, uy: float, vx: float, vy: float) -> float:
		dot = ux * vx + uy * vy
		length = hypot(ux, uy) * hypot(vx, vy)
		if length == 0:
			return 0.0
		value = max(-1.0, min(1.0, dot / length))
		return -acos(value) if (ux * vy - uy * vx) < 0 else acos(value)

	theta1 = angle(1.0, 0.0, (x1 - cx1) / rx, (y1 - cy1) / ry)
	delta = angle((x1 - cx1) / rx, (y1 - cy1) / ry, (-x1 - cx1) / rx, (-y1 - cy1) / ry)
	if not sweep and delta > 0:
		delta -= 2 * pi
	elif sweep and delta < 0:
		delta += 2 * pi

	# A quarter turn or less per cubic keeps the error invisible at glyph sizes.
	count = max(1, int(abs(delta) / (pi / 2) + 0.999))
	step = delta / count
	for n in range(count):
		a1 = theta1 + n * step
		a2 = a1 + step
		alpha = 4.0 / 3.0 * sin((a2 - a1) / 4.0) / cos((a2 - a1) / 4.0) if cos((a2 - a1) / 4.0) != 0 else 0.0
		p1 = _ellipse_point(cx, cy, rx, ry, cos_phi, sin_phi, a1)
		p2 = _ellipse_point(cx, cy, rx, ry, cos_phi, sin_phi, a2)
		d1 = _ellipse_tangent(rx, ry, cos_phi, sin_phi, a1)
		d2 = _ellipse_tangent(rx, ry, cos_phi, sin_phi, a2)
		c1 = QPointF(p1.x() + alpha * d1.x(), p1.y() + alpha * d1.y())
		c2 = QPointF(p2.x() - alpha * d2.x(), p2.y() - alpha * d2.y())
		path.cubicTo(c1, c2, p2)


def _ellipse_point(cx, cy, rx, ry, cos_phi, sin_phi, angle) -> QPointF:
	x, y = rx * cos(angle), ry * sin(angle)
	return QPointF(cx + cos_phi * x - sin_phi * y, cy + sin_phi * x + cos_phi * y)


def _ellipse_tangent(rx, ry, cos_phi, sin_phi, angle) -> QPointF:
	x, y = -rx * sin(angle), ry * cos(angle)
	return QPointF(cos_phi * x - sin_phi * y, sin_phi * x + cos_phi * y)
