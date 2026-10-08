"""Keep an always-on display awake.

A kiosk should not dim, sleep or lock while the dashboard runs. This asks the
operating system not to. It is separate from App Nap (`preventAppNap`), which
throttles timers in a background process and is a different mechanism.

- macOS: `caffeinate -d -i -w <pid>`, which ends by itself when this process does.
- Linux: `systemd-inhibit` holding an idle and sleep lock around a long `sleep`.
- Windows: `SetThreadExecutionState`.
"""

import ctypes
import os
import shutil
import subprocess
from sys import platform
from typing import Optional

from LevityDash.lib.log import LevityUtilsLog

log = LevityUtilsLog.getChild('KeepAwake')

__all__ = ['inhibitCommand', 'startKeepAwake', 'stopKeepAwake']

_process: Optional[subprocess.Popen] = None
_windowsHeld = False

_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001
_ES_DISPLAY_REQUIRED = 0x00000002


def inhibitCommand(system: str = platform, pid: int = None) -> Optional[list[str]]:
	"""The command that holds the lock on `system`, or None when there is none to run."""
	pid = os.getpid() if pid is None else pid
	if system == 'darwin' and shutil.which('caffeinate'):
		return ['caffeinate', '-d', '-i', '-w', str(pid)]
	if system.startswith('linux') and shutil.which('systemd-inhibit'):
		return [
			'systemd-inhibit', '--what=idle:sleep', '--who=LevityDash',
			'--why=LevityDash is showing a dashboard', '--mode=block',
			'tail', f'--pid={pid}', '-f', '/dev/null',
		]
	return None


def startKeepAwake() -> bool:
	"""Hold the lock. Returns whether one is held; False means this system cannot."""
	global _process, _windowsHeld
	if _process is not None and _process.poll() is None or _windowsHeld:
		return True
	if platform == 'win32':
		try:
			ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED | _ES_DISPLAY_REQUIRED)
			_windowsHeld = True
			log.info('Keeping the display awake')
			return True
		except Exception as e:
			log.warning(f'Unable to keep the display awake: {e}')
			return False
	command = inhibitCommand()
	if command is None:
		log.warning('Keep-awake is on, but this system has no tool for it (needs caffeinate on macOS, systemd-inhibit on Linux)')
		return False
	try:
		_process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
	except OSError as e:
		log.warning(f'Unable to keep the display awake: {e}')
		return False
	try:
		# A tool that cannot reach the system (no D-Bus session, say) exits at once.
		code = _process.wait(timeout=0.5)
	except subprocess.TimeoutExpired:
		log.info(f'Keeping the display awake ({command[0]})')
		return True
	log.warning(f'Unable to keep the display awake: {command[0]} exited with {code}')
	_process = None
	return False


def stopKeepAwake() -> None:
	global _process, _windowsHeld
	if _windowsHeld:
		ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
		_windowsHeld = False
	if _process is not None:
		_process.terminate()
		try:
			_process.wait(timeout=2)
		except subprocess.TimeoutExpired:
			_process.kill()
		_process = None
