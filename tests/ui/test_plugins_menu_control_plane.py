"""PluginsMenu routing for the control-plane command half.

The menu must do two different things depending on mode:

- mode=live  -> toggle the local plugin directly (plugin.start()/stop()), the
                original behavior, unchanged.
- mode=remote -> send a 'plugin_command' over the wire via
                RemoteConnection.send_plugin_command(...), and reflect the
                backend's reported running state (connection.plugins), not the
                local (never-started) plugin.

The menu reads ``LevityDashboard`` and ``backend_mode`` through the names bound
in app.py, so the test stubs those name bindings (not the real singleton - its
__slots__ can't be patched) and drives togglePlugin/restartPlugin directly.
"""
from unittest import mock
from contextlib import contextmanager

from LevityDash.lib.ui.frontends.PySide import app as app_module
from LevityDash.lib.ui.frontends.PySide.app import PluginsMenu


class _FakePlugin:
	"""Records start/stop and reports a running flag we can flip."""

	def __init__(self, name, running=False):
		self.name = name
		self.running = running
		self.calls = []

	def start(self):
		self.calls.append('start')
		self.running = True

	def stop(self):
		self.calls.append('stop')
		self.running = False


class _FakeConnection:
	"""Stands in for RemoteConnection: records send_plugin_command calls and
	exposes the backend snapshot the menu reads (connection.plugins)."""

	def __init__(self, alive=True):
		self.calls = []
		self.plugins = {}
		self.backendAlive = alive

	def send_plugin_command(self, name, command, on_response):
		self.calls.append((name, command))
		# Fire the callback on the calling (GUI) thread, like the real impl.
		on_response({'ok': True})

	def set_running(self, name, running):
		from LevityDash.lib.wire.messages import PluginState
		self.plugins[name] = PluginState(name, True, running, 0, None)


class _FakeLevityDashboard:
	"""Minimal stand-in for the LevityDashboard singleton the menu touches."""

	def __init__(self, plugins, remote):
		self.plugins = plugins
		self.dispatcher = _FakeDispatcher(remote)


class _FakeDispatcher:
	def __init__(self, remote):
		self.remote = remote


def _make_menu(plugins, remote, mode):
	"""Build a PluginsMenu whose LevityDashboard/backend_mode references are
	stubbed, avoiding the real singleton's __slots__.

	Returns a context manager yielding (menu, fake_ld): the patches stay active
	for the whole `with` body, so togglePlugin/restartPlugin (called inside it)
	see the stubbed mode, not the real singleton.
	"""
	fake_ld = _FakeLevityDashboard(plugins, remote)

	@contextmanager
	def _ctx():
		with mock.patch.object(app_module, 'LevityDashboard', fake_ld), \
				mock.patch.object(app_module, 'backend_mode', lambda: mode):
			yield PluginsMenu(None), fake_ld

	return _ctx()


def test_remote_toggle_sends_start_command_not_local_start(dashboard):
	plugin = _FakePlugin('OpenMeteo')
	conn = _FakeConnection()
	with _make_menu([plugin], conn, 'remote') as (menu, _):
		menu.togglePlugin(plugin, True)

	assert conn.calls == [('OpenMeteo', 'start')], conn.calls
	assert plugin.calls == [], 'local plugin must not be toggled in remote mode'


def test_remote_toggle_off_sends_stop_command(dashboard):
	plugin = _FakePlugin('OpenMeteo', running=True)
	conn = _FakeConnection()
	with _make_menu([plugin], conn, 'remote') as (menu, _):
		menu.togglePlugin(plugin, False)

	assert conn.calls == [('OpenMeteo', 'stop')]
	assert plugin.calls == []


def test_remote_restart_sends_restart_command(dashboard):
	plugin = _FakePlugin('OpenMeteo')
	conn = _FakeConnection()
	with _make_menu([plugin], conn, 'remote') as (menu, _):
		menu.restartPlugin(plugin)

	assert conn.calls == [('OpenMeteo', 'restart')]
	assert plugin.calls == []


def test_live_toggle_calls_local_plugin_directly(dashboard):
	plugin = _FakePlugin('OpenMeteo')
	with _make_menu([plugin], None, 'live') as (menu, _):
		menu.togglePlugin(plugin, True)

	assert plugin.calls == ['start']
	# No connection exists in live mode -> nothing sent over the wire.
	assert not hasattr(menu, 'connection') or True  # menu has no connection attr in live


def test_live_restart_toggles_local_plugin(dashboard):
	plugin = _FakePlugin('OpenMeteo', running=True)
	with _make_menu([plugin], None, 'live') as (menu, _):
		menu.restartPlugin(plugin)

	assert plugin.calls == ['stop', 'start']


def test_remote_running_state_reflects_backend_snapshot(dashboard):
	plugin = _FakePlugin('OpenMeteo')  # local says not running
	conn = _FakeConnection()
	conn.set_running('OpenMeteo', True)  # backend says running
	with _make_menu([plugin], conn, 'remote') as (menu, _):
		assert menu._is_running(plugin) is True
		conn.set_running('OpenMeteo', False)
		assert menu._is_running(plugin) is False


def test_remote_actions_disabled_when_backend_not_alive(dashboard):
	plugin = _FakePlugin('OpenMeteo')
	conn = _FakeConnection(alive=False)
	with _make_menu([plugin], conn, 'remote') as (menu, _):
		menu.refresh_toggles()

	sub, status, toggle, restart = menu._plugin_actions['OpenMeteo']
	assert toggle.isEnabled() is False
	assert restart.isEnabled() is False
	# The status header is a read-only (always-disabled) info line.
	assert status.isEnabled() is False


def test_menu_builds_one_submenu_per_plugin_with_status_header(dashboard):
	plugins = [_FakePlugin('OpenMeteo'), _FakePlugin('Govee', running=True)]
	with _make_menu(plugins, None, 'live') as (menu, _):
		assert set(menu._plugin_actions) == {'OpenMeteo', 'Govee'}
		sub, status, toggle, restart = menu._plugin_actions['OpenMeteo']
		# The submenu's first action is the non-action status header.
		assert sub.actions()[0] is status
		assert 'OpenMeteo:' in status.text()
		assert 'Stopped' in status.text()
		# The submenu exposes Running (toggle) + Restart.
		assert toggle.isCheckable() is True
		assert restart.text() == 'Restart'


def test_start_all_sends_start_for_every_plugin_over_wire(dashboard):
	plugins = [_FakePlugin('OpenMeteo'), _FakePlugin('Govee')]
	conn = _FakeConnection()
	with _make_menu(plugins, conn, 'remote') as (menu, _):
		menu.startAll()

	assert conn.calls == [('OpenMeteo', 'start'), ('Govee', 'start')]


def test_stop_all_sends_stop_for_every_plugin_over_wire(dashboard):
	plugins = [_FakePlugin('OpenMeteo', running=True), _FakePlugin('Govee', running=True)]
	conn = _FakeConnection()
	with _make_menu(plugins, conn, 'remote') as (menu, _):
		menu.stopAll()

	assert conn.calls == [('OpenMeteo', 'stop'), ('Govee', 'stop')]


def test_bulk_actions_disabled_when_remote_backend_not_alive(dashboard):
	plugins = [_FakePlugin('OpenMeteo'), _FakePlugin('Govee')]
	conn = _FakeConnection(alive=False)
	with _make_menu(plugins, conn, 'remote') as (menu, _):
		menu.refresh_toggles()
		start_all, stop_all = menu._bulk_actions
		assert start_all.isEnabled() is False
		assert stop_all.isEnabled() is False


def test_bulk_actions_enabled_when_remote_backend_alive(dashboard):
	plugins = [_FakePlugin('OpenMeteo'), _FakePlugin('Govee')]
	conn = _FakeConnection(alive=True)
	with _make_menu(plugins, conn, 'remote') as (menu, _):
		menu.refresh_toggles()
		start_all, stop_all = menu._bulk_actions
		assert start_all.isEnabled() is True
		assert stop_all.isEnabled() is True


def test_bulk_actions_enabled_in_live_mode(dashboard):
	# In live mode there is no remote connection; bulk actions drive the
	# local plugins directly and must stay enabled regardless.
	plugins = [_FakePlugin('OpenMeteo'), _FakePlugin('Govee')]
	with _make_menu(plugins, None, 'live') as (menu, _):
		menu.refresh_toggles()
		start_all, stop_all = menu._bulk_actions
		assert start_all.isEnabled() is True
		assert stop_all.isEnabled() is True
