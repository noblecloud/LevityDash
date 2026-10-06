"""Painting for the polar plots: a wind rose, a wind trail and a clock face.

Every function paints into the square the plot owns and returns nothing. The data arrives as
plain numbers and the colours as a `Look`, so none of this reads a plugin, a theme or a
dashboard; `item.py` does that and hands the results over. Angles are degrees clockwise from the
top (see `geometry`); Qt's own arcs run anticlockwise from three o'clock, which is why `_qtAngle`
exists and nothing else converts.
"""
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional, Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QRadialGradient

from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.geometry import (
	RoseData, bezierThrough, clockAngle, compassName, niceStep, polarPoint, timeOfDay,
)

__all__ = ['Look', 'drawClock', 'drawRose', 'drawTrail', 'plotCircle', 'rampColor']

_LABEL_ANGLE = 11.25  # degrees right of the top, in the gap between a rose's first two petals, where ring values sit


@dataclass
class Look:
	"""The colours and type of one plot. Built from the theme at paint time, so a theme change follows."""
	text: QColor
	muted: QColor
	faint: QColor
	rule: QColor
	accent: QColor
	display: str = 'Roboto'
	mono: str = 'Roboto Mono'
	ramp: Sequence[QColor] = field(default_factory=tuple)


def _qtAngle(degrees: float) -> float:
	"""Qt's arc angle for an angle clockwise from the top."""
	return 90.0 - degrees


def _alpha(color: QColor, alpha: float) -> QColor:
	out = QColor(color)
	out.setAlphaF(max(0.0, min(1.0, alpha * color.alphaF())))
	return out


def _font(family: str, pixels: float, bold: bool = False) -> QFont:
	font = QFont(family)
	font.setPixelSize(max(6, round(pixels)))
	font.setBold(bold)
	return font


def rampColor(colors: Sequence[QColor], t: float) -> QColor:
	"""A colour ``t`` (0 to 1) of the way along ``colors``, mixed in sRGB."""
	if not colors:
		return QColor('#ffffff')
	if len(colors) == 1:
		return QColor(colors[0])
	t = max(0.0, min(1.0, t)) * (len(colors) - 1)
	i = min(int(t), len(colors) - 2)
	f = t - i
	a, b = colors[i], colors[i + 1]
	return QColor.fromRgbF(
		a.redF() + (b.redF() - a.redF()) * f,
		a.greenF() + (b.greenF() - a.greenF()) * f,
		a.blueF() + (b.blueF() - a.blueF()) * f,
		a.alphaF() + (b.alphaF() - a.alphaF()) * f,
	)


def plotCircle(rect: QRectF, pad: float) -> tuple[float, float, float]:
	"""Centre and radius of the largest circle that fits in ``rect`` with ``pad`` pixels to spare."""
	return rect.center().x(), rect.center().y(), max(1.0, min(rect.width(), rect.height()) / 2 - pad)


def _text(painter: QPainter, text: str, x: float, y: float, color: QColor, font: QFont, align: str = 'center') -> QRectF:
	"""Draw ``text`` with its horizontal centre (or left or right edge) at x and its vertical centre at y."""
	painter.setFont(font)
	painter.setPen(color)
	metrics = QFontMetricsF(font)
	width = metrics.horizontalAdvance(text)
	height = metrics.height()
	left = x - width / 2 if align == 'center' else (x if align == 'left' else x - width)
	box = QRectF(left, y - height / 2, width, height)
	painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
	return box


def _sector(cx: float, cy: float, inner: float, outer: float, start: float, span: float) -> QPainterPath:
	"""An annular sector from ``start`` degrees (clockwise from the top) for ``span`` degrees."""
	path = QPainterPath()
	outerRect = QRectF(cx - outer, cy - outer, 2 * outer, 2 * outer)
	path.arcMoveTo(outerRect, _qtAngle(start))
	path.arcTo(outerRect, _qtAngle(start), -span)
	if inner > 0.01:
		innerRect = QRectF(cx - inner, cy - inner, 2 * inner, 2 * inner)
		path.arcTo(innerRect, _qtAngle(start + span), span)
	else:
		path.lineTo(cx, cy)
	path.closeSubpath()
	return path


def _haloText(painter: QPainter, text: str, x: float, y: float, color: QColor, font: QFont, align: str = 'center') -> None:
	"""Text with a dark outline, for labels that sit on top of data."""
	metrics = QFontMetricsF(font)
	width = metrics.horizontalAdvance(text)
	left = x - width / 2 if align == 'center' else (x if align == 'left' else x - width)
	path = QPainterPath()
	path.addText(left, y + (metrics.ascent() - metrics.descent()) / 2, font, text)
	painter.setBrush(Qt.BrushStyle.NoBrush)
	painter.setPen(QPen(QColor(0, 0, 0, 235), font.pixelSize() * 0.3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
	painter.drawPath(path)
	painter.setPen(Qt.PenStyle.NoPen)
	painter.setBrush(color)
	painter.drawPath(path)


def _rings(
	painter: QPainter, look: Look, cx: float, cy: float, outer: float,
	values: Sequence[float], toRadius: Callable[[float], float],
) -> None:
	"""Concentric rings at ``values``."""
	painter.setPen(QPen(look.rule, max(1.0, outer * 0.004)))
	painter.setBrush(Qt.BrushStyle.NoBrush)
	for value in values:
		radius = toRadius(value)
		painter.drawEllipse(QPointF(cx, cy), radius, radius)


def _ringLabels(
	painter: QPainter, look: Look, cx: float, cy: float, values: Sequence[float], toRadius: Callable[[float], float],
	label: Callable[[float], str], fontPx: float, degrees: float = _LABEL_ANGLE,
) -> None:
	"""The ring values, written last so a petal or a line never covers one."""
	font = _font(look.mono, fontPx)
	for value in values:
		x, y = polarPoint(cx, cy, toRadius(value), degrees)
		_haloText(painter, label(value), x, y, look.faint, font)


def _spokes(painter: QPainter, look: Look, cx: float, cy: float, inner: float, outer: float, count: int) -> None:
	painter.setPen(QPen(_alpha(look.rule, 0.7), max(1.0, outer * 0.003)))
	for i in range(count):
		a = polarPoint(cx, cy, inner, i * 360 / count)
		b = polarPoint(cx, cy, outer, i * 360 / count)
		painter.drawLine(QPointF(*a), QPointF(*b))


def _compass(painter: QPainter, look: Look, cx: float, cy: float, radius: float, points: int, fontPx: float) -> None:
	"""Compass letters around the rim: the four cardinals bright, the rest faint."""
	for i in range(points):
		degrees = i * 360 / points
		name = compassName(degrees, points)
		cardinal = len(name) == 1
		font = _font(look.display, fontPx * (1.0 if cardinal else 0.72), bold=cardinal)
		x, y = polarPoint(cx, cy, radius + fontPx * (0.95 if cardinal else 0.8), degrees)
		_text(painter, name, x, y, look.text if cardinal else look.faint, font)


def _legend(
	painter: QPainter, look: Look, left: float, top: float, labels: Sequence[str], colors: Sequence[QColor],
	title: str, fontPx: float,
) -> None:
	font = _font(look.mono, fontPx)
	if title:
		_text(painter, title, left, top, look.muted, _font(look.display, fontPx), 'left')
	row = fontPx * 1.5
	for i, (text, color) in enumerate(zip(labels, colors)):
		y = top + row * (i + 1.2)
		painter.setPen(Qt.PenStyle.NoPen)
		painter.setBrush(color)
		painter.drawRoundedRect(QRectF(left, y - fontPx * 0.45, fontPx * 1.1, fontPx * 0.9), fontPx * 0.2, fontPx * 0.2)
		_text(painter, text, left + fontPx * 1.6, y, look.muted, font, 'left')


def _format(value: float) -> str:
	return f'{value:.0f}' if abs(value - round(value)) < 0.05 else f'{value:.1f}'


def _suffix(unit: str) -> str:
	return {'f': '°', 'c': '°', 'º': '°', '%': '%'}.get(unit, f' {unit}' if unit else '')


# Wind rose ---------------------------------------------------------------------------------


def drawRose(
	painter: QPainter, look: Look, rect: QRectF, rose: RoseData, binColors: Sequence[QColor], unit: str,
	ringMax: Optional[float], rings: int, compass: int, current: Optional[float], legend: bool = True,
) -> None:
	"""Stacked petals: how often the wind came from each direction, split by how hard it blew."""
	painter.setRenderHint(QPainter.RenderHint.Antialiasing)
	fontPx = max(8.0, min(rect.width(), rect.height()) * 0.045)
	showLegend = legend and rect.width() > rect.height() * 1.3
	plot = QRectF(rect.left(), rect.top(), rect.width() - (fontPx * 7 if showLegend else 0), rect.height())
	cx, cy, R = plotCircle(plot, fontPx * 2.6)
	hub = R * 0.06

	peak = rose.peak * 100
	top = ringMax if ringMax else niceStep(peak, rings) * math.ceil(max(peak, 1e-6) / niceStep(peak, rings))
	step = niceStep(top, rings)
	values = [step * i for i in range(1, int(round(top / step)) + 1)]
	top = values[-1] if values else top

	def radius(percent: float) -> float:
		return hub + (R - hub) * min(1.0, percent / top)

	_spokes(painter, look, cx, cy, hub, R, 16 if compass >= 8 else 8)
	_rings(painter, look, cx, cy, R, values, radius)

	width = 360 / rose.sectors
	span = width * 0.8
	for sector, row in enumerate(rose.share):
		start = rose.sectorAngle(sector) - span / 2
		cumulative = 0.0
		for bin, share in enumerate(row):
			if share <= 0:
				continue
			inner = radius(cumulative * 100) if cumulative else hub
			cumulative += share
			path = _sector(cx, cy, inner + (0 if cumulative == share else R * 0.004), radius(cumulative * 100), start, span)
			painter.setPen(QPen(QColor(0, 0, 0, 120), max(0.5, R * 0.003)))
			painter.setBrush(binColors[min(bin, len(binColors) - 1)])
			painter.drawPath(path)

	# The centre dot is the share of calm: it has no direction, so it sits where every direction meets.
	painter.setPen(Qt.PenStyle.NoPen)
	painter.setBrush(_alpha(look.faint, 0.55 + 0.45 * min(1.0, rose.calm * 4)))
	painter.drawEllipse(QPointF(cx, cy), hub, hub)

	_ringLabels(painter, look, cx, cy, values, radius, lambda v: f'{_format(v)}%', fontPx * 0.7)
	_compass(painter, look, cx, cy, R, compass, fontPx)

	if current is not None:
		# Where the wind is from right now: a pointer on the rim, tip inwards.
		tip = polarPoint(cx, cy, R * 0.9, current)
		left = polarPoint(cx, cy, R * 1.0, current - 3.5)
		right = polarPoint(cx, cy, R * 1.0, current + 3.5)
		pointer = QPainterPath(QPointF(*tip))
		pointer.lineTo(QPointF(*left))
		pointer.lineTo(QPointF(*right))
		pointer.closeSubpath()
		painter.setPen(Qt.PenStyle.NoPen)
		painter.setBrush(look.accent)
		painter.drawPath(pointer)

	if showLegend:
		edges = rose.edges
		labels = [
			f'{_format(edges[i])}–{_format(edges[i + 1])}' if i + 1 < len(edges) else f'{_format(edges[i])}+'
			for i in range(len(edges))
		]
		_legend(painter, look, plot.right() + fontPx * 0.8, cy - R, labels, list(binColors)[:len(labels)], unit, fontPx * 0.85)


# Wind trail --------------------------------------------------------------------------------


def drawTrail(
	painter: QPainter, look: Look, rect: QRectF,
	times: Sequence[datetime], directions: Sequence[float], speeds: Sequence[float], unit: str,
	colorFor: Callable[[float], QColor], ringMax: Optional[float], rings: int, compass: int, stamps: int,
) -> None:
	"""Where the wind has pointed, oldest to newest: angle is the direction, distance from the centre the speed."""
	painter.setRenderHint(QPainter.RenderHint.Antialiasing)
	fontPx = max(8.0, min(rect.width(), rect.height()) * 0.045)
	cx, cy, R = plotCircle(rect, fontPx * 2.6)
	top = ringMax or (niceStep(max(speeds, default=1.0), rings) * math.ceil(max(max(speeds, default=1.0), 1e-6) / niceStep(max(speeds, default=1.0), rings)))
	step = niceStep(top, rings)
	values = [step * i for i in range(1, int(round(top / step)) + 1)]
	top = values[-1] if values else top

	def radius(speed: float) -> float:
		return R * min(1.0, speed / top)

	_spokes(painter, look, cx, cy, 0, R, 16 if compass >= 8 else 8)
	_rings(painter, look, cx, cy, R, values, radius)
	_compass(painter, look, cx, cy, R, compass, fontPx)

	count = len(speeds)
	if not count:
		return
	points = [polarPoint(cx, cy, radius(s), d) for d, s in zip(directions, speeds)]
	painter.setBrush(Qt.BrushStyle.NoBrush)
	for i in range(1, count):
		age = i / (count - 1)
		color = _alpha(colorFor(speeds[i]), 0.18 + 0.82 * age)
		pen = QPen(color, R * (0.008 + 0.018 * age))
		pen.setCapStyle(Qt.PenCapStyle.RoundCap)
		painter.setPen(pen)
		painter.drawLine(QPointF(*points[i - 1]), QPointF(*points[i]))
	stampFont = _font(look.mono, fontPx * 0.7)
	for i, (x, y) in enumerate(points):
		age = i / max(1, count - 1)
		dot = R * (0.012 + 0.014 * age)
		painter.setPen(Qt.PenStyle.NoPen)
		painter.setBrush(_alpha(colorFor(speeds[i]), 0.35 + 0.65 * age))
		painter.drawEllipse(QPointF(x, y), dot, dot)
		when = times[i]
		if stamps and when.minute == 0 and when.hour % stamps == 0 and i != count - 1:
			away = polarPoint(0, 0, 1, directions[i])
			_text(painter, f'{when.hour}h', x + away[0] * fontPx * 1.1, y + away[1] * fontPx * 1.1, look.muted, stampFont)

	_ringLabels(painter, look, cx, cy, values, radius, lambda v: f'{_format(v)}', fontPx * 0.7, 22.5)
	x, y = points[-1]
	painter.setBrush(Qt.BrushStyle.NoBrush)
	painter.setPen(QPen(look.accent, R * 0.012))
	painter.drawLine(QPointF(cx, cy), QPointF(x, y))
	painter.setBrush(look.accent)
	painter.setPen(QPen(QColor(0, 0, 0, 200), R * 0.008))
	painter.drawEllipse(QPointF(x, y), R * 0.04, R * 0.04)
	painter.setPen(Qt.PenStyle.NoPen)
	painter.setBrush(look.accent)
	painter.drawEllipse(QPointF(cx, cy), R * 0.02, R * 0.02)


# 24 hour clock -----------------------------------------------------------------------------


def drawClock(
	painter: QPainter, look: Look, rect: QRectF,
	times: Sequence[datetime], values: Sequence[float], unit: str, span: int, top: str,
	lo: float, hi: float, rings: int, colorFor: Optional[Callable[[float], QColor]],
	now: Optional[datetime], current: Optional[float], smooth: bool, marks: bool,
) -> None:
	"""A value over a day, wrapped round a clock face: angle is the time of day, distance from the centre the value."""
	painter.setRenderHint(QPainter.RenderHint.Antialiasing)
	fontPx = max(8.0, min(rect.width(), rect.height()) * 0.05)
	cx, cy, R = plotCircle(rect, fontPx * 1.9)
	hole = R * 0.34

	if hi <= lo:
		hi = lo + 1
	step = niceStep(hi - lo, rings)
	first = math.ceil(lo / step) * step
	ringValues = [first + step * i for i in range(int((hi - first) / step) + 1) if first + step * i <= hi + 1e-9]

	def radius(value: float) -> float:
		return hole + (R - hole) * max(0.0, min(1.0, (value - lo) / (hi - lo)))

	# Hour spokes and their numbers.
	every = 3 if span == 24 else 1
	for h in range(0, span, every):
		degrees = clockAngle(h, span, top)
		painter.setPen(QPen(_alpha(look.rule, 0.8 if h % (6 if span == 24 else 3) == 0 else 0.45), max(1.0, R * 0.003)))
		painter.drawLine(QPointF(*polarPoint(cx, cy, hole, degrees)), QPointF(*polarPoint(cx, cy, R, degrees)))
		x, y = polarPoint(cx, cy, R + fontPx * 0.95, degrees)
		strong = h % (6 if span == 24 else 3) == 0
		label = str(h if span == 24 else (h or 12))
		_text(painter, label, x, y, look.text if strong else look.faint, _font(look.display, fontPx * (1.0 if strong else 0.8), bold=strong))
	painter.setBrush(Qt.BrushStyle.NoBrush)
	painter.setPen(QPen(look.rule, max(1.0, R * 0.005)))
	painter.drawEllipse(QPointF(cx, cy), hole, hole)
	_rings(painter, look, cx, cy, R, ringValues, radius)

	points = []
	for when, value in zip(times, values):
		x, y = polarPoint(cx, cy, radius(value), clockAngle(timeOfDay(when), span, top))
		points.append((x, y))
	covered = (times[-1] - times[0]).total_seconds() / 3600 if len(times) > 1 else 0
	closed = len(points) >= 3 and covered >= span * 0.9
	curve = QPainterPath(QPointF(*points[0])) if points else QPainterPath()
	if len(points) >= 2:
		if smooth:
			for c1, c2, end in bezierThrough(points, closed=closed):
				curve.cubicTo(QPointF(*c1), QPointF(*c2), QPointF(*end))
		else:
			for x, y in points[1:]:
				curve.lineTo(x, y)
			if closed:
				curve.lineTo(*points[0])

	if points:
		# A value-keyed gradient colours the line and the area by distance from the centre, so a warm hour reads warm.
		if colorFor is not None:
			shade = QRadialGradient(QPointF(cx, cy), R)
			shade.setColorAt(0.0, colorFor(lo))
			for i in range(0, 13):
				shade.setColorAt(max(hole / R, 0) + (1 - hole / R) * i / 12, colorFor(lo + (hi - lo) * i / 12))
			line = QBrush(shade)
			fillShade = QRadialGradient(QPointF(cx, cy), R)
			for stop in shade.stops():
				fillShade.setColorAt(stop[0], _alpha(stop[1], 0.30))
			fill = QBrush(fillShade)
		else:
			line = QBrush(look.accent)
			fill = QBrush(_alpha(look.accent, 0.22))
		area = QPainterPath(curve)
		if not closed:
			area.lineTo(cx, cy)
			area.closeSubpath()
		disc = QPainterPath()
		disc.addEllipse(QPointF(cx, cy), hole, hole)
		painter.setPen(Qt.PenStyle.NoPen)
		painter.setBrush(fill)
		painter.drawPath(area.subtracted(disc))
		pen = QPen(line, max(2.0, R * 0.018))
		pen.setCapStyle(Qt.PenCapStyle.RoundCap)
		pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
		painter.setPen(pen)
		painter.setBrush(Qt.BrushStyle.NoBrush)
		painter.drawPath(curve)

	_ringLabels(painter, look, cx, cy, ringValues, radius, lambda v: f'{_format(v)}', fontPx * 0.72, 3.5)

	# The highest and lowest hours, written where they happen.
	if marks and values:
		for pick in (max, min):
			i = values.index(pick(values))
			x, y = points[i]
			painter.setPen(QPen(QColor(0, 0, 0, 200), R * 0.006))
			painter.setBrush(look.text)
			painter.drawEllipse(QPointF(x, y), R * 0.022, R * 0.022)
			away = polarPoint(0, 0, 1, clockAngle(timeOfDay(times[i]), span, top))
			_haloText(painter, f'{_format(values[i])}{_suffix(unit)}', x + away[0] * fontPx * 1.5, y + away[1] * fontPx * 1.5, look.text, _font(look.mono, fontPx * 0.9, bold=True))

	# Now: a hand to the rim and a bright dot where the value is.
	if now is not None:
		degrees = clockAngle(timeOfDay(now), span, top)
		painter.setPen(QPen(look.accent if colorFor is None else look.text, max(1.0, R * 0.008), Qt.PenStyle.DashLine))
		painter.drawLine(QPointF(*polarPoint(cx, cy, hole, degrees)), QPointF(*polarPoint(cx, cy, R, degrees)))
		if current is not None:
			x, y = polarPoint(cx, cy, radius(current), degrees)
			painter.setPen(QPen(QColor(0, 0, 0, 220), R * 0.01))
			painter.setBrush(look.accent if colorFor is None else colorFor(current))
			painter.drawEllipse(QPointF(x, y), R * 0.04, R * 0.04)

	if current is not None:
		_text(painter, f'{_format(current)}{_suffix(unit)}', cx, cy, look.text, _font(look.mono, hole * 0.62, bold=True))
