"""A failed dashboard load has to say so, loudly.

One item raising during the load unwinds the whole thing: the board stops at
whatever was built first, the window stays up, and the result looks like a
layout problem rather than a crash. That is how the "just a big moon" symptom
survived two months of debugging. These tests pin the notice - that it fires,
that it names the item that failed, and that it says what did not get built.
"""

import logging

import pytest

from LevityDash.lib.ui.frontends.PySide.utils import _describeItem, _describeParent, itemLoader


class Boom(Exception):
	pass


@pytest.fixture
def failingParent(monkeypatch):
	import LevityDash.lib.ui.frontends.PySide.utils as utils

	def explode(*args, **kwargs):
		raise Boom('the gauge could not build its value label')

	monkeypatch.setattr(utils, 'loadRealtime', explode)
	return object()


def test_the_notice_names_the_item_and_the_cost(failingParent, caplog):
	items = [
		{'type': 'realtime.text', 'key': 'environment.temperature.temperature'},
		{'type': 'realtime.text', 'key': 'environment.humidity.humidity'},
	]
	with caplog.at_level(logging.CRITICAL):
		with pytest.raises(Boom):
			itemLoader(failingParent, items, existing=[])

	notice = '\n'.join(r.getMessage() for r in caplog.records if r.levelno >= logging.CRITICAL)
	assert notice, 'a failed load logged nothing at CRITICAL'
	assert 'realtime' in notice
	assert 'environment.temperature.temperature' in notice
	assert 'not' in notice and 'loaded' in notice


def test_the_exception_carries_a_breadcrumb(failingParent):
	items = [{'type': 'realtime.text', 'key': 'environment.temperature.temperature'}]
	with pytest.raises(Boom) as caught:
		itemLoader(failingParent, items, existing=[])
	notes = '\n'.join(getattr(caught.value, '__notes__', []))
	assert 'realtime' in notes
	assert 'environment.temperature.temperature' in notes


def test_nested_loads_log_one_traceback_not_one_per_level(failingParent, caplog):
	"""Panels nest, so the same exception passes every frame on its way out."""
	items = [{'type': 'realtime.text', 'key': 'environment.temperature.temperature'}]
	error = None
	with caplog.at_level(logging.CRITICAL):
		try:
			itemLoader(failingParent, items, existing=[])
		except Boom as e:
			error = e
		caplog.clear()
		with pytest.raises(Boom):
			# the same exception object travelling through an outer frame
			raise error
	assert not [r for r in caplog.records if r.levelno >= logging.CRITICAL]
	assert getattr(error, '_levityLoadReported', False)


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
