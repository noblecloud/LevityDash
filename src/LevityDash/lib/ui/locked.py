"""Locked (display-only) mode: the dashboard without its editing machinery.

A locked dashboard builds no resize or margin handles, accepts no hover, drag, drop, selection or focus on its
panels, and shows no edit context menu, so a touch or a click on a room display never moves anything. Displays that
read the mouse for their own purpose (a graph's tooltip, say) keep working.

The mode is read once at start: ``--locked`` / ``--unlocked`` on the command line, then ``LEVITY_LOCKED``
in the environment, then ``[Display] locked`` in the config (default off). It is baked into items when they are
built, so changing it at run time (``Ctrl+Alt+L``) rebuilds the dashboard.

Qt-free on purpose; the frontend reads ``isLocked()``.
"""
import os
import sys

__all__ = ['isLocked', 'setLocked', 'resolveLocked']

_state: bool | None = None
_TRUE = {'1', 'true', 'yes', 'on'}


def resolveLocked(argv=None, environ=None, configValue=None) -> bool:
	"""Command line first, then environment, then the config value."""
	argv = sys.argv if argv is None else argv
	environ = os.environ if environ is None else environ
	if '--unlocked' in argv:
		return False
	if '--locked' in argv:
		return True
	if (env := environ.get('LEVITY_LOCKED', '').strip().lower()):
		return env in _TRUE
	return bool(configValue)


def isLocked() -> bool:
	global _state
	if _state is None:
		try:
			from LevityDash.lib.config import userConfig
			configValue = userConfig.getOrSet('Display', 'locked', False, userConfig.getboolean)
		except Exception:
			configValue = False
		_state = resolveLocked(configValue=configValue)
	return _state


def setLocked(value: bool) -> None:
	global _state
	_state = bool(value)
