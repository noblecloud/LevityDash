"""Dev-only: set the environment before the first `LevityDash` import. Gauge Studio.

`import LevityDash` builds the `QApplication` and the config object. With no
override the config object reads, and creates files in, the real config
directory. `LEVITYDASH_CONFIG_DEBUG=1` makes every `LevityDash` directory a
throwaway temp directory. The studio sets it here and nothing else from the
dashboard flows: no seed, no scenario, no dashboard. The builder (`--build`) is the exception.

Import this module without importing the `LevityDash` package, and call
`prepare()` first.
"""
import os
import sys

from _seed import DEFAULT_SEED, parseFlag

DEFAULT_SCENARIO = 'hot-clear-day'


def prepare(argv=None) -> None:
	"""Point every LevityDash directory at a temp dir. With `--build`, also stage the builder's dashboard.

	The builder draws on a real dashboard, so it seeds that temp dir from `devtools/design-seed` and turns on the
	Fixture plugin for `--scenario` (default `hot-clear-day`). The gauge editor needs neither.
	"""
	argv = sys.argv if argv is None else argv
	os.environ['LEVITYDASH_CONFIG_DEBUG'] = '1'
	os.environ.pop('LEVITYDASH_CONFIG_SEED', None)
	if '--build' in argv:
		os.environ['LEVITYDASH_FIXTURE'] = parseFlag(argv, '--scenario') or DEFAULT_SCENARIO
		# Values arrive after the first (blank) board settles, so every preview's displays find them already published.
		os.environ.setdefault('LEVITYDASH_FIXTURE_DELAY_MS', 'end')
		os.environ['LEVITYDASH_CONFIG_SEED'] = parseFlag(argv, '--seed') or str(DEFAULT_SEED)
