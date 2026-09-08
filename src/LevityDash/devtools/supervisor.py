"""Run the backend and the frontend together, and keep them running.

``backend_watch`` supervises the backend alone and gates every restart on the
test suite, which is what you want while editing code. This is the deployed
counterpart: the room display wants *both* processes up, restarted when either
one dies and when the source changes, with no test gate - the tests already ran
before the code was pushed.

Ordering matters. In ``mode=remote`` the frontend is useless without a backend
to connect to, so the backend starts first and the frontend waits until its
port actually accepts a connection. In ``mode=live`` there is no separate
backend at all (the frontend runs the plugins itself), and starting one anyway
would run every plugin twice - so the mode is read from the config and the
backend is skipped.

⚠️ The frontend is a GUI process and inherits this process's GUI session, so
this must be launched from a terminal *on the machine with the display* (or
from a LaunchAgent). Started over plain SSH it will supervise a frontend that
can never open a window.

Launch: ``LevityDash-run`` (or ``python -m LevityDash.devtools.supervisor``).
Status API on ``http://127.0.0.1:8668`` by default
(``LEVITYDASH_SUPERVISOR_HOST``/``_PORT``, or ``--host``/``--port``) -
``GET /health`` (plain 200/503) and ``GET /status`` (full JSON state).

Pure asyncio, no Qt: the children host their own event loops, this process only
starts, watches and reaps them.
"""
import argparse
import asyncio
import configparser
import os
import signal
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import watchfiles
from aiohttp import web

from qolkit.hotkeys import CTRL_R, HotkeyListener

__all__ = ['cli']

DEFAULT_DEBOUNCE_MS = 2000
DEFAULT_STATUS_HOST = '127.0.0.1'
DEFAULT_STATUS_PORT = 8668
DEFAULT_BACKEND_HOST = '127.0.0.1'
DEFAULT_BACKEND_PORT = 8667

#: A child that dies sooner than this after starting is treated as crash-looping
#: rather than as a one-off failure, and its restart is backed off.
HEALTHY_RUN_S = 20.0
BACKOFF_S = (1.0, 2.0, 5.0, 15.0, 30.0)

# src/LevityDash/devtools/supervisor.py -> repo root is 3 parents up.
REPO_ROOT = Path(__file__).resolve().parents[3]


def readBackendConfig() -> Dict[str, str]:
	"""``[Backend]`` from the real config, without importing LevityDash.

	Importing the package pulls in Qt and pins the config directory at import
	time; this tool only needs three strings, so it reads them the same way the
	app resolves the path (appdirs with the same appname/appauthor) and falls
	back to remote-mode defaults when there is no config yet.
	"""
	mode = os.environ.get('LEVITYDASH_BACKEND_MODE')
	found = {'mode': mode or 'remote', 'host': DEFAULT_BACKEND_HOST, 'port': str(DEFAULT_BACKEND_PORT)}
	try:
		from appdirs import AppDirs
		configDir = Path(AppDirs(appname='LevityDash', appauthor='LevityDash.app').user_config_dir)
		parser = configparser.ConfigParser()
		parser.read(configDir / 'config.ini')
		if parser.has_section('Backend'):
			for key in ('mode', 'host', 'port'):
				if parser.has_option('Backend', key):
					found[key] = parser.get('Backend', key)
	except Exception as e:  # noqa: BLE001 - a missing/damaged config must not stop the launcher
		print(f'[run] could not read config ({e}); assuming mode=remote on {found["host"]}:{found["port"]}')
	# An explicit environment override outranks the file, as it does in the app.
	if mode:
		found['mode'] = mode
	return found


@dataclass
class SupervisorState:
	state: str = 'starting'  # starting | running | restarting | degraded | stopped
	mode: str = 'remote'
	started_at: Optional[str] = None
	last_restart_at: Optional[str] = None
	last_restart_reason: Optional[str] = None
	debounce_ms: int = DEFAULT_DEBOUNCE_MS
	watch_paths: List[str] = field(default_factory=list)

	def to_dict(self) -> dict:
		return asdict(self)


class Child:
	"""One supervised subprocess, restarted whenever it is not running."""

	def __init__(self, name: str, argv: List[str], cwd: Path, env: Optional[dict] = None,
	             logDir: Optional[Path] = None):
		self.name = name
		self.argv = argv
		self.cwd = cwd
		self.env = env if env is not None else os.environ.copy()
		self.proc: Optional[asyncio.subprocess.Process] = None
		self.started_at: float = 0.0
		self.restarts: int = 0
		#: Consecutive restarts where the child died before HEALTHY_RUN_S.
		self.failures: int = 0
		#: Where this child's own stdout/stderr is kept. Without it a child's
		#: output only ever reaches the terminal the supervisor was started
		#: from, which is how a dashboard that fails to build has stayed
		#: unexplained: the app's log file records a clean startup while the
		#: traceback goes to a terminal nobody is reading. See
		#: docs/tasks/dashboard-wont-load.md - "the traceback never reached a
		#: log file ... it was terminal-only".
		self.logPath: Optional[Path] = (logDir / f'{name}.out') if logDir else None
		self._pump: Optional[asyncio.Task] = None

	@property
	def is_alive(self) -> bool:
		return self.proc is not None and self.proc.returncode is None

	@property
	def pid(self) -> Optional[int]:
		return self.proc.pid if self.is_alive else None

	async def start(self) -> None:
		if self.logPath is None:
			self.proc = await asyncio.create_subprocess_exec(*self.argv, cwd=str(self.cwd), env=self.env)
		else:
			self.proc = await asyncio.create_subprocess_exec(
				*self.argv, cwd=str(self.cwd), env=self.env,
				stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
			)
			self._pump = asyncio.create_task(self._pumpOutput(self.proc))
		self.started_at = time.monotonic()
		print(f'[run] {self.name} started (pid={self.proc.pid})'
		      + (f' -> {self.logPath}' if self.logPath else ''))

	async def _pumpOutput(self, proc: asyncio.subprocess.Process) -> None:
		"""Copy the child's output to its log file *and* to our own stdout.

		Both, deliberately: watching the terminal is how you use this tool
		interactively, and the file is what is still there tomorrow when the
		display did something odd overnight.
		"""
		try:
			self.logPath.parent.mkdir(parents=True, exist_ok=True)
			with self.logPath.open('a', buffering=1, errors='replace') as fh:
				fh.write(f'\n===== {self.name} started {datetime.now(timezone.utc).isoformat()} =====\n')
				while True:
					line = await proc.stdout.readline()
					if not line:
						break
					text = line.decode(errors='replace')
					fh.write(text)
					sys.stdout.write(f'[{self.name}] {text}')
					sys.stdout.flush()
		except asyncio.CancelledError:
			raise
		except Exception as e:  # noqa: BLE001 - losing the log must not kill the child
			print(f'[run] {self.name}: output capture stopped ({e})')

	async def stop(self, timeout: float = 10.0) -> None:
		if not self.is_alive:
			return
		# The backend's SIGTERM handler needs ~500ms to notice plus a further
		# teardown budget for plugins and the wire server; the frontend has to
		# unwind a Qt event loop. Generous here only delays a restart.
		self.proc.terminate()
		try:
			await asyncio.wait_for(self.proc.wait(), timeout=timeout)
		except asyncio.TimeoutError:
			print(f'[run] {self.name} ignored SIGTERM after {timeout:.0f}s - killing')
			self.proc.kill()
			await self.proc.wait()

	async def restart(self) -> None:
		await self.stop()
		await self.start()
		self.restarts += 1

	def noteExit(self) -> float:
		"""Record an unexpected exit and return how long to wait before retrying."""
		if time.monotonic() - self.started_at >= HEALTHY_RUN_S:
			# It ran long enough to count as working, so this is a fresh
			# failure rather than a crash loop - retry immediately.
			self.failures = 0
			return 0.0
		self.failures += 1
		return BACKOFF_S[min(self.failures - 1, len(BACKOFF_S) - 1)]


async def waitForPort(host: str, port: int, timeout: float = 30.0) -> bool:
	"""Block until something accepts on ``host:port``, or give up.

	The frontend in ``mode=remote`` connects on startup; starting it before the
	backend is listening just makes it fail its first connection and sit in
	retry, which looks like a broken display for as long as the retry takes.
	"""
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		try:
			reader, writer = await asyncio.open_connection(host, port)
			writer.close()
			await writer.wait_closed()
			return True
		except (ConnectionRefusedError, OSError):
			await asyncio.sleep(0.25)
	return False


def _make_status_app(state: SupervisorState, children: List[Child]) -> web.Application:
	app = web.Application()

	async def health(_request: web.Request) -> web.Response:
		# Healthy means every child this run is supposed to have is up. A
		# frontend that died is a blank display, so it counts.
		if children and all(c.is_alive for c in children):
			return web.json_response({'status': 'ok'}, status=200)
		down = [c.name for c in children if not c.is_alive]
		return web.json_response({'status': 'down', 'down': down, 'state': state.state}, status=503)

	async def status(_request: web.Request) -> web.Response:
		payload = state.to_dict()
		payload['children'] = {
			c.name: {
				'pid': c.pid, 'alive': c.is_alive, 'restarts': c.restarts,
				'failures': c.failures, 'log': str(c.logPath) if c.logPath else None,
			}
			for c in children
		}
		return web.json_response(payload)

	app.router.add_get('/health', health)
	app.router.add_get('/status', status)
	return app


class Runner:
	"""Owns the children and the two things that restart them."""

	def __init__(self, args: argparse.Namespace, backend: Dict[str, str]):
		self.args = args
		self.backend = backend
		self.mode = backend['mode'].strip().lower()
		self.host = backend['host']
		try:
			self.port = int(backend['port'])
		except (TypeError, ValueError):
			self.port = DEFAULT_BACKEND_PORT

		self.children: List[Child] = []
		self.backendChild: Optional[Child] = None
		self.frontendChild: Optional[Child] = None
		#: Held for the length of a deliberate restart. Without it the
		#: supervise loop sees the frontend stopped mid-restart, calls it a
		#: crash, and starts it again before the backend is back - so a single
		#: file change produced two frontend starts and the wrong reason in
		#: /status.
		self._restartLock = asyncio.Lock()

		wantBackend = self.mode == 'remote' and not args.no_backend
		if self.mode != 'remote' and not args.no_backend:
			print(f'[run] mode={self.mode}: the frontend runs plugins itself, so no separate backend')
		logDir = None if args.no_capture else Path(args.log_dir).expanduser()
		if wantBackend:
			self.backendChild = Child('backend', [sys.executable, '-m', 'LevityDash.backend'],
			                          REPO_ROOT, logDir=logDir)
			self.children.append(self.backendChild)
		if not args.no_frontend:
			self.frontendChild = Child('frontend', [sys.executable, '-m', 'LevityDash'],
			                           REPO_ROOT, logDir=logDir)
			self.children.append(self.frontendChild)

	async def startAll(self) -> None:
		if self.backendChild is not None:
			await self.backendChild.start()
			if not await waitForPort(self.host, self.port, timeout=self.args.backend_timeout):
				print(f'[run] backend never listened on {self.host}:{self.port} - starting the frontend anyway')
		if self.frontendChild is not None:
			await self.frontendChild.start()

	async def restartAll(self, reason: str, state: SupervisorState) -> None:
		async with self._restartLock:
			await self._restartAll(reason, state)

	async def _restartAll(self, reason: str, state: SupervisorState) -> None:
		print(f'[run] restarting everything ({reason})')
		state.state = 'restarting'
		# Frontend first: it holds a connection to the backend, and tearing it
		# down before the backend goes away avoids a burst of reconnect noise.
		if self.frontendChild is not None:
			await self.frontendChild.stop()
		if self.backendChild is not None:
			await self.backendChild.restart()
			if not await waitForPort(self.host, self.port, timeout=self.args.backend_timeout):
				print(f'[run] backend never listened on {self.host}:{self.port} - starting the frontend anyway')
		if self.frontendChild is not None:
			await self.frontendChild.start()
			self.frontendChild.restarts += 1
		state.last_restart_at = datetime.now(timezone.utc).isoformat()
		state.last_restart_reason = reason
		state.state = 'running'

	async def superviseLoop(self, state: SupervisorState, stop_event: asyncio.Event) -> None:
		"""Restart any child that exits on its own.

		This is the half that makes the display self-healing: a crash, an OOM
		kill, or someone closing the window brings the process back rather than
		leaving a black screen until a human notices.
		"""
		while not stop_event.is_set():
			await asyncio.sleep(1.0)
			for child in self.children:
				if child.is_alive or stop_event.is_set():
					continue
				if self._restartLock.locked():
					# A deliberate restart is mid-flight; this child is meant
					# to be down right now.
					continue
				code = child.proc.returncode if child.proc is not None else None
				delay = child.noteExit()
				if delay:
					print(f'[run] {child.name} exited ({code}) after a short run - retrying in {delay:.0f}s')
					state.state = 'degraded'
					await asyncio.sleep(delay)
					if stop_event.is_set():
						return
				else:
					print(f'[run] {child.name} exited ({code}) - restarting')
				async with self._restartLock:
					if child.is_alive:
						# restartAll got to it while we waited for the lock.
						continue
					# A frontend in remote mode is pointless until the backend
					# is back, so wait for the port on its behalf too.
					if child is self.frontendChild and self.backendChild is not None:
						await waitForPort(self.host, self.port, timeout=self.args.backend_timeout)
					await child.start()
					child.restarts += 1
					state.last_restart_at = datetime.now(timezone.utc).isoformat()
					state.last_restart_reason = f'{child.name} exited ({code})'
					if all(c.is_alive for c in self.children):
						state.state = 'running'

	async def watchLoop(self, state: SupervisorState, stop_event: asyncio.Event) -> None:
		async for changes in watchfiles.awatch(
			*state.watch_paths, debounce=state.debounce_ms,
			watch_filter=watchfiles.PythonFilter(), stop_event=stop_event,
		):
			if stop_event.is_set():
				break
			# No test gate on purpose: whatever is deployed here was tested
			# before it was pushed, and a room display that refuses to pick up
			# a fix because of an unrelated failing test is worse than one that
			# restarts into it.
			await self.restartAll(f'{len(changes)} file(s) changed', state)

	async def stopAll(self) -> None:
		# Frontend first, for the same reason as a restart.
		for child in (self.frontendChild, self.backendChild):
			if child is not None:
				await child.stop()


async def _run(args: argparse.Namespace) -> None:
	backend = readBackendConfig()
	runner = Runner(args, backend)
	if not runner.children:
		print('[run] nothing to supervise (--no-backend and --no-frontend)')
		return

	watch_paths = args.watch or [str(REPO_ROOT / 'src' / 'LevityDash')]
	state = SupervisorState(
		debounce_ms=args.debounce_ms, watch_paths=watch_paths, mode=runner.mode,
	)

	status_app = _make_status_app(state, runner.children)
	web_runner = web.AppRunner(status_app)
	await web_runner.setup()
	site = web.TCPSite(web_runner, args.host, args.port)
	await site.start()
	print(f'[run] status API listening on http://{args.host}:{args.port}')

	state.started_at = datetime.now(timezone.utc).isoformat()
	await runner.startAll()
	state.state = 'running'
	print(f'[run] mode={runner.mode}; watching {", ".join(watch_paths)}')

	stop_event = asyncio.Event()
	# signal.signal rather than loop.add_signal_handler, matching backend_watch:
	# the latter is not available on Windows event loops.
	for sig in (signal.SIGINT, signal.SIGTERM):
		signal.signal(sig, lambda *_: stop_event.set())

	loop = asyncio.get_running_loop()

	async def manualRestart() -> None:
		await runner.restartAll('Ctrl+R', state)

	# The hotkey callback runs on the reader thread, so hop back to the loop
	# rather than touching subprocesses from off-thread.
	hotkeys = HotkeyListener()
	hotkeys.bind(CTRL_R, lambda: asyncio.run_coroutine_threadsafe(manualRestart(), loop))
	if hotkeys.start():
		print('[run] press Ctrl+R to restart everything immediately')

	tasks = [
		asyncio.create_task(runner.superviseLoop(state, stop_event)),
		asyncio.create_task(runner.watchLoop(state, stop_event)),
	]

	await stop_event.wait()
	print('[run] shutting down')
	state.state = 'stopped'
	for task in tasks:
		task.cancel()
	hotkeys.stop()
	await runner.stopAll()
	await web_runner.cleanup()


def _build_arg_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument(
		'--debounce-ms', type=int,
		default=int(os.environ.get('LEVITYDASH_SUPERVISOR_DEBOUNCE_MS', DEFAULT_DEBOUNCE_MS)),
		help='Quiet period after the last change before restarting (default: 2000)',
	)
	parser.add_argument(
		'--host', default=os.environ.get('LEVITYDASH_SUPERVISOR_HOST', DEFAULT_STATUS_HOST),
	)
	parser.add_argument(
		'--port', type=int,
		default=int(os.environ.get('LEVITYDASH_SUPERVISOR_PORT', DEFAULT_STATUS_PORT)),
	)
	parser.add_argument(
		'--watch', action='append', default=None,
		help='Path to watch (repeatable); defaults to src/LevityDash',
	)
	parser.add_argument(
		'--log-dir', default=os.environ.get('LEVITYDASH_SUPERVISOR_LOG_DIR',
		                                    '~/Library/Logs/LevityDash'),
		help="Where to keep each child's stdout/stderr (default: ~/Library/Logs/LevityDash)",
	)
	parser.add_argument(
		'--no-capture', action='store_true',
		help="Let children write straight to this terminal without capturing to a file",
	)
	parser.add_argument('--no-backend', action='store_true', help='Supervise only the frontend')
	parser.add_argument('--no-frontend', action='store_true', help='Supervise only the backend')
	parser.add_argument(
		'--backend-timeout', type=float, default=30.0,
		help='Seconds to wait for the backend to accept connections before starting the frontend',
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
