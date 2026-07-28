"""A key removed from incoming state must return to its default.

Absent means default. Without this, deleting a line from a `.levity` does
nothing until the app is restarted: `setItemState` only visits properties that
appear in the incoming state (the `items` filter at core.py:2048-2052), so a
value set by a *previous* load simply persists on the reused object.

Only properties currently sourced from `UserConfig` revert - ones an earlier
load actually set - which is what keeps preset/`shared:` values, factory-built
children and item defaults out of it.

Pure Python - no Qt, no LevityDash import required.
"""
from statekit import Stateful, StateProperty
from statekit.defaults import SourceType


class Widget(Stateful, tag='widget'):
	@StateProperty(key='label', default='untitled')
	def label(self) -> str:
		return getattr(self, '_label', 'untitled')

	@label.setter
	def label(self, value: str):
		self._label = value

	@StateProperty(key='size', default=10)
	def size(self) -> int:
		return getattr(self, '_size', 10)

	@size.setter
	def size(self, value: int):
		self._size = value

	@StateProperty(key='note')
	def note(self) -> str:
		return getattr(self, '_note', 'no-default')

	@note.setter
	def note(self, value: str):
		self._note = value


def test_key_removed_from_state_reverts_to_default():
	widget = Widget()
	widget.state = {'label': 'Wind', 'size': 42}
	assert widget.label == 'Wind'
	assert widget.size == 42

	# second load, `label` deleted from the file
	widget.state = {'size': 42}

	assert widget.label == 'untitled', 'a deleted key kept its old value'
	assert widget.size == 42, 'a key still present was disturbed'


def test_reverted_key_is_no_longer_sourced_from_config():
	"""Otherwise the next reload reverts it again instead of skipping it."""
	widget = Widget()
	widget.state = {'label': 'Wind'}
	widget.state = {}

	prop = Widget.__state_items__['label']
	assert widget._state_item_sources.get(prop) is SourceType.Default


def test_never_set_key_is_left_alone():
	widget = Widget()
	widget.state = {'size': 3}
	assert widget.label == 'untitled'


def test_property_with_no_default_is_left_alone():
	"""Leaving a stale value is bad; guessing at a cleared one is worse."""
	widget = Widget()
	widget.state = {'note': 'keep me'}
	widget.state = {}
	assert widget.note == 'keep me'


def test_repeated_identical_loads_are_stable():
	widget = Widget()
	for _ in range(3):
		widget.state = {'label': 'Wind'}
	assert widget.label == 'Wind'


def test_construction_reverts_nothing():
	"""State is assigned at construction time; there is nothing to revert."""
	widget = Widget()
	widget.state = {'size': 7}
	assert widget.size == 7
	assert widget.label == 'untitled'


class Shared(Stateful, tag='shared-widget'):
	@StateProperty(key='label', default='untitled')
	def label(self) -> str:
		return getattr(self, '_label', 'untitled')

	@label.setter
	def label(self, value: str):
		self._label = value


def test_a_value_not_sourced_from_config_is_not_reverted():
	"""Guards preset/`shared:` inheritance and anything set at runtime."""
	widget = Shared()
	widget.state = {'label': 'FromConfig'}

	prop = Shared.__state_items__['label']
	# stand in for a value the object got from somewhere other than the file
	widget._state_item_sources[prop] = SourceType.Shared

	widget.state = {}

	assert widget.label == 'FromConfig'
