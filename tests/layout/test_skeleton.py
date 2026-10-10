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


def test_a_finished_stub_is_marked_done_and_leaves_the_pending_list():
	# A thread that fills a stub sets status='done' on its decorator.
	assert layout.flex.resolve_flexible_lengths.__section__.status == 'done'
	assert 'LevityDash.lib.layout.flex.resolve_flexible_lengths' not in pending()


def test_the_package_needs_no_qt():
	for path in (SRC / 'LevityDash' / 'lib' / 'layout').glob('*.py'):
		imports = re.findall(r'^\s*(?:from|import)\s+\S+', path.read_text(), re.M)
		assert not [i for i in imports if re.search(r'PySide6|lib\.ui|frontends', i)], path.name


def test_a_legacy_stack_and_its_flex_form_agree():
	"""Unsized items split the rest equally, sized items keep their size, spacing is the gap."""
	container, items = layout.legacy.stack_as_flex('horizontal', [100, None, None], 10, (0, 0), (0, 0), 400, 50)
	rects = layout.flex.layout_flex(items, container)
	assert [r.width for r in rects] == [100, 140, 140]
	assert [r.x for r in rects] == [0, 110, 260]
	assert all(r.height == 50 for r in rects)


def test_a_vertical_legacy_stack_swaps_the_axes():
	container, items = layout.legacy.stack_as_flex('vertical', [None, 50], 10, (0, 0), (0, 0), 200, 80)
	rects = layout.flex.layout_flex(items, container)
	assert [(r.y, r.height) for r in rects] == [(0, 140), (150, 50)]
	assert all((r.x, r.width) == (0, 80) for r in rects)


def test_a_legacy_item_size_keeps_every_cell_the_same_and_leaves_the_rest_empty():
	container, items = layout.legacy.stack_as_flex('horizontal', [None, None], 10, (0, 0), (0, 0), 400, 50, item_size=100)
	assert [(r.x, r.width) for r in layout.flex.layout_flex(items, container)] == [(0, 100), (110, 100)]
