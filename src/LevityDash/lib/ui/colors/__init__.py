from pathlib import Path

from . import theme
from .color import Color
from .gradient import Gradient
from . import presets


def _userThemes():
	# Looked up on each search, not at import: the config folder is decided after this package loads.
	from LevityDash.lib.config import userConfig
	return [Path(userConfig.userPath.path) / 'themes']


theme.add_search_path(_userThemes)

__all__ = ['Color', 'Gradient', 'presets', 'theme']
