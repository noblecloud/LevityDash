"""The dashboard's ground: a flat colour, or a gradient across the whole board.

A dashboard writes it as a root key, ``background:``, beside ``theme:``::

	theme: dusk
	background: $sky                      # a scale of the theme
	background: $background               # a colour token, same as the default
	background: '#101820'                 # a raw colour
	background: {0: '#0b1020', 1: '#2a1f3d'}     # a gradient written in place
	background: {gradient: $sky, angle: 160}     # with a direction

Without the key the board takes the theme's ``backdrop`` scale if it has one, and its ``background`` colour if
not. A gradient runs top to bottom unless ``angle`` says otherwise. The angle is in CSS degrees: 0 is towards
the top, 90 towards the right, 180 (the default) towards the bottom. Stops sit at their own values, stretched
over the board, so ``{0: a, 1: b}`` and ``{0: a, 100: b}`` are the same ground.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QLinearGradient

from LevityDash.lib.ui.colors import theme as _theme
from LevityDash.lib.ui.colors.color import Color
from LevityDash.lib.ui.colors.gradient import Gradient, setStops

#: The scale a theme may define to give every board that does not choose its own a gradient ground.
BACKDROP_SCALE = 'backdrop'
DEFAULT_ANGLE = 180.0


class Backdrop:
	"""A resolved ground: ``color`` for a flat one, or ``stops`` (position 0-1, ``QColor``) with an ``angle``."""

	__slots__ = ('color', 'stops', 'angle', 'space')

	def __init__(self, color: Optional[QColor] = None, stops: tuple = (), angle: float = DEFAULT_ANGLE, space: str = 'srgb'):
		self.color = color
		self.stops = stops
		self.angle = angle
		self.space = space

	@property
	def flat(self) -> bool:
		return not self.stops

	def __eq__(self, other):
		return isinstance(other, Backdrop) and (self.color, self.stops, self.angle, self.space) == (other.color, other.stops, other.angle, other.space)

	def __hash__(self):
		return hash((self.color.rgba() if self.color else None, tuple((p, c.rgba()) for p, c in self.stops), self.angle, self.space))

	def __repr__(self):
		if self.flat:
			return f'Backdrop({self.color.name()})'
		return f'Backdrop({len(self.stops)} stops, {self.angle:g}deg)'

	def brush(self, rect: QRectF) -> QBrush:
		"""A brush that paints the ground over ``rect`` (scene coordinates)."""
		if self.flat:
			return QBrush(self.color)
		return QBrush(linearGradient(rect, self.angle, self.stops, self.space))


def linearGradient(rect: QRectF, angle: float, stops, space: str = 'srgb') -> QLinearGradient:
	"""A gradient across ``rect`` in the CSS direction ``angle``, long enough that the corners reach the end stops."""
	radians = math.radians(angle)
	dx, dy = math.sin(radians), -math.cos(radians)
	half = (abs(rect.width() * dx) + abs(rect.height() * dy)) / 2
	centre = rect.center()
	gradient = QLinearGradient(QPointF(centre.x() - dx * half, centre.y() - dy * half), QPointF(centre.x() + dx * half, centre.y() + dy * half))
	setStops(gradient, list(stops), space)
	return gradient


def _gradient(spec: Any, angle: float) -> Backdrop:
	gradient = Gradient.decode(spec)
	items = gradient.as_list
	if not items:
		raise _theme.ThemeError(f'background gradient {spec!r} has no stops')
	values = [float(item.value) for item in items]
	low, span = min(values), (max(values) - min(values)) or 1.0
	stops = tuple(sorted(((v - low) / span, item.color.QColor) for v, item in zip(values, items)))
	return Backdrop(stops=stops, angle=angle, space=getattr(gradient, 'space', 'srgb'))


def decode(spec: Any = None, active: Optional[_theme.Theme] = None) -> Backdrop:
	"""The ground a ``background:`` value names, read against ``active`` (default: the active theme)."""
	active = active or _theme.active()
	angle = DEFAULT_ANGLE
	if isinstance(spec, dict) and 'gradient' in spec:
		unknown = set(spec) - {'gradient', 'angle'}
		if unknown:
			raise _theme.ThemeError(f'background: unknown keys {sorted(map(str, unknown))}; expected gradient, angle')
		angle = float(spec.get('angle', DEFAULT_ANGLE))
		spec = spec['gradient']
	if spec is None:
		if BACKDROP_SCALE in active.names('scales'):
			return _gradient(f'${BACKDROP_SCALE}', angle)
		return Backdrop(color=active.color('background').QColor)
	if _theme.is_token(spec):
		group, _ = active.find(_theme.token_name(spec))
		if group == 'scales':
			return _gradient(spec, angle)
		if group == 'colors':
			return Backdrop(color=Color.decode(active.resolve(spec, 'colors')).QColor)
		raise _theme.ThemeError(f'background: ${_theme.token_name(spec)} is a {group[:-1]}, not a colour or a scale')
	if isinstance(spec, (dict, list, tuple)) and not _theme.is_modifier_spec(spec) and not _isColorTuple(spec):
		return _gradient(active.resolve(spec), angle)
	return Backdrop(color=Color.decode(active.resolve(spec)).QColor)


def _isColorTuple(spec) -> bool:
	return isinstance(spec, (list, tuple)) and len(spec) in (3, 4) and all(isinstance(v, (int, float)) for v in spec)


__all__ = ('BACKDROP_SCALE', 'Backdrop', 'DEFAULT_ANGLE', 'decode', 'linearGradient')
