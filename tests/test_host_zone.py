from LevityDash.lib import config


def test_the_host_zone_name_comes_from_the_tz_variable(monkeypatch):
	monkeypatch.setenv('TZ', 'America/New_York')
	assert config.hostZoneName() == 'America/New_York'


def test_the_host_zone_name_comes_from_the_localtime_link(monkeypatch, tmp_path):
	monkeypatch.delenv('TZ', raising=False)
	zone = tmp_path / 'var' / 'db' / 'zoneinfo' / 'America' / 'New_York'
	zone.parent.mkdir(parents=True)
	zone.write_text('')
	monkeypatch.setattr(config.os.path, 'realpath', lambda path: str(zone))
	assert config.hostZoneName() == 'America/New_York'


def test_live_plugins_publish_epoch_seconds_so_the_autumn_hour_is_not_ambiguous():
	# A local wall-clock string cannot tell the first 01:00 of the clock change from
	# the second, so every reading after it landed an hour early.
	from LevityDash.lib.plugins.builtin.Fixture import buildSchema

	scenario = {'keys': {'environment.temperature.temperature': {'value': 1, 'unit': 'f'}}}
	assert buildSchema(scenario, epoch=True)[0]['timestamp']['sourceUnit'] == 'epoch'
	assert buildSchema(scenario)[0]['timestamp']['sourceUnit'] == 'ISO8601'
