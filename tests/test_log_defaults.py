"""Logging defaults: warnings only, and rich can be switched off.

The logger installs at import time, so each case runs in a fresh interpreter against a throwaway config.
"""
import json
import logging
import os
import subprocess
import sys
import textwrap

SCRIPT = textwrap.dedent('''
	import json, logging
	import LevityDash
	LevityDash.LevityDashboard.init()
	from LevityDash.lib import log as L
	cls = L._LevityLogger
	print(json.dumps({
		'root': logging.getLogger().level,
		'console': cls.consoleHandler.level,
		'file': cls.fileHandler.level,
		'statusBar': cls.statusBarHandler.level,
		'consoleIsRich': isinstance(cls.consoleHandler, L.RichHandler),
		'fileIsRich': isinstance(cls.fileHandler, L.RichHandler),
	}))
''')


def _run(**env):
	full = {k: v for k, v in os.environ.items() if not k.startswith('LEVITY_LOG') and k != 'LEVITY_LOG_PLAIN'}
	full.update({'QT_QPA_PLATFORM': 'offscreen', 'LEVITYDASH_CONFIG_DEBUG': '1', **env})
	out = subprocess.run([sys.executable, '-I', '-c', SCRIPT], env=full, capture_output=True, text=True, timeout=120)
	assert out.returncode == 0, out.stderr[-2000:]
	return json.loads(out.stdout.strip().splitlines()[-1])


def test_a_fresh_config_logs_warnings_only():
	got = _run()
	assert got['console'] == got['file'] == got['statusBar'] == logging.WARNING
	assert got['consoleIsRich'] and got['fileIsRich']


def test_rich_can_be_turned_off_with_the_environment():
	got = _run(LEVITY_LOG_RICH='0')
	assert not got['consoleIsRich'] and not got['fileIsRich']
	assert got['file'] == logging.WARNING


def test_the_older_plain_switch_still_works():
	got = _run(LEVITY_LOG_PLAIN='1')
	assert not got['consoleIsRich'] and not got['fileIsRich']
