from types import SimpleNamespace as NS

from LevityDash.lib.plugins.builtin.Host import Counters, HOST_KEYS, TOP_MAX, readHost


def fake(processes, sensors=None, battery=None):
	def process(pid, name, cpu, memory):
		return NS(info={'pid': pid, 'name': name, 'cpu_percent': cpu, 'memory_percent': memory})

	return NS(
		cpu_percent=lambda interval=None: 37.5,
		cpu_count=lambda: 4,
		virtual_memory=lambda: NS(percent=61.0),
		disk_usage=lambda path: NS(percent=72.0),
		sensors_temperatures=(lambda: sensors) if sensors is not None else None,
		sensors_battery=(lambda: battery),
		net_io_counters=lambda: NS(bytes_recv=NET[0], bytes_sent=NET[1]),
		process_iter=lambda attrs: [process(*p) for p in processes],
	)


NET = [0, 0]
PROCESSES = [(1, 'idle', 0.0, 0.1), (2, 'postgres', 200.0, 18.0), (3, 'node', 80.0, 9.3), (4, 'nginx', 0.4, 0.7)]


def test_percentages_are_fractions_and_a_process_cpu_is_a_share_of_the_machine():
	out = readHost(fake(PROCESSES), Counters(), top=3, now=10.0)
	assert out['system.cpu.usage'] == 0.375
	assert out['system.memory.usage'] == 0.61
	assert out['system.process.count'] == 4
	assert out['system.process.top.1.name'] == 'postgres'
	assert out['system.process.top.1.cpu'] == 0.5  # 200% of one core on 4 cores
	assert out['system.process.top.2.name'] == 'node'
	assert 'system.process.top.4.name' not in out, 'only `top` slots are published'


def test_network_rate_needs_two_readings():
	counters = Counters()
	NET[:] = [0, 0]
	first = readHost(fake(PROCESSES), counters, now=10.0)
	assert 'system.network.down' not in first
	NET[:] = [2048 * 5, 1024 * 5]
	second = readHost(fake(PROCESSES), counters, now=15.0)
	assert (second['system.network.down'], second['system.network.up']) == (2, 1)


def test_what_the_platform_lacks_is_left_out():
	out = readHost(fake(PROCESSES, sensors={}, battery=None), Counters(), now=1.0)
	assert 'system.cpu.temperature' not in out and 'system.battery.charge' not in out
	warm = readHost(fake(PROCESSES, sensors={'coretemp': [NS(current=58.26)]}, battery=NS(percent=64.0)), Counters(), now=1.0)
	assert warm['system.cpu.temperature'] == 58.3 and warm['system.battery.charge'] == 0.64


def test_every_published_key_is_declared():
	out = readHost(fake(PROCESSES, sensors={'coretemp': [NS(current=50)]}, battery=NS(percent=50)), Counters(), top=TOP_MAX, now=1.0)
	assert set(out) <= set(HOST_KEYS)
