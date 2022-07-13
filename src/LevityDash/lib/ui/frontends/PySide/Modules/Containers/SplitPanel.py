
from PySide2.QtWidgets import QGraphicsItem

from LevityDash.lib.ui.frontends.PySide.Modules.Handles.Resize import Splitter
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
from LevityDash.lib.utils.geometry import LocationFlag, relativePosition
from ... import UILogger as guiLog

log = guiLog.getChild(__name__)

__all__ = ["SplitPanel"]


class SplitPanel(Panel):
	onlyAddChildrenOnRelease = True
	includeChildrenInState = False

	collisionThreshold = 0.9
	_primary = None
	_secondary = None

	def __init__(self, *args, **kwargs):
		self.orientation = kwargs.get('orientation', 'horizontal')
		super(SplitPanel, self).__init__(*args, **kwargs)
		self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

		primary = kwargs.get('primary', None)
		secondary = kwargs.get('secondary', None)
		if primary and isinstance(primary, dict):
			primary = self.loadChildFromState(primary)
		if secondary and isinstance(secondary, dict):
			secondary = self.loadChildFromState(secondary)
		if not primary and not secondary:
			if 'childItems' in kwargs:
				childItems = list(kwargs['childItems']._values())
				childItems = [self.loadChildFromState(child) for child in childItems]
				if self.orientation.isHorizontal:
					sorted(childItems, key=lambda x: x.geometry.pos().y())
				else:
					sorted(childItems, key=lambda x: x.geometry.pos().x())
				if len(childItems) == 0:
					primary, secondary = None, None
				elif len(childItems) == 1:
					primary = childItems[0]
					secondary = None
				elif len(childItems) == 2:
					primary, secondary = childItems

		self.splitter = Splitter(surface=self, primary=primary, secondary=secondary, splitType=kwargs.get('orientation', 'horizontal'), ratio=kwargs.get('ratio', 0.5))

		if self.primary is not None:
			self.primary.setMovable(False)
			self.primary.setAcceptDrops(False)
		if self.secondary is not None:
			self.secondary.setMovable(False)
			self.secondary.setAcceptDrops(False)

		self.setAcceptDrops(True)
		self.splitter.setGeometries()
		self.splitter.hide()

	@property
	def primary(self):
		return self.splitter.primary

	@primary.setter
	def primary(self, value):
		if isinstance(value, dict):
			value = self.loadChildFromState(value)
		self.splitter.primary = value

	@property
	def secondary(self):
		return self.splitter.secondary

	@secondary.setter
	def secondary(self, value):
		if isinstance(value, dict):
			value = self.loadChildFromState(value)
		self.splitter.secondary = value

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

	@property
	def orientation(self):
		return self._orientation

	@orientation.setter
	def orientation(self, value):
		if isinstance(value, str):
			value = LocationFlag[value.title()]
		self._orientation = value

	def loadChildFromState(self, child):
		try:
			cls = child.pop('class', None)
			if cls is None:
				raise TypeError('No class specified')
			child = cls(parent=self, **child)
			return child
		except TypeError:
			log.exception(f'Error loading child item: {cls} with type: {type(cls)}')

	# def _loadChildren(self, childItems):
	# 	# Children are initiated from the state
	# 	return None

	def _loadChildren(self, childItems):
		pass

	@property
	def state(self) -> dict:
		state = super(SplitPanel, self).state
		state['class'] = self.__class__.__name__
		state['orientation'] = self.orientation.name
		state['ratio'] = self.splitter.ratio
		state.pop('childItems', None)
		state['primary'] = self.primary
		state['secondary'] = self.secondary
		return state
