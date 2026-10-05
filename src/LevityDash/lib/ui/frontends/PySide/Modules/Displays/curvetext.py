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


def warp_path(text: str, font, scale: float, radius: float, side: int, mode: CurveMode, epsilon: float) -> QPainterPath:
	"""
	The one place any text is bent onto a circle: tick labels, value and unit
	labels, captions, titles and dashboard text all come here.

	Cached per (text, font, scale, radius, side, mode). `epsilon` is the flatness
	tolerance in scene units; it only changes the result at the 0.05 level, so it
	is rounded in the key.
	"""
	key = (mode, text, font.key(), round(scale, 4), round(radius, 2), side, round(epsilon, 2))
	hit = _cache.get(key)
	if hit is not None:
		_cache.move_to_end(key)
		return hit
	if mode is CurveMode.glyphs:
		path = glyph_ring_text(text, font, scale, radius, side)
	else:
		path = bend_text(text, font, scale, radius, side, epsilon)
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
		unknown = set(value) - {'center', 'radius', 'angle', 'mode', 'flip'}
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
		return cls(center, value.get('radius', '40%'), float(value.get('angle', 0)), mode, flip)

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
