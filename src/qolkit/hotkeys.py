"""Single-keypress hotkeys for a terminal program.

Ctrl+C is a *signal* and arrives through ``signal.signal``. Ctrl+R is not —
it is just byte ``0x12`` sitting in stdin, and a line-buffered terminal will
not hand it over until Enter is pressed. Reacting to it means putting the
terminal in cbreak mode and reading raw bytes.

``cbreak`` rather than ``raw`` deliberately: it clears ICANON and ECHO but
leaves **ISIG** on, so Ctrl+C/Ctrl+Z keep working normally. A listener here
adds keys; it does not take any away.

Degrades to a no-op when stdin is not a TTY (piped, redirected, or running as
a supervised child) and on platforms without ``termios``, so callers can bind
unconditionally without guarding.

    listener = HotkeyListener()
    listener.bind(CTRL_R, on_restart)
    listener.start()
"""
from __future__ import annotations

import atexit
import os
import select
import sys
import threading
from typing import Callable, Dict, List, NoReturn, Optional

try:
	import termios
	import tty
except ImportError:  # pragma: no cover - Windows
	termios = None
	tty = None

__all__ = ['CTRL_C', 'CTRL_R', 'HotkeyListener', 'restart_process']

CTRL_C = '\x03'
CTRL_R = '\x12'

#: Every started listener, so the terminal can be restored before an exec()
#: replaces the process - atexit does NOT run in that case.
_active: List['HotkeyListener'] = []


class HotkeyListener:
	"""Watches stdin for single keypresses and dispatches to callbacks.

	Callbacks run on the reader thread, so they should be cheap and
	thread-safe — set a flag, signal an event, or post to an event loop.
	"""

	def __init__(self, poll_interval: float = 0.25):
		self._bindings: Dict[str, Callable[[], None]] = {}
		self._poll_interval = poll_interval
		self._thread: Optional[threading.Thread] = None
		self._stop = threading.Event()
		self._saved_attrs = None
		self._fd: Optional[int] = None

	def bind(self, key: str, callback: Callable[[], None]) -> None:
		self._bindings[key] = callback

	@property
	def supported(self) -> bool:
		if termios is None or tty is None:
			return False
		try:
			return sys.stdin is not None and sys.stdin.isatty()
		except (AttributeError, ValueError):
			return False

	def start(self) -> bool:
		"""Begin listening. Returns False (harmlessly) when unsupported."""
		if not self.supported or self._thread is not None:
			return False
		try:
			self._fd = sys.stdin.fileno()
			self._saved_attrs = termios.tcgetattr(self._fd)
			tty.setcbreak(self._fd)  # keeps ISIG: Ctrl+C still signals
		except Exception:
			self._fd = self._saved_attrs = None
			return False

		_active.append(self)
		atexit.register(self.stop)
		self._thread = threading.Thread(target=self._read_loop, name='HotkeyListener', daemon=True)
		self._thread.start()
		return True

	def stop(self) -> None:
		"""Stop listening and put the terminal back how we found it."""
		self._stop.set()
		if self._saved_attrs is not None and self._fd is not None:
			try:
				termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved_attrs)
			except Exception:
				pass
			self._saved_attrs = None
		if self in _active:
			_active.remove(self)

	def _read_loop(self) -> None:
		while not self._stop.is_set():
			try:
				# select so the thread can notice _stop rather than blocking
				# forever on a read nobody is going to satisfy
				ready, _, _ = select.select([sys.stdin], [], [], self._poll_interval)
				if not ready:
					continue
				char = os.read(self._fd, 1).decode(errors='ignore')
			except Exception:
				return
			if (callback := self._bindings.get(char)) is not None:
				try:
					callback()
				except Exception:
					pass


def restore_terminal() -> None:
	"""Restore every active listener's terminal state.

	Call before ``os.exec*`` — that replaces the process image, so ``atexit``
	handlers never run and the terminal would be left in cbreak mode.
	"""
	for listener in list(_active):
		listener.stop()


def restart_process() -> NoReturn:
	"""Replace this process with a fresh copy of itself, same arguments."""
	restore_terminal()
	sys.stdout.flush()
	sys.stderr.flush()

	if getattr(sys, 'frozen', False):
		os.execv(sys.argv[0], sys.argv)

	# `python -m pkg` sets __main__.__package__; re-exec the same way so the
	# package's own entry semantics are preserved rather than running its
	# __main__.py as a loose script.
	package = getattr(sys.modules.get('__main__'), '__package__', None)
	if package:
		os.execv(sys.executable, [sys.executable, '-m', package, *sys.argv[1:]])
	os.execv(sys.executable, [sys.executable, *sys.argv])
