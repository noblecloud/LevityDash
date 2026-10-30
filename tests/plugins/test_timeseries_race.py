"""A rolling 24h min/max over a room key read its series on the computed values' worker thread while a source change
rebuilt it on the main thread, and the series' hash walked the dict mid-rebuild: `OrderedDict mutated during iteration`."""
import sys
import threading
from collections import OrderedDict
from threading import RLock

from LevityDash.lib.plugins.observation import MeasurementTimeSeries


class _Item:
	def __init__(self, value):
		self.rawValue = value


def _series() -> MeasurementTimeSeries:
	series = MeasurementTimeSeries.__new__(MeasurementTimeSeries)
	OrderedDict.__init__(series)
	series._MeasurementTimeSeries__dataLock = RLock()
	return series


def test_hashing_a_series_while_it_is_rebuilt_does_not_raise():
	series = _series()
	hashed = series._MeasurementTimeSeries__valuesHash
	rebuild = series._MeasurementTimeSeries__dataLock
	errors, stop = [], threading.Event()
	interval = sys.getswitchinterval()
	sys.setswitchinterval(1e-6)

	def writer():
		while not stop.is_set():
			with rebuild:
				series.clear()
				for i in range(200):
					series[i] = _Item(i)

	def reader():
		try:
			for _ in range(500):
				hashed()
		except Exception as e:
			errors.append(e)

	thread = threading.Thread(target=writer)
	thread.start()
	try:
		reader()
	finally:
		stop.set()
		thread.join()
		sys.setswitchinterval(interval)
	assert errors == []
