"""`--dashboard PATH` and the local handoff: a second process shows a file in the running window.

The client half (`control.request`) blocks on a plain socket, so a test that calls it in the same thread as
the Qt server would deadlock. `call` runs the client in a thread and pumps Qt events here, which is what the
two real processes do.
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from LevityDash import LevityDashboard
from LevityDash import __main__ as entry
from LevityDash.lib.ui.frontends.PySide import control, screenshotPort
from LevityDash.lib.ui.frontends.PySide.control_server import ControlServer

DASHBOARD = """- type: group
  name: handoff
  items:
    - {type: text, text: 'handed over', geometry: {x: 5%, y: 5%, width: 40%, height: 20%}}
"""


@pytest.fixture(autouse=True)
def cleanRegistrations():
	"""The registration registry is module state; a registered window must not leak into the next test."""
	control._REGISTERED.clear()
	yield
	control._REGISTERED.clear()


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
def idServer(dashboard, monkeypatch, tmp_path):
	"""A server on a test-private *id* path: no env override, so the id is what tells two windows apart.

	`tmp_path` is only used for a unique id: the socket path itself has to stay short for AF_UNIX.
	"""
	monkeypatch.delenv('LEVITYDASH_CONTROL_SOCKET', raising=False)
	monkeypatch.setattr(control, '_SOCKET_ID', f't{os.getpid()}{tmp_path.name[-4:]}')
	controlServer = ControlServer()
	assert controlServer.listen(), 'the test socket could not be listened on'
	yield controlServer
	controlServer.close()
	Path(control.socketPath()).unlink(missing_ok=True)


@pytest.fixture
def panel(dashboard):
	central = LevityDashboard.CENTRAL_PANEL
	saved = central.filePath
	yield central
	central.filePath = saved


def run_pumping(dashboard, function, timeout: float = 10.0):
	"""Run `function` on another thread and pump Qt events here until it returns, as the two processes do."""
	box = {}
	error = {}

	def run():
		try:
			box['result'] = function()
		except BaseException as e:  # noqa: BLE001 - re-raised on the test thread
			error['error'] = e

	worker = threading.Thread(target=run, daemon=True)
	worker.start()
	deadline = time.time() + timeout
	while worker.is_alive() and time.time() < deadline:
		dashboard.app.processEvents()
		# The server only reads on its own event loop, so the pump is what makes the exchange happen.
		time.sleep(0.01)
	worker.join(timeout=1)
	if 'error' in error:
		raise error['error']
	return box.get('result')


def call(dashboard, payload: dict, timeout: float = 10.0, path: str | None = None) -> dict:
	"""Talk to the server from a real socket on another thread, pumping Qt events until the answer arrives."""
	reply = run_pumping(dashboard, lambda: control.request(payload, timeout=timeout, path=path), timeout)
	assert reply is not None, 'the server answered nothing'
	return reply


def test_the_socket_path_does_not_come_from_tmpdir(monkeypatch):
	monkeypatch.delenv('LEVITYDASH_CONTROL_SOCKET', raising=False)
	monkeypatch.setenv('TMPDIR', '/var/folders/somewhere/T/')
	monkeypatch.setattr(control, '_SOCKET_ID', None)
	assert control.socketPath() == f'/tmp/levitydash-{os.getuid()}.sock'
	monkeypatch.setenv('LEVITYDASH_CONTROL_SOCKET', '/tmp/an-explicit.sock')
	assert control.socketPath() == '/tmp/an-explicit.sock'


def test_a_second_instance_names_its_socket_and_the_primary_keeps_the_plain_one(monkeypatch):
	monkeypatch.delenv('LEVITYDASH_CONTROL_SOCKET', raising=False)
	monkeypatch.setattr(control, '_SOCKET_ID', None)
	primary = control.socketPath()
	child = control.socketPath(id='w4242')
	assert primary == f'/tmp/levitydash-{os.getuid()}.sock'
	assert child == f'/tmp/levitydash-{os.getuid()}-w4242.sock'
	assert control.primarySocketPath() == primary
	# `--new-instance` sets the id for the process, so every listener and client half agrees on the path.
	control.setSocketId('w4242')
	try:
		assert control.socketPath() == child
		assert control.primarySocketPath() == primary
	finally:
		control.setSocketId(None)


def test_the_flag_is_parsed_and_a_prefix_is_not(monkeypatch):
	parsed = LevityDashboard.args.parse_known_args(['--dashboard', 'x.levity'])[0]
	assert parsed.dashboard == 'x.levity'
	# `allow_abbrev=False`: a prefix must not silently become the flag.
	assert LevityDashboard.args.parse_known_args(['--dash', 'x.levity'])[0].dashboard is None


def test_new_instance_and_window_id_are_parsed():
	parsed = LevityDashboard.args.parse_known_args(['--new-instance', '--window-id', 'desk'])[0]
	assert parsed.new_instance is True
	assert parsed.window_id == 'desk'
	parsed = LevityDashboard.args.parse_known_args([])[0]
	assert parsed.new_instance is False
	assert parsed.window_id is None


def test_the_window_id_is_the_flag_then_the_file_name():
	assert entry._windowId(Path('/tmp/desk two.levity'), 'Left Monitor') == 'left-monitor'
	assert entry._windowId(Path('/tmp/desk two.levity')) == 'desk-two'
	assert entry._slug('---') == 'window'
	assert entry._slug('a' * 40) == 'a' * 24


def test_a_relative_path_resolves_against_the_client(monkeypatch, tmp_path):
	monkeypatch.chdir(tmp_path)
	(tmp_path / 'here.levity').write_text(DASHBOARD)
	assert control.resolveDashboardArgument('here.levity') == (tmp_path / 'here.levity').resolve()


def test_status_names_the_loaded_file(server, dashboard, panel):
	reply = call(dashboard, {'cmd': 'status'})
	assert reply['ok'] is True
	assert reply['window'].startswith('Levity Dashboard - ')


def test_status_lists_the_one_window_with_every_field(server, dashboard, panel):
	reply = call(dashboard, {'cmd': 'status'})
	windows = reply['windows']
	assert len(windows) == 1, windows
	window = windows[0]
	assert set(window) == {'id', 'title', 'dashboard', 'screen', 'pid'}
	assert window['id'] == 'main'
	assert window['pid'] == os.getpid()
	assert window['title'] == reply['window']
	# The top-level fields stay, so a client written against v1 keeps working.
	assert window['dashboard'] == reply['dashboard']


def test_open_hands_the_file_to_the_running_window(server, dashboard, panel, tmp_path):
	target = tmp_path / 'handed-over.levity'
	target.write_text(DASHBOARD)

	reply = call(dashboard, {'cmd': 'open', 'dashboard': str(target), 'window': 'current'})

	assert reply['ok'] is True, reply
	assert reply['dashboard'] == str(target)
	assert reply['window'] == 'Levity Dashboard - handed-over.levity'
	assert reply['windows'][0]['dashboard'] == str(target)
	assert any('handed over' in (text.text or '') for text in dashboard.texts())


def test_open_accepts_main_as_the_window(server, dashboard, panel, tmp_path):
	target = tmp_path / 'main-window.levity'
	target.write_text(DASHBOARD)
	reply = call(dashboard, {'cmd': 'open', 'dashboard': str(target), 'window': 'main'})
	assert reply['ok'] is True, reply


def test_open_with_a_missing_file_answers_not_found_without_a_dialog(server, dashboard, monkeypatch, tmp_path):
	def boom(*a, **k):
		raise AssertionError('a refused handoff opened a modal dialog')
	monkeypatch.setattr(QMessageBox, 'critical', boom)

	reply = call(dashboard, {'cmd': 'open', 'dashboard': str(tmp_path / 'gone.levity')})

	assert reply['ok'] is False
	assert reply['error']['code'] == 'not_found'
	assert 'not a file' in reply['error']['message']


def test_open_with_a_relative_path_is_bad_request(server, dashboard):
	reply = call(dashboard, {'cmd': 'open', 'dashboard': 'relative.levity'})
	assert reply['ok'] is False
	assert reply['error']['code'] == 'bad_request'
	assert 'absolute' in reply['error']['message']


def test_open_with_window_new_is_not_implemented(server, dashboard, tmp_path):
	target = tmp_path / 'second.levity'
	target.write_text(DASHBOARD)
	reply = call(dashboard, {'cmd': 'open', 'dashboard': str(target), 'window': 'new'})
	assert reply['ok'] is False
	assert reply['error']['code'] == 'not_implemented'
	assert 'not available yet' in reply['error']['message']


def test_an_unknown_window_name_is_bad_request(server, dashboard):
	reply = call(dashboard, {'cmd': 'status', 'window': 'third'})
	assert reply['ok'] is False
	assert reply['error']['code'] == 'bad_request'


def test_a_second_window_is_not_implemented_yet(server, dashboard):
	reply = call(dashboard, {'cmd': 'status', 'window': 'new'})
	assert reply['ok'] is False
	assert reply['error']['code'] == 'not_implemented'
	assert 'not available yet' in reply['error']['message']


def test_unknown_command_lists_the_known_ones(server, dashboard):
	reply = call(dashboard, {'cmd': 'quit'})
	assert reply['ok'] is False
	assert reply['error']['code'] == 'bad_request'
	assert 'open' in reply['error']['message']


# `close` and `workspace` are implemented (see tests/ui/test_workspace.py); these three are still names only.
@pytest.mark.parametrize('command', ['list', 'focus', 'move'])
def test_the_reserved_commands_answer_not_implemented(server, dashboard, command):
	reply = call(dashboard, {'cmd': command})
	assert reply['ok'] is False
	assert reply['error']['code'] == 'not_implemented'
	assert command in reply['error']['message']


def test_the_exit_code_follows_the_error_code():
	assert control.exitCode({'ok': True}) == 0
	assert control.exitCode(None) == 1
	assert control.exitCode({'ok': False, 'error': {'code': 'not_found', 'message': ''}}) == 3
	assert control.exitCode({'ok': False, 'error': {'code': 'bad_request', 'message': ''}}) == 4
	assert control.exitCode({'ok': False, 'error': {'code': 'not_implemented', 'message': ''}}) == 5
	assert control.exitCode({'ok': False, 'error': {'code': 'busy', 'message': ''}}) == 6
	# A code this client does not know is still a failure, not a success.
	assert control.exitCode({'ok': False, 'error': {'code': 'invented', 'message': ''}}) == 1
	assert control.exitCode({'ok': False, 'error': 'the v1 string'}) == 1


def test_the_cli_exits_with_the_code_from_the_reply(server, dashboard, tmp_path, capsys):
	assert run_pumping(dashboard, lambda: control.main(['status'])) == 0
	missing = tmp_path / 'not-here.levity'
	assert run_pumping(dashboard, lambda: control.main(['open', str(missing)])) == 3
	assert run_pumping(dashboard, lambda: control.main(['quit'])) == 4
	assert run_pumping(dashboard, lambda: control.main(['focus'])) == 5
	# The probe prints the reply for a script to read, whatever the exit status.
	printed = capsys.readouterr().out
	assert '"code": "not_found"' in printed


def test_no_wait_writes_the_request_and_returns_without_the_reply(server, dashboard, panel, tmp_path):
	target = tmp_path / 'no-wait.levity'
	target.write_text(DASHBOARD.replace('handed over', 'no wait needed'))

	started = time.monotonic()
	code = run_pumping(dashboard, lambda: control.main(['open', str(target), '--no-wait']))
	elapsed = time.monotonic() - started

	assert code == 0
	assert elapsed < 5, 'the client waited for the window'
	# The request is in the window's queue: the load it asked for still happens, just after the client left.
	dashboard.wait_until(lambda: any('no wait needed' in (t.text or '') for t in dashboard.texts()), timeout=10)
	assert panel._path(panel.loadedFile) == target


def test_nothing_listening_means_start_a_process(monkeypatch, tmp_path):
	monkeypatch.setenv('LEVITYDASH_CONTROL_SOCKET', str(tmp_path / 'absent.sock'))
	assert control.request({'cmd': 'status'}, timeout=0.5) is None
	assert control.main(['status']) == 1
	assert control.main(['status', '--no-wait']) == 1


def test_a_second_instance_does_not_take_the_primary_socket(idServer, dashboard, monkeypatch):
	primary = control.socketPath()
	monkeypatch.setattr(control, '_SOCKET_ID', 'w4242')
	assert control.socketPath() != primary
	# The primary still answers on its own socket — asked by path, the way the child asks for `status`.
	reply = call(dashboard, {'cmd': 'status'}, path=primary)
	assert reply['ok'] is True
	assert reply['windows'][0]['id'] == 'main'


def test_a_second_instance_registers_and_the_primary_lists_it(idServer, dashboard, monkeypatch):
	primary = control.socketPath()
	monkeypatch.setattr(control, 'primarySocketPath', lambda: primary)
	monkeypatch.setattr(control, '_SOCKET_ID', 'w4242')
	child = {'id': 'w4242', 'title': 'Levity Dashboard - child.levity', 'dashboard': '/tmp/child.levity', 'screen': None, 'pid': os.getpid()}
	assert run_pumping(dashboard, lambda: control.announceSecondary(child)) is True, 'the primary refused the registration'

	reply = call(dashboard, {'cmd': 'status'}, path=primary)
	ids = [window['id'] for window in reply['windows']]
	assert ids == ['main', 'w4242'], reply['windows']
	assert reply['windows'][1]['dashboard'] == '/tmp/child.levity'
	# A save in a sibling is worth a log line; this window's own entry must not count as the sibling.
	assert run_pumping(dashboard, lambda: control.otherWindowHasOpen('/tmp/other.levity')) is False
	# Everything above happens in one process, so the child's pid *is* this one: it is not another window.
	assert run_pumping(dashboard, lambda: control.otherWindowHasOpen('/tmp/child.levity')) is False


def test_the_primary_asks_itself_nothing(server, dashboard):
	# The primary has no siblings, and must not block on its own socket from the thread that answers it.
	assert control.otherWindowHasOpen('/tmp/x.levity') is False
	assert control.announceSecondary({'id': 'x', 'pid': os.getpid()}) is False


def test_a_registered_window_puts_the_shared_save_in_the_log(server, dashboard):
	# A child registered with this process: the primary can see it without asking anyone (no socket I/O).
	sibling = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
	try:
		control._REGISTERED['child'] = {'id': 'child', 'dashboard': '/tmp/shared.levity', 'pid': sibling.pid}
		assert control.otherWindowHasOpen('/tmp/shared.levity') is True
		assert control.otherWindowHasOpen('/tmp/another.levity') is False
	finally:
		sibling.kill()
		sibling.wait()
	# A registration left behind by a process that is gone is not a sibling any more.
	control._REGISTERED['gone'] = {'id': 'gone', 'dashboard': '/tmp/gone.levity', 'pid': sibling.pid}
	assert control.otherWindowHasOpen('/tmp/gone.levity') is False


def test_a_second_instance_warns_about_the_double_plugin_load(capsys):
	entry.warnSecondInstance(f'/tmp/levitydash-{os.getuid()}-desk.sock')
	message = capsys.readouterr().err
	assert '--new-instance' in message
	assert 'loads the plugins a second time' in message
	assert 'polls every API twice' in message
	assert f'-desk.sock' in message


def test_the_screenshot_server_is_off_in_a_second_instance():
	# A second instance cannot take the first window's port, and a random one is unguessable: it is off.
	assert screenshotPort(8671, True) == 0
	assert screenshotPort(8671, False) == 8671
	assert screenshotPort(0, True) == 0


def test_the_reply_version_bumped(server, dashboard):
	reply = call(dashboard, {'cmd': 'ping'})
	assert reply['v'] == 2
	assert json.dumps(reply)  # a plain-JSON reply, as every client expects
