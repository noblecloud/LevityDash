"""Notice a plugin that is running but has stopped publishing, and say so (or start it again).

A plugin can be up and silent: a socket that stays bound with nothing on it, a poll loop stuck on a request, a
BLE scan that never reports. `PluginWatch.judge` compares how long a plugin has been quiet with how often it
usually publishes (`freshness.RefreshEstimator`). It reports one of three states:

- `ok`: it published recently enough.
- `quiet`: it is overdue (`staleAfter`). Logged once.
- `silent`: it is far overdue (twice that). With the `restart` policy the plugin is stopped and started again,
  at most `maxRestarts` times, with a growing wait between tries, until it publishes again.

Qt-free: the caller supplies the clock and the last-publish times, so a test can drive it with made-up ones.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, Iterable, Optional

from LevityDash.lib.plugins.freshness import RefreshEstimator
from LevityDash.lib.plugins.web.reconnect import Backoff

__all__ = ['OK', 'QUIET', 'SILENT', 'POLICIES', 'Judgement', 'PluginWatch', 'restartPlugin', 'sweep']

OK, QUIET, SILENT = 'ok', 'quiet', 'silent'
#: `off` never looks, `log` reports, `restart` also starts a silent plugin again.
POLICIES = ('off', 'log', 'restart')
#: Silent once this many times past `staleAfter`.
SILENT_AFTER_STALE = 2.0


@dataclass
class Judgement:
	name: str
	state: str
	#: How long it has published nothing.
	quietFor: timedelta
	#: The overdue limit for this plugin.
	staleAfter: timedelta
	#: True when the caller should stop and start it now.
	restart: bool = False
	#: True the first time a state is reported, so a log line is written once.
	changed: bool = False


class _Track:
	def __init__(self, seen: datetime):
		self.estimator = RefreshEstimator()
		self.lastPublish: Optional[datetime] = None
		self.since = seen
		self.state = OK
		self.restarts = 0
		self.nextRestart: Optional[datetime] = None
		self.backoff = Backoff(initial=60.0, maximum=1800.0)


class PluginWatch:
	"""One watcher for every plugin; call `judge` for each on a timer."""

	def __init__(self, policy: str = 'log', maxRestarts: int = 3):
		if policy not in POLICIES:
			raise ValueError(f'watchdog policy {policy!r} is not one of {", ".join(POLICIES)}')
		self.policy = policy
		self.maxRestarts = maxRestarts
		self._tracks: Dict[str, _Track] = {}

	def judge(self, name: str, running: bool, lastPublish: Optional[datetime], now: datetime,
	          declared: Optional[timedelta] = None) -> Optional[Judgement]:
		"""The state of one plugin, or None when it is not running (a stopped plugin is not silent, it is off)."""
		if self.policy == 'off':
			return None
		if not running:
			self._tracks.pop(name, None)
			return None
		track = self._tracks.get(name)
		if track is None:
			track = self._tracks[name] = _Track(now)
		if lastPublish is not None and lastPublish != track.lastPublish:
			track.lastPublish = lastPublish
			track.estimator.observe(lastPublish.timestamp())
			track.restarts = 0
			track.nextRestart = None
			track.backoff.reset()
		stale = track.estimator.staleAfter(declared)
		quietFor = now - (track.lastPublish or track.since)
		if quietFor > stale * SILENT_AFTER_STALE:
			state = SILENT
		elif quietFor > stale:
			state = QUIET
		else:
			state = OK
		changed = state != track.state
		track.state = state
		restart = False
		if state == SILENT and self.policy == 'restart' and track.restarts < self.maxRestarts \
				and (track.nextRestart is None or now >= track.nextRestart):
			restart = True
			track.restarts += 1
			track.nextRestart = now + timedelta(seconds=track.backoff.next())
			# It has to publish again before it counts as running well; the quiet clock starts over.
			track.since, track.lastPublish = now, None
		return Judgement(name, state, quietFor, stale, restart, changed)

	def health(self) -> Dict[str, str]:
		"""`{plugin name: ok|quiet|silent}` for every plugin judged so far, for the status the backend sends frontends."""
		return {name: track.state for name, track in self._tracks.items()}

	def forget(self, name: str) -> None:
		self._tracks.pop(name, None)


def restartPlugin(plugin) -> None:
	"""Stop `plugin`, then run it on a new thread (a finished `Thread` cannot be started again).

	Blocks while the plugin stops, so call it from a worker, not the GUI thread.
	"""
	plugin.stop()
	plugin.__dict__.pop('thread', None)  # `thread` is a cached property
	plugin.thread.start()


def sweep(watch: PluginWatch, plugins: Iterable, lastPublish: Dict[str, datetime], now: datetime, log, restart: Callable) -> None:
	"""Judge every plugin once. Writes a log line when a plugin's state changes; calls `restart(plugin)` for each the
	watch says to start again (the caller runs it off the GUI thread)."""
	for plugin in plugins:
		name = getattr(plugin, 'name', None)
		if name is None:
			continue
		try:
			running = bool(plugin.running and plugin.enabled)
		except Exception:  # noqa: BLE001 - a plugin that cannot say is not judged
			continue
		verdict = watch.judge(name, running, lastPublish.get(name), now)
		if verdict is None:
			continue
		minutes = verdict.quietFor.total_seconds() / 60
		if verdict.state == SILENT and verdict.restart:
			log.warning(f'{name}: nothing published for {minutes:.0f} min (usually every {verdict.staleAfter.total_seconds() / 150:.0f} min or so); stopping it and starting it again')
			restart(plugin)
		elif verdict.changed and verdict.state != OK:
			log.warning(f'{name}: {verdict.state}: nothing published for {minutes:.0f} min')
		elif verdict.changed:
			log.info(f'{name}: publishing again')
