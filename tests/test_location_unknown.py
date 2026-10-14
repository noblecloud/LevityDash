import configparser
import io

from LevityDash.lib import config as cfg


def _config(monkeypatch, tmp_path, guess):
	monkeypatch.setattr(cfg, 'guessLocation', guess)
	monkeypatch.setattr('time.sleep', lambda s: None)
	c = object.__new__(cfg.Config)
	configparser.ConfigParser.__init__(c)
	return c


def test_an_unguessable_location_is_unknown_not_zero_zero_weather(monkeypatch, tmp_path):
	def fail():
		raise OSError('no route')
	c = _config(monkeypatch, tmp_path, fail)
	c.loc
	assert c.locationKnown is False


def test_the_guess_is_retried_before_giving_up(monkeypatch, tmp_path):
	calls = []

	def flaky():
		calls.append(1)
		if len(calls) < 3:
			raise OSError('blip')
		return '40.0', '-75.0', 'America/New_York'
	c = _config(monkeypatch, tmp_path, flaky)
	c.save = lambda: None
	assert c.loc == (40.0, -75.0)
	assert c.locationKnown is True


def test_a_placeholder_location_is_never_written_out(monkeypatch, tmp_path):
	def fail():
		raise OSError('no route')
	c = _config(monkeypatch, tmp_path, fail)
	c.loc
	out = io.StringIO()
	c.write(out)
	assert '0.0' not in out.getvalue()
	assert c['Location']['latitude'] == '0.0'
