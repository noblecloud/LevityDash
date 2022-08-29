from re import findall

from ..log import LevityLogger

UILogger = LevityLogger.getChild("UI")

from .colors import Color, Gradient
from ..config import userConfig

frontend = ''.join(findall(r'[a-zA-Z]', userConfig['Display'].get('frontend', 'PySide'))).lower()

if frontend in ('qt', 'pyside', 'pyqt'):
	from .frontends.PySide import *
