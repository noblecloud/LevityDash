from datetime import timedelta

from PySide2.QtCore import Qt, Signal
from PySide2.QtGui import QPen, QTransform
from PySide2.QtWidgets import QGraphicsDropShadowEffect, QGraphicsSceneMouseEvent

from LevityDash.lib.ui.frontends.PySide.Modules.Handles.Incrementer import IncrementerGroup, Incrementer

from LevityDash.lib.utils.data import TimeFrameWindow
from LevityDash.lib.utils.geometry import LocationFlag
from LevityDash.lib.ui.frontends.PySide.utils import colorPalette

__all__ = ["GraphZoom", "TimeframeIncrementer"]

"""
Adjusts the scope of a graph
Every Item added to a graph must connect to the action signal and have a slot that accepts an Axis object
FigureRects, Plots, and PeakTroughLists are all connected to this signal
"""


class TimeframeIncrementer(Incrementer):

	def __init__(self, *args, **kwargs):
		super(TimeframeIncrementer, self).__init__(*args, **kwargs)
		self.setVisible(True)
		self.setEnabled(True)

	def toolTip(self) -> str:
		if self.location.isLeft:
			return "Zoom out"
		else:
			return "Zoom in"

	def hoverMoveEvent(self, event) -> None:
		pos = event.pos()
		if pos.x() < 1 or pos.y() < 1:
			self.setToolTip(self.toolTip())
		super(TimeframeIncrementer, self).hoverMoveEvent(event)

	def increase(self):
		self.parent.timeframe.decrease(self.parent.incrementValue)
		self.ensureFramed()
		super(TimeframeIncrementer, self).increase()

	def decrease(self):
		self.parent.timeframe.increase(self.parent.incrementValue)
		self.ensureFramed()
		super(TimeframeIncrementer, self).decrease()

	def ensureFramed(self):
		graph = self.surface
		td = max(f.figureTimeRangeMax for f in graph.figures)
		r = td.total_seconds()/3600*graph.pixelsPerHour
		if r < graph.width():
			graph.timeframe.range = td

	@property
	def _shape(self):
		s = super(TimeframeIncrementer, self)._shape
		T = QTransform()
		T.scale(1.2, 1.2)
		return T.map(s)

	@property
	def position(self):
		return super(TimeframeIncrementer, self).position

	def paint(self, painter, option, widget):
		painter.setPen(QPen(Qt.black, 10))
		painter.drawPath(self._path)
		super(TimeframeIncrementer, self).paint(painter, option, widget)


class GraphZoom(IncrementerGroup):
	handleClass = TimeframeIncrementer
	offset = -40
	locations = [LocationFlag.BottomLeft, LocationFlag.BottomRight]

	def __init__(self, parent: 'Panel', timeframe: TimeFrameWindow, *args, **kwargs):
		self.timeframe = timeframe
		super(GraphZoom, self).__init__(parent=parent, offset=-30, *args, **kwargs)
		self.setVisible(True)
		self.setEnabled(True)

	def _genHandles(self):
		super(GraphZoom, self)._genHandles()

	@property
	def incrementValue(self) -> int:
		days = self.timeframe.rangeSeconds/60/60/24
		if days < 1:
			return timedelta(hours=3)
		elif days < 2:
			return timedelta(hours=6)
		elif days < 5:
			return timedelta(hours=12)
		elif days < 10:
			return timedelta(days=1)
		hour = self.timeframe.rangeSeconds/60/60
		if hour < 24:
			return timedelta(days=1)
		elif hour < 18:
			return timedelta(hours=1)
		elif hour < 12:
			return timedelta(minutes=30)
		elif hour < 6:
			return timedelta(minutes=15)
		else:
			return timedelta(minutes=5)
