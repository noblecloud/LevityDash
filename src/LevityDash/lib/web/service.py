"""LevityWeb service - a headless Qt frontend exposing the live dashboard to
browser clients over WebSocket.

One process does everything a Qt frontend does (boot the dashboard, start the
plugins, run the scene) but renders nothing: instead it flattens the scene into
JSON-safe layout items (see layout.py) and streams them to browsers, which draw
whatever they want. The layout authority - and every display string - still
comes from Qt; the browser is a pure renderer.

Threading is the render service's shape, deliberately:

- Qt runs the main thread (`app.exec()`): plugins publish into the scene, the
  scene's own dirty signal (`QGraphicsScene.changed`) is debounced into a
  snapshot/diff, and finished JSON messages cross to the aiohttp thread via
  `run_coroutine_threadsafe`.
- aiohttp runs on its own thread/loop: static files, the `/ws-web` socket, and
  a 5s heartbeat. Inbound work (a client's `hello` wanting a fresh bake) is
  marshaled onto the Qt thread via the same queued-signal invoker the render
  service uses, and awaited.
- Timeseries requests reuse `RemoteBackend.handle_ts_request` wholesale (the
  two-hop Qt-thread/thread-pool shape it already implements) - no second
  threading idiom.

Web protocol: lib/web/messages.py. Wire protocol reuse: encode_container
payloads, the ts_request/ts_response shapes, and RemoteBackend itself.
"""
import argparse
import asyncio
import logging
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Set, Tuple

import aiohttp
from aiohttp import WSMsgType, web

from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.web.layout import diff, snapshot
from LevityDash.lib.web.messages import (
	encode_heartbeat,
	encode_layout,
	encode_update,
	parse_hello,
)

log = LevityPluginLog.getChild('Web')

DEFAULT_PORT = 8671
DEFAULT_SIZE = (1800, 1090)
SETTLE_SECONDS = 1.5
DEBOUNCE_MS = 250
HEARTBEAT_SECONDS = 5.0


class WebService:
	"""Owns the warm dashboard (Qt thread) and the browser socket (aiohttp
	thread). Construct on the Qt main thread."""

	def __init__(
		self,
		app,
		dashboard,
		host: str = '127.0.0.1',
		port: int = DEFAULT_PORT,
		settle: float = SETTLE_SECONDS,
		static_root: Optional[Path] = None,
	):
		from PySide6.QtCore import QObject, Qt, Signal, Slot

		self._app = app
		self._dashboard = dashboard
		self._host = host
		self._port = port
		self._settle = settle
		self._static_root = Path(static_root) if static_root else None
		self._started = time.monotonic()
		self._seq = 0
		self._bakes = 0

		class Invoker(QObject):
			"""Marshals a callable onto the thread this was constructed on (the
			Qt main thread) via a queued signal - the render service's idiom."""

			_sig = Signal(object)

			def __init__(self):
				super().__init__()
				self._sig.connect(self._run, Qt.ConnectionType.QueuedConnection)

			@Slot(object)
			def _run(self, fn: Callable):
				fn()

			def invoke(self, fn: Callable):
				self._sig.emit(fn)

		# Constructed here so its thread affinity is the Qt main thread (the
		# same pinning rule as RemoteBackend._qt_invoker).
		self._invoker = Invoker()

		# Timeseries resolution reuses RemoteBackend's two-hop handler. Its
		# send callback is a no-op: this service does not relay plugin pushes -
		# the scene's own dirty signal is the delta detector here.
		from LevityDash.lib.wire.backend import RemoteBackend

		self._backend = RemoteBackend(send=lambda _msg: None)
		plugins = getattr(dashboard, 'plugins', None) or getattr(app, 'plugins', None)
		for plugin in getattr(plugins, 'enabled_plugins', ()) or ():
			self._backend._plugins[plugin.name] = plugin

		# State shared between the two threads. The Qt thread is the only
		# writer; the aiohttp thread reads through the asyncio loop's mailbox.
		self._outbox: queue.Queue = queue.Queue()
		self._loop: Optional[asyncio.AbstractEventLoop] = None
		self._clients: Set[web.WebSocketResponse] = set()
		self._latest_layout: Optional[dict] = None
		self._latest_update: Optional[dict] = None
		self._snapshot: Optional[list] = None
		self._size: Tuple[int, int] = DEFAULT_SIZE
		self._ready = threading.Event()
		self._stop: Optional[asyncio.Event] = None
		self._runners: set = set()

	# -- Qt-thread half -----------------------------------------------------

	@property
	def port(self) -> int:
		"""The bound port (resolved once start() is live - differs from the
		requested port when 0 was passed)."""
		return self._port

	def _resize(self, size: Tuple[int, int]) -> None:
		"""Resize the window and let layout settle. A changed size changes
		layout, not just output scale - same rule as the render service."""
		if size == self._size:
			return
		self._app.main_window.resize(*size)
		self._pump(self._settle)
		self._size = size

	def _pump(self, seconds: float) -> None:
		end = time.monotonic() + seconds
		while time.monotonic() < end:
			self._app.processEvents()
			time.sleep(0.005)

	def _arm_debounce(self) -> None:
		"""Scene changed -> debounce a re-snapshot onto the Qt loop."""
		from PySide6.QtCore import QTimer

		if getattr(self, '_debounce', None) is None:
			self._debounce = QTimer()
			self._debounce.setSingleShot(True)
			self._debounce.setInterval(DEBOUNCE_MS)
			self._debounce.timeout.connect(self._on_debounce)
		if not self._debounce.isActive():
			self._debounce.start()

	def _on_debounce(self) -> None:
		scene = self._dashboard.scene
		items = snapshot(scene)
		changed = diff(self._snapshot or [], items)
		self._snapshot = items
		if not changed:
			return
		message = encode_update(items=changed)
		self._latest_update = message
		self._send(message)

	def _bake(self, viewport: dict) -> dict:
		"""Resize to the client's viewport (if new), settle, snapshot, and
		return the 'layout' message. Runs on the Qt thread."""
		size = (int(viewport['w']), int(viewport['h']))
		self._resize(size)
		self._snapshot = snapshot(self._dashboard.scene)
		message = encode_layout(viewport=viewport, items=self._snapshot)
		self._latest_layout = message
		self._latest_update = None
		self._bakes += 1
		return message

	def _send(self, message: dict) -> None:
		"""Hand a finished message to the aiohttp thread (called from Qt)."""
		if self._loop is None:
			self._outbox.put(message)
			return
		loop = self._loop
		asyncio.run_coroutine_threadsafe(self._broadcast(message), loop)

	def _watch_scene(self) -> None:
		"""Start the scene's dirty signal as the delta detector (Qt thread)."""
		self._dashboard.scene.changed.connect(lambda *_a, **_k: self._arm_debounce())
		self._arm_debounce()

	# -- aiohttp-thread half ------------------------------------------------

	async def _broadcast(self, message: dict) -> None:
		for ws in list(self._clients):
			try:
				await ws.send_json(message)
			except Exception:
				self._clients.discard(ws)

	async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
		ws = web.WebSocketResponse(heartbeat=30.0)
		await ws.prepare(request)
		self._clients.add(ws)
		log.info(f'web client connected ({len(self._clients)} total)')
		try:
			async for raw in ws:
				if raw.type != WSMsgType.TEXT:
					continue
				message = raw.json()
				kind = message.get('type')
				if kind == 'hello':
					try:
						viewport = parse_hello(message)
					except Exception as e:
						await ws.send_json({'v': 1, 'type': 'error', 'error': str(e)})
						continue
					layout_message = await self._call(lambda: self._bake(viewport))
					self._latest_layout = layout_message
					await ws.send_json(layout_message)
					if self._latest_update is not None:
						await ws.send_json(self._latest_update)
				elif kind == 'ts_request':
					response = await self._backend.handle_ts_request(message)
					await ws.send_json(response)
		except Exception:
			log.exception('web socket handler failed')
		finally:
			self._clients.discard(ws)
			log.info(f'web client disconnected ({len(self._clients)} remaining)')
		return ws

	async def _call(self, fn: Callable):
		"""Run ``fn()`` on the Qt thread and await its result (render service
		idiom - exceptions cross intact)."""
		loop = asyncio.get_running_loop()
		fut = loop.create_future()

		def finish(setter, value):
			if not fut.done():
				setter(value)

		def run():
			try:
				result = fn()
			except Exception as e:  # noqa: BLE001 - reported to the caller verbatim
				loop.call_soon_threadsafe(finish, fut.set_exception, e)
			else:
				loop.call_soon_threadsafe(finish, fut.set_result, result)

		self._invoker.invoke(run)
		return await fut

	async def _heartbeat_loop(self) -> None:
		while True:
			await asyncio.sleep(HEARTBEAT_SECONDS)
			self._seq += 1
			await self._broadcast(encode_heartbeat(seq=self._seq, uptime=time.monotonic() - self._started))

	async def _drain_outbox(self) -> None:
		"""Deliver anything the Qt thread queued before the loop existed."""
		while True:
			try:
				message = self._outbox.get_nowait()
			except queue.Empty:
				return
			await self._broadcast(message)

	async def _make_app(self) -> web.Application:
		app = web.Application()
		app.router.add_get('/ws-web', self._handle_ws)
		app.router.add_get('/api/status', self._status)
		app.router.add_post('/api/reload', self._reload)

		static_root = self._static_root or (Path(__file__).resolve().parents[4] / 'web' / 'dist')
		if (static_root / 'index.html').is_file():
			app.router.add_get('/', self._index)
			assets = static_root / 'assets'
			if assets.is_dir():
				app.router.add_static('/assets/', assets, append_version=False)
			fonts = static_root / 'fonts'
			if fonts.is_dir():
				app.router.add_static('/fonts/', fonts, append_version=False)
		else:
			async def no_frontend(_request: web.Request) -> web.Response:
				return web.Response(
					text='LevityWeb frontend not built yet - run `npm run build` in web/\n',
					status=503,
					content_type='text/plain',
				)

			app.router.add_get('/', no_frontend)
		return app

	async def _index(self, _request: web.Request) -> web.Response:
		return web.FileResponse(self._static_root or (Path(__file__).resolve().parents[4] / 'web' / 'dist') / 'index.html')

	async def _status(self, _request: web.Request) -> web.Response:
		return web.json_response({
			'status': 'ok',
			'uptime': round(time.monotonic() - self._started, 1),
			'bakes': self._bakes,
			'clients': len(self._clients),
			'size': list(self._size),
			'dashboard': str(getattr(getattr(self._dashboard, 'CENTRAL_PANEL', None), 'filePath', '') or ''),
		})

	async def _reload(self, _request: web.Request) -> web.Response:
		panel = getattr(self._dashboard, 'CENTRAL_PANEL', None)
		if panel is None:
			raise web.HTTPNotFound(text='no central panel to reload\n')
		await self._call(lambda: (panel.reload(), self._pump(self._settle)))
		return web.json_response({'status': 'reloaded'})

	# -- lifecycle -----------------------------------------------------------

	def start(self) -> None:
		"""Start the aiohttp thread. Returns once the socket is live (or the
		thread fails). The Qt thread must be inside exec() before/after."""

		def serve() -> None:
			async def run() -> None:
				app = await self._make_app()
				runner = web.AppRunner(app)
				await runner.setup()
				site = web.TCPSite(runner, self._host, self._port)
				await site.start()
				self._loop = asyncio.get_running_loop()
				self._runners.add(runner)
				self._port = site._server.sockets[0].getsockname()[1] if self._port == 0 else self._port
				await self._drain_outbox()
				log.info(f'LevityWeb on http://{self._host}:{self._port}  (ws at /ws-web)')
				print(f'LevityWeb on http://{self._host}:{self._port}  (ws at /ws-web)', flush=True)
				self._ready.set()
				self._stop = asyncio.Event()
				asyncio.create_task(self._heartbeat_loop(), name='levity-web-heartbeat')
				while not self._stop.is_set():
					await self._stop.wait()

			asyncio.new_event_loop().run_until_complete(run())

		thread = threading.Thread(target=serve, name='levity-web-http', daemon=True)
		thread.start()
		if not self._ready.wait(timeout=30):
			raise RuntimeError('LevityWeb http server failed to start')

	def stop(self) -> None:
		"""Shut the aiohttp thread down cleanly, called from the Qt thread
		after exec() returns: cancel the heartbeat task, close the site so
		browsers see a clean disconnect, then release the thread."""
		loop = self._loop
		if loop is None:
			return
		self._loop = None
		try:
			asyncio.run_coroutine_threadsafe(self._shutdown_site(), loop).result(timeout=5)
		except Exception:
			log.exception('LevityWeb http shutdown failed')

	async def _shutdown_site(self) -> None:
		for task in asyncio.all_tasks():
			if task is not asyncio.current_task() and task.get_name() == 'levity-web-heartbeat':
				task.cancel()
		for runner in list(self._runners):
			await runner.cleanup()
		self._runners.clear()
		if self._stop is not None:
			self._stop.set()
