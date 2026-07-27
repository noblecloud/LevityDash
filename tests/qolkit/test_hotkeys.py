"""Tests for qolkit.hotkeys.

The interesting behaviour is what happens when there is *no* terminal — the
listener has to degrade to a harmless no-op so callers can bind
unconditionally, without guarding every call site. That is also the case the
test suite itself runs in (pytest captures stdin), so it needs pinning.
"""
import sys

import pytest

from qolkit.hotkeys import CTRL_C, CTRL_R, HotkeyListener


class FakeStdin:
	def __init__(self, tty: bool, fileno: int = 0):
		self._tty = tty
		self._fileno = fileno

	def isatty(self):
		return self._tty

	def fileno(self):
		return self._fileno


class TestKeyConstants:

	def test_control_codes(self):
		# Ctrl+<letter> is the letter's position in the alphabet as a byte.
		assert CTRL_C == '\x03'
		assert CTRL_R == '\x12'


class TestDegradesWithoutATerminal:

	def test_not_supported_when_stdin_is_not_a_tty(self, monkeypatch):
		monkeypatch.setattr(sys, 'stdin', FakeStdin(tty=False))
		assert HotkeyListener().supported is False

	def test_start_returns_false_and_does_not_raise(self, monkeypatch):
		monkeypatch.setattr(sys, 'stdin', FakeStdin(tty=False))
		listener = HotkeyListener()
		listener.bind(CTRL_R, lambda: None)
		assert listener.start() is False

	def test_stop_is_safe_when_never_started(self):
		HotkeyListener().stop()  # must not raise

	def test_supported_survives_a_detached_stdin(self, monkeypatch):
		# Some hosts replace stdin with an object whose isatty() raises.
		class Hostile:
			def isatty(self):
				raise ValueError('detached')

		monkeypatch.setattr(sys, 'stdin', Hostile())
		assert HotkeyListener().supported is False


class TestBindings:

	def test_bind_records_the_callback(self):
		listener = HotkeyListener()
		calls = []
		listener.bind(CTRL_R, lambda: calls.append(1))
		# dispatch directly - the reader thread needs a real tty, but the
		# binding table is what maps a byte to an action.
		listener._bindings[CTRL_R]()
		assert calls == [1]

	def test_rebinding_replaces(self):
		listener = HotkeyListener()
		listener.bind(CTRL_R, lambda: 'first')
		listener.bind(CTRL_R, lambda: 'second')
		assert listener._bindings[CTRL_R]() == 'second'

	def test_unbound_key_is_absent(self):
		listener = HotkeyListener()
		listener.bind(CTRL_R, lambda: None)
		assert CTRL_C not in listener._bindings
