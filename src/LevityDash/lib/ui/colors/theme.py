"""Themes: named tokens (``$accent``, ``$mono``, ``$temperature``) that a dashboard writes in place of raw values.

A theme is a small YAML file. One dashboard picks one theme with a root ``theme:`` key, and every colour, font
and gradient in it may name a token instead of a value. Swapping the theme restyles the board; a raw value
written on an item still wins, because the token is only looked up when the item says ``$name``.

Pure Python, no Qt: the colour work goes through ``Color`` and ``oklch`` lazily.

Theme file::

	name: dusk
	mode: dark                      # dark | light; the beam panel reads it
	extends: default                # missing tokens come from here (default: the built-in theme)
	colors:
	  background: '#0b0b0d'
	  text: '#f2f2f2'
	  muted: {color: $text, alpha: 0.65}   # a token may be built from another one
	fonts:
	  display: Roboto
	  mono: Roboto Mono
	scales:                         # named gradients; same forms as ``gradient:`` in a .levity
	  load: {0: $good, 60: $warn, 90: $bad}

A token has one namespace across the three groups, so ``$mono`` is a font and ``$muted`` a colour, and the
place that reads the value decides which group it wants. A colour may also be a modifier mapping::

	{color: $accent, alpha: 0.4}                  # opacity
	{color: $accent, lighten: 0.1}                # Oklch lightness, + or -; darken is the same, negated
	{color: $accent, chroma: 0.8}                 # Oklch chroma times 0.8
	{color: $accent, hue-shift: 30}               # degrees
	{color: $accent, mix: {with: $background, by: 0.3}}   # 0.3 of the way to the other colour, in Oklab
"""
from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from threading import RLock
from weakref import WeakMethod
import json
from typing import Any, Callable, Iterable, Optional

import yaml

from LevityDash.lib.ui import UILogger

log = UILogger.getChild('Theme')

#: Token groups a theme file holds.
GROUPS = ('colors', 'fonts', 'scales')

#: Keys of a colour modifier mapping, beside ``color``.
MODIFIERS = frozenset({'alpha', 'lighten', 'darken', 'chroma', 'hue-shift', 'mix'})

#: Tokens every theme is expected to define. The built-in ``default`` theme defines all of them, and a theme that
#: leaves one out takes it from the theme it extends.
STANDARD_TOKENS: dict[str, tuple[str, ...]] = {
	'colors': (
		'background', 'surface', 'text', 'muted', 'faint', 'rule', 'accent',
		'good', 'warn', 'bad', 'info',
		'series-1', 'series-2', 'series-3', 'series-4', 'series-5', 'series-6',
		'needle-glow', 'moon', 'moon-shade', 'moon-glow',
	),
	'fonts':  ('display', 'mono', 'body'),
	'scales': ('load', 'temperature', 'sky'),
}

DEFAULT_NAME = 'default'

_RESOURCES = Path(__file__).resolve().parents[3] / 'resources' / 'themes'


class ThemeError(ValueError):
	"""A theme file is wrong, or a token is not in any theme."""


def is_token(value: Any) -> bool:
	"""``$name``: a token reference."""
	return isinstance(value, str) and len(value) > 1 and value[0] == '$' and value[1] not in '{ '


def token_name(value: str) -> str:
	return value[1:].strip()


def is_modifier_spec(value: Any) -> bool:
	return isinstance(value, dict) and 'color' in value and bool(MODIFIERS & set(value))


class Theme:
	"""A parsed theme. Raw token values are kept as written; ``resolve`` turns one into something ``Color`` reads."""

	__slots__ = ('name', 'mode', 'extends', 'tokens', 'source', 'parent')

	def __init__(self, name: str, mode: str = 'dark', extends: Optional[str] = None, tokens: Optional[dict[str, dict]] = None, source: str = '', parent: Optional['Theme'] = None):
		if mode not in ('dark', 'light'):
			raise ThemeError(f'theme {name!r}: mode is dark or light, not {mode!r}')
		self.name = name
		self.mode = mode
		self.extends = extends
		self.tokens = {group: dict((tokens or {}).get(group) or {}) for group in GROUPS}
		self.source = source
		self.parent = parent

	@classmethod
	def decode(cls, data: dict, name: str = 'inline', source: str = '') -> 'Theme':
		unknown = set(data) - {'name', 'mode', 'extends', *GROUPS}
		if unknown:
			raise ThemeError(f'theme {name!r}: unknown keys {sorted(map(str, unknown))}; expected name, mode, extends, {", ".join(GROUPS)}')
		extends = data.get('extends')
		parent = None if extends is None and name == DEFAULT_NAME else load(extends or DEFAULT_NAME)
		mode = data.get('mode') or (parent.mode if parent else 'dark')
		return cls(data.get('name') or name, mode, extends, {g: data.get(g) for g in GROUPS}, source, parent)

	def __repr__(self):
		return f'Theme({self.name!r}, {self.mode})'

	def lookup(self, group: str, token: str) -> Any:
		"""The raw value of ``token`` in ``group``, here or in the theme this one extends."""
		theme = self
		while theme is not None:
			if token in theme.tokens[group]:
				return theme.tokens[group][token]
			theme = theme.parent
		raise KeyError(token)

	def find(self, token: str) -> tuple[str, Any]:
		"""``(group, raw value)`` for a token in any group."""
		for group in GROUPS:
			try:
				return group, self.lookup(group, token)
			except KeyError:
				pass
		raise ThemeError(f'theme {self.name!r} has no token ${token}. Known: {", ".join(sorted(self.names()))}')

	def names(self, group: Optional[str] = None) -> set[str]:
		found = set()
		theme = self
		while theme is not None:
			for g in ((group,) if group else GROUPS):
				found |= set(theme.tokens[g])
			theme = theme.parent
		return found

	# Section: resolving

	def resolve(self, value: Any, group: Optional[str] = None, _seen: tuple = ()) -> Any:
		"""``value`` with every token replaced.

		A ``$name`` string gives its token's value, itself resolved. A colour modifier mapping gives an RGBA
		tuple. Lists and mappings are walked, so a gradient spec resolves its stops. Anything else is returned as is.
		"""
		if is_token(value):
			token = token_name(value)
			if token in _seen:
				raise ThemeError(f'theme {self.name!r}: ${token} refers to itself ({" -> ".join(_seen + (token,))})')
			found, raw = self.find(token) if group is None else (group, self._lookup_in(group, token))
			return self.resolve(raw, found, _seen + (token,))
		if is_modifier_spec(value):
			return self._modified(value, _seen)
		if isinstance(value, dict):
			return {self.resolve(k, None, _seen) if is_token(k) else k: self.resolve(v, None, _seen) for k, v in value.items()}
		if isinstance(value, (list, tuple)):
			return type(value)(self.resolve(v, None, _seen) for v in value)
		return value

	def _lookup_in(self, group: str, token: str) -> Any:
		try:
			return self.lookup(group, token)
		except KeyError:
			# A caller that wants a colour may name a token the theme keeps elsewhere; say which.
			found, _ = self.find(token)
			raise ThemeError(f'theme {self.name!r}: ${token} is a {found[:-1]}, not a {group[:-1]}')

	def _modified(self, spec: dict, _seen: tuple) -> tuple[int, int, int, int]:
		from LevityDash.lib.ui.colors import oklch
		from LevityDash.lib.ui.colors.color import Color

		spec = dict(spec)
		base = Color.decode(self.resolve(spec.pop('color'), 'colors', _seen))
		r, g, b, a = base.red, base.green, base.blue, base.alpha / 255
		L, A, B = oklch.srgb_to_oklab((r / 255, g / 255, b / 255))
		if (by := spec.pop('mix', None)) is not None:
			other = Color.decode(self.resolve(by['with'], 'colors', _seen))
			t = float(by.get('by', 0.5))
			oL, oA, oB = oklch.srgb_to_oklab((other.red / 255, other.green / 255, other.blue / 255))
			L, A, B = L + (oL - L) * t, A + (oA - A) * t, B + (oB - B) * t
			a = a + (other.alpha / 255 - a) * t
		C, h = math.hypot(A, B), math.atan2(B, A)
		L += float(spec.pop('lighten', 0.0)) - float(spec.pop('darken', 0.0))
		C *= float(spec.pop('chroma', 1.0))
		h += math.radians(float(spec.pop('hue-shift', 0.0)))
		if 'alpha' in spec:
			a = float(spec.pop('alpha'))
		if spec:
			raise ThemeError(f'unknown colour modifier keys {sorted(map(str, spec))}')
		triple = oklch.oklab_to_srgb((min(1.0, max(0.0, L)), C * math.cos(h), C * math.sin(h)))
		return (*(int(round(min(1.0, max(0.0, c)) * 255)) for c in triple), int(round(min(1.0, max(0.0, a)) * 255)))

	def color(self, token: str):
		"""A ``Color`` for a colour token, named ``$token`` so a save writes the token back."""
		from LevityDash.lib.ui.colors.color import Color
		return Color.decode(self.resolve(f'${token}', 'colors'), name=f'${token}')

	def font(self, token: str) -> str:
		value = self.resolve(f'${token}', 'fonts')
		if not isinstance(value, str):
			raise ThemeError(f'theme {self.name!r}: font ${token} must be a family name, not {value!r}')
		return value

	def scale(self, token: str):
		"""The resolved gradient spec of a scale token, ready for ``Gradient.decode``."""
		return self.resolve(f'${token}', 'scales')


# Section: loading

_lock = RLock()
_cache: dict[str, Theme] = {}
_search: list[Callable[[], Iterable[Path]]] = []


def add_search_path(provider: Callable[[], Iterable[Path]]):
	"""Register a function giving directories to look for ``<name>.yaml`` in, before the built-in ones."""
	_search.append(provider)
	_cache.clear()


def search_paths() -> list[Path]:
	paths: list[Path] = []
	for provider in _search:
		try:
			paths.extend(Path(p) for p in provider())
		except Exception:
			log.exception('theme search path provider failed')
	paths.append(_RESOURCES)
	return paths


def available() -> list[str]:
	"""Names of the themes found on the search paths."""
	return sorted({p.stem for d in search_paths() if d.is_dir() for p in d.glob('*.yaml')})


def load(name: str) -> Theme:
	"""The theme called ``name``: the first ``<name>.yaml`` on the search paths (user folders first)."""
	with _lock:
		if name in _cache:
			return _cache[name]
		for directory in search_paths():
			path = directory / f'{name}.yaml'
			if path.is_file():
				with open(path, encoding='utf-8') as f:
					data = yaml.safe_load(f) or {}
				if not isinstance(data, dict):
					raise ThemeError(f'{path}: a theme is a mapping')
				theme = Theme.decode(data, name=name, source=str(path))
				_cache[name] = theme
				return theme
		raise ThemeError(f'no theme named {name!r}. Available: {", ".join(available()) or "none"}')


def decode(spec: Any) -> Theme:
	"""A theme from a dashboard's ``theme:`` value: a name, or an inline theme mapping (``extends:`` plus tokens)."""
	if isinstance(spec, Theme):
		return spec
	if spec is None:
		return load(DEFAULT_NAME)
	if isinstance(spec, str):
		return load(spec)
	if isinstance(spec, dict):
		key = json.dumps(spec, sort_keys=True, default=str)
		if key not in _inline:
			_inline[key] = Theme.decode(deepcopy(spec), name='inline')
		return _inline[key]
	raise ThemeError(f'theme is a name or a mapping, not {spec!r}')


# Section: the active theme

_active: Optional[Theme] = None
_override: Optional[Theme] = None
_listeners: list[Callable[[Theme], None] | WeakMethod] = []
_inline: dict[str, Theme] = {}


def active() -> Theme:
	global _active
	if _active is None:
		_active = load(DEFAULT_NAME)
	return _active


def on_change(callback: Callable[[Theme], None], call_now: bool = True):
	"""Run ``callback(theme)`` whenever the active theme changes. Class-level defaults use it to follow the theme.

	A bound method is held weakly, so an item can register itself and be dropped with the item.
	"""
	_listeners.append(WeakMethod(callback) if hasattr(callback, '__self__') else callback)
	if call_now:
		callback(active())


def activate(spec: Any = None) -> Theme:
	"""Make a theme the active one. An override from ``set_override`` wins over ``spec``."""
	global _active
	theme = _override or decode(spec)
	if theme is not _active:
		_active = theme
		for listener in list(_listeners):
			callback = listener() if isinstance(listener, WeakMethod) else listener
			if callback is None:
				_listeners.remove(listener)
				continue
			try:
				callback(theme)
			except Exception:
				log.exception('theme change listener failed')
	return theme


def set_override(spec: Any = None) -> Optional[Theme]:
	"""Force one theme whatever a dashboard asks for (a render tool's ``--theme``). ``None`` lifts it."""
	global _override
	_override = decode(spec) if spec is not None else None
	return activate(None) if _override is None else activate(_override)


def color(token: str):
	"""A ``Color`` for a token of the active theme."""
	return active().color(token)


def font(token: str) -> str:
	return active().font(token)


def reset():
	"""Back to the default theme with no override. For tests."""
	global _active, _override
	_override = None
	_cache.clear()
	_inline.clear()
	activate(None)


__all__ = (
	'DEFAULT_NAME', 'GROUPS', 'MODIFIERS', 'STANDARD_TOKENS', 'Theme', 'ThemeError', 'activate', 'active', 'add_search_path',
	'available', 'color', 'decode', 'font', 'is_modifier_spec', 'is_token', 'load', 'on_change', 'reset', 'set_override', 'token_name',
)
