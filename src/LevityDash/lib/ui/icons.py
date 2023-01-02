import os
import shutil

import zipfile
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Dict, Optional, Callable, ClassVar, Union, TypeAlias, TypeVar
from urllib import request

from rich.repr import rich_repr
from PySide6.QtGui import QFont, QFontMetrics

from LevityDash import LevityDashboard
from LevityDash.lib.EasyPath import EasyPath
from LevityDash.lib.log import LevityLogger

__dirs__ = LevityDashboard.paths
__resources__ = LevityDashboard.resources

log = LevityLogger.getChild('icons')

ls = lambda x=None: [x.name for x in Path(x or '').iterdir()]

T = TypeVar('T')
_CharMap = Union[T, Dict[str, str | dict | list | T]]
CharMap: TypeAlias = _CharMap[_CharMap[_CharMap]]


@dataclass
class Icon:
	iconPack: 'IconPack'
	name: str
	unicode: str
	font: QFont

	def __str__(self):
		return self.unicode

	def __hash__(self):
		return hash((self.unicode, self.iconPack))

	def __repr__(self):
		return f'Icon(name={self.iconPack.prefix}:{self.name}, iconPack={self.iconPack!s}, unicode={self.unicode}, style={self.font.styleName()})'


class FontNotFoundError(Exception):
	pass


@rich_repr
class IconPack:
	basePath = Path(f'{__resources__}/icons')

	__icon_packs__: ClassVar[Dict[str, 'IconPack']] = {}

	charMap: CharMap
	charMapPath: Path
	svgMap: Optional[Dict]
	prefix: str
	name: str
	defaultStyle: Optional[str] = None
	processor: Optional[Callable[[], None]]
	metrics: ClassVar[Dict[str, QFontMetrics]] = {}

	def __new__(cls):
		if cls is IconPack:
			raise TypeError('IconPack is an abstract class')
		prefix = getattr(cls, 'prefix')
		if (icon_pack := IconPack.__icon_packs__.get(prefix, None)) is None:
			IconPack.__icon_packs__[prefix] = icon_pack = super().__new__(cls)
		return icon_pack

	def __hash__(self):
		return hash(self.prefix)

	def __str__(self):
		return f'IconPack({self.name})'

	def __rich_repr__(self):
		yield 'name', self.name
		yield 'prefix', self.prefix
		yield 'defaultStyle', self.defaultStyle
		yield 'styles', self.styles
		yield 'charCount', max(len(i.get('chars', {})) for i in self.charMap.values())

	def __class_getitem__(cls, item) -> Union['IconPack', str]:
		if cls is IconPack:
			if (iconPack := cls.__icon_packs__.get(item, None)) is not None:
				return iconPack
			for iconPack in cls.__icon_packs__.values():
				if iconPack.name == item:
					return iconPack
			raise KeyError(f'No icon pack named {item}')
		raise NotImplementedError()

	def processor(self, charMapPath: Path, force_reload: bool = False) -> Dict:
		raise NotImplementedError()

	@cached_property
	def charMap(self) -> CharMap:
		return self.processor(self.charMapPath)

	@cached_property
	def fonts(self) -> Dict[str, QFont]:
		from LevityDash.lib.ui.fonts import loadFont

		def recurse(level: str = None, charMap_: CharMap = self.charMap, fonts_: Dict = None) -> Dict[str, QFont]:
			fonts_ = fonts_ if fonts_ is not None else {}
			level = level or ''
			for key, value in charMap_.items():
				if isinstance(value, dict) and key not in {'svg', 'chars'}:
					recurse(key, value, fonts_)
				elif key == 'font':
					value = value.format(**globals())
					_, font = loadFont(EasyPath(Path(value)))
					font = QFont(font)
					fonts_[level] = font
					self.metrics[level] = QFontMetrics(font)
					fonts_[level].setStyleName(level)

			return fonts_

		return recurse()

	@cached_property
	def styles(self) -> list[str]:
		defaultStyle = getattr(self, 'defaultStyle', None)
		return ([defaultStyle] if defaultStyle is not None else []) + [
      x for x in self.charMap.keys() if x not in {"svg", "chars", defaultStyle}
		]

	def getFont(self, style: str = None, hasChar: str = None) -> QFont:
		style = style or self.defaultStyle
		font = self.fonts.get(style, None) or self.fonts[self.defaultStyle]
		if hasChar is None and len(self.styles) > 1:
			return font
		styleWithChar = next((x for x in (style, *self.styles) if self.metrics[x].inFont(hasChar)), None)
		if styleWithChar is None:
			raise FontNotFoundError(f'No font found with char {hasChar}')
		return self.fonts[styleWithChar]

	def reload(self):
		self.charMap = self.processor(self.charMapPath, force_reload=True)

	def __trim_prefix(self, name: str) -> str:
		prefix_string = f'{self.prefix}-'
		if name.startswith(prefix_string):
			name = name[len(prefix_string):]
		return name

	def getIconSvg(self, name: str, style: Optional[str] = None) -> str:
		name = self.__trim_prefix(name)
		if (style is None or style not in self.charMap) and self.defaultStyle is not None:
			style = self.defaultStyle
		style = self.charMap.get(style, self.charMap)
		return style['svg'][name]

	def getIconChar(self, name: str, style: Optional[str] = None) -> str:
		name = self.__trim_prefix(name)
		if (style is None or style not in self.charMap) and self.defaultStyle is not None:
			style = self.defaultStyle
		style = self.charMap.get(style, self.charMap[self.defaultStyle])
		return style['chars'][name]

	def getIcon(self, name: str, style: Optional[str] = None) -> Icon:

		if (style is None or style not in self.charMap) and self.defaultStyle is not None:
			style = self.defaultStyle

		try:
			char = self.getIconChar(name, style)
		except KeyError:
			styles = (self.defaultStyle, *(k for k, v in self.charMap.items() if k != self.defaultStyle and name in v.get('chars', {})))
			style = next((x for x in styles if x is not None), None)
			char = self.getIconChar(name, style)
		try:
			font = self.getFont(style, hasChar=char)
			icon = Icon(self, name, char, font)
		except FontNotFoundError:
			font = self.getFont(style)
			icon = Icon(self, name, char, font)
			log.warning(f'No font found for {icon!r}')

		return icon


class FontAwesome(IconPack):
	prefix = 'fa'
	name = 'Font Awesome'
	charMapPath = IconPack.basePath/Path('maps/font-awesome.toml')
	defaultStyle = 'solid'
	styles = {'brands', 'regular', 'solid'}
	repo: str = 'https://github.com/FortAwesome/Font-Awesome'

	def get_spec(self, path) -> dict:
		from json import load as json_load
		for folder in (i for i in path.iterdir() if i.is_dir()):
			match EasyPath(folder).asDict(depth=2):
				case {'metadata': {'icons.json': iconFile, **metadata}, 'otfs': {**fonts}}:
					with open(iconFile.path, 'r') as f:
						font_spec = json_load(f)

					_FA_FONT_PATHS = {
						'solid':   fonts['Font Awesome 6 Free-Solid-900.otf'],
						'regular': fonts['Font Awesome 6 Free-Regular-400.otf'],
						'brands':  fonts['Font Awesome 6 Brands-Regular-400.otf'],
						'metadata': font_spec
					}
					break
				case _:
					continue
		else:
			print('No font found')
			print(path.absolute())
			raise FileNotFoundError('Could not find Font Awesome folder')
		return _FA_FONT_PATHS

	def processor(self, font_spec_output_path: Path = charMapPath, force_reload: bool = False):

		from tomli import load

		if font_spec_output_path.exists() and not force_reload:
			try:
				with open(font_spec_output_path, 'rb') as f:
					return load(f)['font-awesome']
			except Exception as e:
				log.error(f'Could not load font spec {font_spec_output_path!s}: {e}')
				return self._download()['font-awesome']
		elif not font_spec_output_path.exists():
			return self._download()['font-awesome']

	def _download(self) -> dict:
		url = f'{self.repo}/archive/6.x.zip'

		tmp_path = Path(__dirs__.user_cache_dir) / 'fa-download'
		os.makedirs(tmp_path, exist_ok=True)

		fa_folder = IconPack.basePath / 'Font-Awesome'

		shutil.rmtree(fa_folder, ignore_errors=True)
		fa_folder.mkdir(parents=True)

		def reporthook(count, block_size, total_size):
			print(f"\rDownloading Font-Awesome ... {count * block_size / (1024 * 1024):3.3g} MB", end="")
		filehandle, _ = request.urlretrieve(url, filename=tmp_path / 'fa.zip', reporthook=reporthook)

		with zipfile.ZipFile(filehandle) as zipped:
			to_extract = [i for i in zipped.filelist if i.filename.endswith('.otf') or i.filename.endswith('icons.json')]
			for member in to_extract:
				zipped.extract(member, path=tmp_path)

		paths = self.get_spec(tmp_path)

		sectionConstructor = lambda p: dict(
			font=f'{{__resources__}}/{p.path.absolute().relative_to(__resources__)!s}',
			chars=dict(),
			svg=dict()
		)

		metadata = paths.pop('metadata')

		items = {'prefix': 'fa'}
		items.update(
			(name, sectionConstructor(
				EasyPath(font.path.rename(fa_folder/f'fa-{name}.otf')))
			 ) for name, font in paths.items()
		)

		shutil.rmtree(tmp_path)

		for name, attrs in metadata.items():
			for style in attrs['styles']:
				items[style]['chars'][name] = chr(int(attrs['unicode'], 16))
				items[style]['svg'][name] = attrs['svg'][style]['raw']

		spec_path = IconPack.basePath / 'maps' / 'font-awesome.toml'
		os.makedirs(spec_path.parent, exist_ok=True)
		with open(spec_path, 'wb') as f:
			from tomli_w import dump
			dump({'font-awesome': items}, f)

		return items


class MaterialDesignIcons(IconPack):
	prefix = 'mdi'
	name = 'Material Design Icons'
	charMapPath = IconPack.basePath/Path('maps/mdi6.toml')
	defaultStyle = 'regular'

	def processor(self, font_spect_path: Path = charMapPath, force_reload: bool = False) -> Dict:
		from tomli import load

		with open(font_spect_path, 'rb') as f:
			font_spec = load(f)['mdi6']
		styles = {k: v for k, v in font_spec.items() if 'chars' in v or 'font' in v}
		for style, style_spec in styles.items():
			chars = style_spec['chars']
			for name, char in chars.items():
				chars[name] = chr(int(char, 16))
		return styles


class WeatherIcons(IconPack):
	prefix = 'wi'
	name = 'Weather Icons'
	charMapPath = IconPack.basePath/Path('maps/weather.toml')
	defaultStyle = 'regular'

	def processor(self, font_spect_path: Path = charMapPath, force_reload: bool = False) -> Dict:
		from tomli import load

		with open(font_spect_path, 'rb') as f:
			font_spec = load(f)['weather-icons']
		styles = {k: v for k, v in font_spec.items() if 'chars' in v or 'font' in v}
		for style, style_spec in styles.items():
			chars = style_spec['chars']
			for name, char in chars.items():
				chars[name] = chr(int(char, 16))
		return styles


def getIcon(name: str, style: Optional[str] = None) -> Icon:
	name = name.lstrip('icon:').strip(' ')
	pack, name = name.split(':', 1)
	pack = IconPack.__icon_packs__.get(pack, None)
	if pack is None:
		raise Exception(f'Could not find icon pack {pack}')
	return pack.getIcon(name, style)

fa = FontAwesome()
mdi = MaterialDesignIcons()
wi = WeatherIcons()
__all__ = ['fa', 'mdi', 'wi', 'getIcon', 'Icon', 'IconPack']
