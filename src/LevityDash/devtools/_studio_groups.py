"""Dev-only: which size group each text item of the previewed dashboard joined, read from the live scene.

The engine decides the groups (`Panel.getAttrGroup`), so this reads what it built instead of working it out again from
the YAML: each `SizeGroup` with the text items in it, who owns it, whether it matches all of a tier, and the tier and
font size every member got. A group whose `@name` scope matched no panel (`SizeGroup.unresolvedScope`) is flagged,
because the engine otherwise gives that label a group nobody else joins and says nothing.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QRectF

#: Where a group's text can be put, by role: (label, the item field that holds the group).
ROLES = (
	('Titles inside', 'shared.title.matchingGroup'),
	('Values inside', 'shared.display.valueLabel.matchingGroup'),
	('This text item', 'matchingGroup'),
)


@dataclass
class Member:
	path: Optional[tuple]  # the nearest item of the tree this text is in
	text: str
	tier: int
	font: float
	rect: QRectF
	role: str = ''  # 'label' for a reading's title, 'value' for its value, '' for any other text


@dataclass
class Group:
	label: str
	key: str
	matchAll: bool
	members: List[Member] = field(default_factory=list)
	unresolved: Optional[str] = None  # the `@name` that no panel has

	@property
	def tiers(self) -> List[int]:
		return sorted({m.tier for m in self.members})

	@property
	def reach(self) -> str:
		return 'the whole tier' if self.matchAll else 'touching boxes'

	def covers(self, path: tuple) -> bool:
		"""Whether a text in the item at `path`, or below it, is in this group."""
		return any(m.path is not None and m.path[:len(path)] == path for m in self.members)


def spec(value) -> Tuple[str, bool]:
	"""A `matchingGroup` as written (a string, or `{group, matchAll}`) as (name, matchAll)."""
	if isinstance(value, dict):
		return str(value.get('group', '')), bool(value.get('matchAll', False))
	return ('' if value is None else str(value)), False


def written(name: str, matchAll: bool):
	"""The value to store for `name`: a bare string, or the mapping when it must match all."""
	name = name.strip()
	if not name:
		return None
	return {'group': name, 'matchAll': True} if matchAll else name


def _pathOf(item, names: Dict[str, tuple]) -> Optional[tuple]:
	while item is not None:
		name = getattr(item, 'stateName', None)
		if isinstance(name, str) and name in names:
			return names[name]
		item = item.parentItem()
	return None


def _roleOf(item) -> str:
	"""Whether a text is a reading's title or its value, from the item it sits in (the text is inside a `TitleLabel` or a `DisplayLabel`)."""
	while item is not None:
		names = {c.__name__ for c in type(item).__mro__}
		if 'TitleLabel' in names:
			return 'label'
		if 'DisplayLabel' in names:
			return 'value'
		if 'Realtime' in names:
			return ''
		item = item.parentItem()
	return ''


def _label(group, scene, names: Dict[str, tuple]) -> str:
	if group.unresolvedScope:
		return f'{group.key}@{group.unresolvedScope}'
	owner = group.parent
	if owner is getattr(scene, 'base', None):
		return f'global.{group.key}'
	name = getattr(owner, 'stateName', None)
	if isinstance(name, str) and name in names:
		return f'{group.key}@{"".join(f"[{i}]" for i in names[name]) or "root"}'
	if isinstance(name, str) and name:
		return f'{group.key}@{name}'
	tag = getattr(owner, '__tag__', None)
	return f'{tag if isinstance(tag, str) else type(owner).__name__}.{group.key}'


def collect(scene, names: Dict[str, tuple]) -> List[Group]:
	"""Every size group with a text item in `scene`, in a stable order."""
	from LevityDash.lib.ui.Groups import MatchAllSizeGroup, SizeGroup
	origin = scene.sceneRect().topLeft()
	found: List[Group] = []
	for g in list(SizeGroup.__groups__):
		try:
			items = [i for i in g.items if i.scene() is scene]
		except RuntimeError:  # the group outlived the scene it was made in
			continue
		if not items:
			continue
		out = Group(_label(g, scene, names), g.key, isinstance(g, MatchAllSizeGroup), unresolved=g.unresolvedScope)
		for i in items:
			try:
				out.members.append(Member(_pathOf(i, names), str(getattr(i, 'text', '') or '')[:40], g.make_size_key(i), float(g.font_size_for(i)), i.sceneBoundingRect().translated(-origin), _roleOf(i)))
			except Exception:  # noqa: BLE001 - one item that cannot report must not hide the rest
				continue
		if out.members:
			out.members.sort(key=lambda m: (m.path is None, m.path or (), m.text))
			found.append(out)
	# Each label that missed gets a group of its own, so one typo makes many one-member groups; show them as the one scope they are.
	merged: Dict[str, Group] = {}
	for g in [g for g in found if g.unresolved]:
		if g.label in merged:
			merged[g.label].members += g.members
		else:
			merged[g.label] = g
	found = [g for g in found if not g.unresolved] + list(merged.values())
	found.sort(key=lambda g: (g.unresolved is None, g.label))
	return found
