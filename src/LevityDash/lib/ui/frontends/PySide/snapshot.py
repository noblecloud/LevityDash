"""Draw an item and everything under it into one pixmap, so a moving subtree costs a blit instead of a repaint.

A band slides its items for most of a second; each frame used to run the Python `paint()` of every item in every
card (about 6,000 on the home showcase). `renderSubtree` paints the subtree once, in the scene's own stacking
order, and `Snapshot` shows that pixmap in the item's place while the real items are made transparent, which Qt
skips without walking their children.

The subtree is taken by walking the item tree, never from the scene's item index (`scene.items(region)`): that
index only covers the scene rectangle, so an item parked outside it - a band card waiting off screen for its turn
- comes back as nothing at all, and the picture is blank. The card then shows an empty slot for the whole move
and pops back in when the move ends.

Things a plain walk cannot draw the way the scene does are refused rather than approximated: an item with a
`QGraphicsEffect` (a drop shadow or blur is drawn by the scene, not by `paint`) makes `renderSubtree` return None,
and the caller animates the real items as before.
"""
from typing import Iterator, Optional, Tuple

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem, QStyleOptionGraphicsItem

__all__ = ['renderSubtree', 'Snapshot', 'MAX_PIXELS']

MAX_PIXELS = 4096 * 4096  # a subtree bigger than this is left live: the pixmap would cost more than it saves

_CLIPS_CHILDREN = QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape
_CLIPS_SELF = QGraphicsItem.GraphicsItemFlag.ItemClipsToShape
_NO_CONTENTS = QGraphicsItem.GraphicsItemFlag.ItemHasNoContents


def _extent(root: QGraphicsItem) -> QRectF:
	"""The rectangle, in `root`'s coordinates, its drawing can cover: its own rect, and its children's unless it clips them."""
	rect = root.boundingRect()
	if not root.flags() & _CLIPS_CHILDREN:
		rect = rect.united(root.childrenBoundingRect())
	return rect


def _paintOrder(root: QGraphicsItem) -> Iterator[QGraphicsItem]:
	"""`root` and every descendant, in the order the scene paints them: an item, then its children by `z`

	`childItems()` is already in stacking order, and a stable sort by `zValue()` keeps that order among equals,
	which is how Qt orders siblings too. The tree is walked rather than the scene index so an item outside the
	scene rectangle is still found.
	"""
	yield root
	for child in sorted(root.childItems(), key=lambda item: item.zValue()):
		yield from _paintOrder(child)


def renderSubtree(root: QGraphicsItem, scale: float) -> Optional[Tuple[QPixmap, QRectF]]:
	"""Paint `root` and its visible descendants into a pixmap with `scale` device pixels per unit of `root`.

	Returns the pixmap (its device pixel ratio set to `scale`) and the rectangle it covers in `root`'s coordinates,
	or None when the subtree cannot be drawn faithfully this way (an effect, nothing to draw, too large).
	"""
	scene = root.scene()
	if scene is None or not root.isVisible():
		return None
	local = _extent(root)
	if local.isEmpty() or local.width() * local.height() * scale * scale > MAX_PIXELS:
		return None
	items = list(_paintOrder(root))
	for item in items:
		effect = item.graphicsEffect()
		if effect is not None and effect.isEnabled() and item.isVisible():
			return None

	device = QRectF(local.x() * scale, local.y() * scale, local.width() * scale, local.height() * scale).toAlignedRect()
	pixmap = QPixmap(device.size())
	pixmap.fill(Qt.GlobalColor.transparent)
	# scene -> root's coordinates -> pixmap pixels
	toPixmap = root.sceneTransform().inverted()[0] * QTransform.fromTranslate(-device.x() / scale, -device.y() / scale) * QTransform.fromScale(scale, scale)
	rootOpacity = root.effectiveOpacity() or 1.0
	painter = QPainter(pixmap)
	painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing | QPainter.RenderHint.SmoothPixmapTransform)
	option = QStyleOptionGraphicsItem()
	try:
		for item in items:
			if not item.isVisible() or item.flags() & _NO_CONTENTS:
				continue
			opacity = item.effectiveOpacity() / rootOpacity
			if opacity <= 0.001:
				continue
			painter.save()
			painter.resetTransform()
			_clip(painter, item, root, toPixmap)
			painter.setWorldTransform(item.sceneTransform() * toPixmap)
			painter.setOpacity(min(opacity, 1.0))
			rect = item.boundingRect()
			option.rect = rect.toRect()
			option.exposedRect = rect
			item.paint(painter, option, None)
			painter.restore()
	finally:
		painter.end()
	pixmap.setDevicePixelRatio(scale)
	return pixmap, QRectF(device.x() / scale, device.y() / scale, device.width() / scale, device.height() / scale)


def _clip(painter: QPainter, item: QGraphicsItem, root: QGraphicsItem, toPixmap: QTransform) -> None:
	"""Clip as the scene would: to the shape of every ancestor up to `root` that clips its children, and to the
	item's own shape when it clips itself. `root`'s own parent is the caller's business (the snapshot sits where it is)."""
	clippers = []
	if item.flags() & _CLIPS_SELF:
		clippers.append(item)
	parent = item.parentItem() if item is not root else None
	while parent is not None:
		if parent.flags() & _CLIPS_CHILDREN:
			clippers.append(parent)
		if parent is root:
			break
		parent = parent.parentItem()
	for clipper in clippers:
		path = (clipper.sceneTransform() * toPixmap).map(clipper.shape())
		painter.setClipPath(path, Qt.ClipOperation.IntersectClip)


class Snapshot(QGraphicsPixmapItem):
	"""A pixmap standing in for `item` (a sibling of it, at the same place and stacking) while `item` is hidden by opacity."""

	def __init__(self, item: QGraphicsItem, pixmap: QPixmap, rect: QRectF):
		super().__init__(pixmap, item.parentItem())
		self.item = item
		self.setOffset(rect.topLeft())
		self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
		self.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)
		self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
		self.setAcceptHoverEvents(False)
		self.setPos(item.pos())
		self.setTransform(item.transform())
		self.setZValue(item.zValue())
		self.stackBefore(item)
		self.savedOpacity = item.opacity()
		item.setOpacity(0.0)

	def release(self) -> None:
		"""Show the real item again and take the pixmap off the scene."""
		self.item.setOpacity(self.savedOpacity)
		scene = self.scene()
		if scene is not None:
			scene.removeItem(self)
		self.setParentItem(None)
