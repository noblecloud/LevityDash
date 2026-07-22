"""Standalone LevityDash backend (Phase 4.2).

Runs the full plugin/observation/schema stack headless and serves encoded
container updates to frontends over a WebSocket (see ``lib/wire/``).

Process anatomy — every piece mirrors a pattern the GUI app already uses:

- The **Qt event loop runs on the main thread** (offscreen platform, no
  windows), exactly like the test suite boots — the ``Publisher``'s queued
  signal hop depends on a Qt loop existing, so plugins publish here unchanged.
- The **aiohttp server gets its own thread + asyncio loop**, mirroring how
  every plugin already runs its own loop in its own thread. Only finished
  JSON-safe messages cross between the two (``run_coroutine_threadsafe``).
- ``RemoteBackend`` (lib/wire/backend.py) attaches to each plugin's real
  ``Publisher`` — the send-side mirror of what ``LoopbackBridge`` proves
  in-process.

This process always ingests **live** internally (the in-process dispatcher
idles alongside, holding containers nobody renders — harmless). ``mode=remote``
is a *frontend* setting; if it leaks into this process's environment it is
forced back to live, otherwise the dispatcher would try to be a frontend of
ourselves.

Launch: ``LevityDash-backend`` (or ``python -m LevityDash.lib.backend``).
Bind host/port: ``[Backend] host/port`` in config, or the
``LEVITYDASH_BACKEND_HOST``/``LEVITYDASH_BACKEND_PORT`` env overrides.
Frontends connect with ``[Backend] mode = remote`` (see dispatcher.py).
"""
import asyncio
import os
import signal
import threading

__all__ = ['main']

DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 8667


def main() -> int:
	# Must be set before LevityDashboard.init(): the QApplication instance is
	# constructed during init()'s `import LevityDash.lib` chain (the package
	# import itself is Qt-free), and the platform can't change afterwards.
	os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
	if os.environ.get('LEVITYDASH_BACKEND_MODE') == 'remote':
		os.environ['LEVITYDASH_BACKEND_MODE'] = 'live'

	from LevityDash import LevityDashboard
	from LevityDash.lib.config import userConfig
	from LevityDash.lib.log import LevityPluginLog
	from LevityDash.lib.wire.backend import RemoteBackend
	from LevityDash.lib.wire.server import WireServer
	from PySide6.QtCore import QTimer

	log = LevityPluginLog.getChild('Backend')

	LevityDashboard.init()
	LevityDashboard.plugins.load_all()

	host = os.environ.get('LEVITYDASH_BACKEND_HOST') or userConfig.getOrSet('Backend', 'host', DEFAULT_HOST)
	port = int(os.environ.get('LEVITYDASH_BACKEND_PORT') or userConfig.getOrSet('Backend', 'port', str(DEFAULT_PORT)))

	server = WireServer(host=host, port=port)
	server_loop = asyncio.new_event_loop()
	started = threading.Event()
	start_error: list = []

	def _serve() -> None:
		asyncio.set_event_loop(server_loop)
		try:
			server_loop.run_until_complete(server.start())
		except Exception as e:  # bind failure, bad host, ...
			start_error.append(e)
			started.set()
			return
		started.set()
		server_loop.run_forever()

	server_thread = threading.Thread(target=_serve, name='WireServer', daemon=True)
	server_thread.start()
	started.wait(timeout=10)
	if start_error:
		log.critical(f'WireServer failed to start on {host}:{port}: {start_error[0]!r}')
		return 1
	if not server_thread.is_alive() and not started.is_set():
		log.critical('WireServer thread died before starting')
		return 1
	log.info(f'Backend serving on {server.url}')

	bridge = RemoteBackend(
		send=lambda message: asyncio.run_coroutine_threadsafe(server.broadcast(message), server_loop)
	)
	for plugin in LevityDashboard.plugins:
		bridge.attach(plugin)

	app = LevityDashboard.app

	def _shutdown(*_) -> None:
		log.info('Backend shutting down')
		app.quit()

	signal.signal(signal.SIGINT, _shutdown)
	signal.signal(signal.SIGTERM, _shutdown)
	# classic Qt-with-Unix-signals trick: wake the interpreter periodically so
	# Python-level signal handlers get a chance to run while app.exec() blocks
	wake = QTimer()
	wake.timeout.connect(lambda: None)
	wake.start(500)

	# mirror the GUI's own startup ordering (PySide/__init__.py): plugins start
	# once the Qt loop is running, so their publisher hops have a loop to land on
	QTimer.singleShot(10, LevityDashboard.plugins.start)

	code = app.exec()

	try:
		LevityDashboard.plugins.stop()
	except Exception as e:
		log.warning(f'plugin shutdown: {e!r}')
	try:
		asyncio.run_coroutine_threadsafe(server.stop(), server_loop).result(timeout=5)
	except Exception as e:
		log.warning(f'server shutdown: {e!r}')
	server_loop.call_soon_threadsafe(server_loop.stop)
	server_thread.join(timeout=5)
	log.info('Backend stopped')
	return code


if __name__ == '__main__':
	raise SystemExit(main())
