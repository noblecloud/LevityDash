"""The layout port is a skeleton: stubs that name the CSS section they will implement."""
import inspect
import re
from pathlib import Path

import pytest

from LevityDash.lib import layout
from LevityDash.lib.layout import REGISTRY, pending

SRC = Path(__file__).parents[2] / 'src'


def test_every_stub_names_its_spec_section():
	assert len(REGISTRY) >= 20
	for name, section in REGISTRY.items():
		assert section.spec in {'css-flexbox-1', 'css-grid-1', 'css-align-3'}, name
		assert section.title, name


def test_every_registered_function_is_documented_and_typed():
	for module in (layout.align, layout.flex, layout.grid, layout.legacy):
		for function in vars(module).values():
			if getattr(function, '__section__', None) is None:
				continue
			assert inspect.getdoc(function), function.__qualname__
			assert 'return' in function.__annotations__, function.__qualname__


def test_a_pending_stub_raises_until_it_is_filled_in():
	# A thread that fills a stub sets status='done' on its decorator and drops this expectation.
	with pytest.raises(NotImplementedError):
		layout.flex.resolve_flexible_lengths([], 0.0, 0.0)
	assert layout.flex.resolve_flexible_lengths.__section__.status == 'stub'
	assert 'LevityDash.lib.layout.flex.resolve_flexible_lengths' in pending()


def test_the_package_needs_no_qt():
	for path in (SRC / 'LevityDash' / 'lib' / 'layout').glob('*.py'):
		imports = re.findall(r'^\s*(?:from|import)\s+\S+', path.read_text(), re.M)
		assert not [i for i in imports if re.search(r'PySide6|lib\.ui|frontends', i)], path.name


@pytest.mark.skip(reason='fills in when layout_flex and legacy.stack_as_flex are done')
def test_a_legacy_stack_and_its_flex_form_agree():
	"""Unsized items split the rest equally, sized items keep their size, spacing is the gap."""
	container, items = layout.legacy.stack_as_flex('horizontal', [100, None, None], 10, (0, 0), (0, 0), 400, 50)
	rects = layout.flex.layout_flex(items, container)
	assert [r.width for r in rects] == [100, 135, 135]
	assert [r.x for r in rects] == [0, 110, 255]
	assert all(r.height == 50 for r in rects)
