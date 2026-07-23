"""WireClient's request/response correlation (lib/wire/client.py) - the
receive-side counterpart to test_wire_ts_transport.py's server dispatch.

Exercises concurrent requests, unmatched/late responses, and that ordinary
'update' messages still reach on_message unaffected by any pending request -
over a real socket, using a hand-written server loop rather than WireServer
(this is specifically testing WireClient in isolation).
"""
import asyncio
import json

import aiohttp
from aiohttp import web

from LevityDash.lib.wire.client import WireClient


async def _serve_delayed_responses(delays: dict):
	"""A minimal server: echoes back {id, delay-keyed} as a ts_response after
	the requested delay, so concurrent requests resolve out of send order."""
	async def handler(request):
		ws = web.WebSocketResponse()
		await ws.prepare(request)
		async for msg in ws:
			if msg.type == aiohttp.WSMsgType.TEXT:
				incoming = json.loads(msg.data)
				delay = delays.get(incoming['id'], 0)
				await asyncio.sleep(delay)
				await ws.send_str(json.dumps({'v': 1, 'type': 'ts_response', 'id': incoming['id'], 'echo': incoming['id']}))
		return ws

	app = web.Application()
	app.router.add_get('/ws', handler)
	runner = web.AppRunner(app)
	await runner.setup()
	site = web.TCPSite(runner, '127.0.0.1', 0)
	await site.start()
	port = site._server.sockets[0].getsockname()[1]
	return runner, f'ws://127.0.0.1:{port}/ws'


def test_concurrent_requests_resolve_to_correct_futures():
	async def scenario():
		# req-slow answers after req-fast is sent, proving correlation isn't
		# just "whatever comes back next" ordering.
		runner, url = await _serve_delayed_responses({'req-slow': 0.3, 'req-fast': 0.0})
		client = WireClient(url, on_message=lambda m: None)
		await client.connect()

		slow = asyncio.ensure_future(client.request({'v': 1, 'type': 'ts_request', 'id': 'req-slow'}))
		fast = asyncio.ensure_future(client.request({'v': 1, 'type': 'ts_request', 'id': 'req-fast'}))

		fast_result = await fast
		slow_result = await slow

		await client.close()
		await runner.cleanup()
		return fast_result, slow_result

	fast_result, slow_result = asyncio.run(scenario())
	assert fast_result['id'] == 'req-fast'
	assert slow_result['id'] == 'req-slow'


def test_update_messages_still_reach_on_message_during_pending_request():
	async def scenario():
		async def handler(request):
			ws = web.WebSocketResponse()
			await ws.prepare(request)
			# push an ordinary 'update' message immediately, then answer the
			# pending ts_request after a short delay
			await ws.send_str(json.dumps({'v': 1, 'type': 'update', 'source': {'name': 'X'}, 'updates': {}}))
			async for msg in ws:
				if msg.type == aiohttp.WSMsgType.TEXT:
					incoming = json.loads(msg.data)
					await asyncio.sleep(0.1)
					await ws.send_str(json.dumps({'v': 1, 'type': 'ts_response', 'id': incoming['id']}))
			return ws

		app = web.Application()
		app.router.add_get('/ws', handler)
		runner = web.AppRunner(app)
		await runner.setup()
		site = web.TCPSite(runner, '127.0.0.1', 0)
		await site.start()
		port = site._server.sockets[0].getsockname()[1]

		updates_seen = []
		client = WireClient(f'ws://127.0.0.1:{port}/ws', on_message=updates_seen.append)
		await client.connect()

		response = await client.request({'v': 1, 'type': 'ts_request', 'id': 'req-1'})

		await client.close()
		await runner.cleanup()
		return updates_seen, response

	updates_seen, response = asyncio.run(scenario())
	assert len(updates_seen) == 1 and updates_seen[0]['type'] == 'update'
	assert response['id'] == 'req-1'


async def _serve_silently(_request):
	"""Accepts the connection and never sends anything back - simulates a
	backend that's still processing when the client gives up on it."""
	ws = web.WebSocketResponse()
	await ws.prepare(_request)
	async for _ in ws:
		pass
	return ws


def test_close_fails_pending_requests_instead_of_hanging():
	async def scenario():
		app = web.Application()
		app.router.add_get('/ws', _serve_silently)
		runner = web.AppRunner(app)
		await runner.setup()
		site = web.TCPSite(runner, '127.0.0.1', 0)
		await site.start()
		port = site._server.sockets[0].getsockname()[1]

		client = WireClient(f'ws://127.0.0.1:{port}/ws', on_message=lambda m: None)
		await client.connect()

		pending = asyncio.ensure_future(client.request({'v': 1, 'type': 'ts_request', 'id': 'never-answered'}, timeout=30))
		await asyncio.sleep(0.1)
		await client.close()
		await runner.cleanup()

		try:
			await pending
			return 'did not raise'
		except Exception as e:
			return type(e).__name__

	result = asyncio.run(scenario())
	assert result == 'ConnectionError'
