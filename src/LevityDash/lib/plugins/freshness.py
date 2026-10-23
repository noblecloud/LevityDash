"""How long a reading may sit before it counts as missed.

A reading is old only compared with how often its source refreshes: a BLE
thermometer that advertises every 20 s and an hourly forecast poll are both
fresh at five minutes. `RefreshEstimator` learns the period from the gaps
between updates it has seen, and `staleAfter` turns that into a threshold.

Qt-free, so the backend can share it.
"""
from collections import deque
from datetime import timedelta
from statistics import median
from typing import Deque, Optional

__all__ = ['RefreshEstimator', 'DEFAULT_STALE_AFTER', 'BURST']

#: What to use before there is anything to learn from.
DEFAULT_STALE_AFTER = timedelta(minutes=15)

#: A source is missed once it is this many periods overdue. One late poll is not a miss.
MISSED_AFTER_PERIODS = 2.5

#: Never flag a reading younger than this, however fast the source runs.
MIN_STALE_AFTER = timedelta(seconds=60)

#: Updates this close together are one update (a poll that publishes forty keys in a row).
BURST = timedelta(seconds=5)

#: A run of updates is cut into bursts of at most this long, so a source that never pauses still shows a period.
MAX_BURST = timedelta(seconds=30)


class RefreshEstimator:
	"""The period of a source, from the gaps between the updates it delivered.

	`observe` takes any clock that only goes forward, in seconds. The estimate
	is the median of the last `window` gaps, so a long outage or a burst does
	not move it far.
	"""

	def __init__(self, window: int = 8, burst: Optional[timedelta] = None):
		self._gaps: Deque[float] = deque(maxlen=window)
		self._last: Optional[float] = None
		self._burstStart: Optional[float] = None
		self._burst = burst.total_seconds() if burst else 0.0

	def observe(self, now: float) -> None:
		"""Take one update. With `burst`, updates within that many seconds of the last one join the same burst
		and the period is measured between the starts of bursts (capped at `MAX_BURST`)."""
		if self._last is None:
			self._burstStart = self._last = now
			return
		if now <= self._last:
			return
		if self._burst and now - self._last <= self._burst and now - self._burstStart <= MAX_BURST.total_seconds():
			self._last = now
			return
		self._gaps.append(now - (self._burstStart if self._burst else self._last))
		self._burstStart = self._last = now

	@property
	def period(self) -> Optional[timedelta]:
		"""The learned period, or None until two updates have arrived."""
		if not self._gaps:
			return None
		return timedelta(seconds=median(self._gaps))

	def staleAfter(self, declared: Optional[timedelta] = None) -> timedelta:
		"""How old a reading may get before a refresh counts as missed.

		`declared` is the period the source states (a forecast's `period`). The
		longer of it and the learned one wins. With neither, the default.
		"""
		known = [p for p in (declared, self.period) if p is not None and p > timedelta(0)]
		if not known:
			return DEFAULT_STALE_AFTER
		return max(max(known) * MISSED_AFTER_PERIODS, MIN_STALE_AFTER)
