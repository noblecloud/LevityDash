from functools import cached_property
from math import sqrt
from typing import Iterable, List, Optional, overload, Union, TYPE_CHECKING, Callable

import numpy as np
from math import ceil, floor
from PySide6.QtCore import QObject, QPoint, QPointF, QRectF, Signal
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsScene, QWidget

from ..Geometry import Geometry
from LevityDash.lib.utils.shared import clearCacheAttr, ColorStr
from . import Position, Size, MultiDimension, log

__all__ = ['Grid', 'GridItems', 'GridItem']

if TYPE_CHECKING:
	from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel


class GridItemSize(Size):
	pass


class GridItemPosition(Position, dimensions=('column', 'row')):
	index: Optional[int] = None

	def __init__(self, *args: int, grid: 'Grid' = None):
		if isinstance(args[0], GridItemPosition):
			super(GridItemPosition, self).__init__(args[0].column, args[0].row)
		elif isinstance(args[0], Iterable):
			args = args[0]
		if len(args) == 1:
			if grid is None:
				raise ValueError('Grid must be specified when passing index')
			self.index = args[0]
			column, row = self.index%grid.columns, self.index//grid.columns
		else:
			column, row = args[0], args[1]

		if grid is not None:
			self.index = row*grid.columns + column
		super().__init__(column, row)


class GridItem:
	__slots__ = ['geometry', '_grid', '_i', '_column', '_row', '__column', '__row', '_width', '_height']
	surface: 'Panel'
	geometry: 'Geometry'
	grid: 'Grid'
	i: int
	column: int
	row: int
	width: int
	height: int
	_grid: 'Grid'
	_i: int
	_column: int
	__column: int
	_row: int
	__row: int
	_width: int
	_height: int
	_widthRatio: float
	_heightRatio: float

	def __init__(self,
		geometry: 'Geometry',
		grid: 'Grid' = None,
		i: int = None,
		column: int = None,
		row: int = None,
		width: int = None,
		height: int = None,
		**kwargs):
		self.__column = None
		self._column = None
		self.__row = None
		self._row = None
		self._grid = None
		if isinstance(geometry, GridItem):
			self.grid = geometry.grid
			i = geometry.i
			column = geometry.column
			row = geometry.row
			height = geometry.height
			width = geometry.width
			geometry = geometry.geometry

		self.geometry = geometry
		self.i = i
		# if grid is None and hasattr(self.surface, 'parentGrid'):
		# 	grid = self.surface.parentGrid
		# self.grid = grid
		if 'location' in kwargs:
			column, row = self.__parseLocation(kwargs['location'])
		self.column = column
		self.row = row
		if 'size' in kwargs:
			height, width = self.__parseSize(kwargs['size'])

		if width is None:
			try:
				self.absoluteWidth = self.surface.rect().width()
			except RuntimeError:
				self.width = 1
			except AttributeError:
				self.width = 1
		elif isinstance(width, dict):
			absolute = width.get('absolute', False)
			if absolute:
				self.absoluteWidth = width['value']
			else:
				self.relativeWidth = width['value']
		else:
			self.width = width

		if height is None:
			try:
				self.absoluteHeight = self.surface.rect().height()
			except RuntimeError:
				self.height = 1
			except AttributeError:
				self.height = 1
		elif isinstance(height, dict):
			absolute = height.get('absolute', False)
			if absolute:
				self.absoluteHeight = height['value']
			else:
				self.relativeHeight = height['value']
		else:
			self.height = height

	def __eq__(self, other):
		if isinstance(other, dict):
			try:
				other = GridItem(**other)
			except TypeError:
				raise TypeError('Cannot compare GridItem with {}'.format(type(other)))
		if isinstance(other, GridItem):
			i = self.i == other.i
			column = self.column == other.column
			row = self.row == other.row
			width = self.width == other.width
			height = self.height == other.height
			surface = self.surface == other.surface
			return i and column and row and width and height and surface
		raise TypeError('Cannot compare GridItem with {}'.format(type(other)))

	def __repr__(self) -> str:
		i = f'({self.i})' if self._i is not None else self.i
		col = f'({self.column})' if self._column is not None else self.column
		row = f'({self.row})' if self._row is not None else self.row
		w = f'({self.width})' if self._width is not None else self.width
		h = f'({self.height})' if self._height is not None else self.height
		return f'GridItem_{self.surface.uuidShort}(i={i}, column={col}, row={row}, width={w}, height={h}'

	def __str__(self) -> str:
		i = ColorStr.bold(f'{self.i}') if self._i is not None else self.i
		col = ColorStr.bold(f'{self.column}') if self._column is not None else self.column
		row = ColorStr.bold(f'{self.row}') if self._row is not None else self.row
		w = ColorStr.bold(f'{self.width}') if self._width is not None else self.width
		h = ColorStr.bold(f'{self.height}') if self._height is not None else self.height
		return f'GridItem(i={i}, column={col}, row={row}, width={w}, height={h}'

	def __gt__(self, other):
		if isinstance(other, GridItem):
			return self.i > other.i
		raise TypeError('Cannot compare GridItem with {}'.format(type(other)))

	def __lt__(self, other):
		if isinstance(other, GridItem):
			return self.i < other.i
		raise TypeError('Cannot compare GridItem with {}'.format(type(other)))

	def __le__(self, other):
		if isinstance(other, GridItem):
			return self.i <= other.i
		raise TypeError('Cannot compare GridItem with {}'.format(type(other)))

	def __ge__(self, other):
		if isinstance(other, GridItem):
			return self.i >= other.i
		raise TypeError('Cannot compare GridItem with {}'.format(type(other)))

	def __ne__(self, other: 'GridItem') -> bool:
		return not self.__eq__(other)

	def __parseSize(self, size):
		if isinstance(size, GridItemSize):
			height = size.height
			width = size.width
		elif isinstance(size, tuple):
			height, self.width = size
		elif isinstance(size, int):
			height = size
			width = size
		elif hasattr(size, 'height') and hasattr(size, 'width'):
			height = size.height
			width = size.width
		elif hasattr(size, 'h') and hasattr(size, 'w'):
			height = size.h
			width = size.w
		else:
			raise TypeError(f'{size} is not a valid size')
		if isinstance(width, Callable):
			width = width()
		if isinstance(height, Callable):
			height = height()
		return GridItemSize(width, height)

	def __parseLocation(self, location):
		if isinstance(location, GridItemPosition):
			return location
		elif isinstance(location, tuple):
			column, row = location[0:2]
		elif hasattr(location, 'x') and hasattr(location, 'y'):
			column = location.x
			row = location.y
		elif hasattr(location, 'column') and hasattr(location, 'row'):
			column = location.column
			row = location.row
		elif hasattr(location, 'col') and hasattr(location, 'row'):
			column = location.col
			row = location.row
		else:
			raise TypeError('Invalid location type')
		if isinstance(column, Callable):
			column = column()
		if isinstance(row, Callable):
			row = row()
		return GridItemPosition(column, row, self.grid)

	def __hash__(self) -> int:
		return hash((self.i, self.column, self.row, self.width, self.height))

	def leftExpand(self, value: int):
		newWidth = self.width - value
		newColumn = self.column + value
		if not 1 <= newWidth <= self.grid.columns or not 0 <= newColumn <= self.grid.columns:
			value = 0

		self.__column += value
		self.geometry.position.x += value/self.grid.columns
		self._width -= value
		self.geometry.size.x -= value/self.grid.columns

	def topExpand(self, value: int):
		newHeight = self.height - value
		newRow = self.row + value
		if not 1 <= newHeight <= self.grid.rows or not 0 <= newRow <= self.grid.rows:
			value = 0
		self.__row += value
		self.geometry.position.y += value/self.grid.rows
		self._height -= value
		self.geometry.size.y -= value/self.grid.rows

	def gridItemSpan(self, grid, index: int = None) -> set[int]:
		# span = set()
		# for i in range(self._h):
		# 	span.update(self.columnSpan(grid, index+(grid.columns*i)))
		if index is None:
			index = self.i
		return set([x + (grid.columns*i) for x in range(index, index + self.width) for i in range(self.height)])

	@property
	def naiveSpan(self) -> set[int]:
		return set([x + (self.grid.columns*i) for x in range(0, self.w) for i in range(self.h)])

	def columnSpan(self, grid, index: int) -> set[int]:
		return set(x for x in range(index, index + self.width))

	def shrink(self):
		# if self._h >= self._w:
		# 	self.h -= 1
		# else:
		self.width -= 1

	@property
	def surface(self):
		if self.geometry is None:
			return None
		return self.geometry.surface

	@property
	def canShrink(self):
		return self.height*self.width < 1

	@property
	def size(self):
		return GridItemSize(self.width, self.height)

	@size.setter
	def size(self, value):
		self.width, self.height = self.__parseSize(value)

	@property
	def location(self):
		return GridItemPosition(self.column, self.row)

	@location.setter
	def location(self, value):
		self.column, self.row = self.__parseLocation(value)

	@property
	def i(self):
		if self._i is None and self.grid is not None:
			self._i = self.grid.gridItems.getIndex()
		return self._i

	@i.setter
	def i(self, value):
		self._i = value

	@property
	def width(self):
		try:
			if self.geometry.size.width.absolute:
				value = self._width
			else:
				value = round(self.geometry.size.width.value*self.grid.columns)
			return max(min(value, self.grid.columns - self.column), 1)
		except AttributeError:
			return 1

	@width.setter
	def width(self, value):
		if isinstance(value, float):
			value = round(value)
		if self.grid is not None and value is not None:
			value = max(1, value)
		else:
			value = 1
		self._width = value

	@property
	def absoluteWidth(self):
		return self.grid.columnWidth*self.width

	@absoluteWidth.setter
	def absoluteWidth(self, value):
		self.width = value/self.grid.columnWidth

	@property
	def relativeWidth(self):
		return self.width/self.grid.columns

	@relativeWidth.setter
	def relativeWidth(self, value):
		self.width = value*self.grid.columns

	@property
	def height(self):
		try:
			if self.geometry.size.height.absolute:
				value = self._height
			else:
				value = round(self.geometry.size.height.value*self.grid.rows)
			return max(min(value, self.grid.rows - self.row), 1)
		except AttributeError:
			return 1

	@height.setter
	def height(self, value):
		if isinstance(value, float):
			value = round(value)
		if self.grid is not None and value is not None:
			value = max(1, value)
		else:
			value = 1
		self._height = value

	@property
	def absoluteHeight(self):
		return self.grid.rowHeight*self.height

	@absoluteHeight.setter
	def absoluteHeight(self, value):
		self.height = value/self.grid.rowHeight

	@property
	def relativeHeight(self):
		return self.height/self.grid.rows

	@relativeHeight.setter
	def relativeHeight(self, value):
		self.height = value*self.grid.rows

	@property
	def column(self):
		if self.geometry.position.x.relative:
			return max(0, round(self.geometry.position.x.value*self.grid.columns))
		if self.__column is None:
			# Return 0 if grid or index is unset
			if self._i is None or self.grid is None:
				return 0
			return self.i%self.grid.columns
		# Keep the column in bounds
		return self.__column

	@column.setter
	def column(self, value):
		if self._i is not None:
			self.__column = None
			return
		if isinstance(value, float):
			value = round(value)

		# if there is a grid and it does not allows for overflow
		if self.grid is not None and self.grid.overflow:
			pass
		elif value is not None:
			value = max(0, min(value, self.grid.columns - self.width))
		if self.__column != value:
			self.__column = value
		if value is not None:
			self._column = max(value, 0)
		else:
			self._column = None

	@property
	def x(self):
		return self.column*self.grid.columnWidth

	@x.setter
	def x(self, value):
		self.column = value/self.grid.columnWidth

	@property
	def relativeX(self):
		return self.column/self.grid.columns

	@relativeX.setter
	def relativeX(self, value):
		self.column = value*self.grid.columns

	@property
	def row(self):
		if self.geometry.position.y.relative:
			return max(0, round(self.geometry.position.y.value*self.grid.rows))
		# return saved row if not none
		if self.__row is None:
			# Return 0 if grid or index is unset
			if self._i is None or self.grid is None:
				return 0
			return self.i//self.grid.columns
		return self.__row

	@row.setter
	def row(self, value):
		if self._i is not None:
			self.__row = None
			return

		if isinstance(value, float):
			value = round(value)

		# if there is a grid and it does not allows for overflow
		if self.grid is not None and self.grid.overflow:
			pass
		# if overflow is not allowed, keep the gridItem inside the grid
		elif value is not None:
			value = max(0, min(value, self.grid.rows - self.height))
		# if value is different than the current value, update the value
		if self.__row != value:
			self.__row = value
		if value is not None:
			self._row = max(value, 0)
		else:
			self._row = None

	@property
	def y(self):
		return self.row*self.grid.rowHeight

	@y.setter
	def y(self, value):
		self.row = value/self.grid.rowHeight

	@property
	def relativeY(self):
		return self.row/self.grid.rows

	@relativeY.setter
	def relativeY(self, value):
		self.row = value*self.grid.rows

	def rect(self):
		return QRectF(0, 0, self.absoluteWidth, self.absoluteHeight)

	def pos(self):
		return QPointF(self.x, self.y)

	@property
	def grid(self) -> 'Grid':
		if self._grid is None:
			if self.surface is not None:
				self._grid = self.surface.parentGrid
		return self._grid

	@grid.setter
	def grid(self, value):
		if self._grid is not value:
			if self._grid is not None:
				self._grid.gridItems.remove(self)
			if value is not None:
				value.gridItems.add(self)
			self._grid = value

	def reset(self):
		pass

	# self.__column = None
	# self.__row = None

	def resize(self, width, height):
		self.width = width
		self.height = height

	@property
	def state(self):
		return {
			'i':      self.i,
			'column': self.column,
			'row':    self.row,
			'width':  self.width,
			'height': self.height
		}


class GridOverFlow:
	__slots__ = ['vertical', 'horizontal']
	vertical: bool
	horizontal: bool

	def __init__(self, *args, **kwargs):
		if len(args) == 1 and isinstance(args[0], Iterable):
			args = args[0]
		if isinstance(args, dict):
			kwargs = args
			args = []
		if 'vertical' in kwargs and 'horizontal' in kwargs:
			vertical = kwargs['vertical']
			horizontal = kwargs['horizontal']

		# elif isinstance(args[0], GridOverFlow):
		# 	vertical = args[0].vertical
		# 	horizontal = args[0].horizontal
		elif len(args) == 1:
			vertical = args[0]
			horizontal = args[0]
		elif len(args) > 1:
			vertical = args[0]
			horizontal = args[1]
		else:
			vertical = False
			horizontal = False
		self.vertical = vertical
		self.horizontal = horizontal

	def __bool__(self):
		return bool(self.vertical or self.horizontal)

	def __repr__(self):
		return f'<GridOverFlow vertical={self.vertical} horizontal={self.horizontal}>'

	def __str__(self):
		return f'GridOverFlow(vertical={self.vertical}, horizontal={self.horizontal})'

	def toDict(self):
		return {'vertical': self.vertical, 'horizontal': self.horizontal}


# def __setattr__(self, key, value):
# 	value = bool(value)
# 	super(GridOverFlow, self).__setattr__(key, value)


class GridSize(MultiDimension, dimensions=('columns', 'rows'), separator='×'):
	dimensions = ('columns', 'rows')


class GridItems(list):
	_size = 0

	def __init__(self, grid: 'Grid'):
		super(GridItems, self).__init__()
		self._grid = grid

	@overload
	def __getitem__(self, i: int) -> GridItem:
		...

	@overload
	def __getitem__(self, s: slice) -> List[GridItem]:
		...

	def __getitem__(self, item: Union[int, slice]):
		if isinstance(item, int):
			try:
				i = self.indexes.index(item)
				return super(GridItems, self).__getitem__(i)
			except ValueError:
				return None
		elif isinstance(item, slice):
			start = item.start if item.start is not None else 0
			stop = item.stop if item.stop is not None else self.grid.columns*self.grid.rows
			return [gridItem for gridItem in self if start <= gridItem.i <= stop]
		else:
			return None

	def __bool__(self):
		return bool(self._size)

	# return sum([gridItem.size for gridItem in self._data._values()])

	@property
	def indexes(self) -> List[int]:
		return [gridItem.i for gridItem in self]

	@property
	def grid(self) -> 'Grid':
		return self._grid

	@grid.setter
	def grid(self, value: 'Grid'):
		self._grid = value

	@property
	def size(self):
		return self._size

	@property
	def gridItemsToPack(self):
		return [gridItem for gridItem in self if gridItem.surface.snapping.location]

	def getIndex(self):
		existing = {*self.indexes}
		if not existing:
			return 0
		all = {i for i in range(int(self.grid.size))}
		open = all - existing
		return min(open) if open else max(existing) + 1

	def add(self, item: Union['Panel', Geometry, GridItem], index: Optional[int] = None):
		if isinstance(item, GridItem):
			gridItem = item
		else:
			try:
				gridItem = item.gridItem
			except AttributeError:
				gridItem = None

		if gridItem is None:
			gridItem = GridItem(surface=item, grid=self.grid)
			item.gridItem = gridItem

		if gridItem is not None:
			if gridItem.grid is self._grid:
				pass
			else:
				gridItem.grid = self._grid
			if index is not None:
				gridItem.i = index
			if gridItem._i is None:
				gridItem.i = self.getIndex()

			# push all gridItems after index by 1
			if gridItem.i in self.indexes:
				self.push(gridItem.i)
			self._size += 1
			self.insert(gridItem.i, gridItem)

	def insert(self, index: int, gridItem: GridItem):
		# This is only for list.insert().  Adding a gridItem to the grid is handled by add()
		try:
			index = self.indexes.index(index)
			super(GridItems, self).insert(index, gridItem)
		except ValueError:
			super(GridItems, self).append(gridItem)

	def naivePlace(self, gridItem):
		pass

	def place(self, gridItem: GridItem):
		occupied = gridItem.gridItemSpan
		gridItems = sorted([c for c in self if c is not gridItem], key=lambda x: x.i)
		empty = {x for x in range(self.grid.size)} - occupied

	def push(self, index: int, end: Optional[int] = None, amount: Optional[int] = None):
		if end is None:
			end = self.grid.columns*self.grid.rows
		if amount is None:
			amount = 1
		toPush = self[index:end]
		toPull = self[end:index]
		for gridItem in toPush:
			gridItem.i += amount
		for gridItem in toPull:
			gridItem.i -= amount

	def sort(self, key=None, reverse=False):
		indexes = self.indexes
		if key is None:
			key = lambda x: x.i
		if key == 'type':
			key = lambda x: x
		super(GridItems, self).sort(key=key, reverse=reverse)
		for items in self:
			items.i = indexes.pop(0)

	def __repr__(self):
		return f'<GridItems size={self.size}>'

	def __str__(self):
		return f'GridItems(size={self.size})'

	#
	# def pop(self, index: Optional[int] = None):
	# 	if index is None:
	# 		index = len(self) - 1

	def remove(self, arg: Union[int, GridItem]):
		if isinstance(arg, int):
			index = arg
			arg = self[index]
		if isinstance(arg, Geometry):
			arg = arg.gridItem
		if isinstance(arg, GridItem):
			try:
				index = self.index(arg)
			except ValueError:
				log.debug(f'GridItem: {arg} not found in grid')
				return
		else:
			return
		self._size -= 1
		self.pop(index)

	# end = self.grid.columns * self.grid.rows
	# amount = c.width
	# toPull = self[index:]
	# for gridItem in toPull:
	# 	gridItem.i -= amount

	def pluck(self, index: int) -> GridItem:
		return self.pop(index)


class Grid(QObject):
	surface: Optional[QGraphicsItem]
	rows: Optional[int]
	columns: Optional[int]
	static: bool
	overflow: bool
	gridItems: GridItems
	_surface: Optional[QGraphicsItem] = None
	_rows: int = 3
	_columns: int = 3
	_static: bool = False
	_overflow: GridOverFlow
	_size: GridSize
	autoPlace: bool = False
	sizeChangeSignal = Signal(GridSize)

	def __init__(self, surface: Union[QWidget, QGraphicsScene], rows: Optional[int] = None, columns: Optional[int] = None, static: bool = None, overflow: bool = False):
		super(Grid, self).__init__()
		if not isinstance(overflow, GridOverFlow):
			overflow = GridOverFlow(overflow)
		self.overflow = overflow
		if rows != columns:
			if rows is None:
				rows = columns
			else:
				columns = rows
		if rows is not None:
			self.rows = rows
			self.columns = columns
		if static is not None:
			self._static = static
		self.gridItems = GridItems(self)
		self.surface = surface

		self.sizeChangeSignal.connect(self.resizeAndReplace)

	@cached_property
	def _size(self):
		return GridSize(0, 0)

	def __hash__(self) -> int:
		try:
			return hash(self.surface)
		except AttributeError:
			return hash((self.rows, self.columns, self.static))

	def __eq__(self, other) -> bool:
		if other is None:
			return False
		return (self.rows, self.columns, self.static) == (other.rows, other.columns, other.static)

	def __repr__(self):
		return f'<(Grid for {self.surface.uuidShort}) size={self.size}>'

	def insert(self, *items, **kwargs):
		for item in items:
			self.gridItems.add(item, **kwargs)

	def createGridItem(self, geometry: QGraphicsItem, i: int = None) -> GridItem:
		if i is None:
			i = self.gridItems.getIndex()
		if not isinstance(geometry, Geometry):
			geometry = geometry.geometry
		item = GridItem(surface=geometry, grid=self, i=i)
		self.insert(item)
		return item

	def getIndex(self, *args: Union[QPoint, tuple[int], int, GridItemPosition]) -> int:
		"""
		:param args:
		:type args:
		:return:
		:rtype:
		"""
		if len(args) == 1:
			args = args[0]
		if isinstance(args, QPoint):
			location = self.getColumnRow(args)
		elif isinstance(args, tuple):
			location = GridItemPosition(*args)
		elif isinstance(args, int):
			return args
		else:
			raise TypeError('Invalid argument type')

		return location.column + (location.row*self.columns)

	def getgridItemPosition(self, *args: Union[QPoint, QPointF, tuple[Union[int, float]], int]) -> GridItemPosition:
		"""
		Takes a Point, Position, tuple of (x, y) or index as an int and returns a GridLocation
		:param args:
		:type args: QPoint, QPointF, Position, tuple[Union[int, float]], int
		:return: A GridLocation
		:rtype: GridLocation
		"""
		if len(args) == 1:
			args = args[0]
		if isinstance(args, (QPoint, QPointF)):
			x = args.x()
			y = args.y()
		elif isinstance(args, Position):
			x, y = args.x, args.y
		elif isinstance(args, tuple):
			x, y = args
		elif isinstance(args, int):
			return GridItemPosition(args, grid=self)
		else:
			raise TypeError('Invalid argument type')

		return GridItemPosition(round(x/self.columnWidth), round(y/self.rowHeight))

	def geometryTogridItem(self, surface: 'Panel') -> GridItem:
		geometry = surface.geometry
		column = round(geometry.x/self.columnWidth)
		row = round(geometry.y/self.rowHeight)
		width = round(geometry.width/self.columnWidth)
		height = round(geometry.height/self.rowHeight)
		return GridItem(surface=surface, column=column, row=row, width=width, height=height)

	def indexToGridLocation(self, index: int) -> GridItemPosition:
		return GridItemPosition(index%self.columns, index//self.columns)

	def place(self, gridItem: GridItem, *args: Union[QPoint, tuple[int], int, GridItemPosition]):
		if args:
			location = self.getColumnRow(*args)
		# else:
		# 	if self.__column is not None:
		# 		self.column = self.__column
		# 	if self.__row is not None:
		# 		self.row = self.__row
		# 	# if gridItem.i is None:
		# 	# 	gridItem.i = self.GridItems.getIndex()
		# 	gridItem.location = self.indexToGridLocation(gridItem.i)
		gridItem.surface.setGeometry(gridItem.rect(), gridItem.pos())

	def simplePack(self):
		items = self.gridItems
		for item in items:
			item.surface.updateFromGeometry()

	# 		item.reset()
	# 		self.place(item)

	def resizeAndReplace(self) -> None:
		self.clearCached()
		if self.autoPlace:
			self.simplePack()

	# if self.GridItems:
	# 	gridItemSize = GridItemSize(self.columnWidth, self.rowHeight)
	# 	for gridItem in self.GridItems:
	# 		# if gridItem.surface.snapping:
	# 			# gridItem.surface.setGeometry(rect, pos)
	# 		# else:
	# 		gridItem.surface.setGeometry(None, None)

	def clearCached(self) -> None:
		if not self.overflow.horizontal:
			clearCacheAttr(self, 'columnWidth')
			clearCacheAttr(self, '_COLUMNS')
		if not self.overflow.vertical:
			clearCacheAttr(self, 'rowHeight')
			clearCacheAttr(self, '_ROWS')
		clearCacheAttr(self, 'gridItemSize')

	# def buildGrid(self, afterIndex: int = None, clear: bool = True):
	#
	# 	items = self.GridItems
	# 	w = self.width()
	# 	h = self.height()
	#
	# 	# columns = min(self.columns, 24)
	# 	# columns = max(9, int(self.width() / 150))
	# 	columns = self.columns
	#
	# 	self.blockScreenSizeWidth = int(w / columns)
	#
	# 	if clear:
	# 		self.empty = set(x for x in range(0, self.columns * self.rows))
	#
	# 	if afterIndex is None:
	# 		i = 0
	# 		it = sorted(items, key=lambda x: x.i)
	# 	else:
	# 		i = afterIndex
	# 		it = items
	# 		# it = sorted([i for i in items if i.gridItem.i >= afterIndex], key=lambda x: x.gridItem.i)
	# 		self.empty.update(set().union(*[i.gridItem.gridItemSpan(self) for i in it]))
	#
	# 	# it.extend([DummyWidget(self, assume=False)] * int((columns * self.rows) - size))
	#
	# 	def willExceedColumns(item: GridItem) -> bool:
	# 		return i + item.width - 1 >= (i // columns * columns) + columns
	#
	# 	# def hasCollisions(gridItem: GridItem) -> bool:
	# 	# 	return span < occupied
	#
	# 	def noSpaceAtIndex(item: GridItem, index: int) -> bool:
	# 		return not item.gridItemSpan(self, index) <= self.empty
	#
	# 	iMax = self.size
	# 	for item in it:
	#
	# 		if item.i is not None:
	# 			i = item.i
	# 		elif self.hasAvailableSpace:
	# 			i = min(self.empty)
	# 		else:
	# 			i = 0
	#
	# 		attempted: set = {i}
	# 		if i < iMax:
	# 			# While item can not fit in space or item would exceed columns
	# 			while (noSpaceAtIndex(item, i) or willExceedColumns(item)) or item.canShrink:
	#
	# 				# add current index to attempted
	# 				if noSpaceAtIndex(item, i):
	# 					attempted.add(i)
	#
	# 				# add the row to attempted
	# 				if willExceedColumns(item):
	# 					attempted |= (item.columnSpan(self, i))
	#
	# 				# jump to the next empty index
	# 				remining = self.empty - attempted
	# 				if remining:
	# 					i = min(remining)
	# 				else:
	# 					if not item.canShrink:
	# 						break
	# 					item.shrink()
	# 					attempted = set([])
	# 					i = min(self.empty - attempted)
	#
	# 			safeSpan = item.gridItemSpan(self, i)
	# 			self.empty -= safeSpan
	# 			row = i // columns
	# 			col = i % columns
	#
	# 			item.row = row
	# 			item.column = col
	# 			item.i = i
	#
	# 			if self.empty:
	# 				i = min(self.empty)
	#
	# 	for item in self.items:
	# 		item.update()
	#
	# 	self.blockScreenSizeWidth = int(w / columns)
	# 	# self.gridItemSize = QSize(int(w / columns), int(h / self.rows))
	# 	self.lastColumnCount = self.columns

	def test(self):
		def willExceedColumns(gridItem: GridItem) -> bool:
			return gridItem.column + gridItem.w > self.columns

		def noSpaceAtIndex(gridItem: GridItem) -> bool:
			return not gridItem.gridItemSpan <= self.empty

		if hasattr(self, 'empty'):
			delattr(self, 'empty')
		if hasattr(self, 'occupied'):
			delattr(self, 'occupied')
		empty = self.empty
		occupied = self.occupied
		gridItems = self.gridItems
		columns = self.columns
		rows = self.rows
		for gridItem in gridItems:
			foundSpace = False
			span = np.array(gridItem.naiveSpan)
			indexesToTry = [i for i in range(-gridItem.width - 1, self.columns*self.rows)]
			while not foundSpace:
				pass

			# indexes = [i for i in range(0, columns * rows) if i // rows + gridItem.w <= columns]

			attempted: set = {gridItem.i}
			while (noSpaceAtIndex(gridItem) or willExceedColumns(gridItem)) or gridItem.canShrink:
				# add current index to attempted
				if noSpaceAtIndex(gridItem, i):
					attempted.add(i)

				# add the row to attempted
				if willExceedColumns(gridItem):
					attempted |= (gridItem.columnSpan(self, i))

				# jump to the next empty index
				remining = self.empty - attempted
				if remining:
					i = min(remining)
				else:
					if not gridItem.canShrink:
						break
					gridItem.shrink()
					attempted = set([])
					i = min(self.empty - attempted)

	# def buildGrid(self, afterIndex: int = None, clear: bool = True):
	#
	# 	if not (self.height > 100 or self.width > 100):
	# 		return
	#
	# 	items = self.GridItems
	# 	w = self.width
	# 	h = self.height
	#
	# 	columns = self.columns
	#
	# 	if clear:
	# 		if hasattr(self, 'empty'):
	# 			delattr(self, 'empty')
	#
	# 	# if afterIndex is None:
	# 	# 	i = 0
	# 	# 	it = items
	# 	# else:
	# 	# 	i = afterIndex
	# 	# 	it = self.GridItems[:afterIndex]
	# 	# 	self.empty.update(set().union(*[gridItem.gridItemSpan(self) for gridItem in it]))
	#
	# 	# it.extend([DummyWidget(self, assume=False)] * int((columns * self.rows) - size))
	#
	# 	def willExceedColumns(gridItem: GridItem) -> bool:
	# 		return i + gridItem.w - 1 >= (i // columns * columns) + columns
	#
	# 	# def hasCollisions(gridItem: GridItem) -> bool:
	# 	# 	return span < occupied
	#
	#
	# 	iMax = self.columns * self.rows
	# 	GridItems = self.GridItems
	# 	for gridItem in GridItems:
	#
	# 		if gridItem.i is not None:
	# 			i = gridItem.i
	# 		elif self.empty:
	# 			i = min(self.empty)
	# 		else:
	# 			i = 0
	#
	# 		attempted: set = {i}
	# 		if i < iMax:
	# 			# While item can not fit in space or item would exceed columns
	# 			while (noSpaceAtIndex(gridItem, i) or willExceedColumns(gridItem)) or gridItem.canShrink:
	#
	# 				# add current index to attempted
	# 				if noSpaceAtIndex(gridItem, i):
	# 					attempted.add(i)
	#
	# 				# add the row to attempted
	# 				if willExceedColumns(gridItem):
	# 					attempted |= (gridItem.columnSpan(self, i))
	#
	# 				# jump to the next empty index
	# 				remining = self.empty - attempted
	# 				if remining:
	# 					i = min(remining)
	# 				else:
	# 					print('shrink')
	# 					if not gridItem.canShrink:
	# 						break
	# 					gridItem.shrink()
	# 					attempted = set([])
	# 					i = min(self.empty - attempted)
	#
	# 			safeSpan = gridItem.gridItemSpan(self, i)
	# 			self.empty -= safeSpan
	# 			row = i // columns
	# 			col = i % columns
	# 			if self.empty:
	# 				i = min(self.empty)
	# 			x = gridItem.h
	# 			y = gridItem.w
	#
	# 			# self.gridLayout.addWidget(item, row, col, gridItem.w, gridItem.h)
	# 			gridItem.row = row
	# 			gridItem.column = col
	# 			# item.width = self.columnWidth * gridItem.w
	# 			# item.height = self.rowHeight * gridItem.h
	# 			item.update()
	# 	# self.gridLayout.addWidget(item, row, col, gridItem.h, gridItem.w)
	# 	self.blockScreenSizeWidth = int(w / columns)
	# 	self.gridItemSize = QSize(int(w / columns), int(h / self.rows))
	# 	self.lastColumnCount = self.columns

	@cached_property
	def gridItemSize(self):
		return GridItemSize(self.columnWidth, self.rowHeight)

	@cached_property
	def occupied(self):
		return {gridItem.gridItemSpan(self) for gridItem in self.gridItems}

	@cached_property
	def empty(self):
		self._cachedValues.append('empty')
		return {x for x in range(self.columns*self.rows)}

	@property
	def surface(self):
		return self._surface

	@surface.setter
	def surface(self, value: 'ResizableItem'):
		self.clearCached()
		if self._surface is not None and hasattr(self._surface, 'signals'):
			self._surface.signals.resized.disconnect(self.clearCached)
		if hasattr(value, 'signals'):
			value.signals.resized.connect(self.clearCached)
		self._surface = value

	@property
	def static(self):
		return self._static

	@static.setter
	def static(self, value):
		self.clearCached()
		self._static = value

	@property
	def overflow(self):
		# if self._overflow:
		# 	return self._size.size < self.GridItems.size
		return self._overflow

	@overflow.setter
	def overflow(self, vertical: bool):
		if isinstance(vertical, GridOverFlow):
			self._overflow = vertical
			horizontal = vertical.horizontal
			vertical = vertical.vertical
		elif isinstance(vertical, bool):
			horizontal = vertical
		elif isinstance(vertical, Iterable):
			horizontal = vertical[1]
			vertical = vertical[0]
		else:
			vertical = bool(vertical)
			horizontal = vertical

		if self._overflow.vertical != vertical:
			clearCacheAttr(self, '_COLUMNS')
			clearCacheAttr(self, 'columnWidth')
			self._overflow.vertical = vertical
		if self._overflow.horizontal != horizontal:
			clearCacheAttr(self, '_ROWS')
			clearCacheAttr(self, '_rowHeight')
			self._overflow.horizontal = horizontal

	def setOverflow(self, *vertical: bool, horizontal: Optional[bool] = None):
		self.clearCached()
		if len(vertical) == 1 and horizontal is None:
			vertical = vertical[0]
			horizontal = vertical
		elif horizontal is not None:
			vertical = vertical[0]
		elif len(vertical) > 1:
			horizontal = vertical[1]
			vertical = vertical[0]
		self._overflow.vertical = vertical
		self._overflow.horizontal = horizontal

	@property
	def size(self) -> GridSize:
		return self._size

	@property
	def visibleRegion(self) -> QRectF:
		if hasattr(self.surface, 'containingRect'):
			return self.surface.containingRect
		if hasattr(self.surface, 'visibleRegion'):
			return self.surface.visibleRegion().boundingRect()
		return self.surface.rect()

	@property
	def height(self):
		if hasattr(self.surface, 'height'):
			return self.surface.height()
		return self.surface.rect().height()

	@property
	def visibleHeight(self):
		return self.visibleRegion.height()

	@property
	def width(self):
		if hasattr(self.surface, 'width'):
			return self.surface.width()
		return self.surface.rect().width()

	@property
	def visibleWidth(self):
		return self.visibleRegion.width()

	@cached_property
	def _COLUMNS(self):
		if self.static:
			if self._columns != self._size.columns:
				self._size.columns = self._columns
				self.sizeChangeSignal.emit(self.size)
			return self._columns
		# if not self.GridItems:
		# 	return 1
		elif self.overflow.horizontal:
			if self.overflow.vertical:
				value = ceil(sqrt(len(self.gridItems)))
			else:
				value = max(round(self.visibleWidth/100), len(self.gridItems)/round(self.visibleHeight/100))
		# if self.width > self.height:
		# 	value = max(1, int(ceil(len(self.GridItems) / max(1, self._size.y))), round(self.visibleWidth / 100))
		# if value != self._size.columns:
		# 	self._size.columns = value
		# 	self.sizeChangeSignal.emit(self.size)
		# return value
		# value = max(1, ceil(len(self.GridItems) / max(1, self.height // 100)), round(self.visibleWidth / 100))
		# elif self.width < 180:
		# 	if 1 != self._size.columns:
		# 		self._size.columns = 1
		# 		self.sizeChangeSignal.emit(self.size)
		# 	return 1
		else:
			value = round(self.width/100)
		value = int(max(1, value))
		if value != self._size.columns:
			self._size.columns = value
			self.sizeChangeSignal.emit(self.size)
		return value

	@property
	def columns(self):
		return self._COLUMNS

	@columns.setter
	def columns(self, value):
		self.clearCached()
		value = max(value, 1)
		self.static = True
		self._columns = value
		self._size.columns = value
		self.sizeChangeSignal.emit(self.size)

	@cached_property
	def _ROWS(self):
		if self.static:
			value = self._rows
			if value != self._size.columns:
				self._size.columns = value
				self.sizeChangeSignal.emit(self.size)
			return value
		# if not self.GridItems:
		# 	return 1
		else:
			value = max(1, int(ceil(self.visibleHeight/100)))
		if self.overflow:
			if self.width < self.height:
				# return ceil(len(self.items) / floor(max(1, self.width / 100)))
				value = int(max(1, int(ceil(len(self.gridItems)/max(1, self._size.rows))), round(self.visibleHeight/100)))
			else:
				value = int(max(1, floor(self.height/100)))

			if value != self._size.columns:
				self._size.columns = value
				self.sizeChangeSignal.emit(self.size)
			return value

		if value != self._size.columns:
			self._size.columns = value
			self.sizeChangeSignal.emit(self.size)
		return value

	@property
	def rows(self):
		return self._ROWS

	@rows.setter
	def rows(self, value):
		self.clearCached()
		value = max(value, 1)
		self.static = True
		self._rows = value
		self._size.columns = value
		self.sizeChangeSignal.emit(self.size)

	@cached_property
	def rowHeight(self):
		# if self.overflow:
		# 	if self.visibleHeight > self.visibleWidth:
		# 		return max(1, int(self.visibleWidth / self._size.columns))
		# 	return max(1, int(self.height / self._size.rows))
		# if self.columns > self.rows:
		# 	return
		value = self.visibleHeight/self.rows
		if self.static:
			if not self.overflow:
				return max(self.visibleHeight/self.rows, 10)
			value = self.visibleHeight/self.rows
		if self.overflow:
			if self.rows <= 2:
				value = self.visibleHeight/self.rows
			elif self.columns <= 2:
				value = self.visibleWidth/self.columns
		return max(value, 40)

	@cached_property
	def columnWidth(self):
		# if self.overflow:
		# 	# return 100
		# 	if self.visibleHeight > self.visibleWidth:
		# 		return max(1, int(self.visibleWidth / self._size.columns))
		# 	return max(1, round(self.height / self._size.rows))
		value = self.visibleWidth/self.columns
		if self.static:
			if not self.overflow:
				return max(self.visibleWidth/self.columns, 40)
			value = self.visibleWidth/self.columns
		if self.overflow:
			if self.columns <= 2:
				value = self.visibleWidth/self.columns
			elif self.rows <= 2:
				value = self.visibleHeight/self.rows
		return max(value, 40)

	# if self.static:
	# 	return self.visibleWidth / self.columns
	# calculated = self.visibleWidth / self.columns
	# if self.columns == 1:
	# 	return self.visibleWidth
	# if self.rows <= 2:
	# 	return self.visibleHeight / self.rows
	# calculated = max(calculated, 90)
	# calculated = min(calculated, 120)

	# return calculated

	def gridRect(self) -> QRectF:
		width = self.columnWidth*self.columns
		height = self.rowHeight*self.rows
		return QRectF(0, 0, width, height)

	def makeRect(self, width: int = None, height: int = None):
		if width is None:
			width = self.columns
		if height is None:
			height = self.rows
		return QRectF(0, 0, width*self.columnWidth, height*self.rowHeight)

	def makePos(self, x: int, y: int):
		return QPointF(x*self.columnWidth, y*self.rowHeight)

	@property
	def state(self):
		if self.static:
			return {
				'columns':  self.columns,
				'rows':     self.rows,
				'static':   self.static,
				'overflow': self.overflow,
			}
		return {
			'static':   self.static,
			'overflow': self.overflow,
		}


Grid.default = Grid(QGraphicsRectItem(0, 0, 100, 100))
