"""One soak child process: ``python _child.py backend|frontend``. Started by ``soak.py``, not by hand.

Order matters. The clock is warped and the fake feeds are wired in *before* ``LevityDash`` is imported, so
every module binds the warped time functions and the plugins' requests never leave the machine.
"""
import asyncio
import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import timewarp

timewarp.installFromEnvironment()
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
timewarp.warpQt()

role = sys.argv[1]
out = Path(os.environ['LEVITYDASH_SOAK_OUT'])


def installBleStub() -> None:
	"""A ``bleak`` that scans nothing: ``SharedScanner.start`` succeeds and the Govee plugin sits subscribed."""
	import types

	class BleakScanner:
		def __init__(self, detection_callback=None, **kwargs):
			pass

		async def start(self):
			pass

		async def stop(self):
			pass

	module = types.ModuleType('bleak')
	module.BleakScanner = BleakScanner
	sys.modules['bleak'] = module


def startFeeds() -> None:
	"""Fake OpenMeteo/PirateWeather HTTP server (real time: it answers a socket) and the Govee advertisement
	loop (warped time: it is a sensor on the soak clock), each on its own thread."""
	import feeds
	server = feeds.FeedServer(faultEvery=int(os.environ.get('LEVITYDASH_SOAK_FAULT_EVERY', '0') or 0))
	ready = threading.Event()

	def serve():
		loop = asyncio.new_event_loop()
		asyncio.set_event_loop(loop)

		async def run():
			await server.start()
			feeds.redirectAiohttp(server.redirects())
			ready.set()

		loop.run_until_complete(run())
		loop.run_forever()

	def govee():
		asyncio.run(feeds.goveeFeed(float(os.environ.get('LEVITYDASH_SOAK_GOVEE_PERIOD', '10'))))

	threading.Thread(target=serve, name='soak-feeds', daemon=True).start()
	ready.wait(10)
	(out / 'feeds.port').write_text(str(server.port))
	threading.Thread(target=govee, name='soak-govee', daemon=True).start()


def waitFor(condition, label):
	import time
	deadline = time.monotonic() + 60
	while not condition():
		if time.monotonic() > deadline:
			raise SystemExit(f'soak: {label} did not come up')
		time.sleep(0.05)


if role == 'backend':
	installBleStub()
	startFeeds()
	import probe
	probe.startBackendProbe(out)
	import LevityDash.backend as backend
	raise SystemExit(backend.main())

if role == 'frontend':
	import signal
	from LevityDash import LevityDashboard

	LevityDashboard.parse_args()
	LevityDashboard.init()
	timewarp.sweep()
	timewarp.warpApp()
	LevityDashboard.app.processEvents()
	LevityDashboard.plugins.load_all()
	import probe
	probe.startFrontendProbe(out)

	app = LevityDashboard.app
	signal.signal(signal.SIGTERM, lambda *_: app.quit())
	signal.signal(signal.SIGINT, lambda *_: app.quit())
	app.start()
	probe.finish()
	sys.stdout.flush()
	os._exit(0)
