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
	Look, _alpha, _font, _haloText, _text, _qtAngle, plotCircle,
)
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar import glyphs as glyphSet
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.geometry import compassName, niceStep, polarPoint

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
	slot: int = 0  # which slot it came from, so a click can read the rest of that slot


# Every size on the radar is a share of the plot's short side, so it scales with the card and the display. Two tiers of
# text: ROOM (ring distances and the cardinals, read across the room) and DETAIL (callsigns, intercardinals, the count,
# read standing in front of it).
_ROOM, _DETAIL = 1.2, 0.92
_BLIP = 0.1  # a silhouette's half-size, as a share of the radius


def _fontPx(rect: QRectF) -> float:
	return max(9.0, min(rect.width(), rect.height()) / 22)


def _blipHalf(radius: float, glyphSize: float = 1.0, glyphScale: float = 1.0) -> float:
	return max(8.0, radius * _BLIP) * glyphSize * glyphScale


def _drawPaths(painter: QPainter, look: Look, cx: float, cy: float, radius: float, top: float,
		paths: Sequence[Sequence[tuple]]) -> None:
	"""A line through each trail, oldest to newest, fading out with age. Points beyond the rim are left off."""
	for points in paths:
		if len(points) < 2:
			continue
		oldest = max((age for age, _, _ in points), default=0.0) or 1.0
		painter.setPen(QPen(_alpha(look.accent, 0.1), max(1.0, radius * 0.006)))
		last = None
		for age, bearing, distance in points:
			if distance > top:
				last = None
				continue
			point = QPointF(*polarPoint(cx, cy, radius * min(distance / top, 1.0), bearing))
			if last is not None:
				fade = 1.0 - min(1.0, max(0.0, age / oldest))  # newest is 1, oldest is 0
				painter.setPen(QPen(_alpha(look.accent, 0.12 + 0.55 * fade), max(1.0, radius * 0.006)))
				painter.drawLine(last, point)
			last = point


def hitBlip(rect: QRectF, blips: Sequence[Blip], top: float, pos: QPointF, slack: float = 12.0) -> Optional[Blip]:
	"""The blip under ``pos`` in the same coordinates ``drawRadar`` paints, or None.

	The reach is a silhouette's own half-size plus ``slack``, so a small mark is still comfortable to hit; a blip
	beyond the rim is not drawn and not returned. Where two share the point, the one nearest the pointer wins.
	"""
	if not blips or top <= 0:
		return None
	fontPx = _fontPx(rect)
	cx, cy, radius = plotCircle(rect, fontPx * 1.9)
	if radius < 12:
		return None
	reach = _blipHalf(radius) * 2 + slack
	found, nearest = None, float('inf')
	for blip in blips:
		if blip.distance > top:
			continue
		x, y = polarPoint(cx, cy, radius * min(blip.distance / top, 1.0), blip.bearing)
		gap = math.hypot(pos.x() - x, pos.y() - y)
		if gap <= reach and gap < nearest:
			found, nearest = blip, gap
	return found


def drawPopover(
	painter: QPainter, look: Look, rect: QRectF, blip: Blip, rows: Sequence[tuple[str, str]], top: float,
) -> QRectF:
	"""A panel beside ``blip``: its name in bold, then ``rows`` of ``(label, value)``, kept inside ``rect``.

	It is drawn where there is room, so a plane near the rim gets its details pushed back toward the middle.
	"""
	fontPx = max(9.0, min(rect.width(), rect.height()) / 34)
	titleFont = _font(look.display, fontPx * 1.15, bold=True)
	rowFont = _font(look.mono, fontPx * 0.9)
	title = blip.name or 'Aircraft'
	titleMetrics = QFontMetricsF(titleFont)
	rowMetrics = QFontMetricsF(rowFont)
	pad = fontPx * 0.8
	lineHeight = rowMetrics.height() * 1.25
	width = max([titleMetrics.horizontalAdvance(title)] + [
		rowMetrics.horizontalAdvance(f'{label}: {value}') for label, value in rows
	]) + pad * 2
	height = titleMetrics.height() + lineHeight * len(rows) + pad * 1.6

	cx, cy, radius = plotCircle(rect, _fontPx(rect) * 2.1)
	x, y = polarPoint(cx, cy, radius * min(blip.distance / top, 1.0) if top > 0 else 0.0, blip.bearing)
	left = x + fontPx * 1.6
	if left + width > rect.right() - 2:
		left = x - fontPx * 1.6 - width
	left = max(rect.left() + 2, min(left, rect.right() - width - 2))
	panelTop = max(rect.top() + 2, min(y - height / 2, rect.bottom() - height - 2))
	panel = QRectF(left, panelTop, width, height)

	painter.setPen(QPen(_alpha(look.accent, 0.75), 1.0))
	painter.setBrush(QColor(look.rule.red(), look.rule.green(), look.rule.blue(), 240))
	painter.drawRoundedRect(panel, fontPx * 0.6, fontPx * 0.6)
	_text(painter, title, left + pad, panelTop + pad * 0.8 + titleMetrics.height() / 2, look.text, titleFont, 'left')
	rowY = panelTop + pad * 0.8 + titleMetrics.height() + lineHeight * 0.5
	for labelText, value in rows:
		_text(painter, f'{labelText}: {value}', left + pad, rowY, look.muted, rowFont, 'left')
		rowY += lineHeight
	return panel


def ringValues(top: float, rings: int) -> list[float]:
	"""Ring distances up to ``top``: round numbers about ``rings`` of them, the last at ``top`` or inside it."""
	step = niceStep(top, max(1, rings))
	return [step * i for i in range(1, int(top / step + 1e-9) + 1)]


def label(blip: Blip, altitudes: bool) -> str:
	"""``UAL123 120`` for a plane at 12,000 ft (flight levels, in hundreds of feet), or just the name."""
	if altitudes and blip.altitude > 0:
		return f'{blip.name} {round(blip.altitude / 100):d}'
	return blip.name


def _radarRings(painter: QPainter, look: Look, cx: float, cy: float, outer: float, values, toRadius) -> None:
	"""Rings in the accent, bright enough to count against the disc's glow."""
	painter.setPen(QPen(_alpha(look.accent, 0.45), max(1.5, outer * 0.007)))
	painter.setBrush(Qt.BrushStyle.NoBrush)
	for value in values:
		radius = toRadius(value)
		painter.drawEllipse(QPointF(cx, cy), radius, radius)


def _radarSpokes(painter: QPainter, look: Look, cx: float, cy: float, outer: float, count: int) -> None:
	"""Spokes: the four cardinals stronger than the rest, all weaker than the rings."""
	for i in range(count):
		cardinal = i % (count // 4) == 0
		painter.setPen(QPen(_alpha(look.accent, 0.3 if cardinal else 0.14), max(1.0, outer * (0.005 if cardinal else 0.003))))
		painter.drawLine(QPointF(cx, cy), QPointF(*polarPoint(cx, cy, outer, i * 360 / count)))


def _radarCompass(painter: QPainter, look: Look, cx: float, cy: float, radius: float, points: int, fontPx: float) -> None:
	"""Compass letters round the rim: the cardinals at room size and bold, the rest at detail size, all legible."""
	for i in range(points):
		degrees = i * 360 / points
		name = compassName(degrees, points)
		cardinal = len(name) == 1
		font = _font(look.display, fontPx * (_ROOM if cardinal else _DETAIL * 0.85), bold=True)
		x, y = polarPoint(cx, cy, radius + fontPx * (1.0 if cardinal else 0.85), degrees)
		_text(painter, name, x, y, look.text if cardinal else _alpha(look.text, 0.75), font)


def _radarRingLabels(
	painter: QPainter, look: Look, cx: float, cy: float, radius: float, values, toRadius, fontPx: float,
	unit: str, avoid: Sequence[tuple[float, float]],
) -> None:
	"""Ring distances in bold at room size, set on the rings between two spokes, in whichever quadrant has the
	fewest blips near its labels (so they are not buried)."""
	if not values:
		return
	font = _font(look.mono, fontPx, bold=True)
	clear = fontPx * 3.5

	def crowd(degrees: float) -> float:
		return sum(
			max(0.0, 1.0 - math.hypot(px - x, py - y) / clear)
			for value in values for x, y in [polarPoint(cx, cy, toRadius(value), degrees)] for px, py in avoid
		)

	# Between spokes (which run every 30 degrees), so a label never sits on a spoke.
	degrees = min((15.0 + 30.0 * i for i in range(12)), key=lambda d: (round(crowd(d), 2), abs(d - 195.0)))
	for value in values:
		text = f'{value:g}'
		metrics = QFontMetricsF(font)
		w, h = metrics.horizontalAdvance(text) + fontPx * 0.5, metrics.height() * 0.95
		# one on the rim is pulled inside it, so it does not cover the compass letters just beyond
		x, y = polarPoint(cx, cy, min(toRadius(value), radius - h * 0.75), degrees)
		pill = QRectF(x - w / 2, y - h / 2, w, h)
		painter.setPen(QPen(_alpha(look.accent, 0.55), max(1.0, radius * 0.004)))
		painter.setBrush(QColor(0, 0, 0, 175))
		painter.drawRoundedRect(pill, h / 2, h / 2)
		_text(painter, text, x, y, look.text, font)


def drawRadar(
	painter: QPainter, look: Look, rect: QRectF, blips: Sequence[Blip], top: float, rings: int, compass: int,
	colorFor: Callable[[float], QColor], labels: int, altitudes: bool = True, sweep: Optional[float] = None,
	unit: str = 'nmi', legend: bool = True, glyphs: bool = True, glyphScale: float = 1.0,
	paths: Optional[Sequence[Sequence[tuple]]] = None,
) -> None:
	"""The disc, rings, spokes and compass, then the blips nearest first, the nearest ``labels`` named.

	``glyphs`` draws each blip as a silhouette of its kind (`glyphs.classify`) turned to its heading; off, a dot with
	a tail. ``glyphScale`` multiplies the silhouette, so a dashboard can ask for larger traffic than the radius alone
	gives. ``paths`` are the trails, each ``(age, bearing, distance)`` oldest first, painted under the blips and fading
	with age. ``top`` is the distance of the rim. ``sweep`` is the sweep line's bearing in degrees, or None for no sweep: a
	wedge of light that trails it and brightens the blips it has just passed."""
	fontPx = _fontPx(rect)
	cx, cy, radius = plotCircle(rect, fontPx * 1.9)
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
	_radarSpokes(painter, look, cx, cy, radius, 12)
	_radarRings(painter, look, cx, cy, radius, values, toRadius)
	painter.setPen(QPen(_alpha(look.accent, 0.8), max(1.5, radius * 0.006)))
	painter.setBrush(Qt.BrushStyle.NoBrush)
	painter.drawEllipse(QPointF(cx, cy), radius, radius)
	_radarCompass(painter, look, cx, cy, radius, compass, fontPx)

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

	if paths:
		_drawPaths(painter, look, cx, cy, radius, top, paths)

	# Blips, farthest first so the near ones sit on top. A blip beyond the rim is not drawn.
	drawn = [b for b in sorted(blips, key=lambda b: -b.distance) if b.distance <= top]
	tail = radius * 0.07
	for blip in drawn:
		x, y = polarPoint(cx, cy, toRadius(blip.distance), blip.bearing)
		color = colorFor(blip.altitude)
		if glyphs:
			glyph = glyphSet.classify(blip.kind, blip.category)
			half = _blipHalf(radius, glyph.size, glyphScale)
			halo = QRadialGradient(QPointF(x, y), half * 2.2)
			halo.setColorAt(0.0, _alpha(color, 0.5))
			halo.setColorAt(1.0, _alpha(color, 0.0))
			painter.setPen(Qt.PenStyle.NoPen)
			painter.setBrush(QBrush(halo))
			painter.drawEllipse(QPointF(x, y), half * 2.2, half * 2.2)
			turn = QTransform().translate(x, y).rotate(blip.heading if blip.speed > 0 else 0.0).scale(half * 2, half * 2)
			painter.setPen(QPen(QColor(0, 0, 0, 235), max(1.0, half * 0.1), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
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

	# Names, nearest first. Each tries the right of its blip, then the left, above, below; one that fits nowhere
	# clear of the blips and the names already written is dropped.
	taken: list[QRectF] = [
		QRectF(*polarPoint(cx, cy, toRadius(b.distance), b.bearing), 0, 0).adjusted(-half, -half, half, half)
		for b in drawn for half in [_blipHalf(radius, glyphSet.classify(b.kind, b.category).size if glyphs else 0.3, glyphScale)]
	]
	if labels > 0:
		font = _font(look.mono, fontPx * _DETAIL, bold=True)
		metrics = QFontMetricsF(font)
		gap = fontPx * 0.25
		bounds = QRectF(rect).adjusted(0, 0, 0, -fontPx * 1.6)
		for blip in sorted(drawn, key=lambda b: b.distance)[:labels]:
			x, y = polarPoint(cx, cy, toRadius(blip.distance), blip.bearing)
			half = _blipHalf(radius, glyphSet.classify(blip.kind, blip.category).size if glyphs else 0.3, glyphScale)
			name, altitude = blip.name, ''
			if altitudes and blip.altitude > 0:
				altitude = f' {round(blip.altitude / 100):d}'
			width, height = metrics.horizontalAdvance(name + altitude), metrics.height()
			reach = half + gap
			for box in (
				QRectF(x + reach, y - height / 2, width, height), QRectF(x - reach - width, y - height / 2, width, height),
				QRectF(x - width / 2, y - reach - height, width, height), QRectF(x - width / 2, y + reach, width, height),
			):
				mine = box.adjusted(-gap, -gap * 0.5, gap, gap * 0.5)
				if not bounds.contains(mine):
					continue
				# a plane's own box is in ``taken`` as well, but a label starts clear of it
				if any(mine.intersects(other) for other in taken if not other.contains(QPointF(x, y))):
					continue
				taken.append(mine)
				_haloText(painter, name, box.left() + metrics.horizontalAdvance(name) / 2, box.center().y(), look.text, font)
				if altitude:
					_haloText(
						painter, altitude, box.left() + metrics.horizontalAdvance(name) + metrics.horizontalAdvance(altitude) / 2,
						box.center().y(), colorFor(blip.altitude).lighter(125), font,
					)
				break

	_radarRingLabels(painter, look, cx, cy, radius, values, toRadius, fontPx * _ROOM, unit, [
		polarPoint(cx, cy, toRadius(b.distance), b.bearing) for b in drawn
	])

	# You, in the middle.
	painter.setPen(QPen(look.text, max(1.0, radius * 0.005)))
	painter.setBrush(look.accent)
	painter.drawEllipse(QPointF(cx, cy), max(2.5, radius * 0.014), max(2.5, radius * 0.014))

	if legend:
		note = f'{len(blips)} in range · {unit}'
		_text(painter, note, rect.left() + fontPx * 0.4, rect.bottom() - fontPx * 0.8, look.text, _font(look.mono, fontPx * 1.05, bold=True), 'left')
