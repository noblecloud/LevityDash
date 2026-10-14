"""Dev-only: write changed data back into a YAML file without disturbing the rest of it.

`patch(text, data)` returns `text` edited so that it loads as `data`. Every part of the file that did not change
is copied from the original text, byte for byte: its comments, blank lines, flow-style mappings, quoting and the
order of its keys. Only what changed is written again. A changed scalar replaces its line. A changed mapping or
list is patched entry by entry. A new entry is written in the style of the file around it (flow for a small
mapping of plain values). An entry that was removed takes the comment lines above it away with it.

The result is checked: it must load to exactly `data`. If the file uses something the patcher does not follow
(anchors and aliases, tags, a multi-document file, tabs) or the check fails, `patch` falls back to a plain dump
of `data` and says so (`Patched.exact` is False), so a save never writes something other than what was asked.
"""
import copy
import re
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

import yaml
from yaml.nodes import CollectionNode, MappingNode, Node, ScalarNode, SequenceNode


@dataclass
class Patched:
	text: str
	#: True when unchanged parts were kept from the original; False when the file was written afresh.
	exact: bool
	why: str = ''


class _Unsupported(Exception):
	pass


def dump(data: Any) -> str:
	"""Block-style YAML in the shape the boards use: sequences under a key start at the key's column."""
	return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False, width=120)


def _scalar(value: Any) -> str:
	out = yaml.safe_dump(value, sort_keys=False, allow_unicode=True, default_flow_style=True, width=10 ** 6)
	return out.replace('\n...\n', '').rstrip('\n')


def _flow(value: Any) -> str:
	return _scalar(value)


def _small(value: Any) -> bool:
	"""A mapping of plain values that reads well on one line (`{x: 0%, y: 0%}`)."""
	return isinstance(value, dict) and 0 < len(value) <= 6 and all(not isinstance(v, (dict, list)) for v in value.values()) and len(_flow(value)) <= 72


def _indent(lines: List[str], by: int) -> List[str]:
	if by == 0:
		return list(lines)
	if by > 0:
		pad = ' ' * by
		return [pad + l if l.strip() else l for l in lines]
	n = -by
	out = []
	for l in lines:
		if l.strip() and not l.startswith(' ' * n):
			raise _Unsupported('cannot shift a line left')
		out.append(l[n:] if l.strip() else l)
	return out


class _Source:
	def __init__(self, text: str):
		if '\t' in text:
			raise _Unsupported('tabs')
		self.lines = text.split('\n')
		docs = list(yaml.compose_all(text, Loader=yaml.SafeLoader))
		if len(docs) != 1:
			raise _Unsupported('not exactly one document')
		self.root = docs[0]
		self._check(self.root, set())
		self._cache = {}

	def _check(self, node: Node, seen: set):
		if id(node) in seen:
			raise _Unsupported('anchors and aliases')
		seen = seen | {id(node)}
		if isinstance(node, CollectionNode):
			if node.tag not in ('tag:yaml.org,2002:map', 'tag:yaml.org,2002:seq'):
				raise _Unsupported('tags')
			for child in node.value:
				if isinstance(node, MappingNode):
					self._check(child[0], seen)
					self._check(child[1], seen)
				else:
					self._check(child, seen)

	def value(self, node: Node) -> Any:
		if id(node) not in self._cache:
			self._cache[id(node)] = yaml.SafeLoader.construct_object(_loader(), node, deep=True)
		return self._cache[id(node)]

	def last(self, node: Node) -> int:
		"""The last line a node's text occupies."""
		if isinstance(node, ScalarNode):
			m = node.end_mark
			return m.line if m.column > 0 else m.line - 1
		if node.flow_style:
			m = node.end_mark
			return m.line if m.column > 0 else m.line - 1
		if isinstance(node, MappingNode):
			return self.last(node.value[-1][1]) if node.value else node.start_mark.line
		return self.last(node.value[-1]) if node.value else node.start_mark.line


def _loader():
	return yaml.SafeLoader('')


@dataclass
class _Entry:
	key: Any
	lead: List[str]
	text: List[str]
	value: Node
	value_py: Any
	kline: int = 0


class _Patcher:
	def __init__(self, src: _Source):
		self.src = src

	# the entries of an old block node, each with the comment and blank lines that lead it

	def entries(self, node: MappingNode, start: int) -> List[_Entry]:
		out, prev = [], start - 1
		for i, (k, v) in enumerate(node.value):
			kline = k.start_mark.line
			lead = self.src.lines[prev + 1:kline] if i or kline > start else []
			end = self.src.last(v)
			out.append(_Entry(self.src.value(k), lead, self.src.lines[kline:end + 1], v, self.src.value(v), kline))
			prev = end
		return out

	def elements(self, node: SequenceNode, start: int) -> List[_Entry]:
		out, prev = [], start - 1
		for e in node.value:
			line = e.start_mark.line
			end = self.src.last(e)
			out.append(_Entry(None, self.src.lines[prev + 1:line], self.src.lines[line:end + 1], e, self.src.value(e), line))
			prev = end
		return out

	# emitting

	def fresh(self, key: Any, value: Any, col: int, flow: bool) -> List[str]:
		if isinstance(value, (dict, list)) and not value:
			return [' ' * col + f'{_scalar(key)}: {_flow(value)}']
		if flow or (_small(value) and isinstance(value, dict)):
			return [' ' * col + f'{_scalar(key)}: {_flow(value)}']
		if not isinstance(value, (dict, list)):
			return [' ' * col + f'{_scalar(key)}: {_scalar(value)}']
		body = dump({key: value}).rstrip('\n').split('\n')
		return _indent(body, col)

	def fresh_element(self, value: Any, col: int) -> List[str]:
		if not isinstance(value, (dict, list)) or not value:
			return [' ' * col + '- ' + _scalar(value)]
		body = dump([value]).rstrip('\n').split('\n')
		return _indent(body, col)

	def dashed(self, lines: List[str], col: int, ecol: int) -> List[str]:
		"""Turn mapping lines at `ecol` into a list element whose dash sits at `col`."""
		first = lines[0]
		return [' ' * col + '- ' + first[ecol:]] + lines[1:] if first.startswith(' ' * ecol) else [' ' * col + '- ' + first.lstrip()] + lines[1:]

	def undash(self, text: List[str]) -> List[str]:
		"""The first entry of a mapping that shares its line with a dash: turn the dash into spaces."""
		m = re.match(r'^(\s*)-(\s+)', text[0])
		if not m:
			return list(text)
		width = len(m.group(0))
		return [' ' * width + text[0][width:]] + list(text[1:])

	def mapping(self, new: dict, node: MappingNode, start: int, inline_first: bool) -> List[str]:
		"""Lines for `new`, patched from the block mapping `node`; entries sit at the old column."""
		col = node.value[0][0].start_mark.column if node.value else 0
		old = self.entries(node, start)
		by_key = {e.key: (i, e) for i, e in enumerate(old)}
		out: List[str] = []
		for j, (k, v) in enumerate(new.items()):
			hit = by_key.get(k)
			if hit is None:
				out += self.fresh(k, v, col, False)
				continue
			i, e = hit
			text = self.undash(e.text) if i == 0 and inline_first else e.text
			lead = [] if (i == 0 and inline_first) else e.lead
			if e.value_py == v and type(e.value_py) is type(v):
				out += lead + text
				continue
			out += lead + self.entry(k, v, e, text, col)
		return out

	def entry(self, key: Any, new: Any, old: _Entry, text: List[str], col: int) -> List[str]:
		node = old.value
		block = isinstance(node, (MappingNode, SequenceNode)) and not node.flow_style and node.start_mark.line > old.kline
		if block and isinstance(node, MappingNode) and isinstance(new, dict) and new:
			return [text[0]] + self.mapping(new, node, old.kline + 1, False)
		if block and isinstance(node, SequenceNode) and isinstance(new, list) and new:
			return [text[0]] + self.sequence(new, node, old.kline + 1)
		flow = isinstance(node, CollectionNode) and node.flow_style
		return self.fresh(key, new, col, bool(flow) and isinstance(new, (dict, list)))

	def sequence(self, new: list, node: SequenceNode, start: int) -> List[str]:
		col = node.start_mark.column
		old = self.elements(node, start)
		matched: List[Optional[Tuple[int, bool]]] = [None] * len(new)
		used = set()
		for j, n in enumerate(new):
			for i, e in enumerate(old):
				if e.value_py == n and type(e.value_py) is type(n):
					matched[j] = (i, True)
					used.add(i)
					break
		for j, n in enumerate(new):
			if matched[j] is not None:
				continue
			pick = None
			if j < len(old) and j not in used and self._alike(old[j].value_py, n):
				pick = j
			elif isinstance(n, dict) and n.get('name') is not None:
				for i, e in enumerate(old):
					if i not in used and isinstance(e.value_py, dict) and e.value_py.get('name') == n.get('name'):
						pick = i
						break
			if pick is not None:
				matched[j] = (pick, False)
				used.add(pick)
		out: List[str] = []
		for j, n in enumerate(new):
			m = matched[j]
			if m is None:
				out += self.fresh_element(n, col)
				continue
			i, same = m
			e = old[i]
			if same:
				out += e.lead + e.text
				continue
			out += e.lead + self.element(n, e, col)
		return out

	@staticmethod
	def _alike(a: Any, b: Any) -> bool:
		return (isinstance(a, dict) and isinstance(b, dict)) or (isinstance(a, list) and isinstance(b, list))

	def element(self, new: Any, old: _Entry, col: int) -> List[str]:
		node = old.value
		if isinstance(node, MappingNode) and not node.flow_style and isinstance(new, dict) and new and node.value:
			ecol = node.value[0][0].start_mark.column
			lines = self.mapping(new, node, node.start_mark.line, True)
			return self.dashed(lines, col, ecol)
		if isinstance(node, SequenceNode) and not node.flow_style and isinstance(new, list) and new:
			# A list inside a list: patch it as a fresh dashed block (rare in a dashboard).
			return self.fresh_element(new, col)
		if isinstance(node, CollectionNode) and node.flow_style:
			return [' ' * col + '- ' + _flow(new)]
		return self.fresh_element(new, col)


def patch(text: str, data: Any) -> Patched:
	"""`text` edited to load as `data`; see the module docstring."""
	try:
		src = _Source(text)
		root = src.root
		if isinstance(root, MappingNode) and not root.flow_style and isinstance(data, dict) and data and root.value:
			body = _Patcher(src).mapping(data, root, 0, False)
		elif isinstance(root, SequenceNode) and not root.flow_style and isinstance(data, list) and data and root.value:
			body = _Patcher(src).sequence(data, root, 0)
		else:
			raise _Unsupported('the root is not a block mapping or list')
		tail = src.lines[src.last(root) + 1:]
		out = '\n'.join(body + tail)
		if not out.endswith('\n'):
			out += '\n'
		if yaml.safe_load(out) != data:
			raise _Unsupported('the patched text did not load back to the data')
		return Patched(out, True)
	except (_Unsupported, yaml.YAMLError, IndexError) as e:
		return Patched(dump(data), False, str(e))
