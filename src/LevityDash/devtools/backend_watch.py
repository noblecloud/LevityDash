"""Dev-only watcher: restart the standalone backend on source changes, gated
on the test suite passing - so a broken save never replaces a working backend.

Pure asyncio, no Qt - unlike ``lib/backend.py`` (which splits a Qt main
thread from an asyncio server thread specifically because it hosts a
``QApplication``), this tool has no GUI at all, so the watch loop, the test
runs, the supervised subprocess, and the status API all share one loop.

Launch: ``LevityDash-backend-watch`` (or ``python -m
LevityDash.devtools.backend_watch``). Status API on
``http://127.0.0.1:8669`` by default (``LEVITYDASH_WATCH_STATUS_HOST``/
``_PORT`` or ``--host``/``--port`` to override) - ``GET /health`` (plain
200/503, the contract basically every generic uptime tool or menu-bar widget
already expects) and ``GET /status`` (full JSON state, for anything that
wants detail).
"""
import argparse
import asyncio
import os
import signal
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import watchfiles
from aiohttp import web

from qolkit.hotkeys import CTRL_R, HotkeyListener

__all__ = ['cli']

DEFAULT_DEBOUNCE_MS = 2000
DEFAULT_STATUS_HOST = '127.0.0.1'
DEFAULT_STATUS_PORT = 8669

# src/LevityDash/devtools/backend_watch.py -> repo root is 3 parents up.
REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class WatchState:
	state: str = 'starting'  # starting | running | restarting | tests_failing | stopped
	started_at: Optional[str] = None
	last_restart_at: Optional[str] = None
	last_test_result: Optional[dict] = None  # {passed, ran_at, duration_s, summary}
	debounce_ms: int = DEFAULT_DEBOUNCE_MS
	watch_paths: List[str] = field(default_factory=list)

	def to_dict(self) -> dict:
		return asdict(self)


class BackendSupervisor:
	def __init__(self, cwd: Path, env: Optional[dict] = None):
		self.cwd = cwd
		self.env = env if env is not None else os.environ.copy()
		self.proc: Optional[asyncio.subprocess.Process] = None

	@property
	def is_alive(self) -> bool:
		return self.proc is not None and self.proc.returncode is None

	async def start(self) -> None:
		self.proc = await asyncio.create_subprocess_exec(
			sys.executable, '-m', 'LevityDash.backend',
			cwd=str(self.cwd), env=self.env,
		)

	async def stop(self, timeout: float = 10.0) -> None:
		if not self.is_alive:
			return
		# lib/backend.py's own SIGTERM handler needs up to ~500ms (its
		# QTimer signal-poll trick) plus a further 5s teardown budget for
		# plugins/WireServer - this timeout is deliberately generous rather
		# than tuned tight against that, since a slow teardown here just
		# delays a restart, not a crash.
		self.proc.terminate()
		try:
			await asyncio.wait_for(self.proc.wait(), timeout=timeout)
		except asyncio.TimeoutError:
			self.proc.kill()
			await self.proc.wait()

	async def restart(self) -> None:
		await self.stop()
		await self.start()


async def run_tests(cwd: Path, timeout: float = 300.0) -> Tuple[bool, str, float]:
	start = time.monotonic()
	proc = await asyncio.create_subprocess_exec(
		sys.executable, '-m', 'pytest', '-q',
		cwd=str(cwd), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
	)
	try:
		stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
		passed = proc.returncode == 0
	except asyncio.TimeoutError:
		proc.kill()
		await proc.wait()
		stdout = b''
		passed = False
	duration = time.monotonic() - start
	output = stdout.decode(errors='replace')
	return passed, output, duration


def _make_status_app(state: WatchState, supervisor: BackendSupervisor) -> web.Application:
	app = web.Application()

	async def health(_request: web.Request) -> web.Response:
		# Deliberately independent of `state.state`: tests_failing still
		# leaves the previous backend running, and that backend is genuinely
		# healthy - only /status's last_test_result should reveal a pending
		# problem, not /health.
		if supervisor.is_alive:
			return web.json_response({'status': 'ok'}, status=200)
		return web.json_response({'status': 'down', 'state': state.state}, status=503)

	async def status(_request: web.Request) -> web.Response:
		payload = state.to_dict()
		payload['pid'] = supervisor.proc.pid if supervisor.is_alive else None
		return web.json_response(payload)

	app.router.add_get('/health', health)
	app.router.add_get('/status', status)
	return app


async def _watch_loop(
	watch_paths: List[str], debounce_ms: int, state: WatchState,
	supervisor: BackendSupervisor, cwd: Path, stop_event: asyncio.Event,
) -> None:
	async for changes in watchfiles.awatch(
		*watch_paths, debounce=debounce_ms,
		watch_filter=watchfiles.PythonFilter(), stop_event=stop_event,
	):
		if stop_event.is_set():
			break
		print(f'[watch] {len(changes)} file(s) changed - running tests before restart')
		state.state = 'restarting'
		passed, output, duration = await run_tests(cwd)
		ran_at = datetime.now(timezone.utc).isoformat()
		summary = next((l for l in reversed(output.strip().splitlines())), '')
		state.last_test_result = {
			'passed':     passed,
			'ran_at':     ran_at,
			'duration_s': round(duration, 2),
			'summary':    summary,
		}
		if passed:
			print(f'[watch] tests passed ({duration:.1f}s) - restarting backend')
			await supervisor.restart()
			state.last_restart_at = ran_at
			state.state = 'running'
		else:
			print(f'[watch] tests failed ({duration:.1f}s) - keeping current backend running')
			print(output[-2000:])
			state.state = 'tests_failing'


async def _run(args: argparse.Namespace) -> None:
	watch_paths = args.watch or [str(REPO_ROOT / 'src' / 'LevityDash'), str(REPO_ROOT / 'tests')]
	state = WatchState(debounce_ms=args.debounce_ms, watch_paths=watch_paths)
	supervisor = BackendSupervisor(cwd=REPO_ROOT)

	status_app = _make_status_app(state, supervisor)
	runner = web.AppRunner(status_app)
	await runner.setup()
	site = web.TCPSite(runner, args.host, args.port)
	await site.start()
	print(f'[watch] status API listening on http://{args.host}:{args.port}')

	state.started_at = datetime.now(timezone.utc).isoformat()
	await supervisor.start()
	state.state = 'running'
	print(f'[watch] backend started (pid={supervisor.proc.pid}); watching {", ".join(watch_paths)}')

	stop_event = asyncio.Event()
	# signal.signal (not loop.add_signal_handler) so this also works on
	# Windows event loops, which don't support the latter.
	for sig in (signal.SIGINT, signal.SIGTERM):
		signal.signal(sig, lambda *_: stop_event.set())

	# Ctrl+R: restart the supervised backend now, without waiting for a file
	# change. Unlike the frontend's Ctrl+C-then-Ctrl+R, this needs no arming -
	# there is nothing destructive about restarting a supervised child.
	#
	# Tests are deliberately NOT run first: this is the manual override for
	# "just bounce it", and the file-change path already gates on them.
	loop = asyncio.get_running_loop()

	async def manual_restart() -> None:
		print('[watch] Ctrl+R - restarting backend (tests skipped)')
		state.state = 'restarting'
		await supervisor.restart()
		state.last_restart_at = datetime.now(timezone.utc).isoformat()
		state.state = 'running'
		print(f'[watch] backend restarted (pid={supervisor.proc.pid})')

	# The hotkey callback runs on the reader thread, so hop to the loop rather
	# than touching the supervisor from off-thread.
	hotkeys = HotkeyListener()
	hotkeys.bind(CTRL_R, lambda: asyncio.run_coroutine_threadsafe(manual_restart(), loop))
	if hotkeys.start():
		print('[watch] press Ctrl+R to restart the backend immediately')

	watch_task = asyncio.create_task(
		_watch_loop(watch_paths, args.debounce_ms, state, supervisor, REPO_ROOT, stop_event)
	)

	await stop_event.wait()
	print('[watch] shutting down')
	state.state = 'stopped'
	watch_task.cancel()
	hotkeys.stop()
	await supervisor.stop()
	await runner.cleanup()


def _build_arg_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument(
		'--debounce-ms', type=int,
		default=int(os.environ.get('LEVITYDASH_WATCH_DEBOUNCE_MS', DEFAULT_DEBOUNCE_MS)),
		help='Quiet period after the last change before running tests/restarting (default: 2000)',
	)
	parser.add_argument(
		'--host', default=os.environ.get('LEVITYDASH_WATCH_STATUS_HOST', DEFAULT_STATUS_HOST),
	)
	parser.add_argument(
		'--port', type=int,
		default=int(os.environ.get('LEVITYDASH_WATCH_STATUS_PORT', DEFAULT_STATUS_PORT)),
	)
	parser.add_argument(
		'--watch', action='append', default=None,
		help='Path to watch (repeatable); defaults to src/LevityDash and tests',
	)
	return parser


def cli() -> int:
	args = _build_arg_parser().parse_args()
	try:
		asyncio.run(_run(args))
	except KeyboardInterrupt:
		pass
	return 0


if __name__ == '__main__':
	raise SystemExit(cli())
