import asyncio
import json
import logging
import socket
from types import SimpleNamespace

from LevityDash.lib.plugins.web.reconnect import Backoff, keepConnected
from LevityDash.lib.plugins.web.socket_ import UDPSocket


def freePort() -> int:
	with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
		s.bind(('127.0.0.1', 0))
		return s.getsockname()[1]


def stubPlugin():
	return SimpleNamespace(name='Stub', pluginLog=logging.getLogger('test.reconnect'))


def send(port, message):
	with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
		s.sendto(json.dumps(message).encode(), ('127.0.0.1', port))


async def until(predicate, timeout=3.0):
	loop = asyncio.get_running_loop()
	end = loop.time() + timeout
	while not predicate():
		assert loop.time() < end, 'timed out'
		await asyncio.sleep(0.01)


def test_backoff_grows_to_its_cap_and_resets():
	b = Backoff(initial=1, maximum=5, factor=2)
	assert [b.next() for _ in range(5)] == [1, 2, 4, 5, 5]
	b.reset()
	assert b.next() == 1


def test_keep_connected_retries_after_failures_and_after_a_clean_return():
	calls = []

	async def connect():
		calls.append(1)
		if len(calls) == 1:
			raise OSError('network down')

	async def main():
		task = asyncio.create_task(keepConnected(connect, logging.getLogger('test.reconnect'), 'x', Backoff(initial=0.01, maximum=0.01)))
		await until(lambda: len(calls) >= 3)
		task.cancel()
		try:
			await task
		except asyncio.CancelledError:
			pass

	asyncio.run(main())


def test_udp_socket_binds_late_when_the_port_is_taken_at_first():
	port = freePort()
	received = []

	async def main():
		blocker = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		blocker.bind(('0.0.0.0', port))
		udp = UDPSocket(stubPlugin(), port=port)
		udp.handler.signal.connect(received.append)
		udp.start()
		await asyncio.sleep(0.1)
		assert not hasattr(udp, 'transport')
		blocker.close()
		await until(lambda: hasattr(udp, 'transport'), timeout=5)
		send(port, {'type': 'obs_st'})
		await until(lambda: received)
		udp.stop()

	asyncio.run(main())
	assert received == [{'type': 'obs_st'}]


def test_udp_socket_rebinds_after_its_transport_is_lost():
	port = freePort()
	received = []

	async def main():
		udp = UDPSocket(stubPlugin(), port=port)
		udp.handler.signal.connect(received.append)
		udp.start()
		await until(lambda: hasattr(udp, 'transport'))
		first = udp.transport
		send(port, {'n': 1})
		await until(lambda: len(received) == 1)
		first.abort()  # what an interface change does to the socket
		await until(lambda: udp.transport is not first, timeout=6)
		send(port, {'n': 2})
		await until(lambda: len(received) == 2)
		udp.stop()

	asyncio.run(main())
	assert received == [{'n': 1}, {'n': 2}]


def test_udp_stop_before_bind_does_not_raise():
	async def main():
		udp = UDPSocket(stubPlugin(), port=freePort())
		udp.stop()

	asyncio.run(main())


def test_weatherflow_websocket_reconnects_after_the_server_hangs_up():
	from aiohttp import web
	from LevityDash.lib.plugins.builtin.WeatherFlow import WFWebsocket

	opened = []

	async def handler(request):
		ws = web.WebSocketResponse()
		await ws.prepare(request)
		opened.append(1)
		if len(opened) == 1:
			await ws.close()
		else:
			await asyncio.sleep(5)
		return ws

	async def main():
		app = web.Application()
		app.router.add_get('/data', handler)
		runner = web.AppRunner(app)
		await runner.setup()
		port = freePort()
		await web.TCPSite(runner, '127.0.0.1', port).start()
		plugin = SimpleNamespace(
			loop=asyncio.get_running_loop(), pluginLog=logging.getLogger('test.reconnect'),
			config={'deviceID': 1},
			urls=SimpleNamespace(websocket=SimpleNamespace(url=f'http://127.0.0.1:{port}/data', params={})),
		)
		ws = WFWebsocket(plugin)
		backoff = Backoff(initial=0.05, maximum=0.05)
		task = asyncio.create_task(keepConnected(lambda: ws._connect(backoff), plugin.pluginLog, 'ws', backoff))
		await until(lambda: len(opened) == 2)
		task.cancel()
		try:
			await task
		except asyncio.CancelledError:
			pass
		await runner.cleanup()

	asyncio.run(main())
