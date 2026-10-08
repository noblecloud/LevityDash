import logging

import pytest

from LevityDash.lib.log import _LevityLogger


def findAction(actions, text):
	for action in actions:
		if action.menu() is not None and action.text().replace('&', '') == text:
			return action
	raise AssertionError(f'no menu {text!r}')


def findMenu(dashboard, keep, *path):
	"""The submenu at `path` in the menu bar.

	PySide deletes a menu's C++ object when a temporary wrapper of it is collected,
	so every wrapper met on the way goes into `keep` and stays alive for the test.
	"""
	actions = dashboard.app.main_window.bar.actions()
	menu = None
	for text in path:
		action = findAction(actions, text)
		menu = action.menu()
		keep += [action, menu]
		actions = menu.actions()
		keep += actions
	return menu


@pytest.fixture
def restoreLevels():
	before = {t: _LevityLogger.runtimeLevel(t) for t in ('log', 'status-bar')}
	root = logging.getLogger().level
	yield
	for target, level in before.items():
		_LevityLogger.setRuntimeLevel(target, level)
	logging.getLogger().setLevel(root)


def test_log_level_menu_changes_the_level_at_once(dashboard, restoreLevels):
	keep = []
	menu = findMenu(dashboard, keep, 'Logs', 'Log Level')
	debug = next(a for a in menu.actions() if a.text() == 'Debug')
	debug.trigger()
	assert _LevityLogger.runtimeLevel('log') == logging.DEBUG
	assert _LevityLogger.consoleHandler.level == logging.DEBUG
	assert logging.getLogger().level <= logging.DEBUG
	next(a for a in menu.actions() if a.text() == 'Error').trigger()
	assert _LevityLogger.runtimeLevel('log') == logging.ERROR


def test_status_bar_level_is_separate_from_the_log_level(dashboard, restoreLevels):
	_LevityLogger.setRuntimeLevel('log', logging.INFO)
	keep = []
	menu = findMenu(dashboard, keep, 'Logs', 'Status Bar Level')
	next(a for a in menu.actions() if a.text() == 'Warning').trigger()
	assert _LevityLogger.runtimeLevel('status-bar') == logging.WARNING
	assert _LevityLogger.runtimeLevel('log') == logging.INFO


def test_root_logger_keeps_the_loudest_handlers_level(restoreLevels):
	_LevityLogger.setRuntimeLevel('log', logging.ERROR)
	_LevityLogger.setRuntimeLevel('status-bar', logging.ERROR)
	assert logging.getLogger().level == logging.ERROR
	_LevityLogger.setRuntimeLevel('status-bar', logging.DEBUG)
	assert logging.getLogger().level == logging.DEBUG


def test_menu_checks_the_current_level(dashboard, restoreLevels):
	_LevityLogger.setRuntimeLevel('log', logging.DEBUG)
	menu = dashboard.app.main_window._levelMenu('Log Level', 'log', '')
	assert [a.text() for a in menu.actions() if a.isChecked()] == ['Debug']
