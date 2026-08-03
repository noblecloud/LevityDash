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


def parseFlag(argv: List[str], flag: str) -> Optional[str]:
	"""The value of `--flag X` or `--flag=X` from a raw argv, or None."""
	value = None
	prefix = f'{flag}='
	for i, arg in enumerate(argv):
		if arg == flag and i + 1 < len(argv):
			value = argv[i + 1]
		elif arg.startswith(prefix):
			value = arg.split('=', 1)[1]
	return value


def parseSeed(argv: List[str]) -> Optional[str]:
	"""The value of `--seed`/`--seed=` from a raw argv, or None."""
	return parseFlag(argv, '--seed')


def seedEnvironment(argv: List[str] = None) -> Optional[str]:
	"""Set the config-debug/seed environment from argv. Returns the seed path.

	Must be called before the first `LevityDash` import. Safe to call when no
	`--seed` is present - it does nothing.

	Deliberately does NOT also stage `--levity` here, despite that looking like
	the same ordering problem this function exists to solve. This function runs
	*before* LevityDash is imported, so the only directory available to write a
	candidate dashboard into is `seed` itself - and `seed` is meant to be read
	from, never written to; it is explicitly supported, documented usage to
	point it at a real, live config directory (CLAUDE.md, the design skill). An
	earlier version of this function copied the candidate straight into `seed`
	here, before any temp directory existed to redirect the write into, and it
	corrupted a real dashboard the one time `seed` was pointed at one - this
	function's own module docstring even names a near-identical incident with
	`--seed` itself, from before this file existed, without noticing this was
	the same class of bug reintroduced. `_boot.boot()` is the only place that
	can stage a candidate `.levity` safely: it runs its copy *after* import,
	once `LevityDash` has resolved a real, disposable temp directory to target.
	"""
	argv = sys.argv if argv is None else argv
	seed = parseSeed(argv)
	if not seed:
		return None
	resolved = Path(seed).expanduser().resolve()
	os.environ['LEVITYDASH_CONFIG_DEBUG'] = '1'
	os.environ['LEVITYDASH_CONFIG_SEED'] = str(resolved)
	return str(resolved)
