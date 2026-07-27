#!/usr/bin/env python
"""Dev-only: scan for BLE devices and report what they advertise.

Never imported by the shipped app. Two uses:

1. **Find a Govee thermometer's advertised name** — the identity a
   multi-device config keys off (see docs/tasks/govee-multi-device.md). The
   name is model + last 4 of the MAC, e.g. ``GVH5102_6736``.
2. **Check whether this host can do BLE at all.** Deliberately imports only
   ``bleak``, no LevityDash — so a TCC kill shows up here as a bare exit 134
   rather than taking a whole dashboard boot down with it.

⚠️ macOS: a host whose bundle lacks ``NSBluetoothAlwaysUsageDescription`` is
killed with SIGABRT and prints **nothing at all** — this is not a missing
permission grant and toggling System Settings will not fix it. See CLAUDE.md's
Bluetooth gotcha. Run from a terminal that ships the key (iTerm does).

Usage:
    poetry run python src/LevityDash/devtools/ble_scan.py [seconds]
"""
import asyncio
import sys

from bleak import BleakScanner

#: Govee advertises this service and packs its readings into manufacturer_data[1].
GOVEE_SERVICE = 'ec88'
GOVEE_MANUFACTURER_ID = 1


async def scan(seconds: float) -> dict:
	found = {}

	def seen(device, adv):
		prev = found.get(device.address) or {}
		# name and manufacturer data can arrive in different packets (scan
		# response vs advertisement), so merge rather than overwrite
		found[device.address] = {
			'name': device.name or prev.get('name'),
			'rssi': adv.rssi,
			'mfg': {**(prev.get('mfg') or {}), **dict(adv.manufacturer_data)},
			'svc': sorted(set((prev.get('svc') or []) + list(adv.service_uuids))),
		}

	scanner = BleakScanner(detection_callback=seen)
	await scanner.start()
	try:
		await asyncio.sleep(seconds)
	finally:
		await scanner.stop()
	return found


def is_govee(entry: dict) -> bool:
	return (
		GOVEE_SERVICE in ' '.join(entry['svc']).lower()
		or GOVEE_MANUFACTURER_ID in entry['mfg']
		or (entry['name'] or '').upper().startswith(('GV', 'GOVEE'))
	)


def main() -> int:
	seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 15.0
	found = asyncio.run(scan(seconds))

	print(f'--- {len(found)} device(s) over {seconds:g}s ---')
	for address, entry in sorted(found.items(), key=lambda kv: -kv[1]['rssi']):
		govee = is_govee(entry)
		marker = '>>> GOVEE  ' if govee else '           '
		print(f"{marker}{address}  rssi={entry['rssi']:>4}  name={entry['name']!r}  mfg={list(entry['mfg'])}")
		if govee:
			for ident, payload in entry['mfg'].items():
				print(f'             mfg[{ident}] = {payload.hex()}  ({len(payload)} bytes)')
			for uuid in entry['svc']:
				print(f'             svc uuid: {uuid}')

	if not any(is_govee(entry) for entry in found.values()):
		print('\nNo Govee device seen. If a thermometer is powered on and nearby it may')
		print('simply not have advertised within the window — try a longer scan.')
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
