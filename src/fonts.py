from PySide2.QtGui import QFont, QFontDatabase

from src import basePath

fontDir = basePath.up()["fonts"]

fonts = [i for i in fontDir['sf'].ls() if not str(i).startswith('.')]
database = QFontDatabase()
fontDict = {}
for font in fonts:
	id = database.addApplicationFont(str(font.path.absolute()))
	fontDict[str(font.name)] = database.applicationFontFamilies(id)[0]
rounded = database.font('SF Pro Rounded', 'Normal', 16)
compact = database.font('SF Compact Rounded', 'Normal', 16)
database.addApplicationFont(str(fontDir['weathericons.ttf'].path.absolute()))
weatherGlyph = database.font('Weather Icons', 'Normal', 16)
