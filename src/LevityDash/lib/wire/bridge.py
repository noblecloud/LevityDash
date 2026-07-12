"""LoopbackBridge: proves the wire codec + RemoteContainer round-trip
without a second process or a real socket. Intercepts each plugin's real
Publisher output, encodes the container's read-surface through codec.py -
a genuine JSON round-trip, not a shortcut - decodes it into a
RemoteContainer update, and feeds that into the same `PluginValueDirectory`
that live mode feeds through `keyAdded`.

This is Phase 4.1's stated goal: prove identical rendering in
mode=loopback before any real process/network exists. Once a real socket
client shows up (Phase 4.3), it does the same encode-on-one-side /
decode-on-the-other dance this bridge does on both sides at once - this
file is the reference for what that client's decode half needs to do.
"""
import json
from datetime import datetime
from typing import Dict, Optional, TYPE_CHECKING

from PySide6.QtCore import Slot

from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.utils.data import KeyData
from LevityDash.lib.wire.codec import decode_value, encode_value
from LevityDash.lib.wire.containers import ContainerFlags, RemoteContainer, RemoteSource

if TYPE_CHECKING:
	from LevityDash.lib.plugins.dispatcher import PluginValueDirectory
	from LevityDash.lib.plugins.observation import Container
	from LevityDash.lib.plugins.plugin import Plugin

log = LevityPluginLog.getChild('Wire').getChild('Loopback')

__all__ = ['LoopbackBridge']

_FLAG_NAMES = ContainerFlags._fields


class LoopbackBridge:
	def __init__(self, dispatcher: 'PluginValueDirectory'):
		self._dispatcher = dispatcher
		self._sources: Dict[str, RemoteSource] = {}

	def attach(self, plugin: 'Plugin') -> None:
		plugin.publisher.connectSlot(self._on_published)

	def _get_source(self, plugin: 'Plugin') -> RemoteSource:
		source = self._sources.get(plugin.name)
		if source is None:
			source = self._sources[plugin.name] = RemoteSource(
				name=plugin.name,
				defaultFor=set(plugin.config.defaultFor),
				enabled=plugin.enabled,
				running=plugin.running,
			)
		return source

	@Slot(KeyData)
	def _on_published(self, data: KeyData) -> None:
		plugin = data.sender
		keys = data.keys
		if isinstance(keys, dict):
			keys = set().union(*keys.values())
		remoteSource = self._get_source(plugin)
		remoteValues = {}
		for key in keys:
			container = plugin[key]
			try:
				remoteContainer = self._relay(remoteSource, key, container)
			except Exception as e:
				# One bad value (e.g. a WeatherUnits localize() failure on
				# an unresolved unit type - seen live with a real plugin)
				# must not take the rest of this batch down with it; every
				# other key in `keys` still needs to reach the dispatcher.
				log.warning(f'{remoteSource.name}:{key}: failed to relay for loopback, skipping this key: {e!r}')
				continue
			if remoteContainer is not None:
				remoteValues[key] = remoteContainer
		if remoteValues:
			self._dispatcher.update(remoteValues)

	def _relay(self, remoteSource: RemoteSource, key: CategoryItem, container: 'Container') -> Optional[RemoteContainer]:
		observationValue = container.value
		if observationValue is None:
			return None

		metadata = container.metadata or {}
		icon_alias = None
		rawValue = observationValue.value
		if metadata.get('type') == 'icon':
			# Icon objects carry a QFont and aren't wire-safe - push the
			# alias string and let the frontend resolve it lazily (see
			# containers.py's RemoteObservationValue.icon_alias).
			try:
				icon_alias = metadata.mapAlias(observationValue.rawValue)
			except Exception as e:
				log.warning(f'{key}: failed to resolve icon alias for loopback push: {e}')
			rawValue = None

		outgoing = {
			'value': encode_value(rawValue) if rawValue is not None else None,
			'timestamp': encode_value(observationValue.timestamp) if isinstance(observationValue.timestamp, datetime) else None,
			'title': container.title,
			'metadata': {k: metadata[k] for k in ('title', 'type', 'iconType') if k in metadata},
			'icon_alias': icon_alias,
			'flags': {name: getattr(container, name) for name in _FLAG_NAMES},
		}
		# A genuine bytes round-trip - this is the actual point of 4.1, not
		# just calling encode_value/decode_value back to back in memory.
		wireBytes = json.dumps(outgoing).encode('utf-8')
		incoming = json.loads(wireBytes.decode('utf-8'))

		remoteContainer = remoteSource.getOrCreate(key)
		remoteContainer._update(
			value=decode_value(incoming['value']) if incoming['value'] is not None else None,
			timestamp=decode_value(incoming['timestamp']) if incoming['timestamp'] is not None else None,
			metadata=incoming['metadata'],
			flags=ContainerFlags(**incoming['flags']),
			title=incoming['title'],
			icon_alias=incoming['icon_alias'],
		)
		return remoteContainer
