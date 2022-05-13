from PySide2.QtGui import QFont, QFontDatabase

from LevityDash.lib.config import userConfig

userFontPath = userConfig.userPath["fonts"]


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

database = QFontDatabase()
fontDict = {}

for font in userFonts:
	_id = database.addApplicationFont(font.path.as_posix())
	fontDict[str(font.name)] = database.applicationFontFamilies(_id)[0]


def __getFontFromConfig(name: str) -> QFont:
	f = userConfig['Fonts'].get(name, fallback='Nunito')
	w = userConfig['Fonts'].get(f'{name}.weight', fallback='Medium')
	# s = config['Fonts'].get('default.style', fallback='Normal')
	return database.font(f, w, 16)


defaultFont = __getFontFromConfig('default')
compactFont = __getFontFromConfig('compact')
weatherGlyph = database.font('Weather Icons', 'Normal', 16)

__all__ = ['defaultFont', 'compactFont', 'weatherGlyph', 'fontDict', 'database']
