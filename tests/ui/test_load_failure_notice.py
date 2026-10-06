"""One item that raises while loading must not cost the board.

It used to unwind the whole load, so the board stopped at whatever was built
first (the "just a big moon" symptom). Now the item is logged with its
traceback and replaced by an error tile; everything else loads.
"""

import logging

import pytest

from LevityDash.lib.ui.frontends.PySide import utils
from LevityDash.lib.ui.frontends.PySide.utils import _describeItem, _describeParent, itemLoader


class Boom(Exception):
	pass


class FakeParent:
	def childItems(self):
		return []


@pytest.fixture
def tiles(monkeypatch):
	made = []

	def explode(parent, items, existing, **kwargs):
		item = items[0]
		if item.get('key') == 'bad':
			raise Boom('the gauge could not build its value label')
		return [item['key']]

	monkeypatch.setattr(utils, 'loadRealtime', explode)
	monkeypatch.setattr(utils, '_errorTile', lambda parent, before, item, error: made.append((item, error)))
	return made


def test_a_failing_item_is_replaced_and_the_rest_load(tiles, caplog):
	items = [{'type': 'realtime.text', 'key': k} for k in ('a', 'bad', 'c')]
	with caplog.at_level(logging.ERROR):
		built = itemLoader(FakeParent(), items, existing=[])
	assert built == ['a', 'c']
	assert [item['key'] for item, _ in tiles] == ['bad']
	assert isinstance(tiles[0][1], Boom)
	record = next(r for r in caplog.records if r.levelno >= logging.ERROR)
	assert "key='bad'" in record.getMessage()
	assert record.exc_info is not None


@pytest.mark.parametrize(
	'item, expected',
	[
		({'type': 'realtime.text', 'key': 'a.b.c'}, "key='a.b.c'"),
		({'type': 'text', 'title': {'text': 'Pressure'}}, "title='Pressure'"),
		({'type': 'group'}, 'no key, name or title'),
	],
)
def test_describeItem_names_an_item_the_way_its_author_would(item, expected):
	assert expected in _describeItem(item)


def test_describeParent_falls_back_to_the_type_name():
	assert _describeParent(object()) == 'object'
