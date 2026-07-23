"""Full timeseries-over-wire path, composed end-to-end over a real socket:

    RemoteContainer.prepare_for_ts_connection
        -> RemoteSource.request_timeseries -> WireClient.request
        -> [socket] -> WireServer -> RemoteBackend.handle_ts_request
        -> (Qt-thread lookup + thread-pool rebuild, mirroring
            Container.prepare_for_ts_connection exactly)
        -> [socket] -> WireClient -> RemoteContainer._timeseries populated

This is the milestone's actual success criterion: a Graph-shaped consumer
(`.signals`, datetime slicing, `.first`) gets real data in remote mode,
instead of `Graph.connectTimeseries`'s documented None-guard firing forever.

Uses a hand-built Plugin/Container/timeseries stand-in (not a full app/plugin
bootstrap, matching test_containers.py's precedent) - the real RemoteBackend,
WireServer, WireClient, RemoteFrontend, RemoteContainer are all exercised for
real; only the plugin-side data source is a stub.
"""
import asyncio
import os
import threading
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from datetime import timedelta

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.observation import TimeSeriesItem
from LevityDash.lib.plugins.utils import Request
from LevityDash.lib.utils.shared import now, Pool
from LevityDash.lib.wire.backend import RemoteBackend
from LevityDash.lib.wire.client import WireClient
from LevityDash.lib.wire.frontend import RemoteFrontend
from LevityDash.lib.wire.server import WireServer
from PySide6.QtWidgets import QApplication

_KEY = CategoryItem('environment.temperature.temperature')
_SOURCE = 'TestPlugin'


class _FakeTimeSeries:
	"""Stands in for observation.MeasurementTimeSeries - exposes exactly what
	RemoteBackend._resolve_ts_request reads: .update() and datetime slicing."""

	def __init__(self):
		self.items = [
			TimeSeriesItem.load_raw(70.0, now() - timedelta(hours=1)),
			TimeSeriesItem.load_raw(72.0, now()),
			TimeSeriesItem.load_raw(75.0, now() + timedelta(hours=1)),
		]

	def update(self):
		pass  # already "fresh" - a real MeasurementTimeSeries would rebuild here

	def __getitem__(self, item):
		lo, hi = item.start, item.stop
		return [i for i in self.items if lo <= i.timestamp <= hi]


class _FakeContainer:
	timeseries = _FakeTimeSeries()


class _FakePlugin:
	name = _SOURCE
	thread_pool = Pool()

	def __getitem__(self, key):
		return _FakeContainer()


def _pump_until(app, done: threading.Event, timeout: float = 5.0) -> bool:
	deadline = time.monotonic() + timeout
	while not done.is_set() and time.monotonic() < deadline:
		app.processEvents()
		time.sleep(0.01)
	return done.is_set()


def test_remote_container_gets_real_timeseries_over_the_wire():
	app = QApplication.instance()
	assert app is not None, 'expected the LevityDash package import to have already constructed a QApplication'

	backend = RemoteBackend(send=lambda m: None)
	backend._plugins[_SOURCE] = _FakePlugin()

	async def scenario():
		server = WireServer(on_request=backend.handle_ts_request)
		await server.start()

		def request_timeseries(message, on_response):
			async def _do():
				try:
					response = await client.request(message)
				except Exception:
					response = None
				on_response(response)
			asyncio.ensure_future(_do())

		updates_seen = []
		frontend = RemoteFrontend(on_update=updates_seen.append, ts_request_fn=request_timeseries)
		client = WireClient(server.url, frontend.handle_message)
		await client.connect()

		source = frontend._get_source({'name': _SOURCE, 'defaultFor': [], 'enabled': True, 'running': True})
		container = source.getOrCreate(_KEY)

		done = threading.Event()
		request = Request(requester=object(), callback=done.set)
		container.prepare_for_ts_connection(request)

		# The Qt-thread hop (RemoteBackend's _QtInvoker) needs the Qt event
		# loop pumped to deliver - run both loops concurrently until the
		# request's callback fires.
		deadline = asyncio.get_running_loop().time() + 5.0
		while not done.is_set() and asyncio.get_running_loop().time() < deadline:
			app.processEvents()
			await asyncio.sleep(0.01)

		await client.close()
		await server.stop()
		return done.is_set(), container

	completed, container = asyncio.run(scenario())
	assert completed, "request.callback() never fired - timeseries request didn't complete"

	timeseries = container.timeseries
	assert timeseries is not None
	assert len(timeseries) == 3

	# The exact surface Graph.connectTimeseries reads - not just "is not None"
	assert timeseries.first is not None
	assert timeseries.first.value == 70.0
	sliced = timeseries[now() - timedelta(hours=2):now() + timedelta(hours=2)]
	assert [i.value for i in sliced] == [70.0, 72.0, 75.0]
	with timeseries.signals as sig:
		class _Listener:
			def on_change(self, *a):
				pass
		listener = _Listener()
		assert sig.connectSlot(listener.on_change)
