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
"""
from typing import Callable, Dict, TYPE_CHECKING

from PySide6.QtCore import Slot

from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.utils.data import KeyData
from LevityDash.lib.wire.messages import encode_container, encode_update_message

if TYPE_CHECKING:
	from LevityDash.lib.plugins.plugin import Plugin

log = LevityPluginLog.getChild('Wire').getChild('Backend')

__all__ = ['RemoteBackend']


class RemoteBackend:
	def __init__(self, send: Callable[[dict], None]):
		# send receives a finished, JSON-safe update message. It must be
		# thread-agnostic/cheap (e.g. run_coroutine_threadsafe into the server
		# loop) - it is called from the thread publisher signals land on.
		self._send = send

	def attach(self, plugin: 'Plugin') -> None:
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
