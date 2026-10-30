"""Run the plugin watchdog (`watchdog.py`) on a timer, in the process that runs the plugins.

The standalone backend and the frontend in `live` mode both run plugins, so both start a `Patrol`. The backend
passes the last-publish times its wire bridge already keeps; the frontend lets the patrol keep its own, by listening
to each plugin's publisher.
"""
import threading
from datetime import datetime
from typing import Callable, Dict, Optional

from PySide6.QtCore import QTimer

from LevityDash.lib.plugins.watchdog import POLICIES, PluginWatch, restartPlugin, sweep
from LevityDash.lib.utils.shared import now as _now

__all__ = ['Patrol', 'policyFromConfig', 'INTERVAL']

#: Seconds between sweeps.
INTERVAL = 30


def policyFromConfig(config, log) -> str:
	"""`[Backend] watchdog`, with a warning and `log` when it is not one of the policies."""
	policy = config.getOrSet('Backend', 'watchdog', 'log').strip().lower()
	if policy not in POLICIES:
		log.warning(f'[Backend] watchdog = {policy!r} is not one of {", ".join(POLICIES)}; using log')
		return 'log'
	return policy


class Patrol:
	"""A `PluginWatch` and the timer that sweeps it. Create on the Qt main thread."""

	def __init__(self, plugins, policy: str, log, lastPublish: Optional[Dict[str, datetime]] = None,
	             interval: int = INTERVAL, clock: Callable[[], datetime] = _now):
		self.plugins = plugins
		self.log = log
		self.watch = PluginWatch(policy)
		self.clock = clock
		self.ownsTimes = lastPublish is None
		self.lastPublish: Dict[str, datetime] = {} if lastPublish is None else lastPublish
		self._listening: set = set()
		self.timer = QTimer()
		self.timer.timeout.connect(self.sweep)
		self.timer.start(interval * 1000)

	def health(self) -> Dict[str, str]:
		return self.watch.health()

	def listen(self) -> None:
		"""Record when each plugin publishes. Does nothing for a plugin already heard, so it can run again."""
		if not self.ownsTimes:
			return
		for plugin in self.plugins:
			name = getattr(plugin, 'name', None)
			if name is None or name in self._listening:
				continue
			try:
				plugin.publisher.connectSlot(self._published)
			except Exception as e:  # noqa: BLE001 - a plugin without a publisher is not watched
				self.log.debug(f'{name}: not watched: {e!r}')
				continue
			self._listening.add(name)

	def _published(self, data) -> None:
		name = getattr(getattr(data, 'sender', None), 'name', None)
		if name is not None:
			self.lastPublish[name] = self.clock()

	def sweep(self) -> None:
		self.listen()
		sweep(self.watch, self.plugins, self.lastPublish, self.clock(), self.log, self._restart)

	def _restart(self, plugin) -> None:
		def run() -> None:
			try:
				restartPlugin(plugin)
			except Exception as e:  # noqa: BLE001
				self.log.error(f'{plugin.name}: restart failed: {e!r}')
		threading.Thread(target=run, name=f'Restart-{plugin.name}', daemon=True).start()

	def stop(self) -> None:
		self.timer.stop()
