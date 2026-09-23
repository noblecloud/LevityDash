"""A remote timeseries must follow the backend, not freeze at first fetch.

In mode=remote a graph fetched its series once, when it connected, and never
again: `RemoteTimeSeries.refresh()` was a no-op and a backend push only
replaced the container's scalar value. A display left running kept drawing
the forecast from the day it started until the forecast ran out - lambda ran
from Sept 8 to Sept 23 on one 16-day OpenMeteo fetch.
"""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.observation import TimeSeriesItem
from LevityDash.lib.plugins.utils import Request
from LevityDash.lib.wire.containers import RemoteSource
from LevityDash.lib.wire.messages import encode_ts_response
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QApplication

KEY = CategoryItem('environment.temperature.temperature')
START = datetime(2026, 9, 8, tzinfo=timezone.utc)


def app():
	return QApplication.instance() or QApplication([])


class FakeBackend:
	"""Answers ts_requests with a series whose last point moves forward one
	hour per request, like a forecast that was fetched again. `hold=True`
	queues the responses instead, to test a push landing mid-flight."""

	def __init__(self, hold=False):
		self.requests = []
		self.pending = []
		self.hold = hold

	def __call__(self, message, on_response):
		self.requests.append(message)
		n = len(self.requests)
		items = [TimeSeriesItem.load_raw(70.0 + i, START + timedelta(hours=i)) for i in range(n + 2)]
		response = encode_ts_response(request_id=message['id'], source='OpenMeteo', key=message['key'], ok=True, items=items)
		if self.hold:
			self.pending.append(lambda: on_response(response))
		else:
			on_response(response)

	def release(self):
		pending, self.pending = self.pending, []
		for fn in pending:
			fn()


class Graph(QObject):
	"""The two things Graph.py relies on: a period hint, and a slot on the
	series' signals."""

	wireTimeseriesPeriod = (timedelta(days=-2), timedelta(days=16))

	def __init__(self):
		super().__init__()
		self.changes = 0

	@Slot()
	def onValueChange(self):
		self.changes += 1


def connected(backend):
	app()
	source = RemoteSource(name='OpenMeteo', ts_request_fn=backend)
	container = source.getOrCreate(KEY)
	graph = Graph()
	container.prepare_for_ts_connection(Request(requester=graph, callback=lambda: None))
	backend.release()
	series = container.timeseries
	series.signals.connectSlot(graph.onValueChange)
	return container, series, graph


def last(series):
	return list(series)[-1].timestamp


def test_a_backend_push_refetches_the_series_in_place():
	backend = FakeBackend()
	container, series, graph = connected(backend)
	before = last(series)

	container._update(71.0)

	assert len(backend.requests) == 2
	assert container.timeseries is series, 'a new object would strand the connected graph'
	assert last(series) > before
	assert graph.changes == 1


def test_the_refetch_keeps_the_graphs_window():
	backend = FakeBackend()
	container, series, graph = connected(backend)

	container._update(71.0)

	first, again = backend.requests
	assert again['minPeriod'] == first['minPeriod'] == timedelta(days=-2).total_seconds()
	assert again['maxPeriod'] == first['maxPeriod'] == timedelta(days=16).total_seconds()


def test_refresh_fetches_again_and_calls_back_after_the_data_lands():
	backend = FakeBackend()
	container, series, graph = connected(backend)
	before = last(series)
	seen = []

	series.refresh(lambda: seen.append(last(series)))

	assert len(backend.requests) == 2
	assert seen and seen[0] > before


def test_pushes_during_a_fetch_coalesce_into_one_more_fetch():
	backend = FakeBackend(hold=True)
	container, series, graph = connected(backend)

	container._update(71.0)
	container._update(72.0)
	container._update(73.0)
	assert len(backend.requests) == 2, 'one in flight; the rest wait'

	backend.release()
	assert len(backend.requests) == 3, 'the stale pushes cost exactly one more fetch'
	backend.release()
	assert len(backend.requests) == 3


def test_a_push_before_any_graph_connects_fetches_nothing():
	backend = FakeBackend()
	source = RemoteSource(name='OpenMeteo', ts_request_fn=backend)
	container = source.getOrCreate(KEY)

	container._update(71.0)

	assert backend.requests == []


def test_a_failed_refetch_keeps_the_old_points():
	backend = FakeBackend()
	container, series, graph = connected(backend)
	before = list(series)

	container.source._ts_request_fn = lambda message, on_response: on_response(None)
	container._update(71.0)

	assert list(series) == before
	assert container._tsRefetching is False
