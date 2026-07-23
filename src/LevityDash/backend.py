"""Entry point for the standalone backend (Phase 4.2).

This module exists at the PACKAGE level - rather than pointing the
``LevityDash-backend`` console script straight at ``LevityDash.lib.backend`` -
because the mode pin below must run BEFORE anything imports
``LevityDash.lib``: that package's __init__ does ``from . import plugins``,
which constructs the dispatcher (a GlobalSingleton) and has it read
``backend_mode()`` immediately. A console script's ``from X import main``
imports every parent package of X first, so a pin inside
``LevityDash.lib.backend`` (whether at module level or in main()) always
runs after the dispatcher has already read the mode.

This process always ingests **live** internally; ``mode=remote`` is a
*frontend* setting that otherwise leaks in through the shared config file
(the natural place a user puts their frontend into remote mode) or a stray
env var - making the backend's dispatcher a remote frontend of itself.

Launch: ``LevityDash-backend`` (or ``python -m LevityDash.backend``).
Everything else lives in ``LevityDash.lib.backend``.
"""
import os

# See the module docstring for why this must happen at this exact spot in
# the import order.
os.environ['LEVITYDASH_BACKEND_MODE'] = 'live'

# Read by lib/log.py to give this process its own log file - frontend and
# backend used to share one path (LevityDash.log) and race each other's log
# rotation, which could wedge a handler's file object closed permanently
# (see the RichRotatingLogHandlerProxy fix).
os.environ.setdefault('LEVITYDASH_PROCESS_ROLE', 'backend')


def main() -> int:
	from LevityDash.lib.backend import main as _main
	return _main()


if __name__ == '__main__':
	raise SystemExit(main())
