"""Painting for `plot: radar`: things around you, each at its bearing and its distance.

Like `draw.py`, nothing here reads a plugin or a theme: `item.py` hands over plain `Blip`s and a `Look`. North is
at the top, you are in the middle, and distance grows outward on a straight scale (a plane at half the range sits
half way out), so what is on the rings is what is on the sky.
"""
import math
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QConicalGradient, QFontMetricsF, QPainter, QPainterPath, QPen, QRadialGradient, QTransform

from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.draw import (
	Look, _alpha, _compass, _font, _haloText, _ringLabels, _rings, _spokes, _text, _qtAngle, plotCircle,
)
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar import glyphs as glyphSet
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.geometry import niceStep, polarPoint

__all__ = ['Blip', 'drawRadar', 'ringValues', 'label']


@dataclass(frozen=True)
class Blip:
	"""One thing on the radar. ``altitude`` colours it, ``heading`` and ``speed`` draw its tail (speed 0: none)."""
	name: str
	bearing: float
	distance: float
	altitude: float = 0.0
	heading: float = 0.0
	speed: float = 0.0
	kind: str = ''  # ICAO type designator (B738), for the silhouette
	category: str = ''  # ADS-B emitter category (A3), for the silhouette when the type is unknown


def ringValues(top: float, rings: int) -> list[float]:
	"""Ring distances up to ``top``: round numbers about ``rings`` of them, the last at ``top`` or inside it."""
	step = niceStep(top, max(1, rings))
	return [step * i for i in range(1, int(top / step + 1e-9) + 1)]


def label(blip: Blip, altitudes: bool) -> str:
	"""``UAL123 120`` for a plane at 12,000 ft (flight levels, in hundreds of feet), or just the name."""
	if altitudes and blip.altitude > 0:
		return f'{blip.name} {round(blip.altitude / 100):d}'
	return blip.name


def drawRadar(
	painter: QPainter, look: Look, rect: QRectF, blips: Sequence[Blip], top: float, rings: int, compass: int,
	colorFor: Callable[[float], QColor], labels: int, altitudes: bool = True, sweep: Optional[float] = None,
	unit: str = 'nmi', legend: bool = True, glyphs: bool = True, glyphScale: float = 1.0,
) -> None:
	"""The disc, rings, spokes and compass, then the blips nearest first, the nearest ``labels`` named.

	``glyphs`` draws each blip as a silhouette of its kind (`glyphs.classify`) turned to its heading; off, a dot with
	a tail. ``glyphScale`` multiplies the silhouette, so a dashboard can ask for larger traffic than the radius alone
	gives. ``top`` is the distance of the rim. ``sweep`` is the sweep line's bearing in degrees, or None for no sweep: a
	wedge of light that trails it and brightens the blips it has just passed."""
	fontPx = max(8.0, min(rect.width(), rect.height()) / 28)
	cx, cy, radius = plotCircle(rect, fontPx * 2.2)
	if radius < 12 or top <= 0:
		return
	toRadius = lambda value: radius * min(value / top, 1.0)

	# The disc: a faint glow that deepens toward the rim, so the edge reads as a screen.
	glow = QRadialGradient(QPointF(cx, cy), radius)
	glow.setColorAt(0.0, _alpha(look.accent, 0.04))
	glow.setColorAt(0.85, _alpha(look.accent, 0.09))
	glow.setColorAt(1.0, _alpha(look.accent, 0.16))
	painter.setPen(Qt.PenStyle.NoPen)
	painter.setBrush(QBrush(glow))
	painter.drawEllipse(QPointF(cx, cy), radius, radius)

	values = ringValues(top, rings)
	_spokes(painter, look, cx, cy, 0, radius, 12)
	_rings(painter, look, cx, cy, radius, values, toRadius)
	painter.setPen(QPen(_alpha(look.accent, 0.8), max(1.5, radius * 0.006)))
	painter.setBrush(Qt.BrushStyle.NoBrush)
	painter.drawEllipse(QPointF(cx, cy), radius, radius)
	_compass(painter, look, cx, cy, radius, compass, fontPx)

	if sweep is not None:
		wedge = QConicalGradient(QPointF(cx, cy), _qtAngle(sweep) + 0.0)
		# QConicalGradient runs anticlockwise from its angle, so the trail (behind a clockwise sweep) is 0 to 0.12.
		wedge.setColorAt(0.0, _alpha(look.accent, 0.38))
		wedge.setColorAt(0.12, _alpha(look.accent, 0.0))
		wedge.setColorAt(1.0, _alpha(look.accent, 0.0))
		painter.setPen(Qt.PenStyle.NoPen)
		painter.setBrush(QBrush(wedge))
		painter.drawEllipse(QPointF(cx, cy), radius, radius)
		painter.setPen(QPen(_alpha(look.accent, 0.9), max(1.0, radius * 0.005)))
		painter.drawLine(QPointF(cx, cy), QPointF(*polarPoint(cx, cy, radius, sweep)))

	# Blips, farthest first so the near ones sit on top. A blip beyond the rim is not drawn.
	drawn = [b for b in sorted(blips, key=lambda b: -b.distance) if b.distance <= top]
	tail = radius * 0.07
	for blip in drawn:
		x, y = polarPoint(cx, cy, toRadius(blip.distance), blip.bearing)
		color = colorFor(blip.altitude)
		if glyphs:
			glyph = glyphSet.classify(blip.kind, blip.category)
			half = max(7.0, radius * 0.075) * glyph.size * glyphScale
			halo = QRadialGradient(QPointF(x, y), half * 2.2)
			halo.setColorAt(0.0, _alpha(color, 0.38))
			halo.setColorAt(1.0, _alpha(color, 0.0))
			painter.setPen(Qt.PenStyle.NoPen)
			painter.setBrush(QBrush(halo))
			painter.drawEllipse(QPointF(x, y), half * 2.2, half * 2.2)
			turn = QTransform().translate(x, y).rotate(blip.heading if blip.speed > 0 else 0.0).scale(half * 2, half * 2)
			painter.setPen(QPen(QColor(0, 0, 0, 210), max(0.8, half * 0.07), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
			painter.setBrush(color)
			painter.drawPath(turn.map(glyphSet.path(glyph.shape)))
			continue
		if blip.speed > 0:
			length = tail * (0.6 + min(blip.speed, 600) / 600)
			ex, ey = polarPoint(x, y, length, blip.heading)
			painter.setPen(QPen(_alpha(color, 0.9), max(1.2, radius * 0.007), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
			painter.drawLine(QPointF(x, y), QPointF(ex, ey))
		size = max(2.5, radius * 0.016)
		halo = QRadialGradient(QPointF(x, y), size * 3.2)
		halo.setColorAt(0.0, _alpha(color, 0.65))
		halo.setColorAt(1.0, _alpha(color, 0.0))
		painter.setPen(Qt.PenStyle.NoPen)
		painter.setBrush(QBrush(halo))
		painter.drawEllipse(QPointF(x, y), size * 3.2, size * 3.2)
		painter.setBrush(color)
		painter.drawEllipse(QPointF(x, y), size, size)

	# Names, nearest first, each dropped when it would sit on one already written.
	if labels > 0:
		font = _font(look.mono, fontPx * 0.72)
		metrics = QFontMetricsF(font)
		taken: list[QRectF] = []
		for blip in sorted(drawn, key=lambda b: b.distance)[:labels]:
			x, y = polarPoint(cx, cy, toRadius(blip.distance), blip.bearing)
			text = label(blip, altitudes)
			width, height = metrics.horizontalAdvance(text), metrics.height()
			onRight = x < cx + radius * 0.55
			box = QRectF(x + fontPx * 0.7 if onRight else x - fontPx * 0.7 - width, y - height * 1.05, width, height)
			if any(box.adjusted(-2, -1, 2, 1).intersects(other) for other in taken):
				continue
			taken.append(box)
			_haloText(painter, text, box.center().x(), box.center().y(), look.text, font)

	_ringLabels(painter, look, cx, cy, values, toRadius, lambda v: f'{v:g}', fontPx * 0.8, degrees=202)

	# You, in the middle.
	painter.setPen(QPen(look.text, max(1.0, radius * 0.005)))
	painter.setBrush(look.accent)
	painter.drawEllipse(QPointF(cx, cy), max(2.5, radius * 0.014), max(2.5, radius * 0.014))

	if legend:
		note = f'{len(blips)} in range · {unit}'
		_text(painter, note, rect.left() + fontPx * 0.4, rect.bottom() - fontPx * 0.8, look.muted, _font(look.mono, fontPx * 0.9), 'left')
