"""A text fill that is a gradient of a scale around a value: ``fill-gradient: {scale: $temperature, of: <key>, spread: 8°F}``.

The glyphs are filled with the scale's colours from ``value + spread`` at one end to ``value - spread`` at the other, so
the colour of the reading sits in the middle and a hot number runs a little hotter at the top and cooler at the foot. It
follows the value like ``color: {scale, of}`` does (`colors/bound.py`) and replaces that colour while it has a value.

	fill-gradient: {scale: $temperature, of: environment.temperature.temperature, spread: 8°F}
	fill-gradient: {scale: $temperature, of: environment.temperature.temperature, spread: 8°F, angle: 160}

``spread`` is a distance on the scale, in the value's own unit unless it carries one (``8°F`` is a step of 8 degrees
Fahrenheit, whatever the data is measured in). ``angle`` is in CSS degrees (180, the default, runs top to bottom, 90
left to right). ``fallback`` is the colour to use before there is a value (the item's own ``color`` otherwise).
"""
import math
from typing import Any, Mapping, Optional

from PySide6.QtGui import QBrush, QGradient, QLinearGradient
from unitcorn import Measurement

from LevityDash.lib.stopunits import parseStop, toDataUnit
from LevityDash.lib.ui.colors.bound import BoundColor
from LevityDash.lib.ui.colors.color import Color

__all__ = ('FillGradient', 'decodeFillGradient')

KEYS = frozenset({'scale', 'of', 'spread', 'angle', 'fallback', 'stops'})
STOPS = 7


class FillGradient:
	"""The decoded ``fill-gradient``: what to follow and how a value becomes a brush."""

	__slots__ = ('spec', 'of', 'bound', 'spread', 'angle', 'fallback', 'stops')

	def __init__(self, spec: Mapping):
		unknown = set(spec) - KEYS
		if unknown or 'scale' not in spec or 'of' not in spec:
			raise ValueError(f'fill-gradient takes scale, of, spread, angle and fallback, not {sorted(map(str, spec))}')
		self.spec = dict(spec)
		self.of = spec['of']
		self.bound = BoundColor({'scale': spec['scale'], 'of': spec['of']})
		parsed = parseStop(spec.get('spread', 0))
		if parsed is None:
			raise ValueError(f'spread {spec.get("spread")!r} is not a number with an optional unit')
		self.spread = parsed
		angle = spec.get('angle', 180)
		if isinstance(angle, bool) or not isinstance(angle, (int, float)):
			raise TypeError(f'angle is a number of degrees, not {angle!r}')
		self.angle = float(angle)
		stops = spec.get('stops', STOPS)
		if isinstance(stops, bool) or not isinstance(stops, int) or not 2 <= stops <= 32:
			raise ValueError(f'stops is a whole number from 2 to 32, not {stops!r}')
		self.stops = stops
		self.fallback = Color.decode(spec['fallback']) if spec.get('fallback') is not None else None

	def _delta(self, value: Any) -> float:
		"""The spread in the unit of ``value``, as a distance (8°F is 4.44°C, not -13.3°C)."""
		number, unit = self.spread
		if unit and isinstance(value, Measurement):
			cls = type(value)
			return toDataUnit(number, unit, cls) - toDataUnit(0.0, unit, cls)
		return number

	def brushFor(self, value: Any) -> Optional[QBrush]:
		"""The brush for ``value``, or None when it has no number to place."""
		if (placed := self.bound.place(value)) is None:
			return None
		gradient, number = placed
		try:
			delta = self._delta(value)
		except (TypeError, ValueError):
			return None
		# Bounding-box units: the brush covers whatever glyphs it is painted on, however large.
		radians = math.radians(self.angle)
		dx, dy = math.sin(radians), -math.cos(radians)
		grad = QLinearGradient(0.5 - dx / 2, 0.5 - dy / 2, 0.5 + dx / 2, 0.5 + dy / 2)
		grad.setCoordinateMode(QGradient.ObjectBoundingMode)
		for n in range(self.stops):
			t = n / (self.stops - 1)
			grad.setColorAt(t, gradient.get_color_for_value(number + delta * (1 - 2 * t)).QColor)
		return QBrush(grad)

	resolve = brushFor

	def __repr__(self):
		return f'FillGradient({self.spec!r})'


def decodeFillGradient(spec: Any) -> Optional[FillGradient]:
	if spec in (None, False):
		return None
	if isinstance(spec, FillGradient):
		return spec
	if not isinstance(spec, Mapping):
		raise TypeError(f'fill-gradient is a mapping with scale and of, not {spec!r}')
	return FillGradient(spec)
