"""The sun, from the clock and the configured location. No network, no key.

Publishes two realtime keys that a sun-arc dial reads:

- ``astronomy.sun.hour``: the local hour of day as a decimal (15.5 is 15:30).
- ``astronomy.sun.remaining``: minutes of daylight left today. It is 0 at night
  and counts down from the day's length at sunrise.

Sunrise and sunset come from ``ephem``, the same library the moon uses, for the
``[Location]`` latitude and longitude in the main config. During a polar day
or night the day is treated as the whole 24 hours or nothing.

The plugin is on by default. Set ``enabled = False`` in
``<config dir>/plugins/Astronomy.ini`` to turn it off. A scenario that defines
either key wins over it, so renders stay repeatable.
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import ephem

from LevityDash.lib.config import userConfig
from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.plugins.ble import LifecyclePlugin
from LevityDash.lib.plugins.builtin.Fixture import buildSchema, ENV_VAR, loadScenario, _TIME_FORMAT
from LevityDash.lib.plugins.schema import LevityDatagram

log = LevityPluginLog.getChild('Astronomy')

ASTRONOMY_KEYS = {
	'astronomy.sun.hour': dict(unit='int', min=0, max=24, title='Hour of day'),
	'astronomy.sun.remaining': dict(unit='int', min=0, max=1440, title='Daylight left (minutes)'),
}


def _sunTimes(lat: float, lon: float, now: datetime) -> Tuple[Optional[datetime], Optional[datetime]]:
	"""Today's sunrise and sunset as aware local datetimes, or ``None`` for a polar day or night."""
	observer = ephem.Observer()
	observer.lat, observer.lon = str(lat), str(lon)
	observer.pressure = 0
	observer.horizon = '-0:34'
	localNoon = now.replace(hour=12, minute=0, second=0, microsecond=0)
	observer.date = localNoon.astimezone(timezone.utc).replace(tzinfo=None)
	sun = ephem.Sun()
	try:
		rise = observer.previous_rising(sun, use_center=True).datetime().replace(tzinfo=timezone.utc).astimezone(now.tzinfo)
		sset = observer.next_setting(sun, use_center=True).datetime().replace(tzinfo=timezone.utc).astimezone(now.tzinfo)
	except (ephem.AlwaysUpError, ephem.NeverUpError):
		return None, None
	return rise, sset


def sunValues(lat: float, lon: float, now: Optional[datetime] = None) -> Tuple[float, float]:
	"""``(hour, minutes of daylight left)`` at ``now``. Pure, so a test can call it."""
	now = (now or datetime.now()).astimezone()
	hour = round(now.hour + now.minute / 60 + now.second / 3600, 4)
	rise, sset = _sunTimes(lat, lon, now)
	if rise is None:
		up = ephem.Observer()
		up.lat, up.lon, up.date = str(lat), str(lon), now.astimezone(timezone.utc).replace(tzinfo=None)
		sun = ephem.Sun(up)
		return hour, (1440.0 if float(sun.alt) > 0 else 0.0)
	if now >= sset or now < rise:
		return hour, 0.0
	return hour, round((sset - now) / timedelta(minutes=1), 1)


class Astronomy(LifecyclePlugin, realtime=True, hourly=False, logged=False):
	"""Publishes ``ASTRONOMY_KEYS``. See the module docstring."""

	name = 'Astronomy'

	__defaultConfig__ = """
	[plugin]
	enabled = True

	[Astronomy]
	interval = 30
	"""

	def __init__(self):
		self.schema, self._sourceKeys = buildSchema({'keys': {k: dict(v) for k, v in ASTRONOMY_KEYS.items()}})
		super().__init__()
		self._scenarioKeys = set()
		if os.environ.get(ENV_VAR, '').strip():
			try:
				self._scenarioKeys = {key.partition('#')[0] for key in loadScenario(os.environ[ENV_VAR].strip())['keys']}
			except Exception as e:  # noqa: BLE001 - the Fixture reports a bad scenario
				log.debug(f'Astronomy: no scenario keys to skip: {e}')

	@property
	def interval(self) -> float:
		try:
			return max(5.0, float(self.config.getOrSet('Astronomy', 'interval', '30', self.config.getfloat)))
		except Exception:
			return 30.0

	def publish(self) -> None:
		hour, remaining = sunValues(float(userConfig.lat), float(userConfig.lon))
		values = {'astronomy.sun.hour': hour, 'astronomy.sun.remaining': remaining}
		realtime = {'time': datetime.now().replace(microsecond=0).strftime(_TIME_FORMAT)}
		for key, value in values.items():
			if key not in self._scenarioKeys:
				realtime[self._sourceKeys[key]] = value
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
				log.error(f'Astronomy: publish failed: {e}')

	async def onStop(self) -> None:
		ticker = getattr(self, '_ticker', None)
		if ticker is not None:
			ticker.cancel()


__plugin__ = Astronomy
