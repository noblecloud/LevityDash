"""What the supervisor starts for the history database (devtools/history_server.py)."""
from pathlib import Path

from LevityDash.devtools.history_server import readHistoryConfig, serverCommand

NOWHERE = lambda name: None
HERE = Path('/data')


def _command(section, which=lambda name: '/usr/bin/influxdb3', exists=lambda p: False):
	return serverCommand(section, which=which, exists=exists, dataDir=HERE)


def test_the_default_is_influxdb_bound_to_this_machine_only():
	server, why = _command({})
	assert why == ''
	assert server.argv[:2] == ['/usr/bin/influxdb3', 'serve']
	assert '--http-bind' in server.argv and server.argv[server.argv.index('--http-bind') + 1] == '127.0.0.1:8181'
	assert '--without-auth' in server.argv and '--disable-telemetry-upload' in server.argv
	assert server.argv[server.argv.index('--data-dir') + 1] == str(HERE / 'history' / 'influxdb')
	assert (server.name, server.host, server.port) == ('history', '127.0.0.1', 8181)


def test_a_port_and_data_dir_are_taken_from_the_config():
	server, _ = _command({'port': '9191', 'data-dir': '/srv/influx'})
	assert server.port == 9191 and '127.0.0.1:9191' in server.argv and '/srv/influx' in server.argv


def test_nothing_is_started_when_there_is_nothing_to_start():
	for section, expected in [
		({'enabled': 'no'}, 'off'),
		({'backend': 'sqlite'}, 'needs no server'),
		({'manage': 'no'}, 'manage'),
		({'host': 'nas.local'}, 'another machine'),
		({'token': 'apiv3_x'}, 'token'),
		({'backend': 'questdb'}, 'own launcher'),
	]:
		server, why = _command(section)
		assert server is None and expected in why, section


def test_a_missing_binary_says_how_to_get_it():
	server, why = _command({}, which=NOWHERE)
	assert server is None and 'brew install influxdb3-core' in why


def test_the_usual_install_places_are_searched():
	server, _ = _command({}, which=NOWHERE, exists=lambda p: str(p) == '/opt/homebrew/bin/influxdb3')
	assert server.argv[0] == '/opt/homebrew/bin/influxdb3'


def test_a_binary_or_command_in_the_config_wins():
	assert _command({'binary': '/opt/x/influxdb3'}, which=NOWHERE)[0].argv[0] == '/opt/x/influxdb3'
	server, _ = _command({'backend': 'questdb', 'command': 'sh -c "questdb start -f"'})
	assert server.argv == ['sh', '-c', 'questdb start -f'] and server.port == 9000


def test_the_config_is_read_from_toml_or_ini(tmp_path, monkeypatch):
	monkeypatch.delenv('LEVITYDASH_HISTORY', raising=False)
	monkeypatch.delenv('LEVITYDASH_HISTORY_BACKEND', raising=False)
	monkeypatch.delenv('LEVITYDASH_HISTORY_DB', raising=False)
	(tmp_path / 'config.ini').write_text('[History]\nbackend = questdb\nport = 9100\n')
	assert readHistoryConfig(tmp_path) == {'backend': 'questdb', 'port': '9100'}
	(tmp_path / 'config.toml').write_text('[History]\nbackend = "influxdb"\nport = 8282\n')
	assert readHistoryConfig(tmp_path) == {'backend': 'influxdb', 'port': '8282'}
	monkeypatch.setenv('LEVITYDASH_HISTORY', 'off')
	assert readHistoryConfig(tmp_path)['enabled'] == 'no'
