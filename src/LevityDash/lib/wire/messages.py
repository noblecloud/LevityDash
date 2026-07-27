"""Container-level wire messages.

Sits one layer above codec.py (which handles individual *values*): encodes a
live ``Container``'s current read-surface into a JSON-safe dict (the
backend/publish side) and applies a received dict onto a ``RemoteContainer``
(the frontend/decode side).

This is the exact encode/decode pair ``LoopbackBridge`` used to inline. It's
pulled out here so the loopback bridge (both halves in-process), and — from
Phase 4.2 — the real ``WireServer`` (encode half) and ``WireClient`` (decode
half), all share one implementation and can't drift apart. The dict shape
produced by ``encode_container`` and consumed by ``apply_container_update`` is
the wire message contract.

Also defines the 'ts_request'/'ts_response' pair (build_ts_request/
encode_ts_response/decode_ts_response) - the frontend->backend->frontend
counterpart to 'update' messages above, which only ever flow backend->
frontend. See lib/wire/server.py's unicast reply path and client.py's
request/response correlation for how these actually cross the wire.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple, TYPE_CHECKING
from uuid import uuid4

from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.wire.codec import WIRE_VERSION, decode_timeseries_values, encode_timeseries_values, decode_value, encode_value
from LevityDash.lib.wire.containers import ContainerFlags, RemoteContainer

if TYPE_CHECKING:
	from LevityDash.lib.plugins.observation import Container

log = LevityPluginLog.getChild('Wire').getChild('Messages')

__all__ = [
	'encode_container', 'apply_container_update', 'encode_update_message', 'parse_update_message',
	'build_ts_request', 'encode_ts_response', 'decode_ts_response',
	'PluginState', 'encode_plugin_status', 'parse_plugin_status',
	'encode_heartbeat', 'parse_heartbeat',
]

# The flag fields a container advertises across the wire (isRealtime,
# isForecast, ...) - read off the live Container by name on encode, rebuilt
# into a ContainerFlags on decode.
_FLAG_NAMES = ContainerFlags._fields


def encode_container(container: 'Container') -> Optional[dict]:
	"""Encode a live ``Container``'s current read-surface to a JSON-safe dict.

	Returns ``None`` when the container has no value yet (nothing to push).
	Raises on a genuinely un-encodable value - callers relay per-key and skip
	the offending key so one bad value can't sink a whole batch.
	"""
	observationValue = container.value
	if observationValue is None:
		return None

	metadata = container.metadata or {}
	icon_alias = None
	rawValue = observationValue.value
	if metadata.get('type') == 'icon':
		# Icon objects carry a QFont and aren't wire-safe - push the alias
		# string and let the frontend resolve it lazily (see containers.py's
		# RemoteObservationValue.icon_alias).
		try:
			icon_alias = metadata.mapAlias(observationValue.rawValue)
		except Exception as e:
			log.warning(f'{container.key}: failed to resolve icon alias for wire push: {e}')
		rawValue = None

	return {
		'value': encode_value(rawValue) if rawValue is not None else None,
		'timestamp': encode_value(observationValue.timestamp) if isinstance(observationValue.timestamp, datetime) else None,
		'title': container.title,
		'metadata': {k: metadata[k] for k in ('title', 'type', 'iconType') if k in metadata},
		'icon_alias': icon_alias,
		'flags': {name: getattr(container, name) for name in _FLAG_NAMES},
	}


def apply_container_update(remoteContainer: RemoteContainer, incoming: dict) -> None:
	"""Apply a received wire message dict onto a frontend ``RemoteContainer``."""
	remoteContainer._update(
		value=decode_value(incoming['value']) if incoming['value'] is not None else None,
		timestamp=decode_value(incoming['timestamp']) if incoming['timestamp'] is not None else None,
		metadata=incoming['metadata'],
		flags=ContainerFlags(**incoming['flags']),
		title=incoming['title'],
		icon_alias=incoming['icon_alias'],
	)


# --- envelope level: a full 'update' message wrapping per-key container dicts ---

def encode_update_message(*, name: str, defaultFor=None, enabled: bool = True, running: bool = True, updates: dict) -> dict:
	"""Wrap already-encoded container dicts in a full 'update' wire message.

	``updates`` maps ``str(key) -> encode_container(container)``. Kept separate
	from encode_container so the per-key encode and the envelope stay independent
	(the server encodes each changed container, then wraps the batch here).
	"""
	return {
		'v': WIRE_VERSION,
		'type': 'update',
		'source': {
			'name': name,
			'defaultFor': sorted(defaultFor or ()),
			'enabled': bool(enabled),
			'running': bool(running),
		},
		'updates': updates,
	}


def parse_update_message(message: dict) -> tuple[dict, dict]:
	"""Split an 'update' message into ``(source_info, {str(key): container_dict})``."""
	return message['source'], message['updates']


# --- timeseries request/response: the frontend->backend->frontend counterpart
# to the backend->frontend-only 'update' messages above ---

def build_ts_request(*, source: str, key: str, min_period: Optional[timedelta], max_period: Optional[timedelta]) -> dict:
	"""Build a 'ts_request' message asking a concrete source (never AnySource -
	dispatcher-side resolution already picked one, see dispatcher.py's
	getPreferredSourceContainer) for a columnar timeseries snapshot of one key.

	min_period/max_period mirror Container.timeseries' own construction
	(observation.py, default ±3h) rather than an explicit start/end - the
	wire protocol doesn't need to know about a Graph's viewport, which
	re-slices client-side out of whatever window it's handed either way.
	"""
	return {
		'v': WIRE_VERSION,
		'type': 'ts_request',
		'id': str(uuid4()),
		'source': source,
		'key': key,
		'minPeriod': min_period.total_seconds() if min_period is not None else None,
		'maxPeriod': max_period.total_seconds() if max_period is not None else None,
	}


def encode_ts_response(*, request_id: str, source: str, key: str, ok: bool, items: Optional[Sequence[Any]] = None, error: Optional[str] = None) -> dict:
	"""Build the matching 'ts_response' - same `id` as the request it answers,
	so the client can correlate it (see client.py's pending-futures map)."""
	return {
		'v': WIRE_VERSION,
		'type': 'ts_response',
		'id': request_id,
		'ok': ok,
		'error': error,
		'source': source,
		'key': key,
		'timeseries': encode_timeseries_values(items) if (ok and items is not None) else None,
	}


def decode_ts_response(message: dict) -> Tuple[bool, List[Tuple[datetime, Any]], Optional[str]]:
	"""Decode a 'ts_response' into (ok, [(timestamp, value), ...], error).
	Always returns a (possibly empty) list - never raises - so callers don't
	need a separate empty/error branch beyond checking `ok`."""
	return message['ok'], decode_timeseries_values(message.get('timeseries')), message.get('error')


# --- control plane: plugin health + liveness -------------------------------
#
# Two message types, both backend->frontend broadcast, deliberately separate:
#
# 'heartbeat' is small and unconditional. It answers "is the backend process
# still alive and pumping?" even when no plugin has published for a while -
# which is the normal state for a weather backend on a slow poll interval, so
# silence on the update channel says nothing about health.
#
# 'plugin_status' is the per-plugin snapshot and is sent on change (plus once
# to each newly-connected client, replayed by WireServer). It is NOT a
# liveness signal: an unchanged status is not resent, so its absence is
# expected. Read staleness off the heartbeat, never off this.


class PluginState(NamedTuple):
	"""One plugin's health as seen from the frontend."""

	name: str
	enabled: bool
	running: bool
	keyCount: int
	#: When the backend last saw this plugin publish, or None if never. Sourced
	#: from RemoteBackend's own view of publishes rather than from Plugin
	#: internals - the backend already sees every publish, and nothing on
	#: Plugin tracks this today.
	lastPublish: Optional[datetime] = None


def _plugin_key_count(plugin: Any) -> int:
	"""How many keys a plugin currently exposes.

	``Plugin`` defines no ``__len__`` (the ``__len__`` nearby in plugin.py
	belongs to its observation-class dict, not the plugin), so ``len(plugin)``
	raises TypeError - which an over-broad except silently reported as 0 for
	every plugin, including busy ones. ``keys()`` is the real published
	surface; the fallbacks keep lightweight test stand-ins working.
	"""
	for source in (
		lambda: len(plugin.keys()),
		lambda: len(plugin.containers),
		lambda: len(plugin),
	):
		try:
			return int(source())
		except Exception:
			continue
	return 0


def encode_plugin_status(*, plugins: Sequence[Any], lastPublish: Optional[dict] = None) -> dict:
	"""Build a 'plugin_status' message from live plugin objects.

	Attributes are read duck-typed (``name``/``enabled``/``running``, and
	``len()`` for the key count) so tests can pass stand-ins without
	constructing a real ``Plugin`` - the same approach ``tests/wire`` already
	takes for containers.
	"""
	lastPublish = lastPublish or {}
	entries = []
	for plugin in plugins:
		name = getattr(plugin, 'name', None)
		if name is None:
			continue
		keyCount = _plugin_key_count(plugin)
		published = lastPublish.get(name)
		entries.append({
			'name': name,
			'enabled': bool(getattr(plugin, 'enabled', False)),
			'running': bool(getattr(plugin, 'running', False)),
			'keyCount': keyCount,
			'lastPublish': encode_value(published) if isinstance(published, datetime) else None,
		})
	return {
		'v': WIRE_VERSION,
		'type': 'plugin_status',
		'plugins': sorted(entries, key=lambda e: e['name']),
	}


def parse_plugin_status(message: dict) -> Dict[str, PluginState]:
	"""Decode a 'plugin_status' message into ``{name: PluginState}``.

	Never raises on a malformed entry - a plugin the frontend can't understand
	is skipped rather than sinking the whole snapshot, matching the per-key
	resilience the update path already relays with.
	"""
	states: Dict[str, PluginState] = {}
	for entry in message.get('plugins') or ():
		try:
			published = entry.get('lastPublish')
			states[entry['name']] = PluginState(
				name=entry['name'],
				enabled=bool(entry.get('enabled', False)),
				running=bool(entry.get('running', False)),
				keyCount=int(entry.get('keyCount') or 0),
				lastPublish=decode_value(published) if published is not None else None,
			)
		except Exception as e:
			log.warning(f'skipping malformed plugin_status entry {entry!r}: {e!r}')
	return states


def encode_heartbeat(*, seq: int, uptime: float) -> dict:
	"""Build a 'heartbeat'. ``seq`` increments per beat so a frontend can spot
	a backend restart (the sequence going backwards) as distinct from a
	reconnect, and ``uptime`` is seconds since the backend started."""
	return {
		'v': WIRE_VERSION,
		'type': 'heartbeat',
		'seq': int(seq),
		'uptime': float(uptime),
	}


def parse_heartbeat(message: dict) -> Tuple[int, float]:
	"""Decode a 'heartbeat' into ``(seq, uptime)``."""
	return int(message.get('seq') or 0), float(message.get('uptime') or 0.0)
