"""
Bend text outlines along a circular arc.

Everything here works in the label's *local* frame: origin at the label centre,
+x along the reading direction. The centre of the dial sits at ``(0, +R)`` when
the label is upright (``s = +1``, glyph tops point away from the dial centre) and
at ``(0, -R)`` when it is flipped (``s = -1``).
"""
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from math import cos, pi, radians, sin
from typing import Any, Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFontMetricsF, QPainterPath, QPolygonF, QTransform

__all__ = ['CurveMode', 'warp_point', 'bend_text', 'glyph_ring_text', 'warp_path', 'WarpSpec', 'WarpPlacement', 'CORNERS', 'normalizeCorner', 'arcFit']


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


def _outline_pieces(path: QPainterPath, scale: float):
	"""
	Split a path into subpaths of cubic pieces.

	Returns a list of (n, 4, 2) arrays, one per subpath. Every piece holds the
	four control points of a cubic. A line becomes a cubic with its control
	points a third of the way along. Coordinates are multiplied by `scale`.
	"""
	subpaths = []
	pieces = []
	current = None
	start = None
	count = path.elementCount()
	i = 0

	def close():
		if pieces:
			if (current[0] - start[0]) ** 2 + (current[1] - start[1]) ** 2 > 1e-12:
				pieces.append(_line_piece(current, start))
			subpaths.append(np.array(pieces) * scale)

	while i < count:
		element = path.elementAt(i)
		kind = element.type
		point = (element.x, element.y)
		if kind == QPainterPath.ElementType.MoveToElement:
			close()
			pieces = []
			start = current = point
			i += 1
		elif kind == QPainterPath.ElementType.LineToElement:
			pieces.append(_line_piece(current, point))
			current = point
			i += 1
		elif kind == QPainterPath.ElementType.CurveToElement:
			c2 = path.elementAt(i + 1)
			end = path.elementAt(i + 2)
			pieces.append((current, point, (c2.x, c2.y), (end.x, end.y)))
			current = (end.x, end.y)
			i += 3
		else:
			i += 1
	close()
	return subpaths


def _line_piece(a, b):
	return (a, (a[0] + (b[0] - a[0]) / 3, a[1] + (b[1] - a[1]) / 3), (a[0] + (b[0] - a[0]) * 2 / 3, a[1] + (b[1] - a[1]) * 2 / 3), b)


def _cubic_at(pieces: np.ndarray, t: np.ndarray) -> np.ndarray:
	"""Points of `pieces` (n, 4, 2) at parameters `t` (n,)."""
	u = 1 - t
	return (
		(u ** 3)[:, None] * pieces[:, 0] + (3 * u * u * t)[:, None] * pieces[:, 1]
		+ (3 * u * t * t)[:, None] * pieces[:, 2] + (t ** 3)[:, None] * pieces[:, 3]
	)


#: Widest arc, in radians, one cubic may cover after the warp.
_MAX_ARC = 0.5


def bend_text(text: str, font, scale: float, radius: float, side: int, epsilon: float, bend: Optional[float] = None) -> QPainterPath:
	"""
	Outline of `text` bent along a circle, in the label's local units.

	`scale` is the item's scale: the outline is warped at final size, then divided
	by it. `radius` is the label-centre radius in scene units. `epsilon` is the
	flatness tolerance in scene units.

	`bend` runs from 0 to 1. At 1 every point follows the warp, so the letters
	stretch. At 0 each letter keeps its shape and turns to the circle's tangent at
	its own centre. Between, every point sits that share of the way from its rigid
	place to its warped place.

	The glyph curves are never flattened. Each cubic is cut into pieces that span
	a small angle of the circle, and the result of every piece is fitted by one
	cubic through its end points and its two third points. The result is a curve
	path: smooth at any zoom.
	"""
	bend = min(1.0, max(0.0, bend))
	fm = QFontMetricsF(font)
	width = fm.horizontalAdvance(text)
	ascent, descent = fm.ascent(), fm.descent()
	scale = scale or 1.0
	y_mid = (descent - ascent) / 2 * scale
	# The fit error grows with the sixth power of the arc. Tighten the arc for a big radius or a small epsilon.
	arc = min(_MAX_ARC, max(0.05, (max(epsilon, 1e-6) / (0.02 * max(radius, 1e-3) + 1e-9)) ** (1 / 6)))
	step = abs(radius) * arc
	half = width * scale / 2
	result = QPainterPath()
	result.setFillRule(Qt.WindingFill)
	third = np.array([1 / 3, 2 / 3])
	for i, char in enumerate(text):
		if char.isspace():
			continue
		advance = fm.horizontalAdvance(text[:i])
		glyph = QPainterPath()
		glyph.addText(QPointF(advance, 0), font, char)
		# Frame of the glyph: its middle on the circle, turned to the tangent there.
		centre_x = (advance + fm.horizontalAdvance(char) / 2) * scale
		alpha = (centre_x - half) / radius
		cx, cy = warp_point(centre_x - half, y_mid, y_mid, radius, side)
		turn = side * alpha
		cos_t, sin_t = cos(turn), sin(turn)
		for pieces in _outline_pieces(glyph, scale):
			# Only the warped share bends, so a low bend needs fewer pieces.
			span = (pieces[:, :, 0].max(axis=1) - pieces[:, :, 0].min(axis=1)) * bend
			counts = np.maximum(1, np.ceil(span / step)).astype(int)
			index = np.repeat(np.arange(len(pieces)), counts)
			first = np.cumsum(counts) - counts
			k = np.arange(len(index)) - first[index]
			n = counts[index]
			whole = pieces[index]
			t0 = k / n
			dt = 1 / n
			samples = np.stack([
				_cubic_at(whole, t0),
				_cubic_at(whole, t0 + dt * third[0]),
				_cubic_at(whole, t0 + dt * third[1]),
				_cubic_at(whole, t0 + dt),
			], axis=1)
			dx = samples[:, :, 0] - centre_x
			dy = samples[:, :, 1] - y_mid
			rigid_x = cx + dx * cos_t - dy * sin_t
			rigid_y = cy + dx * sin_t + dy * cos_t
			if bend >= 1.0:
				x, y = warp_point(samples[:, :, 0] - half, samples[:, :, 1], y_mid, radius, side)
			elif bend <= 0.0:
				x, y = rigid_x, rigid_y
			else:
				wx, wy = warp_point(samples[:, :, 0] - half, samples[:, :, 1], y_mid, radius, side)
				x, y = rigid_x + (wx - rigid_x) * bend, rigid_y + (wy - rigid_y) * bend
			q = np.stack([x, y], axis=2) / scale
			p0, q1, q2, p3 = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
			c1 = (-5 * p0 + 18 * q1 - 9 * q2 + 2 * p3) / 6
			c2 = (2 * p0 - 9 * q1 + 18 * q2 - 5 * p3) / 6
			result.moveTo(float(p0[0, 0]), float(p0[0, 1]))
			for a, b, c in zip(c1.tolist(), c2.tolist(), p3.tolist()):
				result.cubicTo(a[0], a[1], b[0], b[1], c[0], c[1])
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


#: Corner and edge names, as the (x, y) share of a box. `Gauge.anchor` accepts the four corners.
CORNERS = {
	'top-left': (0, 0), 'top-right': (1, 0),
	'bottom-left': (0, 1), 'bottom-right': (1, 1),
	'top': (0.5, 0), 'bottom': (0.5, 1), 'left': (0, 0.5), 'right': (1, 0.5),
	'center': (0.5, 0.5),
}


def normalizeCorner(value) -> str:
	"""`bottom-left`, `bottom_left`, `Bottom Left` and `left-bottom` all give `bottom-left`."""
	name = str(value).strip().lower().replace('_', '-').replace(' ', '-')
	parts = name.split('-')
	if len(parts) == 2 and parts[0] in ('left', 'right') and parts[1] in ('top', 'bottom'):
		name = f'{parts[1]}-{parts[0]}'
	return name


# One warped outline costs a few milliseconds. Value labels ask for the same text
# every refresh, so keep recent results.
_cache: 'OrderedDict[tuple, QPainterPath]' = OrderedDict()
_CACHE_SIZE = 512


def warp_path(text: str, font, scale: float, radius: float, side: int, mode: CurveMode, epsilon: float, bend: Optional[float] = None) -> QPainterPath:
	"""
	The one place any text is bent onto a circle: tick labels, value and unit
	labels, captions, titles and dashboard text all come here.

	Cached per (text, font, scale, radius, side, bend). `bend` is 0 to 1; left out,
	it comes from `mode` (`glyphs` is 0, `warp` is 1). `epsilon` is the flatness
	tolerance in scene units; it only changes the result at the 0.05 level, so it
	is rounded in the key.
	"""
	if bend is None:
		bend = 0.0 if mode is CurveMode.glyphs else 1.0
	key = (text, font.key(), round(scale, 4), round(radius, 2), side, round(epsilon, 2), round(bend, 3))
	hit = _cache.get(key)
	if hit is not None:
		_cache.move_to_end(key)
		return hit
	path = bend_text(text, font, scale, radius, side, epsilon, bend)
	_cache[key] = path
	if len(_cache) > _CACHE_SIZE:
		_cache.popitem(last=False)
	return path


def arcFit(width: float, band: float, scale: float, radius: float) -> float:
	"""
	Factor (at most 1) that keeps warped text inside what its circle can hold: flat
	`width` (at `scale`) no longer than one turn, and glyph `band` height (ascent plus
	descent) no deeper than the circle's radius, so the inner edge never crosses the
	centre. Text that fits is untouched, so turning warp on never changes a size that
	already fit.
	"""
	arc, depth = width * scale, band * scale / 2
	factor = 1.0
	if arc > 0:
		factor = min(factor, 2 * pi * radius * 0.98 / arc)
	if depth > 0:
		factor = min(factor, 0.9 * radius / depth)
	return factor


@dataclass(frozen=True)
class WarpPlacement:
	"""Where one warp lands, in the frame the caller measured in."""
	point: QPointF  # where the middle of the text sits
	radius: float
	rotation: float  # degrees; the item rotation that puts glyph tops away from (or toward) the centre
	side: int  # +1 upright, -1 flipped half a turn


@dataclass(frozen=True)
class WarpSpec:
	"""
	``warp:`` on any text item. Pins the middle of the text to a point on a circle
	and bends the glyphs along it.

	``center``  where the circle is centred: ``dial`` (the gauge's pivot; a card when
	            the text is not in a gauge), ``card``, a corner or edge name
	            (``bottom-left``, ``top``, ``center``...), or ``{x: 50%, y: 100%}`` of the card.
	``radius``  distance from the centre to the middle of the text: ``%`` is a share of
	            the dial's diameter (``dial``) or the card's short side, or ``px``/``in``.
	``angle``   where on the circle the middle sits, degrees clockwise from the top.
	``mode``    ``warp`` bends the outlines; ``glyphs`` keeps each letter straight.
	``bend``    how far the letters bend, ``0%`` to ``100%`` (a bare number is a percent).
	            ``0%`` turns each rigid letter to the circle, ``100%`` is the full warp.
	            ``mode: glyphs`` is ``0%`` and ``mode: warp`` is ``100%``.
	``flip``    ``auto`` turns text in the lower half so it reads left to right;
	            ``true``/``false`` force it.

	``warp: true`` takes every default. Values stay as written (strings and numbers)
	so the spec round-trips to plain YAML.
	"""
	center: Any = 'dial'
	radius: Any = '40%'
	angle: float = 0.0
	mode: CurveMode = CurveMode.warp
	flip: Any = 'auto'
	bend: float = 1.0  # 0..1; the share of the warp each point takes

	@property
	def amount(self) -> float:
		"""The bend to draw with: `mode: glyphs` built in code, without a bend, is 0."""
		return 0.0 if self.mode is CurveMode.glyphs and self.bend == 1.0 else self.bend

	@classmethod
	def decode(cls, value) -> Optional['WarpSpec']:
		if value is None or value is False:
			return None
		if isinstance(value, cls):
			return value
		if value is True:
			return cls()
		if not isinstance(value, dict):
			raise ValueError(f'warp must be true, false or a mapping, got {value!r}')
		unknown = set(value) - {'center', 'radius', 'angle', 'mode', 'flip', 'bend'}
		if unknown:
			raise ValueError(f'warp has unknown keys {sorted(map(str, unknown))}')
		center = value.get('center', 'dial')
		if isinstance(center, dict):
			if set(center) - {'x', 'y'}:
				raise ValueError(f'warp center mapping takes x and y, got {sorted(map(str, center))}')
			center = {'x': center.get('x', '50%'), 'y': center.get('y', '50%')}
		else:
			center = normalizeCorner(center)
			if center not in CORNERS and center not in ('dial', 'card'):
				raise ValueError(f'warp center must be dial, card, one of {sorted(CORNERS)} or {{x, y}}, got {value["center"]!r}')
		mode = value.get('mode', 'warp')
		try:
			mode = mode if isinstance(mode, CurveMode) else CurveMode[str(mode).lower()]
		except KeyError:
			raise ValueError(f'warp mode must be warp or glyphs, got {mode!r}') from None
		if mode is CurveMode.none:
			raise ValueError('warp mode must be warp or glyphs; remove warp to turn it off')
		flip = value.get('flip', 'auto')
		if isinstance(flip, str) and flip.lower() != 'auto':
			flip = {'true': True, 'false': False}.get(flip.lower(), flip)
		if flip != 'auto' and not isinstance(flip, bool):
			raise ValueError(f'warp flip must be auto, true or false, got {flip!r}')
		if isinstance(flip, str):
			flip = 'auto'
		bend = 0.0 if mode is CurveMode.glyphs and 'bend' not in value else 1.0
		if 'bend' in value:
			raw = value['bend']
			try:
				bend = float(str(raw).strip().rstrip('%')) / 100
			except ValueError:
				raise ValueError(f'warp bend must be a percent from 0% to 100%, got {raw!r}') from None
			if not 0 <= bend <= 1:
				raise ValueError(f'warp bend must be between 0% and 100%, got {raw!r}')
		return cls(center, value.get('radius', '40%'), float(value.get('angle', 0)), mode, flip, bend)

	def encode(self):
		"""Plain types only: `true` when everything is default, else a mapping of what differs."""
		out = {}
		default = WarpSpec()
		if self.center != default.center:
			out['center'] = dict(self.center) if isinstance(self.center, dict) else self.center
		if self.radius != default.radius:
			out['radius'] = self.radius
		if self.angle != default.angle:
			out['angle'] = int(self.angle) if self.angle == int(self.angle) else self.angle
		if self.mode is not default.mode:
			out['mode'] = self.mode.value
		if self.flip != default.flip:
			out['flip'] = self.flip
		if self.mode is CurveMode.glyphs and self.bend == 0.0:
			pass  # mode: glyphs already says 0%
		elif self.bend != default.bend:
			out['bend'] = f'{round(self.bend * 100, 1):g}%'
		return out or True

	def resolve(self, card: QRectF, dial: Optional[tuple]) -> 'WarpPlacement':
		"""
		`card` is the card's box and `dial` is `(centre, radius)` when the text sits in
		a gauge, both in one frame; the placement comes back in that frame.
		"""
		from LevityDash.lib.ui.Geometry import parseHeight, parseSize, size_px, DimensionType
		center = self.center
		if center == 'dial' and dial is None:
			center = 'card'
		if center == 'dial':
			point, reference = dial[0], dial[1] * 2
		else:
			if isinstance(center, dict):
				x = size_px(parseSize(center['x'], None, dimension=DimensionType.width), card.width(), dimension=DimensionType.width)
				y = size_px(parseSize(center['y'], None, dimension=DimensionType.height), card.height())
				point = QPointF(card.left() + x, card.top() + y)
			else:
				fx, fy = (0.5, 0.5) if center == 'card' else CORNERS[center]
				point = QPointF(card.left() + fx * card.width(), card.top() + fy * card.height())
			reference = min(card.width(), card.height())
		radius = max(float(size_px(parseHeight(self.radius, None), reference)), 1e-3)
		angle = self.angle
		lower = cos(radians(angle)) < -1e-9
		flipped = lower if self.flip == 'auto' else bool(self.flip)
		# The text's middle sits `radius` from the centre, `angle` clockwise from the top.
		middle = QPointF(point.x() + radius * sin(radians(angle)), point.y() - radius * cos(radians(angle)))
		return WarpPlacement(middle, radius, angle + (180 if flipped else 0), -1 if flipped else 1)
