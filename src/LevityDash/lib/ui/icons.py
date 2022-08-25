from functools import cached_property
from pathlib import Path
from typing import Dict, Optional, Callable, ClassVar, Union, TypeAlias, TypeVar

from PySide2.QtGui import QFont
from rich import pretty

import LevityDash.lib.ui.fonts

# pretty.install()

from LevityDash.lib.EasyPath import EasyPath
from LevityDash import __resources__

ls = lambda x=None: [x.name for x in Path(x or '').iterdir()]

T = TypeVar('T')
_CharMap = Union[T, Dict[str, str | dict | list | T]]
CharMap: TypeAlias = _CharMap[_CharMap[_CharMap]]


class IconPack:
	basePath = Path(f'{__resources__}/icons')

	__icon_packs__: ClassVar[Dict[str, 'IconPack']] = {}

	charMap: CharMap
	charMapPath: Path
	svgMap: Optional[Dict]
	prefix: str
	defaultStyle: Optional[str] = None
	processor: Optional[Callable[[], None]]

	def __new__(cls):
		if cls is IconPack:
			raise TypeError('IconPack is an abstract class')
		prefix = getattr(cls, 'prefix')
		if (icon_pack := IconPack.__icon_packs__.get(prefix, None)) is None:
			IconPack.__icon_packs__[prefix] = icon_pack = super().__new__(cls)
		return icon_pack

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
					fonts_[level] = QFont(font)

			return fonts_

		return recurse()

	def getFont(self, style: str = None) -> QFont:
		return self.fonts.get(style, None) or self.fonts[self.defaultStyle]

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
		style = self.charMap.get(style, self.charMap)
		return style['chars'][name]


class FontAwesome(IconPack):
	prefix = 'fa'
	name = 'Font Awesome'
	charMapPath = IconPack.basePath/Path('maps/font-awesome.toml')
	defaultStyle = 'solid'

	def processor(self, font_spec_output_path: Path = charMapPath, force_reload: bool = False):
		from json import load as json_load
		from tomli import load
		from tomli_w import dump

		for folder in (i for i in IconPack.basePath.iterdir() if i.is_dir()):
			match EasyPath(folder).asDict(depth=2):
				case {'metadata': {'icons.json': iconFile, **metadata}, 'otfs': {**fonts}}:
					_FA_FONT_PATHS = {
						'solid':   fonts['Font Awesome 6 Free-Solid-900.otf'],
						'regular': fonts['Font Awesome 6 Free-Regular-400.otf'],
						'brands':  fonts['Font Awesome 6 Brands-Regular-400.otf']
					}
					font_spec_path = iconFile.path
					break
				case _:
					continue
		else:
			raise Exception('Could not find Font Awesome folder')

		sectionConstructor = lambda p: dict(font=f'{{__resources__}}/{p.path.absolute().relative_to(__resources__)!s}', chars=dict(), svg=dict())
		items = {
			'regular': sectionConstructor(_FA_FONT_PATHS['regular']),
			'solid':   sectionConstructor(_FA_FONT_PATHS['solid']),
			'brands':  sectionConstructor(_FA_FONT_PATHS['brands'])
		}
		if font_spec_output_path.exists() and not force_reload:
			try:
				with open(font_spec_output_path, 'rb') as f:
					font_spec = load(f)['font-awesome']
			except Exception as e:
				pass
			else:
				return font_spec

		with open(font_spec_path, 'r') as f:
			font_spec = json_load(f)
		for name, attrs in font_spec.items():
			for style in attrs['styles']:
				items[style]['chars'][name] = chr(int(attrs['unicode'], 16))
				items[style]['svg'][name] = attrs['svg'][style]['raw']

		# output the processed font to a TOML file
		parentFolder = font_spec_output_path.parent
		if not parentFolder.exists():
			parentFolder.mkdir(parents=True)

		with open(font_spec_output_path, 'xb') as f:
			f.flush()
			dump({'font-awesome': items}, f)

		return items


class MaterialDesignIcons(IconPack):
	prefix = 'mdi'
	name = 'Material Design Icons'
	charMapPath = IconPack.basePath/Path('maps/mdi6.toml')
	defaultStyle = 'solid'

	styles = {'outline', 'solid'}

	def processor(self, font_spect_path: Path = charMapPath, force_reload: bool = False) -> Dict:
		from tomli import load

		with open(font_spect_path, 'rb') as f:
			font_spec = load(f)['mdi6']
		items = {k: dict(chars=dict()) for k in self.styles}
		for name, value in font_spec.pop('chars').items():
			items['chars'][name] = chr(int(value, 16))
		return items


class WeatherIcons(IconPack):
	prefix = 'wi'
	name = 'Weather Icons'
	charMapPath = IconPack.basePath/Path('maps/weather.toml')
	defaultStyle = ''

	styles = {'regular', 'solid'}

	def processor(self, font_spect_path: Path = charMapPath, force_reload: bool = False) -> Dict:
		from tomli import load

		with open(font_spect_path, 'rb') as f:
			font_spec = load(f)['weather-icons']

		items = {}

		for name, value in font_spec.pop('chars').items():
			items[name] = chr(int(value, 16))
		return {**font_spec, 'chars': items}


fa = FontAwesome()
mdi = MaterialDesignIcons()
wi = WeatherIcons()
