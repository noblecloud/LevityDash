"""Dev-only: turn a live `Stateful` tree into a description of controls. Gauge Studio.

The studio does not list the gauge's options by hand. It walks
`type(owner).statefulItems` on the gauge, then on every part the gauge holds
(arc, needle, ticks, tick labels, value label, ...) and describes one control
per settable property. A property added to `Gauge.py` appears here with no edit.

A property has no declared widget type. The control kind comes from what the
property returns and what its current value is:

======= ==========================================================
kind    chosen when
======= ==========================================================
group   the value is itself a `Stateful` (a part with its own properties)
bool    the value is a `bool`
enum    the value, or a declared return type, is an `Enum`
color   a declared return type is `Color`
number  the value is a plain `int` or `float`
percent the saved text is a percentage such as `5%`
text    anything else with a short saved form: `4mm`, `Nunito`, `1.5`
yaml    the saved form is a mapping, list or set
======= ==========================================================

`_refine` then swaps a plain text or YAML control for a structured editor
(`_studio_editors.py`) when the property is one the studio knows: sizes get a
number and a unit, `fill`, `zones`, `markers` and the captions get forms,
gradients and tick label text get lists, and so on. A property the studio does
not know keeps the plain control.

The saved form is what `StateProperty.encodeValue` returns: the same text a
`.levity` file holds. Writing goes through `StateProperty.__set__`, the call a
file load makes. That keeps validation, the decoder and the `after` hooks.
"""
import inspect
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional, Union

import yaml
import WeatherUnits as wu
from statekit.core import Stateful, StateProperty
from statekit.yaml import StatefulDumper
from statekit.validate import StateError
from qolkit import Unset
from LevityDash.lib.ui.colors import Gradient

#: Properties that are not about how a gauge looks: plumbing, layout of the
#: panel itself, or text the gauge computes.
SKIP_KEYS = frozenset({
	'shared', 'type', 'geometry', 'margins', 'border', 'movable', 'resizable', 'locked', 'frozen',
	'filters', 'items', 'matchingGroup', 'modifiers', 'name', 'icon', 'padding', 'text',
	'format-hint', 'text-scale-type', 'displayType', 'center_offset',
})

#: Text the studio edits although the gauge computes a default for it: the tick label words.
UNSKIP = {('text_map',)}

MAX_DEPTH = 4

#: Needle types that use a needle property. A property not listed here applies to every type.
NEEDLE_USES = {
	'hub': {'needle', 'tapered', 'line'}, 'hub-color': {'needle', 'tapered', 'line'}, 'hub-hole': {'needle', 'tapered', 'line'},
	'tail': {'tapered', 'arrow', 'line'}, 'tail-dot': {'line', 'arrow'}, 'head': {'arrow'}, 'point': {'arrow'},
	'halo': {'dot'}, 'halo-color': {'dot'},
}

ALIGNMENTS = ['Center', 'Left', 'Right', 'Top', 'Bottom']
ANCHORS = ['top-left', 'top-right', 'bottom-left', 'bottom-right']

_PERCENT = re.compile(r'^\s*-?\d+(\.\d+)?\s*%\s*$')


@dataclass
class Field:
	"""One control: a property at `path` (property keys from the gauge down)."""
	path: tuple
	kind: str
	choices: List[tuple] = field(default_factory=list)  # (label, saved text) for enum
	lo: float = 0.0
	hi: float = 1.0
	step: float = 0.01
	integer: bool = False
	doc: str = ''
	nullable: bool = False
	suffix: str = ''
	#: A number in the gauge's own unit (degrees F, inHg, mph): the studio adds the unit symbol.
	measured: bool = False
	#: Needle types that use the property. None means every type.
	types: Optional[frozenset] = None

	@property
	def key(self) -> str:
		return self.path[-1]


@dataclass
class Group:
	"""A part with properties of its own, shown as a collapsible section."""
	path: tuple
	title: str
	fields: List[Field] = field(default_factory=list)
	groups: List['Group'] = field(default_factory=list)

	def count(self) -> int:
		return len(self.fields) + sum(g.count() for g in self.groups)

	def walk(self):
		yield from self.fields
		for g in self.groups:
			yield from g.walk()


# Section: reading and writing

def findProp(owner: Stateful, key: str) -> Optional[StateProperty]:
	for prop in type(owner).statefulItems.values():
		if prop.key == key:
			return prop
	return None


def resolve(root: Stateful, path: tuple) -> Optional[Stateful]:
	"""The part at `path`, or None when it is gone."""
	owner = root
	for key in path:
		prop = findProp(owner, key)
		if prop is None:
			return None
		try:
			owner = prop.fget(owner)
		except Exception:
			return None
		if not isinstance(owner, Stateful):
			return None
	return owner


def saved(prop: StateProperty, raw: Any, owner: Stateful) -> Any:
	"""The form a `.levity` file holds for `raw`: the dumper's own text, read back.

	`encodeValue` alone is not enough. Most gauge properties have no encoder, so
	it hands back a `Size`, an `Enum` or a `Color`. The YAML dumper knows how to
	write each of those, so the studio asks it and parses the text.
	"""
	if raw is None or raw is Unset:
		return None
	if isinstance(raw, Gradient):
		return gradientText(raw)
	try:
		encoded = prop.encodeValue(raw, owner)
		# A plain bool, int or float reads back from its own YAML text as itself. Skip the
		# dump and parse, which is most of what `read` costs.
		if type(encoded) in (bool, int) or (type(encoded) is float and encoded == encoded and abs(encoded) != float('inf')):
			return encoded
		text = yaml.dump(encoded, Dumper=StudioDumper, default_flow_style=True, width=10 ** 6)
		return yaml.safe_load(text)
	except Exception:
		return str(raw)


def gradientText(gradient: Gradient) -> dict:
	"""A gradient as the `{stop: '#rrggbb'}` mapping a `.levity` file holds and the loader reads back.

	A stop written with a unit keeps its own text (`99°F`); a bare number stays a number. The stops
	keep the order they were written in.
	"""
	return {stop.key: stop.color.QColor.name() for stop in dict.values(gradient)}


class StudioDumper(StatefulDumper):
	"""`StatefulDumper` that writes a gradient as a plain mapping (the stock dumper tags it, and a plain loader cannot read the tag)."""


StudioDumper.add_multi_representer(Gradient, lambda dumper, data: dumper.represent_dict(gradientText(data)))


def read(root: Stateful, path: tuple) -> Any:
	"""The saved form of the property at `path`; None when it has no value."""
	owner = resolve(root, path[:-1])
	prop = findProp(owner, path[-1]) if owner is not None else None
	if prop is None:
		return None
	try:
		raw = prop.fget(owner)
	except Exception:
		return None
	return saved(prop, raw, owner)


def write(root: Stateful, path: tuple, value: Any) -> Optional[str]:
	"""Set the property at `path` the way a file load would.

	Returns None on success, or the reason the value was rejected. A rejected
	value leaves the gauge as it was.
	"""
	owner = resolve(root, path[:-1])
	prop = findProp(owner, path[-1]) if owner is not None else None
	if prop is None:
		return 'this property is no longer on the gauge'
	pool = owner.action_pool
	before = read(root, path)
	with _capturingWarnings() as messages:
		try:
			with pool:
				prop.__set__(owner, value, afterPool=pool)
		except StateError as e:
			return e.reason
		except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError) as e:
			return f'{type(e).__name__}: {e}'
	# A decoder that cannot read a value often logs a warning and keeps the old one.
	if messages:
		return messages[0]
	# Some decoders keep the old value and say nothing. Notice that: the gauge now
	# holds what it held before, and that is not what was typed.
	after = read(root, path)
	if value is not None and not _same(value, after) and not _same(_canonical(prop, value, owner), after):
		if _same(after, before):
			return f'the gauge did not take {value!r}; it still holds {after!r}'
		return f'the gauge holds {after!r} instead of {value!r}'
	return None


def _canonical(prop: StateProperty, value: Any, owner: Stateful) -> Any:
	"""What `value` becomes after the property decodes it and saves it again.

	An encoder may drop keys that equal the default (`warp: {radius: 40%}` saves as `true`), so the
	typed form and the held form differ in text while they mean the same.
	"""
	try:
		return saved(prop, prop.decodeValue(value, owner), owner)
	except Exception:  # noqa: BLE001
		return value


def _norm(a: Any) -> str:
	return str(a).replace(' ', '').lower()


def _same(a: Any, b: Any) -> bool:
	"""True when two saved forms say the same thing: `12%` and `12.0%`, `#FF0` and `#ff0`, `5 mm` and `5mm`."""
	if a == b or _norm(a) == _norm(b):
		return True
	try:
		return float(_norm(a).rstrip('%\u00b0')) == float(_norm(b).rstrip('%\u00b0'))
	except ValueError:
		return False


class _capturingWarnings:
	"""Collect the text of every WARNING or worse logged inside the block."""

	def __enter__(self) -> List[str]:
		self.messages: List[str] = []
		self._handle = logging.Logger.handle
		messages = self.messages
		original = self._handle

		def handle(logger, record):
			if record.levelno >= logging.WARNING:
				try:
					messages.append(record.getMessage())
				except Exception:
					pass
			return original(logger, record)

		logging.Logger.handle = handle
		return self.messages

	def __exit__(self, *exc):
		logging.Logger.handle = self._handle
		return False


def toYaml(value: Any) -> str:
	"""The one-line flow form shown in a text field."""
	if value is None:
		return ''
	if isinstance(value, (set, frozenset)):
		value = sorted(value)
	if isinstance(value, (dict, list, tuple)):
		return yaml.safe_dump(value, default_flow_style=True, width=10 ** 6).strip().removesuffix('...').strip()
	return str(value)


def fromText(text: str) -> Any:
	"""Text a person typed, as the value to write. YAML reads numbers, booleans and flow mappings."""
	text = text.strip()
	if text == '':
		return None
	try:
		return yaml.safe_load(text)
	except yaml.YAMLError:
		return text


# Section: describing

def _numberRange(key: str, value: Union[int, float]):
	"""A sensible slider range from the property's key and its current value."""
	if 'angle' in key:
		return -360.0, 360.0, 1.0, True
	if key in ('opacity',):
		return 0.0, 1.0, 0.01, False
	if isinstance(value, int) and not isinstance(value, bool):
		return 0.0, float(max(10, abs(value) * 4)), 1.0, True
	hi = max(1.0, abs(float(value)) * 4)
	lo = -hi if value < 0 else 0.0
	return lo, hi, round(hi / 100, 3), False


def _classify(prop: StateProperty, raw: Any, owner: Stateful) -> Optional[Field]:
	returns = [r for r in prop.returns if isinstance(r, type)]
	enumType = type(raw) if isinstance(raw, Enum) else next((r for r in returns if issubclass(r, Enum)), None)
	if isinstance(raw, bool) or (raw is None and bool in returns and len(returns) == 1):
		return Field((), 'bool')
	if enumType is not None:
		choices = []
		# A property that declares `choices` offers only those members, in that order.
		declared = prop.options.get('choices', None)
		for member in (enumType if declared is None else [m for m in declared if isinstance(m, enumType)]):
			text = saved(prop, member, owner)
			choices.append((text if isinstance(text, str) else str(member.name), text if isinstance(text, (str, int, float)) else member.name))
		return Field((), 'enum', choices=choices)
	if any(r.__name__ == 'Color' for r in returns) or type(raw).__name__ == 'Color':
		return Field((), 'color')
	# A temperature, speed or other measurement on a gauge scale: a number in the gauge's unit.
	if isinstance(raw, wu.Measurement) and not isinstance(raw, (wu.Percentage, wu.Length)):
		lo, hi, step, integer = _numberRange(prop.key, float(raw))
		return Field((), 'number', lo=lo, hi=hi, step=step, integer=integer)
	if type(raw) in (int, float):
		lo, hi, step, integer = _numberRange(prop.key, raw)
		return Field((), 'number', lo=lo, hi=hi, step=step, integer=integer)
	if raw is None and returns and all(r in (int, float) or r.__name__ == 'Measurement' for r in returns):
		return Field((), 'number', lo=0.0, hi=100.0, step=1.0, integer=int in returns and float not in returns)
	text = saved(prop, raw, owner)
	if isinstance(text, (dict, list, tuple, set, frozenset)) or raw is None and any(
		issubclass(r, (dict, list, set, tuple)) for r in returns
	):
		return Field((), 'yaml')
	if isinstance(text, str) and _PERCENT.match(text):
		return Field((), 'percent')
	if isinstance(text, (int, float)) and not isinstance(text, bool):
		lo, hi, step, integer = _numberRange(prop.key, text)
		return Field((), 'number', lo=lo, hi=hi, step=step, integer=integer)
	return Field((), 'text')


def describe(owner: Stateful, path: tuple = (), title: str = 'Gauge', _seen: Optional[set] = None, _depth: int = 0) -> Group:
	"""The controls for `owner` and every part under it."""
	seen = _seen if _seen is not None else set()
	seen.add(id(owner))
	group = Group(path, title)
	for prop in type(owner).statefulItems.values():
		if 'set' not in prop.actions or (prop.key in SKIP_KEYS and (prop.fget.__name__,) not in UNSKIP):
			continue
		try:
			raw = prop.fget(owner)
		except Exception:
			raw = None
		if isinstance(raw, Stateful):
			if id(raw) in seen or _depth >= MAX_DEPTH:
				continue
			sub = describe(raw, path + (prop.key,), prop.key, seen, _depth + 1)
			if sub.count():
				group.groups.append(sub)
			continue
		if raw is Unset:
			raw = None
		found = _classify(prop, raw, owner)
		if found is None:
			continue
		found.path = path + (prop.key,)
		found = _refine(found, prop, raw, owner)
		group.fields.append(found)
	return group


_SIZE_NAMES = ('Height', 'Width', 'Length', 'Dimension')
_MEASURED_KEYS = {'min', 'max', 'interval', 'min-interval', 'round-to'}


def _isSizeType(r: type) -> bool:
	name = getattr(r, '__qualname__', r.__name__)
	return name.endswith(_SIZE_NAMES)


def _refine(found: Field, prop: StateProperty, raw: Any, owner: Stateful) -> Field:
	"""Give the field its tooltip, its unit, and a structured editor when the studio has one."""
	key = found.key
	doc = prop.fget.__doc__ if prop.fget is not None else None
	found.doc = inspect.cleandoc(doc) if doc else ''
	found.nullable = bool(prop.allowNone)
	returns = [r for r in prop.returns if isinstance(r, type)]
	ownerName = type(owner).__name__
	if key == 'fill':
		found.kind = 'fill'
	elif key in ('caption', 'sub-label'):
		found.kind = 'caption'
	elif key == 'warp':
		found.kind = 'warp'
	elif key == 'glow':
		found.kind = 'glow'
	elif key == 'zones':
		found.kind = 'zones'
	elif key == 'markers':
		found.kind = 'markers'
	elif key == 'gradient':
		found.kind = 'gradient'
	elif prop.fget.__name__ == 'text_map':
		found.kind = 'textmap'
	elif key == 'format' and not isinstance(raw, Stateful):
		found.kind = 'format'
	elif key == 'offset' and ownerName.startswith('Gauge') and 'Label' in ownerName + ''.join(c.__name__ for c in type(owner).__mro__):
		found.kind = 'offset'
	elif key == 'font':
		found.kind = 'font'
	elif key == 'alignment':
		found.kind = 'choice'
		found.choices = [('auto', None)] + [(a.lower(), a) for a in ALIGNMENTS]
	elif key == 'anchor':
		found.kind = 'choice'
		found.choices = [('none', None)] + [(a, a) for a in ANCHORS]
	elif key == 'point':
		found.kind = 'choice'
		found.choices = [('out', None), ('in', 'in')]
	elif key.endswith('interval-factors'):
		found.kind = 'intset'
	elif found.kind in ('text', 'percent') and returns and any(_isSizeType(r) for r in returns) and not isinstance(raw, Stateful):
		found.kind = 'size'
	elif found.kind == 'number':
		if 'angle' in key:
			found.suffix = '\u00b0'
		elif key == 'animate':
			found.suffix = ' ms'
			found.integer = True
		elif isinstance(raw, wu.Measurement) or (key in _MEASURED_KEYS and ownerName in ('GaugeRange', 'Graduations')):
			found.measured = True
	if found.kind == 'number' and key in ('opacity',):
		found.kind = 'percent'
	if found.path[:1] == ('needle',) and key in NEEDLE_USES:
		found.types = frozenset(NEEDLE_USES[key])
	return found
