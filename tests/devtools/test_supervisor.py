"""Tests for the deployed launcher (devtools/supervisor.py).

Never spawns the real backend or frontend - both are slow and one wants a GUI
session. Uses tiny throwaway subprocesses, driven the way the rest of the suite
drives async scenarios: plain `asyncio.run(scenario())`, no pytest-asyncio.
"""
import asyncio
import sys

from aiohttp.test_utils import TestClient, TestServer

from LevityDash.devtools.supervisor import (
	BACKOFF_S, Child, SupervisorState, _make_status_app, readBackendConfig, waitForPort,
)

_TALKER = (
	"import sys, time, signal\n"
	"signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))\n"
	"print('hello from the child'); sys.stdout.flush()\n"
	"print('Traceback (most recent call last):'); sys.stdout.flush()\n"
	"time.sleep(600)\n"
)

_SLEEPER = (
	"import time, signal, sys\n"
	"signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))\n"
	"time.sleep(600)\n"
)


def _child(tmp_path, name='child'):
	script = tmp_path / 'sleeper.py'
	script.write_text(_SLEEPER)
	return Child(name, [sys.executable, str(script)], tmp_path)


def test_child_start_and_stop(tmp_path):
	child = _child(tmp_path)

	async def scenario():
		await child.start()
		assert child.is_alive
		assert child.pid is not None
		await child.stop(timeout=10)
		assert not child.is_alive
		assert child.pid is None

	asyncio.run(scenario())


def test_a_short_lived_child_backs_off_but_a_long_lived_one_does_not(tmp_path):
	# The crash-loop guard: a child that dies immediately must not be
	# restarted in a tight loop, but one that ran fine for a while and then
	# died should come back at once.
	child = _child(tmp_path)
	child.started_at = 0.0  # pretend it has been up a long time
	assert child.noteExit() == 0.0
	assert child.failures == 0

	import time as _time
	child.started_at = _time.monotonic()  # died immediately
	first = child.noteExit()
	second = child.noteExit()
	assert first == BACKOFF_S[0]
	assert second == BACKOFF_S[1]
	assert second > first


def test_wait_for_port_gives_up_on_a_closed_port():
	# Picking the frontend's start time off a port that never opens must not
	# hang the launcher forever.
	async def scenario():
		return await waitForPort('127.0.0.1', 9, timeout=0.5)

	assert asyncio.run(scenario()) is False


def test_wait_for_port_sees_a_listener():
	async def scenario():
		server = await asyncio.start_server(lambda r, w: None, '127.0.0.1', 0)
		port = server.sockets[0].getsockname()[1]
		try:
			return await waitForPort('127.0.0.1', port, timeout=5)
		finally:
			server.close()
			await server.wait_closed()

	assert asyncio.run(scenario()) is True


def test_health_is_down_until_every_child_is_up(tmp_path):
	# A dead frontend is a blank display, so /health must fail even though the
	# backend is fine - unlike backend_watch, where only the backend counts.
	state = SupervisorState()
	backend = _child(tmp_path, 'backend')
	frontend = _child(tmp_path, 'frontend')

	async def scenario():
		await backend.start()
		client = TestClient(TestServer(_make_status_app(state, [backend, frontend])))
		await client.start_server()
		try:
			resp = await client.get('/health')
			assert resp.status == 503
			assert (await resp.json())['down'] == ['frontend']

			await frontend.start()
			resp = await client.get('/health')
			assert resp.status == 200

			resp = await client.get('/status')
			payload = await resp.json()
			assert payload['children']['backend']['alive'] is True
			assert payload['children']['frontend']['alive'] is True
		finally:
			await client.close()
			await backend.stop()
			await frontend.stop()

	asyncio.run(scenario())


def test_backend_mode_env_overrides_the_config_file(monkeypatch):
	monkeypatch.setenv('LEVITYDASH_BACKEND_MODE', 'live')
	assert readBackendConfig()['mode'] == 'live'


def test_child_output_is_captured_to_a_file(tmp_path):
	"""A child's stdout must survive somewhere other than the terminal.

	Without this a dashboard that fails to build is invisible: the app's own
	log records a clean startup while the traceback goes only to whatever
	terminal the supervisor was launched from. That is the reason
	docs/tasks/dashboard-wont-load.md sat open - "the traceback never reached
	a log file".
	"""
	script = tmp_path / 'talker.py'
	script.write_text(_TALKER)
	logs = tmp_path / 'logs'
	child = Child('frontend', [sys.executable, str(script)], tmp_path, logDir=logs)

	async def scenario():
		await child.start()
		for _ in range(100):                      # let the pump drain
			await asyncio.sleep(0.05)
			if child.logPath.exists() and 'hello from the child' in child.logPath.read_text():
				break
		await child.stop()

	asyncio.run(scenario())
	assert child.logPath == logs / 'frontend.out'
	text = child.logPath.read_text()
	assert 'hello from the child' in text
	assert 'Traceback (most recent call last):' in text, (
		'a traceback on the child\'s stdout must reach the file'
	)


def test_capture_can_be_turned_off(tmp_path):
	child = Child('frontend', [sys.executable, '-c', 'pass'], tmp_path)
	assert child.logPath is None
