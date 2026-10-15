"""`_yamlpatch.patch` changes only what changed and keeps the rest of the file as it was."""
import difflib
from pathlib import Path

import pytest
import yaml

from LevityDash.devtools import _yamlpatch as yp

REPO = Path(__file__).resolve().parents[2]
BOARDS = sorted((REPO / 'docs' / 'design-references' / 'dashboards').glob('*.levity'))

SAMPLE = """\
# A board.
theme: default
vars:
  t: environment.temperature.temperature   # the hero

items:
# the first stack
- type: stack
  name: main
  padding: 1.5mm
  items:

  # a group
  - type: group
    name: temperature
    geometry: {x: 0%, y: 0%, width: 58%, height: 52%}
    shared:
      display:
        font: Roboto Mono
  - type: realtime.text
    key: $t
    color: '#ff9124'
# the end
"""


def changed(old: str, new: str):
	return [l for l in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm='', n=0) if l[0] in '+-' and l[:3] not in ('+++', '---')]


def test_unchanged_data_gives_the_same_text():
	r = yp.patch(SAMPLE, yaml.safe_load(SAMPLE))
	assert r.exact and r.text == SAMPLE


def test_a_changed_scalar_changes_one_line_and_keeps_every_comment():
	data = yaml.safe_load(SAMPLE)
	data['items'][0]['padding'] = '2mm'
	r = yp.patch(SAMPLE, data)
	assert r.exact
	assert changed(SAMPLE, r.text) == ['-  padding: 1.5mm', '+  padding: 2mm']
	assert yaml.safe_load(r.text) == data


def test_a_changed_flow_mapping_stays_flow():
	data = yaml.safe_load(SAMPLE)
	data['items'][0]['items'][0]['geometry']['width'] = '60%'
	r = yp.patch(SAMPLE, data)
	assert changed(SAMPLE, r.text) == ['-    geometry: {x: 0%, y: 0%, width: 58%, height: 52%}', '+    geometry: {x: 0%, y: 0%, width: 60%, height: 52%}']


def test_a_new_key_and_a_new_item_are_added_and_nothing_else_moves():
	data = yaml.safe_load(SAMPLE)
	data['items'][0]['spacing'] = '2mm'
	data['items'][0]['items'].append({'type': 'group', 'name': 'extra'})
	r = yp.patch(SAMPLE, data)
	assert r.exact and yaml.safe_load(r.text) == data
	assert [l for l in changed(SAMPLE, r.text) if l[0] == '-'] == []
	assert '# a group' in r.text and '# the first stack' in r.text and '# the end' in r.text


def test_a_removed_item_takes_its_comment_with_it_and_keeps_the_others():
	data = yaml.safe_load(SAMPLE)
	del data['items'][0]['items'][0]
	r = yp.patch(SAMPLE, data)
	assert yaml.safe_load(r.text) == data
	assert '# a group' not in r.text and '# the first stack' in r.text


def test_a_moved_item_keeps_its_text_and_comment():
	data = yaml.safe_load(SAMPLE)
	kids = data['items'][0]['items']
	kids.reverse()
	r = yp.patch(SAMPLE, data)
	assert r.exact and yaml.safe_load(r.text) == data
	assert '# a group' in r.text


def test_an_anchor_falls_back_to_a_plain_dump_and_says_so():
	text = 'a: &x 1\nb: *x\n'
	r = yp.patch(text, {'a': 1, 'b': 2})
	assert not r.exact and yaml.safe_load(r.text) == {'a': 1, 'b': 2} and r.why


@pytest.mark.parametrize('board', BOARDS, ids=lambda p: p.name)
def test_a_real_board_round_trips_and_a_deep_edit_touches_one_line(board):
	text = board.read_text()
	data = yaml.safe_load(text)
	assert yp.patch(text, data).text == text
	edited = yaml.safe_load(text)

	def deepest(node):
		best = None
		if isinstance(node, dict):
			if 'geometry' in node and isinstance(node['geometry'], dict) and 'width' in node['geometry']:
				best = node
			for v in node.values():
				best = deepest(v) or best
		elif isinstance(node, list):
			for v in node:
				best = deepest(v) or best
		return best
	node = deepest(edited)
	if node is None:
		# split boards size their children by ratio and never write geometry; the round trip above is the whole check
		return
	node['geometry']['width'] = '37%'
	r = yp.patch(text, edited)
	assert r.exact, r.why
	assert yaml.safe_load(r.text) == edited
	diff = changed(text, r.text)
	assert len(diff) == 2, diff
	assert text.count('#') == r.text.count('#')
