from LevityDash.lib.plugins.utils import ChannelSignal


class _Owner:
	def __init__(self):
		self.calls = 0

	def slot(self, observations):
		self.calls += 1


def _channel():
	return ChannelSignal(source=None, key=None)


def test_same_slot_connected_twice_runs_once_per_emit():
	channel, owner = _channel(), _Owner()
	assert channel.connectSlot(owner.slot)
	assert channel.connectSlot(owner.slot)
	channel.publish({1})
	assert owner.calls == 1


def test_disconnect_then_reconnect_still_delivers():
	channel, owner = _channel(), _Owner()
	channel.connectSlot(owner.slot)
	channel.disconnectSlot(owner.slot)
	channel.connectSlot(owner.slot)
	channel.publish({1})
	assert owner.calls == 1
