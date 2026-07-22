"""Full wire receive path over a real socket (Phase 4.2 steps 2+3 composed):

    WireServer.broadcast  ->  [socket]  ->  WireClient  ->  RemoteFrontend  ->  RemoteContainer

Proves the frontend receive stack is whole end-to-end ahead of the backend
process that will eventually feed it. The server broadcasts a hand-built update
message (no live plugins / Qt app) so this exercises the plumbing, not the
integration.
"""
import asyncio

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.wire.client import WireClient
from LevityDash.lib.wire.codec import encode_value
from LevityDash.lib.wire.frontend import RemoteFrontend
from LevityDash.lib.wire.messages import encode_update_message
from LevityDash.lib.wire.server import WireServer

_KEY = 'environment.temperature.temperature'


def _update(value: float) -> dict:
	return encode_update_message(
		name='TestPlugin',
		defaultFor={'temperature'},
		enabled=True,
		running=True,
		updates={
			_KEY: {
				'value': encode_value(value),
				'timestamp': None,
				'title': 'Temperature',
				'metadata': {'title': 'Temperature'},
				'icon_alias': None,
				'flags': {},
			}
		},
	)


async def _wait_for(pred, timeout: float = 2.0) -> bool:
	loop = asyncio.get_running_loop()
	end = loop.time() + timeout
	while loop.time() < end:
		if pred():
			return True
		await asyncio.sleep(0.02)
	return False


def test_broadcast_lands_as_populated_remote_container():
	# RemoteFrontend reuses one RemoteContainer per key (updated in place, as a
	# live stand-in should be), so snapshot the value at receipt rather than
	# holding container references that later mutate.
	seen: list = []

	def on_update(values):
		key = CategoryItem(_KEY)
		seen.append(float(values[key].value.value))

	async def scenario():
		server = WireServer()
		await server.start()
		frontend = RemoteFrontend(on_update=on_update)
		client = WireClient(server.url, frontend.handle_message)
		await client.connect()

		await server.broadcast(_update(72.0))
		got_first = await _wait_for(lambda: len(seen) >= 1)

		# a second value flows through as an incremental update onto the same container
		await server.broadcast(_update(48.0))
		got_second = await _wait_for(lambda: len(seen) >= 2)

		await client.close()
		await server.stop()
		return got_first, got_second

	got_first, got_second = asyncio.run(scenario())
	assert got_first, 'first update never reached the frontend'
	assert got_second, 'second update never reached the frontend'
	assert seen == [72.0, 48.0]
