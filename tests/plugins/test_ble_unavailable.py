import asyncio
import logging
from types import SimpleNamespace

import pytest

from LevityDash.lib.plugins import ble
from LevityDash.lib.plugins.ble import BLEPlugin, BluetoothUnavailable, SharedScanner, explainScanFailure
from LevityDash.lib.plugins.web.reconnect import Backoff


@pytest.mark.parametrize('error, expected', [
	(FileNotFoundError(2, 'No such file or directory'), 'no Bluetooth adapter'),
	(Exception('No Bluetooth adapters found.'), 'no Bluetooth adapter'),
	(PermissionError('denied'), 'permission'),
	(Exception('Bluetooth device is turned off'), 'turned off'),
	(Exception('something odd'), 'something odd'),
])
def test_scan_failures_get_a_plain_reason(error, expected):
	assert expected in explainScanFailure(error)


class FakeScanner:
	failures = []  # errors to raise, one per start()

	def __init__(self, detection_callback=None, **kwargs):
		pass

	async def start(self):
		if FakeScanner.failures:
			raise FakeScanner.failures.pop(0)

	async def stop(self):
		pass


class Radio(BLEPlugin):
	name = 'Radio'
	pluginLog = logging.getLogger('test.ble')

	def wants(self, device, data):
		return True

	def handleAdvertisement(self, device, data):
		pass


@pytest.fixture
def scanner(monkeypatch):
	import bleak
	monkeypatch.setattr(bleak, 'BleakScanner', FakeScanner)
	fresh = SharedScanner()
	monkeypatch.setattr(ble, 'shared_scanner', fresh)
	return fresh


def test_start_without_an_adapter_raises_a_plain_reason(scanner):
	FakeScanner.failures = [FileNotFoundError(2, 'No such file or directory')]
	with pytest.raises(BluetoothUnavailable, match='no Bluetooth adapter'):
		asyncio.run(scanner.start())


def test_plugin_stays_up_without_bluetooth_and_scans_once_it_appears(scanner):
	FakeScanner.failures = [PermissionError('x'), Exception('Bluetooth device is turned off')]

	async def main():
		plugin = object.__new__(Radio)
		await plugin.onStart()
		assert 'permission' in plugin.bluetoothProblem
		plugin._scanRetry.cancel()  # the real retry waits 30s; drive it with a short one
		await plugin._retryScan(Backoff(initial=0.01, maximum=0.01))
		assert plugin.bluetoothProblem is None
		assert scanner.running
		await plugin.onStop()

	asyncio.run(main())
