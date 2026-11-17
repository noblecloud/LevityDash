"""Write every showcase dashboard and its scenario: `python docs/design-references/showcase/build.py`."""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit  # noqa: E402
from kit import write  # noqa: E402

# `default` is the shipped OpenMeteo template: its generator names where it goes (`LEVITY`).
BOARDS = ['atmos', 'rack', 'grow', 'grid', 'tide', 'default']

if __name__ == '__main__':
	for name in BOARDS:
		module = importlib.import_module(name)
		kit._figures = kit.itertools.count(1)
		print(write(name, module.HEADER, module.board(), module.data(), module.FREEZE, levity=getattr(module, 'LEVITY', None)))
