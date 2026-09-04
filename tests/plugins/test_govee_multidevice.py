"""Two Govee devices, live at once, through a stop/start cycle.

The property the rewrite exists to guarantee: N thermometers each get their
own ``Plugin`` instance, their own parsers, and their own keys, and no
device's data can land on another's instance.

Live BLE cannot run here - macOS SIGABRTs a process touching Bluetooth without
``NSBluetoothAlwaysUsageDescription``, which a pytest run does not have. So
these drive the routing seam (``SharedScanner.dispatch``) with stand-in device
objects carrying real captured payloads. Everything below the radio is the
production path: real presets, real config parsing, real ``BLEPayloadParser``,
real subscribe/unsubscribe.
"""
import asyncio
import time

import pytest

from LevityDash.lib.plugins.ble import LifecyclePlugin, SharedScanner
from LevityDash.lib.plugins.builtin.Govee import BLEPayloadParser, Govee
from LevityDash.lib.plugins.govee.config import parse_devices
from LevityDash.lib.plugins.govee.models import detect_model, preset_for, trim_payload

# Real GVH5102 advertisements (same captures as test_govee.py).
TERRARIUM = {
	'name': 'GVH5102_527D',
	'address': '76270FCE-FFB6-E857-54B3-48FA6B868D48',
	'payload': bytes.fromhex('0101038cb2604c000215494e54454c4c495f524f434b535f48575075f2ff0c'),
	'temperature': 23.2626,
	'battery': 96,
}
ROOM = {
	'name': 'GVH5102_6736',
	'address': '3A092DB0-D44A-91AC-6C1B-4C9C11A8A7A4',
	'payload': bytes.fromhex('0101036cdd534c000215494e54454c4c495f524f434b535f48575075f2ffc2'),
	'temperature': 22.4477,
	'battery': 83,
}


class FakeDevice:
	"""Stands in for a ``BLEDevice``: the two attributes routing reads."""

	def __init__(self, spec):
		self.name = spec['name']
		self.address = spec['address']


class FakeAdvertisement:
	"""Stands in for ``AdvertisementData``."""

	def __init__(self, spec, rssi=-60):
		self.manufacturer_data = {1: spec['payload']}
		self.rssi = rssi
		self.local_name = spec['name']


class FakeConfig(dict):
	def sections(self):
		return [k for k in self if k != 'plugin']


TWO_DEVICES = FakeConfig({
	'plugin': {'enabled': 'True'},
	'devices': {'bedroom': ROOM['name'], 'terrarium': TERRARIUM['name']},
})


# --- config -----------------------------------------------------------------

class TestReadableConfig:

	def test_devices_block_is_all_a_known_model_needs(self):
		devices = {d.alias: d for d in parse_devices(TWO_DEVICES)}
		assert set(devices) == {'bedroom', 'terrarium'}
		# No byte offsets were configured, yet parsers are fully specified.
		assert devices['bedroom'].preset.model == 'H5102'
		assert devices['bedroom'].fields['temperature']['startingByte'] == 4
		assert devices['bedroom'].modelPinned is False

	def test_sections_and_short_form_can_be_mixed(self):
		config = FakeConfig({
			'plugin': {},
			'devices': {'bedroom': ROOM['name']},
			'device:garage': {'name': 'GVH5075_A1B2', 'model': 'H5075'},
		})
		devices = {d.alias: d for d in parse_devices(config)}
		assert set(devices) == {'bedroom', 'garage'}
		assert devices['garage'].preset.model == 'H5075'
		assert devices['garage'].modelPinned is True

	def test_a_section_overrides_only_the_field_it_names(self):
		config = FakeConfig({
			'plugin': {},
			'device:odd': {'name': 'GVH5102_9999', 'temperature.expression': 'val / 1000'},
		})
		device = parse_devices(config)[0]
		# Overridden expression, but the preset's slice survives.
		assert device.fields['temperature']['expression'] == 'val / 1000'
		assert device.fields['temperature']['startingByte'] == 4
		assert device.fields['humidity']['expression'] == 'payload % 1000 / 1000'

	def test_legacy_fallback_does_not_double_register(self):
		# The [plugin] device.name must not add a *second* copy of a device
		# already declared in [devices] - one physical sensor, one instance.
		config = FakeConfig({
			'plugin': {'device.name': ROOM['name']},
			'devices': {'bedroom': ROOM['name']},
		})
		devices = parse_devices(config)
		assert [d.alias for d in devices] == ['bedroom']

	def test_legacy_alone_still_works(self):
		config = FakeConfig({'plugin': {'device.name': ROOM['name']}})
		devices = parse_devices(config)
		assert [d.alias for d in devices] == [ROOM['name']]


class TestModelPresets:

	def test_detects_the_tested_hardware(self):
		assert detect_model('GVH5102_6736').model == 'H5102'
		assert detect_model('GVH5075_A1B2').model == 'H5075'

	def test_unknown_model_falls_back_rather_than_failing(self):
		assert detect_model('GVH9999_ZZZZ') is None
		assert preset_for(advertisedName='GVH9999_ZZZZ').model == 'H5102'

	def test_explicit_model_beats_detection(self):
		assert preset_for(model='H5075', advertisedName='GVH5102_6736').model == 'H5075'

	def test_intelli_rocks_tail_is_stripped(self):
		# Both real captures carry it; upstream strips 25 bytes.
		assert len(ROOM['payload']) == 31
		assert len(trim_payload(ROOM['payload'])) == 6

	def test_preset_slices_decode_the_real_captures(self):
		preset = preset_for(advertisedName=ROOM['name'])
		parser = BLEPayloadParser(field='temperature', **preset.fields['temperature'])
		assert parser(ROOM['payload'])['temperature'] == pytest.approx(ROOM['temperature'], abs=1e-4)


# --- routing ----------------------------------------------------------------

class TestScannerRouting:

	def test_each_device_receives_only_its_own_advertisements(self):
		scanner = SharedScanner()
		received = {'bedroom': [], 'terrarium': []}

		for alias, spec in (('bedroom', ROOM), ('terrarium', TERRARIUM)):
			scanner.subscribe(
				alias,
				(lambda s: lambda d, _: d.name == s['name'])(spec),
				(lambda a: lambda d, _: received[a].append(d.name))(alias),
			)

		for spec in (ROOM, TERRARIUM, ROOM):
			scanner.dispatch(FakeDevice(spec), FakeAdvertisement(spec))

		assert received['bedroom'] == [ROOM['name'], ROOM['name']]
		assert received['terrarium'] == [TERRARIUM['name']]

	def test_an_unknown_device_reaches_nobody(self):
		scanner = SharedScanner()
		scanner.subscribe('bedroom', lambda d, _: d.name == ROOM['name'], lambda d, _: None)
		stranger = FakeDevice({'name': 'SomeOtherThing', 'address': '00'})
		assert scanner.dispatch(stranger, FakeAdvertisement(ROOM)) == 0

	def test_one_handler_raising_does_not_starve_the_others(self):
		# A malformed payload from one thermometer must not stop the other
		# from updating - they are independent devices.
		scanner = SharedScanner()
		seen = []
		scanner.subscribe('bad', lambda d, _: True, lambda d, _: (_ for _ in ()).throw(ValueError('boom')))
		scanner.subscribe('good', lambda d, _: True, lambda d, _: seen.append(d.name))
		assert scanner.dispatch(FakeDevice(ROOM), FakeAdvertisement(ROOM)) == 2
		assert seen == [ROOM['name']]

	def test_unsubscribing_one_device_leaves_the_other_scanning(self):
		scanner = SharedScanner()
		seen = []
		scanner.subscribe('bedroom', lambda d, _: True, lambda d, _: seen.append('bedroom'))
		scanner.subscribe('terrarium', lambda d, _: True, lambda d, _: seen.append('terrarium'))
		scanner.unsubscribe('bedroom')
		scanner.dispatch(FakeDevice(ROOM), FakeAdvertisement(ROOM))
		assert seen == ['terrarium']
		assert scanner.subscribers == {'terrarium'}


# --- per-device plugin instances --------------------------------------------

def _instances():
	"""Two real ``Govee`` instances from config, without the plugin loader."""
	return [Govee(device) for device in parse_devices(TWO_DEVICES)]


class TestPerDeviceInstances:

	def test_each_device_is_its_own_named_source(self):
		names = {i.name for i in _instances()}
		assert names == {'Govee-bedroom', 'Govee-terrarium'}

	def test_instances_claim_only_their_own_device(self):
		bedroom, terrarium = _instances()
		assert bedroom.wants(FakeDevice(ROOM), FakeAdvertisement(ROOM))
		assert not bedroom.wants(FakeDevice(TERRARIUM), FakeAdvertisement(TERRARIUM))
		assert terrarium.wants(FakeDevice(TERRARIUM), FakeAdvertisement(TERRARIUM))
		assert not terrarium.wants(FakeDevice(ROOM), FakeAdvertisement(ROOM))

	def test_each_instance_holds_its_own_parsers(self):
		# The pre-rewrite bug: one shared parser set, so whichever device
		# reported last decided how the other's bytes were read.
		bedroom, terrarium = _instances()
		assert bedroom._Govee__parsers is not terrarium._Govee__parsers

	def test_both_devices_decode_simultaneously_and_differently(self):
		bedroom, terrarium = _instances()
		results = {}
		for instance, spec in ((bedroom, ROOM), (terrarium, TERRARIUM)):
			parsers = instance._Govee__parsers
			payload = trim_payload(spec['payload'])
			values = {}
			for field, parser in parsers.items():
				values.update(parser(payload))
			results[instance.name] = values

		assert results['Govee-bedroom']['temperature'] == pytest.approx(ROOM['temperature'], abs=1e-4)
		assert results['Govee-terrarium']['temperature'] == pytest.approx(TERRARIUM['temperature'], abs=1e-4)
		assert results['Govee-bedroom']['battery'] == ROOM['battery']
		assert results['Govee-terrarium']['battery'] == TERRARIUM['battery']
		assert results['Govee-bedroom'] != results['Govee-terrarium']

	def test_identity_is_the_alias_not_the_advertised_name(self):
		bedroom = _instances()[0]
		assert bedroom.device.alias == 'bedroom'
		assert bedroom.device.name == ROOM['name']

	def test_name_is_answerable_before_init_runs(self):
		# __instances__ builds a bare probe (object.__new__, no __init__) to
		# read the config, and PluginConfig.__getitem__ asks for plugin.name
		# on every section miss. An instance-only __name made that raise
		# AttributeError, so the plugin failed to load entirely:
		#   'Govee' object has no attribute '_Govee__name'
		# Caught only in a real GUI run - the unit tests all constructed
		# instances normally, and the config dry-run passed a raw ConfigParser
		# rather than a PluginConfig, so neither reached this path.
		probe = object.__new__(Govee)
		assert probe.name == 'Govee'

	def test_instances_are_built_from_a_real_plugin_config(self):
		# Drives the actual loader path end to end (getConfig -> PluginConfig
		# -> parse_devices), not a hand-made config stand-in.
		instances = Govee.__instances__()
		for instance in instances:
			assert instance.name.startswith('Govee-')
			assert instance.device is not None


# --- lifecycle --------------------------------------------------------------

class _CountingPlugin(LifecyclePlugin):
	"""Minimal LifecyclePlugin - no BLE, no config, just the state machine."""

	name = 'Counting'
	schema = {
		'timestamp': {'type': 'datetime', 'sourceUnit': 'epoch', 'title': 'Time', 'sourceKey': 'timestamp'},
	}
	__defaultConfig__ = '[plugin]\nenabled = True\n'

	def __init__(self):
		self.starts = 0
		self.stops = 0
		super().__init__()

	async def onStart(self):
		self.starts += 1

	async def onStop(self):
		self.stops += 1


class TestLifecycleRestart:
	"""A stopped plugin must be able to start again.

	This is the bug the base class exists to prevent: ``future`` is a
	``cached_property``, so a bootstrap that deletes ``loop`` but not
	``future`` leaves a *resolved* Future cached. The next ``start()`` then
	awaits an already-done Future, returns instantly, and the plugin shuts
	itself down the moment it comes up - permanently, for the life of the
	process. The control plane's stop/start/restart hits this immediately.

	These drive the real ``start()``/``stop()``, not a hand-written imitation
	of them: a test that simulates teardown itself still passes when the
	teardown it is meant to guard is deleted (verified by mutation).
	"""

	@staticmethod
	def _waitFor(predicate, timeout=5.0):
		"""Wait for a background bootstrap thread to reach a state."""
		deadline = time.monotonic() + timeout
		while time.monotonic() < deadline:
			if predicate():
				return True
			time.sleep(0.01)
		return False

	def test_a_plugin_can_be_started_stopped_and_started_again(self):
		plugin = _CountingPlugin()

		plugin.start()
		assert self._waitFor(lambda: plugin.running), 'never came up'
		assert plugin.starts == 1
		firstLoop = plugin.loop

		plugin.stop()
		assert self._waitFor(lambda: not plugin.running), 'never shut down'
		# The bootstrap thread resets loop/future after the await returns.
		assert self._waitFor(lambda: plugin.loop is not firstLoop), 'loop was never reset'

		# The real assertion: a second start must actually run.
		plugin.start()
		assert self._waitFor(lambda: plugin.running), (
			'restart failed - a stopped plugin could not start again. This is '
			'the resolved-cached-future bug: check that the bootstrap deletes '
			'BOTH loop and future.'
		)
		assert plugin.starts == 2
		assert plugin.stops == 1

		plugin.stop()
		self._waitFor(lambda: not plugin.running)

	def test_restart_gets_an_unresolved_future(self):
		plugin = _CountingPlugin()
		plugin.start()
		assert self._waitFor(lambda: plugin.running)
		firstFuture = plugin.future

		plugin.stop()
		assert self._waitFor(lambda: not plugin.running)
		assert self._waitFor(lambda: plugin.future is not firstFuture), 'future was not reset'
		assert not plugin.future.done(), 'a resolved future survived shutdown'

	def test_start_is_idempotent_while_running(self):
		plugin = _CountingPlugin()
		plugin.start()
		assert self._waitFor(lambda: plugin.running)
		plugin.start()  # must not spawn a second loop
		time.sleep(0.05)
		assert plugin.starts == 1
		plugin.stop()
		self._waitFor(lambda: not plugin.running)

	def test_stop_on_a_stopped_plugin_is_a_no_op(self):
		plugin = _CountingPlugin()
		plugin.stop()  # must not raise
		assert plugin.stops == 0


class TestSharedScannerLifecycle:

	def test_scanner_stops_only_after_the_last_device_leaves(self):
		# One device stopping must not blind the others - the failure mode
		# that made a per-device scanner design unworkable.
		scanner = SharedScanner()
		scanner.subscribe('bedroom', lambda d, _: True, lambda d, _: None)
		scanner.subscribe('terrarium', lambda d, _: True, lambda d, _: None)

		class FakeScanner:
			stopped = False

			async def stop(self):
				FakeScanner.stopped = True

		scanner._scanner = FakeScanner()

		scanner.unsubscribe('bedroom')
		asyncio.run(scanner.stop())
		assert FakeScanner.stopped is False, 'stopped while a device was still subscribed'

		scanner.unsubscribe('terrarium')
		asyncio.run(scanner.stop())
		assert FakeScanner.stopped is True

	def test_dispatch_is_safe_when_a_handler_unsubscribes_mid_scan(self):
		scanner = SharedScanner()
		scanner.subscribe('a', lambda d, _: True, lambda d, _: scanner.unsubscribe('b'))
		scanner.subscribe('b', lambda d, _: True, lambda d, _: None)
		scanner.dispatch(FakeDevice(ROOM), FakeAdvertisement(ROOM))
		assert scanner.subscribers == {'a'}
