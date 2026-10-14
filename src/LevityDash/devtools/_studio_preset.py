"""Dev-only: the preset the Studio builder edits. Qt-free.

The format and its rules are `LevityDash.lib.presets`: a preset file holds `props:` (a bare default, or
`{default, type, min, max, doc}`) and a `template:` item whose strings name a property as `$name`; a
dashboard uses it as `preset: name`, `props:` with the values that differ, and any other field of the
item. This module does not define the format. It holds a preset the way an editor needs it (a list of
properties, a tree with paths), builds the library's `Preset` from it to expand and check, and writes it
back in the library's own shape.

Property types are the library's: `number`, `size`, `text`, `key`, `color`, `bool`; a property with no
`type` is `any` here (a list or mapping, such as zones).
"""
import copy
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple

from LevityDash.lib import presets as lib
from LevityDash.lib.variables import substitute

PRESET_KEY = lib.PRESET
PROPS_KEY = lib.PROPS
TEMPLATE_KEY = lib.TEMPLATE
ITEMS_KEY = 'items'

TYPES = ('number', 'size', 'text', 'key', 'color', 'bool', 'any')

_REF = re.compile(r'\$\{([A-Za-z_][\w-]*)\}|\$([A-Za-z_]\w*)')
_SIZE = re.compile(r'^\s*-?\d+(?:\.\d+)?\s*(%|px|mm|cm|in)\s*$')
_COLOR = re.compile(r'^#[0-9a-fA-F]{3,8}$')

#: A path is a tuple of child indexes from the template's root item. The root is `()`.
Path = Tuple[int, ...]


@dataclass
class PropSpec:
	"""One property a preset declares."""
	name: str
	type: str = 'text'
	default: Any = ''
	lo: Optional[float] = None
	hi: Optional[float] = None
	doc: str = ''

	def asData(self) -> Any:
		"""The library's shape: a bare default for an untyped property with nothing else, else a full declaration."""
		if self.type == 'any' and not (self.doc or self.lo is not None or self.hi is not None):
			return copy.deepcopy(self.default)
		out: Dict[str, Any] = {'default': copy.deepcopy(self.default)}
		if self.type != 'any':
			out['type'] = self.type
		if self.lo is not None:
			out['min'] = self.lo
		if self.hi is not None:
			out['max'] = self.hi
		if self.doc:
			out['doc'] = self.doc
		return out

	def kind(self) -> str:
		"""The kind of editor: the declared type, or the one the default suggests when there is none."""
		return self.type if self.type != 'any' else inferType(self.default)


def inferType(value: Any) -> str:
	if isinstance(value, bool):
		return 'bool'
	if isinstance(value, (int, float)):
		return 'number'
	if isinstance(value, str):
		if _SIZE.match(value):
			return 'size'
		if _COLOR.match(value):
			return 'color'
		return 'text'
	return 'any'


def specFrom(prop: 'lib.Prop') -> PropSpec:
	return PropSpec(prop.name, prop.type or 'any', copy.deepcopy(prop.default), prop.min, prop.max, prop.doc)


def refs(node: Any) -> Iterator[str]:
	"""Every property name `$name` or `${name}` the node mentions."""
	if isinstance(node, dict):
		for v in node.values():
			yield from refs(v)
	elif isinstance(node, list):
		for v in node:
			yield from refs(v)
	elif isinstance(node, str):
		for m in _REF.finditer(node):
			yield m.group(1) or m.group(2)


def wholeRef(value: Any) -> Optional[str]:
	"""`name` when `value` is exactly `$name`, else None."""
	if isinstance(value, str):
		m = _REF.fullmatch(value.strip())
		if m:
			return m.group(1) or m.group(2)
	return None


def _without(node: Any, base: Any) -> Any:
	"""`node` minus every leaf equal to the same leaf in `base`. Lists compare whole."""
	if isinstance(node, dict) and isinstance(base, dict):
		out = {}
		for k, v in node.items():
			kept = _without(v, base[k]) if k in base else v
			if kept != {}:
				out[k] = copy.deepcopy(kept)
		return out
	return {} if node == base else copy.deepcopy(node)


@dataclass
class Piece:
	"""A preset being built: its name, declared properties and template."""
	name: str = 'new-preset'
	props: Dict[str, PropSpec] = field(default_factory=dict)
	template: Dict[str, Any] = field(default_factory=lambda: {'type': 'group', ITEMS_KEY: []})
	doc: str = ''

	# files

	@classmethod
	def fromPreset(cls, preset: 'lib.Preset') -> 'Piece':
		return cls(preset.name, {n: specFrom(p) for n, p in preset.props.items()}, copy.deepcopy(preset.template), preset.doc)

	@classmethod
	def fromText(cls, name: str, text: str) -> 'Piece':
		"""Read a preset file with the library's own parser; raises `lib.PresetError` for a file it would refuse."""
		return cls.fromPreset(lib.parse(name, text))

	def toPreset(self) -> 'lib.Preset':
		props = {n: lib.Prop(n, copy.deepcopy(s.default), None if s.type == 'any' else s.type, s.lo, s.hi, s.doc) for n, s in self.props.items()}
		return lib.Preset(self.name, props, copy.deepcopy(self.template), doc=self.doc)

	def asData(self) -> dict:
		out: Dict[str, Any] = {}
		if self.doc:
			out['doc'] = self.doc
		out[PROPS_KEY] = {n: s.asData() for n, s in self.props.items()}
		out[TEMPLATE_KEY] = copy.deepcopy(self.template)
		return out

	def copy(self) -> 'Piece':
		return copy.deepcopy(self)

	# values

	def defaults(self) -> Dict[str, Any]:
		return {n: copy.deepcopy(s.default) for n, s in self.props.items()}

	def problems(self, given: Optional[Dict[str, Any]] = None) -> List[str]:
		"""What the library would refuse for this use: an unknown property, a wrong type, a value out of range, a loop."""
		try:
			self.toPreset().instance({k: v for k, v in (given or {}).items()})
		except lib.PresetError as e:
			return [str(e)]
		return []

	# expansion and the instance

	def expanded(self, given: Optional[Dict[str, Any]] = None) -> dict:
		"""The item a dashboard sees: the library's expansion. A use it would refuse expands with the defaults."""
		try:
			return self.toPreset().instance(given)
		except lib.PresetError:
			return self.toPreset().instance(None)

	def instance(self, given: Optional[Dict[str, Any]] = None, fields: Optional[dict] = None) -> dict:
		"""What a dashboard stores: the preset, only the properties that differ, and the fields that differ."""
		out: Dict[str, Any] = {PRESET_KEY: self.name}
		diff = {k: v for k, v in (given or {}).items() if k in self.props and v != self.props[k].default}
		if diff:
			out[PROPS_KEY] = diff
		if fields:
			out.update(_without(fields, self.expanded(given)))
		return out

	def measuredKey(self, name: str, given: Optional[Dict[str, Any]] = None) -> Optional[str]:
		"""The data key whose scale property `name` sets (`display.range.min` or `.max` on an item with a `key`), else None."""
		values = {n: s.default for n, s in self.props.items()}
		values.update(given or {})
		for _, node in self.walk():
			if any(wholeRef(getField(node, f)) == name for f in ('display.range.min', 'display.range.max')):
				key = node.get('key')
				ref = wholeRef(key)
				return str(values.get(ref)) if ref in values else (key if isinstance(key, str) and not ref else None)
		return None

	# the tree

	def node(self, path: Path) -> Optional[dict]:
		node = self.template
		for i in path:
			kids = node.get(ITEMS_KEY)
			if not isinstance(kids, list) or not 0 <= i < len(kids):
				return None
			node = kids[i]
		return node

	def walk(self) -> Iterator[Tuple[Path, dict]]:
		def go(node, path):
			yield path, node
			for i, kid in enumerate(node.get(ITEMS_KEY) or []):
				yield from go(kid, path + (i,))
		yield from go(self.template, ())

	def add(self, parent: Path, item: dict, index: Optional[int] = None) -> Path:
		node = self.node(parent)
		kids = node.setdefault(ITEMS_KEY, [])
		at = len(kids) if index is None else index
		kids.insert(at, item)
		return parent + (at,)

	def remove(self, path: Path) -> None:
		if path:
			del self.node(path[:-1])[ITEMS_KEY][path[-1]]

	def move(self, path: Path, by: int) -> Path:
		if not path:
			return path
		kids = self.node(path[:-1])[ITEMS_KEY]
		to = max(0, min(len(kids) - 1, path[-1] + by))
		kids.insert(to, kids.pop(path[-1]))
		return path[:-1] + (to,)

	def duplicate(self, path: Path) -> Path:
		if not path:
			return path
		kids = self.node(path[:-1])[ITEMS_KEY]
		kids.insert(path[-1] + 1, copy.deepcopy(kids[path[-1]]))
		return path[:-1] + (path[-1] + 1,)

	#: What stays on the use when an item becomes a preset: where it sits and when it shows, not what it is.
	USE_FIELDS = ('name', 'geometry', 'flex', 'grid', 'when')

	def extract(self, path: Path, name: str) -> 'Piece':
		"""Turn the item at `path` into a preset called `name`: the item takes its place as a use of it, and the new preset is returned.

		Placement (`geometry`, `flex`, `grid`, `when`, `name`) stays on the use, so the preset can sit anywhere. A property of this
		preset that the item reads becomes a property of the new one with the same default, and the use passes it through
		(`props: {x: $x}`), so the item looks as it did.
		"""
		if not path:
			raise ValueError('The whole template is already the preset; pick an item inside it')
		node = self.node(path)
		if node is None:
			raise ValueError('No such item')
		if PRESET_KEY in node:
			raise ValueError('That item is already a use of a preset')
		template = copy.deepcopy(node)
		use: Dict[str, Any] = {PRESET_KEY: name}
		for key in self.USE_FIELDS:
			if key in template:
				use[key] = template.pop(key)
		used = [n for n in self.props if n in set(refs(template))]
		if used:
			use[PROPS_KEY] = {n: f'${n}' if n.isidentifier() else f'${{{n}}}' for n in used}
		piece = Piece(name, {n: copy.deepcopy(self.props[n]) for n in used}, template)
		self.node(path[:-1])[ITEMS_KEY][path[-1]] = use
		return piece

	# properties

	def uniqueName(self, wish: str) -> str:
		base = re.sub(r'[^\w-]+', '-', wish).strip('-') or 'prop'
		name, n = base, 2
		while name in self.props:
			name, n = f'{base}-{n}', n + 1
		return name

	def rename(self, old: str, new: str) -> None:
		"""Rename a property and every `$old` in the template."""
		if old == new or old not in self.props:
			return
		spec = self.props.pop(old)
		spec.name = new
		self.props[new] = spec
		self.template = _rename(self.template, old, new)

	def drop(self, name: str) -> None:
		"""Remove a property; every field that used it takes the default as a plain value."""
		spec = self.props.pop(name, None)
		if spec is not None:
			self.template = substitute(self.template, {name: spec.default})


def _rename(node: Any, old: str, new: str) -> Any:
	if isinstance(node, dict):
		return {k: _rename(v, old, new) for k, v in node.items()}
	if isinstance(node, list):
		return [_rename(v, old, new) for v in node]
	if isinstance(node, str):
		return _REF.sub(lambda m: ('${%s}' if m.group(1) else '$%s') % new if (m.group(1) or m.group(2)) == old else m.group(0), node)
	return node


def setField(node: dict, field_: str, value: Any) -> None:
	"""Set `a.b.c` on a node, creating mappings on the way; a value of None removes the field and any mapping it empties."""
	parts = field_.split('.')
	chain = [node]
	for p in parts[:-1]:
		chain.append(chain[-1].setdefault(p, {}) if value is not None else chain[-1].get(p, {}))
	if value is None:
		chain[-1].pop(parts[-1], None)
		for p, parent, child in zip(reversed(parts[:-1]), reversed(chain[:-1]), reversed(chain[1:])):
			if child == {}:
				parent.pop(p, None)
	else:
		chain[-1][parts[-1]] = value


def getField(node: dict, field_: str, default: Any = None) -> Any:
	cur: Any = node
	for p in field_.split('.'):
		if not isinstance(cur, dict) or p not in cur:
			return default
		cur = cur[p]
	return cur
