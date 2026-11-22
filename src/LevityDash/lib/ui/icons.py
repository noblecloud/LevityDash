"""Glyph packs — the named icons a dashboard draws.

A pack is data, not code. One TOML file per pack under
`resources/icons/maps/*.toml` (user packs in `<config>/icons/maps/`, found
first) with a root table naming its `prefix` and one sub-table per style:

	[weather-icons]
	prefix = "wi"
	name = "Weather Icons"          # optional; shown in error messages
	default = "regular"             # optional; the first style with a font otherwise

	[weather-icons.regular]
	font = "{__resources__}/icons/weathericons.ttf"

	[weather-icons.regular.chars]
	day-sunny = "0xf00d"            # a code point, or the character itself

A style may also carry an `svg` table of raw path data (`fa:` does) which
`getIconSvg` reads; `wi:`/`mdi:` are font-only today.

Discovery never raises at import. A map that will not parse is logged and
skipped, so one bad user file cannot take the window down with it, and a lookup
that fails raises a typed error naming the closest matches instead of a bare
`KeyError`.
"""
import difflib
import os
import shutil
import zipfile
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import ClassVar, Dict, Optional, TypeAlias, TypeVar, Union
from urllib import request

from rich.repr import rich_repr
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetrics, QPainterPath, QPainterPathStroker, QTransform

from LevityDash import LevityDashboard
from LevityDash.lib.EasyPath import EasyPath
from LevityDash.lib.log import LevityLogger
from LevityDash.lib.ui import svgpath

__dirs__ = LevityDashboard.paths
__resources__ = LevityDashboard.resources

log = LevityLogger.getChild('icons')

T = TypeVar('T')
_CharMap = Union[T, Dict[str, str | dict | list | T]]
CharMap: TypeAlias = _CharMap[_CharMap[_CharMap]]

_FONT = 'font'
_CHARS = 'chars'
_SVG = 'svg'
_VIEWBOX = 'viewBox'
_STROKE = 'stroke'
#: Root-table keys that describe the pack rather than a style.
_META = frozenset({'prefix', 'name', 'default', 'aliases', 'format', 'version', 'also'})
_STYLES_KEYS = frozenset({_FONT, _CHARS, _SVG, _VIEWBOX, _STROKE})


class IconError(Exception):
	"""Base class for every glyph lookup that fails."""


class IconPackNotFound(IconError, KeyError):
	"""No pack answers to that prefix."""


class IconNotFound(IconError, KeyError):
	"""The pack exists but has no glyph by that name."""


class FontNotFoundError(IconError):
	"""The pack has a font section, but none of its fonts draws the character."""


@dataclass
class Icon:
	iconPack: 'IconPack'
	name: str
	unicode: str
	font: QFont

	@property
	def pack(self) -> 'IconPack':
		return self.iconPack

	@property
	def prefix(self) -> str:
		return self.iconPack.prefix

	@property
	def svg(self) -> Optional[str]:
		# `None` for a font-only pack rather than the KeyError `wi:` and `mdi:` used to raise here.
		return self.iconPack.getIconSvg(self.name)

	@property
	def isVector(self) -> bool:
		return False

	def __str__(self):
		return self.unicode

	def __hash__(self):
		return hash((self.unicode, self.iconPack))

	def __repr__(self):
		return f'Icon(name={self.iconPack.prefix}:{self.name}, iconPack={self.iconPack!s}, unicode={self.unicode}, style={self.font.styleName()})'


@dataclass
class VectorIcon(Icon):
	"""A glyph drawn from path data instead of a font character.

	`parts` are `d` strings in the pack's `viewBox`; `roles` names the colour role of
	each one (`body` today, `accent`/`edge`/`shadow` when a pack carries a second tone).
	A vector glyph has no `unicode`, so `str()` is empty and callers that lay text out
	must ask `painterPath()` and `advance()` instead.
	"""

	parts: tuple = ()
	viewBox: tuple = (24.0, 24.0)
	roles: tuple = ()
	#: Stroke width in `viewBox` units. A stroke-only set (Lucide, Tabler, Iconoir) declares
	#: one and the outline is baked into the path, so a glyph still fills with one brush.
	stroke: float = 0.0

	@property
	def isVector(self) -> bool:
		return True

	@cached_property
	def unitPath(self) -> QPainterPath:
		"""Every part in the source space, as one path."""
		path = QPainterPath()
		path.setFillRule(Qt.WindingFill)
		stroker = None
		if self.stroke:
			stroker = QPainterPathStroker()
			stroker.setWidth(float(self.stroke))
			stroker.setCapStyle(Qt.RoundCap)
			stroker.setJoinStyle(Qt.RoundJoin)
		for part in self.parts:
			segment = svgpath.parse(part)
			if stroker is not None:
				# Stroke-only geometry (Lucide, Tabler, and this pack): the outline is the glyph.
				# Filling the segments too would turn a drawn circle into a disc.
				path.addPath(stroker.createStroke(segment))
			else:
				path.addPath(segment)
		return path

	def painterPath(self, size: float) -> QPainterPath:
		"""The glyph scaled into a square `size`, box top-left at (0, 0)."""
		width, height = self.viewBox
		largest = max(width, height) or size
		scale = size / largest
		transform = QTransform()
		transform.translate((size - width * scale) / 2.0, (size - height * scale) / 2.0)
		transform.scale(scale, scale)
		return transform.map(self.unitPath)

	def advance(self, size: float) -> float:
		"""The width a glyph of `size` takes on a baseline: its box, square."""
		return size

	def __str__(self):
		return ''

	def __hash__(self):
		return hash((self.iconPack, self.name, self.parts))


@rich_repr
class IconPack:
	basePath = Path(f'{__resources__}/icons')

	#: Registry, keyed by prefix. Kept as a class attribute because callers read it directly.
	__icon_packs__: ClassVar[Dict[str, 'IconPack']] = {}
	#: Retired/alternate prefixes (`mdi6` → `mdi`) declared by a map's `also` key.
	__prefix_aliases__: ClassVar[Dict[str, str]] = {}

	def __init__(self, prefix: str, name: str = None, charMapPath: Path = None, data: dict = None, aliases: dict = None):
		self.prefix = prefix
		self.name = name or prefix
		self.charMapPath = charMapPath
		self._data = data or {}
		self._aliases = dict(aliases or {})
		self._icons: Dict[tuple, Icon] = {}
		self._charMap = None
		self._fonts: Dict[str, QFont] = {}
		self._metrics: Dict[str, QFontMetrics] = {}
		self._names = None

	def __hash__(self):
		return hash(self.prefix)

	def __eq__(self, other):
		return isinstance(other, IconPack) and other.prefix == self.prefix

	def __str__(self):
		return f'IconPack({self.name})'

	def __rich_repr__(self):
		yield 'name', self.name
		yield 'prefix', self.prefix
		yield 'defaultStyle', self.defaultStyle
		yield 'styles', self.styles
		yield 'charCount', max((len(i.get(_CHARS, {})) for i in self.charMap.values()), default=0)

	def __class_getitem__(cls, item) -> Union['IconPack', str]:
		if (pack := cls.get(item)) is not None:
			return pack
		raise IconPackNotFound(f'No icon pack named {item}')

	# ---------------------------------------------------------------- registry

	@classmethod
	def get(cls, prefix: str) -> Optional['IconPack']:
		"""The pack for `prefix`, its name, or `None`. Never raises — callers decide."""
		if not isinstance(prefix, str):
			return None
		packs = cls.__icon_packs__
		needle = prefix.strip().lower()
		for key in (prefix, needle, cls.__prefix_aliases__.get(needle)):
			if key is not None and (pack := packs.get(key)) is not None:
				return pack
		return next((x for x in packs.values() if x.name.lower() == needle), None)

	# ------------------------------------------------------------------- data

	@cached_property
	def charMap(self) -> Dict[str, dict]:
		"""`{style: {font, chars, svg}}`, characters resolved, omitted keys absent."""
		if self._charMap is None:
			self._charMap = self._normalise(self._data)
		return self._charMap

	def _normalise(self, data: dict) -> dict:
		styles = {}
		for style, spec in (data or {}).items():
			if style in _META or not isinstance(spec, dict):
				continue
			chars = {}
			for name, value in (spec.get(_CHARS) or {}).items():
				char = _to_char(value)
				if char is not None:
					chars[name] = char
			entry = {k: v for k, v in spec.items() if k in _STYLES_KEYS and k != _CHARS}
			if _FONT in entry:
				entry[_FONT] = _resolve_path(entry[_FONT])
			if _VIEWBOX in entry:
				entry[_VIEWBOX] = svgpath.viewBox(entry[_VIEWBOX])
			if _SVG in entry and isinstance(entry[_SVG], dict):
				entry[_SVG] = {name: value for name, value in entry[_SVG].items() if value}
			if chars:
				entry[_CHARS] = chars
			if chars or _FONT in entry or _SVG in entry:
				styles[style] = entry
		return styles

	@cached_property
	def defaultStyle(self) -> Optional[str]:
		declared = self._data.get('default')
		if declared in self.charMap:
			return declared
		return next(iter(self.charMap), None)

	@cached_property
	def styles(self) -> tuple:
		"""Styles that carry glyphs, the default first."""
		default = self.defaultStyle
		others = (x for x in self.charMap if x != default)
		return ((default,) if default is not None else ()) + tuple(others)

	@cached_property
	def names(self) -> set:
		if self._names is None:
			self._names = {
				name
				for spec in self.charMap.values()
				for table in (_CHARS, _SVG)
				for name in spec.get(table, {})
			}
		return self._names

	@cached_property
	def fonts(self) -> Dict[str, QFont]:
		from LevityDash.lib.ui.fonts import loadFont

		for style, spec in self.charMap.items():
			path = spec.get(_FONT)
			if not path:
				continue
			try:
				_, font = loadFont(EasyPath(Path(path)))
			except Exception as e:
				log.error(f'{self!s}: font {path} could not be loaded; style {style!r} has no font: {e}')
				continue
			font = QFont(font)
			font.setStyleName(style)
			self._fonts[style] = font
			# Metrics belong to this pack's font. They used to live in a class dict keyed by style
			# alone, so `mdi:regular` and `wi:regular` overwrote each other's metrics.
			self._metrics[style] = QFontMetrics(font)
		return self._fonts

	@property
	def metrics(self) -> Dict[str, QFontMetrics]:
		if not self._fonts:
			_ = self.fonts
		return self._metrics

	# ----------------------------------------------------------------- lookup

	def resolve_alias(self, name: str, _depth: int = 0) -> str:
		"""Follow the pack's `aliases` table (same-pack, or `pack:name`) to a real name."""
		if _depth > 8 or name not in self._aliases:
			return name
		target = self._aliases[name]
		if ':' in target:
			return target
		return self.resolve_alias(target, _depth + 1)

	def hasName(self, name: str) -> bool:
		return self.resolve_alias(name) in self.names

	def _styleFor(self, name: str, style: Optional[str] = None) -> tuple:
		"""`(style, char)` for `name`; the requested style first, then any style that has it."""
		for candidate in self._styleOrder(style):
			if (char := self.charMap[candidate].get(_CHARS, {}).get(name)) is not None:
				return candidate, char
		raise self._missing(name)

	def _svgFor(self, name: str, style: Optional[str] = None) -> tuple:
		"""`(style, markup)` for a vector glyph, or `(None, None)`."""
		for candidate in self._styleOrder(style):
			if (markup := self.charMap[candidate].get(_SVG, {}).get(name)) is not None:
				return candidate, markup
		return None, None

	def _styleOrder(self, style: Optional[str] = None) -> tuple:
		return tuple(dict.fromkeys(x for x in (style, self.defaultStyle, *self.styles) if x in self.charMap))

	def _missing(self, name: str) -> IconNotFound:
		close = difflib.get_close_matches(name, self.names, n=3, cutoff=0.6)
		hint = f'; did you mean {", ".join(close)}?' if close else ''
		return IconNotFound(f'{self.prefix}: has no glyph named {name!r}{hint}')

	def getFont(self, style: str = None, hasChar: str = None) -> QFont:
		"""The font that draws `style` (or the default style when that one has none).

		`hasChar` is a tiebreak only. Which style *holds* a name is the map's job
		(`_styleFor`), because `QFontMetrics.inFont` reports False for thousands of
		Private-Use-Area characters these fonts really do draw (measured: 1083 of the
		1852 Font Awesome names, 1102 of 6395 Material Design Icons names), so a
		failed check must never mean the glyph is missing.
		"""
		style = style or self.defaultStyle
		candidates = self._styleOrder(style)
		if hasChar is not None and len(hasChar) == 1:
			needle = ord(hasChar)
			reported = next((x for x in candidates if (m := self.metrics.get(x)) is not None and m.inFont(needle)), None)  # type: ignore[arg-type]
			if reported is not None:
				return self.fonts[reported]
		for candidate in candidates:
			if (font := self.fonts.get(candidate)) is not None:
				return font
		raise FontNotFoundError(f'{self!s} has no loaded font for style {style!r}')

	def getIconChar(self, name: str, style: Optional[str] = None) -> str:
		return self._styleFor(self.resolve_alias(name), style)[1]

	def getIconSvg(self, name: str, style: Optional[str] = None) -> Optional[str]:
		"""The style's raw path data for `name`, or `None` when the style carries no `svg`."""
		name = self.resolve_alias(name)
		for candidate in self._styleOrder(style):
			if (svg := self.charMap[candidate].get(_SVG, {}).get(name)) is not None:
				return svg
		return None

	def getIcon(self, name: str, style: Optional[str] = None) -> Icon:
		key = (name, style)
		if (icon := self._icons.get(key)) is not None:
			return icon
		resolved = self.resolve_alias(name)
		try:
			style, char = self._styleFor(resolved, style)
		except IconNotFound:
			# No character for that name: a vector pack stores path data instead.
			vector_style, markup = self._svgFor(resolved, style)
			if markup is None:
				raise
			return self._vectorIcon(key, vector_style, resolved, markup)
		try:
			font = self.getFont(style, hasChar=char)
		except FontNotFoundError:
			font = self.getFont(style)
			log.warning(f'{self.prefix}:{resolved} is mapped to {char!r} but no font in the pack loaded; the glyph will not draw')
		icon = self._icons[key] = Icon(self, resolved, char, font)
		return icon

	def _vectorIcon(self, key: tuple, style: str, name: str, markup: str) -> 'VectorIcon':
		spec = self.charMap[style]
		parts = tuple(svgpath.path_data(markup))
		if not parts:
			raise IconNotFound(f'{self.prefix}:{name} has no path data')
		icon = VectorIcon(
			self, name, '', QFont(),
			parts=parts,
			viewBox=spec.get(_VIEWBOX, (24.0, 24.0)),
			roles=tuple(['body'] * len(parts)),
			stroke=float(spec.get(_STROKE) or 0.0),
		)
		self._icons[key] = icon
		return icon

	def validate(self) -> list:
		"""`[(style, what, message)]` for every mapping the pack itself cannot serve.

		Deliberately does not use `QFontMetrics.inFont` to judge coverage: it reports
		False for a large share of the characters these fonts draw, so it would flag
		thousands of working icons. It checks the things that are actually broken when
		they break — a font that will not load, a style with no glyphs, an alias that
		points nowhere, an empty svg entry.
		"""
		issues = []
		for style, spec in self.charMap.items():
			if spec.get(_FONT) and self.metrics.get(style) is None:
				issues.append((style, _FONT, f'font could not be loaded: {spec[_FONT]}'))
			if not spec.get(_CHARS) and not spec.get(_SVG):
				issues.append((style, _CHARS, 'style has no glyphs'))
			if spec.get(_FONT) and not Path(spec[_FONT]).exists():
				issues.append((style, _FONT, f'font file is missing: {spec[_FONT]}'))
			for name, svg in (spec.get(_SVG) or {}).items():
				if not isinstance(svg, str) or not svg.strip():
					issues.append((style, _SVG, f'{name!r} has empty path data'))
		for alias, target in self._aliases.items():
			name = target.split(':', 1)[-1]
			if not self.hasName(name):
				issues.append(('aliases', alias, f'points at {target!r}, which is not a glyph in this pack'))
		return issues

	def reload(self):
		self._icons.clear()
		self._names = None
		self.__dict__.pop('charMap', None)
		self.__dict__.pop('fonts', None)
		self.__dict__.pop('styles', None)
		self.__dict__.pop('defaultStyle', None)
		self._fonts = {}
		self._metrics = {}
		self._charMap = None
		if self.charMapPath is not None and Path(self.charMapPath).exists():
			try:
				self._data = _read_map(Path(self.charMapPath))
				self._aliases = _aliases_of(self._data)
			except Exception as e:
				log.error(f'{self!s}: {self.charMapPath} could not be re-read: {e}')
		return self


# --------------------------------------------------------------------- helpers


def _to_char(value) -> Optional[str]:
	"""`"0xf00d"` or a literal character; `None` for anything that is not a single glyph."""
	if isinstance(value, str):
		if len(value) == 1:
			return value
		try:
			code = int(value, 16)
		except ValueError:
			return None
		if 0 <= code <= 0x10FFFF:
			return chr(code)
		return None
	if isinstance(value, int):
		return chr(value) if 0 <= value <= 0x10FFFF else None
	return None


def _resolve_path(value) -> Optional[str]:
	if not isinstance(value, str):
		return None
	return value.replace('{__resources__}', str(__resources__)).replace('{__dirs__}', str(__dirs__))


def _read_map(path: Path) -> dict:
	try:
		import tomllib as toml
	except ImportError:  # Python < 3.11
		import tomli as toml
	with open(path, 'rb') as f:
		return toml.load(f)


def _root_of(data: dict) -> tuple:
	"""(root key, root table) — a map holds one pack, under a key that names it."""
	for key, value in data.items():
		if isinstance(value, dict):
			return key, value
	return None, {}


def _aliases_of(root: dict) -> dict:
	aliases = root.get('aliases')
	return dict(aliases) if isinstance(aliases, dict) else {}


def _map_dirs() -> tuple:
	dirs = []
	try:
		from LevityDash.lib.config import userConfig
		dirs.append(Path(userConfig.userPath.path) / 'icons' / 'maps')
	except Exception as e:
		log.debug(f'no user icon folder: {e}')
	dirs.append(IconPack.basePath / 'maps')
	return tuple(dirs)


def discover(force: bool = False) -> Dict[str, IconPack]:
	"""Load every pack the map folders hold. A broken map is logged and skipped."""
	if IconPack.__icon_packs__ and not force:
		return IconPack.__icon_packs__

	packs: Dict[str, IconPack] = {}
	if force:
		IconPack.__prefix_aliases__.clear()
	for directory in _map_dirs():
		if not Path(directory).is_dir():
			continue
		for path in sorted(Path(directory).glob('*.toml')):
			try:
				data = _read_map(path)
			except Exception as e:
				log.error(f'icon pack {path.name} could not be read; skipped: {e}')
				continue
			key, root = _root_of(data)
			prefix = str(root.get('prefix') or '').strip()
			if not prefix:
				log.error(f'icon pack {path.name} declares no prefix; skipped')
				continue
			if prefix in packs:
				log.debug(f'icon pack {prefix}: keeping {packs[prefix].charMapPath}, skipping {path}')
				continue
			pack = IconPack(prefix=prefix, name=root.get('name') or key or prefix, charMapPath=path, data=root, aliases=_aliases_of(root))
			for also in root.get('also', ()):
				IconPack.__prefix_aliases__[str(also).strip().lower()] = prefix
			packs[prefix] = pack

	if not packs:
		log.error(f'no icon packs found in {", ".join(str(d) for d in _map_dirs())}')
	IconPack.__icon_packs__.update(packs)
	return IconPack.__icon_packs__


def packs() -> Dict[str, IconPack]:
	return discover()


def _pack(prefix: str) -> IconPack:
	if (pack := IconPack.get(prefix)) is not None:
		return pack
	known = ', '.join(sorted({x for x in IconPack.__icon_packs__}))
	close = difflib.get_close_matches(prefix, list(IconPack.__icon_packs__), n=2, cutoff=0.5)
	hint = f'; did you mean {", ".join(close)}?' if close else ''
	raise IconPackNotFound(f'No glyph pack named {prefix!r}{hint} (packs: {known})')


def _missing(name: str) -> IconNotFound:
	every = {x for pack in packs().values() for x in pack.names}
	close = list(dict.fromkeys(difflib.get_close_matches(name, every, n=6, cutoff=0.6)))[:3]
	qualified = list(dict.fromkeys(f'{pack.prefix}:{x}' for pack in packs().values() for x in close if pack.hasName(x)))[:3]
	hint = f'; did you mean {", ".join(qualified)}?' if qualified else ''
	return IconNotFound(f'No glyph named {name!r}{hint}')


def getIcon(name: str, style: Optional[str] = None) -> Icon:
	"""`fa:solid`, `wi:day-sunny`, or a bare `day-sunny` found in any pack."""
	if isinstance(name, Icon):
		return name
	if not isinstance(name, str):
		raise IconNotFound(f'An icon is a name, not {type(name).__name__}: {name!r}')
	raw = name.strip()
	# `removeprefix`, not `lstrip('icon:')`: lstrip eats any leading character from that set,
	# so a bare name like `cloud` came back as `loud`.
	if raw[:5].lower() == 'icon:':
		raw = raw[5:].strip()
	if ':' in raw:
		prefix, glyph = raw.split(':', 1)
		return _pack(prefix.strip()).getIcon(glyph.strip(), style)
	if not raw:
		raise IconNotFound('An empty string is not an icon name')

	for pack in packs().values():
		if pack.hasName(raw):
			return pack.getIcon(raw, style)
	raise _missing(raw)


# ------------------------------------------------------------------ built-ins


def _fetch_font_awesome(charMapPath: Path = None) -> dict:
	"""Download Font Awesome 6 and write its map. Only runs when the map is missing."""
	from json import load as json_load

	repo = 'https://github.com/FortAwesome/Font-Awesome'
	url = f'{repo}/archive/6.x.zip'
	tmp_path = Path(__dirs__.user_cache_dir) / 'fa-download'
	os.makedirs(tmp_path, exist_ok=True)

	fa_folder = IconPack.basePath / 'Font-Awesome'
	shutil.rmtree(fa_folder, ignore_errors=True)
	fa_folder.mkdir(parents=True)

	def reporthook(count, block_size, total_size):
		print(f"\rDownloading Font-Awesome ... {count * block_size / (1024 * 1024):3.3g} MB", end="")

	filehandle, _ = request.urlretrieve(url, filename=tmp_path / 'fa.zip', reporthook=reporthook)
	with zipfile.ZipFile(filehandle) as zipped:
		for member in (i for i in zipped.filelist if i.filename.endswith(('.otf', 'icons.json'))):
			zipped.extract(member, path=tmp_path)

	metadata = None
	fonts = {}
	for folder in (i for i in tmp_path.iterdir() if i.is_dir()):
		spec = EasyPath(folder).asDict(depth=2)
		if 'metadata' not in spec or 'otfs' not in spec:
			continue
		with open(spec['metadata']['icons.json'], 'r') as f:
			metadata = json_load(f)
		fonts = spec['otfs']
		break
	if metadata is None:
		raise FileNotFoundError('Could not find the Font Awesome folder')

	by_style = {
		'solid':   fonts['Font Awesome 6 Free-Solid-900.otf'],
		'regular': fonts['Font Awesome 6 Free-Regular-400.otf'],
		'brands':  fonts['Font Awesome 6 Brands-Regular-400.otf'],
	}
	items = {'prefix': 'fa', 'name': 'Font Awesome'}
	for style, path in by_style.items():
		items[style] = {
			'font':  f'{{__resources__}}/icons/Font-Awesome/fa-{style}.otf',
			'chars': {},
			'svg':   {},
		}
		Path(path).rename(fa_folder / f'fa-{style}.otf')

	shutil.rmtree(tmp_path, ignore_errors=True)

	for name, attrs in metadata.items():
		for style in attrs['styles']:
			items[style]['chars'][name] = chr(int(attrs['unicode'], 16))
			items[style]['svg'][name] = attrs['svg'][style]['raw']

	path = Path(charMapPath or (IconPack.basePath / 'maps' / 'font-awesome.toml'))
	os.makedirs(path.parent, exist_ok=True)
	with open(path, 'wb') as f:
		try:
			import tomli_w
		except ImportError:
			from tomli_w import dump as tomli_dump
			tomli_dump({'font-awesome': items}, f)
		else:
			tomli_w.dump({'font-awesome': items}, f)
	return items


class _MissingPack(IconPack):
	"""Stands in for a pack whose map could not be found, so import never fails."""

	def __init__(self, prefix: str, reason: str = ''):
		super().__init__(prefix=prefix, name=prefix)
		self._reason = reason

	def __str__(self):
		return f'IconPack(missing: {self.prefix})'

	def getIcon(self, name: str, style: Optional[str] = None) -> Icon:
		raise IconPackNotFound(f'The {self.prefix!r} glyph pack is not installed{": " + self._reason if self._reason else ""}')


if not (IconPack.basePath / 'maps' / 'font-awesome.toml').exists():
	try:
		_fetch_font_awesome()
	except Exception as e:
		log.error(f'Font Awesome could not be downloaded: {e}')

discover()

fa = IconPack.__icon_packs__.get('fa') or _MissingPack('fa', 'font-awesome.toml is missing')
mdi = IconPack.__icon_packs__.get('mdi') or _MissingPack('mdi', 'mdi6.toml is missing')
wi = IconPack.__icon_packs__.get('wi') or _MissingPack('wi', 'weather.toml is missing')

__all__ = [
	'fa', 'mdi', 'wi', 'getIcon', 'packs', 'discover',
	'Icon', 'IconPack', 'IconError', 'IconNotFound', 'IconPackNotFound', 'FontNotFoundError',
]
