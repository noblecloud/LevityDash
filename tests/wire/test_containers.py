"""Tests for RemoteContainer/RemoteSource/RemotePublisher (lib/wire/containers.py)
and LoopbackBridge's translation logic (lib/wire/bridge.py).

Uses lightweight stand-ins for the real observation.Container rather than
bootstrapping a full synthetic Plugin (config files, schema, observations) -
these tests are precise about what LoopbackBridge._relay reads, matching the
verified 4.1 widget-surface inventory (see docs/reviews and the plan file),
rather than fighting the real plugin bootstrap machinery for something a
stub covers exactly as well.

MultiSourceContainer itself is exercised for real (not stubbed) - proving
RemoteContainer is a genuine drop-in for its reconciliation logic is the
actual point of Phase 4.1's "operating on RemoteContainer stand-ins instead
of real Containers, unchanged" design.
"""
import WeatherUnits as wu

# Import LevityDash before `datetime` - see test_codec.py's import-order
# comment for why (shims/_datetime_shim.install() swaps sys.modules['datetime']).
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins import AnySource
from LevityDash.lib.plugins.dispatcher import MultiSourceContainer
from LevityDash.lib.plugins.observation import RealtimeSource, TimeSeriesItem
from LevityDash.lib.plugins.utils import Request
from LevityDash.lib.wire.bridge import LoopbackBridge
from LevityDash.lib.wire.containers import ContainerFlags, RemoteContainer, RemoteSource, RemoteTimeSeries
from datetime import datetime, timedelta, timezone


class FakeObservationValue:
	def __init__(self, value, timestamp=None):
		self.value = value
		self.rawValue = value
		self.timestamp = timestamp


class FakeContainer:
	"""Stands in for observation.Container - exposes exactly what
	LoopbackBridge._relay reads (see bridge.py)."""

	def __init__(self, value, title='Temperature', metadata=None, timestamp=None, **flags):
		self.value = FakeObservationValue(value, timestamp=timestamp)
		self.title = title
		self.metadata = metadata if metadata is not None else {'title': title, 'type': 'measurement'}
		for name in ContainerFlags._fields:
			setattr(self, name, flags.get(name, False))


def make_bridge():
	return LoopbackBridge(dispatcher=None)  # _relay doesn't touch self._dispatcher


def test_relay_produces_a_remote_container_with_matching_value():
	bridge = make_bridge()
	source = RemoteSource(name='TestPlugin', defaultFor={'temperature'})
	key = CategoryItem('environment.temperature.temperature')
	container = FakeContainer(wu.Temperature.Fahrenheit(72.5), isRealtime=True)

	remote = bridge._relay(source, key, container)

	assert isinstance(remote, RemoteContainer)
	assert remote.source is source
	assert remote.key == key
	assert isinstance(remote.value.value, wu.Temperature.Fahrenheit)
	assert float(remote.value.value) == 72.5
	assert remote.isRealtime is True
	assert remote.isForecast is False


def test_relay_carries_flags_through_the_wire():
	bridge = make_bridge()
	source = RemoteSource(name='TestPlugin')
	key = CategoryItem('environment.precipitation.precipitation')
	container = FakeContainer(
		wu.Humidity.Humidity(55),
		isForecast=True,
		isTimeseries=True,
		isRealtimeApproximate=True,
	)

	remote = bridge._relay(source, key, container)

	assert remote.isForecast is True
	assert remote.isTimeseries is True
	assert remote.isRealtimeApproximate is True
	assert remote.isDaily is False


def test_relay_pushes_title_and_metadata():
	bridge = make_bridge()
	source = RemoteSource(name='TestPlugin')
	key = CategoryItem('environment.humidity.humidity')
	container = FakeContainer(wu.Humidity.Humidity(55), title='Humidity')

	remote = bridge._relay(source, key, container)

	assert remote.title == 'Humidity'
	assert remote.metadata.get('title') == 'Humidity'


def test_relay_preserves_timestamp():
	bridge = make_bridge()
	source = RemoteSource(name='TestPlugin')
	key = CategoryItem('environment.temperature.temperature')
	ts = datetime(2026, 7, 12, 9, 0, tzinfo=timezone.utc)
	container = FakeContainer(wu.Temperature.Fahrenheit(70), timestamp=ts)

	remote = bridge._relay(source, key, container)

	assert remote.value.timestamp == ts


def test_relay_resolves_icon_alias_instead_of_pushing_the_icon_object():
	# Icon objects carry a QFont and aren't wire-safe - the bridge must push
	# the alias string, not container.value.value, for icon-type keys.
	class FakeIconMetadata(dict):
		def mapAlias(self, raw):
			return {0: 'clear-day', 1: 'rain'}.get(raw, 'unknown')

	bridge = make_bridge()
	source = RemoteSource(name='TestPlugin')
	key = CategoryItem('environment.condition.icon')
	metadata = FakeIconMetadata(type='icon', iconType='glyph', title='Condition Icon')
	container = FakeContainer(None, metadata=metadata, isRealtime=True)
	container.value.rawValue = 0  # the raw weathercode the alias maps from

	remote = bridge._relay(source, key, container)

	# The RemoteObservationValue resolves the icon lazily via getIcon() -
	# just confirm the alias made it across and no Icon/QFont object was
	# ever handed to the codec.
	assert remote.value._icon_alias == 'clear-day'


def test_remote_container_is_a_drop_in_for_multisourcecontainer_reconciliation():
	# The actual point of 4.1: MultiSourceContainer's reconciliation runs
	# completely unmodified against a RemoteContainer.
	key = CategoryItem('environment.temperature.temperature')
	source = RemoteSource(name='OpenMeteo', defaultFor={'temperature'})
	remote = source.getOrCreate(key)
	remote._update(
		value=wu.Temperature.Fahrenheit(68),
		flags=ContainerFlags(isRealtime=True),
		title='Temperature',
	)

	multi = MultiSourceContainer(key)
	multi.addValue(source, remote)

	assert multi.value is remote
	assert multi['OpenMeteo'] is remote
	assert multi.isRealtime is True
	assert float(multi.value.value.value) == 68


def test_remote_container_channel_fires_on_update():
	# ChannelSignal.connectSlot requires a bound method (it keys its
	# connection registry on slot.__self__ - see utils.py) - matches how
	# every real caller connects (self.updateSlot, self.publish, never a
	# bare lambda), so the receiver here mirrors that shape.
	#
	# ChannelSignal._emit (utils.py) emits its live `_pending` set, then
	# clears that *same* set object immediately after - real consumers only
	# ever use the emission as a change trigger and re-read fresh container
	# state (see the widget-surface inventory), never retain the emitted
	# set past the synchronous callback, so this copies inside the slot to
	# match that usage rather than tripping the clear-after-emit aliasing.
	class Receiver:
		def __init__(self):
			self.received = []

		def on_update(self, observations):
			self.received.append(set(observations))

	key = CategoryItem('environment.temperature.temperature')
	source = RemoteSource(name='OpenMeteo')
	remote = source.getOrCreate(key)

	receiver = Receiver()
	remote.channel.connectSlot(receiver.on_update)

	remote._update(value=wu.Temperature.Fahrenheit(70), flags=ContainerFlags(isRealtime=True))

	assert len(receiver.received) == 1
	assert remote in receiver.received[0]


def test_multisourcechannel_relay_fires_through_remote_container_update():
	# Exercises the actual signal-plumbing loop described in containers.py's
	# module docstring: RemoteContainer publishes itself as its own
	# "observation", RemoteSource.__getitem__ resolves it back, and
	# MultiSourceChannel's listener fires.
	key = CategoryItem('environment.temperature.temperature')
	source = RemoteSource(name='OpenMeteo')
	remote = source.getOrCreate(key)

	multi = MultiSourceContainer(key)
	multi.relay.listen_to_container(remote)

	fired = []
	multi.relay._signal.connect(lambda c: fired.append(c))

	remote._update(value=wu.Temperature.Fahrenheit(72), flags=ContainerFlags(isRealtime=True))

	assert fired == [multi]


def test_remote_observation_value_source_matches_realtime_flag():
	# Realtime.py's stale-label logic (and its tooltip) read value.source:
	# isinstance(RealtimeSource) picks the staleness threshold, .period is
	# the threshold for polled sources. The stand-in must mirror both.
	key = CategoryItem('environment.temperature.temperature')
	source = RemoteSource(name='Govee')
	remote = source.getOrCreate(key)

	remote._update(value=wu.Temperature.Fahrenheit(70), flags=ContainerFlags(isRealtime=True))
	streaming = remote.value.source
	assert isinstance(streaming, RealtimeSource)
	assert streaming.name == 'Govee'

	remote._update(value=wu.Temperature.Fahrenheit(71), flags=ContainerFlags(isRealtime=False))
	polled = remote.value.source
	assert not isinstance(polled, RealtimeSource)
	assert polled.period == timedelta(minutes=15)


def test_remote_source_plugin_surface():
	# MultiSourceContainer's reconciliation fallbacks and the status bar's
	# value path (app.py StatusBarItem.value -> container.realtime) read
	# source.hasRealtimeFor/hasTimeseriesFor/.hourly/.daily - RemoteSource
	# must provide them (their absence crashed mode=remote's real GUI).
	key = CategoryItem('indoor.temperature.temperature')
	source = RemoteSource(name='Govee')
	assert source.hasRealtimeFor(key) is False  # no container yet

	remote = source.getOrCreate(key)
	assert source.hasRealtimeFor(key) is False  # container, no realtime flag
	remote._update(value=wu.Temperature.Fahrenheit(70), flags=ContainerFlags(isRealtime=True))
	assert source.hasRealtimeFor(key) is True
	assert source.hasTimeseriesFor(key) is False
	assert source.hasDailyFor(key) is False
	assert source.hourly is None
	assert source.daily is None


def test_multisource_container_realtime_via_remote_source():
	# The exact dispatcher.py:141 path from the menubar crash log.
	key = CategoryItem('environment.temperature.temperature')
	multi = MultiSourceContainer(key)
	source = RemoteSource(name='OpenMeteo')
	remote = source.getOrCreate(key)
	remote._update(value=wu.Temperature.Fahrenheit(74), flags=ContainerFlags(isRealtime=True, isTimeseriesOnly=False))
	multi.addValue(source, remote)
	assert multi.realtime is remote.value


def test_get_preferred_source_short_circuits_when_data_already_present():
	# mode=remote race: a replayed snapshot lands before panels register
	# their waits; getPreferredSourceContainer must fire immediately instead
	# of holding the request until the next publish.
	from LevityDash.lib.plugins.plugin import AnySource
	key = CategoryItem('environment.temperature.temperature')
	multi = MultiSourceContainer(key)
	source = RemoteSource(name='OpenMeteo')
	remote = source.getOrCreate(key)
	remote._update(
		value=wu.Temperature.Fahrenheit(74),
		flags=ContainerFlags(isRealtimeApproximate=True, isTimeseriesOnly=True),
	)
	multi.addValue(source, remote)

	fired = []
	multi.getPreferredSourceContainer('requester', AnySource, lambda: fired.append(True), timeseriesOnly=False)
	assert fired == [True]  # isTimeseriesOnly -> prepare_for_ts_connection fires synchronously

	# with no qualifying container, the request queues instead of firing
	multi2 = MultiSourceContainer(CategoryItem('environment.wind.speed.speed'))
	fired2 = []
	multi2.getPreferredSourceContainer('requester', AnySource, lambda: fired2.append(True), timeseriesOnly=False)
	assert fired2 == []


def test_get_timeseries_ignores_a_forecast_flagged_container_before_data_is_fetched():
	# Regression guard for a real bug caught only by running the actual app
	# (not by static review or unit tests against stubs): getTimeseries used
	# to hand back any container whose flags looked forecast-ready, which is
	# always safe for a live Container (`.timeseries` is a cached_property
	# that never returns None - the first access always builds a, possibly
	# still-empty, MeasurementTimeSeries; real population happens lazily via
	# .list). A RemoteContainer's `.timeseries` stays None until an explicit
	# wire fetch (prepare_for_ts_connection) completes - so returning it here
	# let GraphItemData.setContainer call connectTimeseries directly on a
	# container with no data, WITHOUT ever having gone through
	# getPreferredSourceContainer (the only thing that actually calls
	# prepare_for_ts_connection). Graphs in mode=remote stayed permanently
	# empty as a result, even once the backend genuinely had data.
	key = CategoryItem('environment.temperature.temperature')
	multi = MultiSourceContainer(key)
	source = RemoteSource(name='OpenMeteo', defaultFor={'temperature'})
	remote = source.getOrCreate(key)
	remote._update(
		value=wu.Temperature.Fahrenheit(70),
		flags=ContainerFlags(isForecast=True, isTimeseriesOnly=True),
	)
	multi.addValue(source, remote)

	assert remote.timeseries is None  # not fetched yet - the crux of the bug
	assert multi.getTimeseries(source, strict=True) is None
	assert multi.getTimeseries(strict=True) is None  # the AnySource/fallback path too

	# once prepare_for_ts_connection (or in this test, direct assignment)
	# populates it, the same container becomes a valid result again
	remote._timeseries = RemoteTimeSeries(source, key, [TimeSeriesItem.load_raw(70.0, datetime(2026, 7, 22, tzinfo=timezone.utc))])
	assert multi.getTimeseries(source, strict=True) is remote
	assert multi.getTimeseries(strict=True) is remote


def test_prepare_for_ts_connection_uses_default_period_without_a_requester_hint():
	# A requester with no wireTimeseriesPeriod attribute (the common case,
	# and every requester before this feature existed) falls back to the
	# fixed default window.
	key = CategoryItem('environment.temperature.temperature')
	source = RemoteSource(name='OpenMeteo')
	remote = source.getOrCreate(key)

	captured = []
	source._ts_request_fn = lambda message, on_response: captured.append(message)

	request = Request(requester=object(), callback=lambda: None)
	remote.prepare_for_ts_connection(request)

	assert len(captured) == 1
	assert captured[0]['minPeriod'] == timedelta(hours=-3).total_seconds()
	assert captured[0]['maxPeriod'] == timedelta(hours=3).total_seconds()


def test_prepare_for_ts_connection_honors_requester_wire_timeseries_period():
	# The actual point of this feature: a requester (Graph.py's
	# GraphItemData in real usage) can expose .wireTimeseriesPeriod to get a
	# fetch matching its own configured timeframe instead of the default.
	key = CategoryItem('environment.temperature.temperature')
	source = RemoteSource(name='OpenMeteo')
	remote = source.getOrCreate(key)

	captured = []
	source._ts_request_fn = lambda message, on_response: captured.append(message)

	class FakeGraphItemData:
		wireTimeseriesPeriod = (timedelta(hours=-18), timedelta(hours=24))

	request = Request(requester=FakeGraphItemData(), callback=lambda: None)
	remote.prepare_for_ts_connection(request)

	assert len(captured) == 1
	assert captured[0]['minPeriod'] == timedelta(hours=-18).total_seconds()
	assert captured[0]['maxPeriod'] == timedelta(hours=24).total_seconds()


def test_prepare_for_ts_connection_degrades_to_default_on_malformed_period_hint():
	# A requester providing garbage for wireTimeseriesPeriod must not crash
	# the request - degrade to the default window instead.
	key = CategoryItem('environment.temperature.temperature')
	source = RemoteSource(name='OpenMeteo')
	remote = source.getOrCreate(key)

	captured = []
	source._ts_request_fn = lambda message, on_response: captured.append(message)

	class BadGraphItemData:
		wireTimeseriesPeriod = 'not a tuple'

	request = Request(requester=BadGraphItemData(), callback=lambda: None)
	remote.prepare_for_ts_connection(request)  # must not raise

	assert len(captured) == 1
	assert captured[0]['minPeriod'] == timedelta(hours=-3).total_seconds()
	assert captured[0]['maxPeriod'] == timedelta(hours=3).total_seconds()


def test_prepare_for_ts_connection_still_fires_callback_and_populates_timeseries():
	# The period-resolution addition must not disturb the existing
	# request/response flow: response arrives -> _timeseries populated ->
	# callback fires.
	key = CategoryItem('environment.temperature.temperature')
	source = RemoteSource(name='OpenMeteo')
	remote = source.getOrCreate(key)

	from LevityDash.lib.wire.messages import encode_ts_response

	def fake_ts_request_fn(message, on_response):
		items = [TimeSeriesItem.load_raw(72.0, datetime(2026, 7, 22, tzinfo=timezone.utc))]
		on_response(encode_ts_response(request_id=message['id'], source='OpenMeteo', key=message['key'], ok=True, items=items))

	source._ts_request_fn = fake_ts_request_fn

	class FakeGraphItemData:
		wireTimeseriesPeriod = (timedelta(hours=-18), timedelta(hours=24))

	fired = []
	request = Request(requester=FakeGraphItemData(), callback=lambda: fired.append(True))
	remote.prepare_for_ts_connection(request)

	assert fired == [True]
	assert remote.timeseries is not None
	assert len(remote.timeseries) == 1


def test_getPreferredSourceContainer_ranks_by_defaultFor():
	"""AnySource must honour `defaultFor`, not insertion order.

	`getTimeseries`/`getRealtimeContainer`/`getDaily` all rank candidates by
	`len(source.config.defaultFor)`, but `getPreferredSourceContainer` - the
	one path Graph.py actually calls - iterated `self.values()` and took the
	first ready container. So a graph could render a source the user had
	explicitly cleared from `defaultFor` while the other three accessors
	disagreed, and no amount of config would change it.

	Observes the real choice: with isTimeseriesOnly set, the function calls
	`prepare_for_ts_connection` on whichever container it picked. The weak
	source is registered FIRST, so insertion order and the correct answer
	are in conflict.
	"""
	key = CategoryItem('environment.temperature.temperature')
	flags = ContainerFlags(isForecast=True, isTimeseries=True, isTimeseriesOnly=True)

	weak = RemoteSource(name='PirateWeather', defaultFor=set())
	strong = RemoteSource(name='OpenMeteo', defaultFor={'temperature', 'precipitation', 'wind'})

	multi = MultiSourceContainer(key)
	picked = []
	for src in (weak, strong):                       # weak first, deliberately
		container = src.getOrCreate(key)
		container._flags = flags
		container.prepare_for_ts_connection = (
			lambda request, _name=src.name: picked.append(_name)
		)
		multi[src.name] = container

	multi.getPreferredSourceContainer(
		requester=object(), plugin=AnySource,
		callback=lambda: None, timeseriesOnly=True,
	)

	assert picked == ['OpenMeteo'], (
		f'picked {picked}; PirateWeather was registered first, so insertion '
		f'order would have chosen it'
	)
