"""validate raises StateError with a reason; setItemState skips that property only.

Pure Python - no Qt, no LevityDash import required.
"""
import logging

import pytest

from statekit import StateError, Stateful, StateProperty, firstOf


def positive(owner, value):
	if value <= 0:
		raise StateError('size must be positive')
	return value


class Box(Stateful, tag='box'):
	@StateProperty(key='size', default=10, validators=[positive])
	def size(self) -> int:
		return getattr(self, '_size', 10)

	@size.setter
	def size(self, value: int):
		self._size = value

	@StateProperty(key='label', default='x')
	def label(self) -> str:
		return getattr(self, '_label', 'x')

	@label.setter
	def label(self, value: str):
		self._label = value


def test_bad_property_is_skipped_and_logged(caplog):
	box = Box()
	with caplog.at_level(logging.ERROR):
		box.setItemState({'size': -3, 'label': 'ok'})
	assert box.size == 10
	assert box.label == 'ok'
	assert not box.is_loading
	assert any('Box' in r.message and 'size' in r.message and 'must be positive' in r.message for r in caplog.records)


def test_good_value_still_sets():
	box = Box()
	box.setItemState({'size': 4, 'label': 'ok'})
	assert box.size == 4


def test_direct_assignment_raises_with_reason():
	with pytest.raises(StateError, match='must be positive'):
		Box().size = 0


def test_validator_can_coerce():
	class Coerced(Stateful, tag='coerced'):
		@StateProperty(key='n', default=0)
		def n(self) -> int:
			return getattr(self, '_n', 0)

		@n.setter
		def n(self, value: int):
			self._n = value

		@n.validator
		def n(self, value):
			return int(value)

	c = Coerced()
	c.setItemState({'n': '7'})
	assert c.n == 7


def test_firstOf_first_match_wins():
	parse = firstOf(float, lambda text: text.upper())
	assert parse('2.5') == 2.5
	assert parse('abc') == 'ABC'
	with pytest.raises(StateError, match='matched none'):
		firstOf(float, int)('abc')


def test_condition_still_drops_silently():
	class Cond(Stateful, tag='cond'):
		@StateProperty(key='n', default=1)
		def n(self) -> int:
			return getattr(self, '_n', 1)

		@n.setter
		def n(self, value: int):
			self._n = value

		@n.condition(method='set')
		def n(value) -> bool:
			return value > 0

	c = Cond()
	c.setItemState({'n': -1})
	assert c.n == 1
	c.setItemState({'n': 5})
	assert c.n == 5
