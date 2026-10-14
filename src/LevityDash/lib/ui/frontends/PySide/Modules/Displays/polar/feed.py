"""A key's timeseries as plain numbers, for items that draw a whole series at once.

`valuesource.KeySource` gives one current value; a polar plot needs the series behind it. The
dispatcher's container holds that as a `MeasurementTimeSeries`, filled lazily and refreshed on its
own signal. `SeriesFeed` waits for a container that has one, reads it into ``(time, number)``
pairs on the GUI thread and calls ``onChange`` after every refresh, so the item never touches a
plugin's objects from a worker.
"""
from typing import Callable, Dict, Optional

from PySide6.QtCore import QObject, Slot

from LevityDash import LevityDashboard
from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.expressions import Expression, ExpressionError
from LevityDash.lib.plugins.plugin import AnySource
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.series import Series, derive, number
from LevityDash.lib.utils.shared import now as localNow

__all__ = ['Series', 'SeriesFeed', 'DerivedFeed', 'openFeed', 'installStandIn', 'standIn']

log = LevityPluginLog.getChild('PolarFeed')


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
		times, values, raw, unit, cls = [], [], [], '', None
		for item in self._timeseries.list:
			value = number(item.value)
			if value is None:
				continue
			if cls is None:
				cls = type(item.value)
				unit = str(getattr(item.value, 'unit', '') or '')
			times.append(item.timestamp)
			values.append(value)
			raw.append(item.value)
		try:
			current = number(self._multi.value.now.value)
		except (AttributeError, ValueError):
			current = None
		self._series = Series(times, values, unit, current, cls, raw)
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


class DerivedFeed:
	"""A series computed from an expression: `temperature - dewpoint` as a whole series, not one value.

	A computed key (`lib/plugins/computed.py`) holds one current value and no history, which is right for
	a gauge and useless for a plot. This opens a feed for every key the expression reads and evaluates it
	at every sample time (`series.derive`), again whenever an input changes.
	"""

	def __init__(self, expression: Expression, onChange: Callable[[], None], openInput: Callable[[str, Callable[[], None]], object]):
		self.key = expression.text
		self._expression = expression
		self._onChange = onChange
		self._closed = False
		self._failed: Optional[str] = None
		self._series = Series()
		self._inputs: Dict[CategoryItem, object] = {}
		for key in expression.inputKeys:
			self._inputs[key] = openInput(str(key), self._inputChanged)
		self._inputChanged()

	@property
	def series(self) -> Series:
		return self._series

	def _inputChanged(self):
		if self._closed or len(getattr(self, '_inputs', ())) < len(self._expression.inputKeys):
			return  # still opening the inputs: one derive once they are all there
		try:
			self._series = derive(self._expression, {key: feed.series for key, feed in self._inputs.items()}, localNow())
			self._failed = None
		except ExpressionError as error:
			self._series = Series()
			if self._failed != str(error):
				self._failed = str(error)
				log.warning(f'polar {self._expression.text!r}: {error}; it shows no data')
		try:
			self._onChange()
		except RuntimeError:
			self.close()

	def close(self):
		self._closed = True
		for feed in self._inputs.values():
			feed.close()
		self._inputs = {}


_standIn: Optional[Callable[[str, Callable[[], None]], object]] = None


def installStandIn(opener: Optional[Callable[[str, Callable[[], None]], object]]) -> None:
	"""Answer every plain-key feed from `opener` (Gauge Studio's made-up data); None puts the dispatcher back."""
	global _standIn
	_standIn = opener


def standIn() -> Optional[Callable[[str, Callable[[], None]], object]]:
	"""The stand-in now installed, so a window can tell whether it is still the one answering."""
	return _standIn


def _openKey(key: str, onChange: Callable[[], None]):
	return _standIn(key, onChange) if _standIn is not None else SeriesFeed(key, onChange)


def openFeed(text: str, onChange: Callable[[], None]):
	"""A feed for a key or an expression over keys. Raises `ExpressionError` for text that is neither."""
	expression = Expression.parse(text)
	if expression.plainKey is not None:
		return _openKey(str(expression.plainKey), onChange)
	return DerivedFeed(expression, onChange, _openKey)
