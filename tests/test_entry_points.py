"""Every console script in pyproject.toml is spec-correct.

`LevityDash = 'LevityDash:__main__.main'` looks reasonable and is wrong: in an
entry point the part after the colon is a dotted path of *attributes*, and
`__main__` is a submodule, so it only resolves once something else has already
imported it. pip's generated wrapper hid this with `from LevityDash import
__main__`, but Poetry's runner does `import_module('LevityDash').__main__.main`
and raised AttributeError - `poetry run LevityDash`, the first command in the
README, did not start the app at all.

These check the *declaration* rather than importing each target: importing
`LevityDash.backend` pins mode=live process-wide, which would poison the rest
of the session.
"""
import tomllib
from importlib.util import find_spec
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).resolve().parents[1] / 'pyproject.toml'


def _spec(name):
	"""find_spec, but None instead of raising when a parent is not a package."""
	try:
		return find_spec(name)
	except (ImportError, AttributeError, ValueError):
		return None


def _scripts():
	data = tomllib.loads(PYPROJECT.read_text())
	scripts = data['tool']['poetry']['scripts']
	return sorted(scripts.items())


@pytest.mark.parametrize('name,target', _scripts())
def test_module_half_is_importable(name, target):
	module, _, attr = target.partition(':')
	assert attr, f'{name}: {target!r} has no ":function" half'
	assert _spec(module) is not None, f'{name}: no module {module!r}'


@pytest.mark.parametrize('name,target', _scripts())
def test_attribute_half_is_not_a_submodule(name, target):
	# The exact defect: `pkg:sub.func` where `sub` is a submodule of `pkg`.
	module, _, attr = target.partition(':')
	first = attr.split('.')[0]
	assert _spec(f'{module}.{first}') is None, (
		f'{name}: {target!r} treats submodule {module}.{first!r} as an attribute of '
		f'{module!r}. Entry points resolve the post-colon path with getattr, so this '
		f'only works if something already imported it. Write {module}.{first}:{attr.split(".", 1)[-1]} instead.'
	)
