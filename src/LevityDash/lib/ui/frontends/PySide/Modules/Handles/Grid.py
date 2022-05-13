from functools import cached_property

from LevityDash.lib.ui.frontends.PySide.Modules.Handles.Incrementer import Incrementer, IncrementerGroup

__all__ = ['GridAdjuster', 'GridAdjusters']


class GridAdjuster(Incrementer):

	def __init__(self, *args, **kwargs):
		super(GridAdjuster, self).__init__(*args, **kwargs)

	def increase(self):
		loc = self.location
		if loc.isVertical:
			self.grid.columns += 1
		else:
			self.grid.rows += 1

	def decrease(self):
		loc = self.location
		if loc.isVertical:
			self.grid.columns -= 1
		else:
			self.grid.rows -= 1


class GridAdjusters(IncrementerGroup):
	handleType = GridAdjuster

	def __init__(self, *args, **kwargs):
		super(GridAdjusters, self).__init__(*args, **kwargs)
		self.setVisible(False)
		self.setEnabled(self.surface.staticGrid)

	@cached_property
	def grid(self) -> 'Grid':
		return self.parentItem().grid
