"""Regression test: a mode=remote Realtime display must split a measurement's
value and unit into separate text boxes, exactly like live mode does.

Realtime.py's `measurement`/`icon`/`unitText` properties each checked
`isinstance(value, ObservationValue)` to unwrap the container's raw value
before doing anything measurement-aware (unit_string, showUnit, withoutUnit).
`ObservationValue` is the live-mode wrapper (lib/plugins/observation.py);
mode=remote uses a separate, unrelated wrapper - `RemoteObservationValue`
(lib/wire/containers.py) - deliberately not a subclass (it avoids
ObservationValue's schema/source/container-coupled constructor). Because the
isinstance check didn't recognize it, a wire-sourced value never got
unwrapped: `unit_string`/`hasUnit`/`showUnit` all read as empty/None (falsy),
which hid the separate unit box - and the value box fell through to Realtime
.py's generic `str(measurement)` fallback, which happens to bake the unit
into the string via the wrapped measurement's own __str__. Net effect: any
showUnit=True measurement (e.g. wind speed) rendered as "3.6 mph" merged into
one giant text box in mode=remote, instead of "3.6" + a separate smaller
"mph" label - reported live as "the units aren't where they're supposed" and
traced to "started when the data had to be encoded for over the wire".

Same subprocess-boot rationale as test_remote_boot.py (PluginValueDirectory
is a process-wide singleton).
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
	from datetime import datetime, timezone

	from LevityDash import LevityDashboard

	from LevityDash.lib.wire.server import WireServer
	from LevityDash.lib.wire.messages import encode_update_message

	server = WireServer(host='127.0.0.1', port={port})
	loop = asyncio.new_event_loop()

	def serve():
		asyncio.set_event_loop(loop)
		loop.run_until_complete(server.start())
		loop.run_forever()

	threading.Thread(target=serve, daemon=True).start()

	def wind_speed_dict(value):
		return {{
			'value': {{'__type__': 'measurement', 'value': value, 'unit': 'mph', 'cls': 'MilesPerHour'}},
			'timestamp': {{'__type__': 'datetime', 'value': datetime.now(timezone.utc).isoformat()}},
			'title': 'Wind Speed',
			'metadata': {{'type': 'value'}},
			'icon_alias': None,
			'flags': {{
				'isRealtime': True, 'isRealtimeApproximate': False, 'isForecast': True,
				'isTimeseries': True, 'isDaily': False, 'isDailyForecast': False,
				'isDailyOnly': False, 'isTimeseriesOnly': False,
			}},
		}}

	def broadcast(value):
		message = encode_update_message(
			name='OpenMeteo', defaultFor=(), enabled=True, running=True,
			updates={{'environment.wind.speed.speed': wind_speed_dict(value)}},
		)
		asyncio.run_coroutine_threadsafe(server.broadcast(message), loop)

	broadcast(4.1)

	LevityDashboard.init()
	from LevityDash.lib.config import userConfig
	userConfig.set('QtOptions', 'openGL', 'False')
	LevityDashboard.plugins.load_all()
	app = LevityDashboard.app

	from PySide6.QtCore import QTimer
	QTimer.singleShot(3000, app.quit)
	threading.Timer(45, lambda: os._exit(2)).start()
	app.start()

	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime import Realtime
	from LevityDash.lib.plugins.categories import CategoryItem

	scene = LevityDashboard.scene
	target = next(
		(i for i in scene.items() if isinstance(i, Realtime) and str(getattr(i, 'key', '')) == 'environment.wind.speed.speed'),
		None,
	)
	result = {{'found': target is not None}}
	if target is not None:
		display = target.display
		result['value_text'] = display.valueTextBox.textBox.text
		result['unit_text'] = display.unitTextBox.textBox.text
		result['unit_box_visible'] = display.unitTextBox.isVisible()
	print('RESULT_JSON:' + json.dumps(result))
	sys.stdout.flush()
	sys.stderr.flush()
	os._exit(0)
""")


def _free_port() -> int:
	with socket.socket() as s:
		s.bind(('127.0.0.1', 0))
		return s.getsockname()[1]


def test_remote_mode_splits_value_and_unit_into_separate_boxes():
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
	assert 'Traceback' not in proc.stderr, f'exceptions during remote boot:\n{proc.stderr}'

	line = next((l for l in proc.stdout.splitlines() if l.startswith('RESULT_JSON:')), None)
	assert line is not None, f'boot script never printed its result - stdout:\n{proc.stdout}'
	result = json.loads(line[len('RESULT_JSON:'):])

	assert result['found'], 'wind speed Realtime display not found in scene'
	assert result['value_text'] == '4.1', f'value box should be bare, got {result["value_text"]!r}'
	assert result['unit_text'] == 'mph', f'unit box should hold the unit, got {result["unit_text"]!r}'
	assert result['unit_box_visible'] is True
