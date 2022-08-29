from pathlib import Path
from typing import Tuple, Dict

from PySide2.QtGui import QFont, QFontDatabase

from LevityDash.lib.config import userConfig

from LevityDash import __resources__
from LevityDash.lib.EasyPath import EasyPath
from LevityDash.lib.log import LevityLogger

log = LevityLogger.getChild('fonts')

userFontPath = userConfig.userPath["fonts"]
builtInFontsPath = EasyPath(Path(__resources__)/'fonts')


def recurseFonts(path):
	fonts = []
	for i in path.ls():
		if i.path.is_dir():
			if 'disabled' in i:
				continue
			fonts += recurseFonts(i)
		elif i.path.is_file() and i.suffix in ['.ttf', '.otf']:
			fonts.append(i)
	return fonts


userFonts = recurseFonts(userFontPath)
builtInFonts = recurseFonts(builtInFontsPath)

database = QFontDatabase()
fontDict = {}


def loadFonts(*fonts: EasyPath):
	global fontDict
	log.verbose(f'Loading fonts...')
	for font in fonts:
		name, font = loadFont(font)
		log.verbose(f'Loaded font {".".join(name.split(".")[:-1])}', verbosity=4)
		fontDict[name] = font


def loadFont(font: EasyPath) -> Tuple[str, QFont]:
	name = font.name
	id_ = database.addApplicationFont(font.path.as_posix())
	font = database.applicationFontFamilies(id_)[0]
	log.verbose(f'Loaded font {font}', verbosity=2)
	return name, font


loadFonts(*builtInFonts, *userFonts)


def __getFontFromConfig(name: str) -> QFont:
	f = userConfig['Fonts'].get(name, fallback='Nunito')
	w = userConfig['Fonts'].get(f'{name}.weight', fallback='Medium')
	# s = config['Fonts'].get('default.style', fallback='Normal')
	return database.font(f, w, 16)


defaultFont = __getFontFromConfig('default')
compactFont = __getFontFromConfig('compact')
weatherGlyph = database.font('Weather Icons', 'Normal', 16)

__all__ = ['defaultFont', 'compactFont', 'weatherGlyph', 'fontDict', 'database']
