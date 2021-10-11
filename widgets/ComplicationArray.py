import logging
from json import dump
from math import ceil, floor, inf, sqrt
from typing import Any, Dict, Optional, Union

from PySide2 import QtGui
from PySide2.QtCore import QPoint, QRect, QSize, QSizeF, Qt, QTimer, Signal, Slot
from PySide2.QtGui import QColor, QDropEvent, QPainter, QPaintEvent, QPen, QShowEvent
from PySide2.QtWidgets import QBoxLayout, QGridLayout, QHBoxLayout, QSizePolicy, QSpacerItem, QVBoxLayout, QWidget
from WeatherUnits import Measurement
from WeatherUnits.base import Measurement

import colors
from src.api import API
from src.grid.Cell import Cell
from src.observations import ObservationRealtime
from src.utils import goToNewYork
from widgets.Complication import Complication
from widgets.DummyWidget import DummyWidget
from widgets.DynamicLabel import DynamicLabel
from widgets.moon import Moon
from widgets.Proto import ComplicationPrototype

log = logging.getLogger(__name__)
log.setLevel(logging.CRITICAL)

NotSet = None

hiddenSizePolicy = QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
displayedSizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
displayedSizePolicy.setRetainSizeWhenHidden(False)


class ComplicationList(list):

	def __init__(self, parent):
		self.parent = parent
		super(ComplicationList, self).__init__([])

	def insert(self, index: int, item: Complication):
		if item.cell.i is None:
			if self:
				item.cell.i = self.parent.nextAvailable
			else:
				item.cell.i = 0
		i = 0
		iI = 0
		if self:
			while iI > index:
				i += i
				iI = self[i].cell.i

		super(ComplicationList, self).insert(i, item)

	def append(self, item: Complication):
		super(ComplicationList, self).append(item)


class ComplicationArray(QWidget):
	_complications: ComplicationList
	_classColor = colors.randomColor()
	_lineWeight = 2
	_layoutDirection = None
	layout: QBoxLayout
	_square: bool = False
	valueChangedSignal = Signal(Complication)
	_balance = True
	startSpacer: QSpacerItem
	endSpacer: QSpacerItem
	debug = False
	placeholder: Optional[DummyWidget] = None
	tempI: int = None
	_acceptsDropsOf: type

	def __init__(self, *args, acceptCluster: bool = False, **kwargs):
		self._complications: list[Optional[Complication]] = ComplicationList(self)
		super(ComplicationArray, self).__init__(*args, **kwargs)
		self.setAcceptDrops(True)
		self.setAttribute(Qt.WA_NoChildEventsForParent)
		self.setAttribute(Qt.WA_NoChildEventsFromChildren)
		if acceptCluster:
			from widgets.ComplicationCluster import ComplicationCluster
			self._acceptsDropsOf = ComplicationCluster
		else:
			self._acceptsDropsOf = Complication
		# self.valueChangedSignal.connect(self.balanceFontSizes)
		self._color = colors.randomColor()
		if self.debug:
			self.setAttribute(Qt.WA_StyledBackground, True)
			self.setStyleSheet(f'background: {self._color}')
		# if not self._complications and not self._forceDisplay:
		# 	self.hide()
		square = self.property("isSquare")
		if square:
			self._square = True

	# s = self.sizePolicy()
	# # s.setRetainSizeWhenHidden(False)
	# self.setSizePolicy(s)

	def paintEvent(self, event: QPaintEvent) -> None:
		if self.debug:
			rect = self.rect()
			pen = QPen(QColor(self._classColor))
			pen.setWidth(self._lineWeight)
			painter = QPainter(self)
			painter.setPen(pen)
			painter.drawRect(rect)

			for i in range(self.columns):
				for j in range(self.rows):
					x = i * self.columnWidth + (self.columnWidth / 2)
					y = j * self.rowHeight - (self.rowHeight / 2)
					value = (i * j) + j
					painter.drawText(QPoint(x, y - 10), f'{i}, {j}')
					painter.drawText(QPoint(x, y + 10), f'{value}')

		super(ComplicationArray, self).paintEvent(event)

	def setMargins(self):
		self.layout.setContentsMargins(0, 0, 0, 0)
		self.layout.setSpacing(0)

	@property
	def isVertical(self) -> bool:
		return self.layout.direction() < 1

	@property
	def nextAvailable(self):
		if self.empty:
			return min(self.empty)
		return len(self._complications)

	@property
	def isEmpty(self):
		return not bool([item for item in self._complications if item is not None and not isinstance(item, DummyWidget)])

	@property
	def blockSize(self) -> QSizeF:
		return QSize(self.columnWidth, self.rowHeight)

	def locationFromPoint(self, point: QPoint, itemSize: QSize = None) -> tuple[int, int, int]:
		"""
		Returns column, row, and index of grid given a point within the frame
		:param point: QPoint location within grid
		:type point: QPoint
		:pram itemSize: Size of item being dragged for preventing column overflow
		:type itemSize: QSize
		:return:
			- col - Column
			- row - Row
			- i - Index within  array, self.items
		:rtype: tuple[int, int, int]
		"""
		# if self._complications:
		x = point.x()
		y = point.y()
		if itemSize:
			x -= itemSize.width() / 2 - self.columnWidth / 2
			y -= itemSize.height() / 2 - self.rowHeight / 2
			x = min(self.width() - itemSize.width() + self.columnWidth, x)
			y = min(self.height() - itemSize.height() + self.rowHeight, y)
		col = floor(x / (self.width() / self.columns))
		row = floor(y / (self.height() / self.rows))
		i = (self.columns * row) + col
		col = max(min(col, self.columns), 0)
		row = max(min(row, self.rows), 0)
		i = max(min(i, self.size), 0)
		return col, row, i

	def balanceFontSizes(self):
		if self.balance:
			complicationsOnly = list(item for item in self._complications if isinstance(item, ComplicationPrototype) and item.canBalance)
			if complicationsOnly:
				maxValueSize = list(item.maxFontSize for item in complicationsOnly)
				heights = list(item.valueLabel.localY for item in complicationsOnly if item.valueLabel.localY is not None and item.valueLabel.isVisible())
				maxTitleSize = list(item.maxFontSizeTitle for item in complicationsOnly if isinstance(item.titleLabel, DynamicLabel) and item.titleLabel.isVisible())
				if maxTitleSize:
					minVal = min(maxTitleSize)
					avVale = sum(maxTitleSize) / len(maxValueSize)
				if maxValueSize:
					minVall = min(maxValueSize)
					avValel = sum(maxValueSize) / len(maxValueSize)
				for comp in complicationsOnly:
					if maxValueSize:
						comp.valueLabel.setSharedFontSize(avValel)
					if maxTitleSize:
						comp.titleLabel.setSharedFontSize(avVale)
			# if heights:
			# 	comp.valueLabel.sharedHeight = (min(heights))
			else:
				pass

	def dragEnterEvent(self, event: QtGui.QDragEnterEvent):
		self.placeholder = DummyWidget(self, assume=event.source())
		if isinstance(event.source(), self._acceptsDropsOf):
			event.accept()
			self.placeholder.setParent(self)
			# clickedLocal = event.source().mapFrom(self, event.pos())
			# offset = clickedLocal - event.source().rect().topLeft()
			col, row, self.tempI = self.locationFromPoint(event.pos())
			self.gridLayout.addWidget(self.placeholder, row, col, self.placeholder.cell.h, self.placeholder.cell.w)
			# self.plop(self.placeholder, self.tempI)
			log.debug(f'Accepted drop of {type(event.source())}')
		elif isinstance(event.source(), Complication):
			event.accept()
		else:
			event.ignore()

	# self.placeholder = DummyWidget(event.source())

	# super(ComplicationArray, self).dragEnterEvent(event)

	def dragMoveEvent(self, event: QtGui.QDragMoveEvent):
		# if not self.isEmpty and isinstance(event.source(), self._acceptsDropsOf):
		# clickedLocal = event.source().mapFrom(self, event.pos())
		# offset = clickedLocal - event.source().rect().topLeft()
		# col, row, i = self.locationFromPoint(event.pos() - offset)

		col, row, i = self.locationFromPoint(event.pos(), event.source().geometry().size())
		print(f'\r{col}, {row}, {i}', end='')
		if self.tempI != i:
			self.tempI = i
			# self.pluck(self.placeholder, orphan=False)
			# self.plop(self.placeholder, i, update=False)
			self.gridLayout.removeWidget(self.placeholder)
			self.gridLayout.addWidget(self.placeholder, row, col, self.placeholder.cell.h, self.placeholder.cell.w)
		super(ComplicationArray, self).dragMoveEvent(event)

	def dragLeaveEvent(self, event: QtGui.QDragLeaveEvent):
		# log.debug(f'Left {self}')
		self.placeholder.kill()
		from widgets.ComplicationCluster import ComplicationCluster
		if isinstance(self.parent(), ComplicationCluster):
			self.parent().hideAll()
		try:
			# self.yank(self.placeholder)
			self.gridLayout.removeWidget(self.placeholder)
		# self.placeholder.kill()
		except Exception:
			pass
		super(ComplicationArray, self).dragLeaveEvent(event)

	def dropEvent(self, event: QDropEvent) -> None:
		self.layout.removeWidget(self.placeholder)
		self.placeholder.kill()

		if isinstance(event.source(), self._acceptsDropsOf):
			log.debug(f'Dropping {event.source()} into {self}')
			self.layout.replaceWidget(self.placeholder, event.source())
			self.placeholder.hide()
			# self.layout.removeWidget(self.placeholder)
			self.plop(event.source(), self.tempI, afterIndex=self.tempI)
			event.source().makeResizable()
			event.accept()
			event.source().show()
		elif isinstance(event.source(), Complication):
			if self.childAt(event.pos() - event.mimeData().offset) is None:
				log.debug(f'Dropping {event.source()} building new cluster')
				from widgets.ComplicationCluster import ComplicationCluster
				new = ComplicationCluster(self)
				new.center.insert(event.source())
				self.insert(new)
				self.buildGrid(afterIndex=self.tempI)
		else:
			event.cancel()

		self.placeholder = None
		super(ComplicationArray, self).dropEvent(event)

	def insert(self, *item: Union[Measurement, str, int, float, QWidget, type], index: int = None, **kwargs):
		inserted = []
		if isinstance(item[0], list):
			item = tuple(item[0])
		if isinstance(item, tuple):
			for i in item:
				complication = self.makeComplication(i, **kwargs)
				inserted.append(complication)
				self.layout.addWidget(complication)
				self.insertIntoArray(complication, index=index)
				index = index + 1 if index else None
		else:
			complication = self.makeComplication(item, **kwargs)
			inserted.append(complication)
			self._complications.append(inserted)
		# self.layout.addWidget(complication)
		# self.insertIntoArray(complication, index)
		self.show()
		# self.update()
		return inserted

	def insertIntoArray(self, comp, index):
		if index is NotSet:
			# log.debug('Index not provided, finding empty location')
			try:
				firstOpenIndex = self._complications.index(None)
				self._complications.insert(firstOpenIndex, comp)
			except ValueError:
				# log.debug('No empty locations found, adding to end')
				self._complications.append(comp)
		else:
			message = f'Inserting with index {index}'
			if len(self._complications) > index:
				if self._complications[index] is None:
					log.debug(f'{message} in an empty location')
					self._complications[index] = comp
				else:
					log.debug(f'P{message} before {self._complications[index]}')
					self._complications.insert(index, comp)
				return comp
			else:
				x = [*self._complications, *[*[None] * (index - len(self._complications))]]
				self._complications.append(comp)
				log.debug(f'index was larger than list')
			pass

	def autoShow(self):
		if self.isEmpty:
			self.hide()
		else:
			self.show()

	def showEvent(self, event) -> None:
		self.setSizePolicy(displayedSizePolicy)
		super(ComplicationArray, self).showEvent(event)

	def hideEvent(self, event) -> None:
		self.setSizePolicy(hiddenSizePolicy)
		super(ComplicationArray, self).hideEvent(event)

	def localSwap(self, a: Complication, b: Complication):
		c = self._complications
		i = c.index(a)
		j = c.index(b)
		c[i], c[j] = c[j], c[i]
		self.update()

	def getIndexItem(self, position, expectedClass: type = None) -> tuple[int, Complication]:
		try:
			item = self.childAt(position)
			return self._complications.index(item), item
		except ValueError as e:
			foundItems = []
			possibleItem = item
			if expectedClass is not None:
				while possibleItem is not None and not isinstance(possibleItem, expectedClass):
					foundItems.append(possibleItem)
					possibleItem = possibleItem.parent()
			else:
				log.error(f'The provided position did not yield a child within the array.  Found: {foundItems}')
				raise e
			item = possibleItem
		return self._complications.index(item), item

	# def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
	# 	if event.sourceParent

	def yank(self, item):
		self.pluck(item)
		item.parent().update()
		item.setParent(None)
		item.hide()
		item.deleteLater()

	def pluck(self, item: Complication, orphan: bool = True) -> tuple[int, Complication]:
		i = self._complications.index(item)
		child = self._complications[i]
		self._complications.pop(i)
		if orphan:
			self.layout.removeWidget(child)
		return i, child

	def abandon(self, item: Complication):
		try:
			i = self._complications.index(item)
			self._complications.pop(i)
			item.hide()
			return i
		except ValueError:
			return None

	def plop(self, item, i, update: bool = True, afterIndex: bool = False):
		i = max(0, i)
		item.setParent(self)
		self._complications.insert(i, item)
		try:
			item.makeResizable()
		except AttributeError:
			pass
		item.cell.i = i
		if update:
			self.update()
		if afterIndex:
			self.buildGrid(afterIndex=i)

	def makeComplication(self, item, **kwargs):
		localArgs = {'parent': self, 'direction': self.layoutDirection}
		if kwargs is not None:
			localArgs.update(kwargs)
		if isinstance(item, tuple):
			localArgs.update(**item[1])
			item = item[0]

		if isinstance(item, ComplicationPrototype):
			comp = item
			comp.setParent(self)
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
			localArgs.update({'title': item.title, 'value': item, 'subscriptionKey': item.subscriptionKey})
		elif isinstance(item, QWidget):
			localArgs.update({'widget': item})

		comp = Complication(**localArgs)
		comp.makeResizable()
		return comp

	def replace(self, items: Union[list[Measurement], Measurement]):
		self.clear()
		self.insert(items)

	def hit(self, sender, position):
		values = (item.hit(sender, position) for item in self._complications if hasattr(item, 'hit'))
		return any(x[0] for x in values), any(x[1] for x in values)

	def inHitBox(self, sender, position):
		return self.geometry().contains(self.mapFrom(sender, position))

	def clear(self):
		while self.layout.count():
			child = self.layout.takeAt(0)
			if child.widget():
				child.widget().deleteLater()

	@property
	def layout(self):
		return super().layout()

	@property
	def layoutDirection(self):
		return self._layoutDirection

	@property
	def complications(self):
		return [*[x for x in self._complications if not hasattr(x, 'complications')], *[l for y in [x.complications for x in self._complications if hasattr(x, 'complications')] for l in y]]

	@property
	def state(self):
		return [item.state for item in self._complications]

	@property
	def balance(self):
		return self._balance

	@balance.setter
	def balance(self, value):
		self._balance = value

	@property
	def layoutDirection(self):
		if self.parent() is not None:
			return QVBoxLayout.TopToBottom if self.parent().height() / 2 < self.pos().y() else QVBoxLayout.BottomToTop
		else:
			return QVBoxLayout.TopToBottom

	@property
	def square(self):
		return self._square

	@square.setter
	def square(self, value):
		self._square = value


class ComplicationArrayGrid(ComplicationArray):
	lastColumnCount: int = 1
	cellSize: QSize
	blockScreenSizeWidth: int
	lastGoodWidth: int
	_layoutDirection = QVBoxLayout.TopToBottom
	layout: QGridLayout
	_columns: int = 1
	_rows: int = 1

	# _square: bool = True

	def __init__(self, *args, **kwargs):
		super(ComplicationArrayGrid, self).__init__(*args, **kwargs)
		self.empty: set = set(x for x in range(0, self.size))
		square = self.property("isSquare")
		self.gridLayout = QGridLayout(self)
		self.setMargins()
		self.setLayout(self.gridLayout)
		self.lastGoodWidth = self.width()
		self.blockScreenSizeWidth = 0
		# self.setContentsMargins(0, 0, 0, 0)
		self.gridLayout.setSpacing(0)
		if square:
			self._square = True

	# def setWidgets(self):
	# 	while len(self._complications) > 1 and not self._complications[-1]:
	# 		self._complications.pop()
	# 	# s = ceil(sqrt(len(self._complications)))
	# 	if self._complications:
	# 		self.layout.buildGrid()
	# 		# while self.layout.count():
	# 		# 	child = self.layout.takeAt(0)
	# 		# val = 60
	# 		# short = self._complications
	# 		# size = sqrt(self.width() * self.height() / len(short))
	# 		# maxWidth = self.width() / len(short)
	# 		# maxHeight = self.height() / len(short)
	# 		# h = self.height()
	# 		# w = self.width()
	# 		# if 0.9 < w/h < 1.3:
	# 		# 	s = ceil(sqrt(val))
	# 		# else:
	# 		# if size:
	# 		# 	s = ceil(self.width() / size)
	# 		# 	f = ceil(s / 2)
	# 		# 	g = f
	# 		#
	# 		# 	while s - (len(short) % s) > len(short) // s and (w/h) < 3:
	# 		# 		s -= 1
	# 		# 	lowest = (w / s) / (h / ceil(len(short) / s))
	# 		# 	if w/h > 1.8:
	# 		# 		for i in range(f, s + f):
	# 		# 			if len(short) % i == 0:
	# 		# 				s = i
	# 		# 	for i in range(f, s + f):
	# 		# 		g = (w / s) / (h / ceil(len(short) / s))
	# 		# 		s = i if g > lowest else s
	# 		# 	if w/h < .5:
	# 		# 		for i in range(1, s + f):
	# 		# 			g = (w / i) / (h / ceil(len(short) / i))
	# 		# 			s = i if g > lowest else s
	# 		# else:
	# 		# 	s = 1
	# 		# if len(short) % s - 1 == 0:
	# 		# 	print(f's')
	# 		# 	s += 1
	#
	# 			# print(f'\r{s}: {w}', end='')
	# 		# s = min((self.width() / minSize), (self.height() / minSize))
	# 		# else:
	# 		# for i, widget in enumerate(self._complications):
	# 		# occupied = []
	# 		# col, row = 0, 0
	# 		# toPlace = short.copy()
	# 		# i = 0
	# 		# while toPlace:
	# 		# 	i+=1
	# 		# 	size = 2 if i == 0 else 1
	# 		# 	row = i // s
	# 		# 	col = i % s
	# 		# 	o = []
	# 		# 	if size:
	# 		# 		for r in range(0, size + 1):
	# 		# 			for c in range(0, size + 1):
	# 		# 				o.append((s * (r - 1)) + c)
	# 		# 	occupied.append(o)
	# 		# 	widget = toPlace.pop(0)
	# 		# 	self.layout.addWidget(widget, row, col, size, size)
	# 		# self.columnCount = s
	# 		# self.rowCount = ceil(len(short) / s)
	#
	#
	# 				# 	row = i // s
	# 				# 	col = i % s
	# 				# 	if widget is not None:
	# 				# self.layout.addWidget(widget, row, col)
	# 				# # widget.setMinimumWidth(minSize)
	# 				# widget.setMaximumHeight(minSize)
	# 				# widget.setMaximumWidth(minSize)
	# 				# widget.update()
	# 		self.show()

	def update(self):
		self.buildGrid()
		# self.balanceFontSizes()
		super(ComplicationArrayGrid, self).update()

	@property
	def items(self):
		return self._complications

	@items.setter
	def items(self, value):
		self._complications = value

	def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
		if event.oldSize().width() > self.rect().size().width() or event.oldSize().width() == -1:
			self.empty = set(x for x in range(0, self.size))
			self.buildGrid()

		# 	# if self.items and self.columns != self.lastColumnCount:
		# 	# 	print('size out of bounds')
		# 	self.buildGrid(self._complications)
		super(ComplicationArrayGrid, self).resizeEvent(event)

	@property
	def size(self) -> int:
		# return sum([x.cell.size for x in self._complications])
		return self.columns * self.rows

	def showEvent(self, event: QShowEvent) -> None:
		self.buildGrid()
		super().showEvent(event)

	@property
	def hasAvailableSpace(self) -> bool:
		return bool(self.empty)

	def buildGrid(self, items: list = None, screen: QRect = None, afterIndex: int = None, clear: bool = True):
		print('buildGrid')
		items = self.items
		w = self.width()
		h = self.height()

		# columns = min(self.columns, 24)
		# columns = max(9, int(self.width() / 150))
		columns = self.columns

		self.blockScreenSizeWidth = int(w / columns)

		if clear:
			self.empty = set(x for x in range(0, self.size))

		if afterIndex is None:
			i = 0
			it = items
		else:
			i = afterIndex
			it = sorted([i for i in items if i.cell.i >= afterIndex], key=lambda x: x.cell.i)
			self.empty.update(set().union(*[i.cell.cellSpan(self) for i in it]))

		# it.extend([DummyWidget(self, assume=False)] * int((columns * self.rows) - size))

		def willExceedColumns(cell: Cell) -> bool:
			return i + item.cell.w - 1 >= (i // columns * columns) + columns

		# def hasCollisions(cell: Cell) -> bool:
		# 	return span < occupied

		def noSpaceAtIndex(cell: Cell, index: int) -> bool:
			return not item.cell.cellSpan(self, index) <= self.empty

		iMax = self.columns * self.rows
		for item in it:

			if item.cell.i is not None:
				i = item.cell.i
			elif self.hasAvailableSpace:
				i = min(self.empty)
			else:
				i = 0

			attempted: set = {i}
			if i < iMax:
				# While item can not fit in space or item would exceed columns
				while (noSpaceAtIndex(item.cell, i) or willExceedColumns(item.cell)) or item.cell.canShrink:

					# add current index to attempted
					if noSpaceAtIndex(item.cell, i):
						attempted.add(i)

					# add the row to attempted
					if willExceedColumns(item.cell):
						attempted |= (item.cell.columnSpan(self, i))

					# jump to the next empty index
					remining = self.empty - attempted
					if remining:
						i = min(remining)
					else:
						print('shrink')
						if not item.cell.canShrink:
							break
						item.cell.shrink()
						attempted = set([])
						i = min(self.empty - attempted)

				safeSpan = item.cell.cellSpan(self, i)
				self.empty -= safeSpan
				row = i // columns
				col = i % columns
				if self.empty:
					i = min(self.empty)
				x = item.cell.h
				y = item.cell.w

				# self.gridLayout.addWidget(item, row, col, item.cell.w, item.cell.h)
				self.gridLayout.addWidget(item, row, col, item.cell.h, item.cell.w)
		self.blockScreenSizeWidth = int(w / columns)
		self.cellSize = QSize(int(w / columns), int(h / self.rows))
		self.lastColumnCount = self.columns

	# @property
	# def columns(self):
	# 	def columnNumberAlgorithm():
	# 		# averageCellSize = sqrt(self.width() * self.height() / self.size)
	# 		# s = round(self.width() / averageCellSize)
	# 		# s = round(sqrt(size))
	# 		s = self.width() / 150
	# 		return s
	# 	return self._columns if not None else columnNumberAlgorithm()

	@property
	def columns(self):
		return max(1, self._columns, round(self.width() / 100))

	@columns.setter
	def columns(self, value):
		self._columns = value

	@property
	def rows(self):
		# return max(1, round(self.height() / 100), (self.size // self.columns) + (1 if self.size % self.columns else 0))
		return max(1, self._rows, round(self.height() / 100))

	@rows.setter
	def rows(self, value):
		self._rows = value

	@property
	def rowHeight(self):
		return round(self.height() / self.rows)

	@property
	def columnWidth(self):
		return round(self.width() / self.columns)


class WidgetBox(ComplicationArrayGrid):
	layout: QGridLayout

	def __init__(self, *args, **kwargs):
		super(WidgetBox, self).__init__(*args, **kwargs)
		self._acceptsDropsOf = ComplicationPrototype

	def dropEvent(self, event):
		super(WidgetBox, self).dropEvent(event)
		event.source().makeResizable()

	def buildGrid(self, *args, **kwargs):
		super(WidgetBox, self).buildGrid(*args, **kwargs)
		self.setMinimumHeight(self.rows * 100 + 30)

		for x in range(0, self.rows):
			self.gridLayout.setRowMinimumHeight(x, self.rowHeight)
		for x in range(self.rows, self.gridLayout.rowCount()):
			self.gridLayout.setRowMinimumHeight(x, 0)

		for x in range(0, self.columns):
			self.gridLayout.setColumnMinimumWidth(x, self.columnWidth)
		for x in range(self.columns, self.gridLayout.columnCount()):
			self.gridLayout.setColumnMinimumWidth(x, 0)


class ClusterGrid(WidgetBox):
	tempSize: QSize = None
	debug = True
	hiddenSize: QSize = QSize(0, 0)

	_classColor: QColor = colors.randomColor()
	_lineWeight: int = 3

	def __init__(self, *args, **kwargs):
		super(ClusterGrid, self).__init__(*args, **kwargs)
		self._color = colors.randomColor()

	# if self.debug:
	# 	self.setAttribute(Qt.WA_StyledBackground, True)
	# 	x = f'''
	# 			background: {self._color};
	# 			border-width: {self._lineWeight};
	#             border-style: solid;
	#             border-color: {self._classColor};
	#             '''
	# 	self.setStyleSheet(x)

	@property
	def columns(self):
		if len(self._complications) > 1:
			return min(super(ClusterGrid, self).columns, len(self._complications))
		return 1

	@property
	def rows(self):
		if len(self._complications) > 1:
			return min(super(ClusterGrid, self).rows, len(self._complications) // self.columns)
		return 1

	@property
	def rowHeight(self):
		return int((self.height()) / self.rows)

	@property
	def columnWidth(self):
		return int(self.width() // self.columns)

	def dragEnterEvent(self, event):
		if self.isEmpty:
			w = self.columns
			h = self.rows
		else:
			w = 1
			h = 1
		event.source().cell.resize(w, h)
		super(ClusterGrid, self).dragEnterEvent(event)

	def dragLeaveEvent(self, event):
		super(ClusterGrid, self).dragLeaveEvent(event)
		self.parent().hideEmpty()

	def dropEvent(self, event):
		super(ClusterGrid, self).dropEvent(event)
		self.parent().hideEmpty()
		self.show()

	def hide(self):
		if self.isEmpty:
			super().hide()
		else:
			pass


class ClusterGridCenter(ClusterGrid):
	displayedNeighbor: ClusterGrid
	_neighbors: list[ClusterGrid] = None
	dropZone: QRect = QRect(0, 0, 0, 0)

	def __init__(self, *args, **kwargs):
		super(ClusterGridCenter, self).__init__(*args, **kwargs)
		self._displayedNeighbor = self
		self._updateDropZone()

	def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
		self._updateDropZone()

	def _updateDropZone(self):
		r = self.rect()
		self.dropZone.setWidth(r.width() - 60)
		self.dropZone.setHeight(r.height() - 60)
		self.dropZone.moveCenter(r.center())

	def dragEnterEvent(self, event):
		# self.parent().hideEmpty()
		print('hide Empty')
		e = self.edges
		n = self.neighbors

		for edge, neighbor in zip(e, n):
			if neighbor.isEmpty:
				r = neighbor.rect()
				r.moveCenter(edge)
				neighbor.setGeometry(r)

		super(ClusterGridCenter, self).dragEnterEvent(event)

	@property
	def neighbors(self) -> list[ClusterGrid]:
		if self._neighbors is None:
			self._neighbors = self.parent().allWidgets.copy()
			self._neighbors.pop(4)
		return self._neighbors

	def dragMoveEvent(self, event):
		p = event.pos()
		n = self.neighbors
		d = self.displayedNeighbor
		v = any([not x.isHidden() for x in n if x is not self._displayedNeighbor])
		if not self.dropZone.contains(p):
			selection = sorted(self.neighbors, key=lambda widget: goToNewYork(widget, event.pos()))[0]
			if selection is not self.displayedNeighbor:
				self.displayedNeighbor = selection
		elif self.displayedNeighbor is not self:
			self.displayedNeighbor = self
		else:
			pass
		super(ClusterGrid, self).dragMoveEvent(event)

	def dragLeaveEvent(self, event):
		# pass
		super(ClusterGrid, self).dragLeaveEvent(event)
		self.parent().hideEmpty(self.displayedNeighbor)
		self.displayedNeighbor.show()

	@property
	def displayedNeighbor(self):
		return self._displayedNeighbor

	@displayedNeighbor.setter
	def displayedNeighbor(self, value):
		hiding = self._displayedNeighbor.objectName()
		showing = value.objectName()
		print(f'hiding {hiding} and showing {showing}')
		self._displayedNeighbor.hide()
		self._displayedNeighbor = value
		self._displayedNeighbor.show()

	def hide(self):
		pass

	@property
	def edges(self):
		# parent = self.parent()
		r = self.parent().rect()
		center = r.center()
		top = QPoint(center)
		top.setY(r.top())
		bottom = QPoint(center)
		bottom.setY(r.bottom())
		left = QPoint(center)
		left.setX(r.left())
		right = QPoint(center)
		right.setX(r.right())
		# [self.topLeft, self.topArray, self.topRight,
		#  self.leftArray, self.center, self.rightArray,
		#  self.bottomLeft, self.bottomArray, self.bottomRight]
		return [r.topLeft(), top, r.topRight(),
		        left, right,
		        r.bottomLeft(), bottom, r.bottomRight()]


class MainBox(WidgetBox):

	def __init__(self, *args, **kwargs):
		super(MainBox, self).__init__(*args, **kwargs)

		self.autoSaveTimer = QTimer(self)
		self.autoSaveTimer.setTimerType(Qt.TimerType.VeryCoarseTimer)
		self.autoSaveTimer.setInterval(300000)  # Every five minutes
		self.autoSaveTimer.timeout.connect(self.save)
		# self.autoSaveTimer.start()

		self.saveTimer = QTimer(self)
		self.saveTimer.setInterval(2000)
		self.saveTimer.timeout.connect(self.save)

	def dropEvent(self, event):
		super(MainBox, self).dropEvent(event)
		print(self.state)

	# def buildGrid(self, *args, **kwargs):
	# 	super(MainBox, self).buildGrid(*args, **kwargs)
	# 	self.saveTimer.start()

	def save(self):
		self.saveTimer.stop()
		if self.state:
			with open('save.json', 'w') as fo:
				print(self.state)
				dump(self.state, fo)


class ToolBox(WidgetBox):
	_name: str = None
	_api: Optional[API]

	def __init__(self, parent, api: API = None, *args, **kwargs):
		super(ToolBox, self).__init__(parent, *args, **kwargs)
		self._api = api
		self.keys = {}
		if self._api is not None:
			self._api.realtime.updateHandler.newKey.connect(self.addMeasurement)
			x = [item for item in self._api.realtime.values()]
			self.insert(x)

		self._acceptsDropsOf = None
		self.setAcceptDrops(False)

	def pluck(self, item: Complication, orphan: bool = True) -> tuple[int, Complication]:
		i = self._complications.index(item)
		child = self._complications[i].copy()
		return i, child

	def insert(self, *args, **kwargs):
		inserted = super(ToolBox, self).insert(api=self.api, *args, **kwargs)
		for item in inserted:
			self.keys.update({item.subscriptionKey: item})
		return inserted

	@Slot(str, Measurement)
	def addMeasurement(self, measurement: Measurement):
		if isinstance(measurement, Measurement):
			insert = self.insert(measurement)
		else:
			self.insert(measurement)

	@property
	def name(self):
		return self._name

	@name.setter
	def name(self, value):
		self._name = value

	@property
	def api(self) -> Optional[API]:
		return self._api

	@api.setter
	def api(self, value: API):
		self._api = value
