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


def test_late_client_gets_every_key_not_only_the_last_batch():
	"""A key published once (the daily forecast) must survive later batches that carry other keys."""
	async def scenario():
		server = WireServer()
		await server.start()
		first = _make_update_message()
		second = _make_update_message()
		second['updates'] = {'environment.light.sunrise': second['updates'].pop('environment.temperature.temperature')}
		await server.broadcast(first)
		await server.broadcast(second)
		received: list[dict] = []
		client = WireClient(server.url, received.append)
		await client.connect()
		ok = await _wait_for(lambda: bool(received))
		await client.close()
		await server.stop()
		return ok, received

	ok, received = asyncio.run(scenario())
	assert ok
	keys = set().union(*(m['updates'] for m in received if m.get('type') == 'update'))
	assert keys == {'environment.temperature.temperature', 'environment.light.sunrise'}


def test_a_value_with_no_json_form_does_not_drop_the_client():
	"""A bare sentinel in a stored update used to raise in the replay, dropping each frontend as it connected."""
	async def scenario():
		server = WireServer()
		await server.start()
		message = _make_update_message()
		message['updates']['environment.temperature.temperature']['value'] = object()
		await server.broadcast(message)
		received: list[dict] = []
		client = WireClient(server.url, received.append)
		await client.connect()
		ok = await _wait_for(lambda: bool(received))
		await server.broadcast(_make_update_message())
		ok = ok and await _wait_for(lambda: len(received) >= 2)
		await client.close()
		await server.stop()
		return ok, received

	ok, received = asyncio.run(scenario())
	assert ok, 'the client was dropped or never got the replay'
	assert received[0]['updates']['environment.temperature.temperature']['value'] is None
	assert received[1]['updates']['environment.temperature.temperature']['value'] == 72.0


def test_a_container_answering_novalue_is_not_encoded():
	"""A recorded log with no entries answers NoValue (a bare object()); it has nothing to push."""
	from types import SimpleNamespace
	from LevityDash.lib.utils.various import NoValue
	from LevityDash.lib.wire.messages import encode_container
	container = SimpleNamespace(value=SimpleNamespace(value=NoValue, timestamp=None), metadata={}, title='t')
	assert encode_container(container) is None
