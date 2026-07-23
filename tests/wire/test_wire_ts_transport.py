"""ts_request/ts_response over a real localhost WebSocket (timeseries-over-wire
milestone, transport layer only).

Proves the request/response envelope round-trips over an actual socket and
that the reply is unicast to the requesting connection - not broadcast to
every connected frontend, which would be a real correctness bug (other
frontends silently receiving responses to requests they never made). Uses a
stub `on_request` handler, not RemoteBackend - this exercises the pipe
(server.py's dispatch + client.py's correlation), not the plugin integration.
"""
import asyncio

from LevityDash.lib.wire.client import WireClient
from LevityDash.lib.wire.server import WireServer


async def _stub_handler(incoming: dict) -> dict:
	return {'v': 1, 'type': 'ts_response', 'id': incoming['id'], 'ok': True, 'echo': incoming['key']}


def test_request_reaches_handler_and_response_returns_to_requester():
	async def scenario():
		server = WireServer(on_request=_stub_handler)
		await server.start()
		client = WireClient(server.url, on_message=lambda m: None)
		await client.connect()

		response = await client.request({'v': 1, 'type': 'ts_request', 'id': 'req-1', 'source': 'X', 'key': 'k'})

		await client.close()
		await server.stop()
		return response

	response = asyncio.run(scenario())
	assert response['id'] == 'req-1'
	assert response['ok'] is True
	assert response['echo'] == 'k'


def test_response_is_unicast_not_broadcast():
	async def scenario():
		server = WireServer(on_request=_stub_handler)
		await server.start()

		requester = WireClient(server.url, on_message=lambda m: None)
		await requester.connect()
		bystander_seen = []
		bystander = WireClient(server.url, on_message=bystander_seen.append)
		await bystander.connect()

		await requester.request({'v': 1, 'type': 'ts_request', 'id': 'req-2', 'source': 'X', 'key': 'k'})
		await asyncio.sleep(0.2)  # give a stray broadcast a chance to arrive if this regresses

		await requester.close()
		await bystander.close()
		await server.stop()
		return bystander_seen

	bystander_seen = asyncio.run(scenario())
	assert bystander_seen == [], 'a second connected client must not receive another client\'s ts_response'


def test_unhandled_request_type_is_ignored_not_erroring():
	async def scenario():
		server = WireServer(on_request=_stub_handler)
		await server.start()
		received = []
		client = WireClient(server.url, on_message=received.append)
		await client.connect()
		await client.send({'v': 1, 'type': 'subscribe', 'id': 'not-a-ts-request'})
		await asyncio.sleep(0.2)
		ok = True  # if the server crashed, the next line would fail
		await client.send({'v': 1, 'type': 'ts_request', 'id': 'req-3', 'source': 'X', 'key': 'k'})
		response = await client.request({'v': 1, 'type': 'ts_request', 'id': 'req-4', 'source': 'X', 'key': 'k'})
		await client.close()
		await server.stop()
		return ok, response

	ok, response = asyncio.run(scenario())
	assert ok
	assert response['ok'] is True


def test_no_handler_registered_leaves_requester_to_time_out():
	async def scenario():
		server = WireServer()  # no on_request wired up
		await server.start()
		client = WireClient(server.url, on_message=lambda m: None)
		await client.connect()
		try:
			await client.request({'v': 1, 'type': 'ts_request', 'id': 'req-5', 'source': 'X', 'key': 'k'}, timeout=0.3)
			return 'no timeout'
		except asyncio.TimeoutError:
			return 'timed out'
		finally:
			await client.close()
			await server.stop()

	result = asyncio.run(scenario())
	assert result == 'timed out'
