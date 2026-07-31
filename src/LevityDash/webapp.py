#!/usr/bin/env python
"""LevityWeb entry point - a headless Qt frontend serving the dashboard to
browsers.

    poetry run LevityDash-web [--seed DIR] [--levity FILE] [--port N]

Boots the real dashboard offscreen (plugins included), then serves it as
flattened layout + live values over WebSocket at /ws-web, with the browser
frontend (web/dist) at /. Exactly the boot chain of the render service, so a
service crash or Ctrl+C leaves the user's own dashboard untouched.

The mode pin below must run BEFORE any LevityDash import - the QApplication is
constructed during the package import chain and QT_QPA_PLATFORM can't change
afterwards. Same rule as render_service.py.
"""
import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

# This process always ingests **live** internally - mode=remote is a Qt
# frontend setting that otherwise leaks in through the shared config file,
# making the web service a remote frontend of itself. Same pin, same reason,
# same placement as backend.py: it must run before anything imports
# LevityDash.lib, which constructs the dispatcher on import.
os.environ['LEVITYDASH_BACKEND_MODE'] = 'live'

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
	from LevityDash.devtools._boot import boot
	from LevityDash.lib.web.service import DEFAULT_PORT, WebService

	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument('--seed', help='config dir copy to serve against; omit for the real config')
	parser.add_argument('--levity', help='candidate .levity to serve (requires --seed)')
	parser.add_argument('--size', default='1800x1090', help='window size driving layout')
	parser.add_argument('--settle', type=float, default=1.5, help='seconds to let layout settle after boot/resize')
	parser.add_argument('--host', default=os.getenv('LEVITYDASH_WEB_HOST', '127.0.0.1'))
	parser.add_argument('--port', type=int, default=int(os.getenv('LEVITYDASH_WEB_PORT', DEFAULT_PORT)))
	args = parser.parse_args()

	width, _, height = args.size.lower().partition('x')
	size = (int(width), int(height))

	app, dashboard = boot(seed=args.seed, levity=args.levity, size=size, settle=6.0, plugins=True)

	service = WebService(app, dashboard, host=args.host, port=args.port, settle=args.settle)
	service.start()
	service._watch_scene()

	from LevityDash.lib.log import LevityLogger as log

	log.info(f'LevityWeb booted with {len(dashboard.plugins.enabled_plugins)} plugins')
	print(f'{len(dashboard.plugins.enabled_plugins)} plugins started', flush=True)

	try:
		return app.exec()
	except KeyboardInterrupt:
		return 0


if __name__ == '__main__':
	raise SystemExit(main())
