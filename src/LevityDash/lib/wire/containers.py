"""Frontend-side stand-ins for the plugin-layer classes that
`MultiSourceContainer` reconciliation and display widgets read directly:
`observation.Container` -> `RemoteContainer`, `plugin.Plugin` -> `RemoteSource`,
`plugin.utils.Publisher` -> `RemotePublisher`.

These hold state pushed over the wire (or, in loopback mode, copied
in-process from a real `Container`) rather than owning live plugin
connections. Per the CONFIRMED seam (see the revival plan, Phase 4): value
approximation (`nowFromTimeseries`) already happened backend-side by the
time a push arrives, so `.value`/`.now`/`.realtime`/`.nowFromTimeseries` all
just return the one value that was pushed - the frontend never resolves an
approximation itself, it only reconciles *which source's* pushed value to
show (that logic lives unchanged in `MultiSourceContainer`, operating on
these stand-ins instead of real `Container`s).

Scope note: `.hourly`/`.daily` still return `None` (no daily/hourly wire
support yet). `.timeseries`/`.timeseriesAll` are now backed by
`RemoteTimeSeries` (the timeseries-over-wire milestone) - populated once
`RemoteContainer.prepare_for_ts_connection` gets a response back from the
backend; `None` until then, exactly like a real `Container` before its
first `.timeseries.update()`.
"""
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Hashable, List, NamedTuple, Optional, Set, Type

from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.observation import RealtimeSource, TimeSeriesItem
from LevityDash.lib.plugins.utils import ChannelSignal, GuardedRequest, Request

# NOTE: messages.py imports ContainerFlags/RemoteContainer from this module -
# build_ts_request/decode_ts_response are imported lazily inside the methods
# that use them (RemoteSource.request_timeseries, Container.prepare_for_ts_
# connection) to avoid a circular import at module load time.

log = LevityPluginLog.getChild('Wire')

__all__ = ['ContainerFlags', 'RemoteObservationValue', 'RemotePublisher', 'RemoteSource', 'RemoteContainer', 'RemoteTimeSeries']

_DEFAULT_MIN_PERIOD = timedelta(hours=-3)
_DEFAULT_MAX_PERIOD = timedelta(hours=3)


class ContainerFlags(NamedTuple):
	"""The is*-flag snapshot pushed alongside a value. Backend computes
	these once (they follow from the plugin's observation periods, see
	Container.isRealtime/.isForecast/etc.) rather than recomputing them
	frontend-side from data it doesn't have."""
	isRealtime: bool = False
	isRealtimeApproximate: bool = False
	isForecast: bool = False
	isTimeseries: bool = False
	isDaily: bool = False
	isDailyForecast: bool = False
	isDailyOnly: bool = False
	isTimeseriesOnly: bool = True


class _RemoteValueSource:
	"""Stand-in for the ObservationDict a pushed value came from (what
	`ObservationValue.source` returns live). Widget code (Realtime.py's stale
	label, `__updateTimeOffsetLabel`) reads exactly two things off it:
	``isinstance(source, RealtimeSource)`` to pick the staleness threshold,
	and ``.period`` as that threshold for polled sources. Remote mode can't
	know the backend's poll period, so polled values reuse the same 15-minute
	fallback streaming sources get - if the label needs live parity there,
	the period has to cross the wire, not be guessed here."""

	period = timedelta(minutes=15)

	def __init__(self, name: str):
		self.name = name


@RealtimeSource.register
class _RemoteRealtimeValueSource(_RemoteValueSource):
	"""The streaming variant - registered so ``isinstance(source, RealtimeSource)``
	holds, exactly as it would for a live WeatherFlow/Govee value. Chosen per
	update from the container's wire-pushed ``isRealtime`` flag."""


class RemoteObservationValue:
	"""Stand-in for `observation.ObservationValue`. Holds an already
	backend-converted value (a real WeatherUnits Measurement, a datetime, or
	a plain scalar) - no schema, no unit conversion, no rawValue/value
	distinction, since the backend already did that work before pushing.

	`icon_alias`, when set, means the pushed value is the plain alias string
	for an icon-type key (e.g. 'clear-day') rather than a resolved Icon -
	Icon objects carry a QFont and are not wire-safe, so icon resolution
	(`getIcon()`, a Qt-touching call) happens here, lazily, frontend-side -
	never on the backend.
	"""

	__slots__ = ('_value', '_timestamp', '_metadata', '_icon_alias', '_source')

	def __init__(self, value: Any, timestamp=None, metadata: Optional[dict] = None, icon_alias: Optional[str] = None, source: Optional[_RemoteValueSource] = None):
		self._value = value
		self._timestamp = timestamp
		self._metadata = metadata if metadata is not None else {}
		self._icon_alias = icon_alias
		self._source = source

	@property
	def source(self) -> Optional[_RemoteValueSource]:
		return self._source

	@property
	def value(self) -> Any:
		if self._icon_alias is not None:
			from LevityDash.lib.ui.icons import getIcon
			return getIcon(self._icon_alias)
		return self._value

	@property
	def rawValue(self) -> Any:
		return self._value

	@property
	def timestamp(self):
		return self._timestamp

	@property
	def isValid(self) -> bool:
		return self._value is not None

	@property
	def metadata(self) -> dict:
		return self._metadata

	@property
	def isIcon(self) -> bool:
		return self._metadata.get('type') == 'icon'

	@property
	def icon(self):
		return self.value if self.isIcon else None

	def __getitem__(self, item):
		if isinstance(item, str) and item.startswith('@'):
			value = self.value
			result = getattr(value, item[1:], None)
			if result is not None:
				return result
			raise AttributeError(item)
		if item in self._metadata:
			return self._metadata[item]
		return getattr(self, item)

	def __str__(self):
		return str(self.value)

	def __format__(self, format_spec: str):
		# Delegates to the underlying value's own __format__ (WeatherUnits
		# Measurements implement precision/unit formatting themselves).
		# Does not replicate ObservationValue's 'human' relative-date DSL -
		# a documented simplification, not a correctness gap: timestamp
		# values still format via WeatherUnits' own Time type.
		value = self.value
		spec = format_spec.replace('human', '').strip(':')
		try:
			return format(value, spec)
		except (TypeError, ValueError):
			return str(value)

	def __repr__(self):
		return f'RemoteObservationValue({self._value!r})'


class RemotePublisher:
	"""Stand-in for `plugins.utils.Publisher`. Owns the per-key
	`ChannelSignal`s for one `RemoteSource`, mirroring how a real `Plugin`'s
	`Publisher` owns them - so `RemoteContainer.channel` and
	`RemoteSource.publisher.disconnectChannel(...)` (both are called by
	widget code, see Realtime.py's connect/disconnect pair) behave
	identically to the real thing."""

	def __init__(self, source: 'RemoteSource'):
		self.source = source
		self.__channels: Dict[CategoryItem, ChannelSignal] = {}

	def connectChannel(self, key: CategoryItem, slot: Callable) -> bool | ChannelSignal:
		channel = self.__channels.get(key, None)
		if channel is None:
			channel = self.__channels[key] = ChannelSignal(self.source, key)
		return channel if channel.connectSlot(slot) else False

	def disconnectChannel(self, key: CategoryItem, slot: Callable) -> bool:
		channel = self.__channels.get(key, None)
		if channel is not None:
			return channel.disconnectSlot(slot)
		return False


class _RemoteConfig:
	"""Stand-in for the slice of `PluginConfig` that reconciliation reads:
	`defaultFor` (source-priority tie-breaking) and `['enabled']`."""

	def __init__(self, defaultFor: Optional[Set[str]] = None, enabled: bool = True):
		self.defaultFor = defaultFor or set()
		self._enabled = enabled

	def __getitem__(self, key):
		if key == 'enabled':
			return self._enabled
		raise KeyError(key)


class RemoteSource:
	"""Stand-in for `plugin.Plugin`. Carries just enough source identity/
	metadata for `MultiSourceContainer`'s reconciliation (source name,
	defaultFor, enabled/running) and for widgets that read `container.source`
	directly (`.name`, `.publisher.disconnectChannel`).

	Owns the `RemoteContainer` registry for this source and resolves
	`self[key] -> RemoteContainer`, which is also how a container's own
	channel-publish loop closes: `RemoteContainer.channel.publish({self})`
	relies on `MultiSourceChannel.publish` grouping by `obs.source[key]`
	(see `dispatcher.MultiSourceChannel.publish`) - a RemoteContainer
	stands in as its own "observation" for that lookup.
	"""

	def __init__(
		self, name: str, defaultFor: Optional[Set[str]] = None, enabled: bool = True, running: bool = True,
		ts_request_fn: Optional[Callable[[dict, Callable], None]] = None,
	):
		self.name = name
		self.config = _RemoteConfig(defaultFor=defaultFor, enabled=enabled)
		self.running = running
		self.publisher = RemotePublisher(self)
		self._containers: Dict[CategoryItem, 'RemoteContainer'] = {}
		# The actual cross-thread request primitive (RemoteConnection.
		# request_timeseries) - None when there's no live connection (e.g. in
		# tests), in which case request_timeseries degrades to "no data"
		# synchronously rather than hanging.
		self._ts_request_fn = ts_request_fn

	@property
	def enabled(self) -> bool:
		return self.config['enabled']

	def request_timeseries(self, key: CategoryItem, min_period: Optional[timedelta], max_period: Optional[timedelta], on_response: Callable[[Optional[dict]], None]) -> None:
		if self._ts_request_fn is None:
			on_response(None)
			return
		from LevityDash.lib.wire.messages import build_ts_request  # deferred - see module note
		message = build_ts_request(source=self.name, key=str(key), min_period=min_period, max_period=max_period)
		self._ts_request_fn(message, on_response)

	# --- the slice of Plugin's observation-surface that MultiSourceContainer
	# reads during reconciliation (dispatcher.py's .realtime/.timeseries/
	# .hourly/.daily fallbacks) and the status bar's value path (app.py
	# StatusBarItem.value -> container.realtime). Timeseries don't cross the
	# wire yet (Phase 4.4), so those report unavailable.

	@property
	def hourly(self):
		return None

	@property
	def daily(self):
		return None

	def hasRealtimeFor(self, key) -> bool:
		container = self._containers.get(key)
		return container is not None and container.isRealtime

	def hasTimeseriesFor(self, key) -> bool:
		# Mirrors hasRealtimeFor's pattern: consult the flag the backend
		# already pushed for this container, rather than trying to replicate
		# the real Plugin.hasTimeseriesFor's endpoint-capability check (this
		# stand-in has no endpoint concept, only per-container flags).
		container = self._containers.get(key)
		return container is not None and container.isForecast

	def hasDailyFor(self, key) -> bool:
		container = self._containers.get(key)
		return container is not None and (container.isDaily or container.isDailyForecast)

	def getOrCreate(self, key: CategoryItem) -> 'RemoteContainer':
		container = self._containers.get(key)
		if container is None:
			container = self._containers[key] = RemoteContainer(self, key)
		return container

	def __getitem__(self, key: CategoryItem) -> 'RemoteContainer':
		return self._containers[key]

	def __contains__(self, key: CategoryItem) -> bool:
		return key in self._containers

	def __hash__(self):
		return hash(self.name)

	def __eq__(self, other):
		if isinstance(other, str):
			return self.name == other
		return isinstance(other, RemoteSource) and self.name == other.name

	def __repr__(self):
		return f'RemoteSource({self.name})'

	def __str__(self):
		return self.name


class RemoteTimeSeries:
	"""Frontend stand-in for `observation.MeasurementTimeSeries` (the
	timeseries-over-wire milestone). Built once from a decoded ts_response's
	columnar arrays - a fully materialized snapshot, not a live/incrementally
	updating series (there's no re-fetch on pan/zoom yet - a follow-up).

	Reuses `TimeSeriesItem` (a plain value holder, no Qt/plugin coupling) and
	`ChannelSignal` (the same generic pub/sub primitive `RemoteContainer.channel`
	already reuses) rather than the real `MeasurementTimeSeries`, which
	subclasses `OrderedDict` and is deeply entangled with `Observation`/
	multi-source merge logic that doesn't exist wire-side.

	Matches exactly the surface `Graph.py` reads off a real timeseries:
	`.signals` (context manager + connect/disconnectSlot), datetime slicing
	(`__getitem__`), `.first`, `len()` (also covers the truthiness checks at
	`Graph.py`'s `if self.data.timeseries` sites - no separate `__bool__`
	needed), and a no-op-but-safe `.refresh()`.
	"""

	__slots__ = ('source', 'key', '_items', 'signals')

	def __init__(self, source: 'RemoteSource', key: CategoryItem, items: List[TimeSeriesItem]):
		self.source = source
		self.key = key
		self._items = sorted(items, key=lambda i: i.timestamp)
		self.signals = ChannelSignal(source, key)

	def __getitem__(self, item):
		if isinstance(item, slice):
			lo = item.start.timestamp() if item.start is not None else float('-inf')
			hi = item.stop.timestamp() if item.stop is not None else float('inf')
			return [i for i in self._items if lo <= i.timestamp.timestamp() <= hi]
		raise TypeError(f'RemoteTimeSeries only supports datetime slicing, not {item!r}')

	def __iter__(self):
		return iter(self._items)

	def __len__(self):
		return len(self._items)

	@property
	def first(self) -> Optional[TimeSeriesItem]:
		return self._items[0] if self._items else None

	def refresh(self, callback: Optional[Callable] = None) -> None:
		# A materialized snapshot, not a live series - no periodic re-fetch
		# this milestone (a follow-up). No-op beyond firing callback, so
		# GraphItemData.refresh (Graph.py, self.timeseries.refresh()) doesn't
		# crash if ever reached in remote mode.
		if callback is not None:
			callback()

	def __repr__(self):
		return f'RemoteTimeSeries({self.source.name}:{self.key.name}, {len(self._items)} points)'


class RemoteContainer:
	"""Stand-in for `observation.Container` - see the module docstring for
	the scope this covers and the rationale for what it doesn't (yet)."""

	def __init__(self, source: RemoteSource, key: CategoryItem):
		self.source = source
		self.key = key
		self._value: Optional[RemoteObservationValue] = None
		self._flags = ContainerFlags()
		self._title: Optional[str] = None
		self._awaitingRequirements: Dict[Hashable, GuardedRequest] = {}
		self._timeseries: Optional[RemoteTimeSeries] = None
		self.__hash_key = CategoryItem(key, source=[source.name])

	def _update(
		self,
		value: Any,
		timestamp=None,
		metadata: Optional[dict] = None,
		flags: Optional[ContainerFlags] = None,
		title: Optional[str] = None,
		icon_alias: Optional[str] = None,
	):
		"""Called by the wire bridge (loopback or, later, a real socket
		client) when a new value arrives for this (source, key)."""
		if flags is not None:
			self._flags = flags
		source_cls = _RemoteRealtimeValueSource if self._flags.isRealtime else _RemoteValueSource
		self._value = RemoteObservationValue(value, timestamp=timestamp, metadata=metadata, icon_alias=icon_alias, source=source_cls(self.source.name))
		if title is not None:
			self._title = title
		self.channel.publish({self})
		self._checkAwaiting()

	@property
	def channel(self) -> ChannelSignal:
		return self.source.publisher.connectChannel(self.key, self._noop_slot)

	def _noop_slot(self, *_):
		# RemoteContainer has no cache of its own to invalidate on update
		# (no live hourly/daily/timeseries yet, see module docstring) - this
		# slot exists only so `.channel` lazily creates the ChannelSignal
		# the same way Container.channel does, keeping the two classes'
		# connect/disconnect behavior identical for widget code.
		pass

	def _checkAwaiting(self):
		if not self._awaitingRequirements:
			return
		for request in list(self._awaitingRequirements.values()):
			try:
				guarded = not request.guard(self)
			except Exception as e:
				log.warning(f'{self.log_repr}: awaiting-request guard raised {e!r}, treating as unmet')
				continue
			if not guarded:
				try:
					request.callback()
				except Exception as e:
					log.error(f'Failed to call callback for {request.requester}: {e}')
				else:
					self._awaitingRequirements.pop(request.requester, None)

	def notifyOnRequirementsMet(self, requester: Hashable = None, guard: Callable = None, callback: Callable = None, guarded_request: GuardedRequest = None):
		# Signature normalization mirrors observation.Container's exactly -
		# dispatcher.checkAwaiting calls this positionally with a bare
		# GuardedRequest, so the stand-in has to accept every shape the real
		# one does.
		signature = {}
		if requester is not None:
			signature['requester'] = requester
		if guard is not None:
			signature['guard'] = guard
		if callback is not None:
			signature['callback'] = callback
		if guarded_request is not None:
			signature['guarded_request'] = guarded_request

		match signature:
			case {'requester': GuardedRequest() as request, **rest} | {'guarded_request': GuardedRequest() as request, **rest}:
				if guard := rest.get('guard', None):
					request = request.with_guard(guard)
			case {'requester': Request() as request, **rest} | {'guarded_request': Request() as request, **rest}:
				if guard := rest.get('guard', None):
					request = GuardedRequest.from_request(request, guard)
			case {'requester': requester, 'callback': callback, 'guard': guard}:
				request = GuardedRequest(**signature)
			case _:
				raise TypeError(f'Invalid signature: {signature}')

		if self._value is not None:
			try:
				met = request.guard(self)
			except Exception:
				met = False
			if met:
				request.callback()
				return
		self._awaitingRequirements[request.requester] = request

	def prepare_for_ts_connection(self, request: Request):
		# The timeseries-over-wire counterpart to Container.prepare_for_ts_
		# connection (observation.py): issues a real request instead of firing
		# back immediately. request.callback() only fires once a response
		# (or a definitive "no connection") comes back, exactly like the live
		# path only calls back once MeasurementTimeSeries.update() finishes.
		from LevityDash.lib.wire.messages import decode_ts_response  # deferred - see module note

		def on_response(response: Optional[dict]) -> None:
			if response is None:
				log.debug(f'{self.log_repr}: no ts_response (no connection or request failed)')
			else:
				ok, points, error = decode_ts_response(response)
				if not ok:
					log.warning(f'{self.log_repr}: ts_request failed: {error}')
				elif points:
					items = [TimeSeriesItem.load_raw(value, timestamp) for timestamp, value in points]
					self._timeseries = RemoteTimeSeries(self.source, self.key, items)
			request.callback()

		minPeriod, maxPeriod = self._resolve_ts_period(request)
		self.source.request_timeseries(self.key, minPeriod, maxPeriod, on_response)

	@staticmethod
	def _resolve_ts_period(request: Request) -> tuple:
		# Duck-typed capability query: a requester (e.g. Graph.py's
		# GraphItemData) can expose `.wireTimeseriesPeriod -> (min, max)` to
		# get a fetch matching its own configured timeframe instead of the
		# generic default - without RemoteContainer/RemoteSource ever
		# importing Graph.py or anything UI-specific. `request.requester` is
		# otherwise only ever used for identity (hashing/logging, see
		# dispatcher.py/utils.py's Request), so this is a deliberate, narrow
		# extension of that contract, not a pre-existing one.
		period = getattr(request.requester, 'wireTimeseriesPeriod', None)
		if period is None:
			return _DEFAULT_MIN_PERIOD, _DEFAULT_MAX_PERIOD
		try:
			minPeriod, maxPeriod = period
			if not isinstance(minPeriod, timedelta) or not isinstance(maxPeriod, timedelta):
				raise TypeError
			return minPeriod, maxPeriod
		except (TypeError, ValueError) as e:
			log.warning(f'requester {request.requester!r} provided an invalid wireTimeseriesPeriod {period!r} ({e!r}), using the default window')
			return _DEFAULT_MIN_PERIOD, _DEFAULT_MAX_PERIOD

	@property
	def log_repr(self) -> str:
		return f'RemoteContainer({self.source.name}:{self.key.name})'

	def __repr__(self):
		return f'RemoteContainer({self.source.name}:{self.key[-1]} {self.value})'

	def __str__(self):
		return str(self.value) if self.value is not None else ''

	def __hash__(self):
		return hash(self.__hash_key)

	def __eq__(self, other):
		return hash(self) == hash(other)

	def toDict(self):
		return {'key': self.key, 'value': self.value}

	@property
	def title(self) -> str:
		if self._title is not None:
			return self._title
		value = self.value
		if value is not None and hasattr(value.value, 'title'):
			return value.value.title
		return str(self.key).title()

	@property
	def value(self) -> Optional[RemoteObservationValue]:
		return self._value

	@property
	def now(self) -> Optional[RemoteObservationValue]:
		return self._value

	realtime = now

	@property
	def nowFromTimeseries(self) -> Optional[RemoteObservationValue]:
		return self._value

	@property
	def hourly(self):
		return None

	@property
	def daily(self):
		return None

	@property
	def timeseries(self) -> Optional[RemoteTimeSeries]:
		return self._timeseries

	# Same snapshot - no separate "all history" fetch this milestone (a
	# follow-up); the columnar response already covers the requested window.
	timeseriesAll = timeseries

	@property
	def metadata(self) -> dict:
		return self._value.metadata if self._value is not None else {}

	@property
	def value_type(self) -> Type:
		try:
			return type(self._value.value)
		except Exception:
			from WeatherUnits import Measurement
			return Measurement

	@property
	def isRealtime(self) -> bool:
		return self._flags.isRealtime

	@property
	def isRealtimeApproximate(self) -> bool:
		return self._flags.isRealtimeApproximate

	@property
	def isForecast(self) -> bool:
		return self._flags.isForecast

	@property
	def isTimeseries(self) -> bool:
		return self._flags.isTimeseries

	@property
	def isDaily(self) -> bool:
		return self._flags.isDaily

	@property
	def isDailyForecast(self) -> bool:
		return self._flags.isDailyForecast

	@property
	def isDailyOnly(self) -> bool:
		return self._flags.isDailyOnly

	@property
	def isTimeseriesOnly(self) -> bool:
		return self._flags.isTimeseriesOnly
