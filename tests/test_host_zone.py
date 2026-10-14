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
