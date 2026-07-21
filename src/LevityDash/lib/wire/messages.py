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
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.wire.codec import decode_value, encode_value
from LevityDash.lib.wire.containers import ContainerFlags, RemoteContainer

if TYPE_CHECKING:
	from LevityDash.lib.plugins.observation import Container

log = LevityPluginLog.getChild('Wire').getChild('Messages')

__all__ = ['encode_container', 'apply_container_update']

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
