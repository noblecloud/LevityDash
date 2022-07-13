from typing import Callable

from numpy import NaN
from PySide2.QtCore import QPoint, QPointF, QRect, QRectF

from LevityDash.lib.utils.shared import ColorStr
from LevityDash.lib.utils.geometry import GridItemPosition, GridItemSize


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


__all__ = ['GridItem']
