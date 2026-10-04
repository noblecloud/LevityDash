"""A setter that raises must not leave the object stuck in `is_loading`.

`setItemState` fills `_unset_keys_` before it applies any property and used to
clear it only on success, so one raising setter kept `is_loading` True (and an
ActionPool's `can_execute` False) for that object permanently.

Pure Python - no Qt, no LevityDash import required.
"""
import pytest

from statekit import Stateful, StateProperty


class Boom(Stateful, tag='boom'):
	@StateProperty(key='size', default=10)
	def size(self) -> int:
		return getattr(self, '_size', 10)

	@size.setter
	def size(self, value: int):
		raise RuntimeError('bad value')


def test_raising_setter_leaves_is_loading_false():
	obj = Boom()
	with pytest.raises(RuntimeError):
		obj.setItemState({'size': 5})
	assert not obj.is_loading
