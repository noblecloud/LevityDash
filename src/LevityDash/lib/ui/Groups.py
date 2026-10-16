"""Size groups: keep related text items visually consistent.

A ``SizeGroup`` makes its member text items share a rendered size (and, for
aligned members, a baseline) so a row of labels or values reads as one unit.
The five behaviours it provides:

1. Format-hint sizing  - each item sizes against a stable hint string (handled
   in ``Text``), so a changing value doesn't resize the group.
2. Tiered matching     - members bucket into size tiers (``make_size_key``) so
   a large label and a small label in the same declared group don't collapse
   onto each other.
3. Proximity clustering - within a tier, only spatially-near members
   (``get_neighbors``) share a size.
4. Baseline alignment  - within a cluster, members with the same vertical
   alignment share a scene-y baseline.
5. Grow-to-fill        - the shared scale is ``min(getTextScale)`` and is a raw
   ratio, so the group grows as well as shrinks to fill its space.

Design: the fit is a **pure recompute** (``refit``) run lazily on pull
(``fit_for``) whenever the group is marked dirty. There is no cached scale
state, no mutable sub-groups items migrate between, and no incremental
invalidation guard - those were the source of the size-group bugs. ``min()``
over a few hundred items is cheap enough to redo on demand.
"""
from abc import abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from numbers import Number
from typing import ClassVar, Dict, List, Optional, Protocol, Set, runtime_checkable

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath

from LevityDash.lib.utils import ActionPoolItemInstance
from LevityDash.lib.utils.shared import connectSignal, disconnectSignal
from LevityDash.lib.ui import UILogger as log

log = log.getChild(__name__)


@runtime_checkable
class SizeGroupItem(Protocol):

	@abstractmethod
	def getTextScale(self) -> float: ...

	@abstractmethod
	def getTextPosition(self) -> QPointF: ...

	@abstractmethod
	def getTextScenePosition(self) -> QPointF: ...

	@property
	@abstractmethod
	def limitRect(self) -> QRectF: ...

	@property
	@abstractmethod
	def suggestedFontPixelSize(self) -> float: ...

	@property
	@abstractmethod
	def containingRect(self) -> QRectF: ...

	@abstractmethod
	def get_neighbors(self, reach: float, items: Set['SizeGroupItem']) -> Set['SizeGroupItem']: ...

	@abstractmethod
	def scaleSelection(self, *elements: Number, **kwargs) -> Number: ...

	@abstractmethod
	def overlap_shape(self, reach: float | int) -> QPainterPath: ...

	@abstractmethod
	def scene_overlap_shape(self, reach: float | int) -> QPainterPath: ...


@dataclass(frozen=True)
class Fit:
	"""The computed fit applied to a member: shared scale, font size, baseline.

	``baseline_y`` is ``None`` when the member's own vertical position should be
	kept (e.g. match-all groups, or a solo member).
	"""
	scale: float
	font_size: float
	baseline_y: Optional[float] = None


def _detached(item: SizeGroupItem) -> bool:
	"""True for a member whose panel has been removed from its scene. Nothing takes a text out of its group when
	its panel goes, and a removed one has no data to fit: a later refit would raise on it."""
	scene = getattr(item, 'scene', None)
	return callable(scene) and scene() is None


def _vertical_alignment(item: SizeGroupItem):
	try:
		return item.alignment.vertical
	except AttributeError:
		return None


class SizeGroup:
	__groups__: ClassVar[List['SizeGroup']] = []
	reach: float = 10
	#: The `@name` this group was asked for when no ancestor has that name, so it is a group of its own. Set by `Panel.getAttrGroup`; tools read it.
	unresolvedScope: Optional[str] = None

	items: Set[SizeGroupItem]
	key: str

	def __new__(cls, *args, **kwargs):
		if kwargs.pop('matchAll', False):
			cls = MatchAllSizeGroup
		instance = super().__new__(cls)
		SizeGroup.__groups__.append(instance)
		return instance

	def __init__(self, parent: ActionPoolItemInstance, key: str, items: Set[SizeGroupItem] = None, matchAll: bool = False):
		self.key = key
		self.items = set(items) if items else set()
		self._fit: Dict[SizeGroupItem, Fit] = {}
		self._dirty = True
		# font sizes are tracked separately from the full fit: font() needs them
		# but must stay cheap (no getTextScale), or refit -> getTextScale ->
		# font -> fit_for -> refit would recurse.
		self._font_sizes: Dict[SizeGroupItem, float] = {}
		self._font_dirty = True
		self.parent = parent  # property setter wires the parent's resized signal

	# ----------------------------------------------------------------- parent
	@property
	def parent(self) -> ActionPoolItemInstance:
		return self._parent

	@parent.setter
	def parent(self, value: ActionPoolItemInstance):
		if (current := getattr(self, '_parent', None)) is not None and current is not value:
			self._disconnect_parent(current)
		self._parent = value
		self._connect_parent(value)

	def _connect_parent(self, parent: ActionPoolItemInstance):
		if parent is self:
			return
		try:
			connectSignal(parent.signals.resized, self.parent_resized)
		except AttributeError:
			pass

	def _disconnect_parent(self, parent: ActionPoolItemInstance):
		try:
			disconnectSignal(parent.signals.resized, self.parent_resized)
		except (AttributeError, RuntimeError):
			pass

	@property
	def is_loading(self) -> bool:
		return self.parent.is_loading

	@property
	def state_is_loading(self) -> bool:
		return self.parent.state_is_loading

	def parent_resized(self, *args) -> None:
		# The parent panel resized; the fit is stale. Members re-apply through
		# their own resized -> asyncUpdateTransform connections, which pull a
		# fresh fit - so here we only need to invalidate.
		self.mark_dirty()

	# --------------------------------------------------------------- membership
	def addItem(self, item: SizeGroupItem):
		self.items.add(item)
		item._sized = self
		self.mark_dirty()

	def removeItem(self, item: SizeGroupItem):
		self.items.discard(item)
		if getattr(item, '_sized', None) is self:
			item._sized = None
		self._fit.pop(item, None)
		self.mark_dirty()

	def mark_dirty(self):
		self._dirty = True
		self._font_dirty = True

	# ---------------------------------------------------------------- sizing
	def font_size_for(self, item: SizeGroupItem) -> float:
		"""Tier-shared font point size for ``item``.

		Cheap (reads only ``suggestedFontPixelSize``), so ``Text.font`` can call
		it without triggering the full, ``getTextScale``-driven refit.
		"""
		if self._font_dirty:
			sizes: Dict[SizeGroupItem, float] = {}
			for tier in self._tiers(self.items).values():
				fs = min((i.suggestedFontPixelSize for i in tier), default=10)
				for i in tier:
					sizes[i] = fs
			self._font_sizes = sizes
			self._font_dirty = False
		return self._font_sizes.get(item, item.suggestedFontPixelSize)

	# ------------------------------------------------------------------- fit
	def fit_for(self, item: SizeGroupItem) -> Fit:
		"""The fit to apply to ``item``, recomputing the whole group if dirty."""
		if self._dirty:
			self.refit()
		fit = self._fit.get(item)
		if fit is None:
			# not part of the current partition (just added, or removed): fall
			# back to the item's own solo fit rather than fail.
			return Fit(scale=item.getTextScale(), font_size=self.font_size_for(item))
		return fit

	def refit(self) -> None:
		"""Recompute the fit for every member from scratch."""
		# Clear dirty first so any reentrant fit_for (via getTextScale) returns a
		# solo fallback instead of recursing.
		self._dirty = False
		fit: Dict[SizeGroupItem, Fit] = {}
		for tier in self._tiers(self.items).values():
			# Font size is tier-scoped (matches the old group_font_size); the
			# shared scale and baseline are scoped to cluster-and-alignment.
			font_size = min((i.suggestedFontPixelSize for i in tier), default=10)
			for cluster in self._clusters(tier):
				for aligned in self._alignment_groups(cluster):
					if not aligned:
						continue
					scale = min(i.getTextScale() for i in aligned)
					baseline = self._baseline(aligned)
					shared = Fit(scale=scale, font_size=font_size, baseline_y=baseline)
					for i in aligned:
						fit[i] = shared
		self._fit = fit

	# ----------------------------------------------- partition (overridable)
	def _tiers(self, items: Set[SizeGroupItem]) -> Dict[int, Set[SizeGroupItem]]:
		tiers: Dict[int, Set[SizeGroupItem]] = defaultdict(set)
		for item in items:
			if _detached(item):
				continue
			tiers[self.make_size_key(item)].add(item)
		return dict(tiers)

	def _clusters(self, tier: Set[SizeGroupItem]) -> List[frozenset]:
		"""Partition a tier into spatially-adjacent clusters (reach distance)."""
		clusters: List[frozenset] = []
		remaining = set(tier)
		while remaining:
			item = remaining.pop()
			cluster = frozenset(item.get_neighbors(self.reach, remaining) | {item})
			clusters.append(cluster)
			remaining -= cluster
		return clusters

	def _alignment_groups(self, cluster: frozenset) -> List[Set[SizeGroupItem]]:
		"""Split a cluster by vertical alignment (baseline + scale scope)."""
		groups: Dict[object, Set[SizeGroupItem]] = defaultdict(set)
		for item in cluster:
			groups[_vertical_alignment(item)].add(item)
		return list(groups.values())

	def _baseline(self, aligned: Set[SizeGroupItem]) -> Optional[float]:
		ys = [i.getTextScenePosition().y() for i in aligned]
		return sum(ys) / len(ys) if ys else None

	def make_size_key(self, item: SizeGroupItem) -> int:
		if not isinstance(item, SizeGroupItem):
			raise TypeError(f'item must be a SizeGroupItem, not {type(item)}')
		reach = self.reach
		# An item may name the height that picks its tier apart from the one that sizes its font
		# (a value with a unit line is shorter than one without, but belongs with it).
		height = getattr(item, 'tierHeight', item.suggestedFontPixelSize)
		return max(int(round(height / reach) * reach), reach)

	def apply(self):
		"""Invalidate this group and re-apply its fit to every member now."""
		self.mark_dirty()
		for item in tuple(self.items):
			if _detached(item):
				continue
			try:
				item.updateTransform(updatePath=False, updateShared=False, reason='group-apply')
			except Exception as e:
				log.warning(f'Could not re-fit {item!r} in size group {self.key!r}: {e}')

	# ------------------------------------------------------------- class-wide
	@classmethod
	def refit_all(cls):
		"""Invalidate every group and re-apply the fit to every member.

		Used for the post-load settle-fit and the manual 'Refresh All
		SizeGroups' action. Idempotent.
		"""
		cls.prune()
		for group in cls.__groups__:
			group.apply()

	@classmethod
	def prune(cls) -> int:
		"""Forget the groups of panels that are gone, and the members that left the scene, and return how many groups went.

		A reload builds a new set of panels and with them new groups, but nothing told
		the registry about the old ones, so every Ctrl+R added a full set of dead
		groups that refits and the Studio then walked. A group is dead when its owning
		panel and every member have left the scene. Run after a load has settled (a
		panel still being built is not in the scene yet).
		"""
		def live(item) -> bool:
			try:
				return item.scene() is not None
			except (RuntimeError, AttributeError):
				return False
		keep = []
		for group in cls.__groups__:
			if live(group.parent) or any(live(i) for i in group.items):
				# a panel that outlives the load (the dashboard's own `global.` groups) still lists the old items
				for item in [i for i in group.items if not live(i)]:
					group.removeItem(item)
				keep.append(group)
			else:
				group._disconnect_parent(group._parent)
		gone = len(cls.__groups__) - len(keep)
		cls.__groups__[:] = keep
		return gone

	# Back-compat aliases for existing callers/tests.
	update_all = refit_all
	rebucket_and_update_all = refit_all

	def __repr__(self):
		return f'{type(self).__name__}({self.key!r}, {len(self.items)} items)'


class MatchAllSizeGroup(SizeGroup):
	"""Every member of a tier shares one size and keeps its own position.

	No proximity clustering and no baseline averaging - the whole tier is one
	group and each item keeps its own vertical position.
	"""

	def _clusters(self, tier: Set[SizeGroupItem]) -> List[frozenset]:
		return [frozenset(tier)]

	def _alignment_groups(self, cluster: frozenset) -> List[Set[SizeGroupItem]]:
		return [set(cluster)]

	def _baseline(self, aligned: Set[SizeGroupItem]) -> Optional[float]:
		return None
