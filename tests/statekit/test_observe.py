"""observe fires on a real change only, with the old value, and not during load.

Pure Python - no Qt, no LevityDash import required.
"""
from statekit import Stateful, StateProperty

seen = []


class Dial(Stateful, tag='dial'):
	@StateProperty(key='level', default=0)
	def level(self) -> int:
		return self._level

	@level.setter
	def level(self, value: int):
		self._level = value

	@level.observe
	def level(self, change):
		seen.append((change.name, change.old, change.new, change.owner is self))


def setup_function():
	seen.clear()


def test_same_value_twice_fires_once():
	dial = Dial()
	dial.level = 3
	dial.level = 3
	assert len(seen) == 1
	assert seen[0][2] == 3


def test_old_value_arrives():
	dial = Dial()
	dial.level = 3
	seen.clear()
	dial.level = 5
	assert seen == [('level', 3, 5, True)]


def test_muted_during_load():
	dial = Dial()
	dial.setItemState({'level': 9})
	assert dial.level == 9
	assert seen == []
	dial.level = 10
	assert seen == [('level', 9, 10, True)]
