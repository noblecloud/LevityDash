from difflib import get_close_matches
from enum import Enum
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Dict, List, Set, Tuple

from PySide2.QtGui import QFont, QFontDatabase
from PySide2.QtWidgets import QApplication

from LevityDash import __resources__
from LevityDash.lib.config import userConfig
from LevityDash.lib.EasyPath import EasyPath
from LevityDash.lib.log import LevityLogger
from LevityDash.lib.utils.shared import ClosestMatchEnumMeta

log = LevityLogger.getChild('fonts')
database = QFontDatabase()

userFontPath = userConfig.userPath["fonts"]
builtInFontsPath = EasyPath(Path(__resources__) / 'fonts')

if not userConfig.has_section("Fonts"):
	defaultConfig = {
		'Fonts': {
			'default':        'Nunito',
			'default.weight': 'Normal',
			'compact':        'Nunito',
			'compact.weight': 'Normal',
			'title':          'Nunito',
			'title.weight':   'Medium',
		}
	}
	userConfig.read_dict(defaultConfig)
	userConfig.save()

fontConfig = userConfig['Fonts']

"""
QFont::Thin	100	100
QFont::ExtraLight	200	200
QFont::Light	300	300
QFont::Normal	400	400
QFont::Medium	500	500
QFont::DemiBold	600	600
QFont::Bold	700	700
QFont::ExtraBold	800	800
QFont::Black	900	900
"""

'''
QFont.Thin  0
QFont.ExtraLight  12
QFont.Light 25
QFont.Normal  50
QFont.Medium  57
QFont.DemiBold  63
QFont.Bold  75
QFont.ExtraBold 81
QFont.Black 87
'''

_Qt5FontWeights: Dict[int, int] = {
	100:  10,
	200:  12,
	300:  25,
	400:  50,
	500:  57,
	600:  63,
	700:  75,
	800:  81,
	900:  87,
	1000: 100,
}

_reverseQt5FontWeights = {v: k for k, v in _Qt5FontWeights.items()}


def _testIsRegular(fnt: QFont) -> bool:
	return not bool(sum(int(i) for i in fnt.key().split(',')[5:-1]))


class FontWeight(int, Enum, metaclass=ClosestMatchEnumMeta):
	Qt5Weight: int

	Thin = 100
	ExtraLight = 200
	Light = 300
	Regular = 400
	Medium = 500
	DemiBold = 600
	Bold = 700
	ExtraBold = 800
	Black = 900
	ExtraBlack = 1000

	# Variants
	Normal = 400
	Heavy = 900
	Book = 400

	@cached_property
	def variantsInclusive(self) -> Set['FontCase']:
		return {w_ for i in FontWeight.__members__ if (w_ := FontWeight[i]).value == self.value}

	@property
	def variants(self) -> Set['FontCase']:
		return self.variantsInclusive - {self}

	@classmethod
	@lru_cache(maxsize=32)
	def availableWeights(cls, family: str) -> Set['FontWeight']:
		return {i for i in cls if i.name in database.styles(family)}

	@classmethod
	# @lru_cache()
	def styleWeights(cls, family: str) -> Dict[int, QFont]:
		styles = [fnt for style in database.styles(family) if _testIsRegular(fnt := database.font(family, style, 10))]
		return {FontWeight[i.styleName()] if i.styleName() in FontWeight._member_map_ else cls.fromQt5(i.weight()): i.styleName() for i in styles}

	@classmethod
	# @lru_cache()
	def closestWeightStyle(cls, family: str, weight: int) -> QFont:
		weights = cls.styleWeights(family)
		closest = min(weights.items(), key=lambda x: abs(x[0] - weight))[1]
		return database.font(family, closest, -1)

	@classmethod
	def getFontWeight(cls, family: str, weight: str | int) -> 'FontWeight':
		weight = cls[weight]

		weights = cls.availableWeights(family)

		try:
			weight = (weight.variantsInclusive & weights).pop()
		except KeyError:
			wIntValue = weight.value
			weight = min(weights, key=lambda x: abs(x.value - wIntValue))
			log.warning(f"Font weight '{weight}' not available for '{family}', using closest match '{weight}' instead")

		return weight

	@classmethod
	def fromQt5(cls, weight: int) -> 'FontWeight':
		w = _reverseQt5FontWeights.get(weight, None)
		if w is None:
			w = _reverseQt5FontWeights[min(_reverseQt5FontWeights, key=lambda x: abs(x - weight))]
		return cls(w)

	@classmethod
	def macOSWeight(cls, family: str, weight: int) -> QFont:
		return cls.closestWeightStyle(family, weight)


for member in FontWeight._member_map_.values():
	member.Qt5Weight = _Qt5FontWeights[member]


class FontCase(str, Enum, metaclass=ClosestMatchEnumMeta):
	MixedCase = 'MixedCase'
	AllUppercase = 'Uppercase'
	AllLowercase = 'Lowercase'
	SmallCaps = 'SmallCaps'
	Capitalize = 'Capitalize'


def __recurseFonts(path: EasyPath) -> List[EasyPath]:
	fonts = []
	for i in path.ls():
		if i.path.is_dir():
			if 'disabled' in i:
				continue
			fonts += __recurseFonts(i)
		elif i.path.is_file() and i.suffix in ['.ttf', '.otf']:
			fonts.append(i)
	return fonts


userFonts = __recurseFonts(userFontPath)
builtInFonts = __recurseFonts(builtInFontsPath)


def loadFonts(*fonts: EasyPath) -> Set[str]:
	log.verbose(f'Loading fonts...')
	fontSet: Set[str] = set()
	for font_ in fonts:
		if font_.path.is_dir():
			fontSet |= loadFonts(*__recurseFonts(font_))
			continue
		name, font_ = loadFont(font_)
		log.verbose(f'Loaded font {".".join(name.split(".")[:-1])}', verbosity=4)
		fontSet.add(font_)
	return fontSet


def loadFont(fontPath: EasyPath) -> Tuple[str, str]:
	name = fontPath.name
	id_ = database.addApplicationFont(fontPath.path.as_posix())
	fontPath = database.applicationFontFamilies(id_)[0]
	log.verbose(f'Loaded font {fontPath}', verbosity=2)
	return name, fontPath


def __getFontFromConfig(name: str) -> QFont:
	global database
	global fontConfig

	f = userConfig['Fonts'][name]
	if not database.hasFamily(f):
		closestMatch = get_close_matches(f, database.families(), n=1, cutoff=0.85)
		try:
			ff = closestMatch[0]
		except IndexError:
			ff = 'Nunito'
		newFontName = f'{name}.notFound'
		log.warning(f'Font {f!r} not found, using {ff!r} instead')
		disabledFontConfig = {f'{k.replace(name, newFontName)}': v for k, v in fontConfig.items() if k.startswith(name)}
		fontConfig[name] = ff
		fontConfig.update(disabledFontConfig)
		userConfig.save()

	w = userConfig['Fonts'].get(f'{name}.weight', fallback='Normal')
	i = userConfig['Fonts'].get(f'{name}.italic', fallback=False)
	u = userConfig['Fonts'].get(f'{name}.underline', fallback=False)
	s = userConfig['Fonts'].get(f'{name}.strikeout', fallback=False)
	sp = userConfig['Fonts'].get(f'{name}.spacing', fallback=False)
	case = FontCase[userConfig['Fonts'].get(f'{name}.case', fallback='MixedCase')]

	w = FontWeight.getFontWeight(f, w)

	font_ = database.font(f, w.name, 16)
	if i:
		font_.setItalic(True)
	if u:
		font_.setUnderline(True)
	if s:
		font_.setStrikeOut(True)
	if sp:
		font_.setLetterSpacing(QFont.AbsoluteSpacing, sp)
	match case:
		case FontCase.MixedCase:
			pass
		case FontCase.AllUppercase:
			font_.setCapitalization(QFont.AllUppercase)
		case FontCase.AllLowercase:
			font_.setCapitalization(QFont.AllLowercase)
		case FontCase.SmallCaps:
			font_.setCapitalization(QFont.SmallCaps)
		case FontCase.Capitalize:
			font_.setCapitalization(QFont.Capitalize)

	return font_


fontDict: Dict[str, QFont] = {f: database.font(f, '', -1) for f in loadFonts(*builtInFonts, *userFonts)}

for namedFont in {i for i in fontConfig.keys() if '.' not in i}:
	if namedFont in locals():
		log.warning(f'Font name {namedFont} is already in use by {locals()[namedFont]}, not adding to namespace')
		continue
	font = __getFontFromConfig(namedFont)
	fontDict[namedFont] = font
	locals()[namedFont] = font

defaultFont = locals()['default']
compactFont = locals()['compact']
titleFont = locals()['title']
weatherGlyph = database.font('Weather Icons', 'Normal', 16)

QApplication.setFont(defaultFont)


def getFontFamily(family: str) -> str:
	if not database.hasFamily(family):
		closestMatch = get_close_matches(family, database.families(), n=1, cutoff=0.85)
		family = None
		try:
			fallback = closestMatch[0]
		except IndexError:
			fallback = defaultFont.family()
		log.warning(f'Font family "{family}" not found, using "{fallback}" instead')
		return fallback
	return family


getFontWeight = FontWeight.getFontWeight

__all__ = ['getFontFamily', 'getFontWeight', 'fontDict', 'database']
