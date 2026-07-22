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
from LevityDash.lib.plugins.dispatcher import MultiSourceContainer
from LevityDash.lib.plugins.observation import RealtimeSource
from LevityDash.lib.wire.bridge import LoopbackBridge
from LevityDash.lib.wire.containers import ContainerFlags, RemoteContainer, RemoteSource
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
