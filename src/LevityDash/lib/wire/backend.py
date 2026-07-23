"""RemoteBackend — the send-side brain of the standalone backend (Phase 4.2 step 4).

The mirror of ``RemoteFrontend``: attaches to each plugin's real ``Publisher``
(exactly like ``LoopbackBridge.attach``), and on publish encodes every changed
container (``encode_container``), wraps the batch in an update envelope
(``encode_update_message``), and hands the message to a sender callback — in the
real backend process, ``lambda msg: run_coroutine_threadsafe(server.broadcast(msg),
server_loop)``.

Decoupled from the socket via that callback for the same reason RemoteFrontend
is: the encode logic stays testable without aiohttp or a running event loop.

Threading: publisher signals are delivered on the thread that owns the
Publisher (the queued hop in ``Publisher._emit``) — the backend's main/Qt
thread. Encoding happens there, synchronously, reading live containers exactly
like LoopbackBridge does today; only the finished JSON-safe message crosses to
the server's asyncio thread.

Also the receive side of the timeseries-over-wire milestone:
``handle_ts_request`` answers a 'ts_request' (arrives on WireServer's asyncio
thread, see server.py's ``on_request`` hook). Resolving ``Plugin``/
``Container`` must happen on the Qt main thread, and the potentially-slow
``MeasurementTimeSeries.update()`` (always a full rebuild) must not block
either the Qt thread or the asyncio thread — so this mirrors
``Container.prepare_for_ts_connection``'s own thread-pool pattern
(observation.py) exactly, adding one hop each direction:
asyncio thread -> Qt thread (via ``_QtInvoker``, same queued-signal idiom as
remote.py's ``_GuiMarshal``) to do the lookup and submit the thread-pool
worker, then worker thread -> asyncio thread (via
``loop.call_soon_threadsafe``, safe to call from any foreign thread) once the
rebuild finishes.
"""
import asyncio
from datetime import timedelta
from typing import Awaitable, Callable, Dict, TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, Signal, Slot

from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.utils.data import KeyData
from LevityDash.lib.utils.shared import now
from LevityDash.lib.wire.messages import encode_container, encode_ts_response, encode_update_message

if TYPE_CHECKING:
	from LevityDash.lib.plugins.plugin import Plugin

log = LevityPluginLog.getChild('Wire').getChild('Backend')

__all__ = ['RemoteBackend']

_DEFAULT_MIN_PERIOD = timedelta(hours=-3)
_DEFAULT_MAX_PERIOD = timedelta(hours=3)


class _QtInvoker(QObject):
	"""Marshals a callable onto the thread this object was created on (the
	backend's Qt main thread) via a queued signal - same shape as remote.py's
	_GuiMarshal, kept local to this module rather than shared since it's ~10
	lines of Qt boilerplate and each wire module already owns its own small
	stand-ins (see containers.py's ContainerFlags)."""

	_invoke = Signal(object)

	def __init__(self):
		super().__init__()
		self._invoke.connect(self._run, Qt.ConnectionType.QueuedConnection)

	@Slot(object)
	def _run(self, fn: Callable):
		fn()

	def invoke(self, fn: Callable):
		self._invoke.emit(fn)


class RemoteBackend:
	def __init__(self, send: Callable[[dict], None]):
		# send receives a finished, JSON-safe update message. It must be
		# thread-agnostic/cheap (e.g. run_coroutine_threadsafe into the server
		# loop) - it is called from the thread publisher signals land on.
		self._send = send
		self._plugins: Dict[str, 'Plugin'] = {}
		# Constructed here rather than lazily: RemoteBackend is built on the Qt
		# main thread (lib/backend.py:main(), before app.exec()), which pins
		# this QObject's thread affinity correctly, same as remote.py's
		# _GuiMarshal.
		self._qt_invoker = _QtInvoker()

	def attach(self, plugin: 'Plugin') -> None:
		self._plugins[plugin.name] = plugin
		plugin.publisher.connectSlot(self._on_published)

	@Slot(KeyData)
	def _on_published(self, data: KeyData) -> None:
		plugin = data.sender
		keys = data.keys
		if isinstance(keys, dict):
			keys = set().union(*keys.values())

		updates: Dict[str, dict] = {}
		for key in keys:
			try:
				encoded = encode_container(plugin[key])
			except Exception as e:
				# same per-key resilience as LoopbackBridge: one bad value must
				# not sink the rest of the batch
				log.warning(f'{plugin.name}:{key}: failed to encode for wire push, skipping this key: {e!r}')
				continue
			if encoded is not None:
				updates[str(key)] = encoded

		if not updates:
			return

		message = encode_update_message(
			name=plugin.name,
			defaultFor=set(plugin.config.defaultFor),
			enabled=plugin.enabled,
			running=plugin.running,
			updates=updates,
		)
		try:
			self._send(message)
		except Exception as e:
			log.warning(f'{plugin.name}: failed to hand off wire message to sender: {e!r}')

	async def handle_ts_request(self, message: dict) -> dict:
		"""The coroutine WireServer awaits per 'ts_request' (server.py's
		on_request hook) - runs on the server's asyncio thread. Marshals the
		actual lookup onto the Qt main thread and awaits the result without
		blocking this loop; see the module docstring for the full two-hop
		shape."""
		loop = asyncio.get_running_loop()
		fut = loop.create_future()
		self._qt_invoker.invoke(lambda: self._resolve_ts_request(message, loop, fut))
		return await fut

	def _resolve_ts_request(self, message: dict, loop: asyncio.AbstractEventLoop, fut: asyncio.Future) -> None:
		"""Runs on the Qt main thread (via _qt_invoker). Resolves plugin/
		container, then hands the potentially-slow timeseries rebuild to the
		plugin's own thread pool - mirroring Container.prepare_for_ts_connection
		(observation.py) exactly, not a reinvented threading idiom."""
		request_id = message['id']
		source = message['source']
		key_str = message['key']

		def _set_result(response: dict) -> None:
			if not fut.done():
				fut.set_result(response)

		def finish(response: dict) -> None:
			loop.call_soon_threadsafe(_set_result, response)

		plugin = self._plugins.get(source)
		if plugin is None:
			finish(encode_ts_response(request_id=request_id, source=source, key=key_str, ok=False, error=f'unknown source: {source!r}'))
			return

		key = CategoryItem(key_str)
		try:
			container = plugin[key]
			timeseries = container.timeseries
		except Exception as e:
			finish(encode_ts_response(request_id=request_id, source=source, key=key_str, ok=False, error=repr(e)))
			return

		minPeriod = timedelta(seconds=message['minPeriod']) if message.get('minPeriod') is not None else _DEFAULT_MIN_PERIOD
		maxPeriod = timedelta(seconds=message['maxPeriod']) if message.get('maxPeriod') is not None else _DEFAULT_MAX_PERIOD
		start, end = now() + minPeriod, now() + maxPeriod

		def on_finish() -> None:
			# Off the Qt main thread - a thread-pool worker thread, per
			# direct=True below (confirmed against Worker.run(), shared.py).
			try:
				items = timeseries[start:end]
				response = encode_ts_response(request_id=request_id, source=source, key=key_str, ok=True, items=items)
			except Exception as e:
				response = encode_ts_response(request_id=request_id, source=source, key=key_str, ok=False, error=repr(e))
			finish(response)

		try:
			plugin.thread_pool.run_threaded_process(timeseries.update, on_finish=on_finish, direct=True)
		except Exception as e:
			finish(encode_ts_response(request_id=request_id, source=source, key=key_str, ok=False, error=repr(e)))
