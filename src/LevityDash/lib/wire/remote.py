"""RemoteConnection — the mode=remote frontend integration (Phase 4.2 step 4).

Owns everything between the socket and the dispatcher:

- a dedicated thread running its own asyncio loop (the same
  loop-per-thread pattern every plugin uses) with a ``WireClient`` inside a
  reconnect/backoff loop — the backend may not be up yet, may restart, etc.;
- a ``RemoteFrontend`` that turns each update message into
  ``{key: RemoteContainer}`` batches for ``dispatcher.update``;
- the **single GUI-thread hop** between them: every received message is
  marshaled onto the GUI thread *before* ``RemoteFrontend`` touches any
  container the scene graph can see. This is the roadmap's design requirement
  for this seam (it's what retires the QBasicTimer off-thread startup burst in
  the remote architecture) — not an optimization.
- ``request_timeseries`` (timeseries-over-wire milestone): the GUI-thread ->
  wire-thread direction. Called from ``RemoteContainer.prepare_for_ts_
  connection`` (containers.py), it hops onto the wire thread via
  ``call_soon_threadsafe``, sends a request through the live ``WireClient``,
  awaits the matching response, then marshals the result back through the
  same ``_GuiMarshal`` used for received 'update' messages - so a caller on
  the GUI thread never touches the socket/asyncio loop directly either way.

Constructed on the GUI thread (dispatcher __init__ runs there), which pins the
marshal QObject's thread affinity correctly.
"""
import asyncio
import threading
from typing import Callable, Optional, TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, Signal, Slot

from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.wire.client import WireClient
from LevityDash.lib.wire.frontend import RemoteFrontend

if TYPE_CHECKING:
	from LevityDash.lib.plugins.dispatcher import PluginValueDirectory

log = LevityPluginLog.getChild('Wire').getChild('Remote')

__all__ = ['RemoteConnection']

_RECONNECT_MAX_SECONDS = 30


class _GuiMarshal(QObject):
	"""Queues a callable onto the thread this object was created on (the GUI
	thread) via a queued signal - same shape as shared.py's _MainThreadCall,
	owned here so the wire layer controls its affinity explicitly.

	Also carries ``connectionStateChanged``: Qt's queued-connection
	cross-thread delivery is already proven safe by ``_invoke`` (emitted from
	the wire thread, delivered on this object's GUI-thread affinity), so a
	second Signal on the same QObject reuses that guarantee rather than
	needing its own marshal.
	"""

	_invoke = Signal(object)
	connectionStateChanged = Signal(str)  # 'connecting' | 'connected' | 'disconnected'

	def __init__(self):
		super().__init__()
		self._invoke.connect(self._run, Qt.ConnectionType.QueuedConnection)

	@Slot(object)
	def _run(self, fn: Callable):
		fn()

	def invoke(self, fn: Callable):
		self._invoke.emit(fn)


class RemoteConnection:
	def __init__(self, dispatcher: 'PluginValueDirectory', url: str):
		self.url = url
		self._frontend = RemoteFrontend(on_update=dispatcher.update, ts_request_fn=self.request_timeseries)
		self._marshal = _GuiMarshal()  # created here -> GUI-thread affinity
		self._stop = threading.Event()
		self._client: Optional[WireClient] = None
		self._loop: Optional[asyncio.AbstractEventLoop] = None
		self._thread = threading.Thread(target=self._run, name='WireClientThread', daemon=True)
		self.connectionStateChanged = self._marshal.connectionStateChanged
		# Plain-attribute "last known state", not just the fire-and-forget
		# Signal: the wire thread starts connecting immediately, so a late
		# observer (e.g. a UI indicator built well after this constructor
		# returns) needs to read where things already stand rather than only
		# ever seeing whatever transition happens to fire *after* it
		# subscribes. Written from the wire thread, read from the GUI thread -
		# a single str attribute swap is atomic enough under the GIL without
		# a lock.
		self.state = 'connecting'
		self._thread.start()
		log.info(f'mode=remote: connecting to backend at {url}')

	# -- client thread ------------------------------------------------------

	def _on_message(self, message: dict) -> None:
		# client thread -> GUI thread, exactly once, at the seam
		self._marshal.invoke(lambda: self._frontend.handle_message(message))

	def _run(self) -> None:
		loop = asyncio.new_event_loop()
		self._loop = loop
		asyncio.set_event_loop(loop)
		try:
			loop.run_until_complete(self._connect_loop())
		finally:
			loop.close()

	def _set_state(self, state: str) -> None:
		self.state = state
		self._marshal.connectionStateChanged.emit(state)

	async def _connect_loop(self) -> None:
		backoff = 1
		while not self._stop.is_set():
			self._set_state('connecting')
			client = WireClient(self.url, self._on_message)
			self._client = client
			try:
				await client.connect()
				log.info(f'connected to backend at {self.url}')
				self._set_state('connected')
				backoff = 1
				await client.wait_closed()
				log.warning('backend connection closed')
				self._set_state('disconnected')
			except Exception as e:
				log.warning(f'backend connection failed ({e!r}); retrying in {backoff}s')
				self._set_state('disconnected')
			finally:
				self._client = None
				try:
					await client.close()
				except Exception:
					pass
			if self._stop.is_set():
				break
			await asyncio.sleep(backoff)
			backoff = min(backoff * 2, _RECONNECT_MAX_SECONDS)

	# -- GUI thread ---------------------------------------------------------

	def request_timeseries(self, message: dict, on_response: Callable[[Optional[dict]], None]) -> None:
		"""Issue a ts_request on the wire thread; ``on_response`` fires on the
		GUI thread exactly once with the ts_response dict, or ``None`` on
		failure/no connection - the single GUI-thread hop this seam requires
		(same ``_marshal`` already used for ordinary 'update' messages)."""
		if self._loop is None:
			# connection thread hasn't reached _run yet (started() not called
			# out) - vanishingly unlikely given __init__ starts the thread
			# immediately, but fail soft rather than crash the caller.
			on_response(None)
			return

		def submit() -> None:
			client = self._client
			if client is None:
				self._marshal.invoke(lambda: on_response(None))
				return

			async def _do() -> None:
				try:
					response = await client.request(message)
				except Exception as e:
					log.warning(f'timeseries request {message.get("id")} failed: {e!r}')
					response = None
				self._marshal.invoke(lambda: on_response(response))

			asyncio.ensure_future(_do())

		self._loop.call_soon_threadsafe(submit)

	def stop(self) -> None:
		self._stop.set()
