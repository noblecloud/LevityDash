"""RemoteFrontend — the receive-side brain of mode=remote (Phase 4.2 step 3).

Turns decoded wire ``update`` messages into ``RemoteContainer`` updates against a
per-source registry and hands each batch to a callback. This is the mirror of
``LoopbackBridge._on_published``'s decode half, but decoupled from both the
socket and the dispatcher: a ``WireClient`` feeds ``handle_message`` and the
callback is ``dispatcher.update`` — that wiring lands with the backend process,
so this logic stays testable without Qt plumbing or a live socket.
"""
from typing import Callable, Dict, Optional

from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.wire.containers import RemoteContainer, RemoteSource
from LevityDash.lib.wire.messages import PluginState, apply_container_update, parse_heartbeat, parse_plugin_status, parse_update_message

log = LevityPluginLog.getChild('Wire').getChild('Frontend')

__all__ = ['RemoteFrontend']


class RemoteFrontend:
	def __init__(
		self, on_update: Callable[[Dict[CategoryItem, RemoteContainer]], None],
		ts_request_fn: Optional[Callable[[dict, Callable], None]] = None,
		on_plugin_status: Optional[Callable[[Dict[str, PluginState]], None]] = None,
		on_heartbeat: Optional[Callable[[int, float], None]] = None,
	):
		# on_update receives {key: RemoteContainer} - dispatcher.update in
		# mode=remote, exactly what LoopbackBridge hands its dispatcher today.
		self._on_update = on_update
		# Threaded into every RemoteSource this creates (see _get_source) so
		# RemoteContainer.prepare_for_ts_connection has a way to reach the
		# live wire connection without RemoteContainer/RemoteSource knowing
		# anything about sockets/asyncio themselves - see remote.py's
		# RemoteConnection.request_timeseries for what this actually is.
		self._ts_request_fn = ts_request_fn
		# Control plane (backend->frontend only). Both optional so the existing
		# update-only construction in tests keeps working untouched.
		self._on_plugin_status = on_plugin_status
		self._on_heartbeat = on_heartbeat
		self._sources: Dict[str, RemoteSource] = {}
		#: Latest per-plugin health snapshot, replayed by the server on connect.
		self.plugin_states: Dict[str, PluginState] = {}

	def handle_message(self, message: dict) -> None:
		match message.get('type'):
			case 'update':
				pass
			case 'plugin_status':
				self.plugin_states = parse_plugin_status(message)
				if self._on_plugin_status is not None:
					self._on_plugin_status(self.plugin_states)
				return
			case 'heartbeat':
				if self._on_heartbeat is not None:
					self._on_heartbeat(*parse_heartbeat(message))
				return
			case _:
				return
		source_info, updates = parse_update_message(message)
		source = self._get_source(source_info)
		remoteValues: Dict[CategoryItem, RemoteContainer] = {}
		for key_str, container_dict in updates.items():
			key = CategoryItem(key_str)
			container = source.getOrCreate(key)
			try:
				apply_container_update(container, container_dict)
			except Exception as e:
				# one bad value must not sink the rest of the batch (same
				# per-key resilience LoopbackBridge relays with)
				log.warning(f'{source.name}:{key_str}: failed to apply wire update, skipping: {e!r}')
				continue
			remoteValues[key] = container
		if remoteValues:
			self._on_update(remoteValues)

	def _get_source(self, info: dict) -> RemoteSource:
		source = self._sources.get(info['name'])
		if source is None:
			source = self._sources[info['name']] = RemoteSource(
				name=info['name'],
				defaultFor=set(info.get('defaultFor') or ()),
				enabled=info.get('enabled', True),
				running=info.get('running', True),
				ts_request_fn=self._ts_request_fn,
			)
		return source
