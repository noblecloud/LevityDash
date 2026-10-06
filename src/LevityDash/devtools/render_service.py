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
    poetry run python src/LevityDash/devtools/render_service.py --scenario hot-clear-day   # fixed values
    curl -s localhost:8670/items
    curl -s 'localhost:8670/render?w=1800&h=1015' -o board.png
    curl -s 'localhost:8670/render/terrarium?scale=3&pad=8' -o cell.png
    curl -s -X POST localhost:8670/reload

Endpoints:
    GET  /health            plain 200/503, for any generic uptime tool
    GET  /status            JSON: size, uptime, render count, dashboard path
    GET  /items             the addressable `name:`s, as render_widget --list
    GET  /tree              the full child structure with indices (?depth=),
                            since /items only sees things carrying a `name:`
    GET  /render/at/<path>  one panel by structural position (?scale= ?pad=).
                            Segments are an index, a `name:`, or a bound key,
                            and both `0/1/main` and `[0][1][main]` parse.
    GET  /render            full dashboard PNG  (?w= ?h= ?scale= ?dpi=)
                            w/h take the same vocabulary as a .levity: pixels
                            (1800, 1800px), relative (80%, of the current size),
                            or physical (12.72in, 320mm) - physical needs ?dpi=,
                            default 96, since a headless process has no screen.
    GET  /render/<name>     one named item PNG  (?scale= ?pad=)
    POST /reload            re-read the current .levity without re-booting Qt
    POST /load              {"path": "..."} switch to another .levity; bare
                            names resolve against the saves directory
    POST /preview           body is a .levity document -> PNG (?scale=). Write a
                            layout, see it, without saving over anything.
                            ⚠️ EXPERIMENTAL - renders real content but does not
                            reliably finish settling: a two-cell probe came back
                            with one value and no titles. Raise --settle if it
                            looks incomplete, and prefer /load + /render when the
                            layout already exists on disk.

Iterating on a layout:

    curl -s --data-binary @candidate.levity localhost:8670/preview -o out.png
    curl -s -X POST localhost:8670/load -d '{"path":"OpenMeteo.levity"}'
    curl -s  localhost:8670/tree?depth=3
    curl -sg 'localhost:8670/render/at/[0][0]?pad=4' -o cell.png

⚠️ `curl` needs `-g` for the bracket form - `[0]` is curl's own glob syntax and
it fails before the request is even made. The slash form needs no flag and
produces byte-identical output.

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


# Same ordering rule as QT_QPA_PLATFORM above: --seed must reach the
# environment before the first LevityDash import. Imported from this directory
# rather than as LevityDash.devtools._seed precisely so it does not pull in the
# package it is trying to configure - see _seed.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _seed import seedEnvironment

seedEnvironment()

from aiohttp import web

from LevityDash.devtools._boot import (
	DEFAULT_SIZE,
	boot,
	named_items,
	pump,
	render_png_bytes,
	resizeScene,
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

	@property
	def settle(self) -> float:
		return self._settle

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
		resizeScene(self._app, size)
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

	@staticmethod
	def _children(item) -> list:
		kids = getattr(item, 'childPanels', None)
		if kids is None:
			kids = [c for c in item.childItems() if hasattr(c, 'sceneBoundingRect')]
		return list(kids)

	@staticmethod
	def _describe(item) -> dict:
		rect = item.sceneBoundingRect()
		entry = {
			'type': type(item).__name__,
			'rect': [round(rect.x()), round(rect.y()), round(rect.width()), round(rect.height())],
		}
		name = getattr(item, 'stateName', None)
		if isinstance(name, str) and name:
			entry['name'] = name
		key = getattr(item, 'key', None)
		if key is not None and str(key) not in ('', 'None'):
			entry['key'] = str(key)
		return entry

	def tree(self, depth: int = 4) -> dict:
		"""The addressable structure, with the indices `/render/at/...` expects.

		`/items` only lists items carrying a `name:`, which leaves every unnamed
		panel unaddressable. This walks the real child order instead, so any
		panel can be pointed at positionally.
		"""
		def walk(item, level):
			entry = self._describe(item)
			if level < depth:
				children = [walk(c, level + 1) for c in self._children(item)]
				if children:
					entry['items'] = children
			return entry

		return walk(self._panel(), 0)

	def itemAt(self, segments: List[str]):
		"""Resolve a structural path to one panel.

		Each segment is an index into the child order, or a `name:`, or a bound
		key - so `0/1/environment.temperature.temperature` and `[0][1]` both work.
		"""
		item = self._panel()
		walked: List[str] = []
		for segment in segments:
			children = self._children(item)
			walked.append(segment)
			target = None
			if segment.lstrip('-').isdigit():
				index = int(segment)
				if -len(children) <= index < len(children):
					target = children[index]
				else:
					raise RenderError(
						f'index {segment} out of range at {"/".join(walked[:-1]) or "<root>"}: '
						f'{len(children)} child item(s)'
					)
			else:
				for child in children:
					if getattr(child, 'stateName', None) == segment or str(getattr(child, 'key', '')) == segment:
						target = child
						break
			if target is None:
				options = ', '.join(
					f'{i}:{self._describe(c).get("name") or self._describe(c).get("key") or self._describe(c)["type"]}'
					for i, c in enumerate(children)
				)
				raise RenderError(f'no child {segment!r} at {"/".join(walked[:-1]) or "<root>"}. Options: {options or "(none)"}')
			item = target
		return item

	def renderAt(self, segments: List[str], scale: float, pad: float) -> bytes:
		item = self.itemAt(segments)
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

	def _panel(self):
		panel = getattr(self._dashboard, 'CENTRAL_PANEL', None)
		if panel is None:
			raise RenderError('no central panel to load into')
		return panel

	def _dashboardsDir(self) -> Path:
		"""The directory the *currently loaded* dashboard came from.

		Derived from `CentralPanel.filePath` rather than `userConfig.userPath`,
		because under `--seed` those differ: userPath resolves to the real
		config directory even when the service is deliberately running against a
		throwaway copy. Getting this wrong once wrote a stray `_preview.levity`
		into the author's actual saves folder.

		`filePath` stringifies to a bare name, so go through EasyPath's `.path`;
		userPath is the fallback when nothing is loaded yet.
		"""
		panel = getattr(self._dashboard, 'CENTRAL_PANEL', None)
		current = getattr(panel, 'filePath', None)
		resolved = getattr(current, 'path', None)
		if resolved is not None:
			return Path(resolved).parent

		from LevityDash.lib.config import userConfig

		# userPath is an EasyPath, which is not os.PathLike - Path() rejects it.
		base = userConfig.userPath
		return Path(getattr(base, 'path', base)).joinpath('saves', 'dashboards')

	def loadFile(self, path: str) -> str:
		"""Load a different `.levity` without restarting Qt.

		A *changed* path makes `CentralPanel._load` call `clear()` first, so this
		is a clean rebuild rather than a reconciliation - which is what you want
		when switching between candidate layouts. Bare names resolve against the
		saves directory, so `{"path": "OpenMeteo.levity"}` works.
		"""
		target = Path(path).expanduser()
		if not target.is_absolute():
			target = self._dashboardsDir() / target
		if not target.exists():
			raise RenderError(f'no such dashboard: {target}')
		self._panel()._load(target)
		pump(self._app, self._settle)
		return str(target)

	def previewLoad(self, source: str) -> str:
		"""Write and load ad-hoc `.levity` YAML. Does NOT render - see below.

		Written as `_preview.levity` in the loaded dashboard's directory so
		anything resolved relative to it still resolves. Overwritten every call,
		and never written over a real dashboard.

		Rendering is a *separate* marshaled call on purpose. Loading queues
		deferred layout work (statekit action pools, singleShot callbacks) that
		does not drain inside the same Qt-thread invocation, however long this
		pumps - rendering here returned a uniformly black image while an
		immediately following /render of the very same state was correct.
		"""
		target = self._dashboardsDir() / '_preview.levity'
		target.parent.mkdir(parents=True, exist_ok=True)
		target.write_text(source, encoding='utf-8')
		self._panel()._load(target)
		pump(self._app, self._settle)
		return str(target)


def _floatArg(request: web.Request, name: str, default: float) -> float:
	raw = request.query.get(name)
	if raw is None:
		return default
	try:
		return float(raw)
	except ValueError:
		raise web.HTTPBadRequest(text=f'{name} must be a number, got {raw!r}\n')


DEFAULT_DPI = 96.0


def _pathSegments(raw: str) -> List[str]:
	"""Split a structural path into segments.

	Accepts both `0/1/name` and the bracket form `[0][1][name]`, since the
	latter reads more naturally when talking about a position in a dashboard.
	"""
	normalized = raw.replace('[', '/').replace(']', '/')
	return [segment for segment in normalized.split('/') if segment]


def _resolveDimension(text: str, reference: int, dpi: float, horizontal: bool) -> int:
	"""One `w`/`h` value, in the same vocabulary a `.levity` uses.

	Accepts bare pixels (`1800`, `1800px`), relative (`80%`, of the service's
	current size) and physical (`12.72in`, `320mm`, `32cm`) - by going through
	the app's own `parseSize` rather than a second parser that could drift from
	it. Physical units need a DPI, which a headless process has no screen to ask,
	so it is a request parameter defaulting to 96.
	"""
	from LevityDash.lib.ui.Geometry import (
		AbsoluteFloat, DimensionType, Length, parseSize, RelativeFloat,
	)

	parsed = parseSize(
		text, None, dimension=DimensionType.width if horizontal else DimensionType.height
	)
	match parsed:
		case AbsoluteFloat() as value:
			resolved = float(value)
		case RelativeFloat() as value:
			resolved = float(value) * reference
		case Length() as value:
			resolved = float(value.inch) * dpi
		case None:
			raise web.HTTPBadRequest(text=f'could not parse size {text!r}\n')
		case _:
			resolved = float(parsed)
	if resolved <= 0:
		raise web.HTTPBadRequest(text=f'size {text!r} resolved to {resolved:g}, which is not positive\n')
	return round(resolved)


def _sizeArg(request: web.Request, reference: Tuple[int, int]) -> Optional[Tuple[int, int]]:
	if 'w' not in request.query and 'h' not in request.query:
		return None
	if 'w' not in request.query or 'h' not in request.query:
		raise web.HTTPBadRequest(text='w and h must both be given\n')
	dpi = _floatArg(request, 'dpi', DEFAULT_DPI)
	return (
		_resolveDimension(request.query['w'], reference[0], dpi, horizontal=True),
		_resolveDimension(request.query['h'], reference[1], dpi, horizontal=False),
	)


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
		size = _sizeArg(request, renderer.size)
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

	async def tree(request: web.Request) -> web.Response:
		depth = int(_floatArg(request, 'depth', 4))
		return web.json_response(await renderer.call(lambda: renderer.tree(depth)))

	async def renderAt(request: web.Request) -> web.Response:
		segments = _pathSegments(request.match_info['path'])
		if not segments:
			raise web.HTTPBadRequest(text='render/at needs a path, e.g. /render/at/0/1\n')
		scale = _floatArg(request, 'scale', 1.0)
		pad = _floatArg(request, 'pad', 0.0)
		try:
			png = await renderer.call(lambda: renderer.renderAt(segments, scale, pad))
		except RenderError as e:
			raise web.HTTPNotFound(text=f'{e}\n')
		return web.Response(body=png, content_type='image/png')

	async def reload(_request: web.Request) -> web.Response:
		await renderer.call(renderer.reload)
		return web.json_response({'status': 'reloaded'})

	async def load(request: web.Request) -> web.Response:
		body = await request.json()
		path = body.get('path')
		if not path:
			raise web.HTTPBadRequest(text='load needs a "path"\n')
		try:
			loaded = await renderer.call(lambda: renderer.loadFile(path))
		except RenderError as e:
			raise web.HTTPNotFound(text=f'{e}\n')
		return web.json_response({'status': 'loaded', 'path': loaded})

	async def preview(request: web.Request) -> web.Response:
		source = await request.text()
		if not source.strip():
			raise web.HTTPBadRequest(text='preview needs a .levity document as the request body\n')
		scale = _floatArg(request, 'scale', 1.0)
		# Load and render are separate marshaled calls with a real await between
		# them. Both parts matter: pumping inside the load call is not enough
		# (it returns a black frame), and neither is queuing the render straight
		# after it. What works is yielding here so the Qt thread gets an
		# uninterrupted stretch of its own event loop - which is exactly why a
		# manually-issued /render seconds later was always correct.
		await renderer.call(lambda: renderer.previewLoad(source))
		await asyncio.sleep(renderer.settle)
		png = await renderer.call(lambda: renderer.renderFull(None, scale))
		return web.Response(body=png, content_type='image/png')

	app.router.add_get('/health', health)
	app.router.add_get('/status', status)
	app.router.add_get('/items', items)
	app.router.add_get('/render', renderFull)
	app.router.add_get('/tree', tree)
	# Registered before /render/{name} so 'at' is not swallowed as an item name.
	app.router.add_get('/render/at/{path:.*}', renderAt)
	app.router.add_get('/render/{name}', renderItem)
	app.router.add_post('/reload', reload)
	app.router.add_post('/load', load)
	app.router.add_post('/preview', preview)
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
	parser.add_argument('--scenario', help='fixed values for every key: a docs/design-references/scenarios name or a YAML path (turns on the Fixture plugin; seeds from devtools/design-seed unless --seed)')
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
