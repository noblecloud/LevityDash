#!/usr/bin/env python
"""Dev-only: a long-lived process that holds a booted dashboard and renders on
demand over HTTP.

`render_dashboard.py` and `render_widget.py` each pay ~6s of Qt boot per look.
Iterating on a layout means that cost every time you want to see what you did,
which is what pushes a design session toward changing several things at once -
and then you can't tell which change did what. This keeps the dashboard warm so
a render costs milliseconds.

It is also, structurally, the prototype of the server-side-rendering backend in
docs/tasks/render-service-and-surface-frontend.md. Step 1 of that brief.

Usage:
    poetry run python src/LevityDash/devtools/render_service.py --seed DIR
    curl -s localhost:8670/items
    curl -s 'localhost:8670/render?w=1800&h=1015' -o board.png
    curl -s 'localhost:8670/render/terrarium?scale=3&pad=8' -o cell.png
    curl -s -X POST localhost:8670/reload

Endpoints:
    GET  /health            plain 200/503, for any generic uptime tool
    GET  /status            JSON: size, uptime, render count, dashboard path
    GET  /items             the addressable `name:`s, as render_widget --list
    GET  /render            full dashboard PNG  (?w= ?h= ?scale=)
    GET  /render/<name>     one named item PNG  (?scale= ?pad=)
    POST /reload            re-read the .levity without re-booting Qt

Threading: aiohttp runs on its own thread with its own event loop; the Qt main
thread runs app.exec(). Every render is marshaled onto the Qt thread through a
queued signal, because scene.render() touches the scene graph. Same two-hop
shape as RemoteBackend.handle_ts_request (lib/wire/backend.py) - deliberately,
rather than a second threading idiom.
"""
import argparse
import asyncio
import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional, Tuple

# Before ANY LevityDash import: the QApplication is constructed during the
# package import chain and the platform cannot change afterwards. See _boot.
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aiohttp import web

from LevityDash.devtools._boot import (
	DEFAULT_SIZE,
	boot,
	named_items,
	pump,
	render_png_bytes,
)

DEFAULT_PORT = 8670  # one above backend_watch's 8669


class RenderError(Exception):
	"""Something the caller asked for that isn't there - becomes a 404/400."""


class QtRenderer:
	"""Owns the warm dashboard and answers render requests on the Qt thread."""

	def __init__(self, app, dashboard, size: Tuple[int, int], settle: float):
		from PySide6.QtCore import QObject, Qt, Signal, Slot

		self._app = app
		self._dashboard = dashboard
		self._size = size
		self._settle = settle
		self._started = time.monotonic()
		self.renders = 0

		class _Invoker(QObject):
			"""Marshals a callable onto the thread it was constructed on."""

			_invoke = Signal(object)

			def __init__(self):
				super().__init__()
				self._invoke.connect(self._run, Qt.ConnectionType.QueuedConnection)

			@Slot(object)
			def _run(self, fn: Callable):
				fn()

			def invoke(self, fn: Callable):
				self._invoke.emit(fn)

		# Constructed on the Qt main thread, which pins this QObject's thread
		# affinity correctly - same reason RemoteBackend builds its _QtInvoker
		# in __init__ rather than lazily.
		self._invoker = _Invoker()

	@property
	def uptime(self) -> float:
		return time.monotonic() - self._started

	@property
	def size(self) -> Tuple[int, int]:
		return self._size

	async def call(self, fn: Callable):
		"""Run `fn()` on the Qt thread and await its result.

		Runs from the aiohttp thread. Exceptions cross the hop intact so a bad
		request becomes a response rather than a silent hang.
		"""
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

	# -- everything below runs on the Qt thread --

	def _resize(self, size: Tuple[int, int]) -> None:
		"""Resize and let the layout settle.

		A changed size changes *layout*, not just output scale, so it has to be
		a property of the request rather than fixed at boot. Only pays the
		settle when the size actually changed.
		"""
		if size == self._size:
			return
		self._app.main_window.resize(*size)
		pump(self._app, self._settle)
		self._size = size

	def renderFull(self, size: Optional[Tuple[int, int]], scale: float) -> bytes:
		if size is not None:
			self._resize(size)
		scene = self._dashboard.scene
		self.renders += 1
		return render_png_bytes(scene, scene.sceneRect(), scale=scale)

	def renderItem(self, name: str, scale: float, pad: float) -> bytes:
		items = named_items(self._dashboard.scene)
		item = items.get(name)
		if item is None:
			raise RenderError(f'no item named {name!r}. Available: {", ".join(sorted(items)) or "(none)"}')
		rect = item.sceneBoundingRect()
		if pad:
			rect = rect.adjusted(-pad, -pad, pad, pad)
		self.renders += 1
		return render_png_bytes(self._dashboard.scene, rect, scale=scale)

	def listItems(self) -> list:
		return [
			{
				'name': name,
				'type': type(item).__name__,
				'width': round(item.sceneBoundingRect().width()),
				'height': round(item.sceneBoundingRect().height()),
			}
			for name, item in sorted(named_items(self._dashboard.scene).items())
		]

	def dashboardPath(self) -> Optional[str]:
		panel = getattr(self._dashboard, 'CENTRAL_PANEL', None)
		path = getattr(panel, 'filePath', None)
		return str(path) if path is not None else None

	def reload(self) -> None:
		panel = getattr(self._dashboard, 'CENTRAL_PANEL', None)
		if panel is None:
			raise RenderError('no central panel to reload')
		panel.reload()
		pump(self._app, self._settle)


def _floatArg(request: web.Request, name: str, default: float) -> float:
	raw = request.query.get(name)
	if raw is None:
		return default
	try:
		return float(raw)
	except ValueError:
		raise web.HTTPBadRequest(text=f'{name} must be a number, got {raw!r}\n')


def _sizeArg(request: web.Request) -> Optional[Tuple[int, int]]:
	if 'w' not in request.query and 'h' not in request.query:
		return None
	try:
		width = int(request.query['w'])
		height = int(request.query['h'])
	except (KeyError, ValueError):
		raise web.HTTPBadRequest(text='w and h must both be given, as integers\n')
	return width, height


def _makeApp(renderer: QtRenderer) -> web.Application:
	app = web.Application()

	async def health(_request: web.Request) -> web.Response:
		return web.Response(text='ok\n')

	async def status(_request: web.Request) -> web.Response:
		return web.json_response({
			'status': 'ok',
			'uptime': round(renderer.uptime, 1),
			'renders': renderer.renders,
			'size': list(renderer.size),
			'dashboard': await renderer.call(renderer.dashboardPath),
		})

	async def items(_request: web.Request) -> web.Response:
		return web.json_response(await renderer.call(renderer.listItems))

	async def renderFull(request: web.Request) -> web.Response:
		size = _sizeArg(request)
		scale = _floatArg(request, 'scale', 1.0)
		png = await renderer.call(lambda: renderer.renderFull(size, scale))
		return web.Response(body=png, content_type='image/png')

	async def renderItem(request: web.Request) -> web.Response:
		name = request.match_info['name']
		scale = _floatArg(request, 'scale', 1.0)
		pad = _floatArg(request, 'pad', 0.0)
		try:
			png = await renderer.call(lambda: renderer.renderItem(name, scale, pad))
		except RenderError as e:
			raise web.HTTPNotFound(text=f'{e}\n')
		return web.Response(body=png, content_type='image/png')

	async def reload(_request: web.Request) -> web.Response:
		await renderer.call(renderer.reload)
		return web.json_response({'status': 'reloaded'})

	app.router.add_get('/health', health)
	app.router.add_get('/status', status)
	app.router.add_get('/items', items)
	app.router.add_get('/render', renderFull)
	app.router.add_get('/render/{name}', renderItem)
	app.router.add_post('/reload', reload)
	return app


def _serve(renderer: QtRenderer, host: str, port: int, ready: threading.Event) -> None:
	"""aiohttp's own thread and event loop; the Qt thread runs app.exec()."""

	async def run():
		runner = web.AppRunner(_makeApp(renderer))
		await runner.setup()
		site = web.TCPSite(runner, host, port)
		await site.start()
		print(f'render service on http://{host}:{port}  (ctrl-c to stop)', flush=True)
		ready.set()
		while True:
			await asyncio.sleep(3600)

	asyncio.new_event_loop().run_until_complete(run())


def _parseSize(text: str) -> Tuple[int, int]:
	width, _, height = text.lower().partition('x')
	return int(width), int(height)


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument('--seed', help='config dir copy to render against; omit for the real config')
	parser.add_argument('--levity', help='candidate .levity to render (requires --seed)')
	parser.add_argument('--size', default='x'.join(map(str, DEFAULT_SIZE)), help='window size driving layout')
	parser.add_argument('--settle', type=float, default=6.0, help='seconds to let layout settle after boot/resize')
	parser.add_argument('--plugins', action='store_true', help='start plugins for real values')
	parser.add_argument('--host', default=os.getenv('LEVITYDASH_RENDER_HOST', '127.0.0.1'))
	parser.add_argument('--port', type=int, default=int(os.getenv('LEVITYDASH_RENDER_PORT', DEFAULT_PORT)))
	args = parser.parse_args()

	size = _parseSize(args.size)
	try:
		app, dashboard = boot(
			seed=args.seed, levity=args.levity, size=size,
			settle=args.settle, plugins=args.plugins,
		)
	except ValueError as e:
		parser.error(str(e))

	renderer = QtRenderer(app, dashboard, size=size, settle=args.settle)

	ready = threading.Event()
	thread = threading.Thread(
		target=_serve, args=(renderer, args.host, args.port, ready),
		name='render-service-http', daemon=True,
	)
	thread.start()
	if not ready.wait(timeout=30):
		print('http server failed to start', file=sys.stderr)
		return 1

	try:
		return app.exec()
	except KeyboardInterrupt:
		return 0


if __name__ == '__main__':
	raise SystemExit(main())
