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
cursor. While *Snap* is on a value snaps to a round step; hold Cmd (Ctrl elsewhere) to
move freely. Hold Option (Alt) to gear the drag down: the handle moves the mouse's
distance divided by the gear ratio (4:1 to start), anchored where the key went down so
nothing jumps. Scroll with Option held to change the ratio; a badge near the cursor
shows it and fades. A drag within `SNAP_PX` of a design target (a fraction, a ratio such as 1/φ, an angle
multiple or the golden angle; see `_studio_targets`) lands on it, and hairline guides (`_studio_guides`) measure
the drag, pink and named for the target it hit. The overlay is one item (`Overlay`) so a screenshot can hide every
handle at once.
"""
import copy
import math
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem

from LevityDash.devtools import _studio_schema as schema
from LevityDash.devtools import _studio_stops as stops
from LevityDash.devtools import _studio_targets as targets
from LevityDash.devtools._studio_guides import Guides, Line, Tag
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

	def sweep(self, a0: float, a1: float, radius: float) -> List[QPointF]:
		"""Scene points along the circle of `radius` from angle `a0` to `a1`."""
		n = max(2, int(abs(a1 - a0) / 3) + 1)
		return [self.toScene(a0 + (a1 - a0) * i / (n - 1), radius) for i in range(n)]

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

	def degPx(self) -> float:
		"""Screen pixels one degree of the track covers."""
		return self.R * math.pi / 180

	def spanPx(self) -> float:
		"""Screen pixels the whole range covers along the track."""
		return self.degPx() * abs(self.a1 - self.a0)


# Section: the items

#: Cmd on a Mac is Qt's Control and Ctrl is Meta; holding either turns snapping off.
FREE = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
GEAR_STEPS = (1, 2, 3, 4, 6, 8, 10, 15, 20)
GEAR_DEFAULT = 4
#: How close, in screen pixels, a drag has to be to a design target to land on it.
SNAP_PX = 7
#: What a handle's tip says about the modifiers.
KEYS = 'Cmd: no snap, Option: fine control'


class Gearing:
	"""A drag's map from the mouse to the point the handle sees.

	While gearing is off the handle follows the mouse one to one. While it is on the handle moves the mouse's distance
	divided by `ratio`. Every change (the key going down or up, the ratio changing) anchors the map where the mouse
	last was, so the handle never jumps.
	"""

	def __init__(self, ratio: int = GEAR_DEFAULT):
		self.ratio = ratio
		self.begin(QPointF())

	def begin(self, pos: QPointF):
		self.raw = self.eff = self.last = QPointF(pos)
		self.geared = False

	def _map(self, raw: QPointF) -> QPointF:
		return self.eff + (raw - self.raw) / (self.ratio if self.geared else 1.0)

	def _anchor(self):
		self.eff, self.raw = self._map(self.last), QPointF(self.last)

	def point(self, raw: QPointF, geared: bool) -> QPointF:
		"""Where the handle goes for the mouse at `raw`, with the gear key held or not."""
		if geared != self.geared:
			self._anchor()
			self.geared = geared
		self.last = QPointF(raw)
		return self._map(raw)

	def step(self, direction: int) -> int:
		"""Move the ratio one step up (`direction` > 0) or down along `GEAR_STEPS`; returns the new ratio."""
		self._anchor()
		i = GEAR_STEPS.index(self.ratio) if self.ratio in GEAR_STEPS else GEAR_STEPS.index(GEAR_DEFAULT)
		self.ratio = GEAR_STEPS[max(0, min(len(GEAR_STEPS) - 1, i + (1 if direction > 0 else -1)))]
		return self.ratio


class Badge(QGraphicsItem):
	"""A short line of text near the cursor that fades about a second after it was last set."""

	LIFE = 1000

	def __init__(self, parent: QGraphicsItem):
		super().__init__(parent)
		self.text = ''
		self.setZValue(Z + 5)
		self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
		self.setVisible(False)
		self._timer = QTimer(singleShot=True, interval=self.LIFE, timeout=self._fade)
		self._fading = QTimer(interval=40, timeout=self._step)

	def boundingRect(self) -> QRectF:
		return QRectF(0, 0, 150, 30)

	def say(self, text: str, pos: QPointF, hold: bool = False):
		"""Show `text` at `pos`. With `hold` it stays until the next `say` or `hide`; otherwise it fades after `LIFE` ms."""
		self._fading.stop()
		self.text = text
		self.setPos(pos + QPointF(16, 16))
		self.setOpacity(1.0)
		self.setVisible(True)
		self.update()
		self._timer.stop()
		if not hold:
			self._timer.start()

	def hide(self):
		self._timer.stop()
		self._fading.stop()
		self.setVisible(False)

	def _fade(self):
		self._fading.start()

	def _step(self):
		self.setOpacity(self.opacity() - 0.1)
		if self.opacity() <= 0.05:
			self._fading.stop()
			self.setVisible(False)

	def paint(self, painter: QPainter, *args):
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		painter.setBrush(QColor(20, 24, 30, 230))
		painter.setPen(QPen(QColor('#f5a524'), 1))
		painter.drawRoundedRect(self.boundingRect().adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
		painter.setPen(QColor('#f0f6fc'))
		font = QFont()
		font.setPixelSize(15)
		font.setBold(True)
		painter.setFont(font)
		painter.drawText(self.boundingRect(), Qt.AlignmentFlag.AlignCenter, self.text)


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
		# After a double click the item still holds the mouse (a colour dialog eats the release), but no press began a drag.
		if self.layer.active is not self:
			return
		self.layer.move(self, event.scenePos(), event.modifiers())

	def mouseReleaseEvent(self, event):
		if self.layer.active is self:
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
		self.gear = Gearing()
		self._wasGeared = False
		self.badge = Badge(self.overlay)
		self.scene.overlay = self.overlay
		self.items: List[_Handle] = []
		self.pool: List[_Handle] = []
		self.enabled = True
		self.inside = False
		self.force = False
		self.snap = True
		#: Hairline distance guides while a handle is dragged, and which target families snapping reaches.
		self.guideOn = True
		self.familyOn = {f: True for f in targets.FAMILIES}
		#: The target each value of the drag in progress landed on, by name of the value (`v`, `x`, `y`).
		self.hits: dict = {}
		self.guides = Guides(self.overlay, -1)
		self.guides.setVisible(False)
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
		self._state = None
		self._state = item.spec.press(pos) if item.spec.press is not None else item.spec.begin()
		self._start = pos
		self.gear.begin(pos)
		self._wasGeared = False
		self.hits = {}
		self.guides.clear()
		if item.spec.kind == 'gradient':
			self.selectedStop = item.spec.tag
		self.studio.beginDrag()
		item.setCursor(Qt.CursorShape.ClosedHandCursor)

	def move(self, item: _Handle, pos: QPointF, modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier):
		spec = item.spec
		if spec.drag is None:
			return
		if not self._moved and (pos - self._start).manhattanLength() < 3:
			return
		self._moved = True
		geared = bool(modifiers & Qt.KeyboardModifier.AltModifier)
		fine = bool(modifiers & FREE) or not self.snap
		point = self.gear.point(pos, geared)
		if geared:
			self.badge.say(f'Gear {self.gear.ratio}:1', pos, hold=True)
		elif self._wasGeared:
			self.badge.say(f'Gear {self.gear.ratio}:1', pos)  # the key came up: let the badge fade
		self._wasGeared = geared
		self.hits = {}
		spec.drag(self._state, point, fine)
		if spec.kind in ('gradient', 'track'):
			self.reposition()

	# snapping to design targets, and the guides that show it

	def pick(self, value: float, step: float, fine: bool, kind: str, unitPx: float, origin: float = 0.0, scale: float = 1.0,
	         name: str = 'v', digits: int = 3) -> float:
		"""`value` snapped: to a design target within `SNAP_PX` of it, else to `step`; unsnapped (rounded to `digits`) when `fine`.

		`kind` is `'fraction'`, `'offset'` or `'angle'` (see `_studio_targets`). A share is `(value - origin) / scale`;
		`unitPx` is the screen pixels one unit of that share (one degree for an angle) covers. The target hit, if any, is
		kept in `hits[name]` for the guides.
		"""
		self.hits.pop(name, None)
		if fine:
			return round(value, digits)
		out = snapTo(value, step)
		x = value if kind == 'angle' else (value - origin) / scale
		target = targets.near(kind, x, SNAP_PX / max(unitPx, 1e-9), [f for f, on in self.familyOn.items() if on])
		if target is not None:
			self.hits[name] = (target, kind)
			out = target.value if kind == 'angle' else origin + target.value * scale
		return out

	def _tag(self, default: str, at: QPointF, name: str = 'v') -> Tag:
		hit = self.hits.get(name)
		return Tag(targets.describe(*hit) if hit else default, at, hot=hit is not None)

	def showGuides(self, lines: List[Line], tags: List[Tag]):
		if self.guideOn:
			self.guides.show(lines, tags, self.scene.sceneRect())

	def angleGuides(self, dl: Dial, angle: float):
		hot = 'v' in self.hits
		r = dl.R * 0.45
		lines = [Line([dl.pivot(), dl.toScene(0, dl.R * 1.15)], dashed=True),
		         Line([dl.pivot(), dl.toScene(angle, dl.R * 1.15)], hot=hot),
		         Line(dl.sweep(0, angle, r), hot=hot)]
		tags = [self._tag(f'{angle:g}°', dl.toScene(angle / 2, r))]
		if dl.a0 != dl.a1:
			lines.append(Line(dl.sweep(dl.a0, dl.a1, dl.R * 0.3)))
			tags.append(Tag(f'sweep {abs(dl.a1 - dl.a0):g}°', dl.toScene((dl.a0 + dl.a1) / 2, dl.R * 0.3)))
		self.showGuides(lines, tags)

	def shareGuides(self, dl: Dial, angle: float, radius: float, text: str, circle: bool = False):
		"""A ray from the pivot to `radius` at `angle`; hot with a circle through its end when the drag snapped."""
		hot = 'v' in self.hits
		lines = [Line([dl.pivot(), dl.toScene(angle, radius)], hot=hot)]
		if circle:
			lines.append(Line(dl.sweep(0, 360, radius), hot=hot))
		self.showGuides(lines, [self._tag(text, dl.toScene(angle, radius))])

	def valueGuides(self, dl: Dial, value: float):
		"""The arc from the dial's start to `value`, and a ray to its end."""
		angle = dl.valueAngle(value)
		hot = 'v' in self.hits
		share = (value - dl.lo) / dl.span if dl.span else 0.0
		r = dl.R * 0.55
		lines = [Line([dl.pivot(), dl.toScene(angle, dl.R * 1.12)], hot=hot), Line(dl.sweep(dl.a0, angle, r), hot=hot)]
		tag = self._tag(f'{share * 100:.0f}% · {value:.4g}', dl.toScene(angle, dl.R * 1.12))
		self.showGuides(lines, [tag])

	def labelGuides(self, rect: QRectF, spec_rect: Callable[[], Optional[QRectF]], dl: Dial):
		"""Distances from a dragged label to the dial's centre, the card's edges and the other labels."""
		c, mid, card = dl.pivot(), rect.center(), self.scene.sceneRect()
		knee = QPointF(mid.x(), c.y())
		lines = [Line([c, knee], hot='x' in self.hits), Line([knee, mid], hot='y' in self.hits)]
		tags = []
		if abs(mid.x() - c.x()) > 24 or 'x' in self.hits:
			tags.append(self._tag(f'{abs(mid.x() - c.x()):.0f}px', QPointF((c.x() + mid.x()) / 2, c.y() - 9), 'x'))
		if abs(mid.y() - c.y()) > 16 or 'y' in self.hits:
			tags.append(self._tag(f'{abs(mid.y() - c.y()):.0f}px', QPointF(rect.right() + 34, (c.y() + mid.y()) / 2 + 12), 'y'))
		edges = ((QPointF(rect.left(), mid.y()), QPointF(card.left(), mid.y()), rect.left() - card.left()),
		         (QPointF(rect.right(), mid.y()), QPointF(card.right(), mid.y()), card.right() - rect.right()),
		         (QPointF(mid.x(), rect.top()), QPointF(mid.x(), card.top()), rect.top() - card.top()),
		         (QPointF(mid.x(), rect.bottom()), QPointF(mid.x(), card.bottom()), card.bottom() - rect.bottom()))
		for a, b, gap in edges:
			lines.append(Line([a, b], dashed=True))
			tags.append(Tag(f'{gap:.0f}', (a + b) / 2))
		for other in self.items:
			if other.spec.kind != 'label' or other.spec.rect is spec_rect or other.spec.rect is None:
				continue
			o = other.spec.rect()
			if o is None or not other.isVisible():
				continue
			if o.left() < rect.right() and rect.left() < o.right():
				x = (max(o.left(), rect.left()) + min(o.right(), rect.right())) / 2
				a, b = (rect.bottom(), o.top()) if o.top() >= rect.bottom() else (rect.top(), o.bottom())
				seg = (QPointF(x, a), QPointF(x, b))
			elif o.top() < rect.bottom() and rect.top() < o.bottom():
				y = (max(o.top(), rect.top()) + min(o.bottom(), rect.bottom())) / 2
				a, b = (rect.right(), o.left()) if o.left() >= rect.right() else (rect.left(), o.right())
				seg = (QPointF(a, y), QPointF(b, y))
			else:
				continue
			lines.append(Line(list(seg)))
			tags.append(Tag(f'{(seg[1] - seg[0]).manhattanLength():.0f}', (seg[0] + seg[1]) / 2))
		self.showGuides(lines, tags)

	def wheel(self, delta: int, at: QPointF) -> bool:
		"""The wheel with Option held sets the gear ratio. True when it was used (a handle is being dragged, or the pointer is over the preview)."""
		if not delta:
			return False
		ratio = self.gear.step(1 if delta > 0 else -1)
		self.badge.say(f'Gear {ratio}:1', at, hold=self.active is not None and self.gear.geared)
		return True

	def end(self, item: _Handle):
		spec = item.spec
		self.active = None
		self.badge.hide()
		self.hits = {}
		self.guides.clear()
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
		state = self._state
		if self.active is not None and self.active.spec.kind in ('gradient', 'track') and isinstance(state, dict) and 'stops' in state:
			# Mid-drag the gauge still holds the old gradient: a write waits for the flush. The held stops are what the node follows.
			return [s.copy() for s in state['stops']]
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
				# A stop outside the range (50°C on a 0-120°F dial) rests on the arc's end, not past it.
				lo, hi = span()
				value = min(max(value, lo), hi)
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

			out.append(Spec('gradient', 'Drag along the track to move this stop (' + KEYS + '). Drag off the track or press Delete to remove it. Double click for its colour.',
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
			# In value order from the start, so the file never holds the new stop out of place.
			key = lambda s: v if (v := stops.native(s, vc())) is not None else float('inf')
			items = sorted(items + [new], key=key)
			at = next(k for k, s in enumerate(items) if s is new)
			write(items)
			return {'index': at, 'stops': items}

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
				angle = self.pick(angle, 5, fine, 'angle', dl.degPx(), digits=1)
				studio.handleEdit(('arc', key), int(angle) if float(angle).is_integer() else angle)
				self.angleGuides(dial(), angle)
			out.append(Spec('angle', 'Drag to set the arc\'s ' + ('end' if end else 'start') + ' angle (' + KEYS + ')', pos, drag=drag))

		# radius, on the track at the arc's middle
		def radiusPos():
			dl = dial()
			return dl.toScene((dl.a0 + dl.a1) / 2, dl.R)

		def radiusDrag(state, p, fine):
			dl = dial()
			ratio = dl.polar(p)[1] / max(dl.gauge.radius_max, 1) * 100
			ratio = self.pick(ratio, 5, fine, 'fraction', dl.gauge.radius_max, scale=100, digits=1)
			studio.handleEdit(('radius',), f'{max(ratio, 5):g}%')
			after = dial()
			self.shareGuides(after, (after.a0 + after.a1) / 2, after.R, f'{after.R:.0f}px · {max(ratio, 5):g}%', circle=True)
		out.append(Spec('radius', 'Drag to set the radius (' + KEYS + ')', radiusPos, drag=radiusDrag))

		# arc weight, on the track's inner edge, a quarter of the way along
		def weightPos():
			dl = dial()
			return dl.toScene(dl.a0 + (dl.a1 - dl.a0) * 0.3, max(dl.R - dl.weight / 2, 0))

		def weightDrag(state, p, fine):
			dl = dial()
			w = max(2 * (dl.R - dl.polar(p)[1]), 0)
			pct = w / max(dl.R, 1) * 100
			pct = self.pick(pct, 0.5, fine, 'fraction', dl.R, scale=100, digits=1)
			studio.handleEdit(('arc', 'weight'), f'{max(pct, 0.5):g}%')
			after = dial()
			mid = (after.a0 + after.a1) / 2
			self.showGuides([Line([after.toScene(mid, after.R), after.toScene(mid, max(after.R - after.weight, 0))], hot='v' in self.hits)],
			                [self._tag(f'{after.weight:.0f}px · {max(pct, 0.5):g}%', after.toScene(mid, after.R + 14))])
		out.append(Spec('weight', 'Drag to set the arc weight (' + KEYS + ')', weightPos, drag=weightDrag))

		# the needle tip sets the preview value
		def needlePos():
			dl = dial()
			value = float(studio.studio.gauge.value)
			return dl.toScene(dl.valueAngle(value), dl.R * 0.72)

		def needleDrag(state, p, fine):
			dl = dial()
			v = dl.angleValue(dl.polar(p)[0])
			v = self.pick(v, dl.step() / 5, fine, 'fraction', dl.spanPx(), dl.lo, dl.span)
			studio.setValueFromDrag(v)
			self.valueGuides(dl, v)
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
				v = self.pick(v, dl.step(), fine, 'fraction', dl.spanPx(), dl.lo, dl.span)
				specs = copy.deepcopy(self.gauge._markerSpecs)
				specs[i]['value'] = int(v) if float(v).is_integer() else v
				studio.handleEdit(('markers',), specs)
				self.valueGuides(dl, v)
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
					v = self.pick(v, dl.step(), fine, 'fraction', dl.spanPx(), dl.lo, dl.span)
					v = int(v) if float(v).is_integer() else v
					specs = copy.deepcopy(self.gauge._zoneSpecs)
					for spec in specs:
						for e in ('from', 'to'):
							if isinstance(spec.get(e), (int, float)) and not isinstance(spec.get(e), bool) and math.isclose(float(spec[e]), state, abs_tol=1e-9):
								spec[e] = v
					state_after = float(v)
					self._state = state_after
					studio.handleEdit(('zones',), specs)
					self.valueGuides(dl, v)
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
				v = self.pick(v, dl.step(), fine, 'fraction', dl.spanPx(), dl.lo, dl.span)
				spec = copy.deepcopy(self.gauge._fillSpec)
				spec[end] = int(v) if float(v).is_integer() else v
				studio.handleEdit(('fill',), spec)
				self.valueGuides(dl, v)
			out.append(Spec('fill', f'Drag the fill\'s {end} end', fpos, drag=fdrag))

		# labels: drag the text
		def labelSpec(name: str, path: tuple, rect: Callable[[], Optional[QRectF]], read: Callable[[], dict], write: Callable[[dict], None]):
			def begin():
				return {'o': read(), 'p0': None, 'r0': rect()}

			def drag(state, p, fine):
				gauge = self.gauge
				if state['p0'] is None:
					state['p0'] = p
					state['g0'] = gauge.mapFromScene(p)
				delta = gauge.mapFromScene(p) - state['g0']
				diameter = max(gauge.radius * 2, 1)
				x = self.pick(state['o']['x'] + delta.x() / diameter, 0.005, fine, 'offset', diameter, name='x', digits=4)
				y = self.pick(state['o']['y'] + delta.y() / diameter, 0.005, fine, 'offset', diameter, name='y', digits=4)
				write({'x': round(x, 4), 'y': round(y, 4)})
				# The label settles a frame after the write, so place the guides from where it was and how far it moved.
				if state['r0'] is not None:
					shift = gauge.mapToScene(QPointF((x - state['o']['x']) * diameter, (y - state['o']['y']) * diameter)) - gauge.mapToScene(QPointF())
					self.labelGuides(state['r0'].translated(shift), rect, dial())
			return Spec('label', f'Drag the {name} ({KEYS})', lambda: None, begin=begin, drag=drag, rect=rect)

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
