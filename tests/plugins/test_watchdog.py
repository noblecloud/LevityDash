from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from LevityDash.lib.plugins.watchdog import OK, QUIET, SILENT, PluginWatch, restartPlugin

T0 = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def at(minutes):
	return T0 + timedelta(minutes=minutes)


def steady(watch, name='Plugin', every=1, until=10):
	"""A plugin that publishes every `every` minutes up to minute `until`."""
	for m in range(0, until + 1, every):
		verdict = watch.judge(name, True, at(m), at(m))
		assert verdict.state == OK
	return at(until)


def test_a_plugin_that_keeps_publishing_is_ok():
	steady(PluginWatch())


def test_overdue_is_quiet_then_silent_and_each_state_is_reported_once():
	watch = PluginWatch()
	last = steady(watch)
	stale = watch.judge('Plugin', True, last, last).staleAfter
	quiet = watch.judge('Plugin', True, last, last + stale + timedelta(seconds=5))
	assert (quiet.state, quiet.changed) == (QUIET, True)
	again = watch.judge('Plugin', True, last, last + stale + timedelta(seconds=30))
	assert (again.state, again.changed) == (QUIET, False)
	silent = watch.judge('Plugin', True, last, last + stale * 2 + timedelta(seconds=5))
	assert (silent.state, silent.changed, silent.restart) == (SILENT, True, False)
	back = watch.judge('Plugin', True, last + stale * 3, last + stale * 3)
	assert back.state == OK and back.changed


def test_a_plugin_that_never_published_is_judged_from_when_it_was_first_seen():
	watch = PluginWatch()
	assert watch.judge('New', True, None, at(0)).state == OK
	stale = watch.judge('New', True, None, at(0)).staleAfter
	assert watch.judge('New', True, None, at(0) + stale * 2 + timedelta(seconds=1)).state == SILENT


def test_a_stopped_plugin_is_not_judged_and_the_off_policy_never_looks():
	watch = PluginWatch()
	assert watch.judge('Stopped', False, None, at(0)) is None
	assert PluginWatch('off').judge('Any', True, None, at(0)) is None


def test_the_restart_policy_restarts_with_a_growing_wait_and_gives_up():
	watch = PluginWatch('restart', maxRestarts=2)
	last = steady(watch)
	stale = watch.judge('Plugin', True, last, last).staleAfter
	now = last + stale * 2 + timedelta(seconds=1)
	first = watch.judge('Plugin', True, last, now)
	assert first.state == SILENT and first.restart
	# the restart reset its quiet clock, and it is not asked again before its wait is over
	assert not watch.judge('Plugin', True, None, now + timedelta(seconds=10)).restart
	later = now + stale * 2 + timedelta(minutes=5)
	assert watch.judge('Plugin', True, None, later).restart
	assert not watch.judge('Plugin', True, None, later + timedelta(hours=2)).restart  # out of tries


def test_publishing_again_gives_back_the_restarts():
	watch = PluginWatch('restart', maxRestarts=1)
	last = steady(watch)
	stale = watch.judge('Plugin', True, last, last).staleAfter
	now = last + stale * 2 + timedelta(seconds=1)
	assert watch.judge('Plugin', True, last, now).restart
	assert watch.judge('Plugin', True, now + timedelta(seconds=5), now + timedelta(seconds=5)).state == OK
	quietAgain = now + stale * 5
	assert watch.judge('Plugin', True, now + timedelta(seconds=5), quietAgain).restart


def test_a_bad_policy_is_refused():
	with pytest.raises(ValueError):
		PluginWatch('reboot')


def test_restart_stops_the_plugin_and_runs_it_on_a_new_thread():
	calls = []

	class Thread:
		def __init__(self, n):
			self.n = n

		def start(self):
			calls.append(('start', self.n))

	class Plugin:
		"""`thread` is a cached property on a real plugin; this one builds a new thread whenever its entry is gone."""
		n = 1

		def stop(self):
			calls.append(('stop',))

		@property
		def thread(self):
			return self.__dict__.setdefault('thread', Thread(self.n))

	plugin = Plugin()
	first = plugin.thread
	plugin.n = 2
	restartPlugin(plugin)
	assert calls == [('stop',), ('start', 2)] and plugin.thread is not first


def test_a_sweep_logs_a_change_once_and_hands_a_restart_to_the_runner():
	import logging
	from LevityDash.lib.plugins.watchdog import sweep
	records, restarted = [], []
	log = logging.getLogger('test-watchdog')
	log.addHandler(type('H', (logging.Handler,), {'emit': lambda self, r: records.append(r.getMessage())})())
	log.setLevel(logging.INFO)
	watch = PluginWatch('restart')
	plugin = SimpleNamespace(name='Tempest', running=True, enabled=True)
	last = steady(watch, 'Tempest')
	stale = watch.judge('Tempest', True, last, last).staleAfter
	sweep(watch, [plugin], {'Tempest': last}, last + stale + timedelta(seconds=1), log, restarted.append)
	sweep(watch, [plugin], {'Tempest': last}, last + stale + timedelta(seconds=20), log, restarted.append)
	assert len([m for m in records if 'quiet' in m]) == 1 and not restarted
	sweep(watch, [plugin], {'Tempest': last}, last + stale * 2 + timedelta(seconds=1), log, restarted.append)
	assert restarted == [plugin] and any('starting it again' in m for m in records)


def test_health_lists_each_judged_plugin_by_state_and_drops_a_stopped_one():
	watch = PluginWatch()
	last = steady(watch, 'Fast')
	watch.judge('Slow', True, None, last)
	stale = watch.judge('Fast', True, last, last).staleAfter
	watch.judge('Fast', True, last, last + stale + timedelta(seconds=1))
	assert watch.health() == {'Fast': QUIET, 'Slow': OK}
	watch.judge('Slow', False, None, last)
	assert watch.health() == {'Fast': QUIET}


def test_a_poll_that_publishes_many_keys_in_a_burst_is_not_flagged_between_polls():
	watch = PluginWatch()
	for poll in range(0, 61, 15):
		# the keys land over three seconds; sweeps happen to catch two moments of it
		watch.judge('OpenMeteo', True, at(poll), at(poll) + timedelta(seconds=1))
		verdict = watch.judge('OpenMeteo', True, at(poll) + timedelta(seconds=3), at(poll) + timedelta(seconds=30))
		assert verdict.state == OK
	late = watch.judge('OpenMeteo', True, at(60) + timedelta(seconds=3), at(60) + timedelta(minutes=14))
	assert late.state == OK
	assert late.staleAfter >= timedelta(minutes=30)


def test_the_period_a_plugin_declares_is_passed_to_the_judgement():
	asked = []
	watch = PluginWatch()
	real = watch.judge
	watch.judge = lambda *a, **k: asked.append(k.get('declared')) or real(*a, **k)
	plugin = SimpleNamespace(name='OpenMeteo', running=True, enabled=True, refreshPeriod=timedelta(minutes=15))
	from LevityDash.lib.plugins.watchdog import sweep
	log = SimpleNamespace(warning=lambda *a: None, info=lambda *a: None)
	sweep(watch, [plugin], {'OpenMeteo': at(0)}, at(1), log, lambda p: None)
	assert asked == [timedelta(minutes=15)]
