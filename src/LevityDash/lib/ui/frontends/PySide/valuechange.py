"""Draws a label's `change-animation` (`lib/ui/value_change.py` holds the styles and parsing).

The text item itself never paints differently. The outgoing text is a child path item (a "ghost") holding the old
outline at its old place; the incoming text is the item as it already is, moved or turned with a `QGraphicsTransform`
and faded with its opacity. `roll` goes one step further: it swaps the item's outline for the characters that did
not change and rolls each changed one in a clipped column of its own. So nothing here adds a Python `paint()` to the
hundreds of text items a dashboard has, and an item that never changes value costs nothing. While a change runs,
each frame sets a few opacities and offsets, and Qt repaints only the small regions involved.

An animation starts from `Text.updateTransform`, once the new outline has its final place, so every effect can map
the old outline (kept with the transform it was shown with) into the item's new frame once, at the start.

`LEVITY_CHANGE_ANIMATION=0` in the environment turns every change animation off, for an A/B on a slow display.
"""
from __future__ import annotations

import os
import re
import time
from typing import NamedTuple, Optional

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QVariantAnimation
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen, QTransform, QVector3D, Qt
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsRectItem, QGraphicsRotation, QGraphicsTransform
from shiboken6 import isValid

from LevityDash.lib.ui import Color
from LevityDash.lib.ui.value_change import ChangeSpec, direction, number

__all__ = ('ChangeAnimator', 'Before', 'enabled', 'glyphs')

#: How far a slide travels, as a share of the text's height.
SLIDE_TRAVEL = 0.5
#: How bright a flash or tint starts (the opacity of the coloured copy over the new text).
FLASH_PEAK = 0.85
#: The size the new text of a `pop` starts at.
POP_FROM = 0.8
#: How much later each changed column of a `roll` starts than the one to its right, as a share of the duration,
#: and the most all of them may add up to.
ROLL_STAGGER, ROLL_STAGGER_MAX = 0.07, 0.3


def enabled() -> bool:
	return os.environ.get('LEVITY_CHANGE_ANIMATION', '1').strip().lower() not in ('0', 'false', 'no', 'off')


def _motionCurve() -> QEasingCurve:
	"""The theme's `motion` curve (`lib/ui/motion.py`, `smooth` or `spring`), an ease out where there is none."""
	try:
		from LevityDash.lib.ui import motion
		return motion.curve()
	except Exception:
		return QEasingCurve(QEasingCurve.Type.OutCubic)


def _smooth(t: float) -> float:
	return t * t * (3 - 2 * t)


def _clamp(t: float) -> float:
	return 0.0 if t < 0 else 1.0 if t > 1 else t


class Before(NamedTuple):
	"""What the text looked like before the new value was built."""
	path: QPainterPath
	transform: QTransform
	brush: QBrush
	pen: QPen
	text: str


class Glyph(NamedTuple):
	rect: QRectF
	path: QPainterPath


def glyphs(path: QPainterPath) -> list[Glyph]:
	"""The outline split into one path per drawn character, left to right.

	A text outline is a list of contours. Contours whose horizontal extents overlap by more than a quarter of the
	narrower one belong to one glyph (the hole of an 8, the dot of an i, the parts of a %); glyphs side by side
	barely overlap, if at all. A space draws nothing, so it has no glyph.
	"""
	subs: list[QPainterPath] = []
	current = None
	types = QPainterPath.ElementType
	i, n = 0, path.elementCount()
	while i < n:
		e = path.elementAt(i)
		if e.type == types.MoveToElement:
			current = QPainterPath()
			current.setFillRule(path.fillRule())
			current.moveTo(e.x, e.y)
			subs.append(current)
			i += 1
		elif e.type == types.LineToElement and current is not None:
			current.lineTo(e.x, e.y)
			i += 1
		elif e.type == types.CurveToElement and current is not None and i + 2 < n:
			c2, end = path.elementAt(i + 1), path.elementAt(i + 2)
			current.cubicTo(e.x, e.y, c2.x, c2.y, end.x, end.y)
			i += 3
		else:
			i += 1
	pieces = sorted(((p.boundingRect(), p) for p in subs if not p.isEmpty()), key=lambda rp: rp[0].left())
	clusters: list[list] = []
	for rect, piece in pieces:
		if clusters:
			last = clusters[-1]
			overlap = last[0].right() - rect.left()
			if overlap > 0.25 * min(rect.width(), last[0].width()):
				last[0] = last[0].united(rect)
				last[1].addPath(piece)
				continue
		merged = QPainterPath()
		merged.setFillRule(path.fillRule())
		merged.addPath(piece)
		clusters.append([QRectF(rect), merged])
	return [Glyph(rect, p) for rect, p in clusters]


class _Shift(QGraphicsTransform):
	"""A vertical offset in the parent's pixels, applied after the item's own transform."""

	def __init__(self):
		super().__init__()
		self.dy = 0.0

	def applyTo(self, matrix):
		matrix.translate(0, self.dy)

	def setOffset(self, dy: float):
		if dy != self.dy:
			self.dy = dy
			self.update()


class _Scale(QGraphicsTransform):
	"""A uniform scale about a point in the parent's coordinates, applied after the item's own transform."""

	def __init__(self, centre: QPointF):
		super().__init__()
		self.centre = centre
		self.factor = 1.0

	def applyTo(self, matrix):
		x, y = self.centre.x(), self.centre.y()
		matrix.translate(x, y, 0)
		matrix.scale(self.factor, self.factor, 1)
		matrix.translate(-x, -y, 0)

	def setFactor(self, factor: float):
		if factor != self.factor:
			self.factor = factor
			self.update()


def _child(parent, path: QPainterPath, brush: QBrush, pen: QPen) -> QGraphicsPathItem:
	child = QGraphicsPathItem(path, parent)
	child.setBrush(brush)
	child.setPen(pen)
	child.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
	child.setAcceptHoverEvents(False)
	return child


def _drop(item):
	if item is not None and isValid(item):
		item.setParentItem(None)
		if (scene := item.scene()) is not None:
			scene.removeItem(item)


class _Effect:
	"""One running change. `begin` builds what it needs, `frame(t)` (t from 0 to 1) moves it, `end` puts the item
	back exactly as built."""

	def __init__(self, item, before: Before, text: str, spec: ChangeSpec):
		self.item, self.before, self.text, self.spec = item, before, text, spec
		self.opacity = item.opacity()
		self.sign = -1 if direction(before.text, text) < 0 else 1
		self.children: list = []

	def oldToNew(self) -> QTransform:
		"""Maps the old outline's coordinates to the item's present ones."""
		inverse, ok = self.item.transform().inverted()
		return self.before.transform * (inverse if ok else QTransform())

	def centre(self) -> QPointF:
		return self.item.transform().map(self.item.path().boundingRect().center())

	def ghost(self, path=None, transform=None, brush=None, pen=None, ownOpacity=True) -> QGraphicsPathItem:
		before = self.before
		child = _child(self.item, before.path if path is None else path, before.brush if brush is None else brush,
		               before.pen if pen is None else pen)
		if transform is not None:
			child.setTransform(transform)
		if ownOpacity:
			# the item fades in while its ghost fades out: the ghost must not take the item's opacity
			child.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresParentOpacity, True)
		self.children.append(child)
		return child

	def begin(self):
		pass

	def frame(self, t: float):
		pass

	def end(self):
		item = self.item
		for child in self.children:
			_drop(child)
		self.children = []
		if isValid(item):
			if item.transformations():
				item.setTransformations([])
			if item.opacity() != self.opacity:
				item.setOpacity(self.opacity)


class _Fade(_Effect):
	def begin(self):
		self.old = self.ghost(transform=self.oldToNew())

	def frame(self, t):
		k = _smooth(t)
		self.item.setOpacity(self.opacity * k)
		self.old.setOpacity(self.opacity * (1.0 - k))


class _Slide(_Effect):
	def begin(self):
		before = self.before
		height = before.path.boundingRect().height() * abs(before.transform.m22() or 1.0)
		# y grows downward: a rising number arrives from below and leaves upward
		self.travel = self.sign * height * SLIDE_TRAVEL
		self.curve = _motionCurve()
		self.shift = _Shift()
		self.item.setTransformations([self.shift])
		self.old = self.ghost()

	def frame(self, t):
		item, before = self.item, self.before
		p = self.curve.valueForProgress(t)
		self.shift.setOffset(self.travel * (1.0 - p))
		item.setOpacity(self.opacity * min(1.0, t * 2.0))
		self.old.setOpacity(self.opacity * max(0.0, 1.0 - t * 2.0))
		inverse, ok = item.transform().inverted()
		offset = -self.travel * p - self.shift.dy
		self.old.setTransform(before.transform * QTransform.fromTranslate(0, offset) * (inverse if ok else QTransform()))


class _Flash(_Effect):
	def colour(self) -> QColor:
		return Color.role('accent').QColor

	def begin(self):
		glow = self.ghost(path=self.item.path(), brush=QBrush(self.colour()), pen=QPen(Qt.PenStyle.NoPen), ownOpacity=False)
		glow.setZValue(1)
		self.glow = glow

	def frame(self, t):
		self.glow.setOpacity(FLASH_PEAK * (1.0 - t) ** 2)


class _Tint(_Flash):
	def colour(self) -> QColor:
		token = {1: 'good', -1: 'bad'}[self.sign] if direction(self.before.text, self.text) else 'accent'
		return Color.role(token).QColor


class _Pop(_Effect):
	def begin(self):
		self.curve = _motionCurve()
		self.scale = _Scale(self.centre())
		self.item.setTransformations([self.scale])
		self.old = self.ghost(transform=self.oldToNew())

	def frame(self, t):
		factor = POP_FROM + (1.0 - POP_FROM) * self.curve.valueForProgress(t)
		self.scale.setFactor(factor)
		self.item.setOpacity(self.opacity * min(1.0, t * 2.5))
		self.old.setOpacity(self.opacity * max(0.0, 1.0 - t * 3.0))
		# the old text is a child, so it takes the item's scale: undo it, it stays its size while it fades
		own = self.item.transform()
		inverse, ok = own.inverted()
		c = self.scale.centre
		unscale = QTransform.fromTranslate(-c.x(), -c.y()) * QTransform.fromScale(1 / factor, 1 / factor) * QTransform.fromTranslate(c.x(), c.y())
		self.old.setTransform(self.before.transform * unscale * (inverse if ok else QTransform()))


class _Flip(_Effect):
	def begin(self):
		self.turn = QGraphicsRotation()
		self.turn.setAxis(Qt.Axis.XAxis)
		centre = self.centre()
		self.turn.setOrigin(QVector3D(centre.x(), centre.y(), 0))
		self.item.setTransformations([self.turn])
		self.old = self.ghost(transform=self.oldToNew())
		self.fold = QEasingCurve(QEasingCurve.Type.InQuad)
		self.land = _motionCurve()

	def frame(self, t):
		# the first half folds the old text away from the viewer, the second folds the new one down into place
		if t < 0.5:
			self.turn.setAngle(-90.0 * self.fold.valueForProgress(t * 2))
			self.item.setOpacity(0.0)
			self.old.setOpacity(self.opacity)
		else:
			self.turn.setAngle(90.0 * (1.0 - self.land.valueForProgress((t - 0.5) * 2)))
			self.item.setOpacity(self.opacity)
			self.old.setOpacity(0.0)


class _Roll(_Effect):
	"""An odometer: the characters that changed roll in their own clipped columns; the rest stay still."""

	def begin(self):
		item, before = self.item, self.before
		self.full = QPainterPath(item.path())
		mapping = self.oldToNew()
		old, new = glyphs(before.path), glyphs(self.full)
		oldChars = [c for c in before.text if not c.isspace()]
		newChars = [c for c in self.text if not c.isspace()]
		if len(old) == len(oldChars) and len(new) == len(newChars):
			pairs = self._pairs(old, oldChars, new, newChars)
		else:
			# the outline does not split into one shape per character: roll it whole
			pairs = [(Glyph(before.path.boundingRect(), before.path), Glyph(self.full.boundingRect(), self.full))]
		static = QPainterPath()
		static.setFillRule(self.full.fillRule())
		moving = []
		for o, n in pairs:
			if isinstance(o, str):  # unchanged character: its new glyph stays in the outline
				static.addPath(n.path)
			else:
				moving.append((o, n))
		if not moving:
			self.columns = []
			return
		rects = [mapping.mapRect(o.rect) for o, _ in moving if o is not None] + [n.rect for _, n in moving if n is not None]
		band = QRectF(rects[0])
		for rect in rects[1:]:
			band = band.united(rect)
		pad = band.height() * 0.12
		top, height = band.top() - pad, band.height() + 2 * pad
		self.travel = height * self.sign
		self.curve = _motionCurve()
		self.columns = []
		count = len(moving)
		stagger = min(ROLL_STAGGER, ROLL_STAGGER_MAX / max(1, count - 1)) if count > 1 else 0.0
		for index, (o, n) in enumerate(moving):
			span = QRectF(n.rect) if n is not None else QRectF()
			if o is not None:
				span = span.united(mapping.mapRect(o.rect)) if not span.isNull() else mapping.mapRect(o.rect)
			grow = span.width() * 0.1
			clip = QGraphicsRectItem(QRectF(span.left() - grow, top, span.width() + 2 * grow, height), item)
			clip.setPen(QPen(Qt.PenStyle.NoPen))
			clip.setBrush(QBrush(Qt.BrushStyle.NoBrush))
			clip.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, True)
			clip.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
			self.children.append(clip)
			outgoing = incoming = None
			if o is not None:
				outgoing = _child(clip, o.path, before.brush, before.pen)
				outgoing.setTransform(mapping)
			if n is not None:
				incoming = _child(clip, n.path, item.brush(), item.pen())
			# the rightmost changed character (the smallest place) moves first
			delay = (count - 1 - index) * stagger
			self.columns.append((delay, outgoing, incoming))
		self.stagger = stagger * max(0, count - 1)
		item.setPath(static)

	@staticmethod
	def _pairs(old, oldChars, new, newChars):
		"""Right-aligned pairs, so 9 to 10 keeps the units column: a character that did not change gives the string
		itself (its new glyph stays put), a changed one gives the old and new glyph, either `None` where the other
		text is shorter."""
		size = max(len(old), len(new))
		po, pn = size - len(old), size - len(new)
		pairs = []
		for i in range(size):
			o = old[i - po] if i >= po else None
			n = new[i - pn] if i >= pn else None
			co = oldChars[i - po] if i >= po else None
			cn = newChars[i - pn] if i >= pn else None
			if o is not None and n is not None and co == cn:
				pairs.append((co, n))
			else:
				pairs.append((o, n))
		return pairs

	def frame(self, t):
		span = 1.0 - self.stagger
		for delay, outgoing, incoming in self.columns:
			local = _clamp((t - delay) / span) if span > 0 else 1.0
			p = self.curve.valueForProgress(local)
			if outgoing is not None:
				outgoing.setPos(0, -self.travel * p)
			if incoming is not None:
				incoming.setPos(0, self.travel * (1.0 - p))

	def end(self):
		item = self.item
		super().end()
		if isValid(item) and getattr(self, 'full', None) is not None:
			item.setPath(self.full)



#: A `slot` strip never holds more than this many digits: a column spins at most once round.
SLOT_MAX_DIGITS = 10
#: The longest a `count` goes between two rebuilds of its text, in seconds (about 30 a second).
COUNT_INTERVAL = 1 / 30
_COUNT_NUMBER = re.compile(r'[-−]?\d[\d,]*(?:\.(\d+))?')


class _Slot(_Roll):
	"""A slot machine: like `roll`, but a changed digit spins through the digits in between before it lands."""

	def _pairs(self, old, oldChars, new, newChars):
		pairs = _Roll._pairs(old, oldChars, new, newChars)
		# remember the characters of each column that moves, in the order `_Roll.begin` keeps them
		size = max(len(old), len(new))
		po, pn = size - len(old), size - len(new)
		chars = []
		for i, pair in enumerate(pairs):
			if not isinstance(pair[0], str):
				chars.append((oldChars[i - po] if i >= po else None, newChars[i - pn] if i >= pn else None))
		self.chars = chars
		return pairs

	def begin(self):
		self.chars = []
		self.strips = []
		super().begin()
		if not getattr(self, 'columns', None) or len(self.chars) != len(self.columns):
			return
		clips = [c for c in self.children if isinstance(c, QGraphicsRectItem)]
		if len(clips) != len(self.columns):
			return
		mapping, kept = self.oldToNew(), []
		pitch = abs(self.travel)
		for (delay, outgoing, incoming), (co, cn), clip in zip(self.columns, self.chars, clips):
			steps = self._steps(co, cn)
			if steps is None or outgoing is None or incoming is None:
				kept.append((delay, outgoing, incoming))
				continue
			strip = self._strip(co, cn, steps, outgoing, incoming, pitch, mapping)
			if strip is None:
				kept.append((delay, outgoing, incoming))
				continue
			_drop(outgoing)
			_drop(incoming)
			child = _child(clip, strip, self.item.brush(), self.item.pen())
			self.strips.append((delay, child, steps))
		self.columns = kept

	def _steps(self, co, cn):
		"""How many digits the strip moves through between the old and the new one, or `None` for a non-digit."""
		if not (co and cn and co.isdecimal() and cn.isdecimal()):
			return None
		a, b = int(co), int(cn)
		n = (b - a) % 10 if self.sign > 0 else (a - b) % 10
		return min(n, SLOT_MAX_DIGITS - 1) or None

	def _strip(self, co, cn, steps, outgoing, incoming, pitch, mapping):
		item = self.item
		font = item.font()
		target = incoming.path().boundingRect()
		probe = QPainterPath()
		probe.addText(0, 0, font, cn)
		ink = probe.boundingRect()
		if ink.height() <= 0 or target.height() <= 0:
			return None
		scale = target.height() / ink.height()
		strip = QPainterPath()
		strip.setFillRule(incoming.path().fillRule())
		a = int(co)
		for k in range(steps + 1):
			y = self.sign * k * pitch
			if k == 0:
				strip.addPath(QTransform.fromTranslate(0, y).map(mapping.map(outgoing.path())))
			elif k == steps:
				strip.addPath(QTransform.fromTranslate(0, y).map(incoming.path()))
			else:
				digit = str((a + self.sign * k) % 10)
				glyph = QPainterPath()
				glyph.addText(0, 0, font, digit)
				b = glyph.boundingRect()
				place = QTransform()
				place.translate(target.center().x() - b.center().x() * scale, target.bottom() - b.bottom() * scale + y)
				place.scale(scale, scale)
				strip.addPath(place.map(glyph))
		return strip

	def frame(self, t):
		super().frame(t)
		span = 1.0 - self.stagger
		for delay, child, steps in self.strips:
			local = _clamp((t - delay) / span) if span > 0 else 1.0
			p = SLOT_EASE.valueForProgress(local)
			child.setPos(0, -self.sign * steps * abs(self.travel) * p)


SLOT_EASE = QEasingCurve(QEasingCurve.Type.OutQuart)


class _Count(_Fade):
	"""A count-up: the number runs from the old value to the new one, in the item's font, drawn as one child path
	that is rebuilt only when the shown string changes (and at most 30 times a second). Text without a number fades."""

	def begin(self):
		old, new = number(self.before.text), number(self.text)
		match = _COUNT_NUMBER.search(self.text)
		target = self.item.path()
		self.counting = old is not None and new is not None and match is not None and not target.isEmpty()
		if not self.counting:
			return super().begin()
		self.old, self.new = old, new
		self.decimals = len(match.group(1) or '')
		self.grouped = ',' in match.group(0)
		self.prefix, self.suffix = self.text[:match.start()], self.text[match.end():]
		self.full = QPainterPath(target)
		self.target = target.boundingRect()
		self.font = self.item.font()
		reference = QPainterPath()
		reference.addText(0, 0, self.font, self.text)
		ink = reference.boundingRect()
		self.scale = self.target.height() / ink.height() if ink.height() > 0 else 1.0
		self.shown = None
		self.stamp = 0.0
		self.curve = QEasingCurve(QEasingCurve.Type.OutCubic)
		self.child = _child(self.item, QPainterPath(), self.item.brush(), self.item.pen())
		self.children.append(self.child)
		self.item.setPath(QPainterPath())

	def shownText(self, value: float) -> str:
		body = f'{value:,.{self.decimals}f}' if self.grouped else f'{value:.{self.decimals}f}'
		return self.prefix + body + self.suffix

	def rebuild(self, text: str):
		path = QPainterPath()
		path.addText(0, 0, self.font, text)
		ink = path.boundingRect()
		place = QTransform()
		place.translate(self.target.right() - ink.right() * self.scale, self.target.bottom() - ink.bottom() * self.scale)
		place.scale(self.scale, self.scale)
		path = place.map(path)
		path.setFillRule(self.full.fillRule())
		self.child.setPath(path)
		self.shown = text

	def frame(self, t):
		if not self.counting:
			return super().frame(t)
		text = self.shownText(self.old + (self.new - self.old) * self.curve.valueForProgress(t))
		now = time.monotonic()
		if text != self.shown and (self.shown is None or t >= 1.0 or now - self.stamp >= COUNT_INTERVAL):
			self.rebuild(text)
			self.stamp = now

	def end(self):
		item = self.item
		super().end()
		if isValid(item) and getattr(self, 'full', None) is not None:
			item.setPath(self.full)


EFFECTS = {
	'fade': _Fade,
	'slide': _Slide,
	'flash': _Flash,
	'tint': _Tint,
	'pop': _Pop,
	'flip': _Flip,
	'roll': _Roll,
	'slot': _Slot,
	'count': _Count,
}


class ChangeAnimator:
	"""One per text item, created the first time its value changes with an animation set."""

	def __init__(self, item):
		self.item = item
		self.animation: Optional[QVariantAnimation] = None
		self.effect: Optional[_Effect] = None

	@property
	def running(self) -> bool:
		return self.animation is not None

	@property
	def spec(self) -> Optional[ChangeSpec]:
		return self.effect.spec if self.effect is not None else None

	@staticmethod
	def capture(item, text: str, transform: Optional[QTransform] = None) -> Before:
		"""`transform` is the one the text was last shown with; the item's own may already be reset for a rebuild."""
		transform = QTransform(transform if transform is not None else item.transform())
		return Before(QPainterPath(item.path()), transform, QBrush(item.brush()), QPen(item.pen()), text)

	def start(self, spec: ChangeSpec, before: Before, text: str):
		self.stop()
		item = self.item
		if not isValid(item) or before.path.isEmpty():
			return
		style = spec.style
		if style in ('roll', 'slot') and getattr(item, '_warpActive', False):
			style = 'slide'
		effect = EFFECTS[style](item, before, text, spec)
		effect.begin()
		self.effect = effect
		animation = QVariantAnimation()
		animation.setStartValue(0.0)
		animation.setEndValue(1.0)
		animation.setDuration(spec.ms)
		animation.valueChanged.connect(self._frame)
		animation.finished.connect(self.stop)
		self.animation = animation
		self._frame(0.0)
		animation.start()

	def _frame(self, t):
		effect = self.effect
		if effect is None or not isValid(self.item):
			return
		effect.frame(_clamp(float(t)))

	def stop(self):
		"""End a running change at its last frame: the item as built, nothing added, nothing moved."""
		animation, self.animation = self.animation, None
		if animation is not None:
			try:
				animation.valueChanged.disconnect(self._frame)
				animation.finished.disconnect(self.stop)
			except (RuntimeError, TypeError):
				pass
			animation.stop()
		effect, self.effect = self.effect, None
		if effect is not None:
			effect.end()
