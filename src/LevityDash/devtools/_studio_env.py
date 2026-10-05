"""Dev-only: set the environment before the first `LevityDash` import. Gauge Studio.

`import LevityDash` builds the `QApplication` and the config object. With no
override the config object reads, and creates files in, the real config
directory. `LEVITYDASH_CONFIG_DEBUG=1` makes every `LevityDash` directory a
throwaway temp directory. The studio sets it here and nothing else from the
dashboard flows: no seed, no scenario, no dashboard.

Import this module without importing the `LevityDash` package, and call
`prepare()` first.
"""
import os


def prepare() -> None:
	os.environ['LEVITYDASH_CONFIG_DEBUG'] = '1'
	os.environ.pop('LEVITYDASH_CONFIG_SEED', None)
