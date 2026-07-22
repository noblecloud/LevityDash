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

Constructed on the GUI thread (dispatcher __init__ runs there), which pins the
marshal QObject's thread affinity correctly.
"""
import asyncio
import threading
from typing import Callable, TYPE_CHECKING

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
	owned here so the wire layer controls its affinity explicitly."""

	_invoke = Signal(object)

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
		self._frontend = RemoteFrontend(on_update=dispatcher.update)
		self._marshal = _GuiMarshal()  # created here -> GUI-thread affinity
		self._stop = threading.Event()
		self._thread = threading.Thread(target=self._run, name='WireClientThread', daemon=True)
		self._thread.start()
		log.info(f'mode=remote: connecting to backend at {url}')

	# -- client thread ------------------------------------------------------

	def _on_message(self, message: dict) -> None:
		# client thread -> GUI thread, exactly once, at the seam
		self._marshal.invoke(lambda: self._frontend.handle_message(message))

	def _run(self) -> None:
		loop = asyncio.new_event_loop()
		asyncio.set_event_loop(loop)
		try:
			loop.run_until_complete(self._connect_loop())
		finally:
			loop.close()

	async def _connect_loop(self) -> None:
		backoff = 1
		while not self._stop.is_set():
			client = WireClient(self.url, self._on_message)
			try:
				await client.connect()
				log.info(f'connected to backend at {self.url}')
				backoff = 1
				await client.wait_closed()
				log.warning('backend connection closed')
			except Exception as e:
				log.warning(f'backend connection failed ({e!r}); retrying in {backoff}s')
			finally:
				try:
					await client.close()
				except Exception:
					pass
			if self._stop.is_set():
				break
			await asyncio.sleep(backoff)
			backoff = min(backoff * 2, _RECONNECT_MAX_SECONDS)

	# -- GUI thread ---------------------------------------------------------

	def stop(self) -> None:
		self._stop.set()
