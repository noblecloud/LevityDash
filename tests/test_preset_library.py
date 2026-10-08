"""The presets that ship with the app: each one loads, fills from its own defaults, and the example boards use them cleanly."""
from pathlib import Path

import pytest
import yaml

from LevityDash.lib import presets

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = sorted(p.stem for p in (ROOT / 'src/LevityDash/resources/presets').glob('*.yaml'))
BOARDS = sorted(p for p in (ROOT / 'docs/design-references').rglob('*.levity') if 'preset:' in p.read_text())


def _failed(node):
	if isinstance(node, dict):
		yield from ([node] if node.get('type') == presets.FAILED else [])
		for value in node.values():
			yield from _failed(value)
	elif isinstance(node, list):
		for value in node:
			yield from _failed(value)


def test_the_library_is_not_empty():
	assert len(SHIPPED) >= 12


@pytest.mark.parametrize('name', SHIPPED)
def test_a_shipped_preset_expands_from_its_defaults(name):
	item = presets.expand([{'preset': name}])[0]
	assert not list(_failed(item)), [f['message'] for f in _failed(item)]
	assert presets.PRESET not in item, 'a nested preset is expanded too'


@pytest.mark.parametrize('name', SHIPPED)
def test_every_property_of_a_shipped_preset_says_what_it_is(name):
	preset = presets.load(name)
	assert preset.doc, f'{name} has no doc line'
	missing = [p.name for p in preset.props.values() if not p.doc]
	assert not missing, f'{name}: properties without a doc: {missing}'


@pytest.mark.parametrize('board', BOARDS, ids=lambda p: p.name)
def test_a_design_board_uses_presets_without_an_error_tile(board):
	data = presets.expand(yaml.safe_load(board.read_text()))
	assert not list(_failed(data)), [f['message'] for f in _failed(data)]
