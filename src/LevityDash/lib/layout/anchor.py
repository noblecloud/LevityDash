"""Anchor positioning: place an item by a point on a sibling, not by the parent's box.

An item inside a `group` normally takes `geometry:` as shares of its parent. `align-to:` puts one point of the item on one
point of a named sibling instead, so "centre this label under that number" survives the number moving or resizing::

	- {name: temp, type: realtime.text, geometry: {x: 10%, y: 10%, width: 50%, height: 40%}}
	- type: text
	  text: Outside
	  geometry: {width: 50%, height: 10%}      # a size only; the position comes from the anchor
	  align-to: {to: temp, y: bottom, self-y: top, offset: {y: 1mm}}

`align-to:` is a sibling's name, or a mapping with `to` (the sibling's `name`), `x` (`left`, `center`, `right`; the point on the sibling, default `center`);
`y` (`top`, `center`, `bottom`; default `center`); `self-x`, `self-y` (the point on this item; they default to the same word
as `x` and `y`, which is "centre with centre", or "left edge with left edge"); `offset: {x, y}` (lengths, added after;
positive is right and down). Leaving both `x` and `y` out centres both. Leaving `x` out (with `y` given) leaves the item's own x alone, and the same for `y`: write
only the axis that should follow the sibling. This is `anchor()` of CSS Anchor Positioning, with `anchor-name` taken from `name`.
The key is not `anchor:` because a gauge already has one (the corner its dial is anchored in).

Pure Python and Qt-free: rects are plain `(x, y, width, height)` tuples in the parent's coordinates.
"""
from dataclasses import dataclass
from typing import Any, Optional

from .spec import implements

__all__ = ['Anchor', 'AnchorError', 'place', 'POINTS_X', 'POINTS_Y']

POINTS_X = ('left', 'center', 'right')
POINTS_Y = ('top', 'center', 'bottom')
_KEYS = {'to', 'x', 'y', 'self-x', 'self-y', 'offset'}
_FRACTION = {'left': 0.0, 'top': 0.0, 'center': 0.5, 'right': 1.0, 'bottom': 1.0}


class AnchorError(ValueError):
	"""An `anchor:` is wrong."""


@dataclass(frozen=True)
class Anchor:
	to: str
	x: Optional[str] = None
	y: Optional[str] = None
	self_x: Optional[str] = None
	self_y: Optional[str] = None
	offset_x: Any = 0
	offset_y: Any = 0

	@classmethod
	def decode(cls, spec: Any) -> 'Anchor':
		if isinstance(spec, Anchor):
			return spec
		if isinstance(spec, str):
			spec = {'to': spec}
		if not isinstance(spec, dict):
			raise AnchorError(f'align-to is a sibling name or a mapping, not {spec!r}')
		if unknown := set(spec) - _KEYS:
			raise AnchorError(f'align-to has no setting {", ".join(sorted(map(str, unknown)))}. It has: {", ".join(sorted(_KEYS))}')
		if not isinstance(spec.get('to'), str) or not spec['to']:
			raise AnchorError('align-to needs `to:`, the name of a sibling')
		x, y = spec.get('x'), spec.get('y')
		if x is None and y is None:
			x = y = 'center'  # centre on the sibling, both ways
		self_x, self_y = spec.get('self-x', x), spec.get('self-y', y)
		for name, value, allowed in (('x', x, POINTS_X), ('self-x', self_x, POINTS_X), ('y', y, POINTS_Y), ('self-y', self_y, POINTS_Y)):
			if value is not None and value not in allowed:
				raise AnchorError(f'align-to {name} is {value!r}; it is {", ".join(allowed)}')
		if (self_x is None) != (x is None) or (self_y is None) != (y is None):
			raise AnchorError('align-to self-x needs x, and self-y needs y')
		offset = spec.get('offset') or {}
		if not isinstance(offset, dict) or set(offset) - {'x', 'y'}:
			raise AnchorError(f'align-to offset is {{x, y}}, not {offset!r}')
		return cls(spec['to'], x, y, self_x, self_y, offset.get('x', 0), offset.get('y', 0))

	def encode(self) -> dict:
		out: dict = {'to': self.to}
		if self.x is not None:
			out['x'] = self.x
			if self.self_x != self.x:
				out['self-x'] = self.self_x
		if self.y is not None:
			out['y'] = self.y
			if self.self_y != self.y:
				out['self-y'] = self.self_y
		if self.offset_x not in (0, None, '0') or self.offset_y not in (0, None, '0'):
			out['offset'] = {k: v for k, v in (('x', self.offset_x), ('y', self.offset_y)) if v not in (0, None, '0')}
		return out


@implements('css-anchor-position-1', 'The anchor() function', None, status='done')
def place(anchor: Anchor, target: tuple, size: tuple, own: tuple, offset: tuple = (0.0, 0.0)) -> tuple:
	"""The (x, y) of an item of `size` (width, height) whose anchored point sits on `target` (x, y, width, height).

	`own` is the item's current (x, y); an axis the anchor does not name keeps it. `offset` is (dx, dy) in the same units.
	"""
	x, y = own
	if anchor.x is not None:
		x = target[0] + target[2] * _FRACTION[anchor.x] - size[0] * _FRACTION[anchor.self_x] + offset[0]
	if anchor.y is not None:
		y = target[1] + target[3] * _FRACTION[anchor.y] - size[1] * _FRACTION[anchor.self_y] + offset[1]
	return x, y
