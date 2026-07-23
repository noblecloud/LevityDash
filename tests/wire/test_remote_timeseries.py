"""Tests for RemoteTimeSeries (lib/wire/containers.py) - the frontend stand-in
for observation.MeasurementTimeSeries, populated once a ts_response comes back
over the wire (see containers.py's RemoteContainer.prepare_for_ts_connection).

Exercises exactly the surface Graph.py reads off a real timeseries: datetime
slicing (bounded and open-ended), `.first`, `len()`/truthiness, and `.signals`
as a connect/disconnectSlot context manager - not a full plugin bootstrap.
"""
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.observation import TimeSeriesItem
from LevityDash.lib.wire.containers import RemoteSource, RemoteTimeSeries
from datetime import datetime, timedelta, timezone

KEY = CategoryItem('environment.temperature.temperature')


def make_series(*values_and_offsets):
	base = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)
	items = [TimeSeriesItem.load_raw(v, base + timedelta(hours=h)) for v, h in values_and_offsets]
	source = RemoteSource(name='TestPlugin')
	return RemoteTimeSeries(source, KEY, items), base


def test_stores_items_sorted_by_timestamp_regardless_of_input_order():
	series, base = make_series((75.0, 2), (70.0, 0), (72.0, 1))
	assert [i.value for i in series] == [70.0, 72.0, 75.0]


def test_first_returns_earliest_item():
	series, base = make_series((72.0, 1), (70.0, 0), (75.0, 2))
	assert series.first.value == 70.0
	assert series.first.timestamp == base


def test_first_is_none_for_empty_series():
	series, _ = make_series()
	assert series.first is None


def test_len_and_truthiness():
	empty, _ = make_series()
	populated, _ = make_series((70.0, 0))
	assert len(empty) == 0
	assert not empty
	assert len(populated) == 1
	assert populated


def test_bounded_slice_returns_items_within_range():
	series, base = make_series((70.0, 0), (72.0, 1), (75.0, 2), (78.0, 3))
	sliced = series[base + timedelta(hours=1):base + timedelta(hours=2)]
	assert [i.value for i in sliced] == [72.0, 75.0]


def test_open_ended_slice_start_none_means_from_the_beginning():
	series, base = make_series((70.0, 0), (72.0, 1), (75.0, 2))
	sliced = series[None:base + timedelta(hours=1)]
	assert [i.value for i in sliced] == [70.0, 72.0]


def test_open_ended_slice_stop_none_means_to_the_end():
	series, base = make_series((70.0, 0), (72.0, 1), (75.0, 2))
	sliced = series[base + timedelta(hours=1):None]
	assert [i.value for i in sliced] == [72.0, 75.0]


def test_full_open_slice_returns_everything():
	series, _ = make_series((70.0, 0), (72.0, 1))
	assert len(series[None:None]) == 2


def test_non_slice_index_raises_type_error():
	series, _ = make_series((70.0, 0))
	try:
		series[0]
		assert False, 'expected TypeError'
	except TypeError:
		pass


def test_signals_context_manager_connect_and_disconnect():
	series, _ = make_series((70.0, 0))

	class Listener:
		def on_change(self, *a):
			pass

	listener = Listener()
	with series.signals as sig:
		assert sig.connectSlot(listener.on_change)
		assert sig.disconnectSlot(listener.on_change)


def test_refresh_is_a_safe_no_op_and_fires_callback():
	series, _ = make_series((70.0, 0))
	series.refresh()  # no callback - must not raise
	seen = []
	series.refresh(callback=lambda: seen.append(True))
	assert seen == [True]
