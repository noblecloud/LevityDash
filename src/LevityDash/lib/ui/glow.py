"""Stroke glow: a halo made of wider, fainter strokes of one path.

Ported from color_sphere's knot (`demo.html`, the per-segment stroke loop). For pass ``k``
(1 to ``passes``) the path is stroked again, wider and fainter, in the colour of the core:

- width: ``1 + size * (1.6 + (k - 1) * 1.2)`` times the core width;
- alpha: ``strength * 0.30`` for ``k = 1``, then ``strength * 0.12 * 2 ** (2 - k)``;
- normal (source-over) blending, so the halo keeps the hue of the core.

One more stroke, at the widest width, adds light (``Plus`` blending) with alpha
``min(bloom, widest pass alpha / 2)``. The cap matters: hue colours added together go to
white and wash the glow out.

There is no blur and no ``QGraphicsEffect``. The helper only strokes paths, so it works the
same on a worker ``QImage`` (graphs), in a cold offscreen render and on screen.

The helper draws the halo and nothing else. The caller draws the core after it, as it does
without glow, so turning glow off leaves the old paint code untouched.

YAML (the same shape for every element that takes it)::

	glow: true          # the defaults below
	glow: {strength: 1.0, size: 0.6, passes: 4, bloom: 0.04}
	glow: false         # or leave it out: no glow
"""
from dataclasses import dataclass, replace
from math import isfinite
from typing import Any, Mapping, Optional

from PySide6.QtCore import QRectF
from PySide6.QtGui import QBrush, QPainter, QPainterPath, QPen, Qt

from LevityDash.lib.stateful import StateProperty, StatefulMixin


@dataclass(frozen=True)
class Glow:
	"""Settings for one glow. Frozen: a gauge and its elements share one value."""

	#: The demo's `glow`: scales every pass alpha. 0 draws nothing.
	strength: float = 1.0
	#: The demo's `glowSize`: how fast the passes widen, as a share of the core width.
	size: float = 0.6
	#: The demo's `glowPass`: how many halo strokes, 1 to 4.
	passes: int = 4
	#: Cap on the additive pass alpha. 0 turns the pass off.
	bloom: float = 0.04

	KEYS = ('strength', 'size', 'passes', 'bloom')

	@classmethod
	def decode(cls, value: Any) -> Optional['Glow']:
		"""``None``, ``False`` and ``{}``-less off forms give ``None``. ``True`` gives the defaults.

		A mapping sets any of strength, size, passes and bloom. Anything else raises ``ValueError``.
		"""
		if value is None or value is False:
			return None
		if isinstance(value, Glow):
			return value
		if value is True:
			return cls()
		if not isinstance(value, Mapping):
			raise ValueError(f'glow is true, false or a mapping of strength, size, passes and bloom, not {value!r}')
		unknown = set(value) - set(cls.KEYS)
		if unknown:
			raise ValueError(f'glow has no {sorted(map(str, unknown))}; use {", ".join(cls.KEYS)}')
		out = cls()
		for key, limits in (('strength', (0.0, 4.0)), ('size', (0.0, 4.0)), ('bloom', (0.0, 1.0))):
			if key in value:
				number = _number(key, value[key])
				if not limits[0] <= number <= limits[1]:
					raise ValueError(f'glow {key} must be {limits[0]:g} to {limits[1]:g}, not {number:g}')
				out = replace(out, **{key: number})
		if 'passes' in value:
			passes = _number('passes', value['passes'])
			if passes != int(passes) or not 1 <= passes <= 16:
				raise ValueError(f'glow passes must be a whole number from 1 to 16, not {value["passes"]!r}')
			out = replace(out, passes=int(passes))
		return out

	@staticmethod
	def encode(value: Optional['Glow']) -> Any:
		"""Plain types for the save file: ``None``, ``True`` for the defaults, else only what differs."""
		if value is None:
			return None
		default = Glow()
		changed = {k: getattr(value, k) for k in Glow.KEYS if getattr(value, k) != getattr(default, k)}
		return changed or True

	@property
	def widest(self) -> float:
		"""The widest halo stroke as a multiple of the core width."""
		return 1 + self.size * (1.6 + (self.passes - 1) * 1.2)

	def reach(self, width: float, filled: bool = False) -> float:
		"""How far the halo reaches past the core, in pixels, on each side.

		``width`` is the core stroke width. For a filled shape pass ``filled=True`` and the
		shape's own width: the halo is then stroked along its outline.
		"""
		if self.strength <= 0:
			return 0.0
		return (self.widest * width if filled else (self.widest - 1) * width) / 2 + 1

	def pad(self, rect: QRectF, width: float, filled: bool = False) -> QRectF:
		"""``rect`` grown by :meth:`reach`: add this to a bounding rect so the halo is not clipped."""
		reach = self.reach(width, filled)
		return rect.adjusted(-reach, -reach, reach, reach)


def _number(key: str, value: Any) -> float:
	if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
		raise ValueError(f'glow {key} must be a number, not {value!r}')
	return float(value)


def resolveGlow(own: Optional[Glow], inherited: Optional[Glow]) -> Optional[Glow]:
	"""The glow an element draws: its own when it set one, else the one it inherits."""
	return own if own is not None else inherited


def passAlpha(glow: Glow, k: int) -> float:
	"""The alpha of halo pass ``k`` (1-based)."""
	return glow.strength * (0.30 if k == 1 else 0.12 * 2 ** (2 - k))


def paintGlow(painter: QPainter, path: QPainterPath, brush: QBrush, width: float, glow: Optional[Glow], dashes=None) -> None:
	"""Draw the halo of ``path``: ``glow.passes`` fainter strokes, then the capped additive pass.

	``brush`` is the core colour or gradient. ``width`` is the core stroke width; for a filled
	shape, a width that stands for its thickness (the halo is stroked along its outline and the
	core, drawn after, hides what lies inside). Does nothing when ``glow`` is ``None``, the
	strength is 0 or the width is 0. Leaves the painter as it found it.
	"""
	if glow is None or glow.strength <= 0 or width <= 0 or path.isEmpty():
		return
	painter.save()
	try:
		painter.setBrush(Qt.BrushStyle.NoBrush)
		opacity = painter.opacity()
		pen = QPen(brush, width)
		pen.setCapStyle(Qt.PenCapStyle.RoundCap)
		pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
		if dashes:
			pen.setDashPattern(list(dashes))
		alpha = 0.0
		for k in range(1, glow.passes + 1):
			alpha = passAlpha(glow, k)
			pen.setWidthF(width * (1 + glow.size * (1.6 + (k - 1) * 1.2)))
			painter.setOpacity(opacity * min(1.0, alpha))
			painter.setPen(pen)
			painter.drawPath(path)
		bloom = min(glow.bloom, alpha * 0.5)
		if bloom > 0:
			pen.setWidthF(width * glow.widest)
			painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
			painter.setOpacity(opacity * bloom)
			painter.setPen(pen)
			painter.drawPath(path)
	finally:
		painter.restore()


def _glowChanged(item) -> None:
	"""After a ``glow`` change: tell the item its bounds changed and repaint it."""
	changed = getattr(item, 'glowChanged', None)
	if changed is not None:
		changed()


class GlowMixin(StatefulMixin):
	"""Adds the ``glow`` state property. The owner draws the halo itself, with :func:`paintGlow`.

	An owner may define ``glowChanged()`` to react (grow its bounding rect, repaint). The default does nothing.
	"""

	@StateProperty(key='glow', default=None, allowNone=True, after=_glowChanged)
	def glow(self) -> Optional[Glow]:
		"""A halo of fainter, wider strokes around the item: ``true``, or ``{strength, size, passes, bloom}``.

		Left out, or ``false``, there is no glow. ``strength: 0`` also draws nothing, which turns off
		a glow the item would otherwise inherit.
		"""
		return getattr(self, '_glow', None)

	@glow.setter
	def glow(self, value: Optional[Glow]):
		self._glow = value

	@glow.decode
	def glow(self, value) -> Optional[Glow]:
		return Glow.decode(value)

	@glow.encode
	def glow(self, value: Optional[Glow]):
		return Glow.encode(value)


__all__ = ('Glow', 'GlowMixin', 'paintGlow', 'resolveGlow', 'passAlpha')
