"""Computed keys: an expression published as a key like any other.

``expressions.py`` parses and evaluates a value-source expression. This module
makes the result subscribable: it registers expressions, recomputes them when
an input key updates, and publishes each result under its computed key
(``computed.x3f9a0c21b7de``) with the source ``Computed``. Display code then
subscribes to that key through the normal dispatcher machinery and never does
maths itself (docs/tasks/value-sources.md, decision 1).

Where it runs
-------------
- ``mode=live`` (and ``loopback``): in the frontend process, next to the
  plugins, feeding the local dispatcher.
- ``mode=remote``: in the backend process (``lib/backend.py``). The frontend
  sends the set of expressions it needs in a ``computed_sync`` message
  (``lib/wire/messages.py``); results reach it through the ordinary 'update'
  path, exactly like a plugin's keys.

Display code never needs to know which: ``acquireValueSource`` and
``releaseValueSource`` are the whole public surface.

Container shape
---------------
A full ``Plugin`` subclass would bring a schema, observations, a config file,
a thread and the start/stop lifecycle, none of which a computed value has. The
result is one value per key with no history, which is exactly what the wire
layer's stand-ins already model: ``RemoteSource`` (a source with a name,
``defaultFor`` and ``enabled``) and ``RemoteContainer`` (one pushed value plus
its ``is*`` flags). The dispatcher and every display path already accept those
in ``mode=remote``, and ``encode_container`` reads nothing a ``RemoteContainer``
lacks. So ``ComputedSource`` is a ``RemoteSource`` whose publisher also has the
``connectSlot`` half of a real ``Publisher``: the dispatcher's ``keyAdded`` and
the backend's ``RemoteBackend._on_published`` both consume its ``KeyData``
unchanged. A computed value has no timeseries of its own (``isForecast`` is
False), so nothing ever asks it for one.

Threading
---------
Everything except the evaluation itself runs on the Qt main thread: input
updates arrive there (``PluginValueDirectory.update`` emits
``new_keys_signal`` on it), and publishing must happen there. A window or an
offset needs a ``MeasurementTimeSeries``, whose ``update()`` is a slow full
rebuild, so each computation reads current values on the main thread, then
rebuilds series and evaluates on one worker thread, then hands the result back
through a queued signal. Each expression has at most one computation in
flight; an input change during it marks the expression stale and one more
computation follows (the ``RemoteContainer._refetchTimeseries`` pattern).
"""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from functools import partial
from time import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot

from LevityDash import LevityDashboard
from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.expressions import Expression, ExpressionError, Missing
from LevityDash.lib.plugins.observation import DAILY_CUTOFF, MeasurementTimeSeries
from LevityDash.lib.utils.data import KeyData
from LevityDash.lib.utils.shared import now as localNow, singleShotSafe, startTimerSafe
from LevityDash.lib.wire.containers import ContainerFlags, RemotePublisher, RemoteSource

log = LevityPluginLog.getChild('Computed')

__all__ = [
	'COMPUTED_SOURCE', 'ComputedSource', 'ComputedEngine', 'computedEngine',
	'acquireValueSource', 'releaseValueSource',
]

#: The source name every computed key is published under.
COMPUTED_SOURCE = 'Computed'

#: A computed value is current as of its computation, so it reports itself as
#: realtime. isTimeseriesOnly must be False, or the dispatcher would try to
#: fetch a timeseries for it before calling a panel back.
_FLAGS = ContainerFlags(isRealtime=True, isTimeseriesOnly=False)

#: Realtime.connectRealtime reads metadata['type'] unguarded.
_METADATA = {'type': 'computed'}

#: How long to wait after an input changes before recomputing. An expression
#: over a window rebuilds a whole timeseries, and a streaming sensor can update
#: every few seconds, so those wait and let a burst of updates collapse into
#: one computation. Current-value expressions recompute at once.
_SERIES_DELAY_MS = 5000
_CURRENT_DELAY_MS = 0


# -- the source --------------------------------------------------------------

class ComputedPublisher(RemotePublisher):
	"""``RemotePublisher`` (per-key channels, for display code) plus the
	``connectSlot`` half of a real ``Publisher``: subscribers receive a
	``KeyData`` naming the keys that changed. Publishing happens on the Qt main
	thread only, so a plain list of callables is enough."""

	def __init__(self, source: 'ComputedSource'):
		super().__init__(source)
		self._slots: List[Callable[[KeyData], Any]] = []

	def connectSlot(self, slot: Callable[[KeyData], Any]) -> bool:
		if slot in self._slots:
			return False
		self._slots.append(slot)
		return True

	def disconnectSlot(self, slot: Callable[[KeyData], Any]) -> bool:
		try:
			self._slots.remove(slot)
		except ValueError:
			return False
		return True

	def publish(self, keys: Iterable[CategoryItem]) -> None:
		keys = set(keys)
		if not keys:
			return
		data = KeyData(self.source, keys)
		for slot in list(self._slots):
			try:
				slot(data)
			except Exception as e:
				log.error(f'a subscriber failed to take computed keys {sorted(map(str, keys))}: {e!r}')


class ComputedSource(RemoteSource):
	"""The ``Computed`` source. See the module docstring for why this is a
	``RemoteSource`` rather than a ``Plugin``."""

	def __init__(self):
		super().__init__(COMPUTED_SOURCE)
		self.publisher = ComputedPublisher(self)

	def keys(self):
		return self._containers.keys()


# -- inputs --------------------------------------------------------------------

class _SnapshotResolver:
	"""A ``Resolver`` over values read on the main thread and series rebuilt
	on the worker thread. Built and used on the worker thread only."""

	__slots__ = ('_current', '_series')

	def __init__(self, current: Dict[CategoryItem, Any], series: Dict[CategoryItem, Optional[MeasurementTimeSeries]]):
		self._current = current
		self._series = series

	def current(self, key: CategoryItem) -> Any:
		return self._current.get(key)

	def series(self, key: CategoryItem, start: datetime, end: datetime) -> Optional[Sequence[Tuple[datetime, Any]]]:
		timeseries = self._series.get(key)
		if timeseries is None or len(timeseries) == 0:
			return None
		return [(item.timestamp, item.value) for item in timeseries[start:end]]

	def at(self, key: CategoryItem, when: datetime) -> Any:
		timeseries = self._series.get(key)
		if timeseries is None or len(timeseries) == 0:
			return None
		try:
			item = timeseries[when]
		except (KeyError, IndexError, ValueError):
			return None
		return getattr(item, 'value', None)


def _msUntilNextMidnight(at: Optional[float] = None) -> int:
	"""Milliseconds from ``at`` (epoch seconds, default now) to one second past
	the next local midnight. Works on naive local time so a DST change on the
	day lands on the real midnight rather than an hour off."""
	at = time() if at is None else at
	today = datetime.fromtimestamp(at).date()
	midnight = datetime.combine(today + timedelta(days=1), datetime.min.time())
	return max(int((midnight.timestamp() - at) * 1000) + 1000, 1000)


# -- the engine ----------------------------------------------------------------

class _Entry:
	__slots__ = ('expression', 'count', 'state', 'stale', 'lastError')

	def __init__(self, expression: Expression):
		self.expression = expression
		self.count = 1
		#: idle | scheduled | running
		self.state = 'idle'
		#: An input changed while a computation was running.
		self.stale = False
		#: The last evaluation error logged, so a broken expression logs once
		#: rather than on every recompute.
		self.lastError: Optional[str] = None

	@property
	def delay(self) -> int:
		expression = self.expression
		return _SERIES_DELAY_MS if expression.series or expression.points else _CURRENT_DELAY_MS

	@property
	def usesToday(self) -> bool:
		return any(i.window.span is None for i in self.expression.series)


class ComputedEngine(QObject):
	"""Holds the registered expressions of one process and keeps their
	computed keys up to date. Construct it on the Qt main thread."""

	_finished = Signal(object)

	def __init__(self, dispatcher=None):
		super().__init__()
		self._dispatcher = dispatcher if dispatcher is not None else LevityDashboard.dispatcher
		self.source = ComputedSource()
		self._entries: Dict[CategoryItem, _Entry] = {}
		#: input key -> computed keys that read it
		self._dependents: Dict[CategoryItem, Set[CategoryItem]] = defaultdict(set)
		#: (source name, key) -> a series owned by this engine, so a rebuild on
		#: the worker thread never races a graph reading the plugin's own.
		self._series: Dict[Tuple[str, CategoryItem], MeasurementTimeSeries] = {}
		self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='ComputedValues')
		#: Injectable for tests; the evaluator's idea of now.
		self.clock: Callable[[], datetime] = lambda: datetime.now().astimezone()
		self._finished.connect(self._onFinished, Qt.ConnectionType.QueuedConnection)
		self._midnight = QTimer(self)
		self._midnight.setSingleShot(True)
		self._midnight.timeout.connect(self._onMidnight)
		self._dispatcher.new_keys_signal.connect(self._onKeysUpdated)
		self._dispatcher.connect_plugin(self.source)

	# -- registration -------------------------------------------------------

	def register(self, expression: Expression) -> CategoryItem:
		"""Count one more user of ``expression``. The first registration
		computes it."""
		key = expression.key
		if (entry := self._entries.get(key)) is not None:
			entry.count += 1
			return key
		entry = self._entries[key] = _Entry(expression)
		for inputKey in expression.inputKeys:
			self._dependents[inputKey].add(key)
		if entry.usesToday:
			self._scheduleMidnight()
		log.debug(f'registered {key} = {expression.text!r}')
		self._schedule(entry, 0)
		return key

	def release(self, key: CategoryItem) -> bool:
		"""Count one fewer user. Returns True when that was the last one and
		the expression is no longer computed. Its last value stays in the
		dispatcher, as a plugin's does when the plugin stops."""
		entry = self._entries.get(key)
		if entry is None:
			return False
		entry.count -= 1
		if entry.count > 0:
			return False
		del self._entries[key]
		for inputKey in entry.expression.inputKeys:
			dependents = self._dependents.get(inputKey)
			if dependents is not None:
				dependents.discard(key)
				if not dependents:
					del self._dependents[inputKey]
		log.debug(f'released {key} = {entry.expression.text!r}')
		return True

	def refcount(self, key: CategoryItem) -> int:
		entry = self._entries.get(key)
		return entry.count if entry is not None else 0

	def __contains__(self, key: CategoryItem) -> bool:
		return key in self._entries

	def republish(self, keys: Iterable[CategoryItem]) -> None:
		"""Publish the current result of ``keys`` again, for a subscriber that
		joined after it was computed (a frontend that just connected)."""
		ready = {key for key in keys if key in self.source and self.source[key].value is not None}
		self.source.publisher.publish(ready)

	# -- scheduling ---------------------------------------------------------

	def _onKeysUpdated(self, pending) -> None:
		# The dispatcher clears `pending` right after emitting, so copy first.
		try:
			changed = set(pending)
		except TypeError:
			return
		for inputKey in changed:
			for key in list(self._dependents.get(inputKey, ())):
				if (entry := self._entries.get(key)) is not None:
					self._schedule(entry, entry.delay)

	def _schedule(self, entry: _Entry, delay: int) -> None:
		if entry.state == 'running':
			entry.stale = True
			return
		if entry.state == 'scheduled':
			return
		entry.state = 'scheduled'
		singleShotSafe(delay, partial(self._start, entry))

	def _scheduleMidnight(self) -> None:
		if not self._midnight.isActive():
			startTimerSafe(self._midnight, _msUntilNextMidnight())

	def _onMidnight(self) -> None:
		entries = [entry for entry in self._entries.values() if entry.usesToday]
		for entry in entries:
			self._schedule(entry, 0)
		if entries:
			self._scheduleMidnight()

	# -- computation --------------------------------------------------------

	def _start(self, entry: _Entry) -> None:
		expression = entry.expression
		if self._entries.get(expression.key) is not entry:
			return  # released while scheduled
		entry.state = 'running'
		entry.stale = False
		try:
			current = {key: self._currentValue(key) for key in expression.keys}
			windowed = {i.key for i in expression.series} | {i.key for i in expression.points}
			series = {key: self._timeseriesFor(key) for key in windowed}
			self._executor.submit(self._compute, entry, current, series, self.clock())
		except Exception as e:
			self._finished.emit((entry, Missing, f'could not read its inputs: {e!r}'))

	def _compute(self, entry: _Entry, current: dict, series: dict, now: datetime) -> None:
		"""Worker thread."""
		try:
			for timeseries in {id(s): s for s in series.values() if s is not None}.values():
				timeseries.update()
			result = entry.expression.evaluate(_SnapshotResolver(current, series), now)
			error = None
		except ExpressionError as e:
			result, error = Missing, str(e)
		except Exception as e:
			result, error = Missing, f'{entry.expression.text!r}: {type(e).__name__}: {e}'
		self._finished.emit((entry, result, error))

	@Slot(object)
	def _onFinished(self, outcome) -> None:
		entry, result, error = outcome
		entry.state = 'idle'
		if self._entries.get(entry.expression.key) is not entry:
			return  # released while running
		if error is not None and error != entry.lastError:
			entry.lastError = error
			log.error(f'computed value {entry.expression.text!r} has no value: {error}')
		self._publish(entry, result)
		if entry.stale:
			self._schedule(entry, entry.delay)

	def _publish(self, entry: _Entry, result: Any) -> None:
		key = entry.expression.key
		container = self.source.getOrCreate(key)
		if result is Missing:
			# Nothing yet: stay silent, so a panel keeps waiting. Had a value:
			# clear it, so yesterday's high does not pass for today's.
			if container.value is None or container.value.rawValue is None:
				return
			result = None
		container._update(
			result,
			timestamp=localNow(),
			metadata=dict(_METADATA),
			flags=_FLAGS,
			title=entry.expression.text,
		)
		self.source.publisher.publish({key})

	def _currentValue(self, key: CategoryItem) -> Any:
		multiSource = self._dispatcher.getContainer(key)
		if not multiSource:
			return None
		try:
			observation = multiSource.value.value
		except Exception:
			return None
		return getattr(observation, 'value', None)

	def _timeseriesFor(self, key: CategoryItem) -> Optional[MeasurementTimeSeries]:
		multiSource = self._dispatcher.getContainer(key)
		if not multiSource:
			return None
		try:
			source = multiSource.value.source
		except Exception:
			return None
		if not hasattr(source, 'observations'):
			return None  # a wire stand-in: no local history to read
		cacheKey = (source.name, key)
		if (timeseries := self._series.get(cacheKey)) is None:
			# The hourly and finer series plus the recorded log, but not the
			# daily series: a daily mean or high is not a point in the day.
			timeseries = self._series[cacheKey] = MeasurementTimeSeries(
				source, key, minPeriod=timedelta(0), maxPeriod=DAILY_CUTOFF
			)
		return timeseries


_engine: Optional[ComputedEngine] = None


def computedEngine() -> ComputedEngine:
	"""This process's engine, created on first use. Only for processes that
	run plugins (mode=live, loopback, and the backend)."""
	global _engine
	if _engine is None:
		_engine = ComputedEngine()
	return _engine


# -- public API for display code -----------------------------------------------

def _parse(text: Any, quiet: bool = False) -> Optional[Expression]:
	"""The parsed expression, or None after logging why not. ``quiet`` skips
	the log, for a release whose acquire already logged."""
	report = (lambda message: None) if quiet else log.error
	if isinstance(text, (int, float)) and not isinstance(text, bool):
		text = str(text)
	try:
		expression = Expression.parse(text)
	except ExpressionError as e:
		report(f'value source {text!r} is not valid and will show no value: {e}')
		return None
	except Exception as e:
		report(f'value source {text!r} could not be read and will show no value: {e!r}')
		return None
	if expression.usesValue:
		report(f'value source {text!r} uses `value`, which only means something in a display property; it will show no value')
		return None
	return expression


def _remote():
	return getattr(LevityDashboard.dispatcher, 'remote', None)


def acquireValueSource(text: Any) -> Optional[CategoryItem]:
	"""The key to subscribe to for the value source ``text`` from a
	``.levity`` value slot.

	A plain key comes back as itself and registers nothing. An expression is
	registered (locally, or with the backend in mode=remote) and its computed
	key comes back. A malformed expression logs an error naming the text and
	returns None. This never raises: one item's exception aborts the whole
	dashboard load.

	Every call that returns a computed key needs a matching
	``releaseValueSource`` with the same text.
	"""
	try:
		expression = _parse(text)
		if expression is None:
			return None
		if expression.plainKey is not None:
			return expression.plainKey
		if (remote := _remote()) is not None:
			remote.acquire_expression(expression)
		else:
			computedEngine().register(expression)
		return expression.key
	except Exception as e:
		log.error(f'value source {text!r} could not be registered and will show no value: {e!r}')
		return None


def releaseValueSource(text: Any) -> None:
	"""Undo one ``acquireValueSource(text)``. When nothing else uses the
	expression, it is no longer computed. Never raises."""
	try:
		expression = _parse(text, quiet=True)
		if expression is None or expression.plainKey is not None:
			return
		if (remote := _remote()) is not None:
			remote.release_expression(expression)
		elif _engine is not None:
			_engine.release(expression.key)
	except Exception as e:
		log.error(f'value source {text!r} could not be released: {e!r}')
