"""The radar, larger, in a popover over the whole dashboard.

Clicking a radar away from any aircraft opens this: the same disc, the same blips and the same colours, drawn into
the largest square the scene allows over a dimmed backdrop. Another click on a blip names it, a click anywhere else
closes it. It draws nothing itself: the panel it belongs to paints, so the two can never disagree about a plane.
"""
from typing import TYPE_CHECKING, Any, Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGraphicsItem

from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar import radar

if TYPE_CHECKING:  # pragma: no cover - typing only
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.item import Polar

__all__ = ['RadarPopover']

#: How much of the scene the popover leaves as a margin, as a fraction of its shorter side.
MARGIN = 0.06


class RadarPopover(QGraphicsItem):
	"""A bigger radar over the scene. Click a blip for its details, or anywhere else to close it."""

	def __init__(self, source):
		"""``source`` is the Polar panel: it paints the disc, and this only frames it."""
		super().__init__()
		self._source = source
		self.setZValue(10_000)
		self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
		sceneOf = getattr(source, 'scene', None)
		scene: Any = sceneOf() if callable(sceneOf) else None
		if scene is not None and not scene.sceneRect().isEmpty():
			base = QRectF(scene.sceneRect())
		else:
			base = QRectF(source.rect())
		self._base = base
		self.setPos(base.topLeft())

	def boundingRect(self) -> QRectF:
		return QRectF(0, 0, self._base.width(), self._base.height())

	def radarArea(self) -> QRectF:
		"""The square the disc is drawn in: the largest that fits with a margin, centred."""
		rect = self.boundingRect()
		side = max(40.0, min(rect.width(), rect.height()) * (1 - MARGIN * 2))
		return QRectF(rect.center().x() - side / 2, rect.center().y() - side / 2, side, side)

	def paint(self, painter: QPainter, option, widget=None) -> None:
		rect = self.boundingRect()
		painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
		painter.setPen(Qt.PenStyle.NoPen)
		painter.setBrush(QColor(0, 0, 0, 205))
		painter.drawRect(rect)
		self._source.drawRadarInto(painter, self.radarArea())

	def mousePressEvent(self, mouseEvent) -> None:
		if mouseEvent.button() != Qt.MouseButton.LeftButton:
			mouseEvent.ignore()
			return
		area = self.radarArea()
		hit = radar.hitBlip(area, self._source.radarBlips(), self._source.radarTop(), mouseEvent.pos())
		if hit is None:
			self.close()
		else:
			self._source.selectRadarSlot(hit.slot)
			self.update()
		mouseEvent.accept()

	def close(self) -> None:
		"""Take the popover out of the scene; the panel drops its reference to it."""
		scene = self.scene()
		if scene is not None:
			scene.removeItem(self)
		if getattr(self._source, '_overlay', None) is self:
			self._source._overlay = None
