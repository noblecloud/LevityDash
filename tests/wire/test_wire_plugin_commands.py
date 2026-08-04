"""Full plugin-command path over a real socket:

    RemoteConnection.send_plugin_command
        -> [GUI-thread hop] -> WireClient.request
        -> [socket] -> WireServer -> _on_request -> RemoteBackend.handle_plugin_command
        -> (Qt-thread marshal) -> plugin.start()/stop()/restart()
        -> [socket] -> WireClient -> on_response(dict) on the GUI thread

Mirrors test_wire_ts_end_to_end.py: real WireServer/WireClient/RemoteBackend are
exercised; only the plugin-side target is a stand-in with start()/stop() that
record calls. Confirms the control-plane command half (the open item from
docs/tasks/timeseries-viewport-and-control-plane.md) actually round-trips, not
just that the message shapes encode/decode.
"""
import asyncio
import os
import threading
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from LevityDash.lib.wire.backend import RemoteBackend
from LevityDash.lib.wire.client import WireClient
from LevityDash.lib.wire.messages import build_plugin_command, decode_plugin_command_response
from LevityDash.lib.wire.server import WireServer
from PySide6.QtWidgets import QApplication

_SOURCE = 'TestPlugin'


class _FakePlugin:
	"""Stands in for a real Plugin: records start/stop calls and tracks running."""

	name = _SOURCE
	thread_pool = None  # handle_plugin_command calls start()/stop() directly, no pool needed

	def __init__(self):
		self.calls = []
		self.running = False

	def start(self):
		self.calls.append('start')
		self.running = True

	def stop(self):
		self.calls.append('stop')
		self.running = False


async def _run_command(server, name, command):
	"""Issue a command through a fresh WireClient and return the parsed response.

	Coroutine (not asyncio.run-wrapped) so it can be awaited from the test's own
	running event loop - nesting asyncio.run() raises RuntimeError. Pumps the
	Qt event loop while awaiting: RemoteBackend.handle_plugin_command marshals
	the actual start/stop onto the Qt main thread via a queued signal, which
	only fires when the loop is pumped (same as test_wire_ts_end_to_end.py).
	"""
	app = QApplication.instance()
	client = WireClient(server.url, lambda m: None)
	await client.connect()
	fut = asyncio.get_running_loop().create_future()

	async def _do():
		try:
			resp = await client.request(build_plugin_command(name=name, command=command))
		except Exception as e:
			resp = {'ok': False, 'error': repr(e)}
		if not fut.done():
			fut.set_result(resp)

	asyncio.ensure_future(_do())
	deadline = asyncio.get_running_loop().time() + 5.0
	while not fut.done() and asyncio.get_running_loop().time() < deadline:
		if app is not None:
			app.processEvents()
		await asyncio.sleep(0.01)
	result = await fut
	await client.close()
	return result


def test_start_and_stop_command_round_trip_over_the_wire():
	plugin = _FakePlugin()
	backend = RemoteBackend(send=lambda m: None)
	backend._plugins[_SOURCE] = plugin

	async def scenario():
		server = WireServer(on_request=backend.handle_plugin_command)
		await server.start()
		try:
			ok_start = await _run_command(server, _SOURCE, 'start')
			ok_stop = await _run_command(server, _SOURCE, 'stop')
			return ok_start, ok_stop
		finally:
			await server.stop()

	start_resp, stop_resp = asyncio.run(scenario())

	assert decode_plugin_command_response(start_resp) == (True, None)
	assert decode_plugin_command_response(stop_resp) == (True, None)
	# start then stop, in command order
	assert plugin.calls == ['start', 'stop']
	assert plugin.running is False


def test_restart_composes_stop_then_start():
	plugin = _FakePlugin()
	backend = RemoteBackend(send=lambda m: None)
	backend._plugins[_SOURCE] = plugin

	async def scenario():
		server = WireServer(on_request=backend.handle_plugin_command)
		await server.start()
		try:
			ok = await _run_command(server, _SOURCE, 'restart')
			return ok
		finally:
			await server.stop()

	resp = asyncio.run(scenario())
	assert decode_plugin_command_response(resp) == (True, None)
	assert plugin.calls == ['stop', 'start']


def test_command_for_unknown_plugin_reports_error_not_crash():
	backend = RemoteBackend(send=lambda m: None)  # no plugins attached

	async def scenario():
		server = WireServer(on_request=backend.handle_plugin_command)
		await server.start()
		try:
			resp = await _run_command(server, 'NoSuchPlugin', 'stop')
			return resp
		finally:
			await server.stop()

	resp = asyncio.run(scenario())
	ok, error = decode_plugin_command_response(resp)
	assert ok is False
	assert 'NoSuchPlugin' in (error or '')


def test_unknown_command_reports_error_not_crash():
	plugin = _FakePlugin()
	backend = RemoteBackend(send=lambda m: None)
	backend._plugins[_SOURCE] = plugin

	async def scenario():
		server = WireServer(on_request=backend.handle_plugin_command)
		await server.start()
		try:
			resp = await _run_command(server, _SOURCE, 'explode')
			return resp
		finally:
			await server.stop()

	resp = asyncio.run(scenario())
	ok, error = decode_plugin_command_response(resp)
	assert ok is False
	assert 'explode' in (error or '')
	assert plugin.calls == []  # nothing executed for a bad command
