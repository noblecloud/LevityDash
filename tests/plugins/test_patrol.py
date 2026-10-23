import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from LevityDash.lib.plugins.patrol import Patrol, policyFromConfig

T0 = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
log = logging.getLogger('test-patrol')


class Publisher:
	def __init__(self):
		self.slots = []

	def connectSlot(self, slot):
		if slot in self.slots:
			return False
		self.slots.append(slot)
		return True

	def publish(self, plugin):
		for slot in self.slots:
			slot(SimpleNamespace(sender=plugin))


class FakePlugin:
	running = True
	enabled = True

	def __init__(self, name):
		self.name = name
		self.publisher = Publisher()


class Clock:
	def __init__(self):
		self.now = T0

	def __call__(self):
		return self.now

	def advance(self, minutes):
		self.now += timedelta(minutes=minutes)


def test_a_patrol_that_keeps_its_own_times_records_each_publish_and_judges_by_them():
	clock, plugin = Clock(), FakePlugin('Tempest')
	patrol = Patrol([plugin], 'log', log, clock=clock)
	for _ in range(11):
		patrol.sweep()
		plugin.publisher.publish(plugin)
		clock.advance(1)
	assert patrol.health() == {'Tempest': 'ok'}
	clock.advance(30)
	patrol.sweep()
	assert patrol.health() == {'Tempest': 'silent'}
	patrol.stop()


def test_listening_twice_connects_a_plugin_once():
	plugin = FakePlugin('Tempest')
	patrol = Patrol([plugin], 'log', log, clock=Clock())
	patrol.listen()
	patrol.listen()
	assert len(plugin.publisher.slots) == 1
	patrol.stop()


def test_given_times_are_used_and_no_slot_is_connected():
	plugin, times = FakePlugin('Tempest'), {}
	patrol = Patrol([plugin], 'log', log, lastPublish=times, clock=Clock())
	patrol.sweep()
	assert plugin.publisher.slots == [] and patrol.lastPublish is times
	patrol.stop()


def test_a_bad_policy_falls_back_to_log():
	config = SimpleNamespace(getOrSet=lambda *a: ' Bogus ')
	assert policyFromConfig(config, log) == 'log'
	assert policyFromConfig(SimpleNamespace(getOrSet=lambda *a: 'RESTART'), log) == 'restart'
