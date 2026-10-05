"""Made-up, slowly changing values for things that are not weather. Off by default.

The gauge showcase (``docs/design-references/gauge-showcase.levity``) shows
dials a weather feed cannot fill: a speedometer, a tachometer, CPU load, a heart
rate, a power meter that goes negative. This plugin publishes plausible values
for those, so a dashboard design has live data to move against.

**It is off until you turn it on.** The plugin always loads, and its config file
``Mock.ini`` starts with ``enabled = False``. To use it, set this in
``<config dir>/plugins/Mock.ini``:

	[plugin]
	enabled = True

Then restart. The values come from the plugin's own thread, so the same
plugin works in ``mode=live`` and in a headless backend that a remote frontend
connects to (``mode=remote``): the frontend gets them over the wire like any
other source.

The ``[Mock]`` section sets how often values change:

	[Mock]
	interval = 2

Every key is a base value plus a slow sine wave plus a little noise, so a dial
drifts instead of jumping. Keys, units and ranges are in ``MOCK_KEYS`` below.
"""
import asyncio
import math
import random
import time
from datetime import datetime
from typing import Dict

from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.plugins.ble import LifecyclePlugin
from LevityDash.lib.plugins.builtin.Fixture import buildSchema, _TIME_FORMAT
from LevityDash.lib.plugins.schema import LevityDatagram

log = LevityPluginLog.getChild('Mock')

#: ``key: {unit, base, swing, period, noise, min, max, title}``.
#: ``base`` is the middle value, ``swing`` the sine amplitude, ``period`` its
#: length in seconds and ``noise`` the random jitter. Values stay within ``min``..``max``.
MOCK_KEYS: Dict[str, dict] = {
	'system.cpu.usage':             dict(unit='%', base=38, swing=22, period=95, noise=4, min=2, max=99, title='CPU'),
	'system.memory.usage':          dict(unit='%', base=61, swing=8, period=300, noise=0.6, min=5, max=99, title='Memory'),
	'system.disk.usage':            dict(unit='%', base=72, swing=1.5, period=900, noise=0.1, min=5, max=99, title='Disk'),
	'system.cpu.temperature':       dict(unit='c', base=58, swing=14, period=110, noise=1.5, min=30, max=95, title='CPU temperature'),
	'system.network.down':          dict(unit='int', base=420, swing=380, period=47, noise=60, min=0, max=1000, title='Download'),
	'vehicle.speed.speed':          dict(unit='int', base=62, swing=38, period=70, noise=1.5, min=0, max=140, title='Speed'),
	'vehicle.engine.rpm':           dict(unit='int', base=3100, swing=2300, period=70, noise=80, min=700, max=7800, title='Engine speed'),
	'vehicle.engine.coolant':       dict(unit='c', base=92, swing=4, period=240, noise=0.4, min=60, max=120, title='Coolant'),
	'vehicle.fuel.level':           dict(unit='%', base=46, swing=40, period=1200, noise=0.2, min=3, max=100, title='Fuel'),
	'power.battery.level':          dict(unit='%', base=64, swing=30, period=1500, noise=0.2, min=2, max=100, title='Battery'),
	'power.grid.net':               dict(unit='int', base=150, swing=2400, period=130, noise=60, min=-3000, max=3000, title='Grid power'),
	'power.solar.output':           dict(unit='int', base=2400, swing=1800, period=210, noise=70, min=0, max=5000, title='Solar'),
	'health.heart.rate':            dict(unit='int', base=96, swing=46, period=85, noise=2.5, min=48, max=190, title='Heart rate'),
	'health.activity.move':         dict(unit='%', base=68, swing=24, period=1400, noise=0.1, min=0, max=100, title='Move'),
	'health.activity.exercise':     dict(unit='%', base=44, swing=24, period=1400, noise=0.1, min=0, max=100, title='Exercise'),
	'health.activity.stand':        dict(unit='%', base=80, swing=14, period=1400, noise=0.1, min=0, max=100, title='Stand'),
	'environment.airQuality.index': dict(unit='int', base=62, swing=48, period=260, noise=3, min=0, max=300, title='Air quality'),
	'home.thermostat.setpoint':     dict(unit='f', base=71, swing=0, period=1, noise=0, min=60, max=80, title='Setpoint'),
	'home.thermostat.temperature':  dict(unit='f', base=69.5, swing=2.5, period=420, noise=0.1, min=55, max=85, title='Room temperature'),
	'time.timer.seconds':           dict(unit='int', base=0, swing=0, period=60, noise=0, min=0, max=60, title='Timer'),
}


def mockValue(key: str, spec: dict, now: float, phase: float = 0.0) -> float:
	"""One key's value at ``now`` seconds. Pure, so a test can call it."""
	if key == 'time.timer.seconds':
		return round(now % spec['period'], 1)
	wave = spec['swing'] * math.sin(2 * math.pi * now / spec['period'] + phase)
	value = spec['base'] + wave + random.uniform(-spec['noise'], spec['noise'])
	return round(min(spec['max'], max(spec['min'], value)), 3)


class Mock(LifecyclePlugin, realtime=True, hourly=False, logged=False):
	"""Publishes ``MOCK_KEYS``. See the module docstring."""

	name = 'Mock'

	__defaultConfig__ = """
	[plugin]
	enabled = False

	[Mock]
	interval = 2
	"""

	def __init__(self):
		self.schema, self._sourceKeys = buildSchema({'keys': {k: dict(v) for k, v in MOCK_KEYS.items()}})
		super().__init__()
		self._phases = {key: random.uniform(0, 2 * math.pi) for key in MOCK_KEYS}

	@property
	def interval(self) -> float:
		try:
			return max(0.2, float(self.config.getOrSet('Mock', 'interval', '2', self.config.getfloat)))
		except Exception:
			return 2.0

	def publish(self) -> None:
		now = time.time()
		realtime = {'time': datetime.now().replace(microsecond=0).strftime(_TIME_FORMAT)}
		for key, spec in MOCK_KEYS.items():
			realtime[self._sourceKeys[key]] = mockValue(key, spec, now, self._phases[key])
		datagram = LevityDatagram(realtime, schema=self.schema, dataMap=self.schema.dataMaps['realtime'], static=False)
		self.realtime.update(datagram)

	async def onStart(self) -> None:
		self.publish()
		self._ticker = asyncio.ensure_future(self._tick())

	async def _tick(self) -> None:
		while True:
			await asyncio.sleep(self.interval)
			try:
				self.publish()
			except Exception as e:
				log.error(f'Mock: publish failed: {e}')

	async def onStop(self) -> None:
		ticker = getattr(self, '_ticker', None)
		if ticker is not None:
			ticker.cancel()


__plugin__ = Mock
