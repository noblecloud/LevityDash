"""Presets: a whole item, written once, used with only what differs.

A preset is a file `<name>.yaml` in a `presets/` folder (the config folder first, then the ones that
ship with the app). It names its own properties, with defaults, and a `template` that uses them:

```yaml
props:
  key: environment.temperature.temperature
  accent: $orange                       # a bare value is a default ...
  hi: {default: 110, type: number, min: 0, max: 200, doc: Top of the scale}   # ... or a full declaration
template:
  type: group
  items:
    - {type: realtime.gauge, key: $key, display: {arc: {gradient: $accent}, range: {max: $hi}}}
```

A board uses it with `preset:`, `props:` for the properties it changes, and any other field it
wants to change, which is merged over the template (mappings merge, lists and values replace):

```yaml
- preset: temp-dial
  name: outside
  props: {accent: $blue}
  geometry: {x: 0%, y: 0%, width: 50%, height: 100%}
```

- `$prop` is replaced anywhere in the template, sub-items included. A value that is exactly `$prop`
  keeps its type. A name that is not a property is left alone, so root `vars:` and theme tokens still
  work: item props, then preset defaults, then `vars:`, then the theme.
- A preset may use another preset. A cycle is an error.
- Where `preset:` is not the name of a preset file it is left alone: `Stack.preset` (the defaults for
  a stack's items) keeps working.
- A save writes `preset`, the `props` as the file had them, and only the fields whose live value
  differs from what the preset gives (`collapse`). Lists are written whole when any item differs.
- A bad preset (unknown name, unknown property, wrong type) becomes an error tile in place of that
  item (`failed`); the rest of the board loads.

Qt-free, like `lib/variables.py`. The names of the three keys are constants below.
"""
import logging
import re
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Dict, Iterable, List, Optional

import yaml

from LevityDash.lib.variables import _same, retemplate, substitute

__all__ = [
	'PresetError', 'Preset', 'Prop', 'PRESET', 'PROPS', 'TEMPLATE', 'FAILED', 'add_search_path', 'available', 'collapse',
	'expand', 'expand_use', 'is_instance', 'load', 'merge', 'search_paths',
]

log = logging.getLogger("LevityDash.presets")

#: The three words of the format. One place, so a rename touches one line.
PRESET = 'preset'
PROPS = 'props'
TEMPLATE = 'template'
#: `type` of a node whose preset could not be expanded; the item loader turns it into an error tile.
FAILED = 'preset-error'

_RESOURCES = Path(__file__).resolve().parents[1] / 'resources' / 'presets'
_DEPTH = 8
_TYPES = {
	'number': lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
	'size': lambda v: isinstance(v, (int, float, str)) and not isinstance(v, bool),
	'text': lambda v: isinstance(v, str),
	'key': lambda v: isinstance(v, str),
	'color': lambda v: isinstance(v, (str, dict, list)),
	'bool': lambda v: isinstance(v, bool),
}


class PresetError(ValueError):
	"""A preset file is wrong, or an item uses one wrongly."""


@dataclass(frozen=True)
class Prop:
	"""One declared property. `type` is optional and checked only for values that are not a `$reference`."""
	name: str
	default: Any = None
	type: Optional[str] = None
	min: Optional[float] = None
	max: Optional[float] = None
	doc: str = ''

	def check(self, value: Any) -> None:
		if isinstance(value, str) and ('$' in value):
			return  # a variable or token: only known once the file is resolved
		if self.type is not None and value is not None and not _TYPES[self.type](value):
			raise PresetError(f'property {self.name!r} is {self.type}, not {value!r}')
		if self.type == 'number' and isinstance(value, (int, float)):
			if self.min is not None and value < self.min or self.max is not None and value > self.max:
				raise PresetError(f'property {self.name!r} is {value}, outside {self.min} to {self.max}')


def _prop(name: str, raw: Any) -> Prop:
	if isinstance(raw, dict) and 'default' in raw:
		unknown = set(raw) - {'default', 'type', 'min', 'max', 'doc'}
		if unknown:
			raise PresetError(f'property {name!r} has unknown settings {sorted(unknown)}')
		kind = raw.get('type')
		if kind is not None and kind not in _TYPES:
			raise PresetError(f'property {name!r} has unknown type {kind!r}; types are {", ".join(_TYPES)}')
		return Prop(name, raw['default'], kind, raw.get('min'), raw.get('max'), str(raw.get('doc', '')))
	return Prop(name, raw)


@dataclass
class Preset:
	name: str
	props: Dict[str, Prop]
	template: dict
	source: str = ''
	doc: str = ''

	def values(self, given: Optional[dict]) -> Dict[str, Any]:
		"""The value of every property: what `given` sets, else the default. A default may use an earlier property."""
		given = dict(given or {})
		unknown = set(given) - set(self.props)
		if unknown:
			raise PresetError(f'preset {self.name!r} has no {"property" if len(unknown) == 1 else "properties"} {", ".join(sorted(unknown))}. It has: {", ".join(self.props) or "none"}')
		values: Dict[str, Any] = {}
		for name, prop in self.props.items():
			if name in given:
				prop.check(given[name])
				values[name] = given[name]
			else:
				values[name] = substitute(prop.default, values)
		return values

	def instance(self, given: Optional[dict] = None, fields: Optional[dict] = None, _stack: tuple = ()) -> dict:
		"""The item this preset makes with `given` properties and `fields` merged over it. Nested presets are expanded."""
		if self.name in _stack or len(_stack) >= _DEPTH:
			raise PresetError(f'presets use each other in a loop: {" > ".join((*_stack, self.name))}')
		item = _apply(deepcopy(self.template), self.values(given))
		if item is _GONE:
			item = {}
		if fields:
			item = merge(item, fields)
		if isinstance(item, dict) and 'items' in item:
			item['items'] = item.pop('items')  # an item takes its own geometry and settings before its children are built
		return _walk(item, (*_stack, self.name))


_REFERENCE = re.compile(r'^\$(?:(\w[\w-]*)|\{(\w[\w-]*)\})$')


def _name(text: Any, values: Dict[str, Any]) -> Optional[str]:
	"""The property that `text` is exactly a reference to, else None."""
	if isinstance(text, str) and (found := _REFERENCE.match(text)):
		if (name := found.group(1) or found.group(2)) in values:
			return name
	return None


_GONE = object()


def _apply(node: Any, values: Dict[str, Any]) -> Any:
	"""`node` with the properties filled in.

	Beyond `substitute`: a mapping key that is exactly `$prop` takes the property's text, so a series can be named by a
	property; and an entry whose key or value is exactly `$prop` for a property that is `null` is left out
	(a list item that is exactly such a `$prop` too), so an optional setting costs nothing when it is not set. A mapping that
	this empties is left out as well.
	"""
	if isinstance(node, dict):
		out: dict = {}
		dropped = False
		for key, value in node.items():
			if (name := _name(key, values)) is not None:
				if values[name] is None:
					dropped = True
					continue
				if not isinstance(values[name], str):
					raise PresetError(f'property {name!r} is used as a key, so it must be text, not {values[name]!r}')
				key = values[name]
			if (name := _name(value, values)) is not None and values[name] is None:
				dropped = True
				continue
			value = _apply(value, values)
			if value is _GONE:
				dropped = True
				continue
			out[key] = value
		return _GONE if dropped and not out else out
	if isinstance(node, list):
		kept = [item for item in node if not ((name := _name(item, values)) is not None and values[name] is None)]
		return [item for item in (_apply(item, values) for item in kept) if item is not _GONE]
	return deepcopy(substitute(node, values))


def merge(base: Any, over: Any) -> Any:
	"""`over` on `base`: mappings merge key by key, anything else in `over` replaces."""
	if isinstance(base, dict) and isinstance(over, dict):
		out = dict(base)
		for key, value in over.items():
			out[key] = merge(base[key], value) if key in base else value
		return out
	return deepcopy(over)


# Section: files

_lock = RLock()
_cache: Dict[str, Preset] = {}
_search: List[Callable[[], Iterable[Path]]] = []

# Same rule as `YAMLPreprocessor` in CentralPanel: a bare hex colour after `color:` is not a comment.
_COLOUR = re.compile(r"(?<=color\:)\s*?#*?(?P<color>[A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})", re.MULTILINE)


def add_search_path(provider: Callable[[], Iterable[Path]]):
	"""Register a function giving directories to look for `<name>.yaml` in, before the built-in one."""
	_search.append(provider)
	_cache.clear()


def _user_presets() -> List[Path]:
	# Looked up on each search, not at import: the config folder is decided after this module loads.
	from LevityDash.lib.config import userConfig
	return [Path(userConfig.userPath.path) / 'presets']


def search_paths() -> List[Path]:
	paths: List[Path] = []
	for provider in _search:
		try:
			paths.extend(Path(p) for p in provider())
		except Exception:
			log.exception('preset search path provider failed')
	paths.append(_RESOURCES)
	return paths


add_search_path(_user_presets)


def available() -> List[str]:
	return sorted({p.stem for d in search_paths() if d.is_dir() for p in d.glob('*.yaml')})


def _find(name: str) -> Optional[Path]:
	if not isinstance(name, str) or not re.fullmatch(r'[\w.-]+', name):
		return None
	for directory in search_paths():
		path = directory / f'{name}.yaml'
		if path.is_file():
			return path
	return None


def parse(name: str, text: str, source: str = '') -> Preset:
	data = yaml.safe_load(_COLOUR.sub(" \\g<color>", text)) or {}
	if not isinstance(data, dict) or not isinstance(data.get(TEMPLATE), dict):
		raise PresetError(f'preset {name!r}: a preset is a mapping with a {TEMPLATE!r} mapping')
	declared = data.get(PROPS) or {}
	if not isinstance(declared, dict):
		raise PresetError(f'preset {name!r}: {PROPS!r} is a mapping of names to defaults')
	unknown = set(data) - {PROPS, TEMPLATE, 'doc'}
	if unknown:
		raise PresetError(f'preset {name!r}: unknown top-level {"key" if len(unknown) == 1 else "keys"} {", ".join(sorted(map(str, unknown)))}')
	return Preset(name, {str(k): _prop(str(k), v) for k, v in declared.items()}, data[TEMPLATE], source, str(data.get('doc', '')))


def load(name: str) -> Optional[Preset]:
	"""The preset called `name`, or None when there is no such file. Raises `PresetError` for a file that is wrong."""
	with _lock:
		if name in _cache:
			return _cache[name]
		path = _find(name)
		if path is None:
			return None
		try:
			preset = parse(name, path.read_text(encoding='utf-8'), str(path))
		except yaml.YAMLError as error:
			raise PresetError(f'{path}: {error}') from error
		_cache[name] = preset
		return preset


def clear_cache():
	with _lock:
		_cache.clear()


# Section: expanding a file

def is_instance(node: Any) -> bool:
	"""A mapping whose `preset:` names a preset file."""
	if not isinstance(node, dict) or not isinstance(node.get(PRESET), str):
		return False
	try:
		return load(node[PRESET]) is not None
	except PresetError:
		return True  # a broken file is still the author's intent; expansion reports it


def expand_use(use: dict, stack: tuple = ()) -> dict:
	"""The item one `preset:` use makes. Raises `PresetError` instead of making a failed node."""
	preset = load(use[PRESET])
	given = use.get(PROPS)
	if given is not None and not isinstance(given, dict):
		raise PresetError(f'{PROPS!r} is a mapping of property names to values')
	fields = {k: v for k, v in use.items() if k not in (PRESET, PROPS)}
	return preset.instance(given, fields, stack)


def _failed(node: dict, error: Exception) -> dict:
	log.error(f'preset {node.get(PRESET)!r} could not be used: {error}')
	out = {'type': FAILED, 'message': str(error)}
	for key in ('name', 'geometry'):
		if key in node:
			out[key] = node[key]
	return out


def _expand_instance(node: dict, stack: tuple) -> dict:
	try:
		return expand_use(node, stack)
	except Exception as error:  # one bad use must not cost the board
		if stack:
			raise  # inside another preset: the outermost use fails, with this reason
		return _failed(node, error)


def _walk(node: Any, stack: tuple = ()) -> Any:
	if isinstance(node, dict):
		if is_instance(node):
			return _expand_instance(node, stack)
		return {key: _walk(value, stack) for key, value in node.items()}
	if isinstance(node, list):
		return [_walk(value, stack) for value in node]
	return node


def expand(state: Any) -> Any:
	"""The root of a dashboard with every preset use replaced by the item it makes. The input is not changed.

	Run before `resolveVariables`, so a preset's text can use the file's `vars:`.
	"""
	try:
		if isinstance(state, dict):
			return {key: (value if key == 'vars' else _walk(value)) for key, value in state.items()}
		return _walk(state)
	except Exception:
		log.exception('presets could not be expanded; the file loads as written')
		return state


# Section: saving

def _equal(a: Any, b: Any) -> bool:
	if isinstance(a, dict) and isinstance(b, dict):
		return a.keys() == b.keys() and all(_equal(a[k], b[k]) for k in a)
	if isinstance(a, list) and isinstance(b, list):
		return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b))
	return _same(a, b) or _same(b, a)


_MISSING = object()


def _fold(live: dict, base: dict, written: dict, collapse_: Callable) -> dict:
	"""The fields of `live` that differ from `base`, with the text of any field the file wrote while it still holds.

	`base` is the item as it loaded, in the app's own dump form, and `written` the fields the file wrote for it.
	"""
	out: dict = {}
	for key, value in live.items():
		here = base.get(key, _MISSING)
		wrote = written.get(key, _MISSING)
		if here is not _MISSING and _equal(value, here):
			if wrote is not _MISSING:
				out[key] = wrote  # the file set it, and it still holds: keep the file's text
			continue
		if isinstance(value, dict) and isinstance(here, dict):
			if part := _fold(value, here, wrote if isinstance(wrote, dict) else {}, collapse_):
				out[key] = part
		elif wrote is not _MISSING and here is not _MISSING:
			out[key] = retemplate(value, here, wrote, collapse_)
		else:
			out[key] = value
	return out


def collapse(live: Any, written: dict, loaded: Any = None, variables: Optional[dict] = None, collapse_: Optional[Callable] = None) -> Any:
	"""A preset use as it should be saved: `written`'s `preset` and `props`, and the fields of `live` that differ from the preset.

	`live` is the item as the app would save it now, `written` the use as the file had it, `loaded` the same item as
	the app dumped it right after loading (the baseline; without it the preset's own expansion is used, which is
	only exact when the app adds nothing on a dump) and `variables` the file's resolved `vars:`.
	Returns None when this cannot be done, and the caller saves the full item.
	"""
	try:
		if not isinstance(live, dict) or not is_instance(written):
			return None
		variables = variables or {}
		hook = collapse_ or (lambda item, wrote, base: collapse(item, wrote, base, variables))
		given = written.get(PROPS)
		if not isinstance(loaded, dict):
			loaded = substitute(expand_use(written), variables)
		fields = {k: v for k, v in written.items() if k not in (PRESET, PROPS)}
		out: dict = {PRESET: written[PRESET]}
		if given:
			out[PROPS] = given
		out.update(_fold(live, loaded, fields, hook))
		return out
	except Exception:
		log.exception('a save could not fold a preset back; it writes the full item')
		return None


