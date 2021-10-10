from dataclasses import dataclass

from PySide2.QtWidgets import QWidget


@dataclass
class Cell:
	item: QWidget
	i: int
	x: int
	y: int
	_h: int = 1
	_w: int = 1

	def __init__(self, item: QWidget, i: int = None, x: int = None, y: int = None, h: int = 1, w: int = 1):
		self.item = item
		self.i = i
		self.x = x
		self.y = y
		self._h = h
		self._w = w

	def cellSpan(self, grid, index: int = None) -> set[int]:
		# span = set()
		# for i in range(self._h):
		# 	span.update(self.columnSpan(grid, index+(grid.columns*i)))
		if index is None:
			index = self.i
		return set([x + (grid.columns * i) for x in range(index, index + self.w) for i in range(self.h)])

	def columnSpan(self, grid, index: int) -> set[int]:
		return set(x for x in range(index, index + self.w))

	def shrink(self):
		# if self._h >= self._w:
		# 	self.h -= 1
		# else:
		self.w -= 1

	@property
	def canShrink(self):
		return self._h * self._w < 1

	@property
	def size(self):
		return self._h * self._w

	@property
	def w(self):
		try:
			return min(self._w, self.item.parent().columns)
		except AttributeError:
			return 1

	@w.setter
	def w(self, value):
		# try:
		# 	# self.item.setMaximumWidth(100 * value)
		# 	# self.item.setMinimumWidth(100 * value - 30)
		# except TypeError:
		# 	pass
		self._w = max(1, value)

	@property
	def h(self):
		try:
			return min(self._h, self.item.parent().rows)
		except AttributeError:
			return 1

	@h.setter
	def h(self, value):
		# try:
		# 	# self.item.setMaximumHeight(100 * value)
		# 	# self.item.setMinimumHeight(100 * value - 30)
		# except TypeError:
		# 	pass
		self._h = max(1, value)

	def reset(self):
		self.h = 1
		self.w = 1

	def resize(self, width, height):
		self.w = width
		self.h = height
