"""The config files are TOML; an INI left from before the move is migrated on first read and kept as a .bak."""
import tomllib
from io import StringIO

import pytest

from LevityDash.lib import configfile
from LevityDash.lib.config import LevityConfig, PluginConfig

LEGACY = """\
[Location]
timezone = America/New_York
latitude = 40.7128
longitude = -74.0060

[Display]
fullscreen = False
width = 8.56in

; a comment
[Comfort]
low = 55F
high = 72F

[Debug]
screenshot-port = 8671

[Logging]
level = WARNING
logTimeFormat = %m/%d/%y %H:%M:%S

[Fonts]
default.weight = Medium

[Units]
temperature = f

[UnitDefaults]
precision = 1
digit_budget = 3

[UnitProperties]
Tiny = precision=3, digit_budget=4
inHg = precision=2, digit_budget=4, trailing_zeros=precision
"""


def test_a_value_reads_back_as_the_text_it_was(tmp_path):
	sections = [('S', {'a': 'True', 'b': '12', 'c': '1.5', 'd': '007', 'e': '1.50', 'f': 'nan', 'g': '55F', 'h': '', 'i': 'a "q" \\n'})]
	text = configfile.dumpToml(sections)
	assert configfile.fromToml(tomllib.loads(text))['S'] == dict(sections[0][1])
	data = tomllib.loads(text)['S']
	assert data['a'] is True and data['b'] == 12 and data['c'] == 1.5
	assert data['d'] == '007' and data['e'] == '1.50' and data['f'] == 'nan'


def test_unit_properties_are_inline_tables_and_back():
	text = configfile.dumpToml([('UnitProperties', {'Tiny': 'precision=3, digit_budget=4'})])
	assert tomllib.loads(text)['UnitProperties']['Tiny'] == {'precision': 3, 'digit_budget': 4}
	assert configfile.fromToml(tomllib.loads(text))['UnitProperties']['Tiny'] == 'precision=3, digit_budget=4'


def test_nested_tables_and_arrays_flatten():
	data = tomllib.loads('[Fonts]\nextra = ["A", "B"]\n[Fonts.default]\nweight = "Medium"\n')
	assert configfile.fromToml(data)['Fonts'] == {'extra': 'A, B', 'default.weight': 'Medium'}


def test_a_top_level_value_is_refused():
	with pytest.raises(ValueError):
		configfile.fromToml({'stray': 1})


def test_an_ini_is_migrated_with_a_backup(tmp_path):
	ini = tmp_path / 'config.ini'
	ini.write_text(LEGACY)
	assert configfile.migrateConfigDir(tmp_path) == [tmp_path / 'config.toml']
	assert not ini.exists()
	assert (tmp_path / 'config.ini.bak').read_text() == LEGACY
	config = LevityConfig()
	config.read(tmp_path / 'config.toml')
	assert config['Location']['latitude'] == '40.7128'
	assert config['Location']['longitude'] == '-74.0060'
	assert config.getboolean('Display', 'fullscreen') is False
	assert config['Comfort']['low'] == '55F'
	assert config.getint('Debug', 'screenshot-port') == 8671
	assert config['Logging']['logTimeFormat'] == '%m/%d/%y %H:%M:%S'
	assert config['Fonts']['default.weight'] == 'Medium'
	assert config['UnitProperties']['inHg'] == 'precision=2, digit_budget=4, trailing_zeros=precision'


def test_migrating_twice_changes_nothing(tmp_path):
	(tmp_path / 'config.ini').write_text(LEGACY)
	configfile.migrateConfigDir(tmp_path)
	before = (tmp_path / 'config.toml').read_text()
	(tmp_path / 'config.ini').write_text('[Other]\nx = 1\n')  # an old file turning up again
	assert configfile.migrateConfigDir(tmp_path) == []
	assert (tmp_path / 'config.toml').read_text() == before
	assert (tmp_path / 'config.ini').exists()  # the TOML wins and the INI is not touched


def test_plugin_files_are_migrated_too(tmp_path):
	plugins = tmp_path / 'plugins'
	(plugins / 'Govee').mkdir(parents=True)
	(plugins / 'plugins.ini').write_text('[Options]\nenabled = True\n')
	(plugins / 'Aircraft.ini').write_text('[plugin]\nenabled = True\n[Aircraft]\nradius = 2.2\n')
	(plugins / 'Govee' / 'config.ini').write_text('[plugin]\nenabled = True\n')
	written = {p.relative_to(tmp_path).as_posix() for p in configfile.migrateConfigDir(tmp_path)}
	assert written == {'plugins/plugins.toml', 'plugins/Aircraft.toml', 'plugins/Govee/config.toml'}


def test_an_unwritable_target_keeps_the_ini(tmp_path, monkeypatch):
	ini = tmp_path / 'config.ini'
	ini.write_text(LEGACY)
	monkeypatch.setattr(type(ini), 'write_text', lambda *a, **k: (_ for _ in ()).throw(OSError('read-only')))
	assert configfile.migrateIni(ini) is None
	assert ini.exists() and not (tmp_path / 'config.toml').exists()


def test_saved_config_is_toml_and_reads_back(tmp_path):
	(tmp_path / 'c.toml').write_text('[Display]\nwidth = "8in"\n')
	config = LevityConfig()
	config.read(tmp_path / 'c.toml')
	config.path = tmp_path / 'c.toml'
	config.add_section('Comfort')
	config['Comfort']['low'] = '55F'
	out = StringIO()
	config.write(out)
	parsed = tomllib.loads(out.getvalue())
	assert parsed == {'Display': {'width': '8in'}, 'Comfort': {'low': '55F'}}


def test_an_ini_that_could_not_move_is_still_read_and_saved_as_ini(tmp_path):
	(tmp_path / 'c.ini').write_text('[Display]\nwidth = 8in\n')
	config = LevityConfig()
	config.read(tmp_path / 'c.ini')
	config.path = tmp_path / 'c.ini'
	out = StringIO()
	config.write(out)
	assert out.getvalue().startswith('[Display]\nwidth = 8in')


def test_plugin_defaults_come_from_toml_or_old_ini_text():
	new = PluginConfig.readString('[plugin]\nenabled = true\n[Host]\ninterval = 2\n')
	old = PluginConfig.readString('\n\t[plugin]\n\tenabled = False\n\n\t[Host]\n\tinterval = 2\n\t')
	assert new.getboolean('plugin', 'enabled') is True and new.getfloat('Host', 'interval') == 2.0
	assert old.getboolean('plugin', 'enabled') is False and old.getfloat('Host', 'interval') == 2.0


def test_every_shipped_config_parses():
	from pathlib import Path
	root = Path(configfile.__file__).resolve().parents[1]
	files = [*root.rglob('*.toml')]
	files = [f for f in files if 'resources/icons' not in f.as_posix() and 'themes' not in f.parts]
	assert files
	for file in files:
		if file.parent.name in ('example-config', 'design-seed', 'seed', 'plugins'):
			configfile.readToml(file)


def test_the_shipped_example_config_keeps_the_comfort_range_documented():
	from pathlib import Path
	text = (Path(configfile.__file__).resolve().parents[1] / 'resources/example-config/config.toml').read_text()
	assert '[Comfort]' in text and 'low' in text and 'high' in text


def test_first_start_moves_a_real_ini_config_over(tmp_path):
	"""Boots the config module against a config folder that only has the old INI files."""
	import os
	import subprocess
	import sys
	config = tmp_path / '.config' / 'LevityDash'
	(config / 'plugins').mkdir(parents=True)
	# the shipped settings written the old way, with this user's own on top
	from configparser import ConfigParser
	from pathlib import Path
	parser = ConfigParser(interpolation=None, allow_no_value=True)
	parser.optionxform = str
	parser.read_dict(configfile.readToml(Path(configfile.__file__).resolve().parents[1] / 'resources/example-config/config.toml'))
	parser.read_dict({'Comfort': {'low': '55F'}, 'Debug': {'screenshot-port': '8671'}})
	with (config / 'config.ini').open('w') as f:
		parser.write(f)
	legacy = (config / 'config.ini').read_text()
	(config / 'plugins' / 'Aircraft.ini').write_text('[plugin]\nenabled = True\n[Aircraft]\nradius = 2.2\n')
	code = (
		'from LevityDash.lib.config import userConfig as c, pluginConfig as p\n'
		'from unitcorn.config import config as u\n'
		'print(c.path.path.name, c["Comfort"]["low"], c.getint("Debug", "screenshot-port"), u.path.name, sorted(p.userConfigs))'
	)
	env = {**os.environ, 'HOME': str(tmp_path), 'XDG_CONFIG_HOME': str(tmp_path / '.config'), 'QT_QPA_PLATFORM': 'offscreen'}
	env.pop('LEVITYDASH_CONFIG_DEBUG', None)
	result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, timeout=120)
	assert result.stdout.strip().endswith("config.toml 55F 8671 config.toml ['Aircraft']"), result.stderr
	assert (config / 'config.ini.bak').read_text() == legacy
	assert not (config / 'config.ini').exists() and (config / 'plugins' / 'Aircraft.ini.bak').exists()
