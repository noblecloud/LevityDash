import sys
from os import chdir

if sys.version_info < (3, 10, 0):
	sys.exit(
		"Python 3.10 or later is required. "
		"See https://levityDash.app/gettinhg-started"
		"for installation instructions."
	)

from pathlib import Path

isCompiled = getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')

__lib__ = (Path(__file__).parent.parent if isCompiled else Path(__file__).parent).joinpath('lib')

if isCompiled:
	chdir(sys._MEIPASS)
