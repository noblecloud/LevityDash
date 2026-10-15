
from typing import List

from PySide6.QtWidgets import QGraphicsItem

from LevityDash.lib.stateful import DefaultGroup, StateProperty
from ..Handles.Splitters import Splitter
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
from LevityDash.lib.ui.Geometry import LocationFlag, relativePosition
from LevityDash.lib.ui.frontends.PySide.utils import hasState, itemLoader
from ... import UILogger as guiLog

log = guiLog.getChild(__name__)

__all__ = ["SplitPanel"]


class SplitPanel(Panel, tag='split'):
	"""Two items on either side of a draggable divider.

	```yaml
	- type: split
	  orientation: vertical   # the divider is vertical: first item left, second right
	  ratio: 0.4              # the first item's share of the split
	  items:
	    - type: group         # first item
	      ...
	    - type: group         # second item
	      ...
	```

	`orientation: horizontal` (the default) puts a horizontal divider with the first item
	on top. Each item fills its side; `geometry` on the two items is ignored (and not
	saved). A third item is an error. Double-click the divider to swap the sides, drag it
	to move it. A save writes `orientation` and `ratio` only when they differ from the
	defaults.
	"""
	onlyAddChildrenOnRelease = True
	includeChildrenInState = True
	placesChildren = True  # the divider moves and sizes the two items, so they save no `locked`, `movable` or `resizable`

	collisionThreshold = 0.9
	_splitter = None
	_orientation = LocationFlag.Horizontal
	_ratio = 0.5

	def __init__(self, *args, **kwargs):
		self.geometries = {}
		super(SplitPanel, self).__init__(*args, **kwargs)
		self.setAcceptDrops(True)

	# section splitter

	@property
	def splitter(self) -> Splitter | None:
		return self._splitter

	def setGeometries(self) -> None:
		"""`GeometryManager`: the splitter owns the children's geometry, so they save none."""
		if self._splitter is not None:
			self._splitter.setGeometries()

	def _arrange(self, primary: Panel | None, secondary: Panel | None) -> None:
		"""Hand two children to the divider, making it first if there is none."""
		if self._splitter is None:
			if primary is None and secondary is None:
				return
			self._splitter = Splitter(
				surface=self, primary=primary, secondary=secondary,
				splitType=self._orientation, ratio=self._ratio,
			)
			self._splitter.hide()
		self._splitter.primary = primary
		self._splitter.secondary = secondary
		for child in (primary, secondary):
			if child is not None:
				child.locked = True
		self._splitter.setGeometries()

	@property
	def primary(self):
		return None if self._splitter is None else self._splitter.primary

	@primary.setter
	def primary(self, value):
		self._arrange(value, self.secondary)

	@property
	def secondary(self):
		return None if self._splitter is None else self._splitter.secondary

	@secondary.setter
	def secondary(self, value):
		self._arrange(self.primary, value)

	# section state

	@StateProperty(
		default=DefaultGroup(None, []),
		dependencies={'geometry', 'margins'},
		sortOrder=-1,
	)
	def items(self) -> List[Panel]:
		return [child for child in (self.primary, self.secondary) if child is not None]

	@items.setter
	def items(self, value: List[dict]):
		if isinstance(value, (list, tuple)) and len(value) > 2:
			raise ValueError(f'A split holds two items, not {len(value)}')
		for item in value:
			if isinstance(item, dict):
				item.pop('geometry', None)
		self.geometry.updateSurface()
		itemLoader(self, value, existing=self.items)
		children = [child for child in self.childItems() if isinstance(child, Panel) and hasState(child)]
		# The previous primary and secondary come first, so a reload keeps the sides.
		order = {id(child): index for index, child in enumerate(self.items)}
		children.sort(key=lambda child: order.get(id(child), len(order)))
		children = children[:2] + [None] * (2 - len(children))
		self._arrange(*children)

	@items.condition(method='get')
	def items(owner: 'SplitPanel') -> bool:
		return owner.hasChildren

	@items.condition(method={'get', 'set'})
	def items(value: List[Panel]) -> bool:
		return hasattr(value, '__len__') and len(value) > 0

	@StateProperty(default='horizontal', allowNone=False, sortOrder=60)
	def orientation(self) -> LocationFlag:
		"""Which way the divider runs: `horizontal` (first item above) or `vertical` (first item to the left)."""
		return self._orientation

	@orientation.setter
	def orientation(self, value: LocationFlag):
		self._orientation = value
		if self._splitter is not None:
			self._splitter.location = value
			self._splitter.updatePosition(self.rect())
			self._splitter.setGeometries()

	@orientation.decode
	def orientation(self, value) -> LocationFlag:
		if isinstance(value, LocationFlag):
			return value
		name = str(value).strip().lower()
		if name not in ('horizontal', 'vertical'):
			raise ValueError(f"orientation must be 'horizontal' or 'vertical', not {value!r}")
		return LocationFlag[name.title()]

	@orientation.encode
	def orientation(value: LocationFlag) -> str:
		return value.name.lower()

	@StateProperty(default=0.5, allowNone=False, sortOrder=61)
	def ratio(self) -> float:
		"""The first item's share of the split, `0` to `1`. Dragging the divider changes it."""
		return self._ratio if self._splitter is None else float(self._splitter.ratio)

	@ratio.setter
	def ratio(self, value: float):
		self._ratio = value
		if self._splitter is not None:
			self._splitter.ratio = value

	@ratio.decode
	def ratio(self, value) -> float:
		value = float(str(value).rstrip('%')) / (100 if str(value).endswith('%') else 1)
		if not 0 <= value <= 1:
			raise ValueError(f'ratio must be between 0 and 1, not {value}')
		return value

	@ratio.encode
	def ratio(value: float) -> float:
		return round(float(value), 3)

	def dropEvent(self, event):
		newChild = super(SplitPanel, self).dropEvent(event)

	# newChild.setMovable(False)

	def placeChild(self, child, pos):
		child.setMovable(False)
		child.setResizable(False)
		if child.previousParent is None:
			pos = child.geometry.absolutePosition().asQPointF()
		position = relativePosition(pos, self.splitter.pos())
		if self.orientation.isHorizontal:
			if position.isTop:
				if self.primary is not None:
					self.primary.delete()
				self.primary = child
			else:
				if self.secondary is not None:
					self.secondary.delete()
				self.secondary = child
		else:
			if pos.x() > self.splitter.pos().x():
				if self.primary is not None:
					self.primary.delete()
				self.primary = child
			else:
				if self.secondary is not None:
					self.secondary.delete()
				self.secondary = child

			if self.primary.parentItem() is None:
				self.primary.setParentItem(self)
			if self.secondary.parentItem() is None:
				self.secondary.setParentItem(self)

		self.splitter.setGeometries()

	# def itemChange(self, change, value):
	# 	if change == QGraphicsItem.ItemChildAddedChange and isinstance(value, Panel):
	# 		if hasattr(self, 'splitter'):
	# 			if isinstance(value, Panel):
	# 				pos = self.mapFromItem(value.previousParent, value.pos())
	# 				self.placeChild(value, pos)
	# 				self.geometry.updateSurface()
	# 	# value.lockedToParent = True
	# 	if change == QGraphicsItem.ItemChildRemovedChange and isinstance(value, Panel):
	# 		if hasattr(self, 'splitter'):
	# 			if self.primary is value:
	# 				self.splitter.primary = None
	# 				self.primary = None
	# 			elif self.secondary is value:
	# 				self.splitter.secondary = None
	# 				self.secondary = None
	# 			self.splitter.setGeometries()
	# 
	# 	return super(SplitPanel, self).itemChange(change, value)
