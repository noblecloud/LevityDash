from pathlib import Path

from sys import path as PYTHONPATH

PYTHONPATH.insert(0, str(Path(__file__).parent.absolute()))
from . import _datetime_shim

_datetime_shim.install()
