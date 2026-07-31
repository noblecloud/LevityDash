"""Routing tests for the LevityWeb service (lib/web/service.py).

Like tests/devtools/test_render_service.py, this never boots a real dashboard
or a real Qt main thread: the service's Qt-thread hops (`_call`, `_pump`) are
stubbed to run inline, and the dashboard is a stand-in owning a real (empty)
QGraphicsScene. What gets pinned is the HTTP/WS surface: static 503 before a
build exists, status, reload's 404 without a central panel, and the hello ->
layout -> heartbeat conversation over a real socket.
"""
import asyncio
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer
from PySide6.QtWidgets import QGraphicsScene

from LevityDash.lib.web.service import WebService


class FakeDashboard:
	def __init__(self):
		self.scene = QGraphicsScene()
		self.plugins = SimpleNamespace(enabled_plugins=[])
		self.main_window = SimpleNamespace(resize=lambda *_: None)
		self.CENTRAL_PANEL = None


def _make_service(tmp_path, **kwargs):
	app = SimpleNamespace(main_window=SimpleNamespace(resize=lambda *_: None))
	service = WebService(app, FakeDashboard(), static_root=tmp_path, **kwargs)

	async def inline_call(fn):
		return fn()

	service._call = inline_call
	service._pump = lambda _seconds: None
	return service


async def _client(service):
	return TestClient(TestServer(await service._make_app()))


def _run(scenario):
	return asyncio.run(scenario())


def test_index_is_503_until_frontend_built(tmp_path):
	service = _make_service(tmp_path)

	async def scenario():
		async with await _client(service) as client:
			response = await client.get('/')
			assert response.status == 503
			assert 'not built' in await response.text()

	_run(scenario)


def test_status_reports_bakes_and_clients(tmp_path):
	service = _make_service(tmp_path)

	async def scenario():
		async with await _client(service) as client:
			status = await (await client.get('/api/status')).json()
			assert status['status'] == 'ok'
			assert status['size'] == [1800, 1090]
			assert status['bakes'] == 0
			assert status['clients'] == 0

	_run(scenario)


def test_reload_without_central_panel_is_404(tmp_path):
	service = _make_service(tmp_path)

	async def scenario():
		async with await _client(service) as client:
			assert (await client.post('/api/reload')).status == 404

	_run(scenario)


def test_hello_gets_layout_then_heartbeat(tmp_path, monkeypatch):
	"""The heartbeat loop is normally started by `start()`; run it here on the
	test's own loop so the conversation is observable without the thread."""
	monkeypatch.setattr('LevityDash.lib.web.service.HEARTBEAT_SECONDS', 0.2)
	service = _make_service(tmp_path)

	async def scenario():
		async with await _client(service) as client:
			async with client.ws_connect('/ws-web') as ws:
				await ws.send_json({'type': 'hello', 'w': 900, 'h': 500, 'dpr': 2.0})
				layout = await asyncio.wait_for(ws.receive_json(), 5)
				assert layout['type'] == 'layout'
				assert layout['viewport'] == {'w': 900, 'h': 500, 'dpr': 2.0}
				assert layout['items'] == []

				await asyncio.sleep(0.05)  # let the server register the socket
				beat_task = asyncio.create_task(service._heartbeat_loop())
				heartbeat = await asyncio.wait_for(ws.receive_json(), 5)
				beat_task.cancel()
				assert heartbeat['type'] == 'heartbeat'
				assert heartbeat['seq'] >= 1

	_run(scenario)


def test_bad_hello_gets_an_error_message(tmp_path):
	service = _make_service(tmp_path)

	async def scenario():
		async with await _client(service) as client:
			async with client.ws_connect('/ws-web') as ws:
				await ws.send_json({'type': 'hello', 'w': 'nope'})
				error = await asyncio.wait_for(ws.receive_json(), 5)
				assert error['type'] == 'error'
				assert 'w' in error['error']

	_run(scenario)


def test_ts_request_to_unknown_source_is_ok_false(tmp_path):
	"""handle_ts_request marshals onto the Qt thread via a queued signal, so
	the Qt event loop must pump while the response is awaited - the same
	requirement the real service satisfies with its exec() loop."""
	service = _make_service(tmp_path)

	async def scenario():
		async with await _client(service) as client:
			async with client.ws_connect('/ws-web') as ws:
				await ws.send_json({
					'type': 'ts_request',
					'id': 'probe-1',
					'source': 'NoSuchPlugin',
					'key': 'environment.temperature.temperature',
					'minPeriod': -10800,
					'maxPeriod': 10800,
				})
				response = await asyncio.wait_for(_with_qt_pump(ws), 5)
				assert response['type'] == 'ts_response'
				assert response['id'] == 'probe-1'
				assert response['ok'] is False

	_run(scenario)


async def _with_qt_pump(ws):
	"""Awaits the next json frame while pumping Qt events (the queued-signal
	invoker needs the loop; the real service runs it in exec())."""
	from LevityDash import LevityDashboard

	app = LevityDashboard.app
	result = None
	done = asyncio.Event()

	async def pump_qt():
		while not done.is_set():
			app.processEvents()
			await asyncio.sleep(0.005)

	async def receive():
		nonlocal result
		result = await ws.receive_json()
		done.set()

	pump_task = asyncio.create_task(pump_qt())
	receive_task = asyncio.create_task(receive())
	await receive_task
	done.set()
	pump_task.cancel()
	return result
