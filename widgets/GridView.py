from functools import cached_property
from math import ceil, floor
from typing import Union

from PySide2.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide2.QtGui import QFocusEvent, QMouseEvent, QPainterPath, QTransform
from PySide2.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsSceneContextMenuEvent, QGraphicsSceneMouseEvent, QGraphicsView, QMenu, QOpenGLWidget, QSizePolicy, QVBoxLayout, QWidget
from WeatherUnits import Measurement

from Grid import Grid
from grid.Cell import Cell
from utils import Subscription
from widgets.Complication import Clock, GraphicComplication


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
		proxy = GridViewItem(proxy)
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


class GridViewItem(QGraphicsItem):
	widget: QWidget = None

	handleTopLeft = 1
	handleTopMiddle = 2
	handleTopRight = 3
	handleMiddleLeft = 4
	handleMiddleRight = 5
	handleBottomLeft = 6
	handleBottomMiddle = 7
	handleBottomRight = 8

	handleSize = +8.0
	handleSpace = -4.0

	handleCursors = {
		handleTopLeft:      Qt.SizeFDiagCursor,
		handleTopMiddle:    Qt.SizeVerCursor,
		handleTopRight:     Qt.SizeBDiagCursor,
		handleMiddleLeft:   Qt.SizeHorCursor,
		handleMiddleRight:  Qt.SizeHorCursor,
		handleBottomLeft:   Qt.SizeBDiagCursor,
		handleBottomMiddle: Qt.SizeVerCursor,
		handleBottomRight:  Qt.SizeFDiagCursor,
	}

	def __init__(self, widget=None, *args):
		"""
		Initialize the shape.
		"""
		super().__init__(*args)
		self._rect = QRectF(0, 0, 100, 100)
		self.handles = {}
		self.handleSelected = None
		self.mousePressPos = None
		self.mousePressRect = None
		self.setAcceptHoverEvents(True)
		self.setFlag(QGraphicsItem.ItemIsMovable, True)
		self.setFlag(QGraphicsItem.ItemIsSelectable, True)
		self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
		self.setFlag(QGraphicsItem.ItemIsFocusable, True)
		self._widget = widget
		if self._widget:
			self._widget.setParentItem(self)
			self.setRect()
		self.updateHandlesPos()

		r = self.rect()
		self.setTransformOriginPoint(r.center())

	# r.translate((r.width() - self.handleSize) / 2, (r.height() - self.handleSize) / 2)
	# self.setRect(r)

	def rect(self) -> QRectF:
		return self._rect

	def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
		"""
		Show the context menu.
		"""
		pos = event.screenPos()
		menu = QMenu()
		menu.addAction("Edit")
		delete = menu.addAction("Delete")
		action = menu.exec_(pos)
		if action == delete:
			self.delete()

	def delete(self):
		self.widget.subscription.disconnect()
		self.widget.deleteLater()
		self.scene().parent().parent().grid.cells.remove(self.cell.i)
		i = self.scene().parent().parent().items.index(self)
		self.scene().parent().parent().items.pop(i)
		p = self.scene().parent().parent()
		self.scene().removeItem(self)
		p.buildGrid()

	def handleAt(self, point):
		"""
		Returns the resize handle below the given point.
		"""
		for k, v, in self.handles.items():
			if v.contains(point):
				return k
		return None

	def hoverMoveEvent(self, moveEvent):
		"""
		Executed when the mouse moves over the shape (NOT PRESSED).
		"""
		if self.isSelected():
			handle = self.handleAt(moveEvent.pos())
			cursor = Qt.ArrowCursor if handle is None else self.handleCursors[handle]
			self.setCursor(cursor)
		super().hoverMoveEvent(moveEvent)

	def hoverLeaveEvent(self, moveEvent):
		"""
		Executed when the mouse leaves the shape (NOT PRESSED).
		"""
		self.setCursor(Qt.ArrowCursor)
		super().hoverLeaveEvent(moveEvent)

	def focusInEvent(self, event: QFocusEvent) -> None:
		# self.scene().focusItem().setZValue(1000)
		# self.setZValue(self.zValue() + 1000)
		# self._widget.setZValue(-100)
		self.updateHandlesPos()
		super(GridViewItem, self).focusInEvent(event)

	def focusOutEvent(self, event: QFocusEvent) -> None:
		# self.setZValue(self.zValue() - 1000)
		super(GridViewItem, self).focusOutEvent(event)

	def mousePressEvent(self, mouseEvent):
		"""
		Executed when the mouse is pressed on the item.
		"""
		if mouseEvent.button() == Qt.RightButton and self.isSelected():
			mouseEvent.accept()
			return super().mousePressEvent(mouseEvent)
		else:
			self.setFocus(Qt.FocusReason.MouseFocusReason)
			if self.isSelected():
				self.mousePressPos = mouseEvent.pos()
				self.handleSelected = self.handleAt(mouseEvent.pos())
				if self.handleSelected:
					self.mousePressPos = mouseEvent.pos()
					self.mousePressRect = self.boundingRect()
			return super().mousePressEvent(mouseEvent)

	def mouseMoveEvent(self, mouseEvent):
		"""
		Executed when the mouse is being moved over the item while being pressed.
		"""
		if self.handleSelected is not None:
			self.interactiveResize(mouseEvent.pos())
		else:
			super().mouseMoveEvent(mouseEvent)

	def mouseReleaseEvent(self, mouseEvent):
		"""
		Executed when the mouse is released from the item.
		"""

		super().mouseReleaseEvent(mouseEvent)
		self.handleSelected = None
		self.mousePressPos = None
		self.mousePressRect = None

		pos = self.mapToScene(self.rect().topLeft())
		gridWidth = self.cell.grid.columnWidth
		gridHeight = self.cell.grid.rowHeight

		pos.setX(pos.x() + gridWidth / 2)
		pos.setY(pos.y() + gridHeight / 2)

		col = int(pos.x() / gridWidth)
		row = int(pos.y() / gridHeight)
		index = col + row * self.scene().parent().parent().columns
		# self.cell.grid.cells.pop(self.cell.i)
		# self.cell.grid.cells.insert(0, self.cell)
		if self.cell.grid.cells[index] and self.cell.i != index:
			self.cell.grid.cells.push(index, self.cell.i)
		self.cell.i = index
		self.cell.row = row
		self.cell.col = col
		self.scene().parent().parent().buildGrid()
		rect = QRectF(0, 0, self.cell.width * gridWidth, self.cell.height * gridHeight)
		self.setRect(rect)
		# self.cell.column = round(self.pos().x() / grid.columnWidth)
		# self.cell.row = round(self.pos().y() / grid.rowHeight)
		# self.setPos(round(self.pos().x() / 100) * 100, round(self.pos().y() / 100) * 100)
		# self.scene().parent().parent().buildGrid()
		self.update()

	def boundingRect(self):
		"""
		Returns the bounding rect of the shape (including the resize handles).
		"""
		o = self.handleSize + self.handleSpace
		return self.rect().adjusted(-o, -o, o, o)

	def updateHandlesPos(self):
		"""
		Update current resize handles according to the shape size and position.
		"""
		s = self.handleSize
		b = self.boundingRect()
		self.handles[self.handleTopLeft] = QRectF(b.left(), b.top(), s, s)
		self.handles[self.handleTopMiddle] = QRectF(b.center().x() - s / 2, b.top(), s, s)
		self.handles[self.handleTopRight] = QRectF(b.right() - s, b.top(), s, s)
		self.handles[self.handleMiddleLeft] = QRectF(b.left(), b.center().y() - s / 2, s, s)
		self.handles[self.handleMiddleRight] = QRectF(b.right() - s, b.center().y() - s / 2, s, s)
		self.handles[self.handleBottomLeft] = QRectF(b.left(), b.bottom() - s, s, s)
		self.handles[self.handleBottomMiddle] = QRectF(b.center().x() - s / 2, b.bottom() - s, s, s)
		self.handles[self.handleBottomRight] = QRectF(b.right() - s, b.bottom() - s, s, s)

	def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		offset = self.handleSize + self.handleSpace
		boundingRect = self.boundingRect()
		rect = self.rect()
		diff = QPointF(0, 0)
		toX = -100
		diff.setX(toX)
		# boundingRect.setLeft(toX)
		# boundingRect.setRight(toX)
		rect.setWidth(rect.width() - toX)
		# rect.setWidth(boundingRect.width() + offset)
		self.setPos(self.pos() + diff)
		self.setRect(rect)

		self.updateHandlesPos()

	def interactiveResize(self, mousePos):
		"""
		Perform shape interactive resize.
		"""
		offset = self.handleSize + self.handleSpace
		boundingRect = self.boundingRect()
		rect = self.rect()
		diff = QPointF(0, 0)

		self.prepareGeometryChange()

		if self.handleSelected == self.handleTopLeft:

			fromX = self.mousePressRect.left()
			fromY = self.mousePressRect.top()
			toX = fromX + mousePos.x() - self.mousePressPos.x()
			toY = fromY + mousePos.y() - self.mousePressPos.y()
			diff.setX(toX - fromX)
			diff.setY(toY - fromY)
			boundingRect.setLeft(toX)
			boundingRect.setTop(toY)
			rect.setLeft(boundingRect.left() + offset)
			rect.setTop(boundingRect.top() + offset)
			self.setPos(self.pos() + diff)

		elif self.handleSelected == self.handleTopMiddle:

			fromY = self.mousePressRect.top()
			toY = fromY + mousePos.y() - self.mousePressPos.y()
			diff.setY(toY - fromY)
			boundingRect.setTop(toY)
			rect.setTop(boundingRect.top() + offset)
			self.setPos(self.pos() + diff)

		elif self.handleSelected == self.handleTopRight:
			fromX = self.mousePressRect.right()
			fromY = self.mousePressRect.top()
			toX = fromX + mousePos.x() - self.mousePressPos.x()
			toY = fromY + mousePos.y() - self.mousePressPos.y()
			# diff.setX(toX - fromX)
			diff.setY(toY - fromY)
			boundingRect.setRight(toX)
			boundingRect.setTop(toY)
			rect.setRight(boundingRect.right() - offset)
			rect.setTop(boundingRect.top() + offset)
			self.setPos(self.pos() + diff)
			pos_diff = self.pos() + diff
		# self.setPos(pos_diff.x(), self.pos().y())

		elif self.handleSelected == self.handleMiddleLeft:

			fromX = self.mousePressRect.left()
			toX = fromX + mousePos.x() - self.mousePressPos.x()
			diff.setX(toX - fromX)
			boundingRect.setLeft(toX)
			boundingRect.setRight(-toX)
			rect.setLeft(boundingRect.left() + offset)
			self.setPos(self.pos() + diff)

		elif self.handleSelected == self.handleMiddleRight:
			fromX = self.mousePressRect.right()
			toX = fromX + mousePos.x() - self.mousePressPos.x()
			diff.setX(toX - fromX)
			boundingRect.setRight(toX)
			rect.setRight(boundingRect.right() - offset)

		elif self.handleSelected == self.handleBottomLeft:

			fromX = self.mousePressRect.left()
			fromY = self.mousePressRect.bottom()
			toX = fromX + mousePos.x() - self.mousePressPos.x()
			toY = fromY + mousePos.y() - self.mousePressPos.y()
			diff.setX(toX - fromX)
			diff.setY(toY - fromY)
			boundingRect.setLeft(toX)
			boundingRect.setBottom(toY)
			rect.setLeft(boundingRect.left() + offset)
			rect.setBottom(boundingRect.bottom() - offset)
			pos_diff = self.pos() + diff
			self.setPos(pos_diff.x(), self.pos().y())

		elif self.handleSelected == self.handleBottomMiddle:

			fromY = self.mousePressRect.bottom()
			toY = fromY + mousePos.y() - self.mousePressPos.y()
			diff.setY(toY - fromY)
			boundingRect.setBottom(toY)
			rect.setBottom(boundingRect.bottom() - offset)

		elif self.handleSelected == self.handleBottomRight:

			fromX = self.mousePressRect.right()
			fromY = self.mousePressRect.bottom()
			toX = fromX + mousePos.x() - self.mousePressPos.x()
			toY = fromY + mousePos.y() - self.mousePressPos.y()
			diff.setX(toX - fromX)
			diff.setY(toY - fromY)
			boundingRect.setRight(toX)
			boundingRect.setBottom(toY)
			rect.setRight(boundingRect.right() - offset)
			rect.setBottom(boundingRect.bottom() - offset)

		self.setRect(rect)
		self.updateHandlesPos()

	def setRect(self, rect: QRectF = None, pos: QPointF = None):
		try:
			gridWidth = self.cell.grid.columnWidth
			gridHeight = self.cell.grid.rowHeight
			if rect:
				width, height = rect.size().toTuple()
				self.cell.width = round(width / gridWidth)
				self.cell.height = round(height / gridHeight)
			else:
				width, height = self.rect().size().toTuple()
			rect = QRectF(0, 0, width, height)
			# rect = QRectF(0, 0, self.cell.width * gridWidth, self.cell.height * gridHeight)

			# log.debug(f"col: {x} / {gridWidth} = {x/gridWidth} | row: {y} / {gridHeight} = {y / gridHeight}")
			self._rect = rect
		except AttributeError:
			pass

		if self.childItems():
			rect = self.boundingRect().toRect()
			rect.setSize(rect.size() - QSize(12, 12))
			rect.moveCenter(self.boundingRect().center().toPoint())
			self.childItems()[0].widget().setGeometry(rect)

	def shape(self):
		"""
		Returns the shape of this item as a QPainterPath in local coordinates.
		"""
		path = QPainterPath()
		path.addRect(self.rect())
		if self.isSelected():
			for shape in self.handles.values():
				path.addEllipse(shape)
		return path

	def paint(self, painter, option, widget=None):
		"""
		Paint the node in the graphic view.
		"""
		if self.isSelected():
			for handle, rect in self.handles.items():
				if self.handleSelected is None or handle == self.handleSelected:
					painter.drawEllipse(rect)

	@property
	def widget(self):
		return self._widget.widget()

	@cached_property
	def cell(self):
		return Cell(self)

	def update(self):
		super(GridViewItem, self).update()
		gridWidth = self.cell.grid.columnWidth
		gridHeight = self.cell.grid.rowHeight
		rect = QRectF(0, 0, self.cell.width * gridWidth, self.cell.height * gridHeight)
		self.setRect(rect)
		# self.setRect()
		if self.collidingItems():
			self.setZValue(self.collidingItems()[0].zValue() + 1)
			self.setPos(self.cell.column * gridWidth + 12, self.cell.row * gridHeight + 12)
		self.setPos(self.cell.column * gridWidth, self.cell.row * gridHeight)
		self.widget.update()
		if self.isSelected():
			self.updateHandlesPos()
