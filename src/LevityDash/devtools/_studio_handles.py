"""Dev-only: drag handles drawn over the gauge on Gauge Studio's preview.

Each handle edits one property of the gauge and writes it back live, the way a
control in the panel does (`Studio.handleEdit`). On release the studio rebuilds
the gauge from its saved form and records one undo step.

========================== ===============================================================
handle                     writes
========================== ===============================================================
arc start and end dots     `arc.start-angle`, `arc.end-angle`
radius dot (on the track)  `radius`
weight dot (track's inner) `arc.weight`
needle tip                 the preview value (not a gauge property)
marker dot                 the marker's `value`, when it is a number
zone edge square           `from` or `to` of the zone; a shared cutoff moves both zones
fill end dot               `from` or `to` of the fill, when it is a number
value, unit, caption,      `value-label.offset`, `unit-label.offset`, and `offset` inside
sub-label (drag the text)  `caption` and `sub-label`
corner squares (click)     `anchor`
gradient node (*Edit       the stop's value in its own unit (drag along the track); drag off
gradient* on)              the track, or Delete, removes it; double click picks its colour;
                           click on the track adds a stop with the colour there
========================== ===============================================================

*Edit gradient* shows one node per stop of `arc.gradient` and dims every other handle, so the two
kinds do not fight for the mouse. A node shows its value and unit while it is dragged.

Handles show while the pointer is over the preview and brighten under the
cursor. Shift while dragging snaps finely; without it a value snaps to a round
step when *Snap* is on. The overlay is one item (`Overlay`) so a screenshot can
hide every handle at once.
"""
import copy
import math
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem

from LevityDash.devtools import _studio_schema as schema
from LevityDash.devtools import _studio_stops as stops
from LevityDash.devtools._studio_stops import niceStep, snapTo

Z = 10000

COLORS = {
	'angle': '#2f81f7', 'radius': '#3fb950', 'weight': '#a371f7', 'needle': '#ffd33d', 'marker': '#f5a524',
	'zone': '#ff7b72', 'fill': '#39c5cf', 'label': '#f0f6fc', 'corner': '#8b949e', 'gradient': '#ffffff', 'track': '#ffffff',
}

GRADIENT = ('arc', 'gradient')


class Dial:
	"""The dial's geometry in the arc's own coordinates: the pivot is (0, 0), 0 degrees is up and angles run clockwise."""

	def __init__(self, gauge):
		self.gauge = gauge
		self.arc = gauge.arc
		self.R = float(gauge.radius)
		self.weight = float(self.arc.weight_px)
		self.a0 = float(gauge.startAngle)
		self.a1 = float(gauge.endAngle)
		rng = gauge._range
		self.lo = float(rng.rounded_min)
		self.span = float(rng.rounded_range)

	def toScene(self, angle: float, radius: float) -> QPointF:
		a = math.radians(angle)
		return self.arc.mapToScene(QPointF(radius * math.sin(a), -radius * math.cos(a)))

	def pivot(self) -> QPointF:
		return self.arc.mapToScene(QPointF(0, 0))

	def polar(self, scene: QPointF):
		"""(angle in degrees, distance from the pivot) of a scene point."""
		p = self.arc.mapFromScene(scene)
		return math.degrees(math.atan2(p.x(), -p.y())), math.hypot(p.x(), p.y())

	def angleNear(self, angle: float, near: float) -> float:
		"""`angle` plus a whole number of turns, whichever lands closest to `near`."""
		return angle + 360 * round((near - angle) / 360)

	def valueAngle(self, value: float) -> float:
		frac = (value - self.lo) / self.span if self.span else 0.0
		return self.a0 + frac * (self.a1 - self.a0)

	def angleValue(self, angle: float) -> float:
		lo, hi = sorted((self.a0, self.a1))
		angle = min(max(self.angleNear(angle, (lo + hi) / 2), lo), hi)
		frac = (angle - self.a0) / (self.a1 - self.a0) if self.a1 != self.a0 else 0.0
		return self.lo + frac * self.span

	def step(self) -> float:
		return niceStep(self.span / 50)


# Section: the items

class Overlay(QGraphicsItem):
	"""Holds every handle. Hide it and the scene renders without them."""

	def __init__(self):
		super().__init__()
		self.setZValue(Z)
		self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemHasNoContents)

	def boundingRect(self) -> QRectF:
		return QRectF()

	def paint(self, *args):
		pass


@dataclass
class Spec:
	"""One handle: where it sits and what dragging or clicking it does."""
	kind: str
	tip: str
	position: Callable[[], Optional[QPointF]]
	begin: Callable[[], Any] = lambda: None
	drag: Optional[Callable[[Any, QPointF, bool], None]] = None
	click: Optional[Callable[[], None]] = None
	rect: Optional[Callable[[], Optional[QRectF]]] = None
	shape: str = 'dot'
	active: Callable[[], bool] = lambda: False
	#: A gradient node: its colour, the text it shows while dragged, whether a drop now would remove it.
	fill: Optional[Callable[[], str]] = None
	label: Optional[Callable[[], str]] = None
	removing: Callable[[], bool] = lambda: False
	#: Runs when the drag ends (the mouse comes up), before the edit is recorded.
	finish: Optional[Callable[[Any], None]] = None
	double: Optional[Callable[[], None]] = None
	remove: Optional[Callable[[], None]] = None
	tag: Any = None
	#: A track hit area, in scene coordinates.
	path: Optional[Callable[[], Optional[Any]]] = None
	#: Takes the scene point of the press and returns the drag state, in place of `begin`.
	press: Optional[Callable[[QPointF], Any]] = None


class _Handle(QGraphicsItem):
	def __init__(self, layer: 'HandleLayer', spec: Spec):
		super().__init__(layer.overlay)
		self.layer = layer
		self.hover = False
		self.setAcceptHoverEvents(True)
		self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
		self.assign(spec)

	def assign(self, spec: Spec):
		"""Handles are reused, never deleted: Qt may still be painting one when the gauge is rebuilt."""
		self.spec = spec
		self.setToolTip(spec.tip)
		self.setCursor(Qt.CursorShape.OpenHandCursor if spec.drag else Qt.CursorShape.PointingHandCursor)
		self.color = QColor(COLORS.get(spec.kind, '#ffffff'))
		node = spec.kind in ('gradient', 'track')
		dim = self.layer.gradientMode and not node
		# While gradients are edited the other handles stay visible but hold no mouse, so a drag on a node never grabs one.
		self.setOpacity(0.25 if dim else 1.0)
		self.setAcceptedMouseButtons(Qt.MouseButton.NoButton if dim else Qt.MouseButton.LeftButton)
		self.setAcceptHoverEvents(not dim)
		self.setZValue(2 if spec.kind == 'gradient' else (1 if spec.kind == 'track' else 0))
		self.update()

	def hoverEnterEvent(self, event):
		self.hover = True
		self.update()

	def hoverLeaveEvent(self, event):
		self.hover = False
		self.update()

	def mousePressEvent(self, event):
		self.layer.begin(self, event.scenePos())
		event.accept()

	def mouseMoveEvent(self, event):
		self.layer.move(self, event.scenePos(), bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))

	def mouseReleaseEvent(self, event):
		self.layer.end(self)
		event.accept()

	def mouseDoubleClickEvent(self, event):
		self.layer.doubleClick(self)
		event.accept()

	def reposition(self):
		spec = self.spec
		p = spec.position()
		if p is None:
			self.setVisible(False)
			return
		self.setVisible(self.layer.visibleFor(spec))
		self.setPos(p)


class Dot(_Handle):
	"""A round (or, for `shape='square'`, square) handle that keeps its size on screen however the view is scaled."""

	R = 6

	def __init__(self, layer, spec):
		super().__init__(layer, spec)
		self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)

	def boundingRect(self) -> QRectF:
		# Room above the dot for the value a gradient node shows while it is dragged.
		return QRectF(-110, -48, 220, 72) if self.spec.kind == 'gradient' else QRectF(-12, -12, 24, 24)

	def shape(self):
		path = QPainterPath()
		path.addEllipse(QPointF(0, 0), 12, 12)
		return path

	def _paintNode(self, painter: QPainter, hot: bool):
		spec = self.spec
		r = 7 + (3 if hot else 0)
		fade = spec.removing() and self.layer.active is self
		painter.setOpacity(self.opacity() * (0.4 if fade else 1.0))
		painter.setPen(QPen(QColor(0, 0, 0, 220), 4))
		painter.setBrush(Qt.BrushStyle.NoBrush)
		painter.drawEllipse(QPointF(0, 0), r, r)
		painter.setPen(QPen(QColor(255, 255, 255), 2))
		painter.setBrush(QBrush(QColor(spec.fill() if spec.fill else '#ffffff')))
		painter.drawEllipse(QPointF(0, 0), r, r)
		painter.setOpacity(self.opacity())
		if self.layer.active is self and spec.label is not None:
			text = 'release to remove' if spec.removing() else spec.label()
			font = painter.font()
			font.setPointSizeF(10)
			painter.setFont(font)
			w = painter.fontMetrics().horizontalAdvance(text) + 16
			box = QRectF(-w / 2, -40, w, 22)
			painter.setPen(QPen(QColor(255, 255, 255), 1))
			painter.setBrush(QBrush(QColor('#0d1117')))
			painter.drawRoundedRect(box, 5, 5)
			painter.setPen(QColor('#f0f6fc'))
			painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

	def paint(self, painter: QPainter, option, widget=None):
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		hot = self.hover or self.layer.active is self
		if self.spec.kind == 'gradient':
			self._paintNode(painter, hot)
			return
		r = self.R + (2 if hot else 0)
		color = QColor(self.color)
		color.setAlpha(255 if hot else 190)
		painter.setPen(QPen(QColor(0, 0, 0, 200), 2))
		on = self.spec.active()
		painter.setBrush(QBrush(color if (on or self.spec.shape != 'square') else QColor(color.red(), color.green(), color.blue(), 70)))
		if self.spec.shape == 'square':
			painter.drawRect(QRectF(-r, -r, r * 2, r * 2))
		elif self.spec.shape == 'diamond':
			painter.save()
			painter.rotate(45)
			painter.drawRect(QRectF(-r * 0.8, -r * 0.8, r * 1.6, r * 1.6))
			painter.restore()
		else:
			painter.drawEllipse(QPointF(0, 0), r, r)


class Box(_Handle):
	"""A rectangle around some text. Dragging it moves the text."""

	_rect = QRectF()

	def boundingRect(self) -> QRectF:
		return self._rect.adjusted(-3, -3, 3, 3)

	def reposition(self):
		rect = self.spec.rect()
		if rect is None or rect.isEmpty():
			self.setVisible(False)
			return
		rect = rect.adjusted(-6, -4, 6, 4)
		if rect != self._rect:
			self.prepareGeometryChange()
			self._rect = rect
		self.setVisible(self.layer.visibleFor(self.spec))
		self.update()

	def shape(self):
		from PySide6.QtGui import QPainterPath
		path = QPainterPath()
		path.addRect(self._rect)
		return path

	def paint(self, painter: QPainter, option, widget=None):
		hot = self.hover or self.layer.active is self
		color = QColor(self.color)
		color.setAlpha(230 if hot else 90)
		pen = QPen(color, 2 if hot else 1, Qt.PenStyle.SolidLine if hot else Qt.PenStyle.DashLine)
		pen.setCosmetic(True)
		painter.setPen(pen)
		fill = QColor(self.color)
		fill.setAlpha(40 if hot else 0)
		painter.setBrush(QBrush(fill))
		painter.drawRoundedRect(self._rect, 4, 4)


class TrackHit(_Handle):
	"""The arc's track, while gradients are edited. A press on it adds a stop there; drag to place it."""

	_path = None

	def boundingRect(self) -> QRectF:
		return self._path.boundingRect() if self._path is not None else QRectF()

	def shape(self):
		return self._path if self._path is not None else QPainterPath()

	def reposition(self):
		path = self.spec.path()
		if path is None:
			self.setVisible(False)
			return
		if self._path is None or path != self._path:
			self.prepareGeometryChange()
			self._path = path
		self.setPos(0, 0)
		self.setVisible(self.layer.visibleFor(self.spec))
		self.update()

	def paint(self, painter: QPainter, option, widget=None):
		if self._path is None:
			return
		hot = self.hover or self.layer.active is self
		color = QColor(255, 255, 255, 120 if hot else 50)
		pen = QPen(color, 1.5, Qt.PenStyle.DashLine)
		pen.setCosmetic(True)
		painter.setPen(pen)
		painter.setBrush(Qt.BrushStyle.NoBrush)
		painter.drawPath(self._path)


# Section: the layer

class HandleLayer:
	"""Builds the handles for the open gauge and turns drags into edits on the studio window."""

	def __init__(self, studio):
		self.studio = studio
		self.scene = studio.scene
		self.overlay = Overlay()
		self.scene.addItem(self.overlay)
		self.scene.overlay = self.overlay
		self.items: List[_Handle] = []
		self.pool: List[_Handle] = []
		self.enabled = True
		self.inside = False
		self.force = False
		self.snap = True
		#: *Edit gradient*: one node per stop of the arc's gradient, and the other handles dimmed.
		self.gradientMode = False
		self.selectedStop: Optional[int] = None
		self.active: Optional[_Handle] = None
		self._state: Any = None
		self._moved = False
		self._signature: tuple = ()
		self._later = QTimer(singleShot=True, interval=0, timeout=self.rebuildNow)

	# state

	@property
	def shown(self) -> bool:
		return self.enabled and (self.inside or self.force or self.active is not None)

	@property
	def gauge(self):
		return self.studio.studio.gauge

	def visibleFor(self, spec: Spec) -> bool:
		"""Gradient nodes stay up for as long as *Edit gradient* is on; the rest show while the pointer is over the preview."""
		if spec.kind in ('gradient', 'track'):
			return self.gradientMode
		return self.shown

	def setGradientMode(self, on: bool):
		self.gradientMode = on
		self.selectedStop = None
		self.rebuildNow()

	def setInside(self, inside: bool):
		self.inside = inside
		self.refresh()

	def setEnabled(self, on: bool):
		self.enabled = on
		self.refresh()

	# building

	def clear(self):
		for item in self.items:
			item.setVisible(False)
			item.hover = False
		self.items = []
		self.active = None

	def rebuild(self):
		"""Make the handles again from the gauge as it is now. It waits for the event loop: a handle
		must not be deleted while its own mouse event is still being handled."""
		self._later.start()

	def rebuildNow(self):
		self.clear()
		if self.gauge is None:
			return
		try:
			specs = self._specs()
		except Exception:  # noqa: BLE001 - a handle must never take the studio down
			import traceback
			traceback.print_exc()
			specs = []
		for spec in specs:
			kind = TrackHit if spec.path is not None else (Box if spec.rect is not None else Dot)
			item = next((i for i in self.pool if type(i) is kind and i not in self.items), None)
			if item is None:
				item = kind(self, spec)
				self.pool.append(item)
			else:
				item.assign(spec)
			self.items.append(item)
		self._signature = self._sig()
		self.reposition()

	def _sig(self) -> tuple:
		g = self.gauge
		return (id(g), len(g._markerSpecs), len(g._zoneSpecs), bool(g._fillSpec), bool(g._captionItem), bool(g._subItem),
		        g._anchor, bool(g.unitLabel.textBox.isVisibleTo(g)), self.gradientMode, len(self._stops()) if self.gradientMode else 0)

	def refresh(self):
		"""Move the handles to where the gauge has them now; make them again if the gauge changed shape."""
		if self.gauge is None:
			return
		if self.active is None and self._sig() != self._signature:
			self.rebuild()
			return
		self.reposition()

	def reposition(self):
		for item in self.items:
			try:
				item.reposition()
			except Exception:  # noqa: BLE001 - the gauge may be mid-rebuild
				item.setVisible(False)

	# the drag

	def begin(self, item: _Handle, pos: QPointF):
		self.active = item
		self._moved = False
		self._state = item.spec.press(pos) if item.spec.press is not None else item.spec.begin()
		self._start = pos
		if item.spec.kind == 'gradient':
			self.selectedStop = item.spec.tag
		self.studio.beginDrag()
		item.setCursor(Qt.CursorShape.ClosedHandCursor)

	def move(self, item: _Handle, pos: QPointF, shift: bool):
		spec = item.spec
		if spec.drag is None:
			return
		if not self._moved and (pos - self._start).manhattanLength() < 3:
			return
		self._moved = True
		fine = shift or not self.snap
		spec.drag(self._state, pos, fine)

	def end(self, item: _Handle):
		spec = item.spec
		self.active = None
		item.setCursor(Qt.CursorShape.OpenHandCursor if spec.drag else Qt.CursorShape.PointingHandCursor)
		if spec.click is not None and not self._moved:
			spec.click()
		moved = self._moved
		if spec.finish is not None and (moved or spec.kind == 'track'):
			spec.finish(self._state)
			moved = True
		self.studio.endDrag(moved or spec.click is not None)
		self.rebuild()

	def doubleClick(self, item: _Handle):
		"""A double click on a node picks its colour. The dialog waits for the event to finish: it runs its own loop."""
		spec = item.spec
		if spec.double is not None:
			QTimer.singleShot(0, spec.double)

	def deleteSelected(self) -> bool:
		"""Delete the chosen gradient node. True when there was one."""
		if not self.gradientMode or self.selectedStop is None:
			return False
		for item in self.items:
			spec = item.spec
			if spec.kind == 'gradient' and spec.tag == self.selectedStop and spec.remove is not None:
				self.selectedStop = None
				spec.remove()
				return True
		return False

	# the specs

	def _stops(self) -> List['stops.Stop']:
		"""The stops of the arc's gradient, in the order the file holds them."""
		if self.gauge is None:
			return []
		try:
			return stops.decode(schema.read(self.gauge, GRADIENT))
		except Exception:  # noqa: BLE001 - a gauge mid-rebuild has nothing to read
			return []

	def _gradientSpecs(self, dial: Callable[[], Dial]) -> List[Spec]:
		"""One node per stop on the track, and the track itself to click for a new stop.

		An edit writes the whole gradient (`arc.gradient`) through the studio, so a drag is one edit like any other
		handle's. While a node is held the stops keep the order they had, so the node under the mouse stays the same
		stop; the drag's end writes them in order of value.
		"""
		studio = self.studio
		out: List[Spec] = []

		def vc():
			return self.gauge.valueClass

		def span():
			dl = dial()
			return dl.lo, dl.lo + dl.span

		def write(items: List['stops.Stop'], ordered: bool = False):
			if ordered:
				items = sorted(items, key=lambda s: v if (v := stops.native(s, vc())) is not None else float('inf'))
			studio.handleEdit(GRADIENT, stops.encode(items))

		def once(items: List['stops.Stop']):
			"""A change that is a whole gesture of its own (a colour, a delete): one undo step."""
			studio.beginDrag()
			write(items, ordered=True)
			studio.endDrag(True)

		def centre() -> float:
			dl = dial()
			return max(dl.R - dl.weight / 2, 0)

		def threshold() -> float:
			return dial().weight / 2 + 30

		def colourAt(value: float, items: List['stops.Stop']) -> str:
			pts = [(n, s.color) for s in items if (n := stops.native(s, vc())) is not None]
			return stops.sample(pts, value) if pts else stops.freshColor([])

		for i in range(len(self._stops())):
			held = {'off': False, 'stop': None}

			def pos(i=i):
				items = self._stops()
				if i >= len(items):
					return None
				value = stops.native(items[i], vc())
				if value is None:
					return None
				dl = dial()
				# Placed through the dial's value-to-angle mapping. Once refactor/meter lands, place nodes through
				# Scale and Track instead (docs/tasks/meter-and-bar.md), so a bar gets gradient nodes for free.
				return dl.toScene(dl.valueAngle(value), centre())

			def begin(i=i, held=held):
				held['off'], held['stop'] = False, None
				return {'index': i, 'stops': self._stops()}

			def drag(state, p, fine, held=held):
				dl = dial()
				angle, radius = dl.polar(p)
				held['off'] = abs(radius - centre()) > threshold()
				if held['off']:
					return
				items = [s.copy() for s in state['stops']]
				lo, hi = span()
				items[state['index']] = stops.place(items[state['index']], dl.angleValue(angle), vc(), lo, hi, fine)
				held['stop'] = items[state['index']]
				state['stops'] = items
				write(items)

			def finish(state, held=held):
				items = state['stops']
				if held['off']:
					items = [s for k, s in enumerate(items) if k != state['index']]
				held['off'] = False
				write(items, ordered=True)

			def fill(i=i):
				items = self._stops()
				return items[i].color if i < len(items) else '#ffffff'

			def label(i=i, held=held):
				items = self._stops()
				stop = held['stop'] or (items[i] if i < len(items) else None)
				return studio.stopLabel(stop) if stop is not None else ''

			def recolor(i=i):
				items = self._stops()
				if i >= len(items):
					return
				chosen = studio.pickColor(items[i].color)
				if chosen is not None:
					items[i].color = chosen
					once(items)

			def remove(i=i):
				items = self._stops()
				if i < len(items):
					del items[i]
					once(items)

			out.append(Spec('gradient', 'Drag along the track to move this stop (shift: fine). Drag off the track or press Delete to remove it. Double click for its colour.',
			                pos, begin=begin, drag=drag, finish=finish, fill=fill, label=label, removing=lambda held=held: held['off'],
			                double=recolor, remove=remove, tag=i))

		def trackPath():
			arc = self.gauge.arc
			return arc.mapToScene(arc.shape())

		def press(p):
			items = self._stops()
			dl = dial()
			value = dl.angleValue(dl.polar(p)[0])
			lo, hi = span()
			colour = colourAt(value, items)
			unit = None
			ordered = sorted(items, key=lambda s: v if (v := stops.native(s, vc())) is not None else float('inf'))
			if ordered:
				unit = ordered[-1].unit
			new = stops.place(stops.Stop(0.0, unit, colour), value, vc(), lo, hi)
			items.append(new)
			write(items)
			return {'index': len(items) - 1, 'stops': items}

		def tdrag(state, p, fine):
			dl = dial()
			items = [s.copy() for s in state['stops']]
			lo, hi = span()
			items[state['index']] = stops.place(items[state['index']], dl.angleValue(dl.polar(p)[0]), vc(), lo, hi, fine)
			state['stops'] = items
			write(items)

		out.append(Spec('track', 'Click the track to add a stop with the colour there; drag to place it', lambda: None, drag=tdrag,
		                finish=lambda state: write(state['stops'], ordered=True), path=trackPath, press=press))
		return out

	def _specs(self) -> List[Spec]:
		g = self.gauge
		d = Dial(g)
		studio = self.studio
		out: List[Spec] = []

		def dial() -> Dial:
			return Dial(self.gauge)

		# arc ends
		for end, key in ((0, 'start-angle'), (1, 'end-angle')):
			def pos(end=end):
				dl = dial()
				return dl.toScene(dl.a1 if end else dl.a0, dl.R)

			def drag(state, p, fine, end=end, key=key):
				dl = dial()
				angle = dl.angleNear(dl.polar(p)[0], dl.a1 if end else dl.a0)
				angle = round(angle, 1) if fine else snapTo(angle, 5)
				studio.handleEdit(('arc', key), int(angle) if float(angle).is_integer() else angle)
			out.append(Spec('angle', 'Drag to set the arc\'s ' + ('end' if end else 'start') + ' angle (shift: fine)', pos, drag=drag))

		# radius, on the track at the arc's middle
		def radiusPos():
			dl = dial()
			return dl.toScene((dl.a0 + dl.a1) / 2, dl.R)

		def radiusDrag(state, p, fine):
			dl = dial()
			ratio = dl.polar(p)[1] / max(dl.gauge.radius_max, 1) * 100
			ratio = round(ratio, 1) if fine else snapTo(ratio, 5)
			studio.handleEdit(('radius',), f'{max(ratio, 5):g}%')
		out.append(Spec('radius', 'Drag to set the radius (shift: fine)', radiusPos, drag=radiusDrag))

		# arc weight, on the track's inner edge, a quarter of the way along
		def weightPos():
			dl = dial()
			return dl.toScene(dl.a0 + (dl.a1 - dl.a0) * 0.3, max(dl.R - dl.weight / 2, 0))

		def weightDrag(state, p, fine):
			dl = dial()
			w = max(2 * (dl.R - dl.polar(p)[1]), 0)
			pct = w / max(dl.R, 1) * 100
			pct = round(pct, 1) if fine else snapTo(pct, 0.5)
			studio.handleEdit(('arc', 'weight'), f'{max(pct, 0.5):g}%')
		out.append(Spec('weight', 'Drag to set the arc weight (shift: fine)', weightPos, drag=weightDrag))

		# the needle tip sets the preview value
		def needlePos():
			dl = dial()
			value = float(studio.studio.gauge.value)
			return dl.toScene(dl.valueAngle(value), dl.R * 0.72)

		def needleDrag(state, p, fine):
			dl = dial()
			v = dl.angleValue(dl.polar(p)[0])
			v = round(v, 3) if fine else snapTo(v, dl.step() / 5)
			studio.setValueFromDrag(v)
		out.append(Spec('needle', 'Drag to set the preview value', needlePos, drag=needleDrag, shape='diamond'))

		# markers
		for i, spec in enumerate(copy.deepcopy(g._markerSpecs)):
			v = spec.get('value')
			if spec.get('time') is not None or isinstance(v, bool) or not isinstance(v, (int, float)):
				continue

			def mpos(i=i):
				specs = self.gauge._markerSpecs
				if i >= len(specs) or not isinstance(specs[i].get('value'), (int, float)):
					return None
				dl = dial()
				return dl.toScene(dl.valueAngle(float(specs[i]['value'])), dl.R)

			def mdrag(state, p, fine, i=i):
				dl = dial()
				v = dl.angleValue(dl.polar(p)[0])
				v = round(v, 3) if fine else snapTo(v, dl.step())
				specs = copy.deepcopy(self.gauge._markerSpecs)
				specs[i]['value'] = int(v) if float(v).is_integer() else v
				studio.handleEdit(('markers',), specs)
			out.append(Spec('marker', f'Drag marker {i + 1} along the arc', mpos, drag=mdrag))

		# zone edges; a cutoff two zones share moves both
		seen = set()
		for i, zone in enumerate(copy.deepcopy(g._zoneSpecs)):
			for end in ('from', 'to'):
				v = zone.get(end)
				if isinstance(v, bool) or not isinstance(v, (int, float)):
					continue
				if round(float(v), 6) in seen:
					continue
				seen.add(round(float(v), 6))

				def zpos(i=i, end=end):
					specs = self.gauge._zoneSpecs
					if i >= len(specs) or not isinstance(specs[i].get(end), (int, float)):
						return None
					dl = dial()
					return dl.toScene(dl.valueAngle(float(specs[i][end])), dl.R + dl.weight / 2 + 9)

				def zbegin(i=i, end=end):
					return float(self.gauge._zoneSpecs[i][end])

				def zdrag(state, p, fine):
					dl = dial()
					v = dl.angleValue(dl.polar(p)[0])
					v = round(v, 3) if fine else snapTo(v, dl.step())
					v = int(v) if float(v).is_integer() else v
					specs = copy.deepcopy(self.gauge._zoneSpecs)
					for spec in specs:
						for e in ('from', 'to'):
							if isinstance(spec.get(e), (int, float)) and not isinstance(spec.get(e), bool) and math.isclose(float(spec[e]), state, abs_tol=1e-9):
								spec[e] = v
					state_after = float(v)
					self._state = state_after
					studio.handleEdit(('zones',), specs)
				out.append(Spec('zone', f'Drag zone {i + 1}\'s {end} edge (a shared cutoff moves both zones)', zpos, begin=zbegin, drag=zdrag, shape='square'))

		# fill ends
		fill = g._fillSpec
		for end in ('from', 'to'):
			if not fill or isinstance(fill.get(end), bool) or not isinstance(fill.get(end), (int, float)):
				continue

			def fpos(end=end):
				spec = self.gauge._fillSpec
				if not spec or not isinstance(spec.get(end), (int, float)):
					return None
				dl = dial()
				return dl.toScene(dl.valueAngle(float(spec[end])), max(dl.R - dl.weight / 2 - 9, 0))

			def fdrag(state, p, fine, end=end):
				dl = dial()
				v = dl.angleValue(dl.polar(p)[0])
				v = round(v, 3) if fine else snapTo(v, dl.step())
				spec = copy.deepcopy(self.gauge._fillSpec)
				spec[end] = int(v) if float(v).is_integer() else v
				studio.handleEdit(('fill',), spec)
			out.append(Spec('fill', f'Drag the fill\'s {end} end', fpos, drag=fdrag))

		# labels: drag the text
		def labelSpec(name: str, path: tuple, rect: Callable[[], Optional[QRectF]], read: Callable[[], dict], write: Callable[[dict], None]):
			def begin():
				return {'o': read(), 'p0': None}

			def drag(state, p, fine):
				gauge = self.gauge
				if state['p0'] is None:
					state['p0'] = p
					state['g0'] = gauge.mapFromScene(p)
				delta = gauge.mapFromScene(p) - state['g0']
				diameter = max(gauge.radius * 2, 1)
				step = 0.001 if fine else 0.005
				x = snapTo(state['o']['x'] + delta.x() / diameter, step)
				y = snapTo(state['o']['y'] + delta.y() / diameter, step)
				write({'x': round(x, 4), 'y': round(y, 4)})
			return Spec('label', f'Drag the {name} (shift: fine)', lambda: None, begin=begin, drag=drag, rect=rect)

		def offsetOf(label) -> dict:
			v = getattr(label, '_offset', None) or (0.0, 0.0)
			return {'x': v[0], 'y': v[1]}

		def sceneBox(box) -> Optional[QRectF]:
			try:
				if not box.isVisibleTo(self.gauge):
					return None
				return box.scenePath().boundingRect()
			except Exception:  # noqa: BLE001
				return None

		out.append(labelSpec('value', ('value-label', 'offset'), lambda: sceneBox(self.gauge.valueLabel.textBox),
		                     lambda: offsetOf(self.gauge.valueLabel), lambda o: studio.handleEdit(('value-label', 'offset'), o)))
		out.append(labelSpec('unit', ('unit-label', 'offset'), lambda: sceneBox(self.gauge.unitLabel.textBox),
		                     lambda: offsetOf(self.gauge.unitLabel), lambda o: studio.handleEdit(('unit-label', 'offset'), o)))
		for attr, key, name in (('_captionItem', 'caption', 'caption'), ('_subItem', 'sub-label', 'sub-label')):
			if getattr(g, attr) is None:
				continue

			def crect(attr=attr):
				item = getattr(self.gauge, attr)
				if item is None or not item.isVisible():
					return None
				return item.sceneBoundingRect()

			def cread(attr=attr):
				item = getattr(self.gauge, attr)
				return {'x': (item._offset or (0.0, 0.0))[0], 'y': (item._offset or (0.0, 0.0))[1]}

			def cwrite(o, key=key):
				spec = copy.deepcopy(self.gauge._captionSpec if key == 'caption' else self.gauge._subSpec)
				if isinstance(spec, str):
					spec = {'text': spec}
				spec['offset'] = o
				studio.handleEdit((key,), spec)
			out.append(labelSpec(name, (key,), crect, cread, cwrite))

		# corners: click to anchor the pivot
		for name in ('top-left', 'top-right', 'bottom-left', 'bottom-right'):
			def cpos(name=name):
				rect = self.scene.sceneRect().adjusted(20, 20, -20, -20)
				return {'top-left': rect.topLeft(), 'top-right': rect.topRight(), 'bottom-left': rect.bottomLeft(), 'bottom-right': rect.bottomRight()}[name]

			def cclick(name=name):
				now = self.gauge._anchor
				studio.handleEdit(('anchor',), None if now == name else name)

			out.append(Spec('corner', f'Click to pin the dial\'s centre to the {name} corner (again to unpin)', cpos, click=cclick, shape='square',
			                active=lambda name=name: self.gauge._anchor == name))
		if self.gradientMode:
			out += self._gradientSpecs(dial)
		return out
