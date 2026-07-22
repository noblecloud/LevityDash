"""Boots the full app in `[Backend] mode = remote` against a real in-process
WireServer - the closest a test can get to "run it like a normal config"
without a second process or a display.

Same subprocess rationale as test_loopback_boot.py (PluginValueDirectory is a
process-wide singleton; a second in-process construction would re-wire the
session `dashboard` fixture's live singleton). Unlike the transport/frontend
tests, this exercises the WHOLE path the user's real run does:

- WireClient reconnect/attach + snapshot replay on connect
- the GUI-thread marshal hop before any scene object is touched
- a full dashboard load with remote values already in the dispatcher
- a STALE pushed value (30min old) so TimeOffsetLabel's enable path actually
  fires - the exact path that crashed the first real mode=remote run
  (Realtime.py's TimeOffsetLabel reaching for qApp.instance().clock)

The parent's assertion on stderr is deliberate: PySide prints exceptions from
slots/signals without crashing the process, so "no Traceback in stderr" is the
only meaningful "it rendered cleanly" signal a headless boot can give.
"""
import json
import socket
import subprocess
import sys
import textwrap

BOOT_SCRIPT = textwrap.dedent("""
	import asyncio
	import json
	import os
	import sys
	import threading
	from datetime import datetime, timedelta, timezone

	from LevityDash import LevityDashboard

	# --- in-process backend stand-in: a real WireServer, up before the app's
	# RemoteConnection finishes its first reconnect cycle (backoff handles the
	# race regardless) ---
	from LevityDash.lib.wire.server import WireServer
	from LevityDash.lib.wire.messages import encode_update_message

	server = WireServer(host='127.0.0.1', port={port})
	loop = asyncio.new_event_loop()

	def serve():
		asyncio.set_event_loop(loop)
		loop.run_until_complete(server.start())
		loop.run_forever()

	threading.Thread(target=serve, daemon=True).start()

	def container_dict(value, minutes_old):
		return {{
			'value': {{'__type__': 'measurement', 'value': value, 'unit': 'ºF', 'cls': 'Fahrenheit'}},
			'timestamp': {{'__type__': 'datetime', 'value': (datetime.now(timezone.utc) - timedelta(minutes=minutes_old)).isoformat()}},
			'title': 'Temperature',
			# a real backend message carries the schema's metadata type;
			# Realtime.py's Text-display branch reads metadata['type'] directly
			'metadata': {{'type': 'value'}},
			'icon_alias': None,
			'flags': {{
				'isRealtime': True, 'isRealtimeApproximate': False, 'isForecast': False,
				'isTimeseries': False, 'isDaily': False, 'isDailyForecast': False,
				'isDailyOnly': False, 'isTimeseriesOnly': False,
			}},
		}}

	def broadcast(minutes_old):
		message = encode_update_message(
			name='OpenMeteo', defaultFor=(), enabled=True, running=True,
			updates={{'environment.temperature.temperature': container_dict(74.0, minutes_old)}},
		)
		asyncio.run_coroutine_threadsafe(server.broadcast(message), loop)

	# stale value first: replayed to the frontend on connect, so the dashboard
	# loads with a value old enough to trigger every stale-value code path
	broadcast(minutes_old=30)

	# --- the real boot path (see __main__.main / LevityDashApp.start) ---
	LevityDashboard.init()
	LevityDashboard.plugins.load_all()
	app = LevityDashboard.app

	from PySide6.QtCore import QTimer
	# schedule BEFORE start(): app.start() enters the Qt event loop, so
	# anything after it never runs until the loop quits. The watchdog
	# guarantees the subprocess dies even if the quit timer never fires.
	QTimer.singleShot(3000, lambda: broadcast(minutes_old=0))  # fresh live update mid-run
	QTimer.singleShot(6000, app.quit)
	threading.Timer(45, lambda: os._exit(2)).start()
	app.start()

	# --- report (event loop has returned) ---
	from LevityDash.lib.plugins.categories import CategoryItem
	dispatcher = LevityDashboard.dispatcher
	key = CategoryItem('environment.temperature.temperature')
	container = dispatcher.getContainer(key, None)
	result = {{
		'mode': dispatcher.backend_mode,
		'is_remote': dispatcher.remote is not None,
		'key_count': len(list(dispatcher.keys())),
		'temperature': str(container.value.value) if container and len(container) else None,
		'is_realtime': container.value.isRealtime if container and len(container) else None,
	}}
	print('RESULT_JSON:' + json.dumps(result))
	sys.stdout.flush()
	sys.stderr.flush()
	os._exit(0)  # skip hanging on non-daemon plugin/pool threads at interpreter exit
""")


def _free_port() -> int:
	with socket.socket() as s:
		s.bind(('127.0.0.1', 0))
		return s.getsockname()[1]


def test_remote_mode_full_boot_with_live_wire_server():
	import os

	port = _free_port()
	env = {
		**os.environ,
		'QT_QPA_PLATFORM': 'offscreen',
		'LEVITYDASH_CONFIG_DEBUG': '1',
		'LEVITYDASH_BACKEND_MODE': 'remote',
		'LEVITYDASH_BACKEND_URL': f'ws://127.0.0.1:{port}/ws',
	}
	proc = subprocess.run(
		[sys.executable, '-c', BOOT_SCRIPT.format(port=port)],
		capture_output=True,
		text=True,
		timeout=120,
		env=env,
	)
	assert proc.returncode == 0, f'remote boot crashed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}'
	# PySide surfaces slot/signal exceptions on stderr without crashing -
	# this is the assertion that would have caught the real-run AttributeErrors
	assert 'Traceback' not in proc.stderr, f'exceptions during remote boot:\n{proc.stderr}'

	line = next((l for l in proc.stdout.splitlines() if l.startswith('RESULT_JSON:')), None)
	assert line is not None, f'boot script never printed its result - stdout:\n{proc.stdout}'
	result = json.loads(line[len('RESULT_JSON:'):])

	assert result['mode'] == 'remote'
	assert result['is_remote'] is True
	assert result['key_count'] > 0
	assert result['temperature'] is not None and '74' in result['temperature']
	assert result['is_realtime'] is True
