"""Draws a label's `change-animation` (`lib/ui/value_change.py` holds the styles and parsing).

The text item itself never paints differently: the outgoing text is a child path item (a "ghost") holding the old
outline at its old place, and the incoming text is the item as it already is, moved with a `QGraphicsTransform` and
faded with its opacity. So nothing here adds a Python `paint()` to the hundreds of text items a dashboard has, and
an item that never changes value costs nothing. While a change runs, each frame sets one opacity and one offset,
and Qt repaints only the two small regions involved.

`LEVITY_CHANGE_ANIMATION=0` in the environment turns every change animation off, for an A/B on a slow display.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, NamedTuple, Optional

from PySide6.QtCore import QEasingCurve, QVariantAnimation
from PySide6.QtGui import QBrush, QPainterPath, QPen, Qt, QTransform
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsTransform
from shiboken6 import isValid

from LevityDash.lib.ui import Color
from LevityDash.lib.ui.value_change import ChangeSpec, direction

if TYPE_CHECKING:
	from PySide6.QtWidgets import QGraphicsPathItem as _TextItem

__all__ = ('ChangeAnimator', 'Before', 'enabled')

#: How far a slide travels, as a share of the text's height.
SLIDE_TRAVEL = 0.5
#: How bright a flash starts (the opacity of the accent copy over the new text).
FLASH_PEAK = 0.85


def enabled() -> bool:
	return os.environ.get('LEVITY_CHANGE_ANIMATION', '1').strip().lower() not in ('0', 'false', 'no', 'off')


def _motionCurve() -> QEasingCurve:
	"""The theme's `motion` curve where this version has one (`lib/ui/motion.py`), the original ease otherwise."""
	try:
		from LevityDash.lib.ui import motion
		return motion.curve()
	except Exception:
		return QEasingCurve(QEasingCurve.Type.OutCubic)


class Before(NamedTuple):
	"""What the text looked like before the new value was built."""
	path: QPainterPath
	transform: QTransform
	brush: QBrush
	pen: QPen
	text: str


class _Shift(QGraphicsTransform):
	"""A vertical offset in the parent's pixels, applied after the item's own transform (Qt has no translation
	`QGraphicsTransform`)."""

	def __init__(self):
		super().__init__()
		self.dy = 0.0

	def applyTo(self, matrix):
		matrix.translate(0, self.dy)

	def setOffset(self, dy: float):
		if dy != self.dy:
			self.dy = dy
			self.update()


class ChangeAnimator:
	"""One per text item, created the first time its value changes with an animation set."""

	def __init__(self, item: '_TextItem'):
		self.item = item
		self.animation: Optional[QVariantAnimation] = None
		self.ghost: Optional[QGraphicsPathItem] = None
		self.shift: Optional[_Shift] = None
		self.spec: Optional[ChangeSpec] = None
		self.before: Optional[Before] = None
		self.opacity = 1.0
		self.travel = 0.0
		self.curve: Optional[QEasingCurve] = None
		self._flashPathSet = False

	@property
	def running(self) -> bool:
		return self.animation is not None

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
		self.spec, self.before = spec, before
		self.opacity = item.opacity()
		ghost = QGraphicsPathItem(item)
		ghost.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
		ghost.setAcceptHoverEvents(False)
		if spec.style == 'flash':
			ghost.setBrush(QBrush(Color.role('accent').QColor))
			ghost.setPen(QPen(Qt.PenStyle.NoPen))
			ghost.setZValue(1)
			ghost.setOpacity(FLASH_PEAK)
			self._flashPathSet = False
		else:
			ghost.setPath(before.path)
			ghost.setBrush(before.brush)
			ghost.setPen(before.pen)
			# the item fades in while its ghost fades out: the ghost must not take the item's opacity
			ghost.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresParentOpacity, True)
		self.ghost = ghost
		if spec.style == 'slide':
			height = before.path.boundingRect().height() * abs(before.transform.m22() or 1.0)
			sign = -1 if direction(before.text, text) < 0 else 1
			# y grows downward: a rising number arrives from below and leaves upward
			self.travel = sign * height * SLIDE_TRAVEL
			self.curve = _motionCurve()
			self.shift = _Shift()
			item.setTransformations([self.shift])
		animation = QVariantAnimation()
		animation.setStartValue(0.0)
		animation.setEndValue(1.0)
		animation.setDuration(spec.ms)
		animation.valueChanged.connect(self._frame)
		animation.finished.connect(self.stop)
		self.animation = animation
		self._frame(0.0)
		animation.start()

	def _ghostTransform(self, offset: float) -> QTransform:
		"""The ghost's transform that puts the old outline where it was drawn, moved `offset` parent pixels down,
		under the item's current transform and slide offset."""
		item = self.item
		inverse, ok = item.transform().inverted()
		if not ok:
			inverse = QTransform()
		own = self.shift.dy if self.shift is not None else 0.0
		return self.before.transform * QTransform.fromTranslate(0, offset - own) * inverse

	def _frame(self, t):
		item, ghost, spec = self.item, self.ghost, self.spec
		if spec is None or ghost is None or not isValid(item) or not isValid(ghost):
			return
		t = min(max(float(t), 0.0), 1.0)
		style = spec.style
		if style == 'flash':
			if not self._flashPathSet:
				# the new outline, once the item has finished building it (warp may replace it after the build)
				ghost.setPath(item.path())
				self._flashPathSet = True
			ghost.setOpacity(FLASH_PEAK * (1.0 - t) ** 2)
			return
		if style == 'fade':
			k = t * t * (3 - 2 * t)
			item.setOpacity(self.opacity * k)
			ghost.setOpacity(self.opacity * (1.0 - k))
			ghost.setTransform(self._ghostTransform(0.0))
			return
		# slide: the position follows the theme's curve (it may pass 1 and come back); the fades are quicker
		p = self.curve.valueForProgress(t) if self.curve is not None else t
		self.shift.setOffset(self.travel * (1.0 - p))
		item.setOpacity(self.opacity * min(1.0, t * 2.0))
		ghost.setOpacity(self.opacity * max(0.0, 1.0 - t * 2.0))
		ghost.setTransform(self._ghostTransform(-self.travel * p))

	def stop(self):
		"""End a running change at its last frame: the item as built, no ghost, no offset."""
		animation, self.animation = self.animation, None
		if animation is not None:
			try:
				animation.valueChanged.disconnect(self._frame)
				animation.finished.disconnect(self.stop)
			except (RuntimeError, TypeError):
				pass
			animation.stop()
		ghost, self.ghost = self.ghost, None
		item = self.item
		if ghost is not None and isValid(ghost):
			ghost.setParentItem(None)
			if (scene := ghost.scene()) is not None:
				scene.removeItem(ghost)
		if isValid(item) and self.spec is not None:
			if self.shift is not None:
				item.setTransformations([])
			if self.spec.style != 'flash':
				item.setOpacity(self.opacity)
		self.shift = None
		self.spec = None
		self.before = None
