"""The workspace file, `--workspace`, repeated `--window`, and one process per window.

Most of this needs no Qt at all: the file half is `workspace.py`, which is Qt-free on purpose so a child that
only spawns its siblings never builds a `QApplication`. The four tests that talk to the control socket reuse
the headless app from `tests/conftest.py`, and the client call is made on a thread while Qt events are pumped
here, exactly as two real processes do it.
"""
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from LevityDash import LevityDashboard
from LevityDash import __main__ as entry
from LevityDash.lib.ui.frontends.PySide import control, workspace

DESK = """\
name: desk
theme: dusk
windows:
  - id: main
    dashboard: home.levity
    screen: {name: "DELL U2720Q", fallback: primary}
    geometry: {x: 0, y: 0, width: 50%, height: 100%}
    mode: windowed
  - id: right
    dashboard: /tmp/right.levity
    screen: Side Monitor
"""


@pytest.fixture(autouse=True)
def cleanWorkspace():
	"""The workspace registry and the close callback are module state: neither may leak into the next test."""
	workspace.clear()
	control._REGISTERED.clear()
	control.setCloseWindow(None)
	yield
	workspace.clear()
	control._REGISTERED.clear()
	control.setCloseWindow(None)


@pytest.fixture
def socketDir(tmp_path, monkeypatch):
	# Short, under /tmp: AF_UNIX paths are limited to ~104 bytes and pytest's tmp_path is longer on macOS.
	path = Path('/tmp') / f'lv-ws-{os.getpid()}-{tmp_path.name[-6:]}.sock'
	monkeypatch.setenv('LEVITYDASH_CONTROL_SOCKET', str(path))
	yield path
	path.unlink(missing_ok=True)


@pytest.fixture
def server(dashboard, socketDir):
	from LevityDash.lib.ui.frontends.PySide.control_server import ControlServer

	controlServer = ControlServer()
	assert controlServer.listen(), 'the test socket could not be listened on'
	yield controlServer
	controlServer.close()


def run_pumping(dashboard, function, timeout: float = 10.0):
	"""Run `function` on another thread and pump Qt events here until it returns."""
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
		time.sleep(0.01)
	worker.join(timeout=1)
	if 'error' in error:
		raise error['error']
	return box.get('result')


def call(dashboard, payload: dict, timeout: float = 10.0) -> dict:
	reply = run_pumping(dashboard, lambda: control.request(payload, timeout=timeout), timeout)
	assert reply is not None, 'the server answered nothing'
	return reply


class FakeProcess:
	"""A child process that is already gone, so `spawn` records the call and its watcher reports at once."""

	pid = 4242

	def __init__(self, returncode=0):
		self.returncode = returncode

	def poll(self):
		return self.returncode

	def wait(self):
		return self.returncode


# ---------------------------------------------------------------------------------------------------------------------
# The file


def test_the_file_parses_every_field(tmp_path):
	path = tmp_path / 'desk.yaml'
	path.write_text(DESK)

	parsed = workspace.load(path)

	assert parsed.name == 'desk'
	assert parsed.theme == 'dusk'
	assert parsed.path == path.absolute()
	assert [window.id for window in parsed.windows] == ['main', 'right']
	main, right = parsed.windows
	assert main.dashboard == 'home.levity'
	assert main.screen.name == 'DELL U2720Q'
	assert main.screen.fallback == 'primary'
	assert main.geometry.width == 0.5
	assert main.geometry.height == 1.0
	assert main.mode == 'windowed'
	assert main.modeName == 'windowed'
	# A window that says nothing about its screen keeps no geometry and no mode: nothing is invented for it.
	assert right.dashboard == '/tmp/right.levity'
	assert right.screen.name == 'Side Monitor'
	assert right.screen.fallback is None
	assert right.geometry is None
	assert right.mode is None
	assert right.modeName == 'windowed'


def test_the_name_defaults_to_the_file_stem(tmp_path):
	path = tmp_path / 'corner-desk.yaml'
	path.write_text('windows:\n  - id: main\n    dashboard: home.levity\n')

	assert workspace.load(path).name == 'corner-desk'


def test_a_resolved_name_lives_under_the_config(tmp_path, monkeypatch):
	monkeypatch.setattr(workspace, 'directory', lambda: tmp_path)
	(tmp_path / 'desk.yaml').write_text('name: desk\nwindows:\n  - id: main\n    dashboard: x.levity\n')

	assert workspace.resolve('desk') == tmp_path / 'desk.yaml'
	# A path (a separator, a suffix, or absolute) is taken as it is written, never looked up by name.
	assert workspace.resolve('sub/desk.yaml') == Path('sub/desk.yaml').absolute()
	assert workspace.resolve('/tmp/desk.yaml') == Path('/tmp/desk.yaml')


@pytest.mark.parametrize(
	'text, key, fragment',
	[
		('workspaces: []\n', 'workspaces', 'unknown key'),
		('[]\n', None, 'top level'),
		('windows: []\n', 'windows', 'non-empty'),
		('windows:\n  - id: a\n', 'dashboard', 'dashboard'),
		('windows:\n  - dashboard: a.levity\n', 'id', 'id is required'),
		('windows:\n  - id: a\n    dashboard: a.levity\n    position: 1\n', 'position', 'unknown key'),
		('windows:\n  - id: a\n    dashboard: a.levity\n    screen: {label: x}\n', 'label', 'unknown key'),
		('windows:\n  - id: a\n    dashboard: a.levity\n    geometry: {depth: 1}\n', 'depth', 'unknown key'),
		('windows:\n  - id: a\n    dashboard: a.levity\n    geometry: {width: 120}\n', 'width', 'fraction between 0 and 1'),
		('windows:\n  - id: a\n    dashboard: a.levity\n    mode: cinema\n', 'mode', 'cinema'),
		('windows:\n  - id: a\n    dashboard: a.levity\n  - id: a\n    dashboard: b.levity\n', 'id', 'used twice'),
		('theme: 3\nwindows:\n  - id: a\n    dashboard: a.levity\n', 'theme', 'theme must be'),
	],
)
def test_a_bad_file_is_refused_with_the_key_named(text, key, fragment, tmp_path):
	path = tmp_path / 'bad.yaml'
	path.write_text(text)

	with pytest.raises(workspace.WorkspaceError) as info:
		workspace.load(path)

	assert fragment in str(info.value)
	assert info.value.key == key
	# The error names the file, not just the problem: a launch has several of these open.
	assert str(path) in str(info.value) or 'top level' in str(info.value)


def test_geometry_takes_percentages_and_fractions(tmp_path):
	path = tmp_path / 'desk.yaml'
	path.write_text('windows:\n  - id: main\n    dashboard: x.levity\n    geometry: {x: 50%, y: 0.25, width: 100%, height: 0.5}\n')

	geometry = workspace.load(path).windows[0].geometry

	assert (geometry.x, geometry.y, geometry.width, geometry.height) == (0.5, 0.25, 1.0, 0.5)
	# The pixels it means are the fractions of the screen's available area, clamped to it.
	assert workspace.Geometry(0.5, 0.0, 0.5, 1.0).pixels((0, 0, 1920, 1080)) == (960, 0, 960, 1080)
	# A window that would hang off the right edge is pushed back inside the screen instead.
	assert workspace.Geometry(x=0.9, y=0.0, width=0.5, height=1.0).pixels((0, 0, 100, 100)) == (50, 0, 50, 100)


def test_geometry_round_trips_through_the_writer(tmp_path):
	path = tmp_path / 'desk.yaml'
	path.write_text(DESK)
	geometry = workspace.Geometry(x=0.25, y=0.5, width=0.5, height=0.5)

	assert workspace.saveWindow(path, 'main', screen='Studio Display', geometry=geometry) is True

	after = workspace.load(path)
	main = after.window('main')
	assert main.geometry == geometry
	assert main.screen.name == 'Studio Display'
	# The fallback the file had is kept: only the name changed.
	assert main.screen.fallback == 'primary'
	# Nothing else moved: same windows, same order, same dashboards, same name and theme.
	assert [window.id for window in after.windows] == ['main', 'right']
	assert [window.dashboard for window in after.windows] == ['home.levity', '/tmp/right.levity']
	assert (after.name, after.theme) == ('desk', 'dusk')
	# And the file is still a workspace: it loads through the same strict parser it was written by.
	assert workspace.dump(after) == workspace.dump(workspace.load(path))


def test_a_screen_the_file_does_not_know_is_left_alone(tmp_path):
	path = tmp_path / 'desk.yaml'
	path.write_text(DESK)

	# Geometry written back for a window whose screen did not change: the saved name survives.
	assert workspace.saveWindow(path, 'right', geometry=workspace.Geometry(0.5, 0.0, 0.5, 1.0)) is True

	assert workspace.load(path).window('right').screen.name == 'Side Monitor'


def test_saving_a_window_the_file_does_not_have_changes_nothing(tmp_path, capsys):
	path = tmp_path / 'desk.yaml'
	path.write_text(DESK)

	assert workspace.saveWindow(path, 'nowhere', geometry=workspace.Geometry(0, 0, 1, 1)) is False

	assert 'no window' in capsys.readouterr().err
	assert workspace.load(path).windows[0].geometry.width == 0.5


# ---------------------------------------------------------------------------------------------------------------------
# Screens


def test_a_missing_screen_falls_back_and_keeps_its_saved_name(tmp_path):
	path = tmp_path / 'desk.yaml'
	path.write_text(DESK)
	window = workspace.load(path).windows[0]

	# Not attached: the fallback answers, which here is the primary screen.
	assert workspace.chooseScreen(window.screen, ['Built-in Retina Display']) == 'primary'
	# The plan still names the monitor the layout was written for, so nothing rewrites the file on quit.
	assert workspace.Launch.fromWindow(window).describe()['screen'] == 'DELL U2720Q'
	# A fallback naming another attached screen is used by name, and an attached primary name wins directly.
	assert workspace.chooseScreen(workspace.Screen('GONE', 'Studio Display'), ['Studio Display']) == 'Studio Display'
	assert workspace.chooseScreen(workspace.Screen('Studio Display'), ['Studio Display', 'Built-in']) == 'Studio Display'
	# Neither the name nor the fallback is attached: primary, still without touching the name.
	assert workspace.chooseScreen(workspace.Screen('GONE', 'ALSO GONE'), ['Built-in']) == 'primary'
	assert workspace.chooseScreen(None, ['Built-in']) is None


# ---------------------------------------------------------------------------------------------------------------------
# The command line


def test_the_window_flag_keeps_the_order_given(tmp_path, monkeypatch):
	monkeypatch.chdir(tmp_path)
	for name in ('first.levity', 'second.levity'):
		(tmp_path / name).write_text('[]\n')

	parsed = LevityDashboard.args.parse_known_args(['--window', 'first.levity', '--window', 'second.levity'])[0]
	assert parsed.window == ['first.levity', 'second.levity']

	active = entry._resolveWorkspace(SimpleNamespace(parsed_args=parsed))

	assert [Path(window.dashboard).name for window in active.windows] == ['first.levity', 'second.levity']
	# An unsaved workspace: no ids and no geometry to write anywhere.
	assert all(window.id is None and window.geometry is None for window in active.windows)
	assert active.path is None


def test_workspace_and_window_together_are_refused():
	args = SimpleNamespace(workspace='desk', window=['a.levity'], dashboard=None)

	with pytest.raises(SystemExit) as info:
		entry._resolveWorkspace(SimpleNamespace(parsed_args=args))

	assert info.value.code == 4  # bad_request


def test_a_workspace_that_is_not_a_file_is_reported(monkeypatch, tmp_path, capsys):
	monkeypatch.setattr(workspace, 'directory', lambda: tmp_path)
	args = SimpleNamespace(workspace='desk', window=None, dashboard=None)

	with pytest.raises(SystemExit) as info:
		entry._resolveWorkspace(SimpleNamespace(parsed_args=args))

	assert info.value.code == 3  # not_found
	assert str(tmp_path / 'desk.yaml') in capsys.readouterr().err


def test_a_bad_workspace_file_is_refused_with_the_key_named(tmp_path):
	path = tmp_path / 'desk.yaml'
	path.write_text('windows:\n  - id: main\n    dashboard: a.levity\n    monitor: 1\n')
	args = SimpleNamespace(workspace=str(path), window=None, dashboard=None)

	with pytest.raises(SystemExit) as info:
		entry._resolveWorkspace(SimpleNamespace(parsed_args=args))

	assert info.value.code == 4


def test_a_flag_wins_over_the_configured_workspace():
	# A flag naming what to show means the configured workspace is not the answer.
	assert entry._workspaceText(SimpleNamespace(workspace=None, window=['a.levity'], dashboard=None)) is None
	assert entry._workspaceText(SimpleNamespace(workspace=None, window=None, dashboard='a.levity')) is None
	assert entry._workspaceText(SimpleNamespace(workspace='other', window=None, dashboard=None)) == 'other'


def test_the_configured_workspace_is_read_when_nothing_says_otherwise():
	from LevityDash.lib.config import userConfig

	userConfig.set('Display', 'workspace', 'desk')
	try:
		assert entry._workspaceText(SimpleNamespace(workspace=None, window=None, dashboard=None)) == 'desk'
	finally:
		userConfig.remove_option('Display', 'workspace')


# ---------------------------------------------------------------------------------------------------------------------
# Spawning one process per window


def test_the_child_argv_is_exactly_as_specced(tmp_path):
	target = tmp_path / 'right.levity'
	target.write_text('[]\n')
	window = workspace.Window(
		dashboard=str(target),
		id='right',
		screen=workspace.Screen('Studio Display', 'primary'),
		geometry=workspace.Geometry(0.5, 0.0, 0.5, 1.0),
		mode='kiosk',
	)

	assert workspace.childArgv(window, python='/usr/bin/python3') == [
		'/usr/bin/python3', '-m', 'LevityDash', '--new-instance', '--window-id', 'right', '--dashboard', str(target),
		'--screen-name', 'Studio Display', '--geometry', '0.5,0,0.5,1', '--mode', 'kiosk',
	]


def test_a_window_that_gives_nothing_passes_nothing(tmp_path):
	target = tmp_path / 'plain.levity'
	target.write_text('[]\n')

	assert workspace.childArgv(workspace.Window(dashboard=str(target), id='plain'), python='py') == [
		'py', '-m', 'LevityDash', '--new-instance', '--window-id', 'plain', '--dashboard', str(target),
	]


def test_a_relative_dashboard_is_resolved_before_the_child_sees_it(tmp_path):
	saves = tmp_path / 'saves'
	saves.mkdir()
	(saves / 'home.levity').write_text('[]\n')

	argv = workspace.childArgv(workspace.Window(dashboard='home.levity', id='main'), python='py', saves=saves)

	assert argv[argv.index('--dashboard') + 1] == str(saves / 'home.levity')


def test_spawn_puts_the_workspace_file_in_the_environment(monkeypatch, tmp_path):
	calls = []

	def fakePopen(argv, env=None):
		calls.append((argv, env))
		return FakeProcess()

	monkeypatch.setattr(workspace.subprocess, 'Popen', fakePopen)
	path = tmp_path / 'desk.yaml'
	path.write_text(DESK)
	window = workspace.load(path).windows[1]

	process = workspace.spawn(window, python='py', workspacePath=path)

	assert calls[0][0] == workspace.childArgv(window, python='py')
	assert calls[0][1][workspace.WORKSPACE_ENV] == str(path.absolute())
	assert process.pid == 4242


def test_a_child_that_exits_is_logged_once_and_never_restarted(monkeypatch, tmp_path, capsys):
	calls = []

	def fakePopen(argv, env=None):
		calls.append(argv)
		return FakeProcess(3)

	monkeypatch.setattr(workspace.subprocess, 'Popen', fakePopen)
	target = tmp_path / 'right.levity'
	target.write_text('[]\n')

	workspace.spawn(workspace.Window(dashboard=str(target), id='right'), python='py', workspacePath=tmp_path / 'desk.yaml')

	deadline = time.monotonic() + 5
	message = ''
	while time.monotonic() < deadline:
		message = capsys.readouterr().err
		if 'not restarted' in message:
			break
		time.sleep(0.02)
	assert 'window right exited (3); it is not restarted' in message
	# One process, one call: a child that dies is not a child that is retried.
	assert len(calls) == 1
	assert workspace.childPid('right') is None


def test_closing_the_primary_asks_each_child_over_its_own_socket(monkeypatch, tmp_path):
	asked = []
	child = FakeProcess()
	monkeypatch.setattr(workspace, '_CHILDREN', {'right': child})

	def fakeRequest(payload, timeout=0, path=None, wait=0):
		asked.append((payload, path))
		child.returncode = 0
		return {'ok': True}

	monkeypatch.setattr(control, 'request', fakeRequest)

	assert workspace.closeChildren(timeout=0.5) == []
	assert [payload['cmd'] for payload, _ in asked] == ['close']
	assert asked[0][1] == control.socketPath(id='right')


def test_a_child_that_will_not_close_is_left_and_named(monkeypatch, capsys):
	monkeypatch.setattr(workspace, '_CHILDREN', {'right': FakeProcess(returncode=None)})
	monkeypatch.setattr(control, 'request', lambda *a, **k: {'ok': True})

	assert workspace.closeChildren(timeout=0.1) == ['right']

	assert 'did not close within' in capsys.readouterr().err


# ---------------------------------------------------------------------------------------------------------------------
# The control command


def test_workspace_answers_the_documented_shape(server, dashboard):
	reply = call(dashboard, {'cmd': 'workspace'})

	assert reply['ok'] is True
	assert set(reply) >= {'ok', 'workspace', 'name', 'windows'}
	assert reply['workspace'] is None
	assert reply['name'] == 'main'
	assert len(reply['windows']) == 1
	window = reply['windows'][0]
	assert set(window) == {'id', 'pid', 'screen', 'geometry', 'mode'}
	assert window['id'] == 'main'
	assert window['pid'] == os.getpid()
	assert window['mode'] == 'windowed'


def test_workspace_lists_every_window_in_file_order(server, dashboard, tmp_path):
	path = tmp_path / 'desk.yaml'
	path.write_text(DESK)
	active = workspace.load(path)
	workspace.setActive(active)
	workspace.setLaunch(workspace.Launch.fromWindow(active.windows[0]))
	# The child registers itself the way a real one does; its pid is this process, which is enough here.
	control._REGISTERED['right'] = {'id': 'right', 'pid': os.getpid(), 'screen': 'Side Monitor', 'dashboard': '/tmp/right.levity'}

	reply = call(dashboard, {'cmd': 'workspace'})

	assert reply['workspace'] == str(path.absolute())
	assert reply['name'] == 'desk'
	assert [window['id'] for window in reply['windows']] == ['main', 'right']
	assert reply['windows'][1]['pid'] == os.getpid()
	assert reply['windows'][1]['screen'] == 'Side Monitor'
	assert reply['windows'][1]['mode'] == 'windowed'
	# Geometry for the window that has one, and none for the one the file never placed.
	assert reply['windows'][0]['geometry'] is not None
	assert reply['windows'][1]['geometry'] is None


def test_close_closes_this_window_through_the_app(server, dashboard):
	closed = []
	control.setCloseWindow(lambda: closed.append(True))

	reply = call(dashboard, {'cmd': 'close', 'window': 'current'})

	assert reply['ok'] is True
	assert reply['closed'] == 'main'
	assert closed == [True]


def test_close_asks_a_window_that_registered_with_this_one(monkeypatch):
	asked = []
	monkeypatch.setattr(control, 'request', lambda payload, timeout=0, path=None, wait=0: asked.append((payload, path)) or {'ok': True})

	reply = control.dispatch({'v': 2, 'id': 'x', 'cmd': 'close', 'window': 'right'})

	assert reply['ok'] is True
	assert reply['closed'] == 'right'
	assert asked[0][1] == control.socketPath(id='right')


def test_close_with_no_window_is_not_found():
	reply = control.dispatch({'v': 2, 'id': 'x', 'cmd': 'close'})

	assert reply['ok'] is False
	assert reply['error']['code'] == 'not_found'


# ---------------------------------------------------------------------------------------------------------------------
# Theme


def test_the_workspace_theme_is_forced_over_a_window_dashboard_theme(tmp_path, capsys):
	from LevityDash.lib.ui.colors import theme

	path = tmp_path / 'desk.yaml'
	path.write_text(DESK)
	first = tmp_path / 'home.levity'
	first.write_text('theme: paper\nitems: []\n')
	active = workspace.load(path)
	active.windows[0].dashboard = str(first)
	workspace.setActive(active)
	workspace.setLaunch(workspace.Launch.fromWindow(active.windows[0]))
	workspace.setTheme('dusk')

	try:
		workspace.applyTheme()

		assert theme.override() is not None and theme.override().name == 'dusk'
	finally:
		theme.set_override(None)

	# One line, naming both themes: a window never quietly renders in a theme the layout does not use.
	assert 'paper theme ignored: the workspace uses dusk' in capsys.readouterr().err


def test_a_window_that_agrees_with_the_layout_says_nothing(tmp_path, capsys):
	from LevityDash.lib.ui.colors import theme

	path = tmp_path / 'desk.yaml'
	path.write_text(DESK)
	first = tmp_path / 'home.levity'
	first.write_text('theme: dusk\nitems: []\n')
	active = workspace.load(path)
	active.windows[0].dashboard = str(first)
	workspace.setActive(active)
	workspace.setLaunch(workspace.Launch.fromWindow(active.windows[0]))
	workspace.setTheme('dusk')

	try:
		workspace.applyTheme()
	finally:
		theme.set_override(None)

	assert 'theme ignored' not in capsys.readouterr().err


def test_without_a_workspace_theme_each_window_keeps_its_own(tmp_path):
	from LevityDash.lib.ui.colors import theme

	path = tmp_path / 'desk.yaml'
	path.write_text(DESK)
	first = tmp_path / 'home.levity'
	first.write_text('theme: paper\nitems: []\n')
	active = workspace.load(path)
	active.windows[0].dashboard = str(first)
	workspace.setActive(active)
	workspace.setLaunch(workspace.Launch.fromWindow(active.windows[0]))
	workspace.setTheme(None)

	try:
		workspace.applyTheme()
		assert theme.override() is None
	finally:
		theme.set_override(None)
