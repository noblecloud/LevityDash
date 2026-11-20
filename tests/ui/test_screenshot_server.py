"""The loopback screenshot server answers a PNG of the dashboard."""
import socket
import threading
import urllib.request

import time


def pump(app, seconds):
	end = time.monotonic() + seconds
	while time.monotonic() < end:
		app.processEvents()
		time.sleep(0.005)


def _free_port():
	with socket.socket() as s:
		s.bind(('127.0.0.1', 0))
		return s.getsockname()[1]


def _get(port, path, out):
	try:
		with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}', timeout=15) as r:
			out.append((r.status, r.read()))
	except Exception as e:  # noqa: BLE001
		out.append((0, str(e).encode()))


def test_both_modes_answer_a_png(dashboard):
	from LevityDash.lib.ui.frontends.PySide.screenshot import start
	port = _free_port()
	server = start(dashboard.app.main_window, port)
	try:
		for path in ('/screenshot', '/screenshot?mode=window&scale=0.5'):
			out = []
			t = threading.Thread(target=_get, args=(port, path, out))
			t.start()
			while t.is_alive():
				pump(dashboard.app, 0.05)
			status, body = out[0]
			assert status == 200, body
			assert body[:8] == b'\x89PNG\r\n\x1a\n'
	finally:
		server.shutdown()
