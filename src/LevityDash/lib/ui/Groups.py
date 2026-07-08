from abc import abstractmethod
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import cached_property, partial, lru_cache
from logging import DEBUG
from numbers import Number
from typing import Set, List, Iterable, ClassVar, Dict, Protocol, runtime_checkable, Callable, Self, Optional
from warnings import warn

from PySide6.QtCore import QPointF, QRectF, QMargins, QTimer
from PySide6.QtGui import QPainterPath
from PySide6.QtWidgets import QApplication

from LevityDash.lib.ui.Geometry import Position, AlignmentFlag
from LevityDash.lib.ui.frontends.PySide.utils import modifyTransformValues
from LevityDash.lib.utils import clearCacheAttr, ActionPool, ActionPoolItemInstance
from LevityDash.lib.utils.protocols import Aligned
from LevityDash.lib.utils.shared import _Panel, guarded_cached_property, defer, attr_is_cached, disconnectSignal, connectSignal
from LevityDash.lib.ui import UILogger as log


@runtime_checkable
class SizeGroupItem(Protocol):

	@abstractmethod
	def getTextScale(self) -> float:
		...

	@abstractmethod
	def getTextPosition(self) -> QPointF:
		...

	@abstractmethod
	def getTextScenePosition(self) -> QPointF:
		...

	@property
	@abstractmethod
	def limitRect(self) -> QRectF:
		...

	@property
	@abstractmethod
	def suggestedFontPixelSize(self) -> float:
		...

	@property
	@abstractmethod
	def containingRect(self) -> QRectF:
		...

	@abstractmethod
	def get_neighbors(self, reach: float, items: Set['SizeGroupItem']) -> Set['SizeGroupItem']:
		...

	@abstractmethod
	def scaleSelection(self, *elements: Number, **kwargs) -> Number:
		...

	@abstractmethod
	def overlap_shape(self, reach: float | int) -> QPainterPath:
		...

	@abstractmethod
	def scene_overlap_shape(self, reach: float | int) -> QPainterPath:
		...


class ValueRange:
	__slots__ = ('min', 'max', 'ave', 'count')
	min: float
	max: float
	ave: float
	count: int

	def __init__(self, *values):
		self.count = count = len(values)
		self.min = self.max = self.ave = values[0] if values else 0
		for value in values[1:]:
			if value < self.min:
				self.min = value
			if value > self.max:
				self.max = value
			self.ave += value
		if count > 0:
			self.ave /= count

	def __contains__(self, item: Self | Number) -> bool:
		match item:
			case Number():
				return self.min <= item <= self.max
			case ValueRange():
				return self.min <= item.min and self.max >= item.max
			case _:
				raise TypeError(f'ValueRange.__contains__ only supports Numbers and ValueRange, not {type(item)}')

	def __eq__(self, other: Self) -> bool:
		try:
			return self.min == other.min and self.max == other.max and self.ave == other.ave
		except AttributeError:
			raise TypeError(f'ValueRange equality only supports ValueRange, not {type(other)}')

	def __repr__(self):
		return f"ValueRange(min={self.min}, max={self.max}, ave={self.ave}, count={self.count})"

	def __str__(self):
		return f"ValueRange(min={self.min}, max={self.max}, ave={self.ave}, count={self.count})"

	def __hash__(self):
		return hash((self.min, self.max, self.ave, self.count))

	def __bool__(self):
		return bool(self.count)

	def __lt__(self, other: Self | Number):
		match other:
			case Number():
				return self.max < other
			case ValueRange():
				return self.max < other.min
			case _:
				raise TypeError(f'ValueRange.__lt__ only supports Numbers and ValueRange, not {type(other)}')

	def __le__(self, other: Self | Number):
		match other:
			case Number():
				return self.max <= other
			case ValueRange():
				return self.max <= other.min
			case _:
				raise TypeError(f'ValueRange.__le__ only supports Numbers and ValueRange, not {type(other)}')

	def __gt__(self, other: Self | Number):
		match other:
			case Number():
				return self.min > other
			case ValueRange():
				return self.min > other.max
			case _:
				raise TypeError(f'ValueRange.__gt__ only supports Numbers and ValueRange, not {type(other)}')

	def __ge__(self, other: Self | Number):
		match other:
			case Number():
				return self.min >= other
			case ValueRange():
				return self.min >= other.max
			case _:
				raise TypeError(f'ValueRange.__ge__ only supports Numbers and ValueRange, not {type(other)}')


class SizeGroup:

	class SubGroup(Set[SizeGroupItem]):

		reach: float = property(lambda self: self._reach)
		super_group: 'SizeGroup' = property(lambda self: self._super_group)
		group_key: int = property(lambda self: self._group_key)

		group_scale_range: ValueRange

		group_size_range: ValueRange
		group_size_limits: ValueRange

		def __init__(self, group_key: int, super_group: 'SizeGroup', reach: float = None, *args, **kwargs):

			if reach is None:
				reach = super_group.reach

			self._reach = reach
			self._group_key = group_key
			self._super_group = super_group

			super().__init__(*args, **kwargs)

		def set_group_key(self, key: int):
			self._group_key = key
			clearCacheAttr(self, 'group_size_range', 'group_size_limits')
			self._reset()

		def __hash__(self) -> int:
			return hash((self.group_key, id(self.super_group)))

		@guarded_cached_property(guardFunc=lambda x: x is not None, default=None)
		def action_pool(self) -> ActionPool:
			if (super_group := self._super_group) is not None:
				return super_group.action_pool.new(self, priority=ActionPool.Priority.Low)

		@property
		def is_loading(self) -> bool:
			return self._super_group.is_loading

		@property
		def state_is_loading(self) -> bool:
			return self._super_group.state_is_loading

		@property
		def group_scale(self) -> float:
			return self.group_scale_range.min

		@cached_property
		def group_size_range(self) -> ValueRange:
			# Note: The height of the limit rects should always determine this
			return ValueRange(*(item.suggestedFontPixelSize for item in self))

		@cached_property
		def group_size_limits(self) -> ValueRange:
			reach = self.reach / 2
			key = self.group_key
			return ValueRange(key - reach, key + reach)

		@cached_property
		def group_scale_range(self) -> ValueRange:
			return ValueRange(*(item.getTextScale() for item in self))

		def is_correct_size(self, item: SizeGroupItem) -> bool:
			return item.suggestedFontPixelSize in self.group_size_limits

		def get_scale_for_item(self, item: SizeGroupItem, cluster: frozenset[SizeGroupItem] = None, aligned: bool = True) -> float:
			cluster = cluster or self.find_cluster_for_item(item)
			aligned = self.get_similar_aligned_items(item) if aligned else cluster
			return self.get_scale_for_cluster(frozenset(cluster & aligned))

		@property
		def group_font_size(self) -> float:
			return min((item.suggestedFontPixelSize for item in self), default=10)

		@cached_property
		def size_clusters(self) -> List[frozenset[SizeGroupItem]]:
			"""
			Clusters the items that have limit rects within the reach distance of each other.

			Returns
			-------
			List[Set[SizeGroupItem]]
			"""

			clusters = []
			items = set(self)

			while items:
				item = items.pop()
				cluster = frozenset(item.get_neighbors(self.reach, items) | {item})
				clusters.append(cluster)
				items -= cluster

			return clusters

		@property
		def h_alignment_clusters(self):
			alignments: Dict[None | AlignmentFlag, Set[SizeGroupItem]] = defaultdict(set)
			for item in self:
				if (item_alignment := getattr(item, 'alignment', None)) is not None:
					item_alignment = item_alignment.horizontal
				alignments[item_alignment].add(item)
			return dict(alignments)

		@property
		def v_alignment_clusters(self):
			alignments: Dict[None | AlignmentFlag, Set[SizeGroupItem]] = defaultdict(set)
			for item in self:
				if (item_alignment := getattr(item, 'alignment', None)) is not None:
					item_alignment = item_alignment.vertical
				alignments[item_alignment].add(item)
			return dict(alignments)

		# @lru_cache(maxsize=64)
		def get_similar_aligned_items(self, item: SizeGroupItem) -> Set[SizeGroupItem]:

			def get_alignment(i: SizeGroupItem | Aligned):
				try:
					return i.alignment.vertical
				except AttributeError:
					return None
			alignment = get_alignment(item)
			v_alignment_cluster = self.v_alignment_clusters.get(alignment, None)
			return v_alignment_cluster & self.find_cluster_for_item(item)

		def group_y(self, item: SizeGroupItem) -> float:
			"""
			Returns the scene y position of the item in the group.
			"""
			similar_aligned_items = self.get_similar_aligned_items(item)
			return sum((i.getTextScenePosition().y() for i in similar_aligned_items)) / (len(similar_aligned_items) or 1)

		def find_cluster_for_item(self, item: SizeGroupItem) -> frozenset[SizeGroupItem]:
			for cluster in self.size_clusters:
				if item in cluster:
					return cluster
			return frozenset({item})

		def get_size_for_item(self, item: SizeGroupItem, method: str = 'min') -> float:
			cluster = self.find_cluster_for_item(item)
			return self.get_size_for_cluster(cluster, method=method)

		# @lru_cache(maxsize=64)
		def get_size_for_cluster(self, cluster: frozenset[SizeGroupItem], method: str = 'min') -> float:
			match method:
				case 'min':
					return min((i.suggestedFontPixelSize for i in cluster))
				case 'max':
					return max((i.suggestedFontPixelSize for i in cluster))
				case 'ave' | _:
					return sum((i.suggestedFontPixelSize for i in cluster)) / len(cluster)

		def get_scale_for_cluster(self, cluster: frozenset[SizeGroupItem], method: str = 'min') -> float:
			match method:
				case 'min':
					return min((i.getTextScale() for i in cluster))
				case 'max':
					return max((i.getTextScale() for i in cluster))
				case 'ave' | _:
					return sum((i.getTextScale() for i in cluster)) / len(cluster)

		@defer
		def make_adjustments(self, exclude: SizeGroupItem = None, reason=None):
			self._reset()
			if len(self) < 1:
				return

			log.verbose(f'Making adjustments for {self.__repr__()}: {reason}')

			for cluster in self.size_clusters:
				for item in cluster:
					if item is exclude:
						continue
					# item_y = item.mapFromScene(QPointF(0, cluster_y)).y()
					# t = item.transform()
					# item_pos = item.getTextPosition()
					# item_pos.setY(item_y)
					# modifyTransformValues(xScale=group_scale, yScale=group_scale, yTranslate=item_pos.y(),xTranslate=item_pos.x(), transform=t)
					# item.setTransform(t)
					if (item_func := item.updateTransform) in (item_action_pool := item.action_pool):
						item_action_pool.update_context(item, kwargs=dict(updateShared=False))
					else:
						item_func(updatePath=False, updateShared=False, reason=reason)

		@defer
		def rescale_group(self):
			for item in self:
				if (item_func := item.updateTransform) in (item_action_pool := item.action_pool):
					args, kwargs = item_action_pool.get_context(item)
					if kwargs.get('updatePath', True):
						continue
					item_action_pool.update_context(item, kwargs=dict(updateShared=False))
				else:
					item_func(updatePath=True, updateShared=False)
				item.updateTransform(updatePath=True, updateShared=False)

		@cached_property
		def adjust_all(self) -> Callable[[], None]:
			return partial(self.make_adjustments, exclude=None, reason='refresh_all')

		@cached_property
		def parent_resized(self) -> Callable[[], None]:
			return partial(self.make_adjustments, exclude=None, reason='parent-resized')

		def will_cause_invalidation(self, item: SizeGroupItem):
			item_size = item.suggestedFontPixelSize
			if len(self) < 1:
				log.verbose(f'Item {self.__item_repr__(item)} will cause invalidation because the group is empty', verbosity=3)
				return True
			if item not in self and len(self) > 0:
				log.verbose(f'Item {self.__item_repr__(item)} will cause invalidation because it is not in the group', verbosity=3)
				return True
			if item_size not in self.group_size_limits:
				log.verbose(f'Item {self.__item_repr__(item)} will cause invalidation because its size {item_size} is not in the group size limits {self.group_size_limits}', verbosity=3)
				return True
			# if item in self:
			if item.getTextScale() not in self.group_scale_range and len(self) > 1:
				log.verbose(f'Item {self.__item_repr__(item)} will cause invalidation because its scale {item.getTextScale()} is not in the group scale range {self.group_scale_range}', verbosity=3)
				return True
			return False

		def invalidate(self, invalided_by: SizeGroupItem = None, reason: str = None):
			item_size = invalided_by.suggestedFontPixelSize
			item_scale = invalided_by.getTextScale()
			match reason:
				case 'item-resized':
					self.make_adjustments(exclude=invalided_by, reason='neighbor_item_resized')

		def _reset(self):
			clearCacheAttr(self, 'group_scale_range', 'group_font_size', 'group_size_range', 'size_clusters')

		def add(self, item: SizeGroupItem) -> None:
			log.debug(f'Adding {self.__item_repr__(item)} to size group {self._group_key}')
			if self.is_loading:
				self._reset()
			else:
				if self.will_cause_invalidation(item):
					log.debug(f'Adding {self.__item_repr__(item)} to size group {self._group_key} will cause invalidation')
					super().add(item)
					self.make_adjustments(reason='add')
					return
			super().add(item)

			if (action_pool := self.action_pool) is not None and not action_pool.can_execute:
				action_pool.add(item.updateTransform, kwargs=dict(updatePath=True, updateShared=False))
			else:
				item.updateTransform(updatePath=True, updateShared=False)

			# self._reset()

			# if (new_size := self.group_scale) != current_size:
			# 	self.action_pool.add(self.adjust_all)

		def remove(self, item: SizeGroupItem) -> None:
			super().remove(item)
			log.debug(f'Removing {self.__item_repr__(item)} from size group {self._group_key}')
			self.make_adjustments(reason='remove')

		def discard(self, item: SizeGroupItem) -> None:
			super().discard(item)
			log.debug(f'Discarding {self.__item_repr__(item)} from size group {self._group_key}')
			self.make_adjustments(reason='discard')

		def pop(self) -> SizeGroupItem:
			element = super().pop()
			self.make_adjustments(reason='pop')
			return element

		def clear(self) -> None:
			super().clear()
			self._reset()

		def update(self, other: Iterable[SizeGroupItem]) -> None:
			super().update(other)
			self.make_adjustments(reason='update')

		def intersection_update(self, other: Iterable[SizeGroupItem]) -> None:
			super().intersection_update(other)
			self.make_adjustments(reason='intersection_update')

		def difference_update(self, other: Iterable[SizeGroupItem]) -> None:
			super().difference_update(other)
			self.make_adjustments(reason='difference_update')

		def symmetric_difference_update(self, other: Iterable[SizeGroupItem]) -> None:
			super().symmetric_difference_update(other)
			self.make_adjustments(reason='symmetric_difference_update')

		def __iand__(self, other: Iterable[SizeGroupItem]) -> 'Group':
			super().__iand__(other)
			self.make_adjustments(reason='__iand__')
			return self

		def __ior__(self, other: Iterable[SizeGroupItem]) -> 'Group':
			super().__ior__(other)
			self.make_adjustments(reason='__ior__')
			return self

		def __isub__(self, other: Iterable[SizeGroupItem]) -> 'Group':
			super().__isub__(other)
			self.make_adjustments(reason='__isub__')
			return self

		def __ixor__(self, other: Iterable[SizeGroupItem]) -> 'Group':
			super().__ixor__(other)
			self.make_adjustments(reason='__ixor__')
			return self

		def __item_repr__(self, item: SizeGroupItem):
			if getattr(item, 'isIcon', False):
				return f'{type(item).__name__}({item.icon.name!r})'
			return f'{type(item).__name__}({item.text!r})'

		def __repr__(self):
			return f"""{type(self).__name__}[{self._group_key}]({", ".join(
				(self.__item_repr__(item) for item in self)
			)})"""

		def __delete__(self, instance):
			action_pool = self.action_pool
			if action_pool is not None:
				action_pool.delete()

		def delete(self):
			self.__delete__(self.super_group)

	@dataclass(unsafe_hash=True, slots=True)
	class ItemData:
		item: SizeGroupItem = field(init=True, hash=True, repr=True, compare=True)
		current_group: 'SizeGroup.SubGroup' = field(init=True, default=None, hash=False, repr=True, kw_only=True)

		last_scale: float = field(init=True, default=0, hash=False, repr=False)
		last_size: float = field(init=True, default=0, hash=False, repr=False)

		pos: Position = field(init=True, default=None, hash=False, repr=False, kw_only=True)
		prev_group: 'SizeGroup.SubGroup' = field(init=False, default=None, hash=False, repr=False)

		@property
		def size(self) -> float:
			return self.item.suggestedFontPixelSize

		@property
		def scale(self) -> float:
			return self.item.getTextScale()

		def set_group(self, group: Optional['SizeGroup.SubGroup']):
			self.prev_group = self.current_group if self.current_group is not None else self.prev_group
			self.current_group = group

	__groups__: ClassVar[List['SizeGroup']] = []
	items: Set[SizeGroupItem]

	parent: ActionPoolItemInstance
	_lock_level: int = 0

	key: str

	_pending: Set[SizeGroupItem] = cached_property(lambda self: set())
	_item_data: Dict[SizeGroupItem, ItemData] = cached_property(lambda self: {})
	_alignments: Dict[AlignmentFlag, float] = cached_property(lambda self: defaultdict(float))
	reach = 10

	margins = QMargins(reach, reach, reach, reach)

	@classmethod
	def update_all(cls):
		for group in cls.__groups__:
			for sub_group in group.sub_groups.values():
				sub_group.make_adjustments(reason='update-all')

	@classmethod
	def rebucket_and_update_all(cls):
		"""
		Re-fit every group against current geometry.

		Unlike update_all, this also re-buckets items whose suggested size no
		longer matches their sub-group — necessary after loading, when items were
		bucketed against pre-layout geometry. Idempotent, so re-running is safe.
		"""
		for group in cls.__groups__:
			for item in tuple(group.items):
				group.on_item_resize(item, reason='post-load-refit')

	def __new__(cls, *args, **kwargs):
		matchAll = kwargs.pop('matchAll', False)
		if matchAll:
			cls = MatchAllSizeGroup
		instance = super().__new__(cls)
		cls.__groups__.append(instance)
		return instance

	def __init__(self, parent: ActionPoolItemInstance, key: str, items: Set['Text'] = None, matchAll: bool = False):
		self.updateTask = None
		self.key = key
		self.items = items or set()
		self.parent = parent

	@cached_property
	def action_pool(self) -> ActionPool:
		parent_action = getattr(self.parent, 'action_pool', None)
		if parent_action is not None:
			return parent_action.new(self, priority=ActionPool.Priority.Low)
		return ActionPool(self)

	@property
	def is_loading(self) -> bool:
		return self.parent.is_loading

	@property
	def state_is_loading(self) -> bool:
		return self.parent.state_is_loading

	@property
	def parent(self) -> ActionPoolItemInstance:
		return self._parent

	@parent.setter
	def parent(self, value: ActionPoolItemInstance):
		if (current_parent := getattr(self, '_parent', None)) is not None:
			self._disconnect_parent(current_parent)
		self._parent = value
		self._connect_parent(value)

	def _connect_parent(self, parent: ActionPoolItemInstance):

		own_action_pool: ActionPool = self.action_pool
		parent_action_pool: ActionPool = parent.action_pool

		if own_action_pool.up is parent_action_pool and own_action_pool in parent_action_pool:
			return

		if parent is self:
			return

		try:
			resize_signal = parent.signals.resized
			connectSignal(resize_signal, self.parent_resized)
		except AttributeError:
			pass

		parent_action_pool.add(own_action_pool)

	def _disconnect_parent(self, parent: ActionPoolItemInstance):
		try:
			resize_signal = parent.signals.resized
			disconnectSignal(resize_signal, self.parent_resized)
		except AttributeError:
			pass

		parent_action_pool = parent.action_pool
		own_action_pool = self.action_pool

		if parent_action_pool is own_action_pool:
			assert own_action_pool.root is own_action_pool
			return

		if own_action_pool is parent_action_pool:
			own_action_pool.up = own_action_pool
			own_action_pool.root = own_action_pool
		else:
			parent_action_pool.discard(own_action_pool)

	def adjustSizes(self, exclude: 'Text' = None, reason=None):
		if len(self.items) < 1:
			return
		for group in self.sub_groups.values():
			group.make_adjustments(exclude=exclude, reason=reason)

	def parent_resized(self) -> None:
		pool = self.action_pool
		for group in self.sub_groups.values():
			if group.make_adjustments in pool:
				continue
			group.make_adjustments(reason='parent-resized')

	@property
	def sorted_items(self) -> dict[int, Set[SizeGroupItem]]:
		sorted_items = defaultdict(set)

		# sort the items into their respective groups
		for item in self.items:
			sorted_items[self.make_size_key(item)].add(item)

		# change the type of sorted_items from defaultdict to dict
		sorted_items = dict(sorted_items.items())

		return sorted_items

	def get_item_data(self, item: SizeGroupItem, sub_group: SubGroup = None) -> ItemData:
		if (item_data := self._item_data.get(item, None)) is None:
			self._item_data[item] = item_data = self.ItemData(item, current_group=sub_group)
		return item_data

	def get_item_sub_group(self, item: SizeGroupItem) -> SubGroup | None:
		item_data = self.get_item_data(item)

		if item not in (item_data.current_group or ()):
			item_data.set_group(None)

		if item_data.current_group is None:
			for group in self.sub_groups.values():
				if item in group:
					item_data.set_group(group)
					break
		return item_data.current_group

	def move_group(self, from_key: int, to_key: int):
		if from_key == to_key:
			return
		if to_key in self.sub_groups and len(self.sub_groups[to_key]) > 0:
			raise ValueError(f'Cannot move group {from_key} to {to_key} because {to_key} is not empty')
		if (from_group := self.sub_groups.pop(from_key, None)) is not None:
			self.sub_groups[to_key] = from_group
			from_group.set_group_key(to_key)

	def find_sub_group_for_item(self, item: 'Text') -> SubGroup:
		if (current_group := self.get_item_sub_group(item)) is not None:
			return current_group
		else:
			key = self.make_size_key(item)
			self.sub_groups[key] = group = self.SubGroup(key, self)
			return group

	def _add_item_to_sub_group(self, item: SizeGroupItem, sub_group: SubGroup = None):
		if sub_group is None:
			sub_group = self.find_sub_group_for_item(item)

		item_data = self.get_item_data(item)
		try:
			item_data.current_group.discard(item)
		except AttributeError:
			pass
		item_data.set_group(None)
		item._sized = self
		self._item_data[item] = item_data
		sub_group.add(item)

	def move_to_group(self, item_data: ItemData, current_group: SubGroup, new_group: SubGroup):
		item = item_data.item
		with self.action_pool:
			current_group.discard(item)
			new_group.add(item)
			item_data.set_group(new_group)

		if not current_group:
			self.sub_groups.pop(current_group.group_key)
			current_group.delete()

	def move_item_to_appropriate_group(self, item: SizeGroupItem):
		new_key = self.make_size_key(item)
		if len(current_group := self.get_item_sub_group(item)) < 1 and new_key not in self.sub_groups:
			self.move_group((new_group := current_group).group_key, new_key)
		else:
			if (new_group := self.sub_groups.get(new_key, None)) is None:
				self.sub_groups[new_key] = new_group = self.SubGroup(new_key, self)
			self.move_to_group(self.get_item_data(item), current_group, new_group)

	def addItem(self, item: SizeGroupItem):
		self.items.add(item)
		if (group := self.sub_groups.get(key := self.make_size_key(item), None)) is None:
			self.sub_groups[key] = group = self.SubGroup(key, self)
		item_data = self.get_item_data(item, sub_group=group)
		item_data.set_group(group)
		group.add(item)
		item._sized = self

	def on_item_resize(self, item: SizeGroupItem, reason: str = 'item-resized'):
		item_group = self.get_item_sub_group(item)

		height = item.suggestedFontPixelSize
		if height not in item_group.group_size_limits:
			with self.action_pool:
				self.move_item_to_appropriate_group(item)
		else:
			if len(item_group) == 1:
				item_group._reset()
				item.updateTransform(updatePath=False, updateShared=False, reason=reason)
			else:
				if self.action_pool.can_execute:
					item_group.make_adjustments(reason=f'{reason} - {item.text}')
				else:
					self.action_pool.add(item_group.make_adjustments, kwargs=dict(reason=f'{reason} - {item.text}'))

	# def deferred_on_item_resize(self, item: SizeGroupItem, reason: str = 'item-resized'):
	# 	if not self.get_item_sub_group(item).will_cause_invalidation(item):
	# 		return
		# self.defer_timer.singleShot(200, partial(self.on_item_resize, item, reason))

	def _remove_item_from_group(self, item: 'Text', group: Set['Text'] = None, key: int = None):
		if item in self._item_data:
			data = self._item_data.pop(item)
			if group is None or key is None:
				group = data.current_group
				key = group.group_key
			group.discard(item)

			if len(group) == 0:
				self.sub_groups.pop(key, None)
				group.delete()

	def removeItem(self, item: SizeGroupItem):
		self._remove_item_from_group(item)

	def make_size_key(self, item: SizeGroupItem | SubGroup) -> int:
		reach = self.reach

		match item:
			case self.SubGroup():
				value = int(round(sum(i.suggestedFontPixelSize for i in item) / len(item) / reach) * reach)
			case SizeGroupItem():
				value = int(round(item.suggestedFontPixelSize / reach) * reach)
			case _:
				raise TypeError(f'item must be a SizeGroupItem or SizeGroup.SubGroup, not {type(item)}')

		return max(value, reach)

	def _get_last_size_key(self, item: SizeGroupItem) -> int:
		if (item_data := self._item_data.get(item, None)) is not None:
			return item_data.prev_group.group_key
		return 0

	@cached_property
	def sub_groups(self) -> Dict[int, SubGroup]:
		return {k: self.SubGroup(k, self, self.reach, v) for k, v in self.sorted_items.items()}


class MatchAllSizeGroup(SizeGroup):

	class SubGroup(SizeGroup.SubGroup):

		def get_similar_aligned_items(self, item: SizeGroupItem) -> Set[SizeGroupItem]:
			return frozenset(self)

		def is_correct_size(self, item: SizeGroupItem) -> bool:
			return True

		def group_y(self, item: SizeGroupItem) -> float:
			return item.getTextScenePosition().y()

		@cached_property
		def group_size_range(self) -> ValueRange:
			# Note: The height of the limit rects should always determine this
			return ValueRange(*(item.suggestedFontPixelSize for item in self))

		@cached_property
		def group_size_limits(self) -> ValueRange:
			return ValueRange(0, 10000)

		@cached_property
		def group_scale_range(self) -> ValueRange:
			return ValueRange(*(item.getTextScale() for item in self))

		@cached_property
		def size_clusters(self) -> List[frozenset[SizeGroupItem]]:
			return [frozenset(self)]

	def make_size_key(self, item: SizeGroupItem | SizeGroup.SubGroup) -> int:
		return 0

	# def on_item_resize(self, item: SizeGroupItem):
	# 	self.sub_groups[0].make_adjustments(reason='item-resized')

	@cached_property
	def sub_groups(self) -> Dict[int, SizeGroup.SubGroup]:
		return {0: self.SubGroup(0, self, self.reach, self.items)}
