"""A graph says where a time sits on its axis, and an item with `time-axis` follows it."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import GraphPanel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.DateTime import ClockComponent


def _graph(left, pps, calls):
	graph = SimpleNamespace(leftTime=left, pixelsPerSecond=pps, width=lambda: 1000, __dict__={})
	graph.__dict__.update(leftTime=left, pixelsPerSecond=pps, width=lambda: 1000)
	graph.timeToX = lambda t: GraphPanel.timeToX(graph, t)
	graph.watchAxis = lambda f: GraphPanel.watchAxis(graph, f)
	graph._notifyAxis = lambda force=False: GraphPanel._notifyAxis(graph, force)
	graph.watchAxis(lambda: calls.append(1))
	return graph


def test_time_to_x_counts_from_the_left_edge():
	left = datetime(2026, 10, 7, 0, 0, tzinfo=timezone.utc)
	graph = _graph(left, 2.0, [])
	assert graph.timeToX(left) == 0
	assert graph.timeToX(left + timedelta(minutes=1)) == 120
	assert graph.timeToX(left - timedelta(seconds=10)) == -20


def test_a_graph_that_has_not_synced_cannot_place_a_time():
	graph = _graph(None, 1.0, [])
	with pytest.raises(ValueError, match='not placed'):
		graph.timeToX(datetime.now(timezone.utc))


def test_watchers_hear_of_a_move_of_a_pixel_or_more_only():
	calls = []
	left = datetime(2026, 10, 7, 0, 0, tzinfo=timezone.utc)
	graph = _graph(left, 1.0, calls)
	graph._notifyAxis()
	graph._notifyAxis()
	assert len(calls) == 1
	graph.leftTime = left + timedelta(seconds=0.4)
	graph._notifyAxis()
	assert len(calls) == 1
	graph.leftTime = left + timedelta(seconds=3)
	graph._notifyAxis()
	assert len(calls) == 2


def test_a_clock_can_show_another_time():
	decode = ClockComponent.statefulItems['offset'].decodeValue
	assert decode('3h', None) == 3
	assert decode('-90min', None) == -1.5
	assert decode(2, None) == 2
