from math import ceil, floor
from typing import Union

from PySide2.QtCore import QRect, QRectF, QSize, Qt
from PySide2.QtGui import QMouseEvent, QTransform
from PySide2.QtWidgets import QGraphicsScene, QGraphicsView, QMenu, QOpenGLWidget, QSizePolicy, QVBoxLayout, QWidget
from WeatherUnits import Measurement

from Grid import Grid
from grid.Cell import Cell
from utils import Subscription
from widgets.Complication import Clock, GraphicComplication, GraphicsRectItem


class GridScene(QGraphicsScene):
	columnWidth = 100
	rowHeight = 100

	def mouseMoveEvent(self, event):
		# if event.buttons() == Qt.MouseButton.LeftButton:
		# 	print(self.focusItem())
		super(GridScene, self).mouseMoveEvent(event)

	def mousePressEvent(self, event: QMouseEvent):
		p = self.itemAt(event.scenePos(), QTransform())
		# p.setZValue(p.zValue() + 100)
		print(p)
		super(GridScene, self).mousePressEvent(event)


class GridView(QOpenGLWidget):
	lastColumnCount = 1
	items = []
	_rows = 1
	_columns = 1

	def __init__(self, *args, **kwargs):
		super(GridView, self).__init__(*args, **kwargs)
		self.setLayout(QVBoxLayout(self))
		self.layout().setContentsMargins(0, 0, 0, 0)
		self.layout().setSpacing(0)
		self.layout().setAlignment(Qt.AlignTop)
		self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
		self.graphicsView = QGraphicsView(self)
		self.layout().addWidget(self.graphicsView)
		self.graphicsView.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
		self.graphicsScene = GridScene(self.graphicsView)
		self.graphicsView.setScene(self.graphicsScene)
		self.graphicsView.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
		self.graphicsView.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
		self.grid = Grid(self.graphicsView)

	def showEvent(self, event):
		self.graphicsView.setSceneRect(self.displayRect)
		super(GridView, self).showEvent(event)

	def contextMenuEvent(self, event):
		contextMenu = QMenu(self)
		# newAct = contextMenu.addAction("Insert")
		insertMenu = contextMenu.addMenu('Insert')
		insertMenu.addAction('Graph')
		insertMenu.addAction('Cluster')
		time = insertMenu.addAction('Time')
		openAct = contextMenu.addAction("Open")
		quitAct = contextMenu.addAction("Quit")
		action = contextMenu.exec_(self.mapToGlobal(event.pos()))
		if action == quitAct:
			self.close()
		elif action == time:
			self.insert(Clock)
			self.buildGrid()

	# self.graphicsView.setDragMode(QGraphicsView.ScrollHandDrag)

	def resizeEvent(self, event):
		super(GridView, self).resizeEvent(event)
		# if hasattr(self, 'columnWidth'):
		# 	delattr(self, 'columnWidth')
		# if hasattr(self, 'rowHeight'):
		# 	delattr(self, 'rowHeight')
		if self.lastColumnCount != self.columns:
			if self.rect().width() > 100 and self.isVisible():
				self.buildGrid()
		for item in self.items:
			item.update()
		# item.width = self.columnWidth
		# item.height = self.rowHeight
		# item.setPos(item.cell.column * self.columnWidth, item.cell.row * self.rowHeight)
		# self.buildGrid()

		self.graphicsView.setSceneRect(self.displayRect)

	@property
	def displayRect(self):
		return QRectF(0, 0, self.columns * self.columnWidth, self.rowHeight * self.rows)

	def insert(self, *item: Union[Measurement, str, int, float, QWidget, type], index: int = None, **kwargs):
		for i in item:
			self._insert(i, **kwargs)
		self.show()

	def _insert(self, item, **kwargs):
		complication = self.makeComplication(item, **kwargs)
		self.grid.insert(complication.cell)
		proxy = self.graphicsScene.addWidget(complication)
		proxy = GraphicsRectItem(proxy)
		self.graphicsScene.addItem(proxy)
		self.items.append(proxy)

	@property
	def hasAvailableSpace(self) -> bool:
		return bool(self.empty)

	def buildGrid(self, items: list = None, screen: QRect = None, afterIndex: int = None, clear: bool = True):
		if not (self.height() > 100 or self.width() > 100):
			return

		items = self.grid.cells
		w = self.width()
		h = self.height()

		# columns = min(self.columns, 24)
		# columns = max(9, int(self.width() / 150))
		columns = self.grid.columns

		self.blockScreenSizeWidth = int(w / columns)

		if clear:
			self.empty = set(x for x in range(0, self.columns * self.rows))

		if afterIndex is None:
			i = 0
			it = sorted(items, key=lambda x: x.i)
		else:
			i = afterIndex
			it = items
			# it = sorted([i for i in items if i.cell.i >= afterIndex], key=lambda x: x.cell.i)
			self.empty.update(set().union(*[i.cell.cellSpan(self) for i in it]))

		# it.extend([DummyWidget(self, assume=False)] * int((columns * self.rows) - size))

		def willExceedColumns(item: Cell) -> bool:
			return i + item.width - 1 >= (i // columns * columns) + columns

		# def hasCollisions(cell: Cell) -> bool:
		# 	return span < occupied

		def noSpaceAtIndex(item: Cell, index: int) -> bool:
			return not item.cellSpan(self, index) <= self.empty

		iMax = self.grid.size
		for item in it:

			if item.i is not None:
				i = item.i
			elif self.hasAvailableSpace:
				i = min(self.empty)
			else:
				i = 0

			attempted: set = {i}
			if i < iMax:
				# While item can not fit in space or item would exceed columns
				while (noSpaceAtIndex(item, i) or willExceedColumns(item)) or item.canShrink:

					# add current index to attempted
					if noSpaceAtIndex(item, i):
						attempted.add(i)

					# add the row to attempted
					if willExceedColumns(item):
						attempted |= (item.columnSpan(self, i))

					# jump to the next empty index
					remining = self.empty - attempted
					if remining:
						i = min(remining)
					else:
						if not item.canShrink:
							break
						item.shrink()
						attempted = set([])
						i = min(self.empty - attempted)

				safeSpan = item.cellSpan(self, i)
				self.empty -= safeSpan
				row = i // columns
				col = i % columns

				item.row = row
				item.column = col
				item.i = i

				if self.empty:
					i = min(self.empty)

		for item in self.items:
			item.update()

		self.blockScreenSizeWidth = int(w / columns)
		self.cellSize = QSize(int(w / columns), int(h / self.rows))
		self.lastColumnCount = self.columns

	@property
	def columns(self):
		if self.width() > self.height():
			val = max(1, ceil(len(self.items) / max(1, self.height() // 100)), floor(self.visibleRegion().boundingRect().width() / 100))
			return val

		if self.width() < 170:
			return 1
		return max(1, self._columns, round(self.width() / 100))

	@columns.setter
	def columns(self, value):
		self._columns = value

	@property
	def rows(self):
		if self.width() < self.height():
			# return ceil(len(self.items) / floor(max(1, self.width() / 100)))
			return max(1, ceil(len(self.items) / max(1, self.width() // 100)), round(self.visibleRegion().boundingRect().height() / 100))
		# return max(ceil(len(self.items) / self.columns), ceil(self.height() / 100))
		# return max(1, floor(self.height() / 100))
		# return max(1, round(self.height() / 100), (self.size // self.columns) + (1 if self.size % self.columns else 0))
		return max(1, self._rows, floor(self.height() / 100))

	@rows.setter
	def rows(self, value):
		self._rows = value

	@property
	def rowHeight(self):
		if self.rows <= 2:
			return self.visibleRegion().boundingRect().height() / self.rows
		if self.columns <= 2:
			return self.visibleRegion().boundingRect().width() / self.columns

		return self.visibleRegion().boundingRect().height() / self.rows
		calculated = max(calculated, 90)
		calculated = min(calculated, 120)
		return calculated

	@property
	def columnWidth(self):
		calculated = self.visibleRegion().boundingRect().width() / self.columns
		if self.columns == 1:
			return self.visibleRegion().boundingRect().width()
		# calculated = floor(self.width() / self.columns)
		if self.rows <= 2:
			return self.visibleRegion().boundingRect().height() / self.rows
		calculated = max(calculated, 90)
		calculated = min(calculated, 120)

		return calculated

	def makeComplication(self, item, **kwargs):
		from widgets import Complication, ComplicationPrototype
		localArgs = {'parent': self, 'direction': self.layoutDirection}
		if kwargs is not None:
			localArgs.update(kwargs)
		if isinstance(item, tuple):
			localArgs.update(**item[1])
			item = item[0]

		if isinstance(item, ComplicationPrototype):
			comp = item
			comp.direction = self.layoutDirection
			comp.makeResizable()
			comp.show()
			return comp
		if isinstance(item, type):
			if issubclass(item, Complication):
				item = item(**localArgs)
				item.show()
				item.makeResizable()
				return item
			if issubclass(item, Measurement):
				item = item(0)
		if isinstance(item, Measurement):
			localArgs.update({'title': item.title, 'value': item, 'key': item.key})
		if isinstance(item, Subscription):
			localArgs.update({'subscription': item})
		elif isinstance(item, QWidget):
			localArgs.update({'widget': item})

		comp = GraphicComplication(**localArgs)
		comp.makeResizable()
		comp.show()
		return comp
