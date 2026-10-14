"""Dev-only: every element of the open gauge as plain scene geometry.

One function, `collect`, reads the live gauge and returns shapes: the card, the dial, the track's centre line and
edges, each tick, each label's layout box and ink box, the needle, the pivot. The wireframe draws them and
`overlapping` finds the ones that collide. `guidelines` builds the guideline layers from the same dial.
Nothing here writes to the gauge, so the overlays change neither the export nor the undo stack.

A label's *layout box* is the box the item reserves; its *ink box* is what the text actually covers.
"""
import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Set, Tuple

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QFont, QFontMetricsF, QPainterPath, QPolygonF

#: The colour each kind of element draws in.
COLORS = {
	'card': '#8b949e', 'dial': '#3fb950', 'track': '#2f81f7', 'pivot': '#ffffff', 'tick': '#7d8590', 'tick-label': '#39c5cf',
	'value': '#f0f6fc', 'unit': '#ffd33d', 'caption': '#a371f7', 'sub-label': '#f5a524', 'needle': '#ff9bce',
}
OVERLAP = '#ff3b30'

LAYERS = ('crosshair', 'radii', 'rays', 'thirds', 'text', 'safe')
LAYER_TITLES = {
	'crosshair': 'Centre crosshair', 'radii': 'Radius circles (track, ticks, labels)', 'rays': 'Angle rays (ends, every 15°)',
	'thirds': 'Thirds and golden ratio (card)', 'text': 'Value text baseline, cap and x-height', 'safe': 'Safe-area inset',
}
#: The share of the card's short side kept clear in the safe-area inset.
SAFE_INSET = 0.05
PHI = (1 + math.sqrt(5)) / 2


@dataclass
class Shape:
	"""One thing to draw: a path in scene coordinates, in a colour, solid or dashed.

	`role` marks what takes part in the overlap check: `label` (an ink box of a label), `needle`, `band` (the track).
	`value` is what a guideline stands for (an angle, a radius, a share), so a drag that snapped there can light it.
	"""
	kind: str
	name: str
	path: QPainterPath
	dashed: bool = False
	role: str = ''
	value: Optional[float] = None
	hot: bool = False


def _rect(rect: QRectF) -> QPainterPath:
	p = QPainterPath()
	p.addRect(rect)
	return p


def _line(*points: QPointF) -> QPainterPath:
	p = QPainterPath()
	p.addPolygon(QPolygonF(list(points)))
	return p


def _circle(dl, radius: float) -> QPainterPath:
	return _line(*dl.sweep(0, 360, radius))


def _inkOf(item) -> Optional[QRectF]:
	try:
		return item.scenePath().boundingRect()
	except Exception:  # noqa: BLE001 - not every item has an ink path
		return None


def _boxes(shapes: List[Shape], kind: str, name: str, item, role: str = 'label'):
	"""A label's layout box (solid) and ink box (dashed), when it is on screen."""
	try:
		if item is None or not item.isVisible():
			return
		layout = item.sceneBoundingRect()
	except Exception:  # noqa: BLE001 - mid-rebuild
		return
	if layout.isEmpty():
		return
	shapes.append(Shape(kind, f'{name} layout', _rect(layout)))
	ink = _inkOf(item)
	if ink is not None and not ink.isEmpty():
		shapes.append(Shape(kind, f'{name} ink', _rect(ink), dashed=True, role=role))


def collect(gauge, dl, card: QRectF) -> List[Shape]:
	"""Every element of `gauge` as scene geometry. `dl` is its `Dial`; `card` the card's scene rect."""
	out: List[Shape] = [Shape('card', 'card', _rect(card))]
	# the dial's square and the track: centre line, inner and outer edge
	try:
		out.append(Shape('dial', 'dial', _rect(gauge.mapToScene(gauge.gaugeRect).boundingRect())))
	except Exception:  # noqa: BLE001
		pass
	R, w = dl.R, dl.weight
	out += [Shape('track', 'track centre', _line(*dl.sweep(dl.a0, dl.a1, R - w / 2))),
	        Shape('track', 'track outer', _line(*dl.sweep(dl.a0, dl.a1, R)), dashed=True),
	        Shape('track', 'track inner', _line(*dl.sweep(dl.a0, dl.a1, max(R - w, 0))), dashed=True)]
	band = QPainterPath()
	band.addPolygon(QPolygonF(dl.sweep(dl.a0, dl.a1, R) + dl.sweep(dl.a1, dl.a0, max(R - w, 0))))
	out.append(Shape('track', 'track band', band, role='band', dashed=True))
	out.append(Shape('pivot', 'pivot', _line(dl.pivot() + QPointF(-4, 0), dl.pivot() + QPointF(4, 0))))
	out.append(Shape('pivot', 'pivot', _line(dl.pivot() + QPointF(0, -4), dl.pivot() + QPointF(0, 4))))
	# ticks: each as its line, with its label's boxes
	for surface in ('major_ticks_surface', 'minor_ticks_surface', 'micro_ticks_surface'):
		for child in getattr(gauge, surface).childItems():
			name = type(child).__name__
			if name == 'GaugeTickText':
				_boxes(out, 'tick-label', 'tick label', child)
			elif hasattr(child, 'startPoint') and hasattr(child, 'endPoint'):
				try:
					out.append(Shape('tick', 'tick', _line(child.mapToScene(child.startPoint), child.mapToScene(child.endPoint))))
				except Exception:  # noqa: BLE001
					continue
	# the labels
	_boxes(out, 'value', 'value', _textBox(gauge.valueLabel))
	_boxes(out, 'unit', 'unit', _textBox(gauge.unitLabel))
	_boxes(out, 'caption', 'caption', getattr(gauge, '_captionItem', None))
	_boxes(out, 'sub-label', 'sub-label', getattr(gauge, '_subItem', None))
	# the needle
	needle = getattr(gauge, 'needle', None)
	if needle is not None and needle.isVisible():
		try:
			path = needle.mapToScene(needle.path())
			out.append(Shape('needle', 'needle', path, role='needle'))
		except Exception:  # noqa: BLE001
			out.append(Shape('needle', 'needle', _rect(needle.sceneBoundingRect()), role='needle'))
	return out


def _textBox(label):
	return getattr(label, 'textBox', None)


def overlapping(shapes: Sequence[Shape]) -> Set[int]:
	"""Indexes of the shapes that collide: a label's ink with another label's, with the needle or with the track."""
	hits: Set[int] = set()
	checked = [(i, s) for i, s in enumerate(shapes) if s.role]
	for a in range(len(checked)):
		for b in range(a + 1, len(checked)):
			(i, p), (j, q) = checked[a], checked[b]
			if {p.role, q.role} <= {'band', 'needle'} or p.kind == q.kind == 'tick-label':
				continue
			if 'band' in (p.role, q.role) and 'tick-label' in (p.kind, q.kind):
				continue  # tick labels stand next to the track by design
			if p.path.intersects(q.path) and not _touching(p, q):
				hits |= {i, j}
	return hits


def _touching(p: Shape, q: Shape) -> bool:
	"""Two boxes that only share an edge are not a collision; a sub-pixel sliver is not either."""
	box = p.path.boundingRect().intersected(q.path.boundingRect())
	return box.width() < 0.75 or box.height() < 0.75


def _textMetrics(gauge) -> Optional[Tuple[float, float]]:
	"""(cap height, x-height) of the value text relative to its ink height; None without a font."""
	try:
		font: QFont = _textBox(gauge.valueLabel).font()
		m = QFontMetricsF(font)
		if m.capHeight() <= 0:
			return None
		return 1.0, m.xHeight() / m.capHeight()
	except Exception:  # noqa: BLE001
		return None


def guidelines(gauge, dl, card: QRectF, layers: Sequence[str]) -> List[Shape]:
	"""The guideline layers that are on, as shapes. They draw in both normal and wireframe mode."""
	out: List[Shape] = []
	c, R = dl.pivot(), dl.R
	if 'crosshair' in layers:
		out += [Shape('guide', 'crosshair', _line(QPointF(card.left(), c.y()), QPointF(card.right(), c.y())), value=0.0),
		        Shape('guide', 'crosshair', _line(QPointF(c.x(), card.top()), QPointF(c.x(), card.bottom())), value=0.0)]
	if 'radii' in layers:
		w = dl.weight
		for name, r in (('track', R - w / 2), ('ticks', R + w * 0.8), ('labels', R + w * 2.2)):
			out.append(Shape('guide', f'{name} radius', _circle(dl, r), dashed=True, value=r))
	if 'rays' in layers:
		angles = {dl.a0, dl.a1}
		lo, hi = sorted((dl.a0, dl.a1))
		step = 15
		for a in range(int(math.ceil(lo / step)) * step, int(hi) + 1, step):
			angles.add(float(a))
		for a in sorted(angles):
			hot = a in (dl.a0, dl.a1)
			out.append(Shape('guide', 'ray' if not hot else 'end ray', _line(c, dl.toScene(a, R * 1.3)), dashed=not hot, value=a))
	if 'thirds' in layers:
		for f, golden in ((1 / 3, False), (2 / 3, False), (1 / PHI ** 2, True), (1 / PHI, True)):
			x, y = card.left() + card.width() * f, card.top() + card.height() * f
			out.append(Shape('guide', 'golden' if golden else 'third', _line(QPointF(x, card.top()), QPointF(x, card.bottom())), dashed=golden, value=f))
			out.append(Shape('guide', 'golden' if golden else 'third', _line(QPointF(card.left(), y), QPointF(card.right(), y)), dashed=golden, value=f))
	if 'text' in layers:
		ink = _inkOf(_textBox(gauge.valueLabel)) if _textBox(gauge.valueLabel) is not None and _textBox(gauge.valueLabel).isVisible() else None
		ratios = _textMetrics(gauge)
		if ink is not None and ratios is not None:
			base = ink.bottom()
			for name, y in (('baseline', base), ('cap height', base - ink.height() * ratios[0]), ('x-height', base - ink.height() * ratios[1])):
				out.append(Shape('guide', name, _line(QPointF(ink.left() - 24, y), QPointF(ink.right() + 24, y)), dashed=name != 'baseline', value=y))
	if 'safe' in layers:
		inset = min(card.width(), card.height()) * SAFE_INSET
		out.append(Shape('guide', 'safe area', _rect(card.adjusted(inset, inset, -inset, -inset)), dashed=True))
	return out
