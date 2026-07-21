"""WireServer <-> WireClient over a real localhost WebSocket (Phase 4.2 step 2).

Proves the transport carries the wire-message contract (envelope + codec-encoded
values) intact across an actual socket — the socket-backed analogue of the
in-process loopback round-trip — and that a late-joining client gets the
replayed snapshot. No plugins/Qt: this exercises the pipe, not the integration.
"""
import asyncio

from LevityDash.lib.utils.shared import now  # app (shim) datetime — the type codec encodes
from LevityDash.lib.wire.client import WireClient
from LevityDash.lib.wire.codec import encode_value
from LevityDash.lib.wire.server import WireServer


def _make_update_message() -> dict:
	return {
		'v': 1,
		'type': 'update',
		'source': {'name': 'TestPlugin', 'defaultFor': ['temperature'], 'enabled': True, 'running': True},
		'updates': {
			'environment.temperature.temperature': {
				'value': encode_value(72.0),
				'timestamp': encode_value(now()),  # a real codec datetime envelope, not a plain string
				'title': 'Temperature',
				'metadata': {},
				'icon_alias': None,
				'flags': {},
			}
		},
	}


async def _wait_for(pred, timeout: float = 2.0) -> bool:
	loop = asyncio.get_running_loop()
	end = loop.time() + timeout
	while loop.time() < end:
		if pred():
			return True
		await asyncio.sleep(0.02)
	return False


def test_broadcast_reaches_connected_client():
	async def scenario():
		server = WireServer()
		await server.start()
		received: list[dict] = []
		client = WireClient(server.url, received.append)
		await client.connect()
		await server.broadcast(_make_update_message())
		ok = await _wait_for(lambda: bool(received))
		await client.close()
		await server.stop()
		return ok, received

	ok, received = asyncio.run(scenario())
	assert ok, 'client did not receive the broadcast'
	got = received[0]
	assert got['source']['name'] == 'TestPlugin'
	value = got['updates']['environment.temperature.temperature']
	# the codec envelope survived the socket + JSON round-trip intact
	assert value['value'] == 72.0
	assert value['timestamp']['__type__'] == 'datetime'
	assert isinstance(value['timestamp']['value'], str)


def test_snapshot_replayed_to_late_client():
	async def scenario():
		server = WireServer()
		await server.start()
		# broadcast with nobody connected — must be stored and replayed on connect
		await server.broadcast(_make_update_message())
		received: list[dict] = []
		client = WireClient(server.url, received.append)
		await client.connect()
		ok = await _wait_for(lambda: bool(received))
		await client.close()
		await server.stop()
		return ok, received

	ok, received = asyncio.run(scenario())
	assert ok, 'late client did not receive the replayed snapshot'
	assert received[0]['source']['name'] == 'TestPlugin'
