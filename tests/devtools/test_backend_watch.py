"""Tests for the dev-only backend-watch tool (lib/devtools/backend_watch.py).

Never spawns the real LevityDash backend or runs the real test suite from
within a test (both are slow and would make this suite recursive) - uses
tiny throwaway subprocesses/test files instead, driven the same way the rest
of tests/wire/ drives async scenarios: plain `asyncio.run(scenario())`, no
pytest-asyncio (not a project dependency).
"""
import asyncio
import sys

from aiohttp.test_utils import TestClient, TestServer

from LevityDash.devtools.backend_watch import (
	BackendSupervisor, WatchState, _make_status_app, run_tests,
)

_SLEEPER = (
	"import time, signal, sys\n"
	"signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))\n"
	"time.sleep(30)\n"
)

_IGNORES_SIGTERM = (
	"import time, signal\n"
	"signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
	"time.sleep(30)\n"
)


def test_supervisor_start_stop(tmp_path):
	script = tmp_path / 'sleeper.py'
	script.write_text(_SLEEPER)

	class DummySupervisor(BackendSupervisor):
		async def start(self):
			self.proc = await asyncio.create_subprocess_exec(sys.executable, str(script))

	async def scenario():
		sup = DummySupervisor(cwd=tmp_path)
		assert not sup.is_alive
		await sup.start()
		assert sup.is_alive
		# give the child a moment to install its SIGTERM handler before
		# stop() sends one - otherwise the OS default (kill) can win the
		# race, which would test process-spawn timing, not stop()'s logic
		await asyncio.sleep(0.3)
		start = asyncio.get_event_loop().time()
		await sup.stop(timeout=5)
		elapsed = asyncio.get_event_loop().time() - start
		assert not sup.is_alive
		assert elapsed < 4  # honored SIGTERM well before the 5s kill fallback

	asyncio.run(scenario())


def test_supervisor_stop_kills_unresponsive_process(tmp_path):
	script = tmp_path / 'stubborn.py'
	script.write_text(_IGNORES_SIGTERM)

	class DummySupervisor(BackendSupervisor):
		async def start(self):
			self.proc = await asyncio.create_subprocess_exec(sys.executable, str(script))

	async def scenario():
		sup = DummySupervisor(cwd=tmp_path)
		await sup.start()
		assert sup.is_alive
		await sup.stop(timeout=0.5)  # too short for the SIGTERM-ignoring process
		assert not sup.is_alive
		assert sup.proc.returncode is not None and sup.proc.returncode != 0  # killed, not a clean exit

	asyncio.run(scenario())


def test_run_tests_reports_pass_and_fail(tmp_path):
	(tmp_path / 'test_ok.py').write_text('def test_ok():\n\tassert True\n')

	async def scenario_pass():
		return await run_tests(tmp_path)

	passed, output, duration = asyncio.run(scenario_pass())
	assert passed is True
	assert duration >= 0

	(tmp_path / 'test_ok.py').unlink()
	(tmp_path / 'test_bad.py').write_text('def test_bad():\n\tassert False\n')

	async def scenario_fail():
		return await run_tests(tmp_path)

	passed, output, duration = asyncio.run(scenario_fail())
	assert passed is False
	assert 'test_bad' in output


def test_status_routes_reflect_supervisor_state(tmp_path):
	script = tmp_path / 'sleeper.py'
	script.write_text(_SLEEPER)

	class DummySupervisor(BackendSupervisor):
		async def start(self):
			self.proc = await asyncio.create_subprocess_exec(sys.executable, str(script))

	async def scenario():
		state = WatchState(debounce_ms=1234, watch_paths=['/tmp/example'])
		supervisor = DummySupervisor(cwd=tmp_path)
		app = _make_status_app(state, supervisor)

		async with TestClient(TestServer(app)) as client:
			# before the backend is started: down
			resp = await client.get('/health')
			assert resp.status == 503
			body = await resp.json()
			assert body['status'] == 'down'

			await supervisor.start()
			resp = await client.get('/health')
			assert resp.status == 200
			body = await resp.json()
			assert body == {'status': 'ok'}

			resp = await client.get('/status')
			assert resp.status == 200
			body = await resp.json()
			assert body['state'] == 'starting'
			assert body['debounce_ms'] == 1234
			assert body['watch_paths'] == ['/tmp/example']
			assert body['pid'] == supervisor.proc.pid

			# tests_failing state: /status reflects it, /health stays "ok"
			# because the previous backend is still genuinely alive
			state.state = 'tests_failing'
			state.last_test_result = {'passed': False, 'ran_at': 'x', 'duration_s': 1.0, 'summary': 'boom'}
			resp = await client.get('/health')
			assert resp.status == 200
			resp = await client.get('/status')
			body = await resp.json()
			assert body['state'] == 'tests_failing'
			assert body['last_test_result']['passed'] is False

			await supervisor.stop(timeout=5)
			resp = await client.get('/health')
			assert resp.status == 503

	asyncio.run(scenario())
