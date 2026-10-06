"""A figure whose time range is zero seconds must not divide by zero.

``GraphItemData.normalize`` scales every x by the figure's time span
(``Figure.figureTimeRangeMaxMin``). A single-sample series, a stalled source or a
frozen clock leaves that span at zero seconds, and the unguarded divide turned
every x into ``inf``/``NaN`` -- a ``RuntimeWarning: divide by zero``, a plot that
drifted between renders, and (a queued update carrying that non-finite geometry)
a crash at teardown. The guard pins x to the left edge, as a flat series is
pinned to the bottom, instead of ever producing a non-finite coordinate. A
healthy span is scaled exactly as before.

Regression for ``docs/tasks/graph-zero-time-range.md``.
"""
from datetime import datetime, timedelta, timezone
import warnings

import numpy as np
import pytest

from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import Figure, GraphItemData, LinePlot


def _a_plots_data(dashboard) -> GraphItemData:
	"""One real plot's data from the seeded dashboard."""
	plots = [i for i in dashboard.scene.items() if isinstance(i, LinePlot)]
	assert plots, 'expected the seeded dashboard to contain a line plot'
	return plots[0].data


def test_a_zero_second_time_range_does_not_divide_by_zero(dashboard, monkeypatch):
	"""The degenerate case: a figure whose time range is zero seconds."""
	data = _a_plots_data(dashboard)
	monkeypatch.setattr(Figure, 'figureTimeRangeMaxMin', property(lambda self: timedelta(0)))

	x = np.array([1_700_000_000.0, 1_700_000_000.0])  # one instant, twice
	with warnings.catch_warnings():
		warnings.simplefilter('error')  # a RuntimeWarning is a failure
		with np.errstate(divide='raise', invalid='raise'):
			nx, _ = data.normalize(x=x)

	assert np.all(np.isfinite(nx)), f'non-finite x from a zero range: {nx!r}'
	assert np.array_equal(nx, np.zeros_like(x)), 'a zero span pins x to the left edge'


def test_a_healthy_time_range_is_scaled_unchanged(dashboard, monkeypatch):
	"""The guard must not move a non-degenerate range."""
	data = _a_plots_data(dashboard)
	monkeypatch.setattr(Figure, 'figureTimeRangeMaxMin', property(lambda self: timedelta(seconds=3600)))

	start = data.graph.timeframe.start.timestamp()
	x = np.array([start, start + 1800, start + 3600])
	with warnings.catch_warnings():
		warnings.simplefilter('error')
		nx, _ = data.normalize(x=x)

	assert nx == pytest.approx([0.0, 0.5, 1.0])


def test_pos_px_to_value_survives_a_zero_item_span():
	"""The hover lookup divides by the item's own time span; a zero span must not crash."""
	class _Degenerate:
		hasData = True
		smoothed = ['the only sample']

		class graph:
			secondsPerPixel = 1.0

		class timeframe:
			min = datetime(2025, 6, 18, 14, 30, tzinfo=timezone.utc)
			range = timedelta(0)

	assert GraphItemData.pos_px_to_value(_Degenerate(), 0.0) == 'the only sample'
