"""Tests for the Govee BLE plugin (lib/plugins/builtin/Govee.py).

Payloads below are **real advertisements** captured from two GVH5102
thermometers on 2026-07-27 (one in a terrarium, one in a room), not invented
bytes - so the decode assertions pin actual device behaviour.

Like test_openweathermap.py, this avoids bootstrapping a Plugin: BLEPayloadParser
is a standalone callable, and the identity resolution under test is a pure
function of config + advertised name.
"""
import pytest

from LevityDash.lib.plugins.builtin.Govee import BLEPayloadParser

# --- captured advertisements ------------------------------------------------
# manufacturer_data[1], service uuid 0000ec88-0000-1000-8000-00805f9b34fb.
# The address is a macOS-generated UUID, NOT a hardware MAC - macOS randomises
# these per machine, which is why identity anchors on the advertised name.
TERRARIUM = {
	'name': 'GVH5102_527D',
	'address': '76270FCE-FFB6-E857-54B3-48FA6B868D48',
	'payload': bytes.fromhex('0101038cb2604c000215494e54454c4c495f524f434b535f48575075f2ff0c'),
}
ROOM = {
	'name': 'GVH5102_6736',
	'address': '3A092DB0-D44A-91AC-6C1B-4C9C11A8A7A4',
	'payload': bytes.fromhex('0101036cdd534c000215494e54454c4c495f524f434b535f48575075f2ffc2'),
}

# The GVH5102 defaults from _defaultConfig / Govee.ini.
TEMPERATURE = BLEPayloadParser(field='temperature', startingByte=4, endingByte=10, expression='val / 10000')
HUMIDITY = BLEPayloadParser(field='humidity', startingByte=4, endingByte=10, expression='payload % 1000 / 1000')
BATTERY = BLEPayloadParser(field='battery', startingByte=10, endingByte=12)


class TestPayloadDecode:
	"""Pins the shipped GVH5102 slices/expressions against real captures."""

	def test_terrarium_decodes(self):
		assert TEMPERATURE(TERRARIUM['payload'])['temperature'] == pytest.approx(23.2626, abs=1e-4)
		assert HUMIDITY(TERRARIUM['payload'])['humidity'] == pytest.approx(0.626, abs=1e-3)
		assert BATTERY(TERRARIUM['payload'])['battery'] == 96

	def test_room_decodes(self):
		assert TEMPERATURE(ROOM['payload'])['temperature'] == pytest.approx(22.4477, abs=1e-4)
		assert HUMIDITY(ROOM['payload'])['humidity'] == pytest.approx(0.477, abs=1e-3)
		assert BATTERY(ROOM['payload'])['battery'] == 83

	def test_the_two_devices_really_do_differ(self):
		# Guards the fixtures themselves: if these ever coincide, the
		# multi-device tests below would pass vacuously.
		assert TEMPERATURE(TERRARIUM['payload']) != TEMPERATURE(ROOM['payload'])
		assert HUMIDITY(TERRARIUM['payload']) != HUMIDITY(ROOM['payload'])
		assert TERRARIUM['name'] != ROOM['name']


# --- device identity --------------------------------------------------------

def test_device_identity_prefers_configured_alias():
	from LevityDash.lib.plugins.builtin.Govee import resolve_device_identity

	devices = {'bedroom': {'name': 'GVH5102_6736'}, 'terrarium': {'name': 'GVH5102_527D'}}
	assert resolve_device_identity(ROOM['name'], devices) == 'bedroom'
	assert resolve_device_identity(TERRARIUM['name'], devices) == 'terrarium'


def test_device_identity_falls_back_to_advertised_name():
	# Two thermometers must work out of the box; aliasing is a readability
	# upgrade, not a requirement.
	from LevityDash.lib.plugins.builtin.Govee import resolve_device_identity

	assert resolve_device_identity(ROOM['name'], {}) == 'GVH5102_6736'


def test_keys_carry_the_device_identity():
	from LevityDash.lib.plugins.builtin.Govee import resolve_device_identity, device_scoped_key

	key = device_scoped_key('indoor.temperature.temperature', resolve_device_identity(ROOM['name'], {'bedroom': {'name': ROOM['name']}}))
	assert str(key) == 'indoor.temperature.temperature#bedroom'


class FakeConfig(dict):
	"""Minimal stand-in for the plugin config object: section access plus a
	`sections()` listing, which is all parse_device_sections reads."""

	def sections(self):
		return [k for k in self if k != 'plugin']


class TestDeviceSections:

	def test_reads_device_sections_keyed_by_alias(self):
		from LevityDash.lib.plugins.builtin.Govee import parse_device_sections

		config = FakeConfig({
			'plugin': {'enabled': 'True'},
			'device:bedroom': {'name': 'GVH5102_6736'},
			'device:terrarium': {'name': 'GVH5102_527D', 'address': TERRARIUM['address']},
		})
		devices = parse_device_sections(config)
		assert set(devices) == {'bedroom', 'terrarium'}
		assert devices['terrarium']['address'] == TERRARIUM['address']

	def test_ignores_unrelated_sections(self):
		from LevityDash.lib.plugins.builtin.Govee import parse_device_sections

		config = FakeConfig({'plugin': {}, 'logging': {'level': 'INFO'}, 'device:bedroom': {'name': 'x'}})
		assert set(parse_device_sections(config)) == {'bedroom'}

	def test_legacy_flat_config_still_yields_one_device(self):
		# The shipped single-device Govee.ini has no [device:*] sections at all;
		# it must keep working, aliased to its own advertised name.
		from LevityDash.lib.plugins.builtin.Govee import parse_device_sections, resolve_device_identity

		config = FakeConfig({'plugin': {'device.name': 'GVH5102_6736'}})
		devices = parse_device_sections(config)
		assert devices == {'GVH5102_6736': {'name': 'GVH5102_6736'}}
		assert resolve_device_identity('GVH5102_6736', devices) == 'GVH5102_6736'

	def test_two_devices_resolve_to_separate_keys(self):
		from LevityDash.lib.plugins.builtin.Govee import parse_device_sections, resolve_device_identity, device_scoped_key

		config = FakeConfig({
			'plugin': {},
			'device:bedroom': {'name': ROOM['name']},
			'device:terrarium': {'name': TERRARIUM['name']},
		})
		devices = parse_device_sections(config)
		keys = {
			device_scoped_key('indoor.temperature.temperature', resolve_device_identity(d['name'], devices))
			for d in (ROOM, TERRARIUM)
		}
		assert {str(k) for k in keys} == {
			'indoor.temperature.temperature#bedroom',
			'indoor.temperature.temperature#terrarium',
		}
		assert len(keys) == 2
