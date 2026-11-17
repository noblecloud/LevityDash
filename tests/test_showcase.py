"""The showcase dashboards: the files on disk are what their generators write, and each scenario loads."""
import importlib
import sys
from pathlib import Path

import pytest
import yaml

SHOWCASE = Path(__file__).resolve().parents[1] / 'docs/design-references/showcase'
sys.path.insert(0, str(SHOWCASE))
BOARDS = importlib.import_module('build').BOARDS
ROOT = SHOWCASE.parents[2]


def levityOf(name) -> Path:
	"""Where a board's dashboard lives: beside its generator, or where the generator says (the shipped default)."""
	levity = getattr(importlib.import_module(name), 'LEVITY', None)
	return ROOT / levity if levity else SHOWCASE / f'{name}.levity'


@pytest.mark.parametrize('name', BOARDS)
def test_the_files_match_their_generator(name, tmp_path, monkeypatch):
	kit = importlib.import_module('kit')
	module = importlib.import_module(name)
	monkeypatch.setattr(kit, 'HERE', tmp_path)
	monkeypatch.setattr(kit, 'ROOT', tmp_path)
	kit._figures = kit.itertools.count(1)
	levity = getattr(module, 'LEVITY', None)
	kit.write(name, module.HEADER, module.board(), module.data(), module.FREEZE, levity=levity)
	written = tmp_path / levity if levity else tmp_path / f'{name}.levity'
	assert written.read_text() == levityOf(name).read_text(), f'run build.py: {name}.levity is stale'
	assert (tmp_path / 'scenarios' / f'{name}.yaml').read_text() == (SHOWCASE / 'scenarios' / f'{name}.yaml').read_text()


@pytest.mark.parametrize('name', BOARDS)
def test_the_scenario_has_every_key_the_board_reads(name):
	from LevityDash.lib.plugins.builtin.Fixture import buildSchema
	scenario = yaml.safe_load((SHOWCASE / 'scenarios' / f'{name}.yaml').read_text())
	schema, _ = buildSchema(scenario)
	assert scenario['start'] == -24
	keys = set(scenario['keys'])
	assert keys and all(len(e['series']) % 24 == 0 for e in scenario['keys'].values() if e.get('series'))
	board = yaml.safe_load(levityOf(name).read_text())

	def walk(node):
		if isinstance(node, dict):
			if node.get('type', '').startswith('realtime') and isinstance(node.get('key'), str):
				yield node['key']
			for v in node.values():
				yield from walk(v)
		elif isinstance(node, list):
			for v in node:
				yield from walk(v)

	plain = {k for k in walk(board) if ' ' not in k and '(' not in k}
	assert plain <= keys, sorted(plain - keys)
