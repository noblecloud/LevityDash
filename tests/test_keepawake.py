import os
import shutil

import pytest

from LevityDash.lib.utils import keepawake


@pytest.fixture(autouse=True)
def released():
	yield
	keepawake.stopKeepAwake()


def test_command_by_system(monkeypatch):
	monkeypatch.setattr(shutil, 'which', lambda name: f'/usr/bin/{name}')
	assert keepawake.inhibitCommand('darwin', 42) == ['caffeinate', '-d', '-i', '-w', '42']
	linux = keepawake.inhibitCommand('linux', 42)
	assert linux[0] == 'systemd-inhibit' and '--pid=42' in linux
	assert keepawake.inhibitCommand('freebsd', 42) is None


def test_no_command_when_the_tool_is_missing(monkeypatch):
	monkeypatch.setattr(shutil, 'which', lambda name: None)
	assert keepawake.inhibitCommand('darwin') is None
	assert keepawake.inhibitCommand('linux') is None


def test_holds_until_stopped(monkeypatch):
	monkeypatch.setattr(keepawake, 'platform', 'linux')
	monkeypatch.setattr(keepawake, 'inhibitCommand', lambda *a, **k: ['sleep', '60'])
	assert keepawake.startKeepAwake()
	process = keepawake._process
	assert process.poll() is None
	assert keepawake.startKeepAwake() and keepawake._process is process  # a second call holds the same lock
	keepawake.stopKeepAwake()
	assert process.poll() is not None


def test_reports_false_when_the_tool_dies_at_once(monkeypatch):
	monkeypatch.setattr(keepawake, 'platform', 'linux')
	monkeypatch.setattr(keepawake, 'inhibitCommand', lambda *a, **k: ['false'])
	assert keepawake.startKeepAwake() is False
	assert keepawake._process is None


def test_real_inhibitor_here_either_holds_or_says_no():
	"""On a Mac or a Linux desktop this holds a real lock; in a container with no bus it returns False."""
	held = keepawake.startKeepAwake()
	assert held == (keepawake._process is not None and keepawake._process.poll() is None)
