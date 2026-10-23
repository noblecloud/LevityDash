"""Dev-only, Qt-free: checks on the order of the text tiers of a dashboard, read from the size groups the engine built.

`design-standards.md` gives a dashboard four text roles: a header names a panel, a label names a value, a value is a
number, a hero is the one number a panel is about. The order that must hold is hero > header > value >= label (a header
at or below its labels, or a label above the value it names, reads upside down). The checks read the fitted font size of
every member of every size group, so they judge what is drawn, not what the file asks for.

Two kinds of check:

- by role of the group: a group is a header, label, value, hero or caption by the last part of its key (`global.head`,
  `title@panel`, `group.value`). The median size of each role is compared with the next one. This sees a whole dashboard.
- by item: a label and the value it names sit in the same item, and the label must not be the larger. This names the item.

Neither changes how groups fit. A group key the check does not know a role for is left out.
"""
from dataclasses import dataclass, field
from statistics import median
from typing import Dict, Iterable, List, Optional, Tuple

#: Group key (lower case) to text role.
ROLE_OF_KEY: Dict[str, str] = {
	'head': 'header', 'header': 'header', 'heads': 'header', 'heading': 'header',
	'title': 'label', 'titles': 'label', 'label': 'label', 'labels': 'label',
	'value': 'value', 'values': 'value', 'stat': 'value', 'stats': 'value',
	'hero': 'hero', 'heroes': 'hero',
	'cap': 'caption', 'caps': 'caption', 'caption': 'caption', 'captions': 'caption',
}

#: A header should be at least this many times its labels. The standard asks for about 1.25 to 1.33 between neighbours.
HEADER_OVER_LABEL = 1.2

WARN, NOTE = 'warn', 'note'


@dataclass
class Finding:
	severity: str  # WARN or NOTE
	message: str
	members: list = field(default_factory=list)  # the members the message is about, so the stage can outline them
	path: Optional[tuple] = None  # the item the message is about, when it is not about text

	@property
	def rects(self):
		return [m.rect for m in self.members]


def role(key: str) -> Optional[str]:
	"""The text role a group key names, or None."""
	return ROLE_OF_KEY.get(str(key).rsplit('.', 1)[-1].split('@', 1)[0].strip().lower())


def _typical(members: list) -> float:
	return float(median(m.font for m in members))


def check(found: Iterable) -> List[Finding]:
	"""The findings for `found`, the groups `_studio_groups.collect` returns: worst first."""
	found = list(found)
	by_role: Dict[str, list] = {}
	for g in found:
		if g.unresolved:
			continue
		if (r := role(g.key)) is not None:
			by_role.setdefault(r, []).extend(g.members)
	out: List[Finding] = []

	def size(r: str) -> Optional[float]:
		return _typical(by_role[r]) if by_role.get(r) else None

	header, label, value, hero, caption = (size(r) for r in ('header', 'label', 'value', 'hero', 'caption'))
	if header is not None and label is not None:
		if header <= label:
			out.append(Finding(WARN, f'Headers ({header:.0f}px) are not larger than labels ({label:.0f}px). A header at or below its labels reads as a footnote.', by_role['header']))
		elif header < label * HEADER_OVER_LABEL:
			out.append(Finding(NOTE, f'Headers ({header:.0f}px) are only {header / label:.2f}x the labels ({label:.0f}px); about 1.25x or more keeps them apart.', by_role['header']))
	if label is not None and value is not None and label > value:
		out.append(Finding(WARN, f'Labels ({label:.0f}px) are larger than values ({value:.0f}px). A label should be no larger than the value it names.', by_role['label']))
	if hero is not None and value is not None and hero <= value:
		out.append(Finding(WARN, f'Heroes ({hero:.0f}px) are not larger than values ({value:.0f}px).', by_role['hero']))
	if caption is not None and label is not None and caption > label:
		out.append(Finding(WARN, f'Captions ({caption:.0f}px) are larger than labels ({label:.0f}px).', by_role['caption']))
	out.extend(_by_item(found))
	out.sort(key=lambda f: f.severity != WARN)
	return out


def _by_item(found: list) -> List[Finding]:
	"""A label larger than the value in the same item. Needs members that know their `role`, which groups of a reading give."""
	items: Dict[tuple, Dict[str, list]] = {}
	for g in found:
		for m in g.members:
			if m.path is not None and getattr(m, 'role', '') in ('label', 'value'):
				items.setdefault(m.path, {}).setdefault(m.role, []).append(m)
	out = []
	for path, roles in sorted(items.items()):
		labels, values = roles.get('label'), roles.get('value')
		if labels and values and max(m.font for m in labels) > max(m.font for m in values):
			where = ''.join(f'[{i}]' for i in path) or 'root'
			name = labels[0].text or values[0].text
			out.append(Finding(WARN, f'In {where}{" (" + name + ")" if name else ""} the label ({max(m.font for m in labels):.0f}px) is larger than its value ({max(m.font for m in values):.0f}px).', labels + values))
	return out
