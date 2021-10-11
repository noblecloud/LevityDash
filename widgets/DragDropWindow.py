import logging

from PySide2 import QtGui
from PySide2.QtCore import QMimeData, QTimer
from PySide2.QtGui import QDrag, QDragEnterEvent, QDragMoveEvent, QMouseEvent, Qt
from PySide2.QtWidgets import QMainWindow, QSizeGrip

from widgets.Complication import Complication
from widgets.ComplicationArray import ComplicationArrayGrid, ToolBox
from widgets.ComplicationCluster import ComplicationCluster
from widgets.WidgetBox import Tabs

log = logging.getLogger(__name__)


class DragDropWindow(QMainWindow):
	grid: ToolBox

	def __init__(self, *args, **kwargs):
		super(DragDropWindow, self).__init__(*args, **kwargs)
		c = Tabs(self)
		# c._acceptsDropsOf = ComplicationCluster
		c.setGeometry(self.rect())
		self.setCentralWidget(c)
		c.addPrebuilt()

	def rebuild(self, m, data):
		for group in data:
			cluster = ComplicationCluster(self)
			for location, items in group.items():
				a: ComplicationArrayGrid = getattr(cluster, location)
				for key, value in items.items():
					c = Complication(a, subscriptionKey=key)
					m[value].subscribe(c)
					a.insert(c)
			self.tabs.insert(cluster)
		self.show()

	def dragEnterEvent(self, event: QDragEnterEvent):
		self.hide()

	def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
		# output = f'''Grid: Columns: {self.grid.layout.columnCount()} | Rows: {self.grid.layout.rowCount()} | Length: {len(self.grid._complications)}'''
		# log.debug(output)
		super(DragDropWindow, self).mouseDoubleClickEvent(event)

	@property
	def tabs(self) -> ToolBox:
		return self.centralWidget()
