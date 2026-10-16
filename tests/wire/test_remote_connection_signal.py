"""RemoteConnection.connectionStateChanged - the Signal added for the
frontend's in-app backend-connection indicator.

Before this, RemoteConnection's connect/close/fail transitions only ever
logged (lib/wire/remote.py's _connect_loop) - nothing Qt-side could react to
them. Verified against a real WireServer over a real socket (not mocked),
matching test_wire_ts_end_to_end.py's precedent: only the plugin-side data
source is ever a stand-in in this test suite, the wire/Qt pieces are real.
"""
import asyncio
import threading
import time

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from LevityDash.lib.wire.remote import RemoteConnection
from LevityDash.lib.wire.server import WireServer
from PySide6.QtWidgets import QApplication


class _FakeDispatcher:
	def update(self, *args, **kwargs):
		pass


def _pump_until(app, pred, timeout: float = 30.0) -> bool:
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		if pred():
			return True
		app.processEvents()
		time.sleep(0.01)
	return pred()


def test_connection_state_signal_fires_on_connect_and_disconnect():
	app = QApplication.instance()
	assert app is not None, 'expected the LevityDash package import to have already constructed a QApplication'

	server = WireServer()
	server_loop = asyncio.new_event_loop()
	started = threading.Event()

	def serve():
		asyncio.set_event_loop(server_loop)
		server_loop.run_until_complete(server.start())
		started.set()
		server_loop.run_forever()

	server_thread = threading.Thread(target=serve, daemon=True)
	server_thread.start()
	assert started.wait(timeout=30), 'WireServer never started'

	states = []
	connection = RemoteConnection(_FakeDispatcher(), server.url)
	connection.connectionStateChanged.connect(states.append)

	try:
		# The wire thread starts connecting in the constructor, so 'connecting' and even 'connected' can fire
		# before this test subscribes, and a queued Signal emitted earlier never reaches a later subscriber.
		# That is what the `state` attribute is for: wait on it, then check the transitions seen afterwards.
		assert _pump_until(app, lambda: connection.state == 'connected'), f'never connected, state {connection.state!r}, saw {states}'
		order = ['connecting', 'connected', 'disconnected']
		assert states == sorted(states, key=order.index), f'states arrived out of order: {states}'

		# stop the server out from under the client - the reconnect loop
		# should notice and report disconnected
		asyncio.run_coroutine_threadsafe(server.stop(), server_loop).result(timeout=30)

		assert _pump_until(app, lambda: 'disconnected' in states), f'never saw disconnected, got {states}'
		assert states == sorted(states, key=order.index), f'states arrived out of order: {states}'
	finally:
		connection.stop()
		server_loop.call_soon_threadsafe(server_loop.stop)
		server_thread.join(timeout=30)
