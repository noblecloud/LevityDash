"""Apply `--seed` to the environment before LevityDash is imported.

Deliberately importable *without* importing the `LevityDash` package: the entry
scripts add this directory to `sys.path` and `import _seed` directly. That is
the whole point of the module existing.

`LevityDash/__init__.py` reads `LEVITYDASH_CONFIG_DEBUG` in a class body, at
import time, to decide whether the config/data/cache directories are temporary.
`from LevityDash.devtools...` imports the parent package first, so anything that
sets the variable *after* that import - as `_boot.boot()` used to - is too late,
and silently so: `--seed` appeared to work while every render actually read and
wrote the live config. It surfaced only when the render service's /preview wrote
a stray file into the author's real saves directory.

Note `tests/conftest.py` was never affected; it sets both variables at module
import, before anything imports LevityDash. Only the devtools entry scripts had
the ordering wrong.
"""
import os
import sys
from pathlib import Path
from typing import List, Optional


def parseSeed(argv: List[str]) -> Optional[str]:
	"""The value of `--seed`/`--seed=` from a raw argv, or None."""
	seed = None
	for i, arg in enumerate(argv):
		if arg == '--seed' and i + 1 < len(argv):
			seed = argv[i + 1]
		elif arg.startswith('--seed='):
			seed = arg.split('=', 1)[1]
	return seed


def seedEnvironment(argv: List[str] = None) -> Optional[str]:
	"""Set the config-debug/seed environment from argv. Returns the seed path.

	Must be called before the first `LevityDash` import. Safe to call when no
	`--seed` is present - it does nothing.
	"""
	seed = parseSeed(sys.argv if argv is None else argv)
	if not seed:
		return None
	resolved = str(Path(seed).expanduser().resolve())
	os.environ['LEVITYDASH_CONFIG_DEBUG'] = '1'
	os.environ['LEVITYDASH_CONFIG_SEED'] = resolved
	return resolved
