"""A key's timeseries as plain numbers, for items that draw a whole series at once.

`valuesource.KeySource` gives one current value; a polar plot needs the series behind it. The
dispatcher's container holds that as a `MeasurementTimeSeries`, filled lazily and refreshed on its
own signal. `SeriesFeed` waits for a container that has one, reads it into ``(time, number)``
pairs on the GUI thread and calls ``onChange`` after every refresh, so the item never touches a
plugin's objects from a worker.
"""
from datetime import datetime
from typing import Callable, Optional

from PySide6.QtCore import QObject, Slot

from LevityDash import LevityDashboard
from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.plugin import AnySource

__all__ = ['Series', 'SeriesFeed']

log = LevityPluginLog.getChild('PolarFeed')


class Series:
	"""Times and numbers of one key, with the unit its first sample came in."""
	__slots__ = ('times', 'values', 'unit', 'now', 'cls')

	def __init__(self, times=(), values=(), unit: str = '', now: Optional[float] = None, cls: Optional[type] = None):
		self.times: list[datetime] = list(times)
		self.values: list[float] = list(values)
		self.unit = unit
		self.now = now
		self.cls = cls

	def __len__(self) -> int:
		return len(self.values)

	def between(self, start: datetime, end: datetime) -> 'Series':
		pairs = [(t, v) for t, v in zip(self.times, self.values) if start <= t < end]
		return Series([t for t, _ in pairs], [v for _, v in pairs], self.unit, self.now, self.cls)


def _number(value) -> Optional[float]:
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


class SeriesFeed(QObject):
	"""Reads one key's series and says when it changes. `close()` lets go."""

	def __init__(self, key: str, onChange: Callable[[], None]):
		super().__init__()
		self.key = CategoryItem(key)
		self._onChange = onChange
		self._closed = False
		self._timeseries = None
		self._series = Series()
		self._multi = LevityDashboard.get_container(self.key)
		self._multi.getPreferredSourceContainer(self, AnySource, self._attach, timeseriesOnly=True)

	@property
	def series(self) -> Series:
		return self._series

	def _attach(self):
		if self._closed or self._timeseries is not None:
			return
		container = self._multi.getTimeseries()
		timeseries = getattr(container, 'timeseries', None)
		if timeseries is None:
			log.warning(f'polar: {self.key} has no timeseries yet; the plot stays empty')
			return
		with timeseries.signals as signal:
			if not signal.connectSlot(self.changed):
				log.warning(f'polar: could not follow {self.key}')
				return
		self._timeseries = timeseries
		self.changed()

	@Slot()
	def changed(self, *args):
		if self._closed or self._timeseries is None:
			return
		times, values, unit, cls = [], [], '', None
		for item in self._timeseries.list:
			number = _number(item.value)
			if number is None:
				continue
			if cls is None:
				cls = type(item.value)
				unit = str(getattr(item.value, 'unit', '') or '')
			times.append(item.timestamp)
			values.append(number)
		try:
			current = _number(self._multi.value.now.value)
		except (AttributeError, ValueError):
			current = None
		self._series = Series(times, values, unit, current, cls)
		try:
			self._onChange()
		except RuntimeError:
			# The item was deleted (a dashboard reload) and this feed outlived it.
			self.close()

	def close(self):
		self._closed = True
		if self._timeseries is not None:
			try:
				self._timeseries.signals.disconnectSlot(self.changed)
			except Exception:
				pass
			self._timeseries = None
