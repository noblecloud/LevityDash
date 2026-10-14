"""Vitals of the machine LevityDash runs on, read with ``psutil``. Off by default.

Publishes, once every ``interval`` seconds:

- ``system.cpu.usage``, ``system.memory.usage``, ``system.disk.usage``: shares of the whole, as percentages.
- ``system.cpu.temperature``: in Celsius, where the platform reports one (Linux and most single-board
  computers do; macOS does not).
- ``system.battery.charge``: a percentage, only on a machine with a battery.
- ``system.network.down`` and ``system.network.up``: kilobytes per second, over every interface.
- ``system.process.count``: how many processes are running.
- ``system.process.top.N.name``, ``.pid``, ``.cpu`` and ``.memory`` for N = 1 to ``top``: whichever process ranks
  Nth by CPU right now. A panel binds to a slot and never to a process, so the ranking can change under it.
  This is what ``docs/design-references/presets/process-table.levity`` reads.

Percentages are fractions (0.458 is 45.8 %), because WeatherUnits reads a value above 1 as a whole percent and one
at or below 1 as a fraction, so a whole-percent 0.1 would show as 10 %. A process's ``cpu`` is a share of the
whole machine, not of one core.

**It is off until you turn it on.** Set this in ``<config dir>/plugins/Host.ini``, then restart:

	[plugin]
	enabled = True

	[Host]
	interval = 2
	top = 6

A key a scenario also defines is left to the scenario, so renders stay repeatable. The plugin skips itself
(and says so once in the log) when ``psutil`` cannot be imported.

``Mock`` publishes made-up values for several of the same ``system.*`` keys. Run one or the other.
"""
import asyncio
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.plugins.ble import LifecyclePlugin
from LevityDash.lib.plugins.builtin.Fixture import buildSchema, ENV_VAR, loadScenario, _TIME_FORMAT
from LevityDash.lib.plugins.schema import LevityDatagram

log = LevityPluginLog.getChild('Host')

try:
	import psutil
except ImportError:  # pragma: no cover - psutil is a dependency; this is for a stripped install
	psutil = None
	log.warning('Host: psutil is not installed, so the Host plugin is off')
	__disabled__ = True

#: The most process slots the schema declares. ``[Host] top`` picks how many are published, up to this.
TOP_MAX = 10
TEMPERATURE_SENSORS = ('coretemp', 'k10temp', 'cpu_thermal', 'cpu-thermal', 'zenpower', 'soc_thermal')

HOST_KEYS: Dict[str, dict] = {
	'system.cpu.usage': dict(unit='%', title='CPU'),
	'system.memory.usage': dict(unit='%', title='Memory'),
	'system.disk.usage': dict(unit='%', title='Disk'),
	'system.cpu.temperature': dict(unit='c', title='CPU temperature'),
	'system.battery.charge': dict(unit='%', title='Battery'),
	'system.network.down': dict(unit='int', title='Download (kB/s)'),
	'system.network.up': dict(unit='int', title='Upload (kB/s)'),
	'system.process.count': dict(unit='int', title='Processes'),
}
for _n in range(1, TOP_MAX + 1):
	HOST_KEYS.update({
		f'system.process.top.{_n}.name': dict(unit='str', title='Name'),
		f'system.process.top.{_n}.pid': dict(unit='int', title='PID'),
		f'system.process.top.{_n}.cpu': dict(unit='%', title='CPU'),
		f'system.process.top.{_n}.memory': dict(unit='%', title='Mem'),
	})


def _share(percent: Optional[float]) -> float:
	"""A psutil percentage (0 to 100) as a fraction, held inside 0 to 1."""
	return round(min(1.0, max(0.0, (percent or 0.0) / 100)), 4)


class Counters:
	"""What the last reading left behind: the network totals and when they were taken, to turn them into a rate."""

	def __init__(self):
		self.net: Optional[tuple] = None
		self.at: float = 0.0


def readHost(ps: Any, counters: Counters, top: int = 6, now: Optional[float] = None) -> Dict[str, Any]:
	"""One reading of the host as ``{key: value}``. A thing the platform cannot report is left out. ``ps`` is ``psutil``.

	The first reading has no network rate yet and its per-process CPU is 0, so the first ranking is by memory only
	in effect; both settle on the second reading.
	"""
	now = time.monotonic() if now is None else now
	out: Dict[str, Any] = {
		'system.cpu.usage': _share(ps.cpu_percent(interval=None)),
		'system.memory.usage': _share(ps.virtual_memory().percent),
		'system.disk.usage': _share(ps.disk_usage(os.path.abspath(os.sep)).percent),
	}
	sensors = getattr(ps, 'sensors_temperatures', None)
	if sensors is not None:
		try:
			readings = sensors() or {}
			chosen = next((readings[n] for n in TEMPERATURE_SENSORS if readings.get(n)), None)
			chosen = chosen or next((r for r in readings.values() if r), None)
			if chosen:
				out['system.cpu.temperature'] = round(float(chosen[0].current), 1)
		except Exception as e:  # noqa: BLE001 - a flaky sensor must not stop the rest
			log.debug(f'Host: no temperature: {e}')
	battery = getattr(ps, 'sensors_battery', None)
	if battery is not None:
		try:
			if (b := battery()) is not None:
				out['system.battery.charge'] = _share(b.percent)
		except Exception as e:  # noqa: BLE001
			log.debug(f'Host: no battery: {e}')
	try:
		net = ps.net_io_counters()
		if counters.net is not None and now > counters.at:
			span = now - counters.at
			out['system.network.down'] = max(0, round((net.bytes_recv - counters.net[0]) / span / 1024))
			out['system.network.up'] = max(0, round((net.bytes_sent - counters.net[1]) / span / 1024))
		counters.net, counters.at = (net.bytes_recv, net.bytes_sent), now
	except Exception as e:  # noqa: BLE001
		log.debug(f'Host: no network counters: {e}')

	cores = max(1, ps.cpu_count() or 1)
	rows = []
	count = 0
	for process in ps.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
		count += 1
		info = process.info
		rows.append((info.get('cpu_percent') or 0.0, info.get('memory_percent') or 0.0, info.get('pid'), info.get('name') or '?'))
	out['system.process.count'] = count
	rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
	for rank, (cpu, memory, pid, name) in enumerate(rows[:max(0, min(top, TOP_MAX))], start=1):
		prefix = f'system.process.top.{rank}'
		out[f'{prefix}.name'] = name
		out[f'{prefix}.pid'] = pid
		out[f'{prefix}.cpu'] = _share(cpu / cores)
		out[f'{prefix}.memory'] = _share(memory)
	return out


class Host(LifecyclePlugin, realtime=True, hourly=False, logged=False):
	"""Publishes ``HOST_KEYS``. See the module docstring."""

	name = 'Host'

	__defaultConfig__ = """
	[plugin]
	enabled = False

	[Host]
	interval = 2
	top = 6
	"""

	def __init__(self):
		self.schema, self._sourceKeys = buildSchema({'keys': {k: dict(v) for k, v in HOST_KEYS.items()}})
		super().__init__()
		self._counters = Counters()
		self._scenarioKeys = set()
		if os.environ.get(ENV_VAR, '').strip():
			try:
				self._scenarioKeys = {key.partition('#')[0] for key in loadScenario(os.environ[ENV_VAR].strip())['keys']}
			except Exception as e:  # noqa: BLE001 - the Fixture reports a bad scenario
				log.debug(f'Host: no scenario keys to skip: {e}')

	@property
	def interval(self) -> float:
		try:
			return max(1.0, float(self.config.getOrSet('Host', 'interval', '2', self.config.getfloat)))
		except Exception:
			return 2.0

	@property
	def top(self) -> int:
		try:
			return max(0, min(TOP_MAX, int(self.config.getOrSet('Host', 'top', '6', self.config.getint))))
		except Exception:
			return 6

	def publish(self) -> None:
		values = readHost(psutil, self._counters, self.top)
		realtime = {'time': datetime.now().replace(microsecond=0).strftime(_TIME_FORMAT)}
		for key, value in values.items():
			if key not in self._scenarioKeys:
				realtime[self._sourceKeys[key]] = value
		datagram = LevityDatagram(realtime, schema=self.schema, dataMap=self.schema.dataMaps['realtime'], static=False)
		self.realtime.update(datagram)

	async def onStart(self) -> None:
		psutil.cpu_percent(interval=None)  # the first call only starts the clock
		self.publish()
		self._ticker = asyncio.ensure_future(self._tick())

	async def _tick(self) -> None:
		while True:
			await asyncio.sleep(self.interval)
			try:
				self.publish()
			except Exception as e:
				log.error(f'Host: publish failed: {e}')

	async def onStop(self) -> None:
		ticker = getattr(self, '_ticker', None)
		if ticker is not None:
			ticker.cancel()


__plugin__ = Host
