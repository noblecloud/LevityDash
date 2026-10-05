"""A Binding pushes a source into a setter and releases the source on unlink.

Pure Python - no Qt, no LevityDash import required.
"""
from qolkit import Unset
from statekit import Binding, Constant, Stateful


class Feed:
	"""A source with a subscriber list, to count subscribers."""

	def __init__(self, value=Unset):
		self.value = value
		self.subscribers = []
		self.released = 0

	def get(self):
		return self.value

	def subscribe(self, callback):
		self.subscribers.append(callback)
		return lambda: self.subscribers.remove(callback)

	def release(self):
		self.released += 1

	def emit(self, value):
		self.value = value
		for callback in list(self.subscribers):
			callback(value)


def test_constant_pushes_once():
	got = []
	Binding(Constant(4), got.append)
	assert got == [4]


def test_follows_source_and_transform():
	feed, got = Feed(1), []
	Binding(feed, got.append, lambda v: v * 10)
	feed.emit(2)
	assert got == [10, 20]


def test_unset_is_skipped():
	feed, got = Feed(), []
	Binding(feed, got.append)
	assert got == []
	feed.emit(3)
	assert got == [3]


def test_unlink_drops_subscriber_and_releases_once():
	feed, got = Feed(1), []
	binding = Binding(feed, got.append)
	assert len(feed.subscribers) == 1
	binding.unlink()
	binding.unlink()
	assert feed.subscribers == []
	assert feed.released == 1
	feed.emit(9)
	assert got == [1]


def test_setter_that_raises_does_not_propagate():
	def boom(value):
		raise RuntimeError('no')

	feed = Feed(1)
	Binding(feed, boom)
	feed.emit(2)


def test_replacing_a_slot_unlinks_the_old_source():
	class Owner(Stateful, tag='bound-owner'):
		pass

	owner, got = Owner(), []
	old, new = Feed(1), Feed(2)
	owner.bind('value', old, got.append)
	owner.bind('value', new, got.append)
	assert old.subscribers == [] and old.released == 1
	assert len(new.subscribers) == 1
	owner.unbind()
	assert new.subscribers == [] and new.released == 1
	assert got == [1, 2]
