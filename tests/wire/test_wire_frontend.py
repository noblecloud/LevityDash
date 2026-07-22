"""RemoteFrontend: decoded wire messages -> RemoteContainer updates (step 3).

The receive-side mirror of LoopbackBridge, exercised in isolation: a full
update message goes in, a batch of populated RemoteContainers comes out to the
callback - no socket, no dispatcher, no Qt app.
"""
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.wire.codec import encode_value
from LevityDash.lib.wire.frontend import RemoteFrontend
from LevityDash.lib.wire.messages import encode_update_message

_KEY = 'environment.temperature.temperature'


def _update_message() -> dict:
	return encode_update_message(
		name='TestPlugin',
		defaultFor={'temperature'},
		enabled=True,
		running=True,
		updates={
			_KEY: {
				'value': encode_value(72.0),
				'timestamp': None,
				'title': 'Temperature',
				'metadata': {'title': 'Temperature'},
				'icon_alias': None,
				'flags': {},
			}
		},
	)


def test_applies_update_and_dispatches_batch():
	batches = []
	fe = RemoteFrontend(on_update=batches.append)
	fe.handle_message(_update_message())

	assert len(batches) == 1
	values = batches[0]
	key = CategoryItem(_KEY)
	assert key in values
	container = values[key]
	assert container.value is not None
	assert float(container.value.value) == 72.0
	assert container.title == 'Temperature'


def test_reuses_remote_source_across_messages():
	fe = RemoteFrontend(on_update=lambda _: None)
	fe.handle_message(_update_message())
	fe.handle_message(_update_message())
	# same source name -> one RemoteSource, reused (not recreated per message)
	assert list(fe._sources) == ['TestPlugin']


def test_ignores_non_update_messages():
	batches = []
	fe = RemoteFrontend(on_update=batches.append)
	fe.handle_message({'v': 1, 'type': 'hello'})
	assert batches == []
