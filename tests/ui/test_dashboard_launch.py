"""`--dashboard PATH` and the local handoff: a second process shows a file in the running window.

The client half (`control.request`) blocks on a plain socket, so a test that calls it in the same thread as
the Qt server would deadlock. `call` runs the client in a thread and pumps Qt events here, which is what the
two real processes do.
"""
import json
import os
import threading
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from LevityDash import LevityDashboard
from LevityDash.lib.ui.frontends.PySide import control
from LevityDash.lib.ui.frontends.PySide.control_server import ControlServer

DASHBOARD = """- type: group
  name: handoff
  items:
    - {type: text, text: 'handed over', geometry: {x: 5%, y: 5%, width: 40%, height: 20%}}
"""


@pytest.fixture
def socketDir(tmp_path, monkeypatch):
	# A short path under /tmp, not pytest's tmp_path: AF_UNIX paths are limited to ~104 bytes and the
	# per-test directory pytest builds is longer than that on macOS.
	path = Path('/tmp') / f'lv-test-{os.getpid()}-{tmp_path.name[-6:]}.sock'
	monkeypatch.setenv('LEVITYDASH_CONTROL_SOCKET', str(path))
	yield path
	path.unlink(missing_ok=True)


@pytest.fixture
def server(dashboard, socketDir):
	controlServer = ControlServer()
	assert controlServer.listen(), 'the test socket could not be listened on'
	yield controlServer
	controlServer.close()


@pytest.fixture
def panel(dashboard):
	central = LevityDashboard.CENTRAL_PANEL
	saved = central.filePath
	yield central
	central.filePath = saved


def call(dashboard, payload: dict, timeout: float = 10.0) -> dict:
	"""Talk to the server from a real socket on another thread, pumping Qt events until the answer arrives."""
	box = {}

	def run():
		box['reply'] = control.request(payload, timeout=timeout)

	worker = threading.Thread(target=run, daemon=True)
	worker.start()
	deadline = time.time() + timeout
	while worker.is_alive() and time.time() < deadline:
		dashboard.app.processEvents()
		# The server only reads on its own event loop, so the pump is what makes the exchange happen.
		time.sleep(0.01)
	worker.join(timeout=1)
	reply = box.get('reply')
	assert reply is not None, 'the server answered nothing'
	return reply


def test_the_socket_path_does_not_come_from_tmpdir(monkeypatch):
	monkeypatch.delenv('LEVITYDASH_CONTROL_SOCKET', raising=False)
	monkeypatch.setenv('TMPDIR', '/var/folders/somewhere/T/')
	assert control.socketPath() == f'/tmp/levitydash-{os.getuid()}.sock'
	monkeypatch.setenv('LEVITYDASH_CONTROL_SOCKET', '/tmp/an-explicit.sock')
	assert control.socketPath() == '/tmp/an-explicit.sock'


def test_the_flag_is_parsed_and_a_prefix_is_not(monkeypatch):
	parsed = LevityDashboard.args.parse_known_args(['--dashboard', 'x.levity'])[0]
	assert parsed.dashboard == 'x.levity'
	# `allow_abbrev=False`: a prefix must not silently become the flag.
	assert LevityDashboard.args.parse_known_args(['--dash', 'x.levity'])[0].dashboard is None


def test_a_relative_path_resolves_against_the_client(monkeypatch, tmp_path):
	monkeypatch.chdir(tmp_path)
	(tmp_path / 'here.levity').write_text(DASHBOARD)
	assert control.resolveDashboardArgument('here.levity') == (tmp_path / 'here.levity').resolve()


def test_status_names_the_loaded_file(server, dashboard, panel):
	reply = call(dashboard, {'cmd': 'status'})
	assert reply['ok'] is True
	assert reply['window'].startswith('Levity Dashboard - ')


def test_open_hands_the_file_to_the_running_window(server, dashboard, panel, tmp_path):
	target = tmp_path / 'handed-over.levity'
	target.write_text(DASHBOARD)

	reply = call(dashboard, {'cmd': 'open', 'dashboard': str(target), 'window': 'current'})

	assert reply['ok'] is True, reply
	assert reply['dashboard'] == str(target)
	assert reply['window'] == 'Levity Dashboard - handed-over.levity'
	assert any('handed over' in (text.text or '') for text in dashboard.texts())


def test_open_with_a_missing_file_answers_without_a_dialog(server, dashboard, monkeypatch, tmp_path):
	def boom(*a, **k):
		raise AssertionError('a refused handoff opened a modal dialog')
	monkeypatch.setattr(QMessageBox, 'critical', boom)

	reply = call(dashboard, {'cmd': 'open', 'dashboard': str(tmp_path / 'gone.levity')})

	assert reply['ok'] is False
	assert 'not a file' in reply['error']


def test_open_with_a_relative_path_is_refused(server, dashboard):
	reply = call(dashboard, {'cmd': 'open', 'dashboard': 'relative.levity'})
	assert reply['ok'] is False
	assert 'absolute' in reply['error']


def test_a_second_window_is_not_implemented_yet(server, dashboard):
	reply = call(dashboard, {'cmd': 'status', 'window': 'new'})
	assert reply['ok'] is False
	assert 'not available yet' in reply['error']


def test_unknown_command_lists_the_known_ones(server, dashboard):
	reply = call(dashboard, {'cmd': 'quit'})
	assert reply['ok'] is False
	assert 'open' in reply['error']


def test_nothing_listening_means_start_a_process(monkeypatch, tmp_path):
	monkeypatch.setenv('LEVITYDASH_CONTROL_SOCKET', str(tmp_path / 'absent.sock'))
	assert control.request({'cmd': 'status'}, timeout=0.5) is None
